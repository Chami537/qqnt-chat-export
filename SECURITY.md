# Security and privacy

This tool accesses private local chat data and reads the selected QQ process memory in read-only mode to validate the database key. Run it only on your own computer and only for data you are authorized to export. Temporary plaintext database files are removed by default. `--keep-workdir` retains them and should be used only for deliberate local troubleshooting.

Do not attach a real `nt_msg.db`, WAL/SHM file, key, `conversation_index.json`, `chat_export.json`, or `chat_export.md` to public issues. A safe report can include QQ version, adapter ID, failure stage/code, and counts. Remove account numbers, display names, file paths containing personal identifiers, and message text before sharing command output.

If you find an issue that could expose private data, report the minimal reproduction with synthetic fixtures. No cloud service, telemetry, or automatic upload is part of this tool.
