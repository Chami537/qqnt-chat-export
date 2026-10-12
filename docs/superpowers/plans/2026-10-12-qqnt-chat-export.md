# QQNT Chat Export CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an open-source Windows Python CLI that safely snapshots a user's QQNT data, decrypts a supported QQ 9.9.27 database, and exports a selected conversation to JSON and Markdown.

**Architecture:** A thin CLI calls version-independent services for discovery, compatibility, snapshotting, parsing, conversation selection, and export. A `qqnt_9_9_27` adapter owns all version-specific process, SQLCipher, schema, and Protobuf knowledge behind typed interfaces.

**Tech Stack:** Python 3.11+, `sqlite3`, `pathlib`, `protobuf`, `sqlcipher3`, `argparse`, `pytest`, `setuptools`.

**Spec:** `docs/superpowers/specs/2026-10-12-qqnt-chat-export-design.md`

## Global Constraints

- Support Windows QQ 9.9.27 only in version 0.1; reject unsupported versions before decryption.
- Open the original QQ database read-only and copy the database plus WAL/SHM files before inspection or decryption.
- Store workspaces, temporary databases, reports, and exports under an explicit user-selected non-system directory; never default to C:.
- Never print or persist decryption keys, chat content, QQ numbers, nicknames, or raw database BLOBs in logs or technical reports.
- Validate source stability during snapshot; stop if QQ writes the source while it is being copied.
- Validate the decrypted database with `PRAGMA quick_check` before parsing.
- Preserve unknown encoded content as structured fallback metadata and never guess its text.
- Use synthetic SQLite/Protobuf fixtures in tests; no personal QQ data enters the repository.
- Do not modify, upload, synchronize, or send messages through QQ.

## Review Focus

- A source database with a changing WAL must stop before export and leave a sanitized recovery report; Task 3 tests the before/after metadata mismatch.
- An unsupported QQ version must exit before key handling and decryption; Task 2 tests the adapter rejection and exit code.
- A malformed or unknown Protobuf payload must remain a typed fallback without fabricated text; Task 5 tests both cases.
- A path inside the source QQ directory or a missing output directory must fail before any copy; Task 1 and Task 3 test path validation.
- A report or exception must not contain key material or message content; Task 4 and Task 8 test redaction.

## File Map

Create these files:

- `pyproject.toml`: package metadata, console entry point, and runtime/test dependencies.
- `README.md`: supported-version statement, one-command usage, privacy model, and troubleshooting.
- `LICENSE`: MIT license text.
- `.gitignore`: Python caches, virtual environments, build output, and local export/work directories.
- `src/qqnt_export/__init__.py`: package version.
- `src/qqnt_export/__main__.py`: `python -m qqnt_export` entry point.
- `src/qqnt_export/cli.py`: argument parsing, orchestration, output messages, and exit-code mapping.
- `src/qqnt_export/errors.py`: public exception types and stable exit-code constants.
- `src/qqnt_export/models.py`: immutable normalized records and report/result dataclasses.
- `src/qqnt_export/discovery.py`: QQ process and account-directory discovery interfaces.
- `src/qqnt_export/compatibility.py`: adapter probing and compatibility result handling.
- `src/qqnt_export/snapshot.py`: read-only source checks and WAL-aware copies.
- `src/qqnt_export/decrypt.py`: decryptor protocol, key validation, and quick-check wrapper.
- `src/qqnt_export/schema.py`: SQLite schema inspection with no hard-coded table assumption in the core.
- `src/qqnt_export/parser.py`: adapter result normalization and unknown-message fallback.
- `src/qqnt_export/conversations.py`: conversation index and selector filtering.
- `src/qqnt_export/exporters.py`: JSON and Markdown output.
- `src/qqnt_export/report.py`: sanitized technical reports and log redaction.
- `src/qqnt_export/cleanup.py`: ownership marker validation and workspace cleanup.
- `src/qqnt_export/adapters/base.py`: adapter protocols.
- `src/qqnt_export/adapters/qqnt_9_9_27.py`: the first verified QQNT adapter.
- `src/qqnt_export/adapters/__init__.py`: adapter registry.

