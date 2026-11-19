"""ceterms:lifeCycleStatusType, read from a course.

Every course the Golden Dataset Studio's reviewers looked at is Active: a
catalog lists the courses it offers. The other statuses are read only where
the course itself prints one.
"""

from __future__ import annotations

import pytest
from extract_doubles import fixture_page

from implementations.discover_dom import parse
from implementations.extract.ceterms.ceterms_lifeCycleStatusType import (
    CLASS,
    PROPERTY,
    read,
    status_of,
)
from implementations.extract_course import course_occurrences
from implementations.extract_run import Page, Reading


def test_the_module_declares_its_ctdl_property() -> None:
    assert PROPERTY == "ceterms:lifeCycleStatusType"


def test_it_is_read_from_courses() -> None:
    assert CLASS == ("ceterms:Course",)


def readings(page: Page) -> list[Reading]:
    return [read(o, page) for o in course_occurrences(page)]


def _page(html: str) -> Page:
    return Page(
        stem="s",
        url="https://catalog.example.edu/s",
        soup=parse(html),
        platform="",
        profile={},
    )


def status(html: str) -> tuple[str, str]:
    (reading,) = readings(_page(html))
    return reading.value, reading.strategy


@pytest.mark.parametrize(
    "name",
    [
        "acalog-course",
        "courseleaf-courseblocks",
        "courseleaf-detail-code",
        "curriqunet-courses",
        "elumen-course",
        "slate-course",
    ],
)
def test_a_course_a_catalog_lists_is_active(name: str) -> None:
    found = readings(fixture_page(name))
    assert found
    assert {(r.value, r.strategy) for r in found} == {
        ("Active", "listed_in_catalog")
    }


def test_the_sites_archived_catalogs_menu_says_nothing_of_the_course() -> None:
    assert status(
        "<body><nav><a>Archived Catalogs</a></nav>"
        "<main><h1>ENGL 101 - Composition</h1>"
        "<p>Students write essays.</p></main></body>"
    ) == ("Active", "listed_in_catalog")


def test_a_status_word_in_the_description_is_not_a_status() -> None:
    assert status(
        "<main><h1>ENVS 31 - Environmental Science</h1>"
        "<p>Models to evaluate environmental problems and their proposed "
        "solutions. Students who have withdrawn may reapply.</p></main>"
    ) == ("Active", "listed_in_catalog")


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Status: Active", "Active"),
        ("Course Status: Inactive", "Ceased"),
        ("Status - Discontinued", "Ceased"),
        ("Status: Suspended", "Suspended"),
        ("Status: Pending Approval", "Developing"),
        ("Life Cycle Status: Teach-out", "Ceasing"),
    ],
)
def test_a_status_label(label: str, expected: str) -> None:
    assert status(
        f"<main><h1>BIOL 210 - Genetics</h1><p>{label}</p></main>"
    ) == (expected, "status_label")


def test_a_students_or_a_sections_status_is_not_the_courses() -> None:
    assert status(
        "<main><h1>BIOL 210 - Genetics</h1>"
        "<p>Enrollment Status: Pending</p><p>Section Status: Cancelled</p>"
        "</main>"
    ) == ("Active", "listed_in_catalog")


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("ENGL 101 - Composition (Inactive)", "Ceased"),
        ("[DELETED] ENGL 101 - Composition", "Ceased"),
        ("ENGL 101 - Composition *Proposed*", "Developing"),
        ("ENGL 101 - Composition - DISCONTINUED", "Ceased"),
    ],
)
def test_a_status_marked_in_the_title(title: str, expected: str) -> None:
    assert status(f"<main><h1>{title}</h1><p>Essays.</p></main>") == (
        expected,
        "title_marker",
    )


def test_a_title_word_in_sentence_case_is_not_a_marker() -> None:
    assert status(
        "<main><h1>GERO 300 - Retired Persons and Society</h1></main>"
    ) == ("Active", "listed_in_catalog")


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("This course is no longer offered.", "Ceased"),
        ("This course has been discontinued.", "Ceased"),
        ("The course was deleted in 2024.", "Ceased"),
        ("This course will be discontinued after Spring 2027.", "Ceasing"),
        ("This course will no longer be offered after 2027.", "Ceasing"),
        ("This course is being phased out.", "Ceasing"),
        ("This course is temporarily inactive.", "Suspended"),
        ("This course is not currently offered.", "Suspended"),
        ("This course is under development.", "Developing"),
    ],
)
def test_a_sentence_about_the_course(sentence: str, expected: str) -> None:
    assert status(
        f"<main><h1>HIST 220 - Modern Europe</h1><p>{sentence}</p></main>"
    ) == (expected, "course_statement")


def test_how_a_course_came_about_is_not_its_status() -> None:
    assert status(
        "<main><h1>HIST 220 - Modern Europe</h1>"
        "<p>This course was proposed by the history faculty.</p></main>"
    ) == ("Active", "listed_in_catalog")


def test_each_block_on_a_page_of_courses_has_its_own_status() -> None:
    page = _page(
        "<main>"
        '<div class="courseblock"><p>CHEM 101 General Chemistry. 4 Hours.'
        "</p><p>Atoms and molecules.</p></div>"
        '<div class="courseblock"><p>CHEM 102 Applied Chemistry (Inactive).'
        " 4 Hours.</p><p>Reactions.</p></div>"
        "</main>"
    )
    assert [r.value for r in readings(page)] == ["Active", "Ceased"]


def test_the_text_it_was_read_from_is_kept() -> None:
    (reading,) = readings(
        _page(
            "<main><h1>HIST 220 - Modern Europe</h1>"
            "<p>This course   has been discontinued.</p></main>"
        )
    )
    assert reading.raw_text == "This course has been discontinued"


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        ("Active", "Active"),
        ("inactive", "Ceased"),
        ("temporarily inactive", "Suspended"),
        ("phasing out", "Ceasing"),
        ("in development", "Developing"),
        ("Open", None),
        ("Closed", None),
    ],
)
def test_the_words_each_status_is_printed_as(
    words: str, expected: str | None
) -> None:
    assert status_of(words) == expected
