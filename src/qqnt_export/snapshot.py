from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .adapters.base import QQNTAdapter
from .errors import SafeFailure
from .models import DatabaseSource
from .workspace import Workspace


@dataclass(frozen=True)
class Snapshot:
    encrypted_db: Path
    wal: Path | None
    shm: Path | None


def _stamp(path: Path) -> tuple[int, int, int] | None:
    try:
        stat = path.stat()
        return stat.st_size, stat.st_mtime_ns, stat.st_ino
    except FileNotFoundError:
        return None


def create_snapshot(
    source: DatabaseSource,
    workspace: Workspace,
    adapter: QQNTAdapter,
    *,
    copy_function: Callable[[Path, Path], object] = shutil.copy2,
) -> Snapshot:
    paths = adapter.snapshot_paths(source)
    if not paths or paths[0] != source.db_path:
        raise SafeFailure("snapshot", "invalid_source", "数据库来源无效")
    if not source.db_path.is_file():
        raise SafeFailure("snapshot", "missing_source", "QQ 数据库不存在")
    before = {path: _stamp(path) for path in paths}
    copied: list[Path] = []
    try:
        for path in paths:
            if before[path] is None:
                continue
            destination = workspace.path_for(path.name)
            if destination.exists():
                raise SafeFailure("snapshot", "occupied_destination", "工作目录已有数据库副本")
            copy_function(path, destination)
            copied.append(destination)
        after = {path: _stamp(path) for path in paths}
        if before != after:
            raise SafeFailure("snapshot", "source_changed", "QQ 数据库在复制期间发生变化，请在 QQ 空闲时重试")
        by_name = {path.name: path for path in copied}
        db = by_name[source.db_path.name]
        return Snapshot(db, by_name.get(source.db_path.name + "-wal"), by_name.get(source.db_path.name + "-shm"))
    except SafeFailure:
        for path in copied:
            path.unlink(missing_ok=True)
        raise
    except OSError:
        for path in copied:
            path.unlink(missing_ok=True)
        raise SafeFailure("snapshot", "copy_failed", "复制 QQ 数据库失败，请检查空间与权限") from None
