# QQNT 桌面批量导出实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 为 Windows QQ 9.9.27 增加可直接运行的 PySide6 图形界面，支持会话多选并批量导出 Markdown 和 JSON。

**Architecture:** 复用现有只读快照、解密、解析和导出模块。新增数据源选择、非系统盘工作位置、可取消的共享批量服务；GUI 只调用服务并在后台线程执行耗时操作。CLI 保持原有命令与输出布局。

**Tech Stack:** Python 3.11+、sqlite3、PySide6 Widgets、PyInstaller 目录模式、pytest。

**Spec:** docs/superpowers/specs/2026-10-13-qqnt-desktop-batch-export-design.md

## Global Constraints

- 首版仅支持 Windows QQ 9.9.27；其他版本在复制前停止。
- 原始 nt_msg.db、WAL、SHM 只读；只对非系统盘工作副本解密和查询。
- 工作目录、导出目录和构建输出都位于非系统盘；不能把大文件写到 C 盘。
- 不输出密钥、QQ 号、昵称、正文、原始 BLOB 或含身份信息的路径到日志与技术报告。
- GUI 与 CLI 使用相同的 Markdown、JSON 记录格式；未知消息不猜正文。
- 不复制 WeFlow 的代码、图标、图片和样式；不做年度分析、媒体导出或云功能。
- GUI 依赖可选，安装 CLI 不应强制安装 PySide6。
- 在用户确认本计划后按此前选择的 Native 方式逐项实现；完成后按技能流程做一次独立整分支审查。

## Review Focus

1. 同一数据库对应多个 QQ 进程：数据源列表必须保留每个 PID，不能默选错误的解密进程；Task 1 测试。
2. 源库在系统盘且所有非系统盘空间不足：扫描前阻止复制并给出可操作提示；Task 2 测试。
3. 消息写出一半时取消：不留下 chat_export.md 或 chat_export.json 的半成品；Task 3 测试。
4. 扫描后会话消失或某条会话导出失败：该项失败，其他所选项继续；Task 4 测试。
5. 筛选或搜索后切换视图：已选会话不丢失，全选只影响当前可见项；Task 5 测试。

## File map

- src/qqnt_export/source_selection.py：给 CLI 与 GUI 使用的多账号、多进程数据源枚举。
- src/qqnt_export/work_locations.py：非系统盘工作位置建议、空间估算与验证。
- src/qqnt_export/exporters.py、errors.py：可取消且原子写入的单会话导出。
- src/qqnt_export/services.py：扫描、批量导出、事件与结果数据模型。
- src/qqnt_export/gui/session_model.py：会话表、筛选和稳定的勾选集合。
- src/qqnt_export/gui/workers.py：Qt 后台工作对象及取消信号。
- src/qqnt_export/gui/window.py、theme.py、__main__.py：窗口、视觉和入口。
- scripts/build_windows.ps1：在非系统盘生成 PyInstaller 目录包。
- pyproject.toml、README.md、SECURITY.md：可选依赖、入口、使用与隐私说明。
- tests/test_source_selection.py、test_work_locations.py、test_services.py、test_gui.py 及现有导出测试：合成数据验证。

### Task 1: 共享数据源枚举

**Files:** Create src/qqnt_export/source_selection.py, tests/test_source_selection.py; modify src/qqnt_export/cli.py.

**Interfaces:** Produces find_sources(source_path: Path | None, data_root: Path | None, pid: int | None) -> list[DatabaseSource]. CLI 继续由 choose_source 和 account 参数选单一来源；GUI 展示全部候选。自动发现多个进程时保留每个数据库与 PID 的组合。

