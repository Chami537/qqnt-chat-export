import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from qqnt_export.conversations import ConversationIndexEntry
from qqnt_export.gui.session_model import ConversationFilterModel, SessionTableModel
from qqnt_export.gui.window import MainWindow


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
