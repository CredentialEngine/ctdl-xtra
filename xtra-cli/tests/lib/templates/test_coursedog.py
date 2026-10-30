"""Coursedog: the RCBC/Hudson, Mercer and Brookdale layouts and the credit
blocks they share."""

from __future__ import annotations

import pytest
from template_texts import (
    COURSEDOG_BROOKDALE,
    COURSEDOG_MCCC,
    COURSEDOG_RCBC,
    lines,
)
from templates.coursedog import (
    FAMILY,
    TEMPLATES,
    _after_courses_slash,
    _coursedog_credits,
    _mccc_this_course_requirement,
    detect,
    extract_brookdale,
    extract_mccc,
    extract_rcbc,
)
from transcribe_lib import TranscriptionError

RCBC = "coursedog_rcbc_course_detail"
MCCC = "coursedog_mccc_course_detail"
BROOKDALE = "coursedog_brookdale_course_detail"


def rows(drafts: list) -> list[tuple]:
    return [(d.canonical_label, d.value, d.excerpt) for d in drafts]


def by_label(drafts: list) -> dict:
    return {d.canonical_label: d for d in drafts}


def test_the_family_has_three_templates() -> None:
    assert FAMILY == "coursedog"
    assert {
        RCBC: extract_rcbc,
        MCCC: extract_mccc,
        BROOKDALE: extract_brookdale,
    } == TEMPLATES


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (lines("Course Long Title", "x"), RCBC),
        (lines("(Credit Hours) Min", "3"), RCBC),
        (
            lines(
                "Subject Code",
                "ENG",
                "Course Number",
                "101",
                "Course Description",
            ),
            MCCC,
        ),
        (
            lines(
                "Subject Code: ENG",
                "Course Number",
                "Course Description",
                "Credit Hours",
            ),
            BROOKDALE,
        ),
        (lines("Course Description", "x", "Credit Hours Min", "3"), BROOKDALE),
        (lines("Course Description", "x"), None),
        (lines("Credit Hours", "Min", "3"), None),
    ],
)
def test_detect_checks_rcbc_and_mercer_labels_before_brookdale(
    text: str, expected: str | None
) -> None:
    assert detect(text) == expected


@pytest.mark.parametrize(
    ("block", "expected"),
    [
        pytest.param(
            ["Credit Hours", "Min", "3"],
            [
                (
                    "course_credits",
                    3,
                    "Credit Hours\nMin\n3",
                    "Credit Hours Min (no Max printed)",
                )
            ],
            id="label-then-min",
        ),
        pytest.param(
            ["Credit Hours", "Min", "3", "Max", "4"],
            [
                (
                    "course_credits_min",
                    3,
                    "Credit Hours\nMin\n3",
                    "Credit Hours Min",
                ),
                ("course_credits_max", 4, "Max\n4", "Credit Hours Max"),
            ],
            id="label-then-min-and-max",
        ),
        pytest.param(
            ["(Credit Hours) Min", "3"],
            [
                (
                    "course_credits",
                    3,
                    "(Credit Hours) Min\n3",
                    "Credit Hours Min only",
                )
            ],
            id="parenthesised-min",
        ),
        pytest.param(
            ["(Credit Hours) Min", "1", "(Credit Hours) Max", "4"],
            [
                ("course_credits_min", 1, "(Credit Hours) Min\n1", "Min bound"),
                ("course_credits_max", 4, "(Credit Hours) Max\n4", "Max bound"),
            ],
            id="parenthesised-min-and-max",
        ),
        pytest.param(
            ["(Credit Hours) Min", "1", "Max", "4"],
            [
                ("course_credits_min", 1, "(Credit Hours) Min\n1", "Min bound"),
                ("course_credits_max", 4, "Max\n4", "Max bound"),
            ],
            id="parenthesised-min-and-bare-max",
        ),
        pytest.param(
            ["Credit Hours Min", "1.5"],
            [
                (
                    "course_credits",
                    1.5,
                    "Credit Hours Min\n1.5",
                    "Credit Hours Min only",
                )
            ],
            id="inline-min",
        ),
        pytest.param(
            ["Credit Hours Min", "1", "Credit Hours Max", "4"],
            [
                ("course_credits_min", 1, "Credit Hours Min\n1", "Min bound"),
                ("course_credits_max", 4, "Credit Hours Max\n4", "Max bound"),
            ],
            id="inline-min-and-max",
        ),
    ],
)
def test_a_credit_block_is_one_value_unless_a_max_is_printed(
    block: list[str], expected: list[tuple]
) -> None:
    assert _coursedog_credits(lines(*block)) == expected


