# QQNT Chat Export CLI Design

**Status:** Approved design; implementation pending a separate implementation plan.

## 1. Purpose and scope

Create an open-source, local Windows command-line tool that exports a user's own QQNT chat history to Markdown and JSON for offline review and LLM analysis. Version 0.1 supports Windows QQ 9.9.27 through a verified adapter. It must refuse unsupported formats with an actionable, privacy-preserving diagnostic rather than claiming universal QQ compatibility.

The tool works entirely on the user's computer. Its source database is read-only. It creates all database snapshots, temporary files, reports, and exports under an explicitly supplied non-system work or output directory. The default working location must never be on the C: drive.

Version 0.1 is a local tool. It does not upload data, provide cloud synchronization, send messages, modify QQ data, or alter running QQ processes.

## 2. Product success criteria

A user with a supported Windows QQ 9.9.27 installation and an already logged-in account can run one command to export a selected private or group conversation.

```powershell
qqnt-export export --peer <QQ_NUMBER> --output E:\QQExports
```

The command detects QQ data, checks compatibility, creates a safe snapshot, decrypts the snapshot using a locally verified method, finds the requested conversation, and produces `chat_export.md` and `chat_export.json`.

The command reports the export location and message count. Its terminal output and technical reports omit message contents, QQ identifiers, display names, and decryption keys.

## 3. User-facing command surface

### `export`

Runs the complete workflow. Required arguments are a conversation selector and an output directory.

- `--peer <qq>` selects a private conversation.
- `--group <id>` selects a group conversation.
- `--output <directory>` is the destination root and must be writable.
- `--work-dir <directory>` optionally chooses an intermediate workspace. If omitted, the workspace is created under `--output`.
- `--keep-workdir` retains the temporary encrypted and plaintext snapshots for inspection.
- `--account <qq>` resolves an ambiguity when more than one account data directory is found.

When no conversation selector is given, the command fails with a concise explanation and points to `conversations`.

### `doctor`

Performs discovery and compatibility checks without copying, decrypting, or exporting message data. It reports only safe technical details: discovered QQ versions, candidate data directories, adapter compatibility, storage availability, and Python dependency status.

### `conversations`

Builds a local, selected-workspace conversation index to help users choose a `--peer` or `--group`. Its default terminal output is a count and file path. The index itself may contain conversation metadata and is treated as private output.

### `cleanup`

Deletes only workspace directories created by this tool. It requires an explicit `--work-dir` path and verifies the tool's ownership marker before deletion.

## 4. Safety and privacy rules

1. Open the original QQ files read-only. Never use write-mode database access against the source.
2. Copy the database, WAL, and SHM files into the workspace before decryption or schema inspection.
3. Record source-file metadata before and after copying. If QQ changes the source during the copy, stop and ask the user to retry while QQ is idle.
4. Obtain and validate decryption material only in local process memory. Never print it, write it to a file, include it in exceptions, or store it in reports.
5. Keep all temporary database artifacts in a user selected non-system location. Remove them after a successful or failed operation unless `--keep-workdir` is supplied.
6. Do not place content, QQ numbers, nicknames, raw database BLOBs, or keys in normal logs, diagnostics, unit-test fixtures, or bug-report bundles.
7. Document that users should export only data they are authorized to access.

## 5. Architecture

The package separates the stable CLI contract from version-specific QQ internals.

```text
CLI
 ├── discovery       locate QQ executable, processes, and account data
 ├── compatibility   select and validate an adapter
 ├── snapshot        copy source database plus WAL/SHM into workspace
 ├── decrypt         produce a standard SQLite working database
 ├── schema          inspect tables and fields without schema assumptions
 ├── parse           map rows and encoded content into normalized messages
 ├── conversations   identify C2C and group conversations
 └── export          write JSON, Markdown, and a privacy-preserving report

adapters/
 └── qqnt_9_9_27     version-specific discovery, decryption, schema, and protobuf rules
```

Each adapter implements an explicit interface:

- `probe(environment) -> CompatibilityResult`
- `snapshot_plan(source) -> SnapshotPlan`
- `decrypt(snapshot, runtime) -> PlainDatabase`
- `message_sources(database) -> list[MessageSource]`
- `parse_message(row) -> ParsedMessage | UnknownMessage`
- `conversation_sources(database) -> list[ConversationSource]`

