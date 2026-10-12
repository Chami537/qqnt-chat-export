from __future__ import annotations


def varint(number: int) -> bytes:
    output = bytearray()
    while number >= 0x80:
        output.append((number & 0x7F) | 0x80)
        number >>= 7
    output.append(number)
    return bytes(output)


def numeric(field: int, value: int) -> bytes:
    return varint(field << 3) + varint(value)


def binary(field: int, value: bytes) -> bytes:
    return varint((field << 3) | 2) + varint(len(value)) + value


def text_body(text: str) -> bytes:
    segment = numeric(45002, 1) + binary(45101, text.encode("utf-8"))
    return binary(40800, segment)


def unknown_body() -> bytes:
    return binary(40800, numeric(45002, 99) + binary(49999, b"private payload"))
