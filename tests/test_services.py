import json
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock

import pytest

from qqnt_export import services
from qqnt_export.decrypt import decrypt_snapshot as actual_decrypt
from qqnt_export.errors import ExportCancelled, SafeFailure
from qqnt_export.models import DatabaseSource
from qqnt_export.reports import write_safe_report as actual_write_report
from fixtures.synthetic_messages import text_body


@pytest.fixture
def synthetic_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DatabaseSource:
    db = tmp_path / "account" / "nt_qq" / "nt_db" / "nt_msg.db"
    db.parent.mkdir(parents=True)
    header = bytearray(1024)
    header[:16] = b"SQLite header 3\x00"
    header[32:40] = b"QQ_NT DB"
    db.write_bytes(header + b"X" * 4096)
    monkeypatch.setattr("qqnt_export.paths.system_drive", lambda: Path("Z:/"))

    class FixedKey:
        def get_key(self, source, encrypted):
            return bytearray(b"synthetic-password")

    def fake_cipher(encrypted, destination, key, config):
        assert encrypted.read_bytes() == b"X" * 4096
        with closing(sqlite3.connect(destination)) as connection:
            for table in ("c2c_msg_table", "group_msg_table"):
                connection.execute(
                    f'CREATE TABLE {table} ("40001" INTEGER, "40013" INTEGER, "40021" INTEGER, '
                    '"40030" INTEGER, "40033" INTEGER, "40050" INTEGER, "40800" BLOB)'
                )
            connection.execute(
                'INSERT INTO c2c_msg_table VALUES (1, 0, 0, 100, 42, 1767270600, ?)',
                (text_body("private synthetic"),),
            )
            connection.execute(
                'INSERT INTO group_msg_table VALUES (2, 0, 200, 0, 99, 1767270660, ?)',
                (text_body("group synthetic"),),
            )
            connection.commit()

    monkeypatch.setattr(services, "ProcessMemoryKeyProvider", lambda config: FixedKey())
    monkeypatch.setattr(
        services, "decrypt_snapshot",
        lambda snapshot, source, workspace, adapter, provider: actual_decrypt(
            snapshot, source, workspace, adapter, provider, cipher_executor=fake_cipher
        ),
    )
    return DatabaseSource(db, "42", "9.9.27", 7)


def test_scan_cleans_plaintext_workspace(
    synthetic_source: DatabaseSource, tmp_path: Path
) -> None:
    original = synthetic_source.db_path.read_bytes()
    index = services.scan_conversations(
        synthetic_source, tmp_path / "work",
        should_cancel=lambda: False, on_progress=lambda event: None,
    )
    assert {(item.kind, item.selector) for item in index} == {("c2c", "100"), ("group", "200")}
    assert not list((tmp_path / "work").rglob("*.db"))
    assert synthetic_source.db_path.read_bytes() == original


