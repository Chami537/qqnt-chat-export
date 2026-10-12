# Contributing

This project has one verified adapter, for Windows QQ 9.9.27. New QQ versions need their own adapter and synthetic tests. Keep QQ-version-specific table names, fields, decryption parameters, and encoded-message mappings out of the core CLI.

Use only data you are authorized to inspect. Do not commit real databases, WAL/SHM files, keys, chat exports, nicknames, QQ numbers, or screenshots with personal data. Tests must create small synthetic SQLite databases and encoded messages. Sanitized structure counts and field numbers are enough for a public compatibility report.

The adapter code must be independently written. GPLv3 reference projects may inform research, but their source or generated schemas must not be copied into this MIT-licensed repository. Record observed facts and their tested QQ build in `src/qqnt_export/adapters/clean_room_notes.md`.

Run `python -m pytest -q`, `python -m build`, and inspect `git ls-files` before proposing a change. Use a local worktree and keep temporary exports outside the repository.
