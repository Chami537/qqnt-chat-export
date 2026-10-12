from __future__ import annotations

import sqlite3
from pathlib import Path

from .adapters.base import QQNTAdapter
from .errors import SafeFailure


def open_verified_database(path: Path, adapter: QQNTAdapter) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        sources = adapter.message_sources(connection)
        required = {source.table for source in sources}
        if not required.issubset(tables):
            raise ValueError("missing message tables")
        columns_required = {"40001", "40013", "40030", "40033", "40050", "40800"}
        for source in sources:
            columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{source.table}")')}
            required_for_source = columns_required | ({"40021"} if source.kind == "group" else set())
            if not required_for_source.issubset(columns):
                raise ValueError("missing message columns")
        return connection
    except (sqlite3.Error, ValueError, OSError):
        if "connection" in locals():
            connection.close()
        raise SafeFailure("schema", "adapter_schema_mismatch", "解密后的数据库结构与 QQ 版本适配器不匹配") from None
