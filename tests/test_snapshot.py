from pathlib import Path

import pytest

from qqnt_export.adapters.qqnt_9_9_27 import QQNT9927Adapter
from qqnt_export.errors import SafeFailure
from qqnt_export.models import DatabaseSource
from qqnt_export.snapshot import create_snapshot
from qqnt_export.workspace import Workspace


def make_source(tmp_path: Path) -> DatabaseSource:
    db = tmp_path / "source" / "nt_msg.db"
    db.parent.mkdir()
    db.write_bytes(b"synthetic encrypted data")
    Path(str(db) + "-wal").write_bytes(b"wal fixture")
    Path(str(db) + "-shm").write_bytes(b"shm fixture")
    return DatabaseSource(db, "demo", "9.9.27", 7)


def make_workspace(tmp_path: Path) -> Workspace:
    root = tmp_path / "work"
    root.mkdir()
    (root / ".qqnt-export-workspace.json").write_text('{"tool":"qqnt-export","run_id":"test"}')
    return Workspace(root, run_id="test")


def test_snapshot_copies_database_and_wal_without_source_change(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    before = source.db_path.read_bytes()
    snapshot = create_snapshot(source, make_workspace(tmp_path), QQNT9927Adapter())
    assert snapshot.encrypted_db.read_bytes() == before
    assert snapshot.wal is not None and snapshot.wal.read_bytes() == b"wal fixture"
    assert source.db_path.read_bytes() == before


def test_snapshot_removes_partial_copy_when_wal_changes(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    workspace = make_workspace(tmp_path)
    wal = Path(str(source.db_path) + "-wal")

    def changing_copy(src: Path, dst: Path) -> None:
        dst.write_bytes(src.read_bytes())
        if src == wal:
            wal.write_bytes(b"new WAL content")

    with pytest.raises(SafeFailure, match="复制期间发生变化"):
        create_snapshot(source, workspace, QQNT9927Adapter(), copy_function=changing_copy)
    assert not list(workspace.root.glob("*.db"))
    assert not list(workspace.root.glob("*-wal"))


def test_snapshot_accepts_absent_wal(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    Path(str(source.db_path) + "-wal").unlink()
    Path(str(source.db_path) + "-shm").unlink()
    snapshot = create_snapshot(source, make_workspace(tmp_path), QQNT9927Adapter())
    assert snapshot.wal is None and snapshot.shm is None
