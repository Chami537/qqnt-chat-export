# 第三方组件说明

Windows 图形界面构建会携带 Python、PySide6/Qt、SQLCipher Python 绑定及其依赖。实际版本以发布包构建环境和发布说明为准。

- **PySide6 / Qt for Python**：项目元数据列出 LGPL-3.0-only、GPL-2.0-only 或 GPL-3.0-only 的许可选项。分发者应按所选许可履行相应义务，保留组件许可文本和动态库替换能力。详见 [Qt for Python 许可说明](https://doc.qt.io/qtforpython-6/licenses.html)。
- **sqlcipher3 与 SQLCipher**：用于本地解密工作副本。分发前应核对所用 wheel 和底层 SQLCipher 的许可与构建来源，详见 [sqlcipher3 项目](https://github.com/coleifer/sqlcipher3)及 [SQLCipher 项目](https://github.com/sqlcipher/sqlcipher)。
- **PyInstaller**：仅用于构建，许可证为 GPLv2-or-later，附带程序打包分发的特别例外，详见 [PyInstaller 许可说明](https://pyinstaller.org/en/stable/license.html)。

本项目代码使用 MIT 许可证；第三方组件遵循各自许可。本说明不替代随二进制组件分发的完整许可文本。
