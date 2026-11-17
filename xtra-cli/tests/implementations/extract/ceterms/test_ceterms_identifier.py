"""ceterms:identifier, read from a course, against pages from real catalogs.

Every expected value below is the code the page prints without its spaces,
which is what the Golden Dataset Studio's reviewers accepted on each of
these platforms.
"""

from __future__ import annotations

import pytest
from extract_doubles import fixture_page

from implementations.discover_dom import parse
from implementations.extract.ceterms.ceterms_identifier import (
    CLASS,
    PROPERTY,
    read,
)
from implementations.extract_course import (
    address_identifier,
    course_occurrences,
    course_resource_id,
)
from implementations.extract_run import Page


def test_the_module_declares_its_ctdl_property() -> None:
    assert PROPERTY == "ceterms:identifier"


def test_it_is_read_from_courses() -> None:
    assert CLASS == ("ceterms:Course",)


def identifiers(page: Page) -> list[str | None]:
    return [read(o, page).value for o in course_occurrences(page)]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # Acalog: "COMM 79073 - (was ACOM 7390) Introduction to…"; the
        # former number is not the course's code.
        ("acalog-course", ["COMM79073"]),
        ("acalog-course-former-number", ["HHPR17001"]),
        ("acalog-course-letter-suffix", ["ECEG8000V"]),
        # CourseLeaf: "PHAR 191.  Title.  1 Hour." in each block.
        (
            "courseleaf-courseblocks",
            [
                "PHAR191",
                "PHAR199",
                "PHAR410",
                "PHAR415",
                "PHAR420",
                "PHAR497",
                "PHAR498",
            ],
        ),
        ("courseleaf-detail-code", ["SOC200", "SOC200H", "SOC280"]),
        # CurriQunet: the subject and number are spans of their own.
        ("curriqunet-courses", ["PSYCC1000", "PSYC1B", "PSYC2"]),
        ("curriqunet-units-in-title", ["ENGL6", "ENGL8"]),
        # eLumen: "AJ 101:" above the title; the colon is not the code's.
        ("elumen-course", ["AJ101"]),
        ("elumen-course-name-paragraph", ["APPRB48G"]),
    ],
)
def test_the_code_without_its_spaces(name: str, expected: list[str]) -> None:
    assert identifiers(fixture_page(name)) == expected


def _page(html: str, url: str = "https://catalog.example.edu/s") -> Page:
    return Page(
        stem="s",
        url=url,
        soup=parse(html),
        platform="",
        profile={},
    )


def test_only_whitespace_goes_a_section_hyphen_stays() -> None:
    page = _page("<main><h1>NUR\xa0741-A  Health Care Practicum</h1></main>")
    assert identifiers(page) == ["NUR741-A"]


def test_a_course_with_no_code_and_no_course_in_its_address_has_none() -> None:
    page = _page("<main><h1>Solar Energy</h1></main>")
    (reading,) = (read(o, page) for o in course_occurrences(page))
    assert (reading.value, reading.reason) == (None, "no_candidate")


def test_it_is_the_code_the_resource_id_is_made_of() -> None:
    page = fixture_page("courseleaf-courseblocks")
    for occurrence in course_occurrences(page):
        resource_id = course_resource_id(occurrence, page, "c")
        assert resource_id == f"c_{read(occurrence, page).value}"


TRAINING = "https://training.example.edu/portal/training?cmd=catalog&course="


def test_a_course_with_no_code_is_known_by_its_page_address() -> None:
    page = _page(
        "<main><h1>Python Programming for Data Science 2</h1></main>",
        url=f"{TRAINING}109497",
    )
    (occurrence,) = course_occurrences(page)
    reading = read(occurrence, page)
    assert (reading.value, reading.strategy) == ("109497", "page_address")
    assert course_resource_id(occurrence, page, "c") == "c_109497"


def test_a_printed_code_comes_before_the_address() -> None:
    page = _page(
        "<main><h1>ABCD 7001 - Example Concepts</h1></main>",
        url=f"{TRAINING}109497",
    )
    assert identifiers(page) == ["ABCD7001"]


def test_a_block_on_a_page_of_courses_is_not_named_by_the_address() -> None:
    """Every block shares the page's address, so it names none of them."""
    page = fixture_page("courseleaf-courseblocks")
    page = Page(
        stem=page.stem,
        url=f"{TRAINING}109497",
        soup=page.soup,
        platform=page.platform,
        profile=page.profile,
    )
    for occurrence in course_occurrences(page):
        assert address_identifier(occurrence, page) is None
