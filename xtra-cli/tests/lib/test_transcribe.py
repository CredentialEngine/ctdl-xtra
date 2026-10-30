"""Transcription for the pack builder, and the entities a page carries."""

from __future__ import annotations

from pathlib import Path

import dynamic_slots
import pytest
import transcribe
from lib_doubles import example_slot
from template_texts import CLEAN_CATALOG
from transcribe_lib import FieldDraft, TranscriptionError


def test_transcribe_slot_returns_the_template_fields() -> None:
    drafts = transcribe.transcribe_slot(example_slot(), CLEAN_CATALOG)
    assert [d.canonical_label for d in drafts][:2] == [
        "course_id",
        "course_name",
    ]


def test_a_page_that_yields_no_fields_is_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transcribe, "extract_course", lambda slot, text: [])
    with pytest.raises(TranscriptionError, match="no fields transcribed"):
        transcribe.transcribe_slot(example_slot(), CLEAN_CATALOG)


def test_a_field_whose_excerpt_is_not_printed_is_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = FieldDraft(
        "src_001", "course_id", "X", None, "Not printed", "text_anchor", "h1"
    )
    monkeypatch.setattr(
        transcribe, "extract_course", lambda slot, text: [draft]
    )
    with pytest.raises(
        TranscriptionError, match="excerpt missing 'Not printed'"
    ):
        transcribe.transcribe_slot(example_slot(), CLEAN_CATALOG)


def test_the_entities_on_a_page_are_the_slots_that_share_it(pack: Path) -> None:
    course = example_slot()
    link = example_slot(record_id="example-engl101-link", entity_type="Link")
    other = example_slot(
        record_id="example-math101-course",
        requested_url="https://catalog.example.edu/math/math101",
    )
    dynamic_slots.write_slots([course, link, other])
    assert transcribe.entities_for_page(course, CLEAN_CATALOG) == [
        {
            "provisional_id": rid,
            "entity_type": entity_type,
            "locator": {
                "strategy": "whole_document",
                "value": rid,
                "occurrence": None,
                "page_number": None,
                "bbox": None,
            },
        }
        for rid, entity_type in (
            ("example-engl101-course", "Course"),
            ("example-engl101-link", "Link"),
        )
    ]
