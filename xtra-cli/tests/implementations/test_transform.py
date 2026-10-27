from __future__ import annotations

import pytest

from implementations.transform import map_fields, to_expected, to_jsonld

RECORD = {
    "id": "example-engl101-course",
    "record_id": "example-engl101-course",
    "catalogue_type": "COURSES",
    "entity_type": "Course",
    "source_url": "https://catalog.example.edu/english/engl101",
    "source_expected": {
        "fields": [
            {
                "field_id": "f_001",
                "canonical_label": "course_id",
                "presence": "present",
                "value": "ENGL101",
            },
            {
                "field_id": "f_002",
                "canonical_label": "course_name",
                "presence": "present",
                "value": "Composition I",
            },
            {
                "field_id": "f_003",
                "canonical_label": "course_credits",
                "presence": "present",
                "value": 3,
            },
        ]
    },
}


def test_to_jsonld_maps_labels_and_omits_ctid() -> None:
    node = to_jsonld(RECORD)
    assert node["@type"] == "ceterms:Course"
    assert node["ceterms:subjectWebpage"] == RECORD["source_url"]
    assert node["ceterms:codedNotation"] == "ENGL101"
    assert node["ceterms:name"] == "Composition I"
    assert "ceterms:ctid" not in node
    assert node["@context"] == "https://credreg.net/ctdl/schema/context/json"


def test_to_expected_scoring_shape() -> None:
    expected = to_expected(RECORD)
    assert expected["id"] == "example-engl101-course"
    assert expected["catalogue_type"] == "COURSES"
    assert expected["source_url"] == RECORD["source_url"]
    assert expected["expected"]["course_id"] == "ENGL101"
    assert expected["expected"]["course_credits"] == 3


def test_to_expected_keeps_existing_expected_dict() -> None:
    record = {**RECORD, "expected": {"course_id": "KEEP"}}
    assert to_expected(record)["expected"] == {"course_id": "KEEP"}


# --- credits ------------------------------------------------------------------


def field(field_id: str, label: str, value: object) -> dict:
    return {
        "field_id": field_id,
        "canonical_label": label,
        "presence": "present",
        "value": value,
    }


def credit_record(credits: object, unit: str | None = None) -> dict:
    """A course printing these credits, in this unit when there is one."""
    fields = [field("f_001", "course_credits", credits)]
    if unit is not None:
        fields.append(field("f_002", "course_credits_unit", unit))
    fields.append(field(f"f_{len(fields) + 1:03d}", "course_name", "Comp I"))
    return {**RECORD, "source_expected": {"fields": fields}}


def test_a_credit_is_a_value_profile() -> None:
    """CTDL has no ceterms:value; a credit value is a ValueProfile."""
    assert to_jsonld(RECORD)["ceterms:creditValue"] == [
        {"@type": "ceterms:ValueProfile", "schema:value": 3}
    ]


def test_the_printed_unit_goes_inside_the_credit_value() -> None:
    node = to_jsonld(credit_record(4.0, "Units"))
    assert node["ceterms:creditValue"] == [
        {
            "@type": "ceterms:ValueProfile",
            "schema:value": 4.0,
            "ceterms:creditUnitType": ["Units"],
        }
    ]
    assert "ceterms:creditUnitType" not in node


@pytest.mark.parametrize(
    ("printed", "low", "high"),
    [("1.0-4.0", 1.0, 4.0), ("1 - 3", 1, 3), ("1–3", 1, 3), ("1 to 3", 1, 3)],
)
def test_a_printed_range_is_a_minimum_and_a_maximum(
    printed: str, low: float, high: float
) -> None:
    """schema:value is a number, so "1.0-4.0" cannot be one."""
    node = to_jsonld(credit_record(printed, "Units"))
    assert node["ceterms:creditValue"] == [
        {
            "@type": "ceterms:ValueProfile",
            "schema:minValue": low,
            "schema:maxValue": high,
            "ceterms:creditUnitType": ["Units"],
        }
    ]


def test_a_credit_that_is_no_number_is_kept_as_its_description() -> None:
    node = to_jsonld(credit_record("Variable"))
    assert node["ceterms:creditValue"] == [
        {"@type": "ceterms:ValueProfile", "schema:description": "Variable"}
    ]


def test_the_unit_is_mapped_with_the_credits_not_as_a_property() -> None:
    """It takes no property id, so the ones after it do not move."""
    fields = credit_record(3, "Credits")["source_expected"]["fields"]
    ctdl = map_fields("Course", fields)
    assert [prop["property_id"] for prop in ctdl["properties"]] == [
        "map_001",
        "map_002",
    ]
    assert ctdl["properties"][0]["source_field_refs"] == ["f_001", "f_002"]
    assert ctdl["unmapped_source_field_refs"] == []


def test_a_unit_with_no_credits_to_go_in_is_unmapped() -> None:
    fields = [
        field("f_001", "course_credits_unit", "Units"),
        field("f_002", "course_name", "Comp I"),
    ]
    ctdl = map_fields("Course", fields)
    assert [prop["property"] for prop in ctdl["properties"]] == ["ceterms:name"]
    assert ctdl["unmapped_source_field_refs"] == ["f_001"]
