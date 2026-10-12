from __future__ import annotations

import ctypes
import os
import re
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Callable, Iterable, Protocol

from .adapters.base import DecryptConfig, QQNTAdapter
from .errors import SafeFailure
from .models import DatabaseSource
from .snapshot import Snapshot
from .workspace import Workspace


class KeyProvider(Protocol):
    def get_key(self, source: DatabaseSource, encrypted_db: Path) -> bytearray: ...


CipherExecutor = Callable[[Path, Path, bytes, DecryptConfig], None]


def _cipher_connection(path: Path, key: bytes, config: DecryptConfig):
    try:
        import sqlcipher3.dbapi2 as cipher
    except ImportError:
        raise SafeFailure("decrypt", "missing_sqlcipher", "缺少 SQLCipher 依赖，请安装 decrypt 额外依赖") from None
    connection = cipher.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA cipher_log_level=NONE")
        connection.execute(f"PRAGMA cipher_page_size={config.page_size}")
        escaped = key.decode("ascii").replace("'", "''")
        connection.execute(f"PRAGMA key='{escaped}'")
        connection.execute(f"PRAGMA kdf_iter={config.kdf_iter}")
        connection.execute(f"PRAGMA cipher_hmac_algorithm={config.hmac_algorithm}")
        connection.execute(f"PRAGMA cipher_kdf_algorithm={config.kdf_algorithm}")
        return connection
    except Exception:
        connection.close()
        raise


def verify_key(encrypted_db: Path, candidate: bytes, config: DecryptConfig) -> bool:
    try:
        with closing(_cipher_connection(encrypted_db, candidate, config)) as connection:
            connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        return True
    except Exception:
        return False


def sqlcipher_executor(encrypted: Path, destination: Path, key: bytes, config: DecryptConfig) -> None:
    with closing(_cipher_connection(encrypted, key, config)) as connection:
        connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        connection.execute("ATTACH DATABASE ? AS plaintext KEY ''", (str(destination),))
        try:
            connection.execute("SELECT sqlcipher_export('plaintext')").fetchone()
        finally:
            connection.execute("DETACH DATABASE plaintext")


def _read_process_chunks(pid: int) -> Iterable[bytes]:
    if os.name != "nt":
        raise SafeFailure("decrypt", "windows_only", "此版本仅支持 Windows")

    class MemoryInfo(ctypes.Structure):
        _fields_ = [
            ("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
            ("AllocationProtect", ctypes.c_ulong), ("RegionSize", ctypes.c_size_t),
            ("State", ctypes.c_ulong), ("Protect", ctypes.c_ulong), ("Type", ctypes.c_ulong),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.VirtualQueryEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(MemoryInfo), ctypes.c_size_t]
    kernel.VirtualQueryEx.restype = ctypes.c_size_t
    kernel.ReadProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    kernel.ReadProcessMemory.restype = ctypes.c_int
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]

    handle = kernel.OpenProcess(0x0400 | 0x0010, 0, pid)
    if not handle:
        raise SafeFailure("decrypt", "process_access", "无法只读访问 QQ 进程，请确认 QQ 正在运行")
    address = 0
    scanned = 0
    maximum_scan = 8 << 30
    try:
        region = MemoryInfo()
        while kernel.VirtualQueryEx(handle, ctypes.c_void_p(address), ctypes.byref(region), ctypes.sizeof(region)):
            start = region.BaseAddress or 0
            end = start + region.RegionSize
            readable = region.State == 0x1000 and not (region.Protect & (0x01 | 0x100))
            if readable:
                offset = start
                while offset < end:
                    amount = min(1 << 20, end - offset)
                    buffer = ctypes.create_string_buffer(amount)
                    received = ctypes.c_size_t()
                    if kernel.ReadProcessMemory(handle, ctypes.c_void_p(offset), buffer, amount, ctypes.byref(received)):
                        scanned += received.value
                        if scanned > maximum_scan:
                            raise SafeFailure("decrypt", "scan_limit", "QQ 进程内存扫描超出限制")
                        yield buffer.raw[:received.value]
                    offset += amount
            if end <= address:
                break
            address = end
    finally:
        kernel.CloseHandle(handle)


class ProcessMemoryKeyProvider:
    """Find candidates in the selected local QQ process and validate on a copy."""

    def __init__(self, config: DecryptConfig, chunks: Callable[[int], Iterable[bytes]] = _read_process_chunks) -> None:
        self.config = config
        self.chunks = chunks

    def get_key(self, source: DatabaseSource, encrypted_db: Path) -> bytearray:
        pattern = re.compile(rb"(?<![\x20-\x7e])[\x20-\x7e]{16}\x00")
        candidates: set[bytes] = set()
        carry = b""
        for part in self.chunks(source.process_id):
            combined = carry + part
            candidates.update(match.group()[:-1] for match in pattern.finditer(combined))
            carry = combined[-18:]
            if len(candidates) > 250_000:
                raise SafeFailure("decrypt", "candidate_limit", "QQ 进程候选值过多，无法安全验证")
        ordered = sorted(candidates, key=lambda value: (not value.startswith(b"#"), value))
        matches: list[bytes] = []
        for candidate in ordered:
            if verify_key(encrypted_db, candidate, self.config):
                matches.append(candidate)
                if len(matches) > 1:
                    break
        if len(matches) != 1:
            raise SafeFailure("decrypt", "key_validation_failed", "无法验证本机 QQ 数据库密钥")
        return bytearray(matches[0])


def _prepare_encrypted_copy(snapshot: Snapshot, workspace: Workspace, config: DecryptConfig) -> Path:
    clear = workspace.path_for("nt_msg.clear.db")
    if clear.exists():
        raise SafeFailure("decrypt", "occupied_destination", "工作目录已有加密副本")
    with snapshot.encrypted_db.open("rb") as original, clear.open("xb") as destination:
        original.seek(config.header_bytes)
        shutil.copyfileobj(original, destination, 8 << 20)
    if clear.stat().st_size < config.page_size:
        raise SafeFailure("decrypt", "short_database", "QQ 数据库副本不完整")
    for suffix, sibling in (("-wal", snapshot.wal), ("-shm", snapshot.shm)):
        if sibling is not None:
            shutil.copy2(sibling, Path(str(clear) + suffix))
    return clear


def decrypt_snapshot(
    snapshot: Snapshot,
    source: DatabaseSource,
    workspace: Workspace,
    adapter: QQNTAdapter,
    key_provider: KeyProvider,
    *,
    cipher_executor: CipherExecutor = sqlcipher_executor,
) -> Path:
    plain = workspace.path_for("nt_msg_plain.db")
    key_material = bytearray()
    try:
        if plain.exists():
            raise SafeFailure("decrypt", "occupied_destination", "工作目录已有明文数据库")
        config = adapter.decrypt_config()
        encrypted = _prepare_encrypted_copy(snapshot, workspace, config)
        key_material = bytearray(key_provider.get_key(source, encrypted))
        cipher_executor(encrypted, plain, bytes(key_material), config)
        with closing(sqlite3.connect(plain.as_uri() + "?mode=ro", uri=True)) as connection:
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("quick_check failed")
        return plain
    except SafeFailure:
        plain.unlink(missing_ok=True)
        raise
    except Exception:
        plain.unlink(missing_ok=True)
        raise SafeFailure("decrypt", "decryption_failed", "无法验证或解密 QQ 数据库") from None
    finally:
        for index in range(len(key_material)):
            key_material[index] = 0
        key_material.clear()
