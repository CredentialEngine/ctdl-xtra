"""Value normalization: the "pass bar" comparison and record identity."""

from __future__ import annotations

import re

_WS = re.compile(r"\s+")


def normalize_value(value: str | None) -> str:
    """Whitespace/case-insensitive form used to decide if two values match."""
    if value is None:
        return ""
    return _WS.sub(" ", value).strip().lower()


def values_match(a: str | None, b: str | None) -> bool:
    return normalize_value(a) == normalize_value(b)


def record_id_from_code(code: str) -> str:
    """'ABDY 113' and 'ABDY113' are the same course: strip spaces, upper-case."""
    return _WS.sub("", code).upper()


def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)
