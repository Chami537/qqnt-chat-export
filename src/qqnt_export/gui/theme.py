from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase


def ui_font() -> QFont:
    families = set(QFontDatabase.families())
    for family in ("Microsoft YaHei UI", "Microsoft YaHei", "SimSun"):
        if family in families:
            return QFont(family, 10)
    system_font = Path("C:/Windows/Fonts/simsun.ttc")
    if system_font.is_file():
        font_id = QFontDatabase.addApplicationFont(str(system_font))
        installed = QFontDatabase.applicationFontFamilies(font_id)
        if installed:
            return QFont(installed[0], 10)
    return QFont("Sans Serif", 10)


STYLE = """
QWidget { color: #e7edf7; font-size: 13px; }
QMainWindow, QWidget#mainPanel { background: #101827; }
QFrame#sidebar { background: #0b1220; border-right: 1px solid #29384e; }
QFrame#card { background: #19263a; border: 1px solid #32435a; border-radius: 10px; }
QLabel#muted { color: #9baec5; }
QLabel#heading { font-size: 23px; font-weight: 700; }
QLabel#section { font-size: 16px; font-weight: 600; }
QPushButton, QComboBox, QLineEdit { min-height: 34px; border-radius: 7px; }
QPushButton { background: #263a54; border: 1px solid #415878; padding: 0 12px; }
QPushButton:hover { background: #304966; }
QPushButton:focus, QComboBox:focus, QLineEdit:focus, QTableView:focus { border: 2px solid #67aaff; }
QPushButton:disabled { color: #74859b; background: #202d3d; border-color: #303f52; }
QPushButton#primary { background: #3277dc; border: 1px solid #61a1ff; font-weight: 600; }
QPushButton#primary:hover { background: #4088f1; }
QComboBox, QLineEdit { background: #152235; border: 1px solid #40516a; padding: 0 9px; }
QTableView { background: #152235; alternate-background-color: #1b2a40; border: 1px solid #354964;
             border-radius: 8px; gridline-color: #26374d; selection-background-color: #284e80; }
QHeaderView::section { background: #22344d; color: #bed1e9; padding: 9px; border: 0; border-bottom: 1px solid #3d526e; }
QScrollBar:vertical { background: #152235; width: 11px; }
QScrollBar::handle:vertical { background: #4e6480; border-radius: 5px; min-height: 24px; }
QProgressBar { background: #1b2b40; border: 1px solid #344c6c; border-radius: 5px; text-align: center; }
QProgressBar::chunk { background: #3b8bea; border-radius: 5px; }
"""
