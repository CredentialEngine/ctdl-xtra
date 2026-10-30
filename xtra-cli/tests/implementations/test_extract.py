# ruff: noqa: I001 - importing implementations.extract is what puts src/lib/
# on sys.path, so the engine import below cannot be sorted above it.
from __future__ import annotations

from pathlib import Path

import pytest

from implementations.extract import (
    TERMS,
    expected_values,
    extract_record,
    record_fields,
    slot_from_dict,
)
from inventory import allowed_for
from transcribe_lib import FieldDraft, TranscriptionError

URL = "https://catalog.example.edu/english/engl101"

# The minimum data for courses, and the two ends of a printed credit
# range some templates read as fields of their own.
COURSE_TERMS = {
    "ceterms:identifier",
    "ceterms:name",
    "ceterms:description",
    "ceterms:subjectWebpage",
    "ceterms:codedNotation",
    "ceterms:creditValue",
    "ceterms:creditUnitType",
    "ceterms:prerequisite",
    "ceterms:creditMinValue",
    "ceterms:creditMaxValue",
}


def test_slot_from_dict_builds_course_slot(engl101_slot: dict) -> None:
    slot = slot_from_dict(engl101_slot)
    assert slot.record_id == "example-engl101-course"
    assert slot.entity_type == "Course"
    assert slot.requested_url.endswith("/engl101")
    assert slot.stem


def test_extract_record_from_fixture(
    engl101_html: str, engl101_slot: dict
) -> None:
    slot = slot_from_dict(engl101_slot)
    record = extract_record(
        slot, engl101_html, retrieved_at="2026-09-14T18:12:00Z"
    )
    assert record["verification"]["status"] == "candidate"
    assert record["catalogue_type"] == "COURSES"
    assert record["expected"]["ceterms:codedNotation"] == "ENGL101"
    assert record["expected"]["ceterms:name"] == "Composition I"
    assert record["expected"]["ceterms:creditValue"] == 3
    assert record["retrieved_at"] == "2026-09-14T18:12:00Z"
    assert record["template_id"] == "clean_catalog_course_detail"


def test_a_record_names_its_fields_by_ctdl_term(
    engl101_html: str, engl101_slot: dict
) -> None:
    """The terms are the record: no labels, and no mapping beside them."""
    record = extract_record(slot_from_dict(engl101_slot), engl101_html)
    fields = record["source_expected"]["fields"]
    assert "ctdl_expected" not in record
    assert all("canonical_label" not in field for field in fields)
    assert {field["property"] for field in fields} == set(record["expected"])


def test_a_course_states_its_code_and_its_page(
    engl101_html: str, engl101_slot: dict
) -> None:
    record = extract_record(slot_from_dict(engl101_slot), engl101_html)
    expected = record["expected"]
    assert expected["ceterms:identifier"] == expected["ceterms:codedNotation"]
    assert expected["ceterms:subjectWebpage"] == record["source_url"]


HEADING_GROUP = (
    "<html><head><title>ELEC 150 - Electrical Maintenance</title></head>"
    "<body><main><header class='header'><h2>Electrical Maintenance</h2>"
    "<h3>ELEC 150:</h3><p class='header-x-meta'>4.0 Units</p></header>"
    "<p>Students will progress from basic electrical theory to the "
    "maintenance of industrial systems.</p></main></body></html>"
)


def test_a_markup_course_carries_its_unit_beside_its_credit_value(
    engl101_slot: dict,
) -> None:
    slot = slot_from_dict({**engl101_slot, "template_id": ""})
    record = extract_record(slot, HEADING_GROUP)
    assert record["template_id"] == "markup"
    assert record["expected"]["ceterms:creditValue"] == 4.0
    assert record["expected"]["ceterms:creditUnitType"] == "Units"


def test_a_markup_course_carries_its_printed_prerequisite(
    engl101_slot: dict, fixture_html_dir: Path
) -> None:
    """No template matches this page; its prerequisite is a bold label."""
    html = (fixture_html_dir / "course-single.html").read_text(encoding="utf-8")
    slot = slot_from_dict({**engl101_slot, "template_id": ""})
    record = extract_record(slot, html)
    assert record["template_id"] == "markup"
    assert record["expected"]["ceterms:prerequisite"] == (
        "placement into college-level reading."
    )


def test_a_template_record_has_a_credit_value_and_no_unit(
    engl101_html: str, engl101_slot: dict
) -> None:
    """The college templates do not read the unit."""
    record = extract_record(slot_from_dict(engl101_slot), engl101_html)
    assert record["expected"]["ceterms:creditValue"] == 3
    assert "ceterms:creditUnitType" not in record["expected"]


