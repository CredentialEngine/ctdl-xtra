from __future__ import annotations

import pytest

from implementations.discover_rules import (
    CREDIT_VALUE_RE,
    EMPTY_OR_ERROR_RE,
    LECTURE_LAB_CREDIT_RE,
    MARKER_MEANING,
    MARKER_NAMES,
    PREREQ_COREQ_COMBINED_RE,
    catalog_year_value,
    course_block_count,
    evidence,
    has_program_content,
    normalize_field_label,
    program_terms,
    url_template,
)


@pytest.mark.parametrize(
    ("url", "template"),
    [
        ("https://x.edu/courses/engl101", "/courses/engl{n}"),
        ("https://x.edu/content.php?catoid=13&navoid=664", "/content.php?catoid={n}&navoid={n}"),
        ("https://x.edu", "/"),
        ("https://x.edu/2026-2027/a", "/{n}-{n}/a"),
    ],
)
def test_url_template_folds_digits(url: str, template: str) -> None:
    assert url_template(url) == template


@pytest.mark.parametrize(
    ("raw", "label"),
    [
        ("Credits:", "credits"),
        ("  Lab   Hours  ", "lab hours"),
        ("Semester 1", "semester #"),
        ("PREREQUISITE", "prerequisite"),
        ("Total Credits.", "total credits"),
    ],
)
def test_normalize_field_label(raw: str, label: str) -> None:
    assert normalize_field_label(raw) == label


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        ":",
        "ENGL 101 Composition I",
        "A label far longer than any key a catalog would ever print on a page",
    ],
)
def test_text_that_is_not_a_label_is_dropped(raw: str) -> None:
    assert normalize_field_label(raw) is None


def test_a_credits_value_is_read_in_either_order() -> None:
    assert CREDIT_VALUE_RE.search("3 credits")
    assert CREDIT_VALUE_RE.search("Credits: 3")
    assert CREDIT_VALUE_RE.search("Credits\n3")
    assert CREDIT_VALUE_RE.search("1-3 credit hours")
    assert CREDIT_VALUE_RE.search("4.0 units")


def test_a_credit_word_inside_another_word_is_not_a_value() -> None:
    """Without the boundary, every accredited college prints credits."""
    assert not CREDIT_VALUE_RE.search("accredited by 3 agencies")


def test_a_course_block_needs_a_code_and_a_value_near_it() -> None:
    assert course_block_count("ENGL 101 Composition I\nCredits\n3") == 1
    assert course_block_count("See ENGL 101 for details.") == 0
    assert (
        course_block_count("ENGL 101\nCredits 3\nENGL 102\nCredits 3") == 2
    )


def test_a_value_too_far_from_the_code_is_a_different_course() -> None:
    far = "ENGL 101" + ("x" * 500) + " 3 credits"
    assert course_block_count(far) == 0


def test_three_numbers_in_a_row_are_lecture_lab_and_credit() -> None:
    assert LECTURE_LAB_CREDIT_RE.search("2-3-3")
    assert LECTURE_LAB_CREDIT_RE.search("3/2/4")
    assert not LECTURE_LAB_CREDIT_RE.search("2026-2027")


def test_a_combined_heading_is_recognised_in_its_usual_spellings() -> None:
    for heading in (
        "Prerequisite/Corequisite",
        "Prerequisites and Corequisites",
        "Pre-requisite or Co-requisite",
    ):
        assert PREREQ_COREQ_COMBINED_RE.search(heading), heading


def test_the_word_as_is_not_a_degree() -> None:
    """Matching bare abbreviations made every page a credential."""
    assert program_terms("this page is as plain as it gets") == []
    assert "degree" in program_terms("Associate in Science")
    assert "degree" in program_terms("awarded the A.A.S. degree")


def test_program_terms_are_reported_by_name() -> None:
    text = "Associate in Science. Program Requirements. Total Credits: 60."
    assert program_terms(text) == [
        "degree",
        "program_requirements",
        "total_credits",
    ]


@pytest.mark.parametrize(
    ("text", "year"),
    [
        ("Example College Catalog 2026-2027", "2026-2027"),
        ("Catalog 2026/2027", "2026-2027"),
        ("Catalog 2026-27", "2026-2027"),
        ("Example College Catalog", None),
    ],
)
def test_catalog_year_is_written_out_in_full(text: str, year: str | None) -> None:
    assert catalog_year_value(text) == year


def test_evidence_is_short_enough_to_read() -> None:
    quote = evidence("word " * 200)
    assert len(quote) <= 80
    assert "\n" not in evidence("a\nb")


def test_every_marker_has_a_line_on_why_it_matters() -> None:
    """patterns.md is a demo document, so no marker may be unexplained."""
    assert set(MARKER_NAMES) == set(MARKER_MEANING)
    for name, meaning in MARKER_MEANING.items():
        assert meaning.strip(), name


def test_a_phone_number_is_not_an_error_page() -> None:
    """A college address carrying (404) marked a real page empty."""
    assert not EMPTY_OR_ERROR_RE.search("Atlanta, GA 30326 (404) 975-5000")
    assert not EMPTY_OR_ERROR_RE.search("call 404-975-5000 for details")


def test_a_real_error_page_still_reads_as_one() -> None:
    for text in (
        "Page Not Found",
        "404 Error",
        "Error 404",
        "Access Denied",
        "Please log in to continue",
    ):
        assert EMPTY_OR_ERROR_RE.search(text), text


def test_a_navigation_menu_is_not_a_program_page() -> None:
    """Every page of a catalog links to Degrees and Certificates."""
    assert not has_program_content(["certificate", "degree"])
    assert has_program_content(["degree", "program_requirements"])
    assert has_program_content(["certificate", "degree", "term_sequence"])