@pytest.mark.parametrize(
    "block", [["Credit Hours", "3"], ["Credits", "3"], ["Course Description"]]
)
def test_no_recognised_credit_block_fails_closed(block: list[str]) -> None:
    with pytest.raises(TranscriptionError, match="no Coursedog credit hours"):
        _coursedog_credits(lines(*block))


def test_the_title_and_code_follow_the_courses_breadcrumb() -> None:
    assert _after_courses_slash(COURSEDOG_BROOKDALE) == (
        "English Composition: Writing as Process",
        "ENGL121",
    )
    with pytest.raises(TranscriptionError, match="no Courses/ breadcrumb"):
        _after_courses_slash(lines("Courses", "Title", "CODE101"))
    with pytest.raises(TranscriptionError, match="expected course code"):
        _after_courses_slash(lines("Courses/", "Title", "Download as PDF"))


def test_brookdale_reads_every_labelled_field() -> None:
    description = COURSEDOG_BROOKDALE.splitlines()[4]
    assert rows(extract_brookdale(COURSEDOG_BROOKDALE)) == [
        ("course_id", "ENGL121", "ENGL121"),
        (
            "course_name",
            "English Composition: Writing as Process",
            "English Composition: Writing as Process",
        ),
        ("course_description", description, description),
        ("course_credits", 3, "Credit Hours\nMin\n3"),
        (
            "course_general_education",
            "Written and Oral Communication",
            "General Education Competencies\nWritten and Oral Communication",
        ),
        ("course_school", "Humanities", "School\nHumanities"),
        ("course_division", "Liberal Arts", "Division\nLiberal Arts"),
        ("course_department", "English", "Department(s) ~*\nEnglish"),
        (
            "course_prerequisites",
            "ENGL095 or placement",
            "(Prerequisite(s): ENGL095 or placement)",
        ),
    ]


def test_brookdale_reads_a_printed_range_as_min_and_max() -> None:
    text = COURSEDOG_BROOKDALE.replace(
        "Credit Hours\nMin\n3\n", "Credit Hours\nMin\n3\nMax\n4\n"
    )
    drafts = by_label(extract_brookdale(text))
    assert "course_credits" not in drafts
    assert drafts["course_credits_min"].value == 3
    assert drafts["course_credits_max"].value == 4
    assert drafts["course_credits_max"].notes == "Printed bound."


def test_a_general_education_label_with_no_value_of_its_own_is_skipped() -> (
    None
):
    text = COURSEDOG_BROOKDALE.replace(
        "General Education Competencies\nWritten and Oral Communication\n",
        "General Education Competencies\n",
    )
    drafts = by_label(extract_brookdale(text))
    assert "course_general_education" not in drafts
    assert drafts["course_school"].value == "Humanities"


def test_brookdale_reads_a_plain_department_label() -> None:
    text = COURSEDOG_BROOKDALE.replace("Department(s) ~*\n", "Department\n")
    drafts = by_label(extract_brookdale(text))
    assert drafts["course_department"].excerpt == "Department\nEnglish"


@pytest.mark.parametrize(
    ("printed", "value"),
    [
        ("(Prerequisite or Corequisite: ENGL095)", "ENGL095"),
        ("(Prerequisite: ENGL095)", "ENGL095"),
        ("Students may enroll in any term.", None),
    ],
)
def test_brookdale_takes_a_requisite_only_from_a_closing_parenthetical(
    printed: str, value: str | None
) -> None:
    text = lines(
        "Courses/",
        "Composition",
        "ENGL121",
        "Course Description",
        f"Develops writing. {printed}",
        "Credit Hours",
        "Min",
        "3",
    )
    drafts = by_label(extract_brookdale(text))
    prereq = drafts.get("course_prerequisites")
    assert (prereq.value if prereq else None) == value


