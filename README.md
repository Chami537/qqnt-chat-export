# QQNT Chat Export

A local Windows command-line tool for exporting your own QQNT conversations to UTF-8 JSON and Markdown. The first adapter supports **Windows QQ 9.9.27**. Other versions stop at a compatibility check; they are not claimed as supported.

The tool reads the original QQ database without writing to it. It copies the database and its WAL/SHM companions to a work directory on a non-system drive, decrypts that copy, and removes the temporary database files after the command completes. It reads decryption material from the already running local QQ process and never prints or writes the key. There is no network upload or QQ login automation.

## Install from this repository

Use Python 3.11 or newer on Windows. Create the virtual environment on a non-system drive if C: space is limited:

```powershell
py -3.11 -m venv E:\QQNTExportVenv
& E:\QQNTExportVenv\Scripts\python.exe -m pip install ".[decrypt]"
```

The `decrypt` extra installs `sqlcipher3`. Installation can require a compatible Windows wheel or local build tools. Run from the cloned repository directory, or install the built wheel.

## One-command export

Open and log in to QQ before running the command. Choose one private QQ number or one group number:

```powershell
& E:\QQNTExportVenv\Scripts\qqnt-export.exe export --peer 123456789 --output E:\QQExports
& E:\QQNTExportVenv\Scripts\qqnt-export.exe export --group 123456789 --output E:\QQExports
```

The CLI reports only the message count and a folder with a hashed selector. The folder contains `chat_export.json`, `chat_export.md`, and `export_report.json`. The JSON and Markdown are private chat data; the report contains only technical status and counts. Existing exports are never overwritten.

If QQ data has been moved away from the usual Documents folder, supply the `Tencent Files` root or the exact database path in the same command:

```powershell
qqnt-export export --peer 123456789 --data-root "D:\MovedData\Tencent Files" --output E:\QQExports
qqnt-export export --peer 123456789 --source "D:\MovedData\Tencent Files\123456789\nt_qq\nt_db\nt_msg.db" --output E:\QQExports
```

`QQNT_DATA_ROOT` can also name a custom `Tencent Files` directory. When several account directories are found, use `--account <your QQ number>`. If several QQ processes are running, `--pid` selects the process carrying the active database key. Use `qqnt-export doctor --source <path>` to test version and header compatibility without making a database copy.

## Other commands

```powershell
qqnt-export doctor --source "D:\MovedData\Tencent Files\123456789\nt_qq\nt_db\nt_msg.db"
qqnt-export conversations --source "D:\MovedData\Tencent Files\123456789\nt_qq\nt_db\nt_msg.db" --output E:\QQExports
qqnt-export cleanup --work-dir E:\QQExports\.qqnt-export-workspaces\<run-id>
```

`conversations` creates a private `conversation_index.json` containing selectors, titles, and counts. Keep this file local. `cleanup` removes only a directory carrying the tool's ownership marker. Normal runs remove their temporary workspace automatically. `--keep-workdir` preserves the encrypted and plaintext working databases for troubleshooting and may use several gigabytes.

If you set `--work-dir`, choose an empty directory separate from `--output`. Cleanup refuses a work directory containing files or directories it did not create; remove or move those items yourself before retrying cleanup.

All output and work directories must be on a non-system drive. The original QQ database may be on C: because it is only read. To avoid a changing snapshot, run the export while QQ is idle; if QQ writes during copying, the command stops and you can retry.

## Content and compatibility limits

The parser uses the table and field layout observed for QQ 9.9.27 and verifies that layout after decryption. It extracts verified UTF-8 text from the encoded message body. Known non-text types use markers such as `[媒体消息]`; unknown or malformed payloads become `[未识别消息结构]` and bounded structural metadata in JSON. It does not invent text for unknown bytes. Timestamps that are missing or zero are exported as JSON `null` and under an `未知日期` Markdown heading.

This first release selects private conversations by numeric `40030` QQ values and groups by `40030`, falling back to `40021`. UID-only private conversations and future QQ layouts need additional adapters or selectors. Use the generated index to see which conversations are currently addressable.

Technical reports and terminal output omit chat content, QQ numbers, names, database keys, and raw BLOBs. Export files and the conversation index intentionally contain private data. Export only data you are authorized to access, and do not attach your real database or export files to public issues.

## Development

```powershell
& E:\QQNTExportVenv\Scripts\python.exe -m pip install ".[test]"
& E:\QQNTExportVenv\Scripts\python.exe -m pytest -q
& E:\QQNTExportVenv\Scripts\python.exe -m build
```

Tests use generated synthetic SQLite and Protobuf messages. See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md) before sharing a bug report or adapter change.
