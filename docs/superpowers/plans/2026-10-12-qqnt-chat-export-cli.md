# QQNT Chat Export CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Windows CLI that safely exports selected QQNT 9.9.27 conversations into JSON and Markdown.

**Architecture:** The `qqnt_export` package owns CLI, path safety, workspaces, report redaction, normalized messages, and exporters. A `qqnt_9_9_27` adapter owns QQ discovery, compatibility evidence, database snapshots, decryption configuration, schema expectations, and encoded-message decoding. The CLI orchestrates these boundaries without logging private values.

**Tech Stack:** Python 3.11+, `argparse`, `pathlib`, `sqlite3`, `ctypes`, optional `sqlcipher3`, `pytest`, `pytest-cov`, and `build`.

**Spec:** `docs/superpowers/specs/2026-10-12-qqnt-chat-export-design.md`

## Global Constraints

- Support Windows QQ 9.9.27 only in the first adapter; reject all other versions before decryption.
- Read original QQ files without modifying them; copy database, WAL, and SHM into a user-selected workspace before decryption or schema inspection.
- Require an output directory and create every temporary or export artifact under that non-system directory; default working files under the output directory.
- Never print or persist decryption keys, message text, QQ identifiers, nicknames, raw BLOBs, or full exception payloads in terminal logs or technical reports.
- Remove tool-owned temporary database artifacts after success or failure unless `--keep-workdir` is set.
- Use only synthetic non-personal test data and clean-room implementation code. Do not copy or derive source from GPLv3 references.
- Provide JSON and Markdown exports plus `doctor`, `conversations`, `export`, and `cleanup` commands.
- Publish Python 3.11+ package metadata with an MIT license and `qqnt-export` console entry point.

## Review Focus

1. A user supplies `C:\` as output or work directory: reject it before a snapshot consumes system-disk space. Tested in Task 2.
2. QQ changes `nt_msg.db` or its WAL during copying: remove the incomplete snapshot and exit before decryption. Tested in Task 5.
3. An encoded message has an unrecognized payload: JSON keeps bounded structural evidence and Markdown uses `[未识别消息结构]` without treating bytes as text. Tested in Task 7.
4. A conversation title has path separators or Markdown heading syntax: files remain inside the selected directory and generated Markdown has one stable title heading. Tested in Task 9.
5. Decryption or process inspection fails with sensitive bytes in an exception: the user-facing error and report omit the bytes. Tested in Task 6.

---

## Planned File Structure

```text
pyproject.toml
README.md
LICENSE
src/qqnt_export/
  __init__.py  cli.py  errors.py  models.py  privacy.py
  paths.py  workspace.py  discovery.py  snapshot.py  decrypt.py
  schema.py  messages.py  conversations.py  exporters.py  reports.py
  adapters/__init__.py  adapters/base.py  adapters/registry.py
  adapters/qqnt_9_9_27.py  adapters/clean_room_notes.md
  resources/compatibility_matrix.json
tests/
  conftest.py  test_models.py  test_paths.py  test_workspace.py
  test_discovery.py  test_reports.py  test_adapters.py  test_snapshot.py
  test_decrypt.py  test_schema.py  test_messages.py  test_conversations.py
  test_exporters.py  test_cli.py  test_release_contract.py
  fixtures/synthetic_messages.py
```

`models.py` is the shared immutable-model boundary. Every other module has one responsibility and accepts or returns these models.

### Task 1: Package skeleton, typed models, and safe error contract

**Files:**
- Create: `pyproject.toml`, `LICENSE`, `README.md`
- Create: `src/qqnt_export/__init__.py`, `models.py`, `errors.py`, `privacy.py`
- Create: `tests/conftest.py`, `tests/test_models.py`

**Interfaces:**
- Produces immutable `CompatibilityResult`, `DatabaseSource`, `ConversationRef`, `NormalizedMessage`, and `ExportResult` dataclasses.
- Produces `SafeFailure(stage: str, code: str, public_message: str)` and `redact_text(value: str) -> str`.

- [ ] **Step 1: Write the failing model and privacy tests**

```python
from qqnt_export.errors import SafeFailure
from qqnt_export.privacy import redact_text, safe_exception_message


