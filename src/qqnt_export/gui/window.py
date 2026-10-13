from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import threading
import os

from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QTableView, QVBoxLayout, QWidget, QHeaderView,
)

from qqnt_export.conversations import ConversationIndexEntry
from qqnt_export.models import DatabaseSource
from qqnt_export.errors import SafeFailure
from qqnt_export.source_selection import find_sources
from qqnt_export.work_locations import suggest_work_root
from qqnt_export.services import BatchSummary, TaskProgress, scan_conversations, export_batch
from .session_model import ConversationFilterModel, SessionTableModel
from .theme import STYLE, ui_font
from .workers import ScanWorker, ExportWorker


class MainWindow(QMainWindow):
    source_selected = Signal(object)
    scan_requested = Signal()
    export_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, *, scan_service=scan_conversations, export_service=export_batch):
        super().__init__()
        self._scan_service = scan_service
        self._export_service = export_service
        self._task_running = False
        self._close_pending = False
        self._thread: QThread | None = None
        self._worker = None
        self.cancel_event = threading.Event()
        self._last_batch_dir: Path | None = None
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
        self.scan_button.clicked.connect(self._request_scan)
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
        self.export_button.clicked.connect(self._request_export)
        bottom.addWidget(self.export_button)
        body.addLayout(bottom)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        body.addWidget(self.progress_bar)
        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setObjectName("muted")
        body.addWidget(self.result_label)
        self.open_output_button = QPushButton("打开输出目录")
        self.open_output_button.setVisible(False)
        self.open_output_button.clicked.connect(self._open_output)
        body.addWidget(self.open_output_button, alignment=Qt.AlignRight)
        self.cancel_button = QPushButton("取消任务")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self._request_cancel)
        body.addWidget(self.cancel_button, alignment=Qt.AlignRight)
        outer.addWidget(main, 1)
        self.session_model.selection_changed.connect(self._selection_changed)

    def _show_help(self):
        QMessageBox.information(self, "使用说明", "打开并登录 QQ，选择非系统盘临时目录，扫描并勾选会话。导出时选择非系统盘输出目录。")

    def _choose_source(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 nt_msg.db", "", "QQNT 数据库 (nt_msg.db)")
        if path:
            try:
                self.set_sources(find_sources(source_path=Path(path)))
            except SafeFailure as failure:
                self.set_sessions([])
                self.source_status.setText(failure.public_message)

    def _choose_work_root(self):
        path = QFileDialog.getExistingDirectory(self, "选择非系统盘临时工作位置")
        if path:
            self.work_edit.setText(path)

    def _source_changed(self):
        source = self.source_combo.currentData()
        if source is not None:
            self.set_source_identity((source.db_path, source.process_id))
            self.source_selected.emit(source)
            try:
                suggestion = suggest_work_root(source)
            except SafeFailure as failure:
                suggestion = None
                self.source_status.setText(failure.public_message)
            if suggestion is not None:
                self.work_edit.setText(str(suggestion))
                self.source_status.setText(f"QQ {source.qq_version} 已就绪；扫描前请确认工作位置")
        else:
            self.set_source_identity(None)
        self.scan_button.setEnabled(source is not None and not self._task_running)

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

    def refresh_sources(self) -> None:
        try:
            self.set_sources(find_sources())
        except SafeFailure as failure:
            self.set_sources([])
            self.source_status.setText(failure.public_message)

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
        self.export_button.setEnabled(count > 0 and not self._task_running)

    def _request_scan(self) -> None:
        source = self.selected_source()
        if source is None:
            self.result_label.setText("请先选择 QQ 数据源")
            return
        if not self.work_edit.text().strip():
            self.result_label.setText("请选择非系统盘临时工作位置")
            return
        self.scan_requested.emit()
        self.start_scan(source, Path(self.work_edit.text()))

    def _request_export(self) -> None:
        source = self.selected_source()
        keys = self.session_model.selected_keys()
        if source is None or not keys or not self.work_edit.text().strip():
            return
        output = QFileDialog.getExistingDirectory(self, "选择非系统盘输出位置")
        if not output:
            return
        choice = QMessageBox.question(
            self, "确认批量导出", f"将 {len(keys)} 条会话同时导出为 Markdown 和 JSON。\n输出到：{output}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if choice != QMessageBox.Yes:
            return
        self.export_requested.emit()
        self.start_export(source, Path(self.work_edit.text()), Path(output), sorted(keys))

    def _start_worker(self, worker, kind: str) -> None:
        if self._task_running:
            return
        self.cancel_event = worker.cancel_event
        self._task_running = True
        self.scan_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.source_combo.setEnabled(False)
        self.source_browse_button.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.result_label.setText("正在扫描会话…" if kind == "scan" else "正在导出所选会话…")
        self.open_output_button.setVisible(False)
        thread = QThread(self)
        self._thread = thread
        self._worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_scan_result if kind == "scan" else self._on_export_result)
        worker.failed.connect(self._on_failed)
        worker.cancelled.connect(self._on_cancelled)
        worker.done.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        thread.start()

    def start_scan(self, source: DatabaseSource, work_root: Path) -> None:
        if self._task_running:
            return
        self.set_sessions([])
        event = threading.Event()
        self._start_worker(ScanWorker(source, work_root, event, self._scan_service), "scan")

    def start_export(
        self, source: DatabaseSource, work_root: Path, output_root: Path,
        keys: Iterable[tuple[str, str]],
    ) -> None:
        if self._task_running:
            return
        event = threading.Event()
        self._start_worker(ExportWorker(source, work_root, output_root, tuple(keys), event, self._export_service), "export")

    def _on_progress(self, progress: TaskProgress) -> None:
        labels = {"snapshot": "复制只读快照", "decrypt": "解密工作副本", "scan": "读取会话", "export": "导出会话", "cleanup": "清理临时工作目录"}
        self.result_label.setText(labels.get(progress.stage, "处理中") + (
            f" · {progress.completed}/{progress.total}" if progress.total else ""
        ))
        if progress.total:
            self.progress_bar.setRange(0, progress.total)
            self.progress_bar.setValue(progress.completed)

    def _on_scan_result(self, entries) -> None:
        self.set_sessions(entries)
        self.result_label.setText(f"扫描完成：找到 {len(entries)} 条会话")

    def _on_export_result(self, summary: BatchSummary) -> None:
        counts = {status: sum(item.status == status for item in summary.outcomes) for status in ("success", "failed", "cancelled")}
        self.result_label.setText(
            f"导出结束：成功 {counts['success']}，失败 {counts['failed']}，取消 {counts['cancelled']}。"
        )
        self._last_batch_dir = summary.batch_dir
        self.open_output_button.setVisible(summary.batch_dir.is_dir())

    def _on_failed(self, message: str) -> None:
        self.result_label.setText(message)

    def _on_cancelled(self) -> None:
        self.result_label.setText("任务已取消，临时文件已清理")

    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._task_running = False
        self.cancel_button.setVisible(False)
        self.progress_bar.setVisible(False)
        self.source_combo.setEnabled(True)
        self.source_browse_button.setEnabled(True)
        self.scan_button.setEnabled(self.selected_source() is not None)
        self.export_button.setEnabled(bool(self.session_model.selected_keys()))
        if self._close_pending:
            QTimer.singleShot(0, self.close)

    def _request_cancel(self) -> None:
        if self._task_running:
            self.cancel_event.set()
            self.cancel_button.setEnabled(False)
            self.result_label.setText("正在取消并清理临时文件…")
            self.cancel_requested.emit()

    def _open_output(self) -> None:
        if self._last_batch_dir and self._last_batch_dir.is_dir():
            os.startfile(str(self._last_batch_dir))

    def closeEvent(self, event) -> None:
        if self._task_running:
            self._close_pending = True
            self._request_cancel()
            event.ignore()
        else:
            event.accept()
