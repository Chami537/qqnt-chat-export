from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Mapping


@dataclass(frozen=True)
class CompatibilityResult:
    supported: bool
    adapter: str
    reason: str


@dataclass(frozen=True)
class DatabaseSource:
    db_path: Path
    account: str
    qq_version: str
    process_id: int
    process_path: Path | None = None


@dataclass(frozen=True)
class ConversationRef:
    kind: Literal["c2c", "group"]
    selector: str
    title: str
    message_count: int


@dataclass(frozen=True)
class NormalizedMessage:
    occurred_at: datetime | None
    sender_role: Literal["self", "peer", "member"]
    content_type: str
    content: str | None
    raw_fallback: Mapping[str, object] | None = None
    message_id: str | None = None

    def __post_init__(self) -> None:
        if self.occurred_at is not None and (self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None):
            raise ValueError("occurred_at must be timezone aware")


@dataclass(frozen=True)
class ExportResult:
    json_path: Path
    markdown_path: Path
    message_count: int