Create these tests:

- `tests/test_models.py`, `tests/test_paths.py`, `tests/test_errors.py`: stable core contracts.
- `tests/test_discovery.py`, `tests/test_compatibility.py`: discovery and adapter selection.
- `tests/test_snapshot.py`: copy safety and source stability.
- `tests/test_decrypt.py`: decryptor protocol, key redaction, and quick check.
- `tests/test_schema.py`, `tests/test_parser.py`: schema probing and normalized/fallback parsing.
- `tests/test_conversations.py`: index and selector behavior.
- `tests/test_exporters.py`, `tests/test_report.py`: file formats and redaction.
- `tests/test_cli.py`: one-command success and each public failure exit code.
- `tests/fixtures.py`: generated temporary SQLite and Protobuf fixtures only.

### Task 1: Package scaffold, domain types, and safe path contracts

**Files:**
- Create: `pyproject.toml`, `README.md`, `LICENSE`, `.gitignore`
- Create: `src/qqnt_export/__init__.py`, `src/qqnt_export/__main__.py`, `src/qqnt_export/errors.py`, `src/qqnt_export/models.py`
- Test: `tests/test_models.py`, `tests/test_paths.py`, `tests/test_errors.py`

**Interfaces:**
- `models.py` provides `ConversationSelector`, `NormalizedMessage`, `UnknownContent`, `UnknownMessage`, `Conversation`, `ExportResult`, `ReportData`, `FileStamp`, and `Snapshot` frozen dataclasses, plus `Message = NormalizedMessage | UnknownMessage`.
- `errors.py` provides `ExitCode` (`IntEnum`) and `ExportError(stage: str, message: str, exit_code: ExitCode)`.
- `models.py` provides `validate_output_root(output: Path, work_dir: Path | None, source_root: Path) -> tuple[Path, Path]`.

- [ ] **Step 1: Write failing domain and path tests.**

```python
def test_validate_output_rejects_source_directory(tmp_path):
    source = tmp_path / "Tencent Files" / "account"
    output = source / "exports"
    source.mkdir(parents=True)
    with pytest.raises(ExportError) as error:
        validate_output_root(output, None, source)
    assert error.value.exit_code is ExitCode.INVALID_ARGUMENT


def test_normalized_message_requires_timezone_aware_time():
    with pytest.raises(ValueError):
        NormalizedMessage(time=datetime(2026, 1, 1), sender="self", content_type="text", content="x")
```

- [ ] **Step 2: Run `pytest tests/test_models.py tests/test_paths.py tests/test_errors.py -q` and verify collection fails because the package does not exist.**
- [ ] **Step 3: Add the package metadata and typed dataclasses.** Define `NormalizedMessage` (`time`, `sender`, `content_type`, `content`), `UnknownContent` (`source`, `field_numbers`, `wire_types`, `byte_length`, `hash_prefix`), `UnknownMessage` (`time`, `sender`, `content_type="unknown"`, `fallback`), `ConversationSelector` (`peer` or `group`), `Conversation` (`kind`, `key`, `title`, `message_count`), `FileStamp`, `Snapshot`, `ExportResult`, and `ReportData`. Use `pathlib.Path.resolve()` for containment checks, reject output/work paths inside the source directory, and require a timezone-aware `datetime` in `NormalizedMessage`.
- [ ] **Step 4: Add `python -m qqnt_export` and a console entry point that returns `ExitCode.INTERNAL_ERROR` for an uncaught `ExportError` only after sanitizing its message.**
- [ ] **Step 5: Run the three test files and `python -m build --wheel`; verify all pass and the wheel contains no local data.**
- [ ] **Step 6: Commit with `git add pyproject.toml README.md LICENSE .gitignore src tests && git commit -m "build: scaffold QQNT export package"`.**

### Task 2: Discovery, adapter registry, and compatibility probe

