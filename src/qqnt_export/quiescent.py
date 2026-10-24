from __future__ import annotations

import ctypes
import os
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from .adapters.base import QQNTAdapter
from .decrypt import KeyProvider, ProcessMemoryKeyProvider
from .discovery import windows_qq_processes
from .errors import ExportCancelled, SafeFailure
from .models import DatabaseSource
from .workspace import Workspace


def _mark_sparse(handle: object) -> None:
    if os.name != "nt":
        raise SafeFailure("snapshot", "sparse_unsupported", "密钥探测文件需要 Windows NTFS 工作目录")
    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.DeviceIoControl.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong,
        ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p,
    ]
    kernel.DeviceIoControl.restype = ctypes.c_int
    returned = ctypes.c_ulong()
    if not kernel.DeviceIoControl(
        msvcrt.get_osfhandle(handle.fileno()), 0x900C4, None, 0,
        None, 0, ctypes.byref(returned), None,
    ):
        raise SafeFailure("snapshot", "sparse_unsupported", "工作目录不支持稀疏文件，请使用 NTFS 磁盘")


def acquire_key_before_exit(
    source: DatabaseSource,
    workspace: Workspace,
    adapter: QQNTAdapter,
    provider: KeyProvider | None = None,
) -> bytearray:
    config = adapter.decrypt_config()
    probe = workspace.path_for("nt_msg.key-probe.db")
    artifacts = (probe, Path(str(probe) + "-wal"), Path(str(probe) + "-shm"))
    if any(path.exists() for path in artifacts):
        raise SafeFailure("snapshot", "occupied_destination", "工作目录已有密钥探测文件")
    try:
        with source.db_path.open("rb") as original:
            original.seek(0, os.SEEK_END)
            logical_size = original.tell() - config.header_bytes
            if logical_size < config.page_size or logical_size % config.page_size:
                raise SafeFailure("snapshot", "invalid_size", "QQ 数据库大小不符合加密页格式")
            original.seek(config.header_bytes)
            first_page = original.read(config.page_size)
            if len(first_page) != config.page_size:
                raise SafeFailure("snapshot", "short_database", "QQ 数据库首个加密页不完整")
        with probe.open("xb") as destination:
            _mark_sparse(destination)
            destination.write(first_page)
            destination.truncate(logical_size)
        key_provider = provider or ProcessMemoryKeyProvider(config)
        return bytearray(key_provider.get_key(source, probe))
    except OSError:
        raise SafeFailure("snapshot", "probe_failed", "无法在工作目录创建密钥探测文件") from None
    finally:
        for path in artifacts:
            path.unlink(missing_ok=True)


def wait_for_qq_exit(
    should_cancel: Callable[[], bool],
    *,
    process_query: Callable[[], Sequence[object]] = windows_qq_processes,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    timeout: float = 900,
) -> None:
    deadline = clock() + timeout
    while True:
        if should_cancel():
            raise ExportCancelled()
        if not process_query():
            return
        if clock() >= deadline:
            raise SafeFailure("snapshot", "qq_exit_timeout", "等待 QQ 退出超时，请重试")
        sleeper(1)