- [ ] **Step 1: 写失败测试。** 在 test_source_selection.py 用两个合成进程、一个合成数据库调用 find_sources，并断言 PID 集合为 {7, 8}；对手动 source_path 也做相同断言。另测 pid=8 仅返回 8，账号目录名不输出到异常文字。
- [ ] **Step 2: 运行失败测试。** 运行 python -m pytest tests/test_source_selection.py -q；预期因模块或函数不存在失败。
- [ ] **Step 3: 实现最小枚举。** 将现有 cli._source_from_args 的手动路径验证移入 source_selection.py。自动发现继续用 discover_qq_installations 找数据库路径，再与已发现的每个 QQ 进程组合；不改变 discovery.py 默认去重行为。find_sources 对组合应用 pid 过滤，source_path 不存在、QQ 未运行时抛原有 SafeFailure。
- [ ] **Step 4: 保留 CLI 行为并验证。** cli._source_from_args 调用 find_sources 后按 account 过滤；多个进程但用户未给 --pid 时返回明确选择提示。运行 python -m pytest tests/test_source_selection.py tests/test_discovery.py tests/test_cli.py -q，预期通过。
- [ ] **Step 5: 只暂存本任务文件并提交。** 提交信息 feat: expose QQ data sources for desktop UI。

测试示例：

    def test_manual_source_keeps_each_process(tmp_path, monkeypatch):
        db = tmp_path / "123" / "nt_qq" / "nt_db" / "nt_msg.db"
        db.parent.mkdir(parents=True)
        db.write_bytes(b"synthetic")
        monkeypatch.setattr(source_selection, "windows_qq_processes", lambda: [
            {"pid": 7, "version": "9.9.27", "path": "D:/QQ/QQ.exe"},
            {"pid": 8, "version": "9.9.27", "path": "D:/QQ/QQ.exe"},
        ])
        assert {item.process_id for item in find_sources(source_path=db)} == {7, 8}
        assert [item.process_id for item in find_sources(source_path=db, pid=8)] == [8]

关键实现：

    def find_sources(
        source_path: Path | None = None,
        data_root: Path | None = None,
        pid: int | None = None,
    ) -> list[DatabaseSource]:
        processes = windows_qq_processes()
        if pid is not None:
            processes = [item for item in processes if int(item["pid"]) == pid]
        if not processes:
            raise SafeFailure("discovery", "qq_not_running", "请先打开并登录 QQ")
        if source_path is not None:
            paths = [source_path.expanduser().resolve()]
        else:
            roots = [data_root] if data_root is not None else None
            paths = [item.db_path for item in discover_qq_installations(lambda: processes, roots)]
        if not paths or any(not path.is_file() for path in paths):
            raise SafeFailure("discovery", "database_not_found", "未找到 QQNT 数据库")
        return [
            DatabaseSource(path, path.parents[2].name if len(path.parents) > 2 else "", str(process.get("version", "")),
                           int(process["pid"]), Path(str(process["path"])) if process.get("path") else None)
            for path in dict.fromkeys(paths) for process in processes
        ]

### Task 2: 非系统盘临时工作位置

**Files:** Create src/qqnt_export/work_locations.py, tests/test_work_locations.py.

**Interfaces:** Produces required_work_bytes(source: DatabaseSource) -> int; suggest_work_root(source: DatabaseSource, drives: Iterable[Path] | None = None) -> Path | None; prepare_work_root(source: DatabaseSource, root: Path) -> Path. Task 4 在创建 Workspace 前调用 prepare_work_root。

- [ ] **Step 1: 写失败测试。** 用合成 nt_msg.db、WAL、SHM 验证空间估算至少覆盖三份总大小与 512 MiB 余量；候选仅有 C 盘或空间不足时 suggest_work_root 返回 None；prepare_work_root 对系统盘、源树内路径和空间不足抛 SafeFailure，且在失败前不复制数据库。
- [ ] **Step 2: 运行失败测试。** 运行 python -m pytest tests/test_work_locations.py -q；预期因模块不存在失败。
- [ ] **Step 3: 实现位置逻辑。** Windows 上枚举存在的本地盘符，排除 SystemDrive，按可用空间选择候选下的 QQNTExportWork 子目录。用户指定路径由 validate_non_system_directory 验证，再用 shutil.disk_usage 检查空间。所需空间采用 3 × 数据库及现存 WAL/SHM 总大小 + 512 MiB；估算只用于事前拦截，复制仍处理真实磁盘错误。
- [ ] **Step 4: 运行测试。** 运行 python -m pytest tests/test_work_locations.py tests/test_paths.py tests/test_workspace.py -q，预期通过。
- [ ] **Step 5: 只暂存本任务文件并提交。** 提交信息 feat: choose safe non-system workspace。

