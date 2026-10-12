from pathlib import Path

import pytest

from qqnt_export import paths
from qqnt_export.errors import SafeFailure


def test_rejects_system_drive_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "system_drive", lambda: Path("C:/"))
    with pytest.raises(SafeFailure, match="非系统盘"):
        paths.validate_non_system_directory(Path("C:/QQExports"))


def test_safe_child_rejects_parent_escape(tmp_path: Path) -> None:
    with pytest.raises(SafeFailure):
        paths.safe_child(tmp_path, "../escape")


def test_validate_rejects_source_tree(tmp_path: Path) -> None:
    source_root = tmp_path / "qq-data"
    source_root.mkdir()
    with pytest.raises(SafeFailure):
        paths.validate_non_system_directory(source_root / "export", source_root=source_root)
