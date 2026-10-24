"""Smoke check for the Qt DLLs in a built Windows directory bundle."""

import os
import subprocess
import sys
import time
import ctypes
from ctypes import wintypes
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DLL loader only")
def test_bundled_qt_libraries_load_in_a_fresh_process() -> None:
    bundle_root = os.environ.get("QQNT_WINDOWS_BUNDLE_DIR")
    if not bundle_root:
        pytest.skip("set QQNT_WINDOWS_BUNDLE_DIR to verify a built bundle")

    internal = Path(bundle_root) / "_internal"
    assert (internal / "PySide6" / "Qt6Widgets.dll").is_file()

    probe = """
import ctypes
import os
import sys
from pathlib import Path

internal = Path(sys.argv[1])
os.add_dll_directory(str(internal))
os.add_dll_directory(str(internal / 'PySide6'))
for name in ('Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll'):
    ctypes.WinDLL(str(internal / 'PySide6' / name))
"""
    result = subprocess.run(
        [sys.executable, "-c", probe, str(internal)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="Windows GUI only")
def test_bundled_exe_opens_the_main_window() -> None:
    bundle_root = os.environ.get("QQNT_WINDOWS_BUNDLE_DIR")
    if not bundle_root:
        pytest.skip("set QQNT_WINDOWS_BUNDLE_DIR to verify a built bundle")

    exe = Path(bundle_root) / "qqnt-export-gui.exe"
    assert exe.is_file()
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visible_windows(pid: int) -> list[tuple[int, str]]:
        found = []

        @callback_type
        def collect(hwnd: int, _param: int) -> bool:
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == pid and user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                title = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, title, length + 1)
                found.append((hwnd, title.value))
            return True

        user32.EnumWindows(collect, 0)
        return found

    env = {**os.environ, "QT_QPA_PLATFORM": "windows"}
    process = subprocess.Popen([str(exe)], cwd=exe.parent, env=env)
    windows = []
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            windows = visible_windows(process.pid)
            if any(title == "QQNT 聊天记录导出" for _, title in windows):
                break
            if process.poll() is not None:
                break
            time.sleep(0.25)
        assert any(title == "QQNT 聊天记录导出" for _, title in windows), windows
    finally:
        for hwnd, _title in visible_windows(process.pid):
            user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
