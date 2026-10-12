from __future__ import annotations

from datetime import datetime, timezone

import pytest

from qqnt_export.errors import SafeFailure
from qqnt_export.models import NormalizedMessage
from qqnt_export.privacy import redact_text, safe_exception_message


def test_redaction_never_returns_private_input() -> None:
    assert redact_text("123456789: private words") == "[REDACTED]"
    assert safe_exception_message(ValueError("key=secret")) == "ValueError"


def test_failure_exposes_only_public_message() -> None:
    failure = SafeFailure("decrypt", "key_validation_failed", "无法验证本机 QQ 数据库")
    assert failure.stage == "decrypt"
    assert "secret" not in repr(failure).lower()


def test_message_requires_timezone_aware_time() -> None:
    with pytest.raises(ValueError):
        NormalizedMessage(datetime(2026, 1, 1), "self", "text", "example")
    message = NormalizedMessage(datetime(2026, 1, 1, tzinfo=timezone.utc), "self", "text", "example")
    assert message.content == "example"
