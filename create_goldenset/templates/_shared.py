"""Helpers shared by every catalog family extractor.

Field ids, occurrence counting, labelled-line lookup, number parsing.
Nothing here knows what a catalog looks like; that lives in the family modules.
"""

from __future__ import annotations

import re

from transcribe_lib import FieldDraft, TranscriptionError


def _f(field_id, label, value, excerpt, loc, *, raw=None, notes=None, occ=None) -> FieldDraft:
    return FieldDraft(
        field_id=field_id,
        canonical_label=label,
        value=value,
        raw_text=raw if raw is not None else (excerpt if isinstance(value, str) else excerpt),
        excerpt=excerpt,
        locator_strategy="text_anchor",
        locator_value=loc,
        occurrence=occ,
        notes=notes,
    )


def _occ(text: str, excerpt: str) -> int | None:
    n = text.count(excerpt)
    if n == 0:
        raise TranscriptionError(f"missing {excerpt[:160]!r}")
    return None if n == 1 else 1


def _line_after(text: str, label: str) -> str | None:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == label:
            for nxt in lines[i + 1 :]:
                if nxt.strip():
                    return nxt
    return None


def _num(txt: str):
    t = txt.strip()
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    if re.fullmatch(r"-?\d+\.\d+", t):
        return float(t)
    raise TranscriptionError(f"not a number: {txt!r}")


def _add(drafts: list[FieldDraft], label: str, value, excerpt: str, loc: str, text: str, **kwargs) -> None:
    drafts.append(
        _f(
            f"src_{len(drafts) + 1:03d}",
            label,
            value,
            excerpt,
            loc,
            occ=kwargs.pop("occ", _occ(text, excerpt)),
            **kwargs,
        )
    )


def _maybe_labeled_number(text: str, label: str) -> tuple[object, str] | None:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() != label:
            continue
        for nxt in lines[i + 1 :]:
            if nxt.strip():
                n_txt = nxt.strip()
                return _num(n_txt), f"{label}\n{n_txt}"
    return None


def _prereq_value(block: str) -> str:
    """Keep Prerequisite(s): when the printed remainder is the glued 'and Corequisite' label."""
    block = block.strip()
    prefix = "Prerequisite(s):"
    if not block.startswith(prefix):
        return block
    rest = block[len(prefix) :].strip()
    if rest.lower().startswith("and corequisite"):
        return block
    return rest