**Files:**
- Create: `src/qqnt_export/discovery.py`, `src/qqnt_export/compatibility.py`, `src/qqnt_export/adapters/base.py`, `src/qqnt_export/adapters/__init__.py`, `src/qqnt_export/adapters/qqnt_9_9_27.py`
- Test: `tests/test_discovery.py`, `tests/test_compatibility.py`

**Interfaces:**
- `discovery.py`: `QqProcess` (`pid`, `executable`, `version`, `module_paths`) and `ProbeEnvironment` (`process`, `source_db`, `source_root`) dataclasses; `discover_qq_processes() -> list[QqProcess]`, `discover_account_roots(process: QqProcess) -> list[Path]`.
- `adapters/base.py`: `CompatibilityResult` (`supported`, `adapter_id`, `reason`), a `Decryptor` protocol with `decrypt(snapshot: Snapshot, destination: Path) -> PlainDatabase`, and a `VersionAdapter` protocol with `adapter_id: str`, `probe(environment: ProbeEnvironment) -> CompatibilityResult`, `build_decryptor() -> Decryptor`, `message_sources(schema: DatabaseSchema) -> tuple[MessageSource, ...]`, and `conversation_sources(schema: DatabaseSchema) -> tuple[ConversationSource, ...]`.
- `compatibility.py`: `select_adapter(environment: ProbeEnvironment, adapters: Sequence[VersionAdapter]) -> VersionAdapter`.
- `qqnt_9_9_27.py`: `Qqnt9927Adapter.probe()` checks executable version and encrypted header/file fingerprints without opening the source in write mode.

- [ ] **Step 1: Write tests for one accepted 9.9.27 environment, one unsupported version, and two discovered processes. Add a `fake_environment` pytest fixture returning the `ProbeEnvironment` dataclass and an `adapter` fixture returning `Qqnt9927Adapter`.**

```python
def test_select_adapter_rejects_unsupported_version(fake_environment, adapter):
    fake_environment.process.version = "9.9.28"
    with pytest.raises(ExportError) as error:
        select_adapter(fake_environment, [adapter])
    assert error.value.exit_code is ExitCode.UNSUPPORTED_VERSION
```

- [ ] **Step 2: Run `pytest tests/test_discovery.py tests/test_compatibility.py -q`; verify the adapter protocol and selector are missing.**
- [ ] **Step 3: Implement discovery behind injectable process and filesystem providers.** Keep the default Windows provider small and make tests pass fake process records instead of reading a real QQ installation. Use quoted protocol annotations for `PlainDatabase`, `DatabaseSchema`, `MessageSource`, and `ConversationSource`, which are defined by later tasks but are imported at runtime only after their modules exist.
- [ ] **Step 4: Implement `Qqnt9927Adapter` with explicit fingerprint constants sourced from the already verified local workflow.** The probe returns a structured reason and never returns or logs a key.
- [ ] **Step 5: Run the two test files and add a compatibility matrix section to `README.md` stating only QQ 9.9.27 is supported.**
- [ ] **Step 6: Commit with `git add src tests README.md && git commit -m "feat: add QQNT discovery and version adapter"`.**

### Task 3: Read-only snapshot and cleanup ownership

**Files:**
- Create: `src/qqnt_export/snapshot.py`, `src/qqnt_export/cleanup.py`
- Modify: `src/qqnt_export/models.py`
- Test: `tests/test_snapshot.py`

**Interfaces:**
- `snapshot.py`: `create_snapshot(source_db: Path, workspace: Path, stability_probe: Callable[[Path], FileStamp] = ...) -> Snapshot`.
- `cleanup.py`: `write_ownership_marker(workspace: Path, run_id: str) -> None`, `cleanup_workspace(workspace: Path, run_id: str) -> None`.
- `models.py`: `Snapshot` contains copied database, optional WAL/SHM paths, source stamps, and workspace path; `FileStamp` contains size, mtime, and SHA-256 of a bounded metadata read.

