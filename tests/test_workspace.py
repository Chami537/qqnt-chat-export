from pathlib import Path

import pytest

from qqnt_export.errors import SafeFailure
from qqnt_export.workspace import Workspace


def test_cleanup_refuses_unmarked_directory(tmp_path: Path) -> None:
    target = tmp_path / "foreign"
    target.mkdir()
    (target / "keep.txt").write_text("keep")
    workspace = Workspace(target, keep=False)
    with pytest.raises(SafeFailure, match="工具工作目录"):
        workspace.close(success=True)
    assert (target / "keep.txt").exists()


def test_owned_workspace_cleanup_removes_only_run_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("qqnt_export.paths.system_drive", lambda: Path("Z:/"))
    parent = tmp_path / "output"
    parent.mkdir()
    (parent / "keep.txt").write_text("keep")
    workspace = Workspace.create(parent, None, keep=False)
    (workspace.root / "snapshot.db").write_bytes(b"synthetic")
    workspace.close(success=True)
    assert not workspace.root.exists()
    assert (parent / "keep.txt").read_text() == "keep"


def test_keep_workspace_preserves_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("qqnt_export.paths.system_drive", lambda: Path("Z:/"))
    workspace = Workspace.create(tmp_path, None, keep=True)
    workspace.close(success=False)
    assert (workspace.root / ".qqnt-export-workspace.json").is_file()
