from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, Signal

from qqnt_export.conversations import ConversationIndexEntry


ConversationKey = tuple[str, str]


class SessionTableModel(QAbstractTableModel):
    selection_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries: list[ConversationIndexEntry] = []
        self._selected: set[ConversationKey] = set()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 4

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return ("选择", "会话", "类型", "消息数")[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.entries):
            return None
        entry = self.entries[index.row()]
        if role == Qt.CheckStateRole and index.column() == 0:
            return Qt.Checked if (entry.kind, entry.selector) in self._selected else Qt.Unchecked
        if role == Qt.DisplayRole:
            return ("", entry.title, "私聊" if entry.kind == "c2c" else "群聊", entry.message_count)[index.column()]
        if role == Qt.UserRole:
            return (entry.kind, entry.selector)
        return None

    def flags(self, index):
        flags = super().flags(index)
        return flags | Qt.ItemIsUserCheckable if index.isValid() and index.column() == 0 else flags

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or index.column() != 0 or role != Qt.CheckStateRole:
            return False
        entry = self.entries[index.row()]
        key = (entry.kind, entry.selector)
        if value == Qt.Checked:
            self._selected.add(key)
        else:
            self._selected.discard(key)
        self.dataChanged.emit(index, index, [Qt.CheckStateRole])
        self.selection_changed.emit(len(self._selected))
        return True

    def set_sessions(self, entries: Iterable[ConversationIndexEntry]) -> None:
        self.beginResetModel()
        self.entries = list(entries)
        self._selected.clear()
        self.endResetModel()
        self.selection_changed.emit(0)

    def selected_keys(self) -> set[ConversationKey]:
        return set(self._selected)

    def select_keys(self, keys: set[ConversationKey]) -> None:
        available = {(entry.kind, entry.selector) for entry in self.entries}
        self._selected = set(keys) & available
        if self.entries:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.entries) - 1, 0), [Qt.CheckStateRole])
        self.selection_changed.emit(len(self._selected))


class ConversationFilterModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._kind = "all"
        self._search = ""

    def set_kind(self, kind: str) -> None:
        self.beginFilterChange()
        self._kind = kind
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def set_search(self, text: str) -> None:
        self.beginFilterChange()
        self._search = text.strip().casefold()
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if not isinstance(model, SessionTableModel):
            return False
        entry = model.entries[source_row]
        return (self._kind == "all" or entry.kind == self._kind) and (
            not self._search or self._search in entry.title.casefold() or self._search in entry.selector.casefold()
        )
