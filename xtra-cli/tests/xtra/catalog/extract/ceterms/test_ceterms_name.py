"""ceterms:name, read from a course, against headings and pages from real catalogs.

Every expected value below is one the Golden Dataset Studio's reviewers
accepted, or the title the page prints when they didn't review it.
"""

from __future__ import annotations

import pytest
from extract_doubles import fixture_page

from implementations.discover_dom import parse
from implementations.extract import Occurrence, Page
from implementations.extract_course import course_occurrences as occurrences
from xtra.catalog.extract.ceterms.ceterms_name import (
    CLASS,
    PROPERTY,
    is_code_only,
    read,
    split_name,
)


def test_the_module_declares_its_ctdl_property() -> None:
    assert PROPERTY == "ceterms:name"


def test_it_is_read_from_courses() -> None:
    assert CLASS == ("ceterms:Course",)


# --- split_name --------------------------------------------------------------


@pytest.mark.parametrize(
    ("heading", "name"),
    [
        # CourseLeaf classic: code, title and hours on one line.
        ("LAW\xa0604.  Natural Resources.  3 Hours.", "Natural Resources"),
        # A section letter after a hyphen is part of the code, not the name.
        ("NUR 741-A Health Care Practicum", "Health Care Practicum"),
        ("CAHS 690. Teaching Practicum. 1-3 Hours.", "Teaching Practicum"),
        # The publisher wrote hours into the title itself; only the
        # heading's own credits go.
        (
            "PHAR 199.  Orientation to Pharmacy 1-2 Hr.  1,2 Hour.",
            "Orientation to Pharmacy 1-2 Hr",
        ),
        # Acalog: "CODE - Title", with a former number sometimes.
        (
            "COMM 79073\xa0-\xa0(was ACOM 7390) Introduction to Applied "
            "Communication Studies",
            "Introduction to Applied Communication Studies",
        ),
        (
            "HHPR 17001\xa0-\xa0(Was 1170)  C P R ",
            "C P R",
        ),
        (
            "ECEG 8000V\xa0-\xa0Electrical and Computer Engineering "
            "Master's Thesis",
            "Electrical and Computer Engineering Master's Thesis",
        ),
        # CourseLeaf detail theme: code, then title, a space between.
        (
            "SOC\xa0200\xa0 \xa0Understanding Society (CT)",
            "Understanding Society (CT)",
        ),
        # Credits in parentheses after the title.
        (
            "PSYC C1000 - Introduction to Psychology (3.0)",
            "Introduction to Psychology",
        ),
    ],
)
def test_a_combined_heading_gives_its_title(heading: str, name: str) -> None:
    assert split_name(heading, combined=True) == name


def test_an_empty_title_gives_nothing_not_the_credits() -> None:
    """WVU prints LAW 793 with no title at all."""
    assert split_name("LAW\xa0793.  .  1-6 Hours.", combined=True) == ""


@pytest.mark.parametrize(
    "title",
    [
        "United States History since 1865 - Honors",
        "Skills Lab 922L",
        "19Th Century Literature",
        "Child Development: The First Three Years",
        "LEGAL/ETHIC ASP COUNS & STU PE",
    ],
)
def test_a_title_keeps_what_it_prints(title: str) -> None:
    """No splitting on " - " or ":", no trailing digits lost, no recasing."""
    assert split_name(title, combined=True) == title
    assert split_name(title, combined=False) == title


def test_a_title_only_element_is_only_collapsed() -> None:
    assert (
        split_name("  Juvenile   Procedures ", combined=False)
        == "Juvenile Procedures"
    )


def test_a_bare_trailing_number_is_part_of_the_title() -> None:
    assert split_name("MATH 102 Calculus 2", combined=True) == "Calculus 2"


@pytest.mark.parametrize("text", ["AJ 101:", "PSYC 1B", "LAW\xa0604."])
def test_a_code_alone_is_code_only(text: str) -> None:
    assert is_code_only(text)


def test_a_title_is_not_code_only() -> None:
    assert not is_code_only("Skills Lab 922L")


# --- read, on real pages -------------------------------------------------


def names(page: Page) -> list[tuple[str | None, str]]:
    """(name, strategy) per course, or (None, why) when there is none."""
    return [
        (reading.value, reading.reason or reading.strategy)
        for reading in (read(o, page) for o in occurrences(page))
    ]


def test_acalog_reads_the_preview_title() -> None:
    assert names(fixture_page("acalog-course")) == [
        ("Introduction to Applied Communication Studies", "profile_title")
    ]


def test_acalog_reads_a_code_with_a_letter_suffix() -> None:
    """UALR's own rule left all 222 of these empty."""
    assert names(fixture_page("acalog-course-letter-suffix")) == [
        (
            "Electrical and Computer Engineering Master’s Thesis",
            "profile_title",
        )
    ]


def test_acalog_drops_a_former_number_whatever_its_case() -> None:
    assert names(fixture_page("acalog-course-former-number")) == [
        ("C P R", "profile_title")
    ]


def test_courseleaf_reads_every_block_title() -> None:
    assert [
        value for value, _ in names(fixture_page("courseleaf-courseblocks"))
    ] == [
        "First-Year Seminar",
        "Orientation to Pharmacy 1-2 Hr",
        "Pathophysiology Behind Drug-Induced Diseases",
        "Introduction to Pharmaceutical and Cosmetic Compounding",
        "Introduction to Herbs in Medicine",
        "Research",
        "Honors",
    ]


