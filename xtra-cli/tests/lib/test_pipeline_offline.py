"""The pack pipeline end to end, offline. Freeze copies two saved pages
instead of fetching them, so no browser and no network are involved, and
the pack that comes out has to pass the pack's own check."""

from __future__ import annotations

import json
from pathlib import Path

import cli
import dynamic_slots
from lib_doubles import example_slot

import lib

STEPS = ("freeze", "normalize", "classify", "build", "validate", "assemble")


def test_two_saved_pages_become_a_pack_that_passes_its_own_check(
    pack: Path, fixture_html_dir: Path
) -> None:
    clean_catalog = example_slot(
        copy_html=fixture_html_dir / "example-engl101.html"
    )
    brookdale = example_slot(
        record_id="example-engl121-course",
        requested_url="https://catalog.example.edu/courses/ENGL121",
        page_id="example-engl121",
        source_family="coursedog",
        template_id="coursedog",
        copy_html=fixture_html_dir / "course-coursedog-brookdale.html",
    )
    dynamic_slots.write_slots([clean_catalog, brookdale])

    for step in STEPS:
        assert cli.main([step]) == 0, step

    assert lib.check_pack(pack) == []
    assert [slot.template_id for slot in dynamic_slots.load_slots()] == [
        "clean_catalog_course_detail",
        "coursedog_brookdale_course_detail",
    ]
    exported = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in (pack / "courses").glob("*.json")
    }
    assert exported["example-engl101-course"]["expected"] == {
        "course_id": "ENGL101",
        "course_name": "Composition I",
        "course_description": "An introduction to college writing.",
        "course_credits": 3,
        "course_lecture_hours": 3,
    }
    assert exported["example-engl121-course"]["expected"] == {
        "course_id": "ENGL121",
        "course_name": "English Composition: Writing as Process",
        "course_description": (
            "Develops writing as a process of drafting and revision. "
            "(Prerequisite(s): ENGL095 or placement)"
        ),
        "course_credits": 3,
        "course_prerequisites": "ENGL095 or placement",
        "course_school": "Humanities",
        "course_division": "Liberal Arts",
        "course_department": "English",
        "course_general_education": "Written and Oral Communication",
    }
    manifest = json.loads((pack / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["record_count"] == 2
