"""Thin dispatcher over the per-family course extractors in templates/.

This module knows nothing about any catalog layout. It picks a template from
the freeze text and calls the matching extractor. Each catalog family lives in
its own file under templates/ (clean_catalog.py, coursedog.py, acalog.py).

Kept as the import surface so college_capture and transcribe do not change.
"""

from __future__ import annotations

import sys

from slots import Slot
from transcribe_lib import FieldDraft, TranscriptionError
from templates import FAMILY_OF, TEMPLATE, detect_template

__all__ = ["TEMPLATE", "FAMILY_OF", "detect_template", "extract_course"]


def extract_course(slot: Slot, text: str) -> list[FieldDraft]:
    """Extract one course from normalized freeze text. Fails closed, no LLM fallback."""
    tid = detect_template(text)
    if tid is None and slot.template_id in TEMPLATE:
        print(
            f"warning: detect_template=None for {slot.record_id}; "
            f"using slot.template_id={slot.template_id!r}",
            file=sys.stderr,
        )
        tid = slot.template_id
    if tid not in TEMPLATE:
        raise TranscriptionError(
            f"{slot.record_id}: freeze does not match a known course template "
            "(Clean Catalog, Coursedog, or Acalog). No LLM fallback."
        )
    return TEMPLATE[tid](text)
