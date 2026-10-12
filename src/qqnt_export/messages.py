from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from typing import Iterator

from .adapters.base import MessageSource, QQNTAdapter
from .models import NormalizedMessage


@dataclass(frozen=True)
class WireField:
    number: int
    wire_type: int
    value: int | bytes


def _varint(data: bytes, index: int) -> tuple[int, int]:
    value = 0
    for shift in range(0, 70, 7):
        if index >= len(data):
            raise ValueError("truncated varint")
        byte = data[index]
        index += 1
        value |= (byte & 0x7f) << shift
        if byte < 0x80:
            return value, index
    raise ValueError("oversized varint")


def read_wire_fields(data: bytes) -> list[WireField]:
    if len(data) > 16 << 20:
        raise ValueError("payload too large")
    result: list[WireField] = []
    index = 0
    while index < len(data):
        if len(result) >= 4096:
            raise ValueError("too many fields")
        tag, index = _varint(data, index)
        number, wire_type = tag >> 3, tag & 7
        if number == 0:
            raise ValueError("invalid field number")
        if wire_type == 0:
            value, index = _varint(data, index)
        elif wire_type == 2:
            length, index = _varint(data, index)
            if length > len(data) - index:
                raise ValueError("truncated field")
            value = data[index:index + length]
            index += length
        elif wire_type in (1, 5):
            length = 8 if wire_type == 1 else 4
            if length > len(data) - index:
                raise ValueError("truncated fixed field")
            value = data[index:index + length]
            index += length
        else:
            raise ValueError("unsupported wire type")
        result.append(WireField(number, wire_type, value))
    return result


def unknown_fallback(payload: bytes, fields: list[WireField] | None = None) -> dict[str, object]:
    return {
        "byte_length": len(payload),
        "sha256_prefix": hashlib.sha256(payload).hexdigest()[:12],
        "fields": [
            {"number": item.number, "wire_type": item.wire_type,
             "length": len(item.value) if isinstance(item.value, bytes) else None}
            for item in (fields or [])[:32]
        ],
    }


_KNOWN_TYPES = {2: "media", 6: "emoji", 7: "quote", 8: "system"}
_MARKERS = {"media": "[媒体消息]", "emoji": "[表情消息]", "quote": "[引用消息]", "system": "[系统消息]"}


def parse_40800(payload: bytes | None) -> tuple[str, str | None, dict[str, object] | None]:
    if not payload:
        return "unknown", None, unknown_fallback(payload or b"")
    try:
        outer = read_wire_fields(payload)
        segments = [field for field in outer if field.number == 40800 and field.wire_type == 2]
        if not segments or len(segments) != len(outer):
            return "unknown", None, unknown_fallback(payload, outer)
        kinds: list[str] = []
        rendered: list[str] = []
        unknown_fields: list[WireField] = []
        for segment in segments:
            inner = read_wire_fields(segment.value)
            content_type = next((field.value for field in inner if field.number == 45002 and field.wire_type == 0), None)
            if content_type == 1:
                values = [field.value for field in inner if field.number == 45101 and field.wire_type == 2]
                if not values:
                    kinds.append("unknown")
                    unknown_fields.extend(inner)
                    rendered.append("[未识别消息结构]")
                    continue
                try:
                    rendered.append("".join(value.decode("utf-8") for value in values))
                    kinds.append("text")
                except UnicodeDecodeError:
                    kinds.append("unknown")
                    unknown_fields.extend(inner)
                    rendered.append("[未识别消息结构]")
            elif content_type in _KNOWN_TYPES:
                kind = _KNOWN_TYPES[content_type]
                kinds.append(kind)
                rendered.append(_MARKERS[kind])
            else:
                kinds.append("unknown")
                unknown_fields.extend(inner)
                rendered.append("[未识别消息结构]")
        fallback = unknown_fallback(payload, unknown_fields) if "unknown" in kinds else None
        if len(kinds) == 1:
            kind = kinds[0]
            return kind, rendered[0] if kind == "text" else None, fallback
        return "mixed", "".join(rendered), fallback
    except (ValueError, TypeError):
        return "unknown", None, unknown_fallback(payload)


def iter_messages(
    connection: sqlite3.Connection,
    source: MessageSource,
    adapter: QQNTAdapter,
    account: str,
    where_sql: str = "",
    params: tuple[object, ...] = (),
) -> Iterator[NormalizedMessage]:
    if source.table not in {"c2c_msg_table", "group_msg_table"}:
        raise ValueError("unrecognized message table")
    query = f'SELECT "40001", "40013", "40030", "40033", "40050", "40800" FROM "{source.table}"'
    if where_sql:
        query += " WHERE " + where_sql
    query += ' ORDER BY "40050", "40001"'
    for row in connection.execute(query, params):
        yield adapter.parse_message(row, source.kind, account)
