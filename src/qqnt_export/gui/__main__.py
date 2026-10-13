from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from qqnt_export.gui.window import MainWindow


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.refresh_sources()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