The core passes typed, normalized data between layers. Adapters do not write export files, and exporters do not inspect QQ-specific storage formats.

## 6. Data flow

1. The CLI validates arguments, output location, free space, and user permissions.
2. Discovery locates running QQ processes and account data. Ambiguity produces a selectable, non-sensitive result.
3. Compatibility probes executable version, encrypted database-header characteristics, and adapter-specific file fingerprints. It selects `qqnt_9_9_27` only after all pre-decryption checks pass.
4. Snapshot copies the encrypted database and associated WAL/SHM files into the workspace and confirms source stability.
5. Decryption produces a standard SQLite database inside the workspace and runs `PRAGMA quick_check`.
6. Schema inspection confirms actual message and conversation sources exposed by the adapter.
7. Parsing creates normalized messages containing time, sender identity relative to the current account, conversation identity, content type, text when known, attachments when known, and an unknown-content fallback.
8. The exporter filters to the selected conversation, writes JSON and Markdown, and writes a technical report without private content.
9. Cleanup removes workspace database artifacts unless the user selected `--keep-workdir`.

## 7. Export model and file formats

The JSON export is an ordered list of normalized records. At minimum each record includes:

```json
{
  "time": "2026-01-01T20:30:00+08:00",
  "sender": "self",
  "content_type": "text",
  "content": "你好"
}
```

`sender` uses `self`, `peer`, or `member` roles by default. Optional identifiers may be included only with a deliberate future option. Markdown groups messages by local date:

```markdown
# 与 <会话标题> 的聊天记录

## 2026-01-01

20:30 我：
你好
```

Known non-text content uses an explicit type marker such as `[图片消息]`, `[文件消息]`, or `[引用消息]`. Unknown encoded messages preserve a compact `raw_fallback` in JSON: message-source name, field numbers, types, lengths, and hash prefixes. The parser must never infer text from unrecognized bytes.

## 8. Compatibility policy

Version 0.1 declares support only for the adapter verified against Windows QQ 9.9.27. QQ paths, encryption parameters, key retrieval, SQLite schema, and Protobuf wire structures are adapter details that may change per release.

An unsupported QQ version exits before decryption and writes a safe `compatibility_report.json`. An unexpected schema detected after a successful decrypt stops before message parsing and reports the adapter mismatch without exporting content. Supporting a new version means adding an adapter, representative synthetic fixtures, adapter tests, documentation, and an entry in the compatibility matrix. Existing adapters remain isolated.

## 9. Errors and exit codes

The CLI returns distinct nonzero exit codes for invalid arguments, missing or ambiguous QQ installation, unsupported version, unstable source snapshot, local key validation failure, invalid decrypted database, conversation not found, output write failure, and internal error.

Errors name the failed stage, the recovery action, and a safe report file path. Exceptions are sanitized before they reach the terminal or a report.

## 10. Test strategy

Tests use synthetic SQLite databases, synthetic Protobuf payloads, and mock process/discovery results. They never include a real QQ account, key, chat message, database, nickname, or other personal data.

Coverage includes:

- argument parsing and exit codes;
- output and workspace path validation;
- source copy stability checks and read-only guarantees;
- adapter probe acceptance and rejection;
- decryption invocation parameters and failed-key handling;
- schema detection and field mapping;
- parsing of text, attachment, unknown, malformed, and timestamp edge cases;
- Markdown and JSON snapshots;
- report redaction and cleanup ownership checks.

Integration tests operate only on generated fixtures. A separately documented manual verification procedure may use a volunteer's local data but must keep all artifacts out of the repository.

## 11. Packaging and licensing

The project uses Python 3.11+ and publishes a Windows-installable CLI package with a `qqnt-export` console entry point. Dependencies are pinned in project metadata and installation instructions keep virtual environments and workspaces outside C: where requested.

The initial repository includes a permissive project license, proposed as MIT. Research sources with GPLv3 licenses are documented as references only. No GPLv3 source code or derived implementation enters this repository unless the project's own licensing is deliberately changed.

## 12. Non-goals for version 0.1

- Claiming support for every QQ or QQNT version.
- Writing to original QQ databases or modifying QQ files.
- Cloud upload, account synchronization, account login automation, or remote key extraction.
- Perfect rendering of every encoded message type.
- Including real user data in the source tree, test fixtures, logs, reports, examples, or issue templates.