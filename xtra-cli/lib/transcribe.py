"""Copy source fields from normalized freeze text. Never invent values."""

from __future__ import annotations

from active import active_slots
from record import locator
from slots import Slot
from transcribe_courses import extract_course
from transcribe_lib import FieldDraft, TranscriptionError


def transcribe_slot(slot: Slot, text: str) -> list[FieldDraft]:
    drafts = extract_course(slot, text)
    if not drafts:
        raise TranscriptionError(f"{slot.record_id}: no fields transcribed")
    for d in drafts:
        if d.excerpt not in text:
            raise TranscriptionError(
                f"{slot.record_id}: excerpt missing {d.excerpt[:160]!r}"
            )
    return drafts


def entities_for_page(slot: Slot, text: str) -> list[dict]:
    same = [s for s in active_slots() if s.stem == slot.stem]
    return [
        {
            "provisional_id": s.record_id,
            "entity_type": s.entity_type,
            "locator": locator("whole_document", s.record_id),
        }
        for s in same
    ]
