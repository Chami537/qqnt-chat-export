from __future__ import annotations

import os
from pathlib import Path

from .errors import SafeFailure


def system_drive() -> Path:
    return Path(os.environ.get("SystemDrive", "C:") + "/")


def safe_child(root: Path, leaf: str) -> Path:
    resolved_root = root.resolve()
    candidate = (resolved_root / leaf).resolve()
    if candidate.parent != resolved_root:
        raise SafeFailure("paths", "unsafe_child", "导出文件名无效")
    return candidate


def validate_non_system_directory(path: Path, *, source_root: Path | None = None) -> Path:
    resolved = path.expanduser().resolve()
    drive = resolved.drive.casefold()
    if not drive or drive == system_drive().drive.casefold():
        raise SafeFailure("paths", "system_drive", "请选择非系统盘输出目录")
    if source_root is not None and resolved.is_relative_to(source_root.resolve()):
        raise SafeFailure("paths", "source_tree", "输出目录不能位于 QQ 数据目录内")
    if resolved == Path(resolved.anchor):
        raise SafeFailure("paths", "drive_root", "请选择非系统盘上的子目录")
    try:
        resolved.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise SafeFailure("paths", "unwritable", "无法创建输出目录") from None
    if not resolved.is_dir():
        raise SafeFailure("paths", "unwritable", "输出目录不可用")
    return resolved
