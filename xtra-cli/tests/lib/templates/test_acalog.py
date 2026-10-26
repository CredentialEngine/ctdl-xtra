"""Acalog: the HCC, units, Bergen and Raritan layouts. Three of them split
a code and a title on a non-breaking-space dash."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from template_texts import (
    ACALOG_BERGEN,
    ACALOG_HCC,
    ACALOG_RARITAN,
    ACALOG_UNITS,
    lines,
)
from templates.acalog import (
    FAMILY,
    TEMPLATES,
    detect,
    extract_bergen,
    extract_hcc,
    extract_raritan,
    extract_units,
)
from transcribe_lib import TranscriptionError

HCC = "acalog_hcc_nbsp_credits"
UNITS = "acalog_units_glued_hours"
BERGEN = "acalog_bergen_glued_credits"
RARITAN = "acalog_raritan_hours_credits"

D4 = (
    "D4: a glued heading whose course name ends in a digit is split one "
    "digit too early, giving 14 credits and a name without its number"
)


def rows(drafts: list) -> list[tuple]:
    return [(d.canonical_label, d.value, d.excerpt) for d in drafts]


def by_label(drafts: list) -> dict:
    return {d.canonical_label: d for d in drafts}


def test_the_family_has_four_templates() -> None:
    assert FAMILY == "acalog"
    assert {
        HCC: extract_hcc,
        UNITS: extract_units,
        BERGEN: extract_bergen,
        RARITAN: extract_raritan,
    } == TEMPLATES


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (ACALOG_HCC, HCC),
        (lines("ENG 1010\xa0-\xa0College Composition I", "Credits: 3"), HCC),
        (ACALOG_UNITS, UNITS),
        (lines("MATH 5\xa0-\xa0Study Skills1 unit", "1 hour lab"), UNITS),
        (lines("MATH 5\xa0-\xa0Study Skills1 unit"), None),
        (ACALOG_BERGEN, BERGEN),
        (ACALOG_RARITAN, RARITAN),
        (lines("ENGL 111 - English I", "(3,0) 3 Credits"), None),
        (lines("English I", "3 Credits"), None),
    ],
)
def test_detect_recognises_each_heading_shape(
    text: str, expected: str | None
) -> None:
    assert detect(text) == expected


def test_hcc_splits_code_name_and_credits_from_one_glued_heading() -> None:
    heading = "ENG 1010\xa0-\xa0College Composition I Credits: 3"
    description = (
        "Introduces academic writing, argument and research at college level."
    )
    assert rows(extract_hcc(ACALOG_HCC)) == [
        ("course_id", "ENG 1010", heading),
        ("course_name", "College Composition I", heading),
        ("course_credits", 3, heading),
        ("course_description", description, description),
        ("course_lecture_hours", 3, "Lecture: 3"),
        ("course_lab_hours", 0, "Lab: 0"),
        ("course_ceu_credits", 3.0, "3.0 CEUs"),
        (
            "course_prerequisites",
            "ENG 0930 or placement",
            "Prerequisite(s): ENG 0930 or placement",
        ),
    ]


def test_hcc_reads_credits_printed_on_their_own_line() -> None:
    text = lines(
        "ENG 1010\xa0-\xa0College Composition I",
        "Credits: 3",
        "Introduces academic writing, argument and research at college level.",
    )
    drafts = by_label(extract_hcc(text))
    assert drafts["course_name"].value == "College Composition I"
    assert drafts["course_credits"].excerpt == "Credits: 3"
    assert "course_lab_hours" not in drafts


def test_hcc_description_skips_short_lines_and_page_chrome() -> None:
    text = lines(
        "ENG 1010\xa0-\xa0College Composition I Credits: 3",
        "Fall only",
        "Share this page with classmates on any social network you use",
        "Print this page for your own records and keep it somewhere safe",
        "Introduces academic writing, argument and research at college level.",
    )
    drafts = by_label(extract_hcc(text))
    assert drafts["course_description"].value.startswith("Introduces")


def test_hcc_without_its_heading_fails_closed() -> None:
    with pytest.raises(TranscriptionError, match="NBSP-dash heading"):
        extract_hcc(lines("Credits: 3"))


def test_units_reads_the_glued_units_and_the_hours_line() -> None:
    heading = "ENGL 1\xa0-\xa0Reading and Composition4 units"
    description = (
        "Develops critical reading and expository writing across disciplines."
    )
    drafts = extract_units(ACALOG_UNITS)
    assert rows(drafts) == [
        ("course_id", "ENGL 1", heading),
        ("course_name", "Reading and Composition", heading),
        ("course_credits", 4, heading),
        ("course_lecture_hours", 4, "4 hours lecture, 1 hour lab"),
        ("course_lab_hours", 1, "4 hours lecture, 1 hour lab"),
        ("course_description", description, description),
    ]
    assert by_label(drafts)["course_credits"].raw_text == "4 units"


def test_units_reads_one_unit_and_a_lab_only_line() -> None:
    text = lines(
        "MATH 5\xa0-\xa0Study Skills1 unit",
        "1 hour lab",
        "Builds note-taking, test preparation and time management skills.",
    )
    drafts = by_label(extract_units(text))
    assert drafts["course_name"].value == "Study Skills"
    assert drafts["course_credits"].raw_text == "1 unit"
    assert drafts["course_lab_hours"].value == 1
    assert "course_lecture_hours" not in drafts


def test_units_quotes_the_unit_word_as_the_heading_prints_it() -> None:
    text = lines(
        "ENGL 1\xa0-\xa0Reading and Composition4 unit",
        "4 hours lecture",
        "Short note.",
        "Develops critical reading and expository writing across disciplines.",
    )
    drafts = by_label(extract_units(text))
    assert drafts["course_credits"].raw_text == "4 unit"
    assert drafts["course_description"].value.startswith("Develops")


def test_units_with_lecture_hours_only_has_no_lab_field() -> None:
    text = ACALOG_UNITS.replace(
        "4 hours lecture, 1 hour lab\n", "4 hours lecture\n"
    )
    drafts = by_label(extract_units(text))
    assert drafts["course_lecture_hours"].value == 4
    assert "course_lab_hours" not in drafts


def test_units_without_its_heading_fails_closed() -> None:
    with pytest.raises(TranscriptionError, match="unit\\(s\\) heading"):
        extract_units(lines("4 hours lecture"))


def test_bergen_splits_the_glued_credits_off_the_title() -> None:
    heading = "WRT-101 English Composition I3 Credit(s)"
    description = "This course develops writing through the study of rhetoric."
    assert rows(extract_bergen(ACALOG_BERGEN)) == [
        ("course_id", "WRT-101", heading),
        ("course_name", "English Composition I", heading),
        ("course_credits", 3, "3 Credit(s)"),
        ("course_lab_hours", 0, "0 Lab Hour(s)"),
        ("course_lecture_hours", 3, "3 Lecture Hour(s)"),
        ("course_description", description, description),
        (
            "course_general_education",
            "General Education Course: Communication",
            "General Education Course: Communication",
        ),
        (
            "course_prerequisites",
            "WRT-095 or placement",
            "Prerequisite(s): WRT-095 or placement",
        ),
    ]


def test_bergen_reads_corequisites_printed_before_the_prerequisites() -> None:
    text = ACALOG_BERGEN.replace(
        "Prerequisite(s):", "Corequisite(s): WRT-100\nPrerequisite(s):"
    )
    drafts = by_label(extract_bergen(text))
    assert drafts["course_corequisites"].value == "WRT-100"
    assert drafts["course_prerequisites"].value == "WRT-095 or placement"


def test_bergen_keeps_a_prerequisite_label_glued_to_its_corequisite() -> None:
    text = ACALOG_BERGEN.replace(
        "Prerequisite(s): WRT-095 or placement",
        "Prerequisite(s): and Corequisite(s): WRT-100",
    )
    drafts = by_label(extract_bergen(text))
    assert drafts["course_prerequisites"].value == (
        "Prerequisite(s): and Corequisite(s): WRT-100"
    )


def test_bergen_without_its_heading_fails_closed() -> None:
    with pytest.raises(TranscriptionError, match="Credit\\(s\\) heading"):
        extract_bergen(lines("3 Lecture Hour(s)"))


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=D4)
@pytest.mark.parametrize(
    ("text", "extract"),
    [
        pytest.param(
            lines(
                "MAT-150 Calculus 14 Credit(s)",
                "This course covers limits, derivatives and integrals.",
            ),
            extract_bergen,
            id="bergen",
        ),
        pytest.param(
            lines(
                "MATH 3\xa0-\xa0Calculus 14 units",
                "4 hours lecture",
                "Covers limits, derivatives and integrals of one variable.",
            ),
            extract_units,
            id="units",
        ),
    ],
)
def test_a_course_name_that_ends_in_a_digit_keeps_it(
    text: str, extract: Callable[[str], list]
) -> None:
    drafts = by_label(extract(text))
    assert (drafts["course_name"].value, drafts["course_credits"].value) == (
        "Calculus 1",
        4,
    )


def test_raritan_reads_the_hours_line_under_its_heading() -> None:
    title = "ENGL 111\xa0-\xa0English I"
    description = (
        "This course develops expository writing through structured practice."
    )
    assert rows(extract_raritan(ACALOG_RARITAN)) == [
        ("course_id", "ENGL 111", title),
        ("course_name", "English I", title),
        ("course_credits", 3, "(3,0) 3 Credits"),
        ("course_lecture_hours", 3, "(3,0) 3 Credits"),
        ("course_lab_hours", 0, "(3,0) 3 Credits"),
        (
            "course_general_education",
            "Written Communication",
            "General Education Course: Written Communication",
        ),
        ("course_prerequisites", "ENGL 070", "Prerequisite(s): ENGL 070"),
        ("course_description", description, description),
    ]


def test_raritan_reads_hours_printed_inside_the_heading() -> None:
    text = ACALOG_RARITAN.replace(
        "ENGL 111\xa0-\xa0English I\n(3,0) 3 Credits\n",
        "ENGL 111\xa0-\xa0English I (3,0) 3 Credits\n",
    )
    drafts = by_label(extract_raritan(text))
    assert drafts["course_name"].value == "English I"
    assert drafts["course_credits"].excerpt == "(3,0) 3 Credits"


def test_raritan_keeps_a_prerequisite_label_glued_to_its_corequisite() -> None:
    text = ACALOG_RARITAN.replace(
        "Prerequisite(s): ENGL 070",
        "Prerequisite(s): and Corequisite(s): ENGL 080",
    )
    drafts = by_label(extract_raritan(text))
    assert drafts["course_prerequisites"].value == (
        "Prerequisite(s): and Corequisite(s): ENGL 080"
    )


def test_raritan_reads_a_description_only_with_a_known_opening() -> None:
    """Fragile by design: other wording drops the description and prereqs."""
    text = ACALOG_RARITAN.replace("This course develops", "Students develop")
    drafts = by_label(extract_raritan(text))
    assert "course_description" not in drafts
    assert "course_prerequisites" not in drafts
    assert drafts["course_general_education"].value == "Written Communication"
