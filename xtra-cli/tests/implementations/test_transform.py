from __future__ import annotations

from implementations.transform import to_expected, to_jsonld

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
