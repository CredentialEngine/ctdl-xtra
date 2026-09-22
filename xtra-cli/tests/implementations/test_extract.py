from __future__ import annotations

import pytest

from implementations.extract import extract_record, slot_from_dict
from transcribe_lib import TranscriptionError


def test_slot_from_dict_builds_course_slot(engl101_slot: dict) -> None:
    slot = slot_from_dict(engl101_slot)
    assert slot.record_id == "example-engl101-course"
    assert slot.entity_type == "Course"
    assert slot.requested_url.endswith("/engl101")
    assert slot.stem


def test_extract_record_from_fixture(engl101_html: str, engl101_slot: dict) -> None:
    slot = slot_from_dict(engl101_slot)
    record = extract_record(slot, engl101_html, retrieved_at="2026-09-14T18:12:00Z")
    assert record["verification"]["status"] == "candidate"
    assert record["catalogue_type"] == "COURSES"
    assert record["expected"]["course_id"] == "ENGL101"
    assert record["expected"]["course_name"] == "Composition I"
    assert record["expected"]["course_credits"] == 3
    assert record["ctdl_expected"]["class_uri"] == "ceterms:Course"
    assert record["retrieved_at"] == "2026-09-14T18:12:00Z"
    assert record["template_id"] == "clean_catalog_course_detail"


def test_extract_record_unknown_template_fails_closed(engl101_slot: dict) -> None:
    slot = slot_from_dict({**engl101_slot, "template_id": ""})
    with pytest.raises(TranscriptionError):
        extract_record(slot, "<html><body>unrelated page</body></html>")
