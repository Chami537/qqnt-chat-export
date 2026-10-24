import os
import time
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtCore import QThread
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from qqnt_export.conversations import ConversationIndexEntry
from qqnt_export.gui.session_model import ConversationFilterModel, SessionTableModel
from qqnt_export.gui.window import MainWindow
from qqnt_export.errors import ExportCancelled, SafeFailure
from qqnt_export.models import DatabaseSource
from qqnt_export.models import ExportResult
from qqnt_export.services import BatchSummary, SessionOutcome, TaskProgress


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def entries():
    return [
        ConversationIndexEntry("c2c", "100", "联系人甲", 3),
        ConversationIndexEntry("group", "200", "群甲", 7),
        ConversationIndexEntry("c2c", "300", "联系人乙", 5),
    ]


def test_model_selection_survives_filter_and_search(qapp):
    model = SessionTableModel()
    model.set_sessions(entries())
    model.select_keys({("c2c", "100")})
    proxy = ConversationFilterModel()
    proxy.setSourceModel(model)
    proxy.set_kind("group")
    assert proxy.rowCount() == 1
    assert model.selected_keys() == {("c2c", "100")}
    proxy.set_kind("all")
    proxy.set_search("联系人乙")
    assert proxy.rowCount() == 1
    assert model.selected_keys() == {("c2c", "100")}


def test_visible_select_adds_only_filtered_rows(qapp):
    window = MainWindow()
    window.set_sessions(entries())
    window.session_model.select_keys({("c2c", "100")})
    window.filter_model.set_kind("group")
    window.select_visible()
    assert window.session_model.selected_keys() == {("c2c", "100"), ("group", "200")}
    window.close()


def test_source_change_clears_previous_selection(qapp):
    window = MainWindow()
    window.set_source_identity("account-one")
    window.set_sessions(entries())
    window.session_model.select_keys({("c2c", "100")})
    window.set_source_identity("account-two")
    assert window.session_model.selected_keys() == set()
    assert window.session_model.rowCount() == 0
    window.close()


def test_export_disabled_without_selection(qapp):
    window = MainWindow()
    window.set_sessions([])
    assert not window.export_button.isEnabled()
    window.set_sessions(entries())
    assert not window.export_button.isEnabled()
    window.session_model.select_keys({("c2c", "100")})
    assert window.export_button.isEnabled()
    window.close()


