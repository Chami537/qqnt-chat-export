from __future__ import annotations

import os
import shutil
import string
from collections.abc import Iterable
from pathlib import Path

from .errors import SafeFailure
from .models import DatabaseSource
from .paths import system_drive, validate_non_system_directory


def required_work_bytes(source: DatabaseSource) -> int:
    """Conservative space estimate for snapshot, prepared copy, and plaintext."""
    files = [
        source.db_path,
        Path(str(source.db_path) + "-wal"),
        Path(str(source.db_path) + "-shm"),
    ]
    if not source.db_path.is_file():
        raise SafeFailure("discovery", "database_not_found", "QQ 数据库不存在")
    try:
        total = sum(path.stat().st_size for path in files if path.is_file())
    except OSError:
        raise SafeFailure("paths", "source_unreadable", "无法读取 QQ 数据库大小") from None
    return 3 * total + (512 << 20)


def _windows_drives() -> list[Path]:
    if os.name != "nt":
        return []
    return [drive for letter in string.ascii_uppercase if (drive := Path(f"{letter}:/")).is_dir()]


def suggest_work_root(
    source: DatabaseSource,
    drives: Iterable[Path] | None = None,
) -> Path | None:
    needed = required_work_bytes(source)
    system = system_drive().drive.casefold()
    candidates: list[tuple[int, Path]] = []
    for drive in drives if drives is not None else _windows_drives():
        resolved = drive.resolve()
        if not resolved.drive or resolved.drive.casefold() == system:
            continue
        target = resolved / "QQNTExportWork"
        if target.is_relative_to(source.db_path.parents[2].resolve()):
            continue
        try:
            free = shutil.disk_usage(resolved).free
        except OSError:
            continue
        if free >= needed:
            candidates.append((free, target))
    return max(candidates, default=(0, None), key=lambda item: item[0])[1]


def prepare_work_root(source: DatabaseSource, root: Path) -> Path:
    needed = required_work_bytes(source)
    location = validate_non_system_directory(root, source_root=source.db_path.parents[2])
    try:
        free = shutil.disk_usage(location).free
    except OSError:
        raise SafeFailure("paths", "space_unavailable", "无法检查临时目录剩余空间") from None
    if free < needed:
        raise SafeFailure("paths", "insufficient_space", "临时目录空间不足，请选择其他非系统盘位置")
    return location
