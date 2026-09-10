"""Deterministic transcription from normalized freeze text. Fail if a value is missing."""

from __future__ import annotations

import re
from dataclasses import dataclass



class TranscriptionError(ValueError):
    pass


@dataclass
class FieldDraft:
    field_id: str
    canonical_label: str
    value: object
    raw_text: str | None
    excerpt: str
    locator_strategy: str
    locator_value: str
    occurrence: int | None = None
    notes: str | None = None


def must_find(text: str, excerpt: str, *, where: str) -> str:
    if excerpt not in text:
        raise TranscriptionError(f"{where}: excerpt not in freeze: {excerpt[:120]!r}")
    return excerpt


def first_occurrence_ok(text: str, excerpt: str) -> int | None:
    count = text.count(excerpt)
    if count == 0:
        raise TranscriptionError(f"excerpt not in freeze: {excerpt[:120]!r}")
    if count == 1:
        return None
    return 1


def line_after_label(text: str, label: str) -> str | None:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == label and i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if nxt:
                return nxt
    return None


def after_heading(text: str, heading: str, skip_empty: bool = True) -> str | None:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == heading:
            for nxt in lines[i + 1 :]:
                if skip_empty and not nxt.strip():
                    continue
                return nxt.strip()
    return None
