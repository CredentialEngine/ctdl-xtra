"""Deterministic extract, two readings deep. No LLM fallback.

A course page is read by the college templates in lib/templates, which
know one college's layout each. What they do not match, and every page
that is not a course, is read from the markup by extract_dom: the label a
platform marks up says what the value beside it is, whichever college
printed it.
"""

from __future__ import annotations

from typing import Any

from common.clock import utc_timestamp
from implementations.engine import load_engine
from implementations.extract_dom import (
    ENTITY_COURSE,
    NothingToExtract,
    entity_type_for,
    extract_fields,
)

load_engine()

from html_text import slug_url
from mapping import map_fields
from normalize import normalize_html
from slots import Slot
from transcribe_courses import detect_template, extract_course
from transcribe_lib import TranscriptionError

# What the record says read it, when the markup did rather than a
# college template.
MARKUP_TEMPLATE_ID = "markup"


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


def slot_from_labels_entry(
    entry: dict[str, Any],
    *,
    retrieved_at: str | None = None,
    entity_type: str | None = None,
    record_id: str | None = None,
) -> Slot:
    """One queued page from the discovery list.

    Institution, family, and template are left empty on purpose. Discovery
    says what a page is about; which extractor fits is still decided by
    reading the page, in one place.

    The entity type is the one thing taken from discovery, because
    discovery is what decided it: a page labelled Credential produces a
    credential record, and no amount of reading the page again changes
    that.
    """
    stem = entry["stem"]
    return Slot(
        record_id or stem,
        entity_type or entity_type_for(entry.get("labels") or []) or "Course",
        entry["url"],
        "",
        "",
        "",
        "1",
        stem,
        None,
        retrieved_at,
        False,
        "",
    )


def _course_from_template(slot: Slot, text: str) -> tuple[list[Any], str]:
    template_id = detect_template(text) or slot.template_id
    if not template_id:
        raise TranscriptionError(
            f"{slot.record_id}: freeze does not match a known course template"
        )
    return extract_course(slot, text), template_id


def transcribe(slot: Slot, html: str) -> tuple[list[Any], str]:
    """The page's printed fields, and what read them.

    A course page goes to the college templates first: they are the
    verified path, they have fixtures behind them, and where one matches
    it is the answer. Anything they do not match is read from the markup,
    which is also the only way the other three entities are read at all -
    the templates are course templates, and a credential page has no
    course block for them to find.
    """
    if slot.entity_type == ENTITY_COURSE:
        text = normalize_html(html)
        try:
            return _course_from_template(slot, text)
        except TranscriptionError:
            pass
    try:
        return extract_fields(slot.entity_type, html), MARKUP_TEMPLATE_ID
    except NothingToExtract as exc:
        # One failure for the caller, whichever reading came up empty:
        # this stage fails closed and says why, it does not write a
        # record with nothing in it.
        raise TranscriptionError(f"{slot.record_id}: {exc}") from exc


def extract_record(
    slot: Slot,
    html: str,
    *,
    retrieved_at: str | None = None,
    stem: str | None = None,
) -> dict[str, Any]:
    drafts, template_id = transcribe(slot, html)
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
        # Slot.stem is the old slug. Storage keys use the crawl stem, so
        # the record has to carry that one or nothing can find its page.
        "stem": stem or slot.stem or slug_url(slot.requested_url),
        "retrieved_at": retrieved_at or utc_timestamp(),
        "verification": {"status": "candidate"},
        "source_expected": {"fields": fields},
        "expected": expected,
        "ctdl_expected": map_fields(slot.entity_type, fields),
    }
