from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from .adapters.base import QQNTAdapter
from .errors import SafeFailure
from .messages import iter_messages
from .models import NormalizedMessage


@dataclass(frozen=True)
class ConversationIndexEntry:
    kind: str
    selector: str
    title: str
    message_count: int


_KEY_EXPRESSION = (
    'CASE WHEN "40030" IS NOT NULL AND CAST("40030" AS TEXT) NOT IN (\'0\', \'\') '
    'THEN CAST("40030" AS TEXT) ELSE CAST("40021" AS TEXT) END'
)


def _contact_titles(connection: sqlite3.Connection) -> dict[str, str]:
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "recent_contact_v3_table" not in tables:
        return {}
    columns = {row[1] for row in connection.execute('PRAGMA table_info("recent_contact_v3_table")')}
    needed = {"40030", "40093", "40094", "40095"}
    if not needed.issubset(columns):
        return {}
    titles: dict[str, str] = {}
    for row in connection.execute('SELECT "40030", "40093", "40094", "40095" FROM recent_contact_v3_table'):
        key = str(row[0] or "")
        if not key or key == "0":
            continue
        for value in (row[3], row[1], row[2]):
            if isinstance(value, str) and value.strip():
                titles[key] = value.strip()
                break
    return titles


def build_conversation_index(connection: sqlite3.Connection, adapter: QQNTAdapter) -> list[ConversationIndexEntry]:
    titles = _contact_titles(connection)
    entries: list[ConversationIndexEntry] = []
    for source in adapter.message_sources(connection):
        if source.table not in {"c2c_msg_table", "group_msg_table"}:
            raise SafeFailure("schema", "unsafe_table", "数据库结构与适配器不匹配")
        if source.kind == "c2c":
            expression = 'CAST("40030" AS TEXT)'
        elif source.kind == "group":
            expression = _KEY_EXPRESSION
        else:
            raise SafeFailure("schema", "unknown_conversation_kind", "未知会话类型")
        query = f'SELECT {expression} AS selector, COUNT(*) AS total FROM "{source.table}" GROUP BY {expression}'
        for row in connection.execute(query):
            selector = str(row[0] or "")
            if not selector or selector == "0":
                continue
            entries.append(ConversationIndexEntry(source.kind, selector, titles.get(selector, selector), int(row[1])))
    return sorted(entries, key=lambda entry: (entry.kind, entry.selector))


def resolve_conversation(
    index: Sequence[ConversationIndexEntry], peer: str | None, group: str | None
) -> ConversationIndexEntry:
    if bool(peer) == bool(group):
        raise SafeFailure("conversation", "invalid_selector", "请仅指定一个会话：私聊或群聊")
    kind, selector = ("c2c", peer) if peer else ("group", group)
    matches = [entry for entry in index if entry.kind == kind and entry.selector == selector]
    if len(matches) != 1:
        raise SafeFailure("conversation", "not_found", "未找到指定会话")
    return matches[0]


def iter_selected_messages(
    connection: sqlite3.Connection,
    adapter: QQNTAdapter,
    conversation: ConversationIndexEntry,
    account: str,
) -> Iterator[NormalizedMessage]:
    sources = {source.kind: source for source in adapter.message_sources(connection)}
    source = sources.get(conversation.kind)
    if source is None:
        raise SafeFailure("schema", "missing_source", "数据库结构与适配器不匹配")
    if conversation.kind == "c2c":
        where = 'CAST("40030" AS TEXT) = ?'
    else:
        where = _KEY_EXPRESSION + " = ?"
    yield from iter_messages(connection, source, adapter, account, where, (conversation.selector,))