测试示例：

    def test_only_system_drive_cannot_be_suggested(tmp_path, monkeypatch):
        db = tmp_path / "nt_msg.db"
        db.write_bytes(b"x" * 1024)
        source = DatabaseSource(db, "synthetic", "9.9.27", 7)
        monkeypatch.setattr(work_locations, "system_drive", lambda: Path("C:/"))
        assert suggest_work_root(source, drives=[Path("C:/")]) is None

关键代码接口：

    def required_work_bytes(source: DatabaseSource) -> int:
        files = [source.db_path, Path(str(source.db_path) + "-wal"), Path(str(source.db_path) + "-shm")]
        return 3 * sum(path.stat().st_size for path in files if path.is_file()) + (512 << 20)

### Task 3: 可取消的原子文件导出

**Files:** Modify src/qqnt_export/exporters.py, errors.py, tests/test_exporters.py.

**Interfaces:** export_conversation 增加可选 should_cancel: Callable[[], bool]，默认永不取消以保持 CLI 行为。Produces ExportCancelled 异常，Task 4 捕获它。成功时返回现有 ExportResult；取消或失败时删除临时文件和本次新建的空会话目录。

- [ ] **Step 1: 写失败测试。** 提供产生两条消息的迭代器，should_cancel 在第二条前返回 True；断言抛 ExportCancelled、无 chat_export.json/md、目录内无临时文件。再测写入异常和旧目标目录不能被删除。
- [ ] **Step 2: 运行失败测试。** 运行 python -m pytest tests/test_exporters.py -q；预期新增用例失败。
- [ ] **Step 3: 实现取消检查。** 在消息循环前和每次写入前检查 should_cancel；以 ExportCancelled 中断。finally 清理本次临时文件，并仅对本次创建且为空的目录调用 rmdir，不用递归删除。保留原有双文件成功路径与内容格式。
- [ ] **Step 4: 运行测试。** 运行 python -m pytest tests/test_exporters.py tests/test_messages.py -q，预期通过。
- [ ] **Step 5: 只暂存本任务文件并提交。** 提交信息 feat: cancel incomplete conversation exports safely。

测试示例：

    def test_cancel_removes_partial_files(tmp_path):
        entry = ConversationIndexEntry("c2c", "100", "虚构会话", 2)
        message = NormalizedMessage(
            datetime(2026, 1, 1, tzinfo=timezone.utc), "self", "text", "合成文本"
        )
        cancelled = False
        def messages():
            nonlocal cancelled
            yield message
            cancelled = True
            yield message
        with pytest.raises(ExportCancelled):
            export_conversation(tmp_path, entry, messages(), should_cancel=lambda: cancelled)
        assert not list(tmp_path.rglob("chat_export.*"))

关键代码：

    class ExportCancelled(Exception):
        pass

    def export_conversation(output_dir, conversation, messages, *, should_cancel=lambda: False):
        for message in messages:
            if should_cancel():
                raise ExportCancelled()

### Task 4: 扫描与批量导出服务

**Files:** Create src/qqnt_export/services.py, tests/test_services.py; modify src/qqnt_export/cli.py.

