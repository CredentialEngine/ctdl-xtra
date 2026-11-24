"""Deterministic source_expected → ctdl_expected. No invented CTIDs or vocab."""

from __future__ import annotations

import re
from typing import Any

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

# A printed credit range as the readers write it: "1.0-4.0", "1 - 3",
# "1–3", "1 to 3". One number on its own matches too.
CREDIT_RANGE_RE = re.compile(
    r"(\d+(?:\.\d+)?)(?:\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?))?", re.IGNORECASE
)


def _number(text: str) -> int | float:
    try:
        return int(text)
    except ValueError:
        return float(text)


def _credit_profile(credits: Any, unit: Any) -> tuple[dict, str]:
    """The ceterms:ValueProfile a printed credit value is, and why.

    One number is schema:value and a printed range is schema:minValue and
    schema:maxValue. CTDL types all three as xsd:float, so a value that is
    neither ("Variable") is the profile's schema:description. The unit
    word goes in as the page printed it.
    """
    profile: dict[str, Any] = {"@type": "ceterms:ValueProfile"}
    note = "Single printed credit; not expanded into min/max."
    if isinstance(credits, (int, float)):
        profile["schema:value"] = credits
    else:
        text = str(credits).strip()
        match = CREDIT_RANGE_RE.fullmatch(text)
        if match is None:
            profile["schema:description"] = text
            note = "Printed credit is not a number; kept as its description."
        elif match.group(2) is None:
            profile["schema:value"] = _number(match.group(1))
        else:
            profile["schema:minValue"] = _number(match.group(1))
            profile["schema:maxValue"] = _number(match.group(2))
            note = "Printed range; its two ends are minValue and maxValue."
    if unit:
        profile["ceterms:creditUnitType"] = [unit]
    return profile, note


def map_fields(entity_type: str, fields: list[dict]) -> dict:
    class_uri = CLASS_URI[entity_type]
    present = {
        field["canonical_label"]: field
        for field in fields
        if field.get("presence") == "present"
    }
    # The unit word is written inside the credit value printed with it, so
    # it is no property of its own; with no credit value to go in, it is
    # left unmapped like any other label.
    unit = (
        present.get("course_credits_unit")
        if "course_credits" in present
        else None
    )
    props = []
    unmapped = []
    n = 0
    for field in fields:
        label = field["canonical_label"]
        if field.get("presence") != "present":
            unmapped.append(field["field_id"])
            continue
        if field is unit:
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
            profile, note = _credit_profile(
                field["value"], unit["value"] if unit else None
            )
            refs = [field["field_id"]]
            if unit:
                refs.append(unit["field_id"])
            props.append(
                {
                    "property_id": pid,
                    "property": "ceterms:creditValue",
                    "value": [profile],
                    "source_field_refs": refs,
                    "publisher_input_refs": [],
                    "mapping_method": "nested_profile",
                    "notes": note,
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
        "mapping_version": "v4-pilot-0.2",
        "properties": [] if entity_type == "Link" else props,
        "unmapped_source_field_refs": unmapped
        if entity_type != "Link"
        else [f["field_id"] for f in fields],
    }
