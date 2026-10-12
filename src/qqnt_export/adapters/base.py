from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from qqnt_export.models import CompatibilityResult, DatabaseSource, NormalizedMessage


@dataclass(frozen=True)
class DecryptConfig:
    header_bytes: int
    page_size: int
    kdf_iter: int
    hmac_algorithm: str
    kdf_algorithm: str


@dataclass(frozen=True)
class MessageSource:
    kind: str
    table: str


class QQNTAdapter(Protocol):
    name: str

    def probe(self, source: DatabaseSource) -> CompatibilityResult: ...

    def snapshot_paths(self, source: DatabaseSource) -> tuple[Path, ...]: ...

    def decrypt_config(self) -> DecryptConfig: ...

    def message_sources(self, database: sqlite3.Connection) -> Sequence[MessageSource]: ...

    def parse_message(self, row: sqlite3.Row, kind: str, account: str) -> NormalizedMessage: ...