def test_redaction_never_returns_input() -> None:
    assert redact_text("123456789: hello") == "[REDACTED]"
    assert safe_exception_message(ValueError("key=secret")) == "ValueError"


def test_safe_failure_has_public_fields_only() -> None:
    failure = SafeFailure("decrypt", "key_validation_failed", "无法验证本机 QQ 数据库")
    assert failure.stage == "decrypt"
    assert "secret" not in repr(failure).lower()
```

- [ ] **Step 2: Run the test before implementation**

Run: `python -m pytest tests/test_models.py -q`

Expected: FAIL during import because `qqnt_export` is absent.

- [ ] **Step 3: Implement metadata and minimal safe types**

```python
@dataclass(frozen=True)
class NormalizedMessage:
    occurred_at: datetime
    sender_role: Literal["self", "peer", "member"]
    content_type: str
    content: str | None
    raw_fallback: Mapping[str, object] | None


class SafeFailure(Exception):
    def __init__(self, stage: str, code: str, public_message: str) -> None:
        super().__init__(public_message)
        self.stage, self.code, self.public_message = stage, code, public_message
```

Set `requires-python = ">=3.11"`, add `qqnt-export = "qqnt_export.cli:main"`, add `pytest` and `pytest-cov` test extras, and include full MIT license text.

- [ ] **Step 4: Verify model tests and package build**

Run: `python -m pytest tests/test_models.py -q; python -m build`

Expected: PASS and wheel plus sdist under `dist/`.

- [ ] **Step 5: Commit the foundation**

```powershell
git add pyproject.toml LICENSE README.md src/qqnt_export/__init__.py src/qqnt_export/models.py src/qqnt_export/errors.py src/qqnt_export/privacy.py tests/conftest.py tests/test_models.py
git commit -m "feat: add package foundation and safe models"
```

### Task 2: Output-path policy and tool-owned workspace lifecycle

**Files:**
- Create: `src/qqnt_export/paths.py`, `src/qqnt_export/workspace.py`
- Create: `tests/test_paths.py`, `tests/test_workspace.py`

**Interfaces:**
- Consumes `SafeFailure`.
- Produces `validate_non_system_directory(path: Path) -> Path`, `safe_child(root: Path, leaf: str) -> Path`, and `Workspace.create(output_dir: Path, requested_work_dir: Path | None, keep: bool) -> Workspace`.
- `Workspace.close(success: bool) -> None` deletes only a directory carrying `.qqnt-export-workspace.json` when `keep` is false.

- [ ] **Step 1: Write failing path and ownership tests**

```python
def test_rejects_c_drive_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "system_drive", lambda: Path("C:/"))
    with pytest.raises(SafeFailure, match="非系统盘"):
        paths.validate_non_system_directory(Path("C:/QQExports"))


def test_cleanup_refuses_unmarked_directory(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "foreign", keep=False)
    workspace.root.mkdir()
    with pytest.raises(SafeFailure, match="工具工作目录"):
        workspace.close(success=True)
```

- [ ] **Step 2: Run tests before implementation**

Run: `python -m pytest tests/test_paths.py tests/test_workspace.py -q`

Expected: FAIL during import because modules are absent.

- [ ] **Step 3: Implement resolved-path checks and marker-controlled cleanup**

```python
def safe_child(root: Path, leaf: str) -> Path:
    candidate = (root / leaf).resolve()
    if candidate.parent != root.resolve():
        raise SafeFailure("paths", "unsafe_child", "导出文件名无效")
    return candidate


