from pathlib import Path
from types import SimpleNamespace

import pytest

from qqnt_export import work_locations
from qqnt_export.errors import SafeFailure
from qqnt_export.models import DatabaseSource
from qqnt_export.work_locations import prepare_work_root, required_work_bytes, suggest_work_root


def _source(tmp_path: Path) -> DatabaseSource:
    db = tmp_path / "account" / "nt_qq" / "nt_db" / "nt_msg.db"
    db.parent.mkdir(parents=True)
    db.write_bytes(b"x" * 1024)
    Path(str(db) + "-wal").write_bytes(b"w" * 20)
    Path(str(db) + "-shm").write_bytes(b"s" * 10)
    return DatabaseSource(db, "synthetic", "9.9.27", 7)


def test_space_estimate_covers_three_copies_and_margin(tmp_path: Path) -> None:
    assert required_work_bytes(_source(tmp_path)) == 3 * (1024 + 20 + 10) + (512 << 20)


def test_system_drive_is_never_suggested(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _source(tmp_path)
    monkeypatch.setattr(work_locations, "system_drive", lambda: Path("C:/"))
    assert suggest_work_root(source, drives=[Path("C:/")]) is None


def test_insufficient_non_system_drive_is_not_suggested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path)
    monkeypatch.setattr(work_locations, "system_drive", lambda: Path("C:/"))
    monkeypatch.setattr(work_locations.shutil, "disk_usage", lambda path: SimpleNamespace(free=1024))
    assert suggest_work_root(source, drives=[Path("E:/")]) is None


def test_prepare_rejects_system_drive_before_creating_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path)
    monkeypatch.setattr("qqnt_export.paths.system_drive", lambda: tmp_path)
    target = tmp_path / "new-work"
    with pytest.raises(SafeFailure, match="非系统盘"):
        prepare_work_root(source, target)
    assert not target.exists()


def test_prepare_rejects_source_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _source(tmp_path)
    monkeypatch.setattr("qqnt_export.paths.system_drive", lambda: Path("Z:/"))
    target = source.db_path.parents[2] / "work"
    with pytest.raises(SafeFailure, match="QQ 数据目录"):
        prepare_work_root(source, target)
    assert not target.exists()


def test_prepare_rejects_insufficient_space_before_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path)
    original = source.db_path.read_bytes()
    monkeypatch.setattr("qqnt_export.paths.system_drive", lambda: Path("Z:/"))
    monkeypatch.setattr(work_locations.shutil, "disk_usage", lambda path: SimpleNamespace(free=1024))
    with pytest.raises(SafeFailure, match="空间"):
        prepare_work_root(source, tmp_path / "work")
    assert source.db_path.read_bytes() == original
