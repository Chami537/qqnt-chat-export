from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from .errors import SafeFailure
from .paths import safe_child, validate_non_system_directory


MARKER = ".qqnt-export-workspace.json"
OWNED_ARTIFACTS = frozenset({
    MARKER,
    "nt_msg.db", "nt_msg.db-wal", "nt_msg.db-shm",
    "nt_msg.key-probe.db", "nt_msg.key-probe.db-wal", "nt_msg.key-probe.db-shm",
    "nt_msg.clear.db", "nt_msg.clear.db-wal", "nt_msg.clear.db-shm", "nt_msg.clear.db-journal",
    "nt_msg_plain.db", "nt_msg_plain.db-wal", "nt_msg_plain.db-shm", "nt_msg_plain.db-journal",
})


@dataclass
class Workspace:
    root: Path
    keep: bool = False
    run_id: str | None = None

    @classmethod
    def create(
        cls,
        output_dir: Path,
        requested_work_dir: Path | None,
        *,
        keep: bool,
        source_root: Path | None = None,
    ) -> "Workspace":
        output = validate_non_system_directory(output_dir, source_root=source_root)
        if requested_work_dir is None:
            parent = output / ".qqnt-export-workspaces"
            root = parent / uuid.uuid4().hex
        else:
            requested = requested_work_dir.expanduser().resolve()
            if output == requested or output.is_relative_to(requested):
                raise SafeFailure("workspace", "overlapping_output", "工作目录不能包含输出目录")
            root = validate_non_system_directory(requested_work_dir, source_root=source_root)
            if any(root.iterdir()):
                raise SafeFailure("workspace", "occupied", "工作目录必须为空")
        root.mkdir(parents=True, exist_ok=False) if requested_work_dir is None else None
        run_id = uuid.uuid4().hex
        (root / MARKER).write_text(
            json.dumps({"tool": "qqnt-export", "run_id": run_id}), encoding="utf-8"
        )
        return cls(root.resolve(), keep, run_id)

    def path_for(self, leaf: str) -> Path:
        return safe_child(self.root, leaf)

    def close(self, *, success: bool) -> None:
        if self.keep:
            return
        self._verify_marker()
        shutil.rmtree(self.root)

    def _verify_marker(self) -> None:
        root = self.root.resolve()
        if self.root.is_symlink() or root == Path(root.anchor) or not root.is_dir():
            raise SafeFailure("cleanup", "unsafe_workspace", "无法确认工具工作目录")
        marker = root / MARKER
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise SafeFailure("cleanup", "not_owned", "这不是工具工作目录") from None
        if data.get("tool") != "qqnt-export" or (self.run_id and data.get("run_id") != self.run_id):
            raise SafeFailure("cleanup", "not_owned", "这不是工具工作目录")
        try:
            contents = list(root.iterdir())
        except OSError:
            raise SafeFailure("cleanup", "unreadable_workspace", "无法检查工具工作目录") from None
        if any(item.name not in OWNED_ARTIFACTS or not item.is_file() or item.is_symlink() for item in contents):
            raise SafeFailure("cleanup", "foreign_file", "工作目录含有非工具文件，已保留整个目录")


def cleanup_marked_workspace(root: Path) -> None:
    Workspace(root, keep=False)._verify_marker()
    Workspace(root, keep=False).close(success=True)
