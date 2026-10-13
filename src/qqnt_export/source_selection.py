from __future__ import annotations

from pathlib import Path

from .discovery import discover_qq_installations, windows_qq_processes
from .errors import SafeFailure
from .models import DatabaseSource


def find_sources(
    source_path: Path | None = None,
    data_root: Path | None = None,
    pid: int | None = None,
) -> list[DatabaseSource]:
    """List each database and running QQ process combination."""
    processes = windows_qq_processes()
    if pid is not None:
        processes = [item for item in processes if int(item.get("pid", 0)) == pid]
    if not processes:
        raise SafeFailure("discovery", "qq_not_running", "请先打开并登录 QQ，或检查指定的进程")

    if source_path is not None:
        paths = [source_path.expanduser().resolve()]
    else:
        roots = [data_root] if data_root is not None else None
        paths = [
            item.db_path for item in
            discover_qq_installations(lambda: processes, roots)
        ]
    if not paths or any(not path.is_file() for path in paths):
        raise SafeFailure("discovery", "database_not_found", "指定的 QQ 数据库不存在")

    return [
        DatabaseSource(
            path,
            path.parents[2].name if len(path.parents) > 2 else "",
            str(process.get("version", "")),
            int(process["pid"]),
            Path(str(process["path"])) if process.get("path") else None,
        )
        for path in dict.fromkeys(paths)
        for process in processes
    ]