- [ ] **Step 1: Write tests that copy a generated database with WAL/SHM siblings, reject a source inside output, and fail when the source stamp changes between pre-copy and post-copy.**
- [ ] **Step 2: Run `pytest tests/test_snapshot.py -q`; verify the snapshot functions are missing.**
- [ ] **Step 3: Implement `create_snapshot()` with `shutil.copy2()` for the database and existing `-wal`/`-shm` siblings, then re-stat every source file and raise `ExportError(stage="snapshot", exit_code=ExitCode.UNSTABLE_SOURCE)` on mismatch.**
- [ ] **Step 4: Create a JSON ownership marker containing only a generated run ID, tool version, and relative artifact names; do not write account identifiers or contents.**
- [ ] **Step 5: Implement cleanup to require that exact marker and refuse paths without it; test cleanup leaves unrelated files untouched.**
- [ ] **Step 6: Run the snapshot test file and commit with `git add src tests && git commit -m "feat: add WAL-aware read-only snapshots"`.**

### Task 4: Decryptor boundary and SQLCipher validation

**Files:**
- Create: `src/qqnt_export/decrypt.py`, `src/qqnt_export/report.py`
- Modify: `src/qqnt_export/adapters/base.py`, `src/qqnt_export/adapters/qqnt_9_9_27.py`
- Test: `tests/test_decrypt.py`, `tests/test_report.py`

**Interfaces:**
- `decrypt.py`: `PlainDatabase` (`path`, `connection_factory`) dataclass and `Decryptor.decrypt(snapshot: Snapshot, destination: Path) -> PlainDatabase`.
- `decrypt.py`: `validate_plain_database(path: Path) -> None` uses standard `sqlite3` and `PRAGMA quick_check`.
- `report.py`: `sanitize_error(text: str, secrets: Collection[str]) -> str`, `write_report(path: Path, report: ReportData) -> None`.

- [ ] **Step 1: Write tests for successful quick-check, invalid plaintext, a thrown key-validation error, and report redaction.**

```python
def test_report_redacts_key_and_message():
    text = sanitize_error("key=secret-key body=private message", ["secret-key", "private message"])
    assert "secret-key" not in text
    assert "private message" not in text
    assert "[REDACTED]" in text
```

- [ ] **Step 2: Run `pytest tests/test_decrypt.py tests/test_report.py -q`; verify the decryptor and report implementations are missing.**
- [ ] **Step 3: Implement the decryptor protocol and inject the SQLCipher connection factory.** The 9.9.27 adapter owns the verified header stripping, page size, KDF, HMAC, and key-validation sequence; the core receives only a success/failure result and never stores the key in a report object.
- [ ] **Step 4: Copy the validated plaintext result to a destination inside the workspace and run `validate_plain_database()` before returning it.** Reject overwrite of an existing plaintext database unless the path belongs to the current run marker.
- [ ] **Step 5: Run the two test files and a synthetic standard SQLite quick-check fixture; commit with `git add src tests && git commit -m "feat: add validated decryptor boundary"`.**

### Task 5: Schema inspection and normalized message parsing

**Files:**
- Create: `src/qqnt_export/schema.py`, `src/qqnt_export/parser.py`, `tests/fixtures.py`
- Modify: `src/qqnt_export/models.py`, `src/qqnt_export/adapters/base.py`, `src/qqnt_export/adapters/qqnt_9_9_27.py`
- Test: `tests/test_schema.py`, `tests/test_parser.py`

**Interfaces:**
- `schema.py`: `DatabaseSchema` (`tables: tuple[TableSchema, ...]`) and `inspect_schema(connection: sqlite3.Connection) -> DatabaseSchema`, where `TableSchema` contains name, columns, declared types, and row count.
- `parser.py`: `MessageSource` (`table`, `payload_column`, `field_map`) and `parse_row(row: sqlite3.Row, source: MessageSource, account_qq: str) -> NormalizedMessage | UnknownMessage`.
- `qqnt_9_9_27.py`: `ConversationSource` (`table`, `conversation_key_column`, `title_columns`) is the adapter-provided source used by Task 6 to build an index.
- `adapters/qqnt_9_9_27.py`: message sources target the verified `c2c_msg_table` and `group_msg_table` only after schema checks confirm them; the core never assumes those names.

