from __future__ import annotations

from pathlib import Path

from qqnt_export.models import CompatibilityResult, DatabaseSource


class QQNT9927Adapter:
    name = "qqnt_9_9_27_windows"
    header_bytes = 1024

    def probe(self, source: DatabaseSource) -> CompatibilityResult:
        version = source.qq_version.strip()
        if version != "9.9.27" and not version.startswith("9.9.27."):
            return CompatibilityResult(False, self.name, "unsupported_version")
        if source.db_path.name.casefold() != "nt_msg.db":
            return CompatibilityResult(False, self.name, "unexpected_database_name")
        try:
            with source.db_path.open("rb") as handle:
                header = handle.read(40)
        except OSError:
            return CompatibilityResult(False, self.name, "unreadable_database")
        if len(header) < 40 or header[:16] != b"SQLite format 3\x00" or header[32:40] != b"QQ_NT DB":
            return CompatibilityResult(False, self.name, "unexpected_encrypted_header")
        return CompatibilityResult(True, self.name, "ok")

    def snapshot_paths(self, source: DatabaseSource) -> tuple[Path, ...]:
        db = source.db_path
        return (db, Path(str(db) + "-wal"), Path(str(db) + "-shm"))
