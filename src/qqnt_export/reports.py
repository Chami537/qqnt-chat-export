from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Mapping


SAFE_REPORT_KEYS = frozenset({"stage", "code", "qq_version", "adapter", "status", "message_count", "time_range", "quick_check"})
_SAFE_TOKEN = re.compile(r"^[a-zA-Z0-9_.:-]{1,64}$")
_SAFE_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){1,3}$")
_SAFE_STATUS = frozenset({"ok", "failed", "supported", "unsupported", "complete"})


def _safe_value(key: str, value: object) -> object:
    if key not in SAFE_REPORT_KEYS:
        return "[REDACTED]"
    if key == "message_count":
        return value if isinstance(value, int) and value >= 0 else "[REDACTED]"
    if key == "qq_version":
        return value if isinstance(value, str) and _SAFE_VERSION.fullmatch(value) else "[REDACTED]"
    if key == "status":
        return value if value in _SAFE_STATUS else "[REDACTED]"
    if key == "quick_check":
        return value if value in ("ok", "failed") else "[REDACTED]"
    if key == "time_range":
        if isinstance(value, list) and len(value) == 2 and all(isinstance(v, str) and len(v) <= 35 and re.fullmatch(r"[0-9T:+-]+", v) for v in value):
            return value
        return "[REDACTED]"
    return value if isinstance(value, str) and _SAFE_TOKEN.fullmatch(value) else "[REDACTED]"


def write_safe_report(path: Path, report: Mapping[str, object]) -> None:
    safe = {key: _safe_value(key, value) for key, value in report.items()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