- [ ] **Step 1: Build generated fixtures containing a tiny `c2c_msg_table`, `group_msg_table`, and a synthetic `40800` payload for text, unknown bytes, and malformed bytes.**
- [ ] **Step 2: Write tests for table/column enumeration, text extraction, sender direction, timezone conversion, and unknown fallback metadata.**
- [ ] **Step 3: Run `pytest tests/test_schema.py tests/test_parser.py -q`; verify the implementation is absent.**
- [ ] **Step 4: Implement `inspect_schema()` with `sqlite_master`, `PRAGMA table_info`, and parameterized row counts.** Keep raw samples out of the returned report model.
- [ ] **Step 5: Implement the adapter's Protobuf decoder for the verified `40800` structure and map message ID, sender/peer, Unix time, and content type into normalized records. For unknown or malformed payloads, return field numbers, wire types, byte length, and hash prefix only.
- [ ] **Step 6: Run both test files, including the malformed payload tests, and commit with `git add src tests && git commit -m "feat: parse QQNT messages with safe fallback"`.**

### Task 6: Conversation index and selection

**Files:**
- Create: `src/qqnt_export/conversations.py`
- Modify: `src/qqnt_export/models.py`
- Test: `tests/test_conversations.py`

**Interfaces:**
- `conversations.py`: `build_index(database: PlainDatabase, adapter: VersionAdapter) -> list[Conversation]`.
- `conversations.py`: `select_conversation(index: Sequence[Conversation], selector: ConversationSelector) -> Conversation`.
- `conversations.py`: `conversation_messages(database: PlainDatabase, conversation: Conversation, adapter: VersionAdapter, account_qq: str) -> Iterator[NormalizedMessage | UnknownMessage]`.

- [ ] **Step 1: Write tests for private QQ selection, group selection, missing selector, duplicate matches, and chronological ordering.**
- [ ] **Step 2: Run `pytest tests/test_conversations.py -q`; verify the index and selectors are missing.**
- [ ] **Step 3: Implement index construction from adapter-provided conversation sources, keeping display labels private to the index file and out of technical reports.**
- [ ] **Step 4: Implement exact-match selectors and raise `ExitCode.CONVERSATION_NOT_FOUND` or `ExitCode.INVALID_ARGUMENT` for zero or ambiguous matches.**
- [ ] **Step 5: Run the test file and commit with `git add src tests && git commit -m "feat: index and select conversations"`.**

### Task 7: JSON, Markdown, and technical reports

**Files:**
- Create: `src/qqnt_export/exporters.py`
- Modify: `src/qqnt_export/report.py`
- Test: `tests/test_exporters.py`, `tests/test_report.py`

**Interfaces:**
- `exporters.py`: `Message` is the alias defined in Task 1; `write_json(messages: Iterable[Message], path: Path) -> int`.
- `exporters.py`: `write_markdown(messages: Iterable[Message], conversation_title: str, path: Path) -> int`.
- `report.py`: `build_export_report(result: ExportResult) -> ReportData`.

- [ ] **Step 1: Write snapshot tests for a two-day text conversation, a non-text marker, and an unknown fallback.**

```python
def test_markdown_groups_by_local_date(tmp_path, sample_messages):
    count = write_markdown(sample_messages, "测试会话", tmp_path / "chat_export.md")
    text = (tmp_path / "chat_export.md").read_text(encoding="utf-8")
    assert count == 2
    assert "# 与 测试会话 的聊天记录" in text
    assert "## 2026-01-01" in text
    assert "20:30 我：" in text
```

- [ ] **Step 2: Run `pytest tests/test_exporters.py tests/test_report.py -q`; verify the exporters are missing.**
- [ ] **Step 3: Implement JSON serialization with stable UTF-8, ISO-8601 timestamps, explicit `content_type`, and `raw_fallback` only for unknown records.**
- [ ] **Step 4: Implement Markdown grouping by local date and `我`/`对方` roles, escaping headings and line breaks so message content cannot alter document structure.**
- [ ] **Step 5: Implement a report containing adapter ID, counts, time range, quick-check result, and sanitized stage statuses only.**
- [ ] **Step 6: Run both test files and commit with `git add src tests && git commit -m "feat: export chats to JSON and Markdown"`.**