**Interfaces:** Produces open_working_database(source: DatabaseSource, adapter: QQNTAdapter, workspace: Workspace) -> sqlite3.Connection；scan_conversations(source, work_root, *, should_cancel, on_progress) -> list[ConversationIndexEntry]；export_batch(source, work_root, output_root, selected, *, should_cancel, on_progress) -> BatchSummary。selected 为 Sequence[tuple[str, str]]，键为 (kind, selector)。TaskProgress 包含 stage、completed、total；SessionOutcome 包含会话键、状态、消息数、安全错误文案；BatchSummary 包含本次目录与 outcome 元组。扫描取消抛 ExportCancelled；批量取消返回带 cancelled 结果的 BatchSummary。

- [ ] **Step 1: 写失败测试。** 在 test_services.py 定义 synthetic_source fixture，复用 tests/test_cli.py 的 fake_cipher 思路创建合成 SQLite，绝不使用真实 QQ 数据。断言扫描结束工作目录无明文库；一次批量导出只创建一次快照；两条选中会话各有 Markdown/JSON；扫描后消失的会话失败但其他项成功；单条写入或报告写入 SafeFailure 时继续且不留下半成品；取消后余项标为 cancelled；数据库原文件字节不变。
- [ ] **Step 2: 运行失败测试。** 运行 python -m pytest tests/test_services.py -q；预期因模块不存在失败。
- [ ] **Step 3: 实现共享打开流程。** 将 cli._open_working_database 的快照、解密、结构校验三步原样提取到 services.open_working_database。scan_conversations 先 select_adapter，再 prepare_work_root 和 Workspace.create，调用共享打开函数；finally 关闭连接与工作目录。
- [ ] **Step 4: 实现批量循环。** validate_non_system_directory(output_root) 后用排他 mkdir 创建 batch_日期_随机值目录；重新构建索引并按 (kind, selector) 核对，重复 key 只处理一次；逐条调用 iter_selected_messages 与 export_conversation；写脱敏 export_report.json，成功标记必须在三份文件均完整之后。报告写入失败时仅清理该次新建的会话文件，记录 failed 并继续；其他 SafeFailure 同样按项继续，ExportCancelled 停止且剩余项标 cancelled；finally 关闭连接与工作目录。
- [ ] **Step 5: 保持 CLI 兼容。** CLI 改用共享打开流程，不改变 export 命令原有 c2c_ 或 group_ 目录布局和输出文字。运行 python -m pytest tests/test_services.py tests/test_cli.py tests/test_conversations.py tests/test_snapshot.py -q，预期通过。
- [ ] **Step 6: 只暂存本任务文件并提交。** 提交信息 feat: share scan and batch export services。

测试示例：

    def test_batch_reuses_one_snapshot(synthetic_source, monkeypatch, tmp_path):
        snapshot_spy = Mock(wraps=services.create_snapshot)
        monkeypatch.setattr(services, "create_snapshot", snapshot_spy)
        result = services.export_batch(
            synthetic_source, tmp_path / "work", tmp_path / "out",
            [("c2c", "100"), ("group", "200")],
            should_cancel=lambda: False, on_progress=lambda event: None,
        )
        assert snapshot_spy.call_count == 1
        assert [item.status for item in result.outcomes] == ["success", "success"]

关键数据对象：

    @dataclass(frozen=True)
    class TaskProgress:
        stage: str
        completed: int
        total: int

    @dataclass(frozen=True)
    class SessionOutcome:
        key: tuple[str, str]
        status: Literal["success", "failed", "cancelled"]
        message_count: int = 0
        public_message: str | None = None

    @dataclass(frozen=True)
    class BatchSummary:
        batch_dir: Path
        outcomes: tuple[SessionOutcome, ...]

### Task 5: 会话列表与静态窗口

**Files:** Create src/qqnt_export/gui/__init__.py, session_model.py, theme.py, window.py, tests/test_gui.py.

**Interfaces:** SessionTableModel.set_sessions(entries) 更新列表；selected_keys() 返回 set[tuple[str, str]]；select_keys(keys) 只勾选指定集合。ConversationFilterModel(QSortFilterProxyModel).set_kind(kind) 和 set_search(text) 只筛选，不删除原始选择。MainWindow 提供 source_selected、scan_requested、export_requested、cancel_requested 信号，Task 6 接服务。不得在 Qt model 的 display role 泄露到日志。

