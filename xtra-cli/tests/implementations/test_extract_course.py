from __future__ import annotations

import pytest
from extract_doubles import COURSE_FIXTURES, fixture_html, fixture_page

from implementations.discover_dom import parse, read_fingerprint
from implementations.discover_rules import (
    LABEL_COURSE,
    PLATFORM_NAMES,
    PLATFORM_WEAK,
)
from implementations.extract_course import (
    COURSE,
    COURSE_BLOCK_SELECTORS,
    COURSE_CODE_PARTS,
    code_at_start,
    course_code,
    course_occurrences,
    course_resource_id,
)
from implementations.extract_run import printed_text


@pytest.mark.parametrize(
    ("name", "platform"),
    [
        ("acalog-course", "acalog"),
        ("acalog-course-letter-suffix", "acalog"),
        ("acalog-course-former-number", "acalog"),
        ("courseleaf-courseblocks", "courseleaf"),
        ("courseleaf-empty-title", "courseleaf"),
        ("courseleaf-detail-code", "courseleaf"),
        ("courseleaf-detail-title", "courseleaf"),
        ("curriqunet-courses", "curriqunet"),
        ("curriqunet-units-in-title", "curriqunet"),
        ("elumen-course", "elumen"),
        ("elumen-course-name-paragraph", "elumen"),
        ("slate-course", ""),
    ],
)
def test_each_trimmed_page_still_fingerprints_as_its_platform(
    name: str, platform: str
) -> None:
    assert read_fingerprint(parse(fixture_html(name))).platform == platform


def test_every_fixture_is_tested_here() -> None:
    names = {path.stem for path in COURSE_FIXTURES.glob("*.html")}
    assert len(names) == 12


def test_a_courseleaf_page_has_one_occurrence_per_course_block() -> None:
    occurrences = course_occurrences(fixture_page("courseleaf-courseblocks"))
    assert len(occurrences) == 7
    assert not any(o.is_whole_page for o in occurrences)
    assert printed_text(occurrences[1].element).startswith("PHAR 199.")


def test_curriqunet_blocks_come_from_its_own_markup() -> None:
    occurrences = course_occurrences(fixture_page("curriqunet-courses"))
    assert len(occurrences) == 3
    assert all(
        "course-summary-wrapper" in o.element["class"] for o in occurrences
    )


@pytest.mark.parametrize(
    "name", ["elumen-course", "acalog-course", "slate-course"]
)
def test_a_one_course_page_is_one_whole_page_occurrence(name: str) -> None:
    (occurrence,) = course_occurrences(fixture_page(name))
    assert occurrence.is_whole_page


def test_the_site_heading_is_outside_the_course() -> None:
    """UALR prints "Catalogs" as an h1 in its banner, above the course."""
    page = fixture_page("acalog-course")
    (occurrence,) = course_occurrences(page)
    headings = [printed_text(h) for h in occurrence.element.find_all("h1")]
    assert "Catalogs" not in headings
    assert any(h.startswith("COMM 79073") for h in headings)


def test_an_occurrence_path_finds_its_element_again() -> None:
    page = fixture_page("courseleaf-courseblocks")
    for occurrence in course_occurrences(page):
        assert page.soup.select_one(occurrence.css_path) is occurrence.element


def test_an_unknown_platform_still_finds_courseleaf_blocks_by_class() -> None:
    page = fixture_page("courseleaf-detail-code", platform="")
    assert len(course_occurrences(page)) == 3


def test_a_block_without_a_code_near_its_start_is_not_a_course() -> None:
    page = fixture_page("slate-course", platform="")
    page.soup.body.append(
        parse(
            '<div class="course-description">A long text about solar '
            "energy with no code at all.</div>"
        ).div
    )
    (occurrence,) = course_occurrences(page)
    assert occurrence.is_whole_page


def test_block_selectors_are_known_strong_platforms() -> None:
    for platform in COURSE_BLOCK_SELECTORS:
        assert platform in PLATFORM_NAMES
        assert platform not in PLATFORM_WEAK


