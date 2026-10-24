# QQNT 聊天记录导出工具

这是一个在 Windows 本地运行的 QQNT 聊天记录导出工具，提供图形界面和命令行。它可将你有权访问的聊天记录批量导出为 UTF-8 编码的 JSON 和 Markdown。首个适配器仅支持 **Windows QQ 9.9.27**；其他版本会在兼容性检查阶段停止，不保证能够导出。

工具不会写入原始 QQ 数据库。它先将数据库及对应的 WAL、SHM 文件复制到非系统盘的工作目录，再对副本解密和分析；命令结束后默认清理临时数据库。解密材料只在本机已登录的 QQ 进程内存中读取和验证，不会打印或写入文件。工具不会上传数据，也不会自动登录 QQ。

## 图形界面

下载 Windows 目录模式程序后，保持整个 `qqnt-export-gui` 目录完整，运行其中的 `qqnt-export-gui.exe`。不需要安装 Python；首次使用请先打开并登录 QQ 9.9.27。程序启动时只查找本机数据源，不自动复制数据库。

1. 在顶部选择 QQ 数据源。多个账号或进程会分别列出，也可点“选择数据库”指定 `nt_msg.db`。
2. 确认“临时工作位置”位于非系统盘，点“扫描会话”。扫描结束即清理该次的数据库副本。
3. 搜索或筛选私聊、群聊，勾选多条会话，或“全选当前结果”。切换筛选不会清除已勾选的会话。
4. 点“导出所选”，指定非系统盘输出目录并确认。每次导出建立独立的 `batch_...` 文件夹；每条成功会话含 `chat_export.md`、`chat_export.json`、`export_report.json`。
5. 任务中可点“取消任务”；已完成的会话保留，未完成的临时文件和工作数据库会清理。关闭窗口时程序会先请求取消并等待清理。

如果扫描因整库完整性检查失败而中止，可点“按号码恢复私聊”，输入对方 QQ 号并选择输出目录。工具先从已登录的 QQ 验证密钥，再等待你正常退出 QQ，随后只读取该私聊。导出报告中的 `quick_check` 为 `not_run`：此模式不能证明整库或未返回消息的完整性。若所选会话的页面无法读取，工具会停止且不保留未完成的导出。

窗口会显示每条任务的成功、失败和取消数量。结果文件包含私人聊天内容，请自行保管。GUI 不保存上次账号、会话索引或路径；重新启动后需要再次扫描。

从源码运行图形界面：

```powershell
py -3.11 -m venv E:\QQNTExportVenv
& E:\QQNTExportVenv\Scripts\python.exe -m pip install ".[decrypt,gui]"
& E:\QQNTExportVenv\Scripts\qqnt-export-gui.exe
```

## 从仓库安装命令行

需要 Windows 和 Python 3.11 或更新版本。如果 C 盘空间有限，请把虚拟环境建在其他盘。以下命令在克隆后的仓库目录中运行：

```powershell
py -3.11 -m venv E:\QQNTExportVenv
& E:\QQNTExportVenv\Scripts\python.exe -m pip install ".[decrypt]"
```

`decrypt` 可选依赖会安装 `sqlcipher3`。安装时可能需要兼容的 Windows wheel，或本机编译工具。也可以安装项目构建出的 wheel。

## 一条命令导出

先打开并登录 QQ，再选择一个私聊对象的 QQ 号或一个群号：

```powershell
& E:\QQNTExportVenv\Scripts\qqnt-export.exe export --peer 123456789 --output E:\QQExports
& E:\QQNTExportVenv\Scripts\qqnt-export.exe export --group 123456789 --output E:\QQExports
```

终端只显示消息数量和经过哈希处理的会话目录名。目录中包含 `chat_export.json`、`chat_export.md` 和 `export_report.json`。前两个文件含有私人聊天数据；报告只包含技术状态和数量。工具不会覆盖已有的导出文件。

若普通导出提示稳定副本无法通过完整性检查，可按号码尝试只恢复一条可读会话。运行时保持 QQ 已登录；密钥验证成功后按提示正常退出所有 QQ 进程：

```powershell
& E:\QQNTExportVenv\Scripts\qqnt-export.exe recover --peer 123456789 --output E:\QQExports
```

`recover` 也支持 `--group <群号>`，但只要所选会话有无法读取的数据库页，导出就会失败。此命令不执行整库完整性校验，报告写入 `quick_check: not_run`；消息数量只表示这次查询实际返回的行数。

如果 QQ 数据已从默认的“文档”目录移走，可以指定 `Tencent Files` 根目录，或直接指定数据库文件：

```powershell
qqnt-export export --peer 123456789 --data-root "D:\MovedData\Tencent Files" --output E:\QQExports
qqnt-export export --peer 123456789 --source "D:\MovedData\Tencent Files\123456789\nt_qq\nt_db\nt_msg.db" --output E:\QQExports
```

