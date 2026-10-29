"""Deterministic extract, two readings deep. No LLM fallback.

A course page is read by the college templates in lib/templates, which
know one college's layout each. What they do not match, and every page
that is not a course, is read from the markup by extract_dom: the label a
platform marks up says what the value beside it is, whichever college
printed it.

The record names what was read by the CTDL term it goes out under, not by
the label the reader gave it, and a course record carries the minimum
data for courses and nothing more. See TERMS.
"""

from __future__ import annotations

import re
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
from normalize import normalize_html
from slots import Slot
from transcribe_courses import detect_template, extract_course
from transcribe_lib import TranscriptionError

# What the record says read it, when the markup did rather than a
# college template.
MARKUP_TEMPLATE_ID = "markup"

CODED_NOTATION = "ceterms:codedNotation"
IDENTIFIER = "ceterms:identifier"
SUBJECT_WEBPAGE = "ceterms:subjectWebpage"
CREDIT_MIN = "ceterms:creditMinValue"
CREDIT_MAX = "ceterms:creditMaxValue"

# The "low-high" a reader writes a printed credit range as.
CREDIT_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)")
RANGE_NOTE = (
    "Printed range; its two ends are creditMinValue and creditMaxValue."
)

# The CTDL term each label the readers write goes out under, as the
# Learning Opportunity bulk-upload template names them; that template is
# why a printed credit range is creditMinValue and creditMaxValue. A
# course carries the minimum data for courses and nothing more. A label
# missing here is still read, because every field read counts toward the
# two a page needs to be a record at all, but the record leaves it out.
TERMS = {
    "course_id": CODED_NOTATION,
    "course_name": "ceterms:name",
    "course_description": "ceterms:description",
    "course_credits": "ceterms:creditValue",
    "course_credits_min": "ceterms:creditMinValue",
    "course_credits_max": "ceterms:creditMaxValue",
    "course_credits_unit": "ceterms:creditUnitType",
    "course_prerequisites": "ceterms:prerequisite",
    "learning_program_id": CODED_NOTATION,
    "learning_program_name": "ceterms:name",
    "learning_program_description": "ceterms:description",
    "credential_name": "ceterms:name",
    "credential_description": "ceterms:description",
    "competency_framework_name": "ceasn:name",
    "competency_text": "ceasn:competencyText",
}


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


def _field(
    field_id: str, prop: str, value: Any, raw_text: Any, notes: Any
) -> dict[str, Any]:
    return {
        "field_id": field_id,
        "property": prop,
        "presence": "present",
        "value": value,
        "raw_text": raw_text,
        "notes": notes,
    }


def _credit_range(draft: Any) -> tuple[float, float] | None:
    """The two ends of a printed credit range, "1.0-8.0", or None."""
    if draft.canonical_label != "course_credits":
        return None
    match = CREDIT_RANGE_RE.fullmatch(str(draft.value).strip())
    if match is None:
        return None
    return float(match.group(1)), float(match.group(2))


def record_fields(
    entity_type: str, drafts: list[Any], source_url: str
) -> list[dict[str, Any]]:
    """The record's fields, each named by the CTDL term it goes out under.

    A draft whose label has no term in TERMS is left out. A course also
    states two things its page prints no field for: its code as its
    external identifier, and the page itself as its subject webpage.
    """
    fields: list[dict[str, Any]] = []
    for index, draft in enumerate(drafts, start=1):
        if draft.canonical_label not in TERMS:
            continue
        field_id = draft.field_id or f"f_{index:03d}"
        bounds = _credit_range(draft)
        if bounds is None:
            fields.append(
                _field(
                    field_id,
                    TERMS[draft.canonical_label],
                    draft.value,
                    draft.raw_text,
                    draft.notes,
                )
            )
            continue
        # A printed range is two values, never one creditValue.
        low, high = bounds
        fields.append(
            _field(field_id, CREDIT_MIN, low, draft.raw_text, RANGE_NOTE)
        )
        fields.append(
            _field(
                f"{field_id}_max", CREDIT_MAX, high, draft.raw_text, RANGE_NOTE
            )
        )
    if entity_type == ENTITY_COURSE:
        fields.extend(_course_derived(fields, source_url))
    return fields


def _course_derived(
    fields: list[dict[str, Any]], source_url: str
) -> list[dict[str, Any]]:
    derived = []
    code = next(
        (field for field in fields if field["property"] == CODED_NOTATION),
        None,
    )
    if code is not None:
        derived.append(
            (
                IDENTIFIER,
                code["value"],
                code["raw_text"],
                "The printed course code, used as the external identifier.",
            )
        )
    derived.append((SUBJECT_WEBPAGE, source_url, None, "The page's own URL."))
    return [
        _field(f"derived_{index:03d}", prop, value, raw_text, notes)
        for index, (prop, value, raw_text, notes) in enumerate(derived, start=1)
    ]


def expected_values(fields: list[dict[str, Any]]) -> dict[str, Any]:
    """{term: value} for the record's present fields.

    A term read more than once keeps every value, as a list in the order
    they were read. A competency list is several outcomes under one term,
    and a plain mapping would keep only the last of them.
    """
    values: dict[str, list[Any]] = {}
    for field in fields:
        if field.get("presence") == "present":
            values.setdefault(field["property"], []).append(field["value"])
    return {
        prop: found[0] if len(found) == 1 else found
        for prop, found in values.items()
    }


def extract_record(
    slot: Slot,
    html: str,
    *,
    retrieved_at: str | None = None,
    stem: str | None = None,
) -> dict[str, Any]:
    drafts, template_id = transcribe(slot, html)
    fields = record_fields(slot.entity_type, drafts, slot.requested_url)
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
        "expected": expected_values(fields),
    }
