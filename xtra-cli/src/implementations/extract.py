"""Deterministic template extract. No LLM fallback."""

from __future__ import annotations

from typing import Any

from common.clock import utc_timestamp
from implementations.engine import load_engine

load_engine()

from html_text import slug_url
from mapping import map_fields
from normalize import normalize_html
from slots import Slot
from transcribe_courses import detect_template, extract_course
from transcribe_lib import TranscriptionError


def slot_from_dict(payload: dict[str, Any]) -> Slot:
    return Slot(
        payload["record_id"],
        payload.get("entity_type") or "Course",
        payload["requested_url"],
        payload.get("institution_name") or "",
        payload.get("source_family") or "",
        payload.get("template_id") or "",
        payload.get("template_version") or "1",
        payload.get("page_id") or payload["record_id"],
        None,
        payload.get("retrieved_at"),
        payload.get("multi_entity_bundle") or False,
        payload.get("notes") or "",
    )


def extract_record(
    slot: Slot,
    html: str,
    *,
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    text = normalize_html(html)
    template_id = detect_template(text) or slot.template_id
    if not template_id:
        raise TranscriptionError(
            f"{slot.record_id}: freeze does not match a known course template"
        )
    drafts = extract_course(slot, text)
    fields = []
    for index, draft in enumerate(drafts, start=1):
        fields.append(
            {
                "field_id": draft.field_id or f"f_{index:03d}",
                "canonical_label": draft.canonical_label,
                "presence": "present",
                "value": draft.value,
                "raw_text": draft.raw_text,
                "notes": draft.notes,
            }
        )
    expected = {
        field["canonical_label"]: field["value"]
        for field in fields
        if field.get("presence") == "present"
    }
    return {
        "id": slot.record_id,
        "record_id": slot.record_id,
        "catalogue_type": "COURSES",
        "entity_type": slot.entity_type,
        "source_url": slot.requested_url,
        "institution_name": slot.institution_name,
        "template_id": template_id,
        "stem": slot.stem or slug_url(slot.requested_url),
        "retrieved_at": retrieved_at or utc_timestamp(),
        "verification": {"status": "candidate"},
        "source_expected": {"fields": fields},
        "expected": expected,
        "ctdl_expected": map_fields(slot.entity_type, fields),
    }
