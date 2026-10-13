from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from .adapters.base import QQNTAdapter
from .adapters.qqnt_9_9_27 import QQNT9927Adapter
from .adapters.registry import select_adapter
from .conversations import ConversationIndexEntry, build_conversation_index, iter_selected_messages
from .decrypt import ProcessMemoryKeyProvider, decrypt_snapshot
from .errors import ExportCancelled, SafeFailure
from .exporters import export_conversation
from .models import DatabaseSource, ExportResult
from .paths import validate_non_system_directory
from .reports import write_safe_report
from .schema import open_verified_database
from .snapshot import create_snapshot
from .work_locations import prepare_work_root
from .workspace import Workspace


ConversationKey = tuple[str, str]


@dataclass(frozen=True)
class TaskProgress:
    stage: str
    completed: int
    total: int


@dataclass(frozen=True)
class SessionOutcome:
    key: ConversationKey
    status: Literal["success", "failed", "cancelled"]
    message_count: int = 0
    public_message: str | None = None


@dataclass(frozen=True)
class BatchSummary:
    batch_dir: Path
    outcomes: tuple[SessionOutcome, ...]


def open_working_database(
    source: DatabaseSource,
    adapter: QQNTAdapter,
    workspace: Workspace,
    on_stage: Callable[[str], None] | None = None,
) -> sqlite3.Connection:
    if on_stage is not None:
        on_stage("snapshot")
    snapshot = create_snapshot(source, workspace, adapter)
    if on_stage is not None:
        on_stage("decrypt")
    provider = ProcessMemoryKeyProvider(adapter.decrypt_config())
    plain = decrypt_snapshot(snapshot, source, workspace, adapter, provider)
    return open_verified_database(plain, adapter)


def scan_conversations(
    source: DatabaseSource,
    work_root: Path,
    *,
    should_cancel: Callable[[], bool],
    on_progress: Callable[[TaskProgress], None],
) -> list[ConversationIndexEntry]:
    if should_cancel():
        raise ExportCancelled()
    adapter = select_adapter(source, [QQNT9927Adapter()])
    work_location = prepare_work_root(source, work_root)
    if should_cancel():
        raise ExportCancelled()
    workspace: Workspace | None = None
    connection: sqlite3.Connection | None = None
    try:
        workspace = Workspace.create(
            work_location, None, keep=False, source_root=source.db_path.parents[2]
        )
        connection = open_working_database(
            source, adapter, workspace,
            on_stage=lambda stage: on_progress(TaskProgress(stage, 0, 0)),
        )
        if should_cancel():
            raise ExportCancelled()
        index = build_conversation_index(connection, adapter)
        on_progress(TaskProgress("scan", len(index), len(index)))
        return index
    finally:
        if connection is not None:
            connection.close()
        try:
            on_progress(TaskProgress("cleanup", 0, 0))
        finally:
            if workspace is not None:
                workspace.close(success=True)


def _remove_completed_export(result: ExportResult, batch_dir: Path) -> None:
    directory = result.json_path.parent
    if directory.resolve().parent != batch_dir.resolve() or directory.is_symlink():
        raise SafeFailure("output", "unsafe_cleanup", "无法安全清理未完成的会话导出")
    for path in (result.json_path, result.markdown_path, directory / "export_report.json"):
        path.unlink(missing_ok=True)
    directory.rmdir()


def export_batch(
    source: DatabaseSource,
    work_root: Path,
    output_root: Path,
    selected: Sequence[ConversationKey],
    *,
    should_cancel: Callable[[], bool],
    on_progress: Callable[[TaskProgress], None],
) -> BatchSummary:
    adapter = select_adapter(source, [QQNT9927Adapter()])
    work_location = prepare_work_root(source, work_root)
    output = validate_non_system_directory(output_root, source_root=source.db_path.parents[2])
    keys = tuple(dict.fromkeys(selected))
    if not keys:
        raise SafeFailure("conversation", "empty_selection", "请至少选择一条会话")
    batch_dir = output / f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    try:
        batch_dir.mkdir(exist_ok=False)
    except OSError:
        raise SafeFailure("output", "write_failed", "无法创建本次导出目录") from None

    outcomes: list[SessionOutcome] = []
    if should_cancel():
        return BatchSummary(batch_dir, tuple(SessionOutcome(key, "cancelled") for key in keys))
    workspace: Workspace | None = None
    connection: sqlite3.Connection | None = None
    try:
        workspace = Workspace.create(
            work_location, None, keep=False, source_root=source.db_path.parents[2]
        )
        connection = open_working_database(
            source, adapter, workspace,
            on_stage=lambda stage: on_progress(TaskProgress(stage, 0, len(keys))),
        )
        index = {
            (item.kind, item.selector): item
            for item in build_conversation_index(connection, adapter)
        }
        for position, key in enumerate(keys):
            if should_cancel():
                outcomes.extend(SessionOutcome(rest, "cancelled") for rest in keys[position:])
                break
            conversation = index.get(key)
            if conversation is None:
                outcomes.append(SessionOutcome(key, "failed", public_message="会话已变化，请重新扫描"))
            else:
                result: ExportResult | None = None
                try:
                    messages = iter_selected_messages(connection, adapter, conversation, source.account)
                    result = export_conversation(
                        batch_dir, conversation, messages, should_cancel=should_cancel
                    )
                    write_safe_report(result.json_path.parent / "export_report.json", {
                        "stage": "output", "code": "complete", "qq_version": source.qq_version,
                        "adapter": adapter.name, "status": "complete",
                        "message_count": result.message_count, "quick_check": "ok",
                    })
                    outcomes.append(SessionOutcome(key, "success", result.message_count))
                except ExportCancelled:
                    outcomes.extend(SessionOutcome(rest, "cancelled") for rest in keys[position:])
                    break
                except SafeFailure as failure:
                    if result is not None:
                        _remove_completed_export(result, batch_dir)
                    outcomes.append(SessionOutcome(key, "failed", public_message=failure.public_message))
                except Exception:
                    if result is not None:
                        _remove_completed_export(result, batch_dir)
                    outcomes.append(SessionOutcome(key, "failed", public_message="该会话导出未完成"))
            on_progress(TaskProgress("export", len(outcomes), len(keys)))
        return BatchSummary(batch_dir, tuple(outcomes))
    except Exception:
        try:
            batch_dir.rmdir()
        except OSError:
            pass
        raise
    finally:
        if connection is not None:
            connection.close()
        try:
            on_progress(TaskProgress("cleanup", len(outcomes), len(keys)))
        finally:
            if workspace is not None:
                workspace.close(success=True)
