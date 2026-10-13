from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from qqnt_export.errors import ExportCancelled, SafeFailure
from qqnt_export.models import DatabaseSource
from qqnt_export.services import BatchSummary, TaskProgress, export_batch, scan_conversations


class ScanWorker(QObject):
    progress = Signal(object)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    done = Signal()

    def __init__(
        self, source: DatabaseSource, work_root: Path, cancel_event: threading.Event,
        service: Callable = scan_conversations,
    ):
        super().__init__()
        self.source = source
        self.work_root = work_root
        self.cancel_event = cancel_event
        self.service = service

    @Slot()
    def run(self):
        try:
            result = self.service(
                self.source, self.work_root, should_cancel=self.cancel_event.is_set,
                on_progress=self.progress.emit,
            )
            self.finished.emit(result)
        except ExportCancelled:
            self.cancelled.emit()
        except SafeFailure as failure:
            self.failed.emit(failure.public_message)
        except Exception:
            self.failed.emit("扫描未完成，请检查 QQ 状态和工作目录")
        finally:
            self.done.emit()


class ExportWorker(QObject):
    progress = Signal(object)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    done = Signal()

    def __init__(
        self, source: DatabaseSource, work_root: Path, output_root: Path,
        selected: Sequence[tuple[str, str]], cancel_event: threading.Event,
        service: Callable = export_batch,
    ):
        super().__init__()
        self.source = source
        self.work_root = work_root
        self.output_root = output_root
        self.selected = tuple(selected)
        self.cancel_event = cancel_event
        self.service = service

    @Slot()
    def run(self):
        try:
            result: BatchSummary = self.service(
                self.source, self.work_root, self.output_root, self.selected,
                should_cancel=self.cancel_event.is_set, on_progress=self.progress.emit,
            )
            self.finished.emit(result)
        except ExportCancelled:
            self.cancelled.emit()
        except SafeFailure as failure:
            self.failed.emit(failure.public_message)
        except Exception:
            self.failed.emit("导出未完成，请检查输出目录")
        finally:
            self.done.emit()