- [ ] **Step 1: 写失败 GUI 测试。** 设置 QT_QPA_PLATFORM=offscreen，创建 QApplication；注入三条虚构会话，勾选一条私聊，切换群聊筛选再切回，断言原选择保留；在搜索结果里全选，断言只新增可见会话；切换账号后清除旧账号选择；检验无会话时导出按钮禁用。
- [ ] **Step 2: 运行失败测试。** 安装可选 GUI 与测试依赖后运行 python -m pytest tests/test_gui.py -q；预期因 GUI 模块不存在失败。
- [ ] **Step 3: 实现 model 与窗口。** 用 QAbstractTableModel 保存原始条目与独立的选中 key 集合，QSortFilterProxyModel 做搜索和类型筛选；窗口按已确认草图建立窄侧栏、来源与工作位置栏、搜索和筛选、会话表、固定底栏、确认对话框、任务结果区。主题颜色独立定义于 theme.py。
- [ ] **Step 4: 验证视觉和键盘。** 运行 python -m pytest tests/test_gui.py -q；在 Windows 125% 和 150% 缩放下人工检查窗口与焦点状态，截图仅用虚构数据。
- [ ] **Step 5: 只暂存本任务文件并提交。** 提交信息 feat: add desktop conversation picker。

测试示例：

    def test_selection_survives_filter_change(qapp):
        model = SessionTableModel()
        model.set_sessions([
            ConversationIndexEntry("c2c", "100", "联系人甲", 3),
            ConversationIndexEntry("group", "200", "群甲", 7),
        ])
        model.select_keys({("c2c", "100")})
        proxy = ConversationFilterModel()
        proxy.setSourceModel(model)
        proxy.set_kind("group")
        assert model.selected_keys() == {("c2c", "100")}
        model.select_keys({("group", "200")})
        assert model.selected_keys() == {("c2c", "100"), ("group", "200")}

关键模型状态：

    class SessionTableModel(QAbstractTableModel):
        def __init__(self):
            super().__init__()
            self.entries: list[ConversationIndexEntry] = []
            self.selected: set[tuple[str, str]] = set()

### Task 6: 后台任务、进度与安全退出

**Files:** Create src/qqnt_export/gui/workers.py; modify gui/window.py and tests/test_gui.py.

**Interfaces:** ScanWorker 与 ExportWorker 在 QThread 中分别调用 Task 4 服务；progress、finished、failed 信号只传数据对象或 SafeFailure.public_message。MainWindow.closeEvent 在任务运行时设置取消标记并忽略本次关闭，线程完成后再次关闭。

- [ ] **Step 1: 写失败测试。** 注入会阻塞直到取消的假服务；触发扫描后断言界面仍能处理 Qt 事件，重复扫描被禁用；点击取消后断言服务看到标记且任务完成；关闭窗口时先取消、随后关闭。另测错误信号仅展示安全文案。
- [ ] **Step 2: 运行失败测试。** 运行 python -m pytest tests/test_gui.py -q；预期新增用例失败。
- [ ] **Step 3: 实现 worker 与连接。** QObject worker 持有 threading.Event，run 捕获 SafeFailure 与意外异常；用 PySide6 Signal 发送结果，线程完成时 quit、deleteLater。窗口在主线程接收事件并更新阶段状态，取消不强制 terminate 线程。
- [ ] **Step 4: 运行测试并人工操作。** 运行 python -m pytest tests/test_gui.py tests/test_services.py -q，预期通过；手动检查扫描、取消、重新扫描、导出和部分失败结果页。
- [ ] **Step 5: 只暂存本任务文件并提交。** 提交信息 feat: run desktop exports without blocking UI。