def validate_non_system_directory(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.drive.casefold() == system_drive().drive.casefold():
        raise SafeFailure("paths", "system_drive", "请选择非系统盘输出目录")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved
```

Create and validate a JSON ownership marker before any temporary file. Preserve a marked workspace when `keep=True`.

- [ ] **Step 4: Verify path and cleanup behavior**

Run: `python -m pytest tests/test_paths.py tests/test_workspace.py -q; python -m pytest -q`

Expected: PASS. Add a test that `safe_child` rejects `..\\`.

- [ ] **Step 5: Commit workspace safety**

```powershell
git add src/qqnt_export/paths.py src/qqnt_export/workspace.py tests/test_paths.py tests/test_workspace.py
git commit -m "feat: add safe output workspaces"
```

### Task 3: QQ discovery and privacy-preserving doctor report

**Files:**
- Create: `src/qqnt_export/discovery.py`, `src/qqnt_export/reports.py`
- Create: `tests/test_discovery.py`, `tests/test_reports.py`

**Interfaces:**
- Produces `discover_qq_installations(process_provider, data_roots) -> list[DatabaseSource]`, `choose_source(candidates, account_hint) -> DatabaseSource`, and `write_safe_report(path, report) -> None`.
- Full source paths exist only in memory; reports use an allow-list of safe technical keys.

- [ ] **Step 1: Write failing discovery and report tests**

```python
def test_choose_source_rejects_ambiguous_accounts() -> None:
    with pytest.raises(SafeFailure, match="多个 QQ 数据目录"):
        choose_source([source("alpha"), source("beta")], account_hint=None)


def test_report_redacts_private_values(tmp_path: Path) -> None:
    output = tmp_path / "doctor.json"
    write_safe_report(output, {"account": "123456789", "message": "hello", "status": "ok"})
    assert "123456789" not in output.read_text(encoding="utf-8")
    assert "hello" not in output.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests before implementation**

Run: `python -m pytest tests/test_discovery.py tests/test_reports.py -q`

Expected: FAIL during import because modules are absent.

- [ ] **Step 3: Implement injectable Windows discovery and allow-listed reporting**

```python
SAFE_REPORT_KEYS = frozenset({"stage", "code", "qq_version", "adapter", "status", "message_count", "time_range"})


def discover_qq_installations(process_provider, data_roots) -> list[DatabaseSource]:
    # Match QQ processes and candidate nt_db/nt_msg.db files without write handles.
    ...
```

Use injected process enumeration in tests. Filter reports through `SAFE_REPORT_KEYS`, rendering other values as `[REDACTED]`.

- [ ] **Step 4: Verify discovery and redaction**

Run: `python -m pytest tests/test_discovery.py tests/test_reports.py -q; python -m pytest -q`

Expected: PASS. Add a test that an account hint selects one candidate without reaching the report.

- [ ] **Step 5: Commit discovery and reports**

```powershell
git add src/qqnt_export/discovery.py src/qqnt_export/reports.py tests/test_discovery.py tests/test_reports.py
git commit -m "feat: add QQ discovery and safe diagnostics"
```
### Task 4: Adapter protocol, compatibility registry, and clean-room provenance

**Files:**
- Create: `src/qqnt_export/adapters/__init__.py`, `base.py`, `registry.py`, `clean_room_notes.md`
- Create: `src/qqnt_export/resources/compatibility_matrix.json`
- Create: `tests/test_adapters.py`

**Interfaces:**
- Produces `QQNTAdapter` protocol: `probe(source) -> CompatibilityResult`, `snapshot_paths(source) -> tuple[Path, ...]`, `decrypt_config() -> DecryptConfig`, `message_sources(database) -> Sequence[MessageSource]`, and `parse_message(row) -> NormalizedMessage`.
- Produces `select_adapter(source, adapters) -> QQNTAdapter`.

- [ ] **Step 1: Write failing adapter-selection tests**

```python
class RejectingAdapter:
    name = "reject"
    def probe(self, source: DatabaseSource) -> CompatibilityResult:
        return CompatibilityResult(False, self.name, "unsupported_version")


def test_select_adapter_reports_unsupported_version() -> None:
    with pytest.raises(SafeFailure, match="暂不支持"):
        select_adapter(source("one"), [RejectingAdapter()])
```

- [ ] **Step 2: Run tests before implementation**

Run: `python -m pytest tests/test_adapters.py -q`

Expected: FAIL during import because adapter modules are absent.

- [ ] **Step 3: Implement protocol, deterministic registry, and provenance rules**

```python
@runtime_checkable
class QQNTAdapter(Protocol):
    name: str
    def probe(self, source: DatabaseSource) -> CompatibilityResult: ...
    def snapshot_paths(self, source: DatabaseSource) -> tuple[Path, ...]: ...
    def decrypt_config(self) -> DecryptConfig: ...
    def message_sources(self, database: sqlite3.Connection) -> Sequence[MessageSource]: ...
    def parse_message(self, row: sqlite3.Row) -> NormalizedMessage: ...
```

Zero compatible adapters raise `unsupported_version`; more than one raises `ambiguous_adapter`. In `clean_room_notes.md`, document that GPLv3 repositories are never copied, vendored, or used as implementation source.

- [ ] **Step 4: Verify registry behavior**

Run: `python -m pytest tests/test_adapters.py -q; python -c "from qqnt_export.adapters.registry import select_adapter"`

Expected: PASS. Add a two-accepting-adapter ambiguity test.

- [ ] **Step 5: Commit adapter boundaries**

```powershell
git add src/qqnt_export/adapters tests/test_adapters.py src/qqnt_export/resources/compatibility_matrix.json
git commit -m "feat: add version adapter registry"
```

### Task 5: QQ 9.9.27 probe and stable source snapshot

**Files:**
- Create: `src/qqnt_export/adapters/qqnt_9_9_27.py`, `src/qqnt_export/snapshot.py`
- Create: `tests/test_snapshot.py`
- Modify: `tests/test_adapters.py`

**Interfaces:**
- Produces `QQNT9927Adapter` and `create_snapshot(source, workspace, adapter) -> Snapshot`.
- `QQNT9927Adapter.probe` validates executable version `9.9.27`, `nt_msg.db`, and fixed QQNT encrypted-header bytes without decrypting.

- [ ] **Step 1: Write failing probe and changing-source tests**

```python
def test_9927_adapter_rejects_different_version() -> None:
    assert QQNT9927Adapter().probe(source_with_version("9.9.28")).supported is False


def test_snapshot_removes_copy_when_source_changes(tmp_path: Path) -> None:
    source = make_source_with_wal(tmp_path)
    with pytest.raises(SafeFailure, match="复制期间发生变化"):
        create_snapshot(source, workspace(tmp_path), adapter_that_mutates_source(source))
    assert not list(workspace(tmp_path).root.glob("*.db"))
```

- [ ] **Step 2: Run tests before implementation**

Run: `python -m pytest tests/test_snapshot.py tests/test_adapters.py -q`

Expected: FAIL because adapter and snapshot code are absent.

- [ ] **Step 3: Implement pre-decryption probe and metadata-verified copy**

```python
def create_snapshot(source: DatabaseSource, workspace: Workspace, adapter: QQNTAdapter) -> Snapshot:
    source_paths = adapter.snapshot_paths(source)
    before = {path: file_fingerprint(path) for path in source_paths}
    copied = tuple(copy2(path, workspace.root / path.name) for path in source_paths if path.exists())
    after = {path: file_fingerprint(path) for path in source_paths}
    if before != after:
        remove_snapshot_files(copied)
        raise SafeFailure("snapshot", "source_changed", "QQ 数据库在复制期间发生变化，请在 QQ 空闲时重试")
    return Snapshot(*copied)
```

Fingerprint size and nanosecond modification time. Open sources only in binary read mode; include WAL and SHM when present.

- [ ] **Step 4: Verify stable and unstable copies**

Run: `python -m pytest tests/test_snapshot.py tests/test_adapters.py -q; python -m pytest -q`

Expected: PASS. Add a missing-WAL acceptance test and confirm copies remain in the marked workspace.

- [ ] **Step 5: Commit compatibility and snapshot**

```powershell
git add src/qqnt_export/adapters/qqnt_9_9_27.py src/qqnt_export/snapshot.py tests/test_snapshot.py tests/test_adapters.py
git commit -m "feat: add QQ 9.9.27 probe and stable snapshots"
```

### Task 6: Local decryption boundary and secret-safe failures

**Files:**
- Create: `src/qqnt_export/decrypt.py`, `tests/test_decrypt.py`
- Modify: `src/qqnt_export/adapters/base.py`, `src/qqnt_export/reports.py`

**Interfaces:**
- Produces `KeyProvider.get_key(source) -> bytes` and `decrypt_snapshot(snapshot, source, workspace, adapter, key_provider) -> Path`.
- Key material is held in a local `bytearray` and cleared in `finally`.

- [ ] **Step 1: Write failing decryption-redaction tests**

```python
class FailingKeyProvider:
    def get_key(self, source: DatabaseSource) -> bytes:
        raise RuntimeError("candidate=super-secret-key")


def test_key_provider_error_is_sanitized(tmp_path: Path) -> None:
    with pytest.raises(SafeFailure) as caught:
        decrypt_snapshot(snapshot(tmp_path), source("one"), workspace(tmp_path), adapter(), FailingKeyProvider())
    assert "super-secret-key" not in caught.value.public_message


def test_plain_database_is_inside_workspace(tmp_path: Path) -> None:
    plain = decrypt_snapshot(snapshot(tmp_path), source("one"), workspace(tmp_path), adapter(), fake_valid_key_provider())
    assert plain.parent == workspace(tmp_path).root
```

- [ ] **Step 2: Run tests before implementation**

Run: `python -m pytest tests/test_decrypt.py -q`

Expected: FAIL during import because decryption code is absent.

- [ ] **Step 3: Implement an injectable SQLCipher executor and Windows-only key-provider seam**

```python
class KeyProvider(Protocol):
    def get_key(self, source: DatabaseSource) -> bytes: ...


def decrypt_snapshot(..., cipher_executor: CipherExecutor = sqlcipher_executor) -> Path:
    key_material = bytearray(key_provider.get_key(source))
    try:
        plain_path = workspace.path_for("nt_msg_plain.db")
        cipher_executor(snapshot.encrypted_db, plain_path, bytes(key_material), adapter.decrypt_config())
        quick_check(plain_path)
        return plain_path
    except Exception:
        raise SafeFailure("decrypt", "decryption_failed", "无法验证或解密 QQ 数据库") from None
    finally:
        key_material.clear()
```

The built-in executor imports `sqlcipher3` lazily and opens only the copied snapshot. The Windows provider uses read-only `ctypes` process-memory APIs behind the protocol and never writes to the process or network.

- [ ] **Step 4: Verify decryption failure handling**

Run: `python -m pytest tests/test_decrypt.py tests/test_reports.py -q; python -m pytest -q`

Expected: PASS. Add a failed quick-check test that removes plaintext when `keep=False`.

- [ ] **Step 5: Commit decryption boundary**

```powershell
git add src/qqnt_export/decrypt.py src/qqnt_export/adapters/base.py src/qqnt_export/reports.py tests/test_decrypt.py
git commit -m "feat: add local decryption boundary"
```

### Task 7: Schema validation and bounded encoded-message parsing

**Files:**
- Create: `src/qqnt_export/schema.py`, `src/qqnt_export/messages.py`
- Create: `tests/fixtures/synthetic_messages.py`, `tests/test_schema.py`, `tests/test_messages.py`

**Interfaces:**
- Produces `open_verified_database(path, adapter) -> sqlite3.Connection`, `iter_messages(connection, source) -> Iterator[NormalizedMessage]`, and `unknown_fallback(payload, field_numbers) -> dict[str, object]`.
- `unknown_fallback` contains only field numbers, payload length, and first 12 SHA-256 hex characters.

- [ ] **Step 1: Write failing schema and unknown-payload tests**

```python
def test_schema_rejects_missing_adapter_message_table(tmp_path: Path) -> None:
    with pytest.raises(SafeFailure, match="数据库结构"):
        open_verified_database(sqlite_database_without_tables(tmp_path), QQNT9927Adapter())


def test_unknown_payload_never_becomes_text() -> None:
    message = parse_synthetic_unknown(b"\xff\x00secret-text")
    assert message.content is None
    assert message.content_type == "unknown"
    assert "secret-text" not in repr(message.raw_fallback)
```

- [ ] **Step 2: Run tests before implementation**

Run: `python -m pytest tests/test_schema.py tests/test_messages.py -q`

Expected: FAIL because schema and parser modules are absent.

- [ ] **Step 3: Implement read-only verification and clean-room wire decoding**

```python
def open_verified_database(path: Path, adapter: QQNTAdapter) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    required = {source.table for source in adapter.message_sources(connection)}
    existing = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not required.issubset(existing):
        connection.close()
        raise SafeFailure("schema", "adapter_schema_mismatch", "解密后的数据库结构与 QQ 版本适配器不匹配")
    return connection
```

Implement a minimal length-delimited Protobuf wire reader that returns typed records only for mappings documented independently in `qqnt_9_9_27.py`. Invalid wire values and unknown tags become unknown content. Never import GPLv3 parser code or generated schemas.

- [ ] **Step 4: Verify parser boundaries**

Run: `python -m pytest tests/test_schema.py tests/test_messages.py -q; python -m pytest -q`

Expected: PASS. Include synthetic text, attachment, malformed-wire, and unknown-nested-field cases.

- [ ] **Step 5: Commit schema and parser**

```powershell
git add src/qqnt_export/schema.py src/qqnt_export/messages.py tests/fixtures/synthetic_messages.py tests/test_schema.py tests/test_messages.py
git commit -m "feat: add schema checks and safe message parsing"
```

### Task 8: Conversation indexing and deterministic selector resolution

**Files:**
- Create: `src/qqnt_export/conversations.py`, `tests/test_conversations.py`
- Modify: `src/qqnt_export/adapters/base.py`, `src/qqnt_export/adapters/qqnt_9_9_27.py`

**Interfaces:**
- Produces `ConversationIndexEntry(kind, selector, title, message_count)`, `build_conversation_index(connection, adapter) -> list[ConversationIndexEntry]`, and `resolve_conversation(index, peer, group) -> ConversationIndexEntry`.

- [ ] **Step 1: Write failing index and selector tests**

```python
def test_resolve_requires_one_selector(index: list[ConversationIndexEntry]) -> None:
    with pytest.raises(SafeFailure, match="一个会话"):
        resolve_conversation(index, peer="123", group="456")


def test_index_orders_same_count_by_stable_selector() -> None:
    entries = build_conversation_index(connection_with_two_entries(), adapter())
    assert [entry.selector for entry in entries] == ["100", "200"]
```

- [ ] **Step 2: Run tests before implementation**

Run: `python -m pytest tests/test_conversations.py -q`

Expected: FAIL during import because the module is absent.

- [ ] **Step 3: Implement adapter-backed index and exact resolution**

```python
def resolve_conversation(index: Sequence[ConversationIndexEntry], peer: str | None, group: str | None) -> ConversationIndexEntry:
    if bool(peer) == bool(group):
        raise SafeFailure("conversation", "invalid_selector", "请仅指定一个私聊或群聊会话")
    kind, value = ("c2c", peer) if peer else ("group", group)
    matches = [entry for entry in index if entry.kind == kind and entry.selector == value]
    if len(matches) != 1:
        raise SafeFailure("conversation", "not_found", "未找到指定会话")
    return matches[0]
```

Sort index output by `kind` then selector. Keep titles inside private index/export files and out of terminal and diagnostic output.

- [ ] **Step 4: Verify selection behavior**

Run: `python -m pytest tests/test_conversations.py -q; python -m pytest -q`

Expected: PASS. Add absent-selector and multiple-row-to-one-conversation tests.

- [ ] **Step 5: Commit conversation selection**

```powershell
git add src/qqnt_export/conversations.py src/qqnt_export/adapters/base.py src/qqnt_export/adapters/qqnt_9_9_27.py tests/test_conversations.py
git commit -m "feat: add conversation indexing and selection"
```

### Task 9: Deterministic JSON and Markdown exporters

**Files:**
- Create: `src/qqnt_export/exporters.py`, `tests/test_exporters.py`

**Interfaces:**
- Produces `export_conversation(output_dir, conversation, messages) -> ExportResult`.
- Writes `chat_export.json` and `chat_export.md` beneath a safe child derived from conversation kind and selector; refuses to overwrite an existing export.

- [ ] **Step 1: Write failing exporter and unsafe-title tests**

```python
def test_export_creates_ordered_json_and_markdown(tmp_path: Path) -> None:
    result = export_conversation(tmp_path, conversation("c2c", "255"), two_messages())
    assert result.json_path.name == "chat_export.json"
    assert "## 2026-01-01" in result.markdown_path.read_text(encoding="utf-8")


def test_title_cannot_escape_directory_or_add_heading(tmp_path: Path) -> None:
    result = export_conversation(tmp_path, conversation("c2c", "255", title="../# injected"), one_message())
    assert result.markdown_path.parent.parent == tmp_path
    assert result.markdown_path.read_text(encoding="utf-8").count("# ") == 1
```

- [ ] **Step 2: Run tests before implementation**

Run: `python -m pytest tests/test_exporters.py -q`

Expected: FAIL during import because exporter module is absent.

- [ ] **Step 3: Implement atomic exports and explicit unknown markers**

```python
def render_markdown(conversation: ConversationIndexEntry, messages: Sequence[NormalizedMessage]) -> str:
    title = markdown_inline(conversation.title or conversation.selector)
    lines = [f"# 与 {title} 的聊天记录", ""]
    # Group sorted messages by date; unknown content renders [未识别消息结构].
    return "\n".join(lines) + "\n"
```

Write JSON with `ensure_ascii=False` and ISO 8601 timestamps. Write sibling temporary files, then `Path.replace` after complete writes. Sanitize displayed titles by removing line breaks and heading markers; preserve message content as content.

- [ ] **Step 4: Verify exporters**

Run: `python -m pytest tests/test_exporters.py -q; python -m pytest -q`

Expected: PASS. Add duplicate-destination refusal, non-text marker, and JSON fallback-without-payload tests.

- [ ] **Step 5: Commit exporters**

```powershell
git add src/qqnt_export/exporters.py tests/test_exporters.py
git commit -m "feat: export conversations as JSON and Markdown"
```

### Task 10: CLI orchestration, exit codes, and cleanup command

**Files:**
- Create: `src/qqnt_export/cli.py`, `tests/test_cli.py`
- Modify: `README.md`

**Interfaces:**
- Produces `build_parser() -> argparse.ArgumentParser`, `main(argv=None) -> int`, `run_doctor`, `run_conversations`, `run_export`, and `run_cleanup`.
- Exit codes: `0` success; `2` usage; `10` discovery; `11` compatibility; `12` snapshot; `13` decryption; `14` schema/parse; `15` conversation; `16` output; `17` cleanup; `70` internal.

- [ ] **Step 1: Write failing CLI contract tests**

```python
def test_export_requires_one_conversation_selector(tmp_path: Path) -> None:
    assert main(["export", "--output", str(tmp_path)]) == 2


def test_safe_failure_maps_to_stage_exit_code(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "run_export", lambda args: (_ for _ in ()).throw(SafeFailure("snapshot", "source_changed", "retry")))
    assert main(["export", "--peer", "123", "--output", str(tmp_path)]) == 12
```

- [ ] **Step 2: Run tests before implementation**

Run: `python -m pytest tests/test_cli.py -q`

Expected: FAIL during import because `cli.py` is absent.

- [ ] **Step 3: Implement parser and one-way orchestration**

```python
def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except SafeFailure as failure:
        print(f"{failure.stage}: {failure.public_message}", file=sys.stderr)
        return EXIT_CODES[failure.stage]
    except Exception:
        print("internal: 操作未完成；请运行 doctor 生成安全诊断", file=sys.stderr)
        return 70
```

`run_export` calls discovery, adapter selection, workspace creation, snapshot, decryption, schema verification, selector resolution, parsing, export, then cleanup. Use `finally` for `Workspace.close(success=False)` when a workspace exists. Terminal output contains only count and export paths.

- [ ] **Step 4: Verify command contracts**

Run: `python -m pytest tests/test_cli.py -q; python -m qqnt_export.cli --help; python -m pytest -q`

Expected: PASS; help lists four commands and test output has no synthetic chat content.

- [ ] **Step 5: Commit CLI orchestration**

```powershell
git add src/qqnt_export/cli.py tests/test_cli.py README.md
git commit -m "feat: add one-command QQNT export CLI"
```

### Task 11: Release documentation, package smoke test, and repository privacy audit

**Files:**
- Modify: `README.md`
- Create: `CONTRIBUTING.md`, `SECURITY.md`, `.gitignore`, `tests/test_release_contract.py`

**Interfaces:**
- Consumes the public command contract and produces no runtime interface.

- [ ] **Step 1: Write failing release-contract tests**

```python
def test_distribution_declares_console_script_and_mit_license() -> None:
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["license"]["text"] == "MIT"
    assert metadata["project"]["scripts"]["qqnt-export"] == "qqnt_export.cli:main"


def test_repository_has_no_database_or_key_artifacts() -> None:
    forbidden = {".db", ".wal", ".shm", ".key"}
    assert not [p for p in Path(".").rglob("*") if p.is_file() and p.suffix.casefold() in forbidden]
```

- [ ] **Step 2: Run tests before completing release files**

Run: `python -m pytest tests/test_release_contract.py -q`

Expected: FAIL because privacy files and release documentation are incomplete.

- [ ] **Step 3: Document use, privacy, and contribution rules**

Write prerequisites, `doctor` before export, non-system output/workspace selection, the exact 9.9.27 support claim, cleanup behavior, redaction, and troubleshooting. `SECURITY.md` asks reporters to omit chat content and keys. `CONTRIBUTING.md` requires synthetic fixtures and a clean-room note for future adapters. Ignore `*.db`, `*.db-wal`, `*.db-shm`, `*.wal`, `*.shm`, `*.key`, `dist/`, `.venv/`, workspace markers, and reports.

- [ ] **Step 4: Run complete release verification**

Run: `python -m pytest -q; python -m build; python -m pip install --force-reinstall dist/*.whl; qqnt-export --help; git status --short`

Expected: PASS; installed CLI lists four subcommands, build artifacts are ignored, and Git status contains only intended tracked files.

- [ ] **Step 5: Commit release documentation**

```powershell
git add README.md CONTRIBUTING.md SECURITY.md .gitignore tests/test_release_contract.py
git commit -m "docs: prepare safe open source release"
```

## Final Verification

- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m build`.
- [ ] Install the wheel into a fresh virtual environment on a non-system drive and run `qqnt-export --help`.
- [ ] Run only mocked discovery tests in automated verification; do not use a real QQ account or database.
- [ ] Run `git ls-files` and verify no database, WAL, SHM, key, report, chat export, or plaintext fixture is tracked.
- [ ] Review `git diff HEAD~11..HEAD` and ensure each commit touches only the task files listed in this plan.
