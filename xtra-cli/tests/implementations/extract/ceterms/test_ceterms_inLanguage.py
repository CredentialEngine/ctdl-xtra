"""ceterms:inLanguage, read from a course: what it says it is taught in,
else what the page's markup declares."""

from __future__ import annotations

import pytest
from extract_doubles import fixture_page

from implementations.discover_dom import parse
from implementations.extract.ceterms.ceterms_inLanguage import (
    CLASS,
    PROPERTY,
    read,
    tag_language,
)
from implementations.extract_course import course_occurrences
from implementations.extract_run import Page, Reading


def test_the_module_declares_its_ctdl_property() -> None:
    assert PROPERTY == "ceterms:inLanguage"


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


def _course(description: str, lang: str = ' lang="en"') -> Page:
    return _page(
        f"<!DOCTYPE html><html{lang}><body><main>"
        f"<h1>SPAN 203 Advanced Spanish</h1><p>{description}</p>"
        "</main></body></html>"
    )


@pytest.mark.parametrize(
    "name",
    [
        "acalog-course",
        "courseleaf-courseblocks",
        "curriqunet-courses",
        "elumen-course",
    ],
)
def test_a_page_that_declares_english_gives_every_course_english(
    name: str,
) -> None:
    found = readings(fixture_page(name))
    assert found
    assert {(r.value, r.strategy) for r in found} == {
        ("English", "markup_lang")
    }


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("The course will be conducted entirely in Spanish.", "Spanish"),
        ("Course taught in Japanese. Pre-req: JPN 204.", "Japanese"),
        ("Conducted in Italian.", "Italian"),
        ("Course conducted primarily in Italian.", "Italian"),
        ("This course, conducted entirely in German, is for", "German"),
        ("This course is taught in ASL only.", "American Sign Language"),
        ("Course is taught in Mandarin.", "Mandarin Chinese"),
        ("Taught in English, this course examines Japanese film.", "English"),
    ],
)
def test_a_course_that_says_what_it_is_taught_in(
    description: str, expected: str
) -> None:
    (reading,) = readings(_course(description))
    assert (reading.value, reading.strategy) == (expected, "stated")


@pytest.mark.parametrize(
    "description",
    [
        # About a language, not taught in it.
        "Introduction to Spanish grammar and conversation.",
        "Oral practice in Spanish and readings in French.",
        "Students read texts in German translation.",
    ],
)
def test_a_course_about_a_language_is_not_taught_in_it(
    description: str,
) -> None:
    (reading,) = readings(_course(description))
    assert (reading.value, reading.strategy) == ("English", "markup_lang")


def test_each_course_on_a_page_says_its_own() -> None:
    page = _page(
        '<html lang="en"><body><main>'
        '<div class="courseblock"><p>FREN 301 Composition.</p>'
        "<p>Taught in French.</p></div>"
        '<div class="courseblock"><p>FCLT 210 Chinese Civilization.</p>'
        "<p>A survey of Chinese institutions.</p></div>"
        "</main></body></html>"
    )
    assert [r.value for r in readings(page)] == ["French", "English"]


def test_the_nearest_lang_around_the_course_wins() -> None:
    page = _page(
        '<html lang="en"><body><main lang="fr-CA">'
        "<h1>FREN 101 Introduction</h1></main></body></html>"
    )
    assert [r.value for r in readings(page)] == ["French"]


def test_a_content_language_header_when_no_lang_is_declared() -> None:
    page = _page(
        '<html><head><meta http-equiv="Content-Language" content="es, en">'
        "</head><body><main><h1>SPAN 101 Elementary Spanish</h1></main>"
        "</body></html>"
    )
    (reading,) = readings(page)
    assert (reading.value, reading.strategy) == ("Spanish", "content_language")


def test_a_page_that_declares_no_language_gives_none() -> None:
    (reading,) = readings(_course("Introduction to Spanish.", lang=""))
    assert (reading.value, reading.reason) == (None, "no_candidate")


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("en", "English"),
        ("en-US", "English"),
        ("EN_gb", "English"),
        ("zh-Hant", "Chinese"),
        ("x-klingon", "x-klingon"),
        ("  ", None),
    ],
)
def test_a_language_tag_by_its_english_name(
    tag: str, expected: str | None
) -> None:
    assert tag_language(tag) == expected