测试示例：

    def test_close_requests_cancel(qapp):
        window = MainWindow()
        window.show()
        window._task_running = True
        window.close()
        assert window.cancel_event.is_set()
        assert window.isVisible()
        window._task_running = False
        window.close()
        qapp.processEvents()
        assert not window.isVisible()

关键取消连接：

    self.cancel_event = threading.Event()
    self.cancel_requested.connect(self.cancel_event.set)
    summary = export_batch(
        source, work_root, output_root, keys,
        should_cancel=self.cancel_event.is_set,
        on_progress=self.progress.emit,
    )

### Task 7: Windows 入口、打包与文档

**Files:** Create src/qqnt_export/gui/__main__.py and scripts/build_windows.ps1; modify pyproject.toml, README.md, SECURITY.md, tests/test_release_contract.py.

**Interfaces:** 安装 GUI 依赖后运行 qqnt-export-gui；脚本以指定非系统盘构建根目录生成 dist/qqnt-export-gui/qqnt-export-gui.exe。CLI 入口 qqnt-export 保持不变。

- [ ] **Step 1: 写失败发布契约测试。** 校验 pyproject 含 gui 可选依赖与 gui-scripts 入口；构建脚本拒绝 C 盘路径并使用 PyInstaller 目录模式；wheel 包含 GUI Python 文件及兼容性元数据。
- [ ] **Step 2: 运行失败测试。** 运行 python -m pytest tests/test_release_contract.py -q；预期新增断言失败。先安装正确的 build 包，解决当前 python -m build 不可执行的环境问题。
- [ ] **Step 3: 实现入口与构建。** GUI 入口创建 QApplication 和 MainWindow；pyproject 增加 PySide6 可选依赖与 GUI script；build_windows.ps1 检查输出不在 SystemDrive，将 TEMP 和 TMP 指向非系统盘构建根目录后调用 PyInstaller --onedir --windowed，并显式收集 sqlcipher3、Qt 插件和兼容性资源。使用独立的非系统盘虚拟环境与构建缓存。
- [ ] **Step 4: 更新中文文档。** README 加图形界面安装、扫描、批量导出、目录模式程序和 QQ 版本限制；SECURITY 说明本地会话列表、临时明文库与取消后的清理。附第三方许可证说明，不放真实数据截图。
- [ ] **Step 5: 验证发布包。** 运行 python -m pytest -q、python -m build --wheel，并在 Windows x64 用干净环境启动 dist 中的 exe；用合成数据库验证启动、扫描、批量导出和输出位置。若实际 QQ 9.9.27 私下验证不可行，明确记录未验证，不宣称已通过。
- [ ] **Step 6: 只暂存本任务文件并提交。** 提交信息 feat: package QQNT desktop exporter。

构建脚本关键命令：

    $BuildRoot = [IO.Path]::GetFullPath($BuildRoot)
    if ([IO.Path]::GetPathRoot($BuildRoot) -ieq "$env:SystemDrive\") { throw "构建目录不能位于系统盘" }
    $env:TEMP = "$BuildRoot/tmp"
    $env:TMP = $env:TEMP
    New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
    & $PythonExe -m PyInstaller --noconfirm --onedir --windowed --name qqnt-export-gui `
      --distpath "$BuildRoot/dist" --workpath "$BuildRoot/work" --specpath "$BuildRoot/spec" `
      --collect-all sqlcipher3 --collect-data qqnt_export src/qqnt_export/gui/__main__.py

## 交付前总验证

- [ ] 在 E 盘独立环境中安装 decrypt、gui、test 依赖，运行完整测试且确认无因环境缺包导致的失败。
- [ ] 运行 git diff --check，确认 git ls-files 不含数据库、密钥、聊天导出、草图缓存或真实聊天截图。
- [ ] 检查目录模式程序不把大型运行文件解包到 C 盘，删除临时工作目录后原始 nt_msg.db 字节与时间戳不变。
- [ ] 由独立审查者检查整个分支，修正实质问题，再决定是否按既有发布授权推送远端。
