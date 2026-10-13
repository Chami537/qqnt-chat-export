from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable, Iterable
from pathlib import Path

from .conversations import ConversationIndexEntry
from .errors import ExportCancelled, SafeFailure
from .models import ExportResult, NormalizedMessage


_NON_TEXT_MARKERS = {
    "media": "[媒体消息]", "emoji": "[表情消息]", "quote": "[引用消息]",
    "system": "[系统消息]", "unknown": "[未识别消息结构]",
}


def _safe_title(value: str) -> str:
    cleaned = " ".join(value.splitlines()).strip()
    return cleaned.replace("\\", "\\\\").replace("#", "\\#") or "未知会话"


def _markdown_message_content(message: NormalizedMessage) -> str:
    body = message.content if message.content is not None else _NON_TEXT_MARKERS.get(message.content_type, "[非文本消息]")
    return "\n".join("\\" + line if line.lstrip().startswith(("#", ">", "- ", "* ")) else line for line in body.splitlines())


def _record(message: NormalizedMessage) -> dict[str, object]:
    record: dict[str, object] = {
        "time": message.occurred_at.isoformat() if message.occurred_at else None,
        "sender": message.sender_role,
        "content_type": message.content_type,
        "content": message.content,
    }
    if message.message_id is not None:
        record["message_id"] = message.message_id
    if message.raw_fallback is not None:
        record["raw_fallback"] = dict(message.raw_fallback)
    return record


def export_conversation(
    output_dir: Path,
    conversation: ConversationIndexEntry,
    messages: Iterable[NormalizedMessage],
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> ExportResult:
    if conversation.kind not in ("c2c", "group"):
        raise SafeFailure("output", "invalid_conversation", "会话类型无效")
    digest = hashlib.sha256(conversation.selector.encode("utf-8")).hexdigest()[:12]
    directory = output_dir.resolve() / f"{conversation.kind}_{digest}"
    try:
        directory.mkdir()
    except FileExistsError:
        raise SafeFailure("output", "already_exists", "该会话的导出目录已存在，请另选输出目录") from None
    except OSError:
        raise SafeFailure("output", "write_failed", "无法创建导出目录，请检查空间和权限") from None
    json_path = directory / "chat_export.json"
    markdown_path = directory / "chat_export.md"
    if json_path.exists() or markdown_path.exists():
        raise SafeFailure("output", "already_exists", "该会话的导出文件已存在，请另选输出目录")
    nonce = uuid.uuid4().hex
    temp_json = directory / f".chat_export.{nonce}.json.tmp"
    temp_markdown = directory / f".chat_export.{nonce}.md.tmp"
    count = 0
    current_date: str | None = None
    created: list[Path] = []
    completed = False
    try:
        if should_cancel is not None and should_cancel():
            raise ExportCancelled()
        with temp_json.open("x", encoding="utf-8", newline="\n") as json_file, temp_markdown.open("x", encoding="utf-8", newline="\n") as markdown_file:
            json_file.write("[\n")
            markdown_file.write(f"# 与 {_safe_title(conversation.title)} 的聊天记录\n\n")
            for message in messages:
                if should_cancel is not None and should_cancel():
                    raise ExportCancelled()
                if count:
                    json_file.write(",\n")
                json_file.write(json.dumps(_record(message), ensure_ascii=False, separators=(",", ":")))
                date = message.occurred_at.date().isoformat() if message.occurred_at else "未知日期"
                if date != current_date:
                    markdown_file.write(f"## {date}\n\n")
                    current_date = date
                time = message.occurred_at.strftime("%H:%M") if message.occurred_at else "??:??"
                sender = {"self": "我", "peer": "对方", "member": "群成员"}[message.sender_role]
                markdown_file.write(f"{time} {sender}：\n{_markdown_message_content(message)}\n\n")
                count += 1
            json_file.write("\n]\n")
        if should_cancel is not None and should_cancel():
            raise ExportCancelled()
        if json_path.exists() or markdown_path.exists():
            raise SafeFailure("output", "already_exists", "该会话的导出文件已存在，请另选输出目录")
        temp_json.rename(json_path)
        created.append(json_path)
        temp_markdown.rename(markdown_path)
        created.append(markdown_path)
        completed = True
        return ExportResult(json_path, markdown_path, count)
    except SafeFailure:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    except (OSError, TypeError, ValueError, KeyError):
        for path in created:
            path.unlink(missing_ok=True)
        raise SafeFailure("output", "write_failed", "无法写入导出文件，请检查空间和权限") from None
    finally:
        temp_json.unlink(missing_ok=True)
        temp_markdown.unlink(missing_ok=True)
        if not completed:
            try:
                directory.rmdir()
            except OSError:
                pass
