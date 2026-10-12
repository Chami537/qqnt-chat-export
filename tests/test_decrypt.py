import sqlite3
from pathlib import Path

import pytest

from qqnt_export.adapters.qqnt_9_9_27 import QQNT9927Adapter
from qqnt_export.decrypt import decrypt_snapshot
from qqnt_export.errors import SafeFailure
from qqnt_export.models import DatabaseSource
from qqnt_export.snapshot import Snapshot
from qqnt_export.workspace import Workspace


def fixtures(tmp_path: Path) -> tuple[Snapshot, DatabaseSource, Workspace]:
    work = tmp_path / "work"
    work.mkdir()
    encrypted = work / "nt_msg.db"
    encrypted.write_bytes(b"X" * 1024 + b"encrypted" + b"X" * (4096 - len(b"encrypted")))
    marker = work / ".qqnt-export-workspace.json"
    marker.write_text('{"tool":"qqnt-export","run_id":"test"}')
    return Snapshot(encrypted, None, None), DatabaseSource(tmp_path / "original.db", "demo", "9.9.27", 5), Workspace(work, run_id="test")


class FailingKeyProvider:
    def get_key(self, source: DatabaseSource, encrypted_db: Path) -> bytearray:
        raise RuntimeError("candidate=super-secret-key")


class FixedKeyProvider:
    def get_key(self, source: DatabaseSource, encrypted_db: Path) -> bytearray:
        return bytearray(b"synthetic-password")


def fake_executor(encrypted: Path, destination: Path, key: bytes, config: object) -> None:
    assert encrypted.read_bytes().startswith(b"encrypted")
    assert key == b"synthetic-password"
    assert config.page_size == 4096
    assert config.kdf_iter == 4000
    with sqlite3.connect(destination) as connection:
        connection.execute("CREATE TABLE item (value TEXT)")


def test_key_provider_failure_omits_secret(tmp_path: Path) -> None:
    snapshot, source, work = fixtures(tmp_path)
    with pytest.raises(SafeFailure) as caught:
        decrypt_snapshot(snapshot, source, work, QQNT9927Adapter(), FailingKeyProvider(), cipher_executor=fake_executor)
    assert "super-secret-key" not in caught.value.public_message
    assert not (work.root / "nt_msg_plain.db").exists()


def test_plain_database_stays_in_workspace(tmp_path: Path) -> None:
    snapshot, source, work = fixtures(tmp_path)
    plain = decrypt_snapshot(snapshot, source, work, QQNT9927Adapter(), FixedKeyProvider(), cipher_executor=fake_executor)
    assert plain.parent == work.root
    with sqlite3.connect(plain) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_invalid_plain_database_is_removed(tmp_path: Path) -> None:
    snapshot, source, work = fixtures(tmp_path)

    def bad_executor(encrypted: Path, destination: Path, key: bytes, config: object) -> None:
        destination.write_bytes(b"not sqlite")

    with pytest.raises(SafeFailure):
        decrypt_snapshot(snapshot, source, work, QQNT9927Adapter(), FixedKeyProvider(), cipher_executor=bad_executor)
    assert not (work.root / "nt_msg_plain.db").exists()
