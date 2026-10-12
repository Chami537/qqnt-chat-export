from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Mapping, Any

from .base import DecryptConfig, MessageSource
from qqnt_export.models import CompatibilityResult, DatabaseSource, NormalizedMessage


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
        if len(header) < 40 or header[:16] != b"SQLite header 3\x00" or header[32:40] != b"QQ_NT DB":
            return CompatibilityResult(False, self.name, "unexpected_encrypted_header")
        return CompatibilityResult(True, self.name, "ok")

    def snapshot_paths(self, source: DatabaseSource) -> tuple[Path, ...]:
        db = source.db_path
        return (db, Path(str(db) + "-wal"), Path(str(db) + "-shm"))

    def decrypt_config(self) -> DecryptConfig:
        return DecryptConfig(1024, 4096, 4000, "HMAC_SHA1", "PBKDF2_HMAC_SHA512")

    def message_sources(self, database) -> tuple[MessageSource, ...]:
        return (MessageSource("c2c", "c2c_msg_table"), MessageSource("group", "group_msg_table"))

    def parse_message(self, row: Mapping[str, Any], kind: str, account: str) -> NormalizedMessage:
        from qqnt_export.messages import parse_40800

        timestamp = row["40050"]
        try:
            occurred_at = datetime.fromtimestamp(int(timestamp), timezone(timedelta(hours=8))) if timestamp and int(timestamp) > 0 else None
        except (TypeError, ValueError, OverflowError, OSError):
            occurred_at = None
        sender = str(row["40033"] or "")
        role = "self" if sender == account else ("member" if kind == "group" else "peer")
        content_type, content, fallback = parse_40800(row["40800"])
        return NormalizedMessage(
            occurred_at, role, content_type, content, fallback,
            str(row["40001"]) if row["40001"] is not None else None,
        )