### Task 8: One-command CLI orchestration and public failure behavior

**Files:**
- Modify: `src/qqnt_export/cli.py`, `src/qqnt_export/__main__.py`, `src/qqnt_export/discovery.py`, `src/qqnt_export/report.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- `cli.py`: `build_parser() -> argparse.ArgumentParser`.
- `cli.py`: `ServiceContainer` dataclass holding discovery, adapter registry, snapshot, decrypt, parse, export, report, and cleanup callables; `run_export(args: argparse.Namespace, services: ServiceContainer) -> ExportResult`.
- `cli.py`: `main(argv: Sequence[str] | None = None) -> int`.

- [ ] **Step 1: Write CLI tests with fake services for successful private export, unsupported version, unstable source, missing conversation, and unwritable output.** Assert exit codes and that terminal output contains paths/counts only.
- [ ] **Step 2: Run `pytest tests/test_cli.py -q`; verify the orchestration functions are missing or incomplete.**
- [ ] **Step 3: Implement `export`, `doctor`, `conversations`, and `cleanup` subcommands and wire the exact service order: validate paths → discover → probe → snapshot → decrypt → quick-check → inspect schema → select conversation → parse → export → report → cleanup.**
- [ ] **Step 4: Catch only known `ExportError` values at the command boundary, sanitize unexpected exceptions, and return the documented `ExitCode` integer.**
- [ ] **Step 5: Add `--keep-workdir` handling and ensure `finally` cleanup runs after both success and failure unless retention was requested.**
- [ ] **Step 6: Run the CLI tests and `python -m qqnt_export --help`; commit with `git add src tests && git commit -m "feat: add one-command export workflow"`.**

### Task 9: Packaging, documentation, and release verification

**Files:**
- Modify: `README.md`, `pyproject.toml`
- Create: `docs/compatibility.md`, `docs/privacy.md`, `tests/test_package.py`

**Interfaces:**
- The built wheel exposes the `qqnt-export` command and `python -m qqnt_export`.
- Documentation examples use a non-system output path and explain that only QQNT 9.9.27 is supported initially.

- [ ] **Step 1: Write a packaging test that builds a wheel in a temporary directory, installs it into a temporary virtual environment, and runs `qqnt-export --help`.**
- [ ] **Step 2: Run `pytest tests/test_package.py -q`; verify packaging metadata or entry points fail before the final configuration is complete.**
- [ ] **Step 3: Document installation, one-command export, `doctor`, `conversations`, cleanup, supported-version limits, privacy behavior, and sanitized bug-report collection.**
- [ ] **Step 4: Build the wheel and run the full suite with `python -m pytest -q`.**
- [ ] **Step 5: Run `python -m compileall src`, `python -m build`, and inspect the wheel contents for source data, keys, local paths, and temporary databases.**
- [ ] **Step 6: Commit with `git add README.md pyproject.toml docs tests && git commit -m "docs: package QQNT export CLI"`.**
- [ ] **Step 7: Record the final verification commands and supported-version limitation in the release checklist; do not publish or push until the user separately authorizes a remote.**

## Execution Order

Execute Tasks 1 through 9 in order. Each task must pass its focused tests and commit before the next task begins. After Task 9, run the full suite and a manual dry run against a copied, user-authorized QQNT 9.9.27 workspace outside the repository. Keep any resulting exports and databases outside the repository and outside C:.

## Verification Checklist

- `python -m pytest -q` passes with only synthetic fixtures.
- `python -m compileall src` passes.
- `python -m build` succeeds.
- `qqnt-export --help` works from an installed wheel.
- Unsupported version stops before decryption.
- Source database and WAL/SHM timestamps and hashes are unchanged after a dry run.
- No key, message content, QQ number, nickname, or raw BLOB appears in terminal output, reports, test fixtures, wheel contents, or Git history.
- The generated Markdown and JSON exist only under the selected output directory and contain the expected message count.
