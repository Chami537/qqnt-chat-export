from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QTableView, QVBoxLayout, QWidget, QHeaderView,
)

from qqnt_export.conversations import ConversationIndexEntry
from qqnt_export.models import DatabaseSource
from .session_model import ConversationFilterModel, SessionTableModel
from .theme import STYLE, ui_font


class MainWindow(QMainWindow):
    source_selected = Signal(object)
    scan_requested = Signal()
    export_requested = Signal()
    cancel_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("QQNT 聊天记录导出")
        self.resize(1120, 760)
        self.setMinimumSize(880, 610)
        self.setStyleSheet(STYLE)
        self.setFont(ui_font())
        self._source_identity: object = None
        self._sources: list[DatabaseSource] = []
        self.session_model = SessionTableModel(self)
        self.filter_model = ConversationFilterModel(self)
        self.filter_model.setSourceModel(self.session_model)

        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(190)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(20, 27, 20, 22)
        brand = QLabel("QQNT Export")
        brand.setObjectName("section")
        side.addWidget(brand)
        side.addSpacing(32)
        side.addWidget(QLabel("●  导出聊天记录"))
        side.addSpacing(16)
        help_button = QPushButton("使用说明")
        help_button.clicked.connect(self._show_help)
        side.addWidget(help_button)
        side.addStretch()
        side.addWidget(QLabel("仅在本机处理数据"))
        outer.addWidget(sidebar)

        main = QWidget()
        main.setObjectName("mainPanel")
        body = QVBoxLayout(main)
        body.setContentsMargins(28, 24, 28, 22)
        body.setSpacing(16)
        title = QLabel("导出聊天记录")
        title.setObjectName("heading")
        body.addWidget(title)
        subtitle = QLabel("选择 QQ 数据源，扫描会话，再批量导出 Markdown 与 JSON")
        subtitle.setObjectName("muted")
        body.addWidget(subtitle)

        source_card = QFrame()
        source_card.setObjectName("card")
        source_layout = QVBoxLayout(source_card)
        source_layout.setContentsMargins(18, 16, 18, 16)
        source_layout.setSpacing(10)
        source_heading = QLabel("数据源与工作位置")
        source_heading.setObjectName("section")
        source_layout.addWidget(source_heading)
        source_row = QHBoxLayout()
        self.source_combo = QComboBox()
        self.source_combo.setMinimumWidth(300)
        self.source_combo.addItem("正在查找 QQ 数据源…", None)
        self.source_combo.currentIndexChanged.connect(self._source_changed)
        source_row.addWidget(self.source_combo, 1)
        self.source_browse_button = QPushButton("选择数据库")
        self.source_browse_button.clicked.connect(self._choose_source)
        source_row.addWidget(self.source_browse_button)
        source_layout.addLayout(source_row)
        work_row = QHBoxLayout()
        work_row.addWidget(QLabel("临时工作位置"))
        self.work_edit = QLineEdit()
        self.work_edit.setPlaceholderText("请选择非系统盘目录")
        work_row.addWidget(self.work_edit, 1)
        work_button = QPushButton("浏览")
        work_button.clicked.connect(self._choose_work_root)
        work_row.addWidget(work_button)
        source_layout.addLayout(work_row)
        action_row = QHBoxLayout()
        self.source_status = QLabel("请先打开并登录 QQ")
        self.source_status.setObjectName("muted")
        action_row.addWidget(self.source_status, 1)
        self.scan_button = QPushButton("扫描会话")
        self.scan_button.setEnabled(False)
        self.scan_button.clicked.connect(self.scan_requested)
        action_row.addWidget(self.scan_button)
        source_layout.addLayout(action_row)
        body.addWidget(source_card)

        list_heading = QHBoxLayout()
        section = QLabel("会话")
        section.setObjectName("section")
        list_heading.addWidget(section)
        list_heading.addStretch()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索会话名称或号码")
        self.search_edit.setMaximumWidth(260)
        self.search_edit.textChanged.connect(self.filter_model.set_search)
        list_heading.addWidget(self.search_edit)
        self.kind_combo = QComboBox()
        for title_text, kind in (("全部", "all"), ("私聊", "c2c"), ("群聊", "group")):
            self.kind_combo.addItem(title_text, kind)
        self.kind_combo.currentIndexChanged.connect(
            lambda: self.filter_model.set_kind(self.kind_combo.currentData())
        )
        list_heading.addWidget(self.kind_combo)
        body.addLayout(list_heading)

        self.table = QTableView()
        self.table.setModel(self.filter_model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(1, 430)
        self.table.setColumnWidth(2, 105)
        self.table.setColumnWidth(3, 105)
        self.table.doubleClicked.connect(self._toggle_row)
        body.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.selection_label = QLabel("已选择 0 条会话")
        bottom.addWidget(self.selection_label)
        bottom.addStretch()
        select_button = QPushButton("全选当前结果")
        select_button.clicked.connect(self.select_visible)
        bottom.addWidget(select_button)
        clear_button = QPushButton("清空选择")
        clear_button.clicked.connect(lambda: self.session_model.select_keys(set()))
        bottom.addWidget(clear_button)
        self.export_button = QPushButton("导出所选")
        self.export_button.setObjectName("primary")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_requested)
        bottom.addWidget(self.export_button)
        body.addLayout(bottom)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        body.addWidget(self.progress_bar)
        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setObjectName("muted")
        body.addWidget(self.result_label)
        self.cancel_button = QPushButton("取消任务")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.cancel_requested)
        body.addWidget(self.cancel_button, alignment=Qt.AlignRight)
        outer.addWidget(main, 1)
        self.session_model.selection_changed.connect(self._selection_changed)

    def _show_help(self):
        QMessageBox.information(self, "使用说明", "打开并登录 QQ，选择非系统盘临时目录，扫描并勾选会话。导出时选择非系统盘输出目录。")

    def _choose_source(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 nt_msg.db", "", "QQNT 数据库 (nt_msg.db)")
        if path:
            self.manual_source_path = Path(path)
            self.source_status.setText("已选择数据库；请扫描会话")
            self.source_combo.clear()
            self.source_combo.addItem("手动选择的数据库", None)
            self.set_source_identity(str(self.manual_source_path))
            self.source_selected.emit(self.manual_source_path)

    def _choose_work_root(self):
        path = QFileDialog.getExistingDirectory(self, "选择非系统盘临时工作位置")
        if path:
            self.work_edit.setText(path)

    def _source_changed(self):
        source = self.source_combo.currentData()
        if source is not None:
            self.set_source_identity((source.db_path, source.process_id))
            self.source_selected.emit(source)
        self.scan_button.setEnabled(source is not None or hasattr(self, "manual_source_path"))

    def set_sources(self, sources: Iterable[DatabaseSource]) -> None:
        self._sources = list(sources)
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        for source in self._sources:
            self.source_combo.addItem(f"QQ {source.account} · PID {source.process_id} · {source.qq_version}", source)
        if not self._sources:
            self.source_combo.addItem("未找到运行中的 QQ 数据源", None)
        self.source_combo.blockSignals(False)
        self._source_changed()

    def set_source_identity(self, identity: object) -> None:
        if identity != self._source_identity:
            self._source_identity = identity
            self.set_sessions([])

    def selected_source(self) -> DatabaseSource | None:
        source = self.source_combo.currentData()
        return source if isinstance(source, DatabaseSource) else None

    def set_sessions(self, entries: Iterable[ConversationIndexEntry]) -> None:
        self.session_model.set_sessions(entries)
        self.result_label.setText("" if self.session_model.entries else "暂无会话。请检查数据源后重新扫描。")

    def select_visible(self) -> None:
        keys = self.session_model.selected_keys()
        for row in range(self.filter_model.rowCount()):
            index = self.filter_model.mapToSource(self.filter_model.index(row, 0))
            entry = self.session_model.entries[index.row()]
            keys.add((entry.kind, entry.selector))
        self.session_model.select_keys(keys)

    def _toggle_row(self, proxy_index):
        index = self.filter_model.mapToSource(proxy_index)
        check_index = self.session_model.index(index.row(), 0)
        state = self.session_model.data(check_index, Qt.CheckStateRole)
        self.session_model.setData(check_index, Qt.Unchecked if state == Qt.Checked else Qt.Checked, Qt.CheckStateRole)

    def _selection_changed(self, count: int) -> None:
        self.selection_label.setText(f"已选择 {count} 条会话")
        self.export_button.setEnabled(count > 0)
