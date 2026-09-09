"""Allowed source labels for v4. Mapping is separate from capture."""

from __future__ import annotations

# canonical_label -> (allowed entity types, value_kind, typical CTDL term or None)
INVENTORY: dict[str, tuple[tuple[str, ...], str, str | None]] = {
    "course_id": (("Course",), "string", "ceterms:codedNotation"),
    "course_name": (("Course",), "string", "ceterms:name"),
    "course_description": (("Course",), "string", "ceterms:description"),
    "course_credits": (("Course",), "number", "ceterms:creditValue"),
    "course_credits_min": (("Course",), "number", "ceterms:creditValue"),
    "course_credits_max": (("Course",), "number", "ceterms:creditValue"),
    "course_prerequisites": (("Course",), "string", "ceterms:requires"),
    "course_corequisites": (("Course",), "string", None),
    "course_lecture_hours": (("Course",), "number", None),
    "course_lab_hours": (("Course",), "number", None),
    "course_program": (("Course",), "string", None),
    "course_department": (("Course",), "string", None),
    "course_school": (("Course",), "string", None),
    "course_division": (("Course",), "string", None),
    "course_subject_code": (("Course",), "string", None),
    "course_number": (("Course",), "string", None),
    "course_long_title": (("Course",), "string", None),
    "course_academic_level": (("Course",), "string", None),
    "course_general_education": (("Course",), "string", None),
    "learning_program_id": (("LearningProgram",), "string", "ceterms:codedNotation"),
    "learning_program_name": (("LearningProgram",), "string", "ceterms:name"),
    "learning_program_description": (("LearningProgram",), "string", "ceterms:description"),
    "credential_name": (("Credential",), "string", "ceterms:name"),
    "credential_description": (("Credential",), "string", "ceterms:description"),
    "competency_framework_name": (("CompetencyFramework",), "string", "ceasn:name"),
    "competency_text": (("Competency",), "string", "ceasn:competencyText"),
    "relationship_heading": (("Link",), "string", None),
}

CSV_HEADER = (
    "canonical_label,target_classes,value_kind,ctdl_property,notes\n"
)


def csv_text() -> str:
    lines = [CSV_HEADER]
    for label, (classes, kind, prop) in INVENTORY.items():
        notes = "Omit when not printed. Never invent min/max from a single credit."
        if label == "course_credits":
            notes = "Single printed credit is one value. Do not emit min/max unless the freeze prints a range or both bounds."
        elif label == "course_credits_min":
            notes = "Only when the freeze prints an explicit minimum bound (Min, range start)."
        elif label == "course_credits_max":
            notes = "Only when the freeze prints an explicit maximum bound (Max, range end)."
        elif label == "relationship_heading":
            notes = "Printed heading that names the program and the award; used only as link evidence."
        lines.append(
            f"{label},{'|'.join(classes)},{kind},{prop or ''},{notes}\n"
        )
    return "".join(lines)


def allowed_for(entity_type: str) -> set[str]:
    return {label for label, (classes, _, _) in INVENTORY.items() if entity_type in classes}
