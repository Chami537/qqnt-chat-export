import sqlite3
from pathlib import Path

import pytest

from qqnt_export.adapters.qqnt_9_9_27 import QQNT9927Adapter
from qqnt_export.errors import SafeFailure
from qqnt_export.schema import open_verified_database


def test_schema_rejects_missing_message_table(tmp_path: Path) -> None:
    path = tmp_path / "plain.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE other (x TEXT)")
    with pytest.raises(SafeFailure, match="数据库结构"):
        open_verified_database(path, QQNT9927Adapter())


def test_schema_rejects_missing_required_column(tmp_path: Path) -> None:
    path = tmp_path / "plain.db"
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE c2c_msg_table ("40001" INTEGER)')
        connection.execute('CREATE TABLE group_msg_table ("40001" INTEGER)')
    with pytest.raises(SafeFailure, match="数据库结构"):
        open_verified_database(path, QQNT9927Adapter())