也可以用环境变量 `QQNT_DATA_ROOT` 指定自定义的 `Tencent Files` 目录。找到多个账号目录时，用 `--account <你的 QQ 号>` 选择账号；运行多个 QQ 进程时，用 `--pid` 选择持有当前数据库密钥的进程。运行 `qqnt-export doctor --source <数据库路径>` 可只检查版本与文件头兼容性，不复制数据库。

## 其他命令

```powershell
qqnt-export doctor --source "D:\MovedData\Tencent Files\123456789\nt_qq\nt_db\nt_msg.db"
qqnt-export conversations --source "D:\MovedData\Tencent Files\123456789\nt_qq\nt_db\nt_msg.db" --output E:\QQExports
qqnt-export cleanup --work-dir E:\QQExports\.qqnt-export-workspaces\<run-id>
```

`conversations` 会生成包含会话选择值、标题和消息数量的 `conversation_index.json`，请将它作为私人文件保存在本地。`cleanup` 只清理带有工具所有权标记的工作目录。正常运行时会自动清理临时目录；使用 `--keep-workdir` 则会保留加密副本和明文数据库，可能占用数 GB 空间。

如果指定 `--work-dir`，请选择与 `--output` 不同的空目录。工作目录中若出现工具未创建的文件或子目录，清理会拒绝删除整个目录；请自行移走这些内容，再重新执行清理。

输出目录和工作目录必须位于非系统盘。原始 QQ 数据库可以位于 C 盘，因为工具只读取它。若 QQ 在复制期间修改了数据库或 WAL 文件，工具会先从运行中的 QQ 验证密钥，再提示你正常退出 QQ。所有 QQ 进程退出后，工具会重新复制数据库并检查完整性；图形界面可点击“取消任务”，命令行可按 Ctrl+C 取消。等待 15 分钟仍未退出会超时。

如果退出 QQ 后仍提示“数据库稳定副本无法通过完整性检查”，说明空闲重试无法解决这次失败。请先备份原始 QQ 数据目录，再检查 QQ 自身是否能正常读取这段聊天记录；工具不会修改或自动修复原始数据库。数据库格式不兼容也可能导致此提示。

扫描会话和批量导出是两次独立操作。如果扫描时退出了 QQ，导出前需要重新登录 QQ，让工具再次从进程中验证密钥。

## 内容与兼容性限制

解析器使用在 QQ 9.9.27 中观察到的表和字段布局，并在解密后验证数据库结构。它只提取已确认的 UTF-8 文本。已知的非文本消息会显示如 `[媒体消息]` 的标记；未知或损坏的内容会显示 `[未识别消息结构]`，并在 JSON 中保留有界的结构信息，不会将未知字节猜成正文。缺失或为零的时间戳在 JSON 中为 `null`，在 Markdown 中归入“未知日期”。

此版本通过数值字段 `40030` 选择私聊；群聊优先使用 `40030`，缺失时使用 `40021`。仅有 UID 的私聊，以及未来 QQ 版本的新布局，需要后续增加选择方式或适配器。可以查看生成的会话索引，确认哪些会话目前能够选择。

终端输出和技术报告不包含聊天正文、QQ 号、昵称、数据库密钥或原始 BLOB。导出文件和会话索引则有意包含私人数据。只导出你有权访问的记录，不要将真实数据库或导出文件附在公开 issue 中。

## 开发与验证

```powershell
& E:\QQNTExportVenv\Scripts\python.exe -m pip install ".[test]"
& E:\QQNTExportVenv\Scripts\python.exe -m pytest -q
& E:\QQNTExportVenv\Scripts\python.exe -m build
```

在 Windows x64 上构建图形界面便携目录时，先安装 `.[decrypt,gui,test]` 与 `pyinstaller>=6,<7`，然后指定非系统盘构建根目录：

```powershell
.\scripts\build_windows.ps1 -BuildRoot E:\QQNTExportBuild -PythonExe E:\QQNTExportVenv\Scripts\python.exe
$env:QQNT_WINDOWS_BUNDLE_DIR = "E:\QQNTExportBuild\dist\qqnt-export-gui"
& E:\QQNTExportVenv\Scripts\python.exe -m pytest -q tests\test_windows_bundle.py
```

程序位于 `E:\QQNTExportBuild\dist\qqnt-export-gui\qqnt-export-gui.exe`。构建脚本将临时文件与 PyInstaller 缓存放在指定目录；目录模式启动时不会像单文件模式那样每次向系统盘解包大型依赖。打包和分发前请阅读[第三方组件说明](THIRD_PARTY_NOTICES.md)。

测试使用合成的 SQLite 数据库和 Protobuf 消息。提交问题或新增适配器前，请阅读[贡献指南](CONTRIBUTING.md)和[安全与隐私说明](SECURITY.md)。