def test_a_platform_block_counts_even_when_its_code_reads_as_no_code() -> None:
    """CurriQunet prints "PARA 51"; the code pattern refuses two bare
    digits (so "GOAL 1" isn't a course), and the block is still a course."""
    page = fixture_page("curriqunet-courses")
    for subject in page.soup.select(".course-number"):
        subject.string = "51 "
    assert len(course_occurrences(page)) == 3


def test_the_course_class_reads_course_pages_by_their_blocks() -> None:
    assert COURSE.rdf_type == "ceterms:Course"
    assert COURSE.page_label == LABEL_COURSE
    assert COURSE.occurrences is course_occurrences
    assert COURSE.resource_id is course_resource_id


# --- resource ids --------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "ids"),
    [
        ("acalog-course", ["c_COMM79073"]),
        ("acalog-course-former-number", ["c_HHPR17001"]),
        ("acalog-course-letter-suffix", ["c_ECEG8000V"]),
        ("courseleaf-courseblocks", ["c_PHAR191", "c_PHAR199"]),
        ("courseleaf-detail-code", ["c_SOC200", "c_SOC200H"]),
        ("courseleaf-detail-title", ["c_BAS4253", "c_BAS4353"]),
        ("courseleaf-empty-title", ["c_LAW604", "c_LAW793"]),
        ("curriqunet-courses", ["c_PSYCC1000", "c_PSYC1B"]),
        ("curriqunet-units-in-title", ["c_ENGL6", "c_ENGL8"]),
        ("elumen-course", ["c_AJ101"]),
        ("elumen-course-name-paragraph", ["c_APPRB48G"]),
    ],
)
def test_a_course_is_identified_by_its_catalog_and_clean_code(
    name: str, ids: list[str]
) -> None:
    page = fixture_page(name)
    found = [course_resource_id(o, page, "c") for o in course_occurrences(page)]
    assert found[: len(ids)] == ids


def test_a_course_with_no_code_has_no_resource_id() -> None:
    page = fixture_page("slate-course")
    (occurrence,) = course_occurrences(page)
    assert course_resource_id(occurrence, page, "c") is None


def test_curriqunet_codes_come_from_its_subject_and_number_markup() -> None:
    """ "ENGL 6" is a code the code pattern refuses on its own."""
    page = fixture_page("curriqunet-units-in-title")
    assert COURSE_CODE_PARTS["curriqunet"] == (
        ".course-subject",
        ".course-number",
    )
    assert course_code(course_occurrences(page)[0], page) == "ENGL 6"


def test_a_one_course_page_reads_its_code_from_a_heading_only() -> None:
    """A paragraph's first code is as likely a prerequisite."""
    page = fixture_page("slate-course")
    page.soup.body.insert(
        0, parse("<p>Prerequisite: MATH 101 or equivalent.</p>").p
    )
    (occurrence,) = course_occurrences(page)
    assert course_code(occurrence, page) is None


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("NUR 741-A Health Care Practicum", "NUR 741-A"),
        ("NUR 741A Health Care Clinical Practicum", "NUR 741A"),
        ("NUR 741 Adv HC Prac/Phys As", "NUR 741"),
        ("PSYC C1000 - Introduction to Psychology", "PSYC C1000"),
        ("COMM 79073 - (was ACOM 7390) Intro", "COMM 79073"),
        ("ABC 101-Intro to Things", "ABC 101"),
        ("A&VS 591. Advanced Topics", "A&VS 591"),
        ("Introduction to Psychology", None),
    ],
)
def test_a_section_letter_after_a_hyphen_is_part_of_the_code(
    text: str, code: str | None
) -> None:
    assert code_at_start(text) == code


def test_courses_told_apart_by_a_hyphen_keep_different_ids() -> None:
    """Marshall prints NUR 741-A and NUR 741A, two different courses."""
    page = fixture_page("courseleaf-detail-code")
    first, second, *_ = course_occurrences(page)
    for occurrence, code in ((first, "NUR 741-A"), (second, "NUR 741A")):
        title = occurrence.element.select_one(".detail-code strong, strong")
        title.string = f"{code} Health Care Practicum"
    assert [course_resource_id(o, page, "c") for o in (first, second)] == [
        "c_NUR741-A",
        "c_NUR741A",
    ]