def _wait_for(qapp, predicate, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    pytest.fail("background task did not finish")


def test_scan_keeps_ui_responsive_and_cancel_stops_worker(qapp, tmp_path):
    started = threading.Event()
    saw_cancel = threading.Event()

    def slow_scan(source, root, *, should_cancel, on_progress):
        started.set()
        while not should_cancel():
            time.sleep(0.01)
        saw_cancel.set()
        raise ExportCancelled()

    window = MainWindow(scan_service=slow_scan)
    window.show()
    source = DatabaseSource(tmp_path / "nt_msg.db", "synthetic", "9.9.27", 1)
    window.start_scan(source, tmp_path / "work")
    _wait_for(qapp, started.is_set)
    assert not window.scan_button.isEnabled()
    ticked = threading.Event()
    QTimer.singleShot(0, ticked.set)
    _wait_for(qapp, ticked.is_set)
    window.cancel_button.click()
    _wait_for(qapp, lambda: not window._task_running)
    assert saw_cancel.is_set()
    window.close()


def test_close_waits_for_worker_cleanup(qapp, tmp_path):
    started = threading.Event()

    def slow_scan(source, root, *, should_cancel, on_progress):
        started.set()
        while not should_cancel():
            time.sleep(0.01)
        raise ExportCancelled()

    window = MainWindow(scan_service=slow_scan)
    window.show()
    window.start_scan(DatabaseSource(tmp_path / "nt_msg.db", "synthetic", "9.9.27", 1), tmp_path / "work")
    _wait_for(qapp, started.is_set)
    window.close()
    assert window.isVisible()
    _wait_for(qapp, lambda: not window.isVisible())


def test_safe_worker_error_exposes_only_public_message(qapp, tmp_path):
    def fail_scan(source, root, *, should_cancel, on_progress):
        raise SafeFailure("decrypt", "secret-path", "无法解密数据库")

    window = MainWindow(scan_service=fail_scan)
    window.start_scan(DatabaseSource(tmp_path / "private-value" / "nt_msg.db", "synthetic", "9.9.27", 1), tmp_path / "work")
    _wait_for(qapp, lambda: not window._task_running)
    assert "无法解密数据库" in window.result_label.text()
    assert "private-value" not in window.result_label.text()
    window.close()


def test_cancel_control_reenabled_for_next_task(qapp, tmp_path):
    started = threading.Event()

    def slow_scan(source, root, *, should_cancel, on_progress):
        started.set()
        while not should_cancel():
            time.sleep(0.01)
        raise ExportCancelled()

    window = MainWindow(scan_service=slow_scan)
    source = DatabaseSource(tmp_path / "nt_msg.db", "synthetic", "9.9.27", 1)
    window.start_scan(source, tmp_path / "work")
    _wait_for(qapp, started.is_set)
    window.cancel_button.click()
    _wait_for(qapp, lambda: not window._task_running)
    started.clear()
    window.start_scan(source, tmp_path / "work")
    _wait_for(qapp, started.is_set)
    assert window.cancel_button.isEnabled()
    window.cancel_button.click()
    _wait_for(qapp, lambda: not window._task_running)
    window.close()


def test_source_disappearance_clears_old_conversations(qapp, tmp_path):
    window = MainWindow()
    source = DatabaseSource(tmp_path / "nt_msg.db", "synthetic", "9.9.27", 1)
    window.set_sources([source])
    window.set_sessions(entries())
    window.session_model.select_keys({("c2c", "100")})
    window.set_sources([])
    assert window.session_model.rowCount() == 0
    assert window.session_model.selected_keys() == set()
    window.close()


def test_export_updates_result_on_main_thread(qapp, tmp_path):
    output = tmp_path / "out"
    output.mkdir()
    seen = []

    def fake_export(source, work_root, output_root, selected, *, should_cancel, on_progress):
        on_progress(TaskProgress("export", 1, 2))
        return BatchSummary(output, (
            SessionOutcome(("c2c", "100"), "success", 3),
            SessionOutcome(("group", "200"), "failed", public_message="合成失败"),
        ))

    class CheckingWindow(MainWindow):
        def _on_progress(self, progress):
            seen.append(QThread.currentThread() is qapp.thread())
            super()._on_progress(progress)

    window = CheckingWindow(export_service=fake_export)
    window.show()
    window.set_sessions(entries())
    source = DatabaseSource(tmp_path / "nt_msg.db", "synthetic", "9.9.27", 1)
    window.start_export(source, tmp_path / "work", output, [("c2c", "100"), ("group", "200")])
    _wait_for(qapp, lambda: not window._task_running)
    assert seen == [True]
    assert "成功 1，失败 1" in window.result_label.text()
    result_lines = [window.result_list.item(row).text() for row in range(window.result_list.count())]
    assert any("联系人甲" in line and "成功" in line for line in result_lines)
    assert any("群甲" in line and "失败" in line and "合成失败" in line for line in result_lines)
    assert window.open_output_button.isVisible()
    window.close()


def test_recovery_controls_and_result_warning(qapp, tmp_path):
    output = tmp_path / "recovered"
    output.mkdir()
    json_path = output / "chat_export.json"
    md_path = output / "chat_export.md"
    json_path.write_text("[]", encoding="utf-8")
    md_path.write_text("# test", encoding="utf-8")

    def fake_recover(source, work, destination, kind, selector, *, should_cancel, on_stage):
        assert (kind, selector) == ("c2c", "100")
        on_stage("export")
        return ExportResult(json_path, md_path, 3)

    window = MainWindow(recover_service=fake_recover)
    window.show()
    source = DatabaseSource(tmp_path / "nt_msg.db", "synthetic", "9.9.27", 1)
    window.set_sources([source])
    assert window.recover_button.isEnabled()
    window.start_recovery(source, tmp_path / "work", tmp_path / "out", "100")
    _wait_for(qapp, lambda: not window._task_running)
    assert "3 条" in window.result_label.text()
    assert "未验证整库" in window.result_label.text()
    assert window.open_output_button.isVisible()
    window.close()


def test_space_checks_conversation_in_view(qapp):
    window = MainWindow()
    window.set_sessions(entries())
    window.show()
    window.table.setFocus()
    window.table.setCurrentIndex(window.filter_model.index(0, 0))
    QTest.keyClick(window.table, Qt.Key_Space)
    qapp.processEvents()
    assert window.session_model.selected_keys() == {("c2c", "100")}
    assert window.export_button.isEnabled()
    window.close()


def test_multiple_processes_require_explicit_source_choice(qapp, tmp_path):
    window = MainWindow()
    db = tmp_path / "nt_msg.db"
    db.write_bytes(b"synthetic")
    window.set_sources([
        DatabaseSource(db, "synthetic", "9.9.27", 7),
        DatabaseSource(db, "synthetic", "9.9.27", 8),
    ])
    assert window.selected_source() is None
    assert not window.scan_button.isEnabled()
    window.source_combo.setCurrentIndex(2)
    assert window.selected_source().process_id == 8
    assert window.scan_button.isEnabled()
    window.close()


def test_refresh_recovers_after_qq_starts(qapp, tmp_path):
    db = tmp_path / "nt_msg.db"
    db.write_bytes(b"synthetic")
    calls = 0

    def discover():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise SafeFailure("discovery", "qq_not_running", "请先打开并登录 QQ")
        return [DatabaseSource(db, "synthetic", "9.9.27", 7)]

    window = MainWindow(discover_service=discover)
    window.show()
    window.refresh_sources()
    _wait_for(qapp, lambda: not window._task_running)
    assert not window.scan_button.isEnabled()
    assert window.refresh_button.isEnabled()
    window.refresh_button.click()
    _wait_for(qapp, lambda: not window._task_running)
    assert window.selected_source().process_id == 7
    assert window.scan_button.isEnabled()
    window.close()
