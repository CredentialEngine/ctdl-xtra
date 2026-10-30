"""Clean Catalog (custom_html): read from the two real fixture pages, and
from a fuller page that prints a program, lab hours and requisites."""

from __future__ import annotations

from pathlib import Path

import pytest
from normalize import normalize_html
from template_texts import CLEAN_CATALOG, lines
from templates.clean_catalog import (
    FAMILY,
    TEMPLATES,
    detect,
    extract_clean_catalog,
)

TID = "clean_catalog_course_detail"


def rows(drafts: list) -> list[tuple]:
    return [(d.canonical_label, d.value, d.excerpt) for d in drafts]


def test_the_family_has_one_template() -> None:
    assert FAMILY == "custom_html"
    assert {TID: extract_clean_catalog} == TEMPLATES


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (lines("Course Catalog Software by Clean Catalog", "Credits"), TID),
        (lines("ENGL101:", "Credits"), TID),
        (lines("Course Catalog Software by Clean Catalog", "Credits: 3"), None),
        (lines("ENGL101:", "Credit Hours"), None),
        (lines("ENGL101: Composition I", "Credits"), None),
        (lines("Credits", "3"), None),
    ],
)
def test_detect_needs_a_footer_or_code_heading_and_a_bare_credits_line(
    text: str, expected: str | None
) -> None:
    assert detect(text) == expected


@pytest.mark.parametrize(
    "name", ["example-engl101.html", "course-clean-catalog.html"]
)
def test_the_real_fixture_pages_read_as_one_course(
    fixture_html_dir: Path, name: str
) -> None:
    text = normalize_html((fixture_html_dir / name).read_text(encoding="utf-8"))
    assert detect(text) == TID
    assert rows(extract_clean_catalog(text)) == [
        ("course_id", "ENGL101", "ENGL101:"),
        ("course_name", "Composition I", "Composition I"),
        ("course_credits", 3, "Credits\n3"),
        ("course_lecture_hours", 3, "Lecture Hours\n3"),
        (
            "course_description",
            "An introduction to college writing.",
            "An introduction to college writing.",
        ),
    ]


def test_a_full_page_reads_program_hours_and_requisites() -> None:
    """The description is the line before Prerequisites on this layout."""
    description = (
        "Develops college-level writing through drafting and revision."
    )
    assert rows(extract_clean_catalog(CLEAN_CATALOG)) == [
        ("course_id", "ENGL101", "ENGL101:"),
        ("course_name", "English Composition I", "English Composition I"),
        ("course_program", "English", "Program\nEnglish"),
        ("course_credits", 3, "Credits\n3"),
        ("course_lab_hours", 0, "Lab/Clinical/Field Study Hours\n0"),
        ("course_lecture_hours", 3, "Lecture Hours\n3"),
        ("course_description", description, description),
        (
            "course_prerequisites",
            "ENGL099 or placement",
            "ENGL099 or placement",
        ),
        ("course_corequisites", "ENGL101L", "ENGL101L"),
    ]


def test_the_name_skips_the_download_as_pdf_link() -> None:
    drafts = extract_clean_catalog(CLEAN_CATALOG)
    assert drafts[1].value == "English Composition I"
    assert "Download as PDF" not in [d.value for d in drafts]


def test_credits_are_one_printed_value_never_a_range() -> None:
    drafts = {
        d.canonical_label: d for d in extract_clean_catalog(CLEAN_CATALOG)
    }
    assert drafts["course_credits"].raw_text == "Credits\n3"
    assert "Not expanded to min/max" in drafts["course_credits"].notes
    assert "course_credits_min" not in drafts
    assert "course_credits_max" not in drafts


@pytest.mark.parametrize("chrome", ["User account menu", "Staff Login"])
def test_site_chrome_after_the_corequisites_label_is_not_a_corequisite(
    chrome: str,
) -> None:
    text = CLEAN_CATALOG.replace(
        "Corequisites\nENGL101L\n", f"Corequisites\n{chrome}\n"
    )
    labels = [d.canonical_label for d in extract_clean_catalog(text)]
    assert "course_corequisites" not in labels
