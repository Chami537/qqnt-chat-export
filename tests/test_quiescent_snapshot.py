from pathlib import Path

import pytest

from qqnt_export.adapters.qqnt_9_9_27 import QQNT9927Adapter
from qqnt_export.errors import ExportCancelled, SafeFailure
from qqnt_export.models import DatabaseSource
from qqnt_export.quiescent import acquire_key_before_exit, wait_for_qq_exit
from qqnt_export.workspace import Workspace


def test_key_probe_preserves_logical_size_without_copying_database(tmp_path: Path) -> None:
    db = tmp_path / "nt_msg.db"
    page = b"P" * 4096
    with db.open("wb") as handle:
        handle.write(b"H" * 1024 + page)
        handle.truncate(128 * 1024 * 1024 + 1024)
    work = tmp_path / "work"
    work.mkdir()
    workspace = Workspace(work)
    source = DatabaseSource(db, "demo", "9.9.27", 7)

    class InspectingProvider:
        def get_key(self, source, encrypted_db):
            assert encrypted_db.stat().st_size == 128 * 1024 * 1024
            with encrypted_db.open("rb") as handle:
                assert handle.read(4096) == page
                assert handle.read(4096) == b"\0" * 4096
            return bytearray(b"temporary-key")

    key = acquire_key_before_exit(source, workspace, QQNT9927Adapter(), InspectingProvider())
    assert key == b"temporary-key"
    assert not (work / "nt_msg.key-probe.db").exists()
    assert db.stat().st_size == 128 * 1024 * 1024 + 1024


def test_probe_is_removed_when_key_provider_fails(tmp_path: Path) -> None:
    db = tmp_path / "nt_msg.db"
    db.write_bytes(b"H" * 1024 + b"P" * 4096)
    work = tmp_path / "work"
    work.mkdir()

    class FailingProvider:
        def get_key(self, source, encrypted_db):
            raise SafeFailure("decrypt", "key_validation_failed", "无法验证密钥")

    with pytest.raises(SafeFailure):
        acquire_key_before_exit(
            DatabaseSource(db, "demo", "9.9.27", 7), Workspace(work),
            QQNT9927Adapter(), FailingProvider(),
        )
    assert not list(work.glob("*.db"))


def test_key_probe_removes_sqlcipher_sidecars(tmp_path: Path) -> None:
    db = tmp_path / "nt_msg.db"
    db.write_bytes(b"H" * 1024 + b"P" * 4096)
    work = tmp_path / "work"
    work.mkdir()

    class SidecarProvider:
        def get_key(self, source, encrypted_db):
            Path(str(encrypted_db) + "-wal").write_bytes(b"")
            Path(str(encrypted_db) + "-shm").write_bytes(b"X" * 32)
            return bytearray(b"temporary-key")

    acquire_key_before_exit(
        DatabaseSource(db, "demo", "9.9.27", 7), Workspace(work),
        QQNT9927Adapter(), SidecarProvider(),
    )
    assert not list(work.iterdir())


def test_wait_for_qq_exit_checks_cancel_and_timeout() -> None:
    with pytest.raises(ExportCancelled):
        wait_for_qq_exit(lambda: True, process_query=lambda: [{}], sleeper=lambda _: None)
    with pytest.raises(SafeFailure) as caught:
        wait_for_qq_exit(
            lambda: False, process_query=lambda: [{}], sleeper=lambda _: None,
            clock=iter((0.0, 901.0)).__next__, timeout=900,
        )
    assert caught.value.code == "qq_exit_timeout"


def test_wait_for_qq_exit_returns_only_after_all_qq_processes_stop() -> None:
    states = iter(([{"pid": 1}], [{"pid": 2}], []))
    wait_for_qq_exit(
        lambda: False, process_query=lambda: next(states), sleeper=lambda _: None,
    )
