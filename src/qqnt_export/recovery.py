"""Explicit selected-conversation export when whole-database validation fails."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import closing
from pathlib import Path

from .adapters.qqnt_9_9_27 import QQNT9927Adapter
from .adapters.registry import select_adapter
from .conversations import ConversationIndexEntry, _KEY_EXPRESSION, iter_selected_messages
from .decrypt import _cipher_connection, _prepare_encrypted_copy
from .errors import ExportCancelled, SafeFailure
from .exporters import export_conversation
from .models import DatabaseSource, ExportResult
from .paths import validate_non_system_directory
from .quiescent import acquire_key_before_exit, wait_for_qq_exit
from .reports import write_safe_report
from .snapshot import create_snapshot
from .work_locations import prepare_work_root
from .workspace import Workspace


def recover_selected_conversation(
    source: DatabaseSource,
    work_root: Path,
    output_root: Path,
    kind: str,
    selector: str,
    *,
    should_cancel: Callable[[], bool],
    on_stage: Callable[[str], None],
) -> ExportResult:
    """Read only one selected conversation on a stable encrypted copy.

    The report explicitly states that whole-database integrity was not checked.
    """
    if kind not in ("c2c", "group") or not selector.isascii() or not selector.isdigit() or not 1 <= len(selector) <= 20:
        raise SafeFailure("conversation", "invalid_selector", "请输入有效的 QQ 号或群号")
    adapter = select_adapter(source, [QQNT9927Adapter()])
    work_location = prepare_work_root(source, work_root)
    output = validate_non_system_directory(output_root, source_root=source.db_path.parents[2])
    if should_cancel():
        raise ExportCancelled()
    workspace = Workspace.create(work_location, None, keep=False, source_root=source.db_path.parents[2])
    key = bytearray()
    result: ExportResult | None = None
    try:
        on_stage("key_probe")
        key = acquire_key_before_exit(source, workspace, adapter)
        if should_cancel():
            raise ExportCancelled()
        on_stage("wait_qq_exit")
        wait_for_qq_exit(should_cancel)
        on_stage("snapshot")
        snapshot = create_snapshot(source, workspace, adapter)
        clear = _prepare_encrypted_copy(snapshot, workspace, adapter.decrypt_config())
        if should_cancel():
            raise ExportCancelled()

        try:
            from sqlcipher3.dbapi2 import DatabaseError, Row
        except ImportError:
            raise SafeFailure("decrypt", "missing_sqlcipher", "缺少 SQLCipher 依赖，请安装 decrypt 额外依赖") from None

        try:
            with closing(_cipher_connection(clear, bytes(key), adapter.decrypt_config())) as database:
                database.row_factory = Row
                database.execute("PRAGMA query_only=ON")
                table = "c2c_msg_table" if kind == "c2c" else "group_msg_table"
                expression = 'CAST("40030" AS TEXT)' if kind == "c2c" else _KEY_EXPRESSION
                count = database.execute(
                    f'SELECT COUNT(*) FROM "{table}" WHERE {expression} = ?', (selector,)
                ).fetchone()[0]
                if count == 0:
                    raise SafeFailure("conversation", "not_found", "未找到指定会话")
                conversation = ConversationIndexEntry(kind, selector, selector, count)
                on_stage("export")
                result = export_conversation(
                    output, conversation,
                    iter_selected_messages(database, adapter, conversation, source.account),
                    should_cancel=should_cancel,
                )
                if result.message_count != count:
                    raise SafeFailure("conversation", "count_mismatch", "会话消息数量不一致，导出已取消")
                write_safe_report(result.json_path.parent / "export_report.json", {
                    "stage": "output", "code": "selected_only", "qq_version": source.qq_version,
                    "adapter": adapter.name, "status": "partial",
                    "message_count": result.message_count, "quick_check": "not_run",
                })
                return result
        except DatabaseError:
            raise SafeFailure("decrypt", "selected_unreadable", "所选会话包含无法读取的数据库页，未生成导出") from None
    except Exception:
        if result is not None:
            for path in (result.json_path, result.markdown_path, result.json_path.parent / "export_report.json"):
                path.unlink(missing_ok=True)
            result.json_path.parent.rmdir()
        raise
    finally:
        for index in range(len(key)):
            key[index] = 0
        key.clear()
        on_stage("cleanup")
        workspace.close(success=True)