def test_mercer_reads_its_code_from_the_title_code_title_heading() -> None:
    assert rows(extract_mccc(COURSEDOG_MCCC)) == [
        ("course_id", "ENG101", "Composition I\nENG101\nComposition I"),
        ("course_name", "Composition I", "Composition I"),
        ("course_subject_code", "ENG", "Subject Code\nENG"),
        ("course_number", "101", "Course Number\n101"),
        (
            "course_description",
            "Introduces expository writing and research.",
            "Introduces expository writing and research.",
        ),
        ("course_credits", 3, "Credit Hours\nMin\n3"),
        (
            "course_prerequisites",
            "Earn a minimum grade of C in the following\n"
            "ENG021 - Basic Writing",
            "Earn a minimum grade of C in the following\n"
            "ENG021 - Basic Writing",
        ),
        (
            "course_corequisites",
            "Enroll in the following\nENG111 - Composition Lab",
            "Enroll in the following\nENG111 - Composition Lab",
        ),
    ]


def test_without_the_repeated_title_the_code_line_is_the_evidence() -> None:
    rows_ = COURSEDOG_MCCC.splitlines()
    del rows_[3]
    drafts = by_label(extract_mccc(lines(*rows_)))
    assert drafts["course_id"].excerpt == "ENG101"


def test_courses_this_one_is_a_prerequisite_for_are_not_its_requisites() -> (
    None
):
    text = lines(
        "Course Description",
        "Introduces writing.",
        "ENG101 is a prerequisite for",
        "Prerequisite",
        "Earn a minimum grade of C in the following",
        "ENG102 - Composition II",
    )
    assert _mccc_this_course_requirement(text, "ENG101", "Prerequisite") == (
        None,
        None,
    )


def test_a_requirement_needs_a_header_and_at_least_one_course() -> None:
    no_courses = lines(
        "Course Description",
        "x",
        "Prerequisite",
        "Earn a minimum grade of C in the following",
        "Collapse All",
    )
    no_header = lines(
        "Course Description", "x", "Prerequisite", "ENG021 - Basic Writing"
    )
    for text in (no_courses, no_header, lines("Prerequisite")):
        assert _mccc_this_course_requirement(
            text, "ENG101", "Prerequisite"
        ) == (
            None,
            None,
        )


def test_a_requirement_ends_at_the_first_line_that_is_not_a_course() -> None:
    text = lines(
        "Course Description",
        "x",
        "Prerequisite",
        "Enroll in the following",
        "ENG021 - Basic Writing",
        "Placement by exam is also accepted.",
        "ENG022 - Not part of the requirement",
    )
    block = "Enroll in the following\nENG021 - Basic Writing"
    assert _mccc_this_course_requirement(text, "ENG101", "Prerequisite") == (
        block,
        block,
    )


def test_a_requirement_whose_lines_are_not_contiguous_is_dropped() -> None:
    """A Courses label between header and course breaks the excerpt."""
    text = lines(
        "Course Description",
        "x",
        "Prerequisite",
        "Earn a minimum grade of C in the following",
        "Courses",
        "ENG021 - Basic Writing",
    )
    assert _mccc_this_course_requirement(text, "ENG101", "Prerequisite") == (
        None,
        None,
    )


def test_rcbc_reads_its_long_title_level_and_description_corequisite() -> None:
    assert rows(extract_rcbc(COURSEDOG_RCBC)) == [
        ("course_id", "ENG-101", "ENG-101"),
        ("course_name", "English Composition I", "English Composition I"),
        (
            "course_long_title",
            "English Composition I: Academic Writing",
            "Course Long Title\nEnglish Composition I: Academic Writing",
        ),
        ("course_subject_code", "ENG", "Subject code\nENG"),
        ("course_number", "101", "Course Number\n101"),
        (
            "course_academic_level",
            "Undergraduate",
            "Academic Level\nUndergraduate",
        ),
        (
            "course_description",
            "Develops academic writing. Co-requisite: ENG-091",
            "Develops academic writing. Co-requisite: ENG-091",
        ),
        ("course_credits", 3, "(Credit Hours) Min\n3"),
        ("course_corequisites", "ENG-091", "Co-requisite: ENG-091"),
    ]


def test_rcbc_accepts_the_mercer_style_labels_too() -> None:
    text = COURSEDOG_RCBC.replace("Subject code\n", "Subject Code\n").replace(
        "Description\nDevelops academic writing. Co-requisite: ENG-091\n",
        "Course Description\nDevelops academic writing.\n",
    )
    drafts = by_label(extract_rcbc(text))
    assert drafts["course_subject_code"].excerpt == "Subject Code\nENG"
    assert drafts["course_description"].value == "Develops academic writing."
    assert "course_corequisites" not in drafts