def test_batch_reuses_one_snapshot_and_exports_two_conversations(
    synthetic_source: DatabaseSource, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    snapshot_spy = Mock(wraps=services.create_snapshot)
    monkeypatch.setattr(services, "create_snapshot", snapshot_spy)
    summary = services.export_batch(
        synthetic_source, tmp_path / "work", tmp_path / "out",
        [("c2c", "100"), ("group", "200")],
        should_cancel=lambda: False, on_progress=lambda event: None,
    )
    assert snapshot_spy.call_count == 1
    assert [item.status for item in summary.outcomes] == ["success", "success"]
    assert len(list(summary.batch_dir.rglob("chat_export.json"))) == 2
    assert len(list(summary.batch_dir.rglob("chat_export.md"))) == 2
    assert len(list(summary.batch_dir.rglob("export_report.json"))) == 2
    assert not list((tmp_path / "work").rglob("*.db"))


def test_missing_selected_conversation_does_not_block_next(
    synthetic_source: DatabaseSource, tmp_path: Path
) -> None:
    summary = services.export_batch(
        synthetic_source, tmp_path / "work", tmp_path / "out",
        [("c2c", "999"), ("group", "200")],
        should_cancel=lambda: False, on_progress=lambda event: None,
    )
    assert [item.status for item in summary.outcomes] == ["failed", "success"]
    assert len(list(summary.batch_dir.rglob("chat_export.json"))) == 1


def test_one_export_failure_does_not_block_next(
    synthetic_source: DatabaseSource, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    real_export = services.export_conversation

    def fail_first(output, conversation, messages, **kwargs):
        if conversation.kind == "c2c":
            raise SafeFailure("output", "synthetic_failure", "合成导出失败")
        return real_export(output, conversation, messages, **kwargs)

    monkeypatch.setattr(services, "export_conversation", fail_first)
    summary = services.export_batch(
        synthetic_source, tmp_path / "work", tmp_path / "out",
        [("c2c", "100"), ("group", "200")],
        should_cancel=lambda: False, on_progress=lambda event: None,
    )
    assert [item.status for item in summary.outcomes] == ["failed", "success"]
    assert len(list(summary.batch_dir.rglob("chat_export.json"))) == 1


def test_report_failure_removes_only_its_conversation_files(
    synthetic_source: DatabaseSource, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fail_first(path, report):
        if path.parent.name.startswith("c2c_"):
            raise SafeFailure("output", "write_failed", "无法写入安全报告")
        return actual_write_report(path, report)

    monkeypatch.setattr(services, "write_safe_report", fail_first)
    summary = services.export_batch(
        synthetic_source, tmp_path / "work", tmp_path / "out",
        [("c2c", "100"), ("group", "200")],
        should_cancel=lambda: False, on_progress=lambda event: None,
    )
    assert [item.status for item in summary.outcomes] == ["failed", "success"]
    assert len(list(summary.batch_dir.rglob("chat_export.json"))) == 1
    assert len(list(summary.batch_dir.rglob("export_report.json"))) == 1


def test_cancel_after_first_conversation_leaves_completed_output(
    synthetic_source: DatabaseSource, tmp_path: Path
) -> None:
    cancelled = False

    def progress(event):
        nonlocal cancelled
        if event.stage == "export" and event.completed == 1:
            cancelled = True

    summary = services.export_batch(
        synthetic_source, tmp_path / "work", tmp_path / "out",
        [("c2c", "100"), ("group", "200")],
        should_cancel=lambda: cancelled, on_progress=progress,
    )
    assert [item.status for item in summary.outcomes] == ["success", "cancelled"]
    assert len(list(summary.batch_dir.rglob("chat_export.json"))) == 1
    assert not list((tmp_path / "work").rglob("*.db"))


def test_scan_cancelled_before_snapshot_creates_no_workspace(
    synthetic_source: DatabaseSource, tmp_path: Path
) -> None:
    with pytest.raises(ExportCancelled):
        services.scan_conversations(
            synthetic_source, tmp_path / "work",
            should_cancel=lambda: True, on_progress=lambda event: None,
        )
    assert not (tmp_path / "work").exists()


def test_snapshot_failure_removes_empty_batch_and_plaintext_workspace(
    synthetic_source: DatabaseSource, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        services, "create_snapshot",
        lambda *args: (_ for _ in ()).throw(SafeFailure("snapshot", "synthetic", "合成快照失败")),
    )
    with pytest.raises(SafeFailure):
        services.export_batch(
            synthetic_source, tmp_path / "work", tmp_path / "out", [("c2c", "100")],
            should_cancel=lambda: False, on_progress=lambda event: None,
        )
    assert not list((tmp_path / "out").glob("batch_*"))
    assert not list((tmp_path / "work").rglob("*.db"))


def test_scan_cancel_after_snapshot_skips_decryption(
    synthetic_source: DatabaseSource, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cancelled = False

    def progress(event):
        nonlocal cancelled
        if event.stage == "decrypt":
            cancelled = True

    monkeypatch.setattr(services, "decrypt_snapshot", lambda *args: pytest.fail("decryption ran after cancel"))
    with pytest.raises(ExportCancelled):
        services.scan_conversations(
            synthetic_source, tmp_path / "work",
            should_cancel=lambda: cancelled, on_progress=progress,
        )
    assert not list((tmp_path / "work").rglob("*.db"))


def test_batch_cancel_after_snapshot_marks_all_selected_cancelled(
    synthetic_source: DatabaseSource, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cancelled = False

    def progress(event):
        nonlocal cancelled
        if event.stage == "decrypt":
            cancelled = True

    monkeypatch.setattr(services, "decrypt_snapshot", lambda *args: pytest.fail("decryption ran after cancel"))
    summary = services.export_batch(
        synthetic_source, tmp_path / "work", tmp_path / "out",
        [("c2c", "100"), ("group", "200")],
        should_cancel=lambda: cancelled, on_progress=progress,
    )
    assert [item.status for item in summary.outcomes] == ["cancelled", "cancelled"]
    assert not list((tmp_path / "work").rglob("*.db"))


def test_changed_source_waits_for_qq_exit_before_retrying_snapshot(
    synthetic_source: DatabaseSource, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    real_snapshot = services.create_snapshot
    attempts = 0
    stages = []

    def changing_once(*args):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise SafeFailure("snapshot", "source_changed", "数据库发生变化")
        assert "wait_qq_exit" in stages
        return real_snapshot(*args)

    monkeypatch.setattr(services, "create_snapshot", changing_once)
    monkeypatch.setattr(services, "acquire_key_before_exit", lambda *args: bytearray(b"synthetic-password"))
    monkeypatch.setattr(services, "wait_for_qq_exit", lambda *args, **kwargs: None)
    index = services.scan_conversations(
        synthetic_source, tmp_path / "work",
        should_cancel=lambda: False,
        on_progress=lambda item: stages.append(item.stage),
    )
    assert attempts == 2
    assert len(index) == 2
    assert not list((tmp_path / "work").rglob("*.db"))


def test_changed_source_cancelled_while_waiting_leaves_no_database(
    synthetic_source: DatabaseSource, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key = bytearray(b"synthetic-password")
    monkeypatch.setattr(
        services, "create_snapshot",
        lambda *args: (_ for _ in ()).throw(SafeFailure("snapshot", "source_changed", "变化")),
    )
    monkeypatch.setattr(services, "acquire_key_before_exit", lambda *args: key)
    monkeypatch.setattr(services, "wait_for_qq_exit", lambda *args, **kwargs: (_ for _ in ()).throw(ExportCancelled()))
    with pytest.raises(ExportCancelled):
        services.scan_conversations(
            synthetic_source, tmp_path / "work",
            should_cancel=lambda: False, on_progress=lambda item: None,
        )
    assert not any(key)
    assert not list((tmp_path / "work").rglob("*.db"))