def draft(field_id: str, label: str, value: object) -> FieldDraft:
    return FieldDraft(
        field_id, label, value, str(value), str(value), "dom_path", "test"
    )


def properties(fields: list[dict]) -> list[str]:
    return [field["property"] for field in fields]


def test_every_term_is_a_ctdl_term() -> None:
    assert all(
        term.startswith(("ceterms:", "ceasn:")) for term in TERMS.values()
    )


def test_a_course_holds_the_minimum_data_for_courses_and_nothing_more() -> None:
    """Every course label read gives these terms and no others.

    Lecture and lab hours, the department and the rest are still read,
    because they count toward the fields a page needs to be a record,
    but the record leaves them out.
    """
    drafts = [
        draft(f"src_{index:03d}", label, "x")
        for index, label in enumerate(sorted(allowed_for("Course")), start=1)
    ]
    assert set(properties(record_fields("Course", drafts, URL))) == (
        COURSE_TERMS
    )


def test_a_label_with_no_term_is_left_out() -> None:
    fields = record_fields(
        "Course",
        [
            draft("f_001", "course_lecture_hours", 3),
            draft("f_002", "course_name", "Composition I"),
        ],
        URL,
    )
    assert [field["field_id"] for field in fields] == ["f_002", "derived_001"]
    assert properties(fields) == ["ceterms:name", "ceterms:subjectWebpage"]


def test_a_course_states_its_printed_code_as_its_external_identifier() -> None:
    fields = record_fields(
        "Course", [draft("src_001", "course_id", "ENGL 101")], URL
    )
    derived = {
        field["property"]: field
        for field in fields
        if field["field_id"].startswith("derived_")
    }
    assert derived["ceterms:identifier"]["value"] == "ENGL 101"
    assert derived["ceterms:identifier"]["raw_text"] == "ENGL 101"
    assert derived["ceterms:subjectWebpage"]["value"] == URL
    assert derived["ceterms:subjectWebpage"]["raw_text"] is None


def test_a_course_with_no_code_has_no_external_identifier() -> None:
    fields = record_fields(
        "Course", [draft("f_001", "course_name", "Composition I")], URL
    )
    assert "ceterms:identifier" not in properties(fields)


def test_only_a_course_states_its_page_as_its_subject_webpage() -> None:
    fields = record_fields(
        "Credential", [draft("f_001", "credential_name", "Nursing AAS")], URL
    )
    assert properties(fields) == ["ceterms:name"]


def test_a_printed_credit_range_is_its_minimum_and_its_maximum() -> None:
    """Some templates read the two ends as fields of their own."""
    expected = expected_values(
        record_fields(
            "Course",
            [
                draft("src_001", "course_credits_min", 1),
                draft("src_002", "course_credits_max", 4),
            ],
            URL,
        )
    )
    assert expected["ceterms:creditMinValue"] == 1
    assert expected["ceterms:creditMaxValue"] == 4
    assert "ceterms:creditValue" not in expected


def test_a_credit_range_read_as_one_value_is_split_into_min_and_max() -> None:
    """eLumen prints "1.0-8.0 Units"; the readers give it as one string."""
    expected = expected_values(
        record_fields(
            "Course",
            [
                draft("f_001", "course_credits", "1.0-8.0"),
                draft("f_002", "course_credits_unit", "Units"),
            ],
            URL,
        )
    )
    assert expected["ceterms:creditMinValue"] == 1.0
    assert expected["ceterms:creditMaxValue"] == 8.0
    assert expected["ceterms:creditUnitType"] == "Units"
    assert "ceterms:creditValue" not in expected


def test_a_single_credit_stays_a_credit_value() -> None:
    expected = expected_values(
        record_fields("Course", [draft("f_001", "course_credits", 3)], URL)
    )
    assert expected["ceterms:creditValue"] == 3
    assert "ceterms:creditMinValue" not in expected


def test_a_term_read_more_than_once_keeps_every_value_in_order() -> None:
    """A competency list is several outcomes under one term."""
    fields = record_fields(
        "Competency",
        [
            draft("f_001", "competency_framework_name", "Program Outcomes"),
            draft("f_002", "competency_text", "Write clearly."),
            draft("f_003", "competency_text", "Read critically."),
        ],
        URL,
    )
    assert expected_values(fields) == {
        "ceasn:name": "Program Outcomes",
        "ceasn:competencyText": ["Write clearly.", "Read critically."],
    }


def test_extract_record_unknown_template_fails_closed(
    engl101_slot: dict,
) -> None:
    slot = slot_from_dict({**engl101_slot, "template_id": ""})
    with pytest.raises(TranscriptionError):
        extract_record(slot, "<html><body>unrelated page</body></html>")
