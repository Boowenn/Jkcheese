from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import base64
import re
import zlib


class ProtoSheetError(RuntimeError):
    """Raised when Tencent Docs sheet data cannot be decoded."""


@dataclass(frozen=True, slots=True)
class ProtoField:
    number: int
    wire_type: int
    value: int | float | bytes


def decode_related_sheet(encoded: str) -> dict[int, dict[int, str]]:
    """Decode the compressed Tencent Docs sheet payload into a sparse grid."""

    try:
        payload = zlib.decompress(base64.b64decode(encoded))
    except (ValueError, zlib.error) as exc:
        raise ProtoSheetError("Tencent Docs related_sheet payload is not valid compressed data.") from exc

    sheet = _first_path(payload, (1, 5, 19))
    if sheet is None:
        raise ProtoSheetError("Tencent Docs sheet payload did not contain a readable grid.")

    value_tables = _children(sheet, 5)
    if not value_tables:
        raise ProtoSheetError("Tencent Docs sheet payload did not contain value tables.")

    values = value_tables[0]
    simple_values = [_first_text(record) for record in _children(values, 1)]
    rich_values = [_text_runs(record) for record in _children(values, 2)]

    grid: dict[int, dict[int, str]] = {}
    for cell in _children(sheet, 6):
        varints = _flatten_varints(cell)
        row = _first_int(varints.get("1"), default=0)
        col = _first_int(varints.get("2"), default=0)
        value_type = _first_int(varints.get("3.1"), default=None)
        value_ref = _first_int(varints.get("3.2.1"), default=None)
        value = _resolve_cell_value(value_type, value_ref, simple_values, rich_values)
        if value:
            grid.setdefault(row, {})[col] = value
    return grid


def _resolve_cell_value(
    value_type: int | None,
    value_ref: int | None,
    simple_values: list[str],
    rich_values: list[tuple[str, ...]],
) -> str:
    if value_ref is None:
        return ""
    if value_type == 6 and 0 <= value_ref < len(rich_values):
        return " / ".join(rich_values[value_ref])
    if 0 <= value_ref < len(simple_values):
        return simple_values[value_ref]
    return ""


def _first_text(message: bytes) -> str:
    texts = _text_runs(message)
    return texts[-1] if texts else ""


def _text_runs(message: bytes) -> tuple[str, ...]:
    texts: list[str] = []

    def visit(blob: bytes, depth: int = 0) -> None:
        for field in _parse_fields(blob):
            if field.wire_type != 2:
                continue
            child = field.value
            if not isinstance(child, bytes):
                continue
            text = _decode_text(child)
            if text:
                cleaned = _clean_text(text)
                if _is_useful_text(cleaned):
                    texts.append(cleaned)
            if depth < 5:
                visit(child, depth + 1)

    visit(message)

    deduped: list[str] = []
    for text in texts:
        if text not in deduped:
            deduped.append(text)
    return tuple(deduped)


def _clean_text(text: str) -> str:
    cleaned = text.strip()
    while cleaned and ord(cleaned[0]) < 32:
        cleaned = cleaned[1:].strip()
    if len(cleaned) > 1 and cleaned[0].isascii() and cleaned[0].isalpha():
        if _starts_with_cjk_or_code(cleaned[1:]):
            cleaned = cleaned[1:].strip()
    return cleaned


def _starts_with_cjk_or_code(text: str) -> bool:
    return bool(text) and (text.startswith("【") or "\u4e00" <= text[0] <= "\u9fff")


def _is_useful_text(text: str) -> bool:
    if not text:
        return False
    if "http://" in text or "https://" in text or "docimg" in text:
        return False
    if re.fullmatch(r"[0-9a-fA-F]{8}", text):
        return False
    if re.fullmatch(r"[0-9a-fA-F-]{20,}", text):
        return False
    return any("\u4e00" <= char <= "\u9fff" for char in text) or "【阵容码】" in text


def _decode_text(blob: bytes) -> str:
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        return ""
    if not text:
        return ""
    printable = sum(char.isprintable() or char in "\r\n\t" for char in text)
    if printable / len(text) < 0.8:
        return ""
    return text


def _flatten_varints(message: bytes) -> dict[str, list[int]]:
    values: dict[str, list[int]] = {}

    def visit(blob: bytes, prefix: str = "", depth: int = 0) -> None:
        for field in _parse_fields(blob):
            path = f"{prefix}.{field.number}" if prefix else str(field.number)
            if field.wire_type == 0 and isinstance(field.value, int):
                values.setdefault(path, []).append(field.value)
            elif field.wire_type == 2 and isinstance(field.value, bytes) and depth < 6:
                visit(field.value, path, depth + 1)

    visit(message)
    return values


def _first_int(values: list[int] | None, default: int | None) -> int | None:
    return values[0] if values else default


def _first_path(message: bytes, path: Iterable[int]) -> bytes | None:
    current: list[bytes] = [message]
    for number in path:
        next_messages: list[bytes] = []
        for candidate in current:
            next_messages.extend(_children(candidate, number))
        if not next_messages:
            return None
        current = next_messages
    return current[0]


def _children(message: bytes, number: int) -> list[bytes]:
    return [
        field.value
        for field in _parse_fields(message)
        if field.number == number and field.wire_type == 2 and isinstance(field.value, bytes)
    ]


def _parse_fields(message: bytes) -> list[ProtoField]:
    fields: list[ProtoField] = []
    index = 0
    end = len(message)
    while index < end:
        try:
            key, index = _read_varint(message, index, end)
        except ProtoSheetError:
            break
        number = key >> 3
        wire_type = key & 7
        if wire_type == 0:
            try:
                value, index = _read_varint(message, index, end)
            except ProtoSheetError:
                break
        elif wire_type == 1:
            if index + 8 > end:
                break
            value = message[index : index + 8]
            index += 8
        elif wire_type == 2:
            try:
                length, index = _read_varint(message, index, end)
            except ProtoSheetError:
                break
            if index + length > end:
                break
            value = message[index : index + length]
            index += length
        elif wire_type == 5:
            if index + 4 > end:
                break
            value = message[index : index + 4]
            index += 4
        else:
            break
        fields.append(ProtoField(number=number, wire_type=wire_type, value=value))
    return fields


def _read_varint(message: bytes, index: int, end: int) -> tuple[int, int]:
    shift = 0
    result = 0
    while index < end:
        byte = message[index]
        index += 1
        result |= (byte & 0x7F) << shift
        if byte < 0x80:
            return result, index
        shift += 7
        if shift > 70:
            break
    raise ProtoSheetError("Invalid protobuf varint in Tencent Docs sheet payload.")
