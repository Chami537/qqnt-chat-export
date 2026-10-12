from datetime import datetime, timedelta, timezone

from qqnt_export.adapters.qqnt_9_9_27 import QQNT9927Adapter
from qqnt_export.messages import parse_40800, unknown_fallback

from fixtures.synthetic_messages import binary, numeric, text_body, unknown_body


def test_text_body_extracts_only_verified_text_field() -> None:
    parsed = parse_40800(text_body("synthetic hello"))
    assert parsed == ("text", "synthetic hello", None)


def test_unknown_payload_keeps_metadata_without_private_bytes() -> None:
    payload = unknown_body()
    kind, text, fallback = parse_40800(payload)
    assert kind == "unknown"
    assert text is None
    assert fallback["byte_length"] == len(payload)
    assert "private payload" not in repr(fallback)


def test_malformed_wire_never_becomes_text() -> None:
    kind, text, fallback = parse_40800(b"\xff\x00secret-text")
    assert kind == "unknown" and text is None
    assert fallback["byte_length"] == len(b"\xff\x00secret-text")


def test_nontext_type_is_explicit_marker() -> None:
    body = binary(40800, numeric(45002, 2) + binary(45402, b"opaque"))
    kind, text, fallback = parse_40800(body)
    assert kind == "media"
    assert text is None
    assert fallback is None


def test_sender_role_uses_sender_identity_not_direction_flag() -> None:
    adapter = QQNT9927Adapter()
    row = {"40001": 17, "40013": 0, "40033": 42, "40050": 1767270600, "40800": text_body("hello")}
    message = adapter.parse_message(row, "c2c", "42")
    assert message.sender_role == "self"
    assert message.occurred_at.utcoffset() == timedelta(hours=8)
