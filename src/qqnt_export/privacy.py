from __future__ import annotations


def redact_text(value: str) -> str:
    return "[REDACTED]" if value else ""


def safe_exception_message(error: BaseException) -> str:
    return type(error).__name__
