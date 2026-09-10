"""Copy source fields from normalized freeze text. Never invent values."""

from __future__ import annotations

from record import locator
from active import active_slots
from slots import Slot
from transcribe_lib import FieldDraft, TranscriptionError


def transcribe_slot(slot: Slot, text: str) -> list[FieldDraft]:
    from config import SLOTS_NAME

    if SLOTS_NAME not in {"courses_30", "dynamic"}:
        raise TranscriptionError(
            f"{slot.record_id}: GOLDEN_SET_SLOTS={SLOTS_NAME!r} is not supported here. "
            "This folder builds Course packs from catalog URLs; the mixed-entity v4 "
            "replay lives in its own tool."
        )
    from transcribe_courses import extract_course

    drafts = extract_course(slot, text)
    if not drafts:
        raise TranscriptionError(f"{slot.record_id}: no fields transcribed")
    for d in drafts:
        if d.excerpt not in text:
            raise TranscriptionError(f"{slot.record_id}: excerpt missing {d.excerpt[:160]!r}")
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
