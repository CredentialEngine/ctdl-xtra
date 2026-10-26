"""source_expected fields to ctdl_expected properties, as transform reads
them. Mapping goes by canonical label alone; it invents no CTIDs or
vocabulary."""

from __future__ import annotations

import config
import pytest
from mapping import CLASS_URI, DIRECT, map_fields


def field(
    label: str, value: object, field_id: str, presence: str = "present"
) -> dict:
    """A field shaped as src/implementations/extract.py builds one."""
    return {
        "field_id": field_id,
        "canonical_label": label,
        "presence": presence,
        "value": value,
        "raw_text": None,
        "evidence": [],
        "notes": None,
    }


def verbatim(property_: str, value: object, field_id: str, n: int) -> dict:
    return {
        "property_id": f"map_{n:03d}",
        "property": property_,
        "value": value,
        "source_field_refs": [field_id],
        "publisher_input_refs": [],
        "mapping_method": "verbatim",
        "notes": None,
    }


@pytest.mark.parametrize(("label", "property_"), sorted(DIRECT.items()))
def test_a_direct_label_maps_verbatim(label: str, property_: str) -> None:
    mapped = map_fields("Course", [field(label, "Printed value", "src_001")])
    assert mapped["properties"] == [
        verbatim(property_, "Printed value", "src_001", 1)
    ]
    assert mapped["unmapped_source_field_refs"] == []


def test_a_single_credit_becomes_one_credit_value_profile() -> None:
    mapped = map_fields("Course", [field("course_credits", 3, "src_004")])
    assert mapped["properties"] == [
        {
            "property_id": "map_001",
            "property": "ceterms:creditValue",
            "value": [{"ceterms:value": 3}],
            "source_field_refs": ["src_004"],
            "publisher_input_refs": [],
            "mapping_method": "nested_profile",
            "notes": "Single printed credit; not expanded into min/max.",
        }
    ]


def test_prerequisites_become_a_requires_profile() -> None:
    mapped = map_fields(
        "Course", [field("course_prerequisites", "ENGL099", "src_008")]
    )
    assert mapped["properties"][0]["property"] == "ceterms:requires"
    assert mapped["properties"][0]["value"] == [{"ceterms:name": "ENGL099"}]
    assert mapped["properties"][0]["mapping_method"] == "nested_profile"


def test_a_printed_range_and_unmapped_labels_stay_unmapped() -> None:
    fields = [
        field("course_credits_min", 1, "src_001"),
        field("course_credits_max", 4, "src_002"),
        field("course_school", "Humanities", "src_003"),
    ]
    mapped = map_fields("Course", fields)
    assert mapped["properties"] == []
    assert mapped["unmapped_source_field_refs"] == [
        "src_001",
        "src_002",
        "src_003",
    ]


def test_property_ids_count_present_fields_so_unmapped_ones_leave_gaps() -> (
    None
):
    fields = [
        field("course_id", "ENGL101", "src_001", presence="not_present"),
        field("course_name", "Composition I", "src_002"),
        field("course_credits_min", 1, "src_003"),
        field("course_description", "Writing.", "src_004"),
    ]
    mapped = map_fields("Course", fields)
    assert [p["property_id"] for p in mapped["properties"]] == [
        "map_001",
        "map_003",
    ]
    assert mapped["unmapped_source_field_refs"] == ["src_001", "src_003"]


@pytest.mark.parametrize(
    ("entity_type", "class_uri"), sorted(CLASS_URI.items())
)
def test_each_entity_type_maps_to_its_ctdl_class(
    entity_type: str, class_uri: str | None
) -> None:
    assert map_fields(entity_type, [])["class_uri"] == class_uri


def test_a_link_maps_no_properties_and_leaves_every_field_unmapped() -> None:
    fields = [
        field("relationship_heading", "AAS in Nursing", "src_001"),
        field("credential_name", "AAS", "src_002"),
    ]
    mapped = map_fields("Link", fields)
    assert mapped["properties"] == []
    assert mapped["unmapped_source_field_refs"] == ["src_001", "src_002"]


def test_mapping_goes_by_label_not_by_what_the_entity_type_allows() -> None:
    """Inventory allows competency_framework_name only on a framework, yet a
    Competency carrying it, as extract_dom builds one, still maps it."""
    mapped = map_fields(
        "Competency",
        [field("competency_framework_name", "Nursing outcomes", "src_001")],
    )
    assert mapped["properties"] == [
        verbatim("ceasn:name", "Nursing outcomes", "src_001", 1)
    ]


def test_an_unknown_entity_type_is_refused() -> None:
    with pytest.raises(KeyError):
        map_fields("Program", [])


def test_the_release_and_version_stamps_match_config() -> None:
    mapped = map_fields("Course", [])
    assert mapped["schema_release"] == config.SCHEMA_RELEASE
    assert mapped["mapping_version"] == config.MAPPING_VERSION
