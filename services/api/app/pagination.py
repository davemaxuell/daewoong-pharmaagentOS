from __future__ import annotations

import base64
import json


class InvalidCursor(ValueError):
    pass


def encode_cursor(offset: int) -> str:
    payload = json.dumps({"v": 1, "o": offset}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    if len(cursor) > 2_048:
        raise InvalidCursor("cursor is too long")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if value.get("v") != 1 or not isinstance(value.get("o"), int):
            raise ValueError
        offset = value["o"]
        if offset < 0 or offset > 10_000_000:
            raise ValueError
        return offset
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidCursor("cursor is malformed") from exc


def page_window[T](items: list[T], *, offset: int, limit: int) -> tuple[list[T], str | None, bool]:
    page = items[offset : offset + limit]
    has_more = len(items) > offset + limit
    return page, encode_cursor(offset + limit) if has_more else None, has_more
