"""Deterministic source_expected → ctdl_expected. No invented CTIDs or vocab."""

from __future__ import annotations

CLASS_URI = {
    "Course": "ceterms:Course",
    "LearningProgram": "ceterms:LearningProgram",
    "Credential": "ceterms:Credential",
    "CompetencyFramework": "ceasn:CompetencyFramework",
    "Competency": "ceasn:Competency",
    "Link": None,
}

DIRECT = {
    "course_id": "ceterms:codedNotation",
    "course_name": "ceterms:name",
    "course_description": "ceterms:description",
    "learning_program_id": "ceterms:codedNotation",
    "learning_program_name": "ceterms:name",
    "learning_program_description": "ceterms:description",
    "credential_name": "ceterms:name",
    "credential_description": "ceterms:description",
    "competency_framework_name": "ceasn:name",
    "competency_text": "ceasn:competencyText",
}


def map_fields(entity_type: str, fields: list[dict]) -> dict:
    class_uri = CLASS_URI[entity_type]
    props = []
    unmapped = []
    n = 0
    for field in fields:
        label = field["canonical_label"]
        if field.get("presence") != "present":
            unmapped.append(field["field_id"])
            continue
        n += 1
        pid = f"map_{n:03d}"
        if label in DIRECT:
            props.append(
                {
                    "property_id": pid,
                    "property": DIRECT[label],
                    "value": field["value"],
                    "source_field_refs": [field["field_id"]],
                    "publisher_input_refs": [],
                    "mapping_method": "verbatim",
                    "notes": None,
                }
            )
        elif label == "course_credits":
            props.append(
                {
                    "property_id": pid,
                    "property": "ceterms:creditValue",
                    "value": [{"ceterms:value": field["value"]}],
                    "source_field_refs": [field["field_id"]],
                    "publisher_input_refs": [],
                    "mapping_method": "nested_profile",
                    "notes": "Single printed credit; not expanded into min/max.",
                }
            )
        elif label in {"course_credits_min", "course_credits_max"}:
            unmapped.append(field["field_id"])
        elif label == "course_prerequisites":
            props.append(
                {
                    "property_id": pid,
                    "property": "ceterms:requires",
                    "value": [{"ceterms:name": field["value"]}],
                    "source_field_refs": [field["field_id"]],
                    "publisher_input_refs": [],
                    "mapping_method": "nested_profile",
                    "notes": None,
                }
            )
        else:
            unmapped.append(field["field_id"])

    return {
        "class_uri": class_uri,
        "schema_release": "ctdl-json-2026-09-07-audit-pin",
        "mapping_version": "v4-pilot-0.1",
        "properties": [] if entity_type == "Link" else props,
        "unmapped_source_field_refs": unmapped if entity_type != "Link" else [f["field_id"] for f in fields],
    }
