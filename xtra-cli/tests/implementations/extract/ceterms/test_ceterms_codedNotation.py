"""ceterms:codedNotation, read from a course, against pages from real catalogs.

Every expected value below is the code as the page prints it, its
whitespace collapsed to one space.
"""

from __future__ import annotations

import pytest
from extract_doubles import fixture_page

from implementations.discover_dom import parse
from implementations.discover_rules import PLATFORM_CURRIQUNET
from implementations.extract.ceterms.ceterms_codedNotation import (
    CLASS,
    PROPERTY,
    read,
)
from implementations.extract.ceterms.ceterms_identifier import (
    read as read_identifier,
)
from implementations.extract_course import course_occurrences
from implementations.extract_run import Page


def test_the_module_declares_its_ctdl_property() -> None:
    assert PROPERTY == "ceterms:codedNotation"


def test_it_is_read_from_courses() -> None:
    assert CLASS == ("ceterms:Course",)


def notations(page: Page) -> list[str | None]:
    return [read(o, page).value for o in course_occurrences(page)]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # "COMM 79073 - (was ACOM 7390) Introduction to…": a former
        # number printed after the code is not the course's code.
        ("acalog-course", ["COMM 79073"]),
        ("acalog-course-former-number", ["HHPR 17001"]),
        ("acalog-course-letter-suffix", ["ECEG 8000V"]),
        # "Administrative Law - LAWW 65043": the code after the title.
        ("acalog-course-code-after-title", ["LAWW 65043"]),
        ("acalog-course-honors-number", ["HNRS 103H1"]),
        # A page of course blocks, each opening "PHAR 191.  Title.".
        (
            "courseleaf-courseblocks",
            [
                "PHAR 191",
                "PHAR 199",
                "PHAR 410",
                "PHAR 415",
                "PHAR 420",
                "PHAR 497",
                "PHAR 498",
            ],
        ),
        ("courseleaf-detail-code", ["SOC 200", "SOC 200H", "SOC 280"]),
        # The subject and number are elements of their own, "PSYC " and
        # "C1000  ".
        ("curriqunet-courses", ["PSYC C1000", "PSYC 1B", "PSYC 2"]),
        ("curriqunet-units-in-title", ["ENGL 6", "ENGL 8"]),
        # "AJ 101:" above the title; the colon is not the code's.
        ("elumen-course", ["AJ 101"]),
        ("elumen-course-name-paragraph", ["APPR B48G"]),
    ],
)
def test_the_code_as_printed(name: str, expected: list[str]) -> None:
    assert notations(fixture_page(name)) == expected


def _page(
    html: str,
    url: str = "https://catalog.example.edu/s",
    platform: str = "",
) -> Page:
    return Page(
        stem="s",
        url=url,
        soup=parse(html),
        platform=platform,
        profile={},
    )


def test_whitespace_collapses_to_one_space_a_section_hyphen_stays() -> None:
    page = _page(
        "<main><h1>NUR\xa0\xa0741-A  Health Care Practicum</h1></main>"
    )
    assert notations(page) == ["NUR 741-A"]


def test_a_subject_of_two_words_keeps_its_space() -> None:
    """A subject can be two words, "F SC", printed apart from its number."""
    page = _page(
        '<main><div class="course-summary-wrapper">'
        '<b class="course-title-units-row">'
        '<span class="course-subject">F SC </span>'
        '<span class="course-number">33A </span>'
        '<span class="course-sbj-num-delimiter"> - </span>'
        '<span class="course-title">Fire Investigation</span></b>'
        "</div></main>",
        platform=PLATFORM_CURRIQUNET,
    )
    assert notations(page) == ["F SC 33A"]


def test_a_course_with_no_code_has_none() -> None:
    page = _page("<main><h1>Solar Energy</h1></main>")
    (reading,) = (read(o, page) for o in course_occurrences(page))
    assert (reading.value, reading.reason) == (None, "no_candidate")


def test_a_course_named_only_by_its_address_has_none() -> None:
    """The address gives an identifier, but nothing printed to notate."""
    page = _page(
        "<main><h1>Python Programming for Data Science 2</h1></main>",
        url="https://training.example.edu/portal/training?cmd=catalog&course=1",
    )
    assert notations(page) == [None]


def test_it_is_the_identifier_with_its_spaces() -> None:
    page = fixture_page("courseleaf-courseblocks")
    for occurrence in course_occurrences(page):
        notation = read(occurrence, page).value
        identifier = read_identifier(occurrence, page).value
        assert notation.replace(" ", "") == identifier
