import sqlite3

import pytest

from qqnt_export.adapters.qqnt_9_9_27 import QQNT9927Adapter
from qqnt_export.conversations import ConversationIndexEntry, build_conversation_index, iter_selected_messages, resolve_conversation
from qqnt_export.errors import SafeFailure

from fixtures.synthetic_messages import text_body


def connection() -> sqlite3.Connection:
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    for table in ("c2c_msg_table", "group_msg_table"):
        database.execute(f'CREATE TABLE {table} ("40001" INTEGER, "40013" INTEGER, "40021" INTEGER, "40030" INTEGER, "40033" INTEGER, "40050" INTEGER, "40800" BLOB)')
    for peer in (200, 100, 200):
        database.execute('INSERT INTO c2c_msg_table VALUES (?, 0, 0, ?, 42, 1767270600, ?)', (peer, peer, text_body("synthetic")))
    database.execute('INSERT INTO group_msg_table VALUES (7, 0, 300, 0, 42, 1767270600, ?)', (text_body("group"),))
    database.commit()
    return database


def test_index_groups_rows_by_conversation_and_sorts_stably() -> None:
    with connection() as database:
        index = build_conversation_index(database, QQNT9927Adapter())
    assert [(entry.kind, entry.selector, entry.message_count) for entry in index] == [
        ("c2c", "100", 1), ("c2c", "200", 2), ("group", "300", 1),
    ]


def test_resolve_requires_exactly_one_selector() -> None:
    index = [ConversationIndexEntry("c2c", "100", "100", 1)]
    with pytest.raises(SafeFailure, match="一个会话"):
        resolve_conversation(index, peer="100", group="200")
    with pytest.raises(SafeFailure, match="未找到"):
        resolve_conversation(index, peer="999", group=None)


def test_selected_message_iterator_filters_other_peers() -> None:
    with connection() as database:
        selected = resolve_conversation(build_conversation_index(database, QQNT9927Adapter()), "200", None)
        messages = list(iter_selected_messages(database, QQNT9927Adapter(), selected, "42"))
    assert len(messages) == 2
    assert all(message.content == "synthetic" for message in messages)