def test_a_courseleaf_block_with_no_title_has_no_name() -> None:
    assert names(fixture_page("courseleaf-empty-title")) == [
        ("Natural Resources", "profile_title"),
        (None, "empty_title"),
    ]


def test_the_courseleaf_detail_theme_keeps_its_designation() -> None:
    assert names(fixture_page("courseleaf-detail-code")) == [
        ("Understanding Society (CT)", "profile_title"),
        ("Understanding Society Hon (CT)", "profile_title"),
        ("Special Topics", "profile_title"),
    ]


def test_curriqunet_reads_the_title_span_alone() -> None:
    assert names(fixture_page("curriqunet-courses")) == [
        ("Introduction to Psychology", "profile_title"),
        ("Biological Psychology", "profile_title"),
        ("Research Methods", "profile_title"),
    ]


def test_elumen_reads_the_course_header_not_the_hidden_page_heading() -> None:
    assert names(fixture_page("elumen-course")) == [
        ("Introduction to Administration of Justice", "profile_title")
    ]


# Catalogs the Studio never saw, of the same platforms: the profile holds
# each platform's other themes too.


def test_the_courseleaf_detail_theme_with_a_title_of_its_own() -> None:
    """The code is alone in .detail-code; the title is in .detail-title."""
    assert names(fixture_page("courseleaf-detail-title")) == [
        ("Quality Control", "profile_title"),
        ("Project Management", "profile_title"),
    ]


def test_an_elumen_title_printed_as_a_paragraph_beside_the_code() -> None:
    assert names(fixture_page("elumen-course-name-paragraph")) == [
        (
            "Work Experience Education/Internship Digital Marketer",
            "profile_title",
        )
    ]


def test_curriqunet_units_inside_the_title_span_are_dropped() -> None:
    assert names(fixture_page("curriqunet-units-in-title")) == [
        ("Creative Writing", "profile_title"),
        ("British Literature I", "profile_title"),
    ]


# --- read, with no platform: the generic strategies alone ------------------


def test_a_page_with_no_platform_reads_its_title_class() -> None:
    """training-uark runs on Slate, which discovery doesn't fingerprint."""
    assert names(fixture_page("slate-course")) == [
        ("Solar Energy", "title_class")
    ]


def test_elumen_without_its_profile_reads_the_heading_beside_the_code() -> None:
    assert names(fixture_page("elumen-course", platform="")) == [
        ("Introduction to Administration of Justice", "heading_beside_code")
    ]


def test_acalog_without_its_profile_reads_the_first_heading() -> None:
    assert names(fixture_page("acalog-course", platform="")) == [
        ("Introduction to Applied Communication Studies", "first_heading")
    ]


def test_courseleaf_without_its_profile_reads_the_title_class() -> None:
    assert names(fixture_page("courseleaf-empty-title", platform="")) == [
        ("Natural Resources", "title_class"),
        (None, "empty_title"),
    ]


def test_a_block_whose_title_no_class_names_reads_its_code_line() -> None:
    """Marshall's spans hold the title; nothing calls them a title."""
    assert names(fixture_page("courseleaf-detail-code", platform="")) == [
        ("Understanding Society (CT)", "code_line"),
        ("Understanding Society Hon (CT)", "code_line"),
        ("Special Topics", "code_line"),
    ]


# --- read, edge cases --------------------------------------------------------


def _whole_page(html: str, **profile) -> tuple[Occurrence, Page]:
    page = Page(
        stem="s",
        url="https://catalog.example.edu/s",
        soup=parse(html),
        platform="",
        profile=profile,
    )
    (occurrence,) = occurrences(page)
    return occurrence, page


def test_the_page_name_is_the_last_resort_on_a_one_course_page() -> None:
    occurrence, page = _whole_page(
        "<main><p>Text only.</p></main>",
        h1="",
        title="Welding Basics | Example College",
    )
    reading = read(occurrence, page)
    assert (reading.value, reading.strategy) == ("Welding Basics", "page_name")


def test_the_site_name_is_never_a_course_name() -> None:
    occurrence, page = _whole_page(
        '<head><meta property="og:site_name" content="Example Catalog">'
        "</head><main><h1>Example Catalog</h1></main>"
    )
    reading = read(occurrence, page)
    assert reading.value is None
    assert reading.reason == "rejected:site_name"


def test_a_heading_too_long_to_be_a_title_is_passed_over() -> None:
    long = "word " * 40
    occurrence, page = _whole_page(
        f"<main><h2>{long}</h2><h3>Short Title</h3></main>"
    )
    assert read(occurrence, page).value is None


def test_nothing_to_read_says_so() -> None:
    occurrence, page = _whole_page("<main><p>No heading.</p></main>")
    reading = read(occurrence, page)
    assert reading.value is None
    assert reading.reason == "no_candidate"


def test_a_title_element_holding_only_the_code_is_code_only() -> None:
    page = Page(
        stem="s",
        url="u",
        soup=parse(
            '<main><div class="courseblock"><p class="courseblocktitle">'
            "LAW 793.</p></div></main>"
        ),
        platform="courseleaf",
        profile={},
    )
    (occurrence,) = occurrences(page)
    assert read(occurrence, page).reason == "code_only"


def test_a_code_with_a_section_letter_alone_is_code_only() -> None:
    assert is_code_only("NUR 741-A")
    assert not is_code_only("NUR 741-A Health Care Practicum")
