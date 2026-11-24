"""CMS family detection and course URL helpers of the old pack crawler."""

from __future__ import annotations

import pytest
from catalog import (
    abs_url,
    college_slug,
    detect_family,
    institution_from_html,
    is_course_detail_url,
    normalize_course_url,
    origin_of,
    page_id_for,
    record_id_for,
    sample_urls,
    subject_key,
)

import lib

SLUGS = [
    ("https://catalog.brookdalecc.edu/courses/ENGL121", "brookdalecc"),
    ("https://www.atlanticcape.edu", "atlanticcape"),
    ("https://coursecatalog.example.org/x", "example"),
    ("https://bulletin.example.edu", "example"),
    ("https://catalog.mccc.edu:8443/x", "mccc"),
    ("https://Catalog.Example.EDU/", "example"),
    ("https://my_college.example.com", "my-college-example-com"),
    # Each prefix is tried once, in order, so catalog. survives www.
    ("https://www.catalog.example.edu", "catalog-example"),
    ("https://.edu", "college"),
    ("not a url", "catalog"),
]


@pytest.mark.parametrize(("url", "slug"), SLUGS)
@pytest.mark.parametrize("slugify", [college_slug, lib.college_slug])
def test_college_slug_names_the_pack_after_the_host(
    slugify, url: str, slug: str
) -> None:
    """lib.py keeps its own copy of college_slug; the two must agree."""
    assert slugify(url) == slug


def test_origin_defaults_to_https_and_drops_path_query_and_fragment() -> None:
    assert (
        origin_of("http://c.example.edu:81/a?b#c") == "http://c.example.edu:81"
    )
    assert origin_of("//c.example.edu/a") == "https://c.example.edu"


def test_abs_url_resolves_relative_links_and_drops_the_fragment() -> None:
    assert (
        abs_url("https://c.example.edu/a/b", "../c#top")
        == "https://c.example.edu/c"
    )


@pytest.mark.parametrize(
    ("html", "url", "family"),
    [
        ("<script src='https://app.coursedog.com/x.js'>", "", "coursedog"),
        ("", "https://c.example.edu/courses/ENGL121", "coursedog"),
        ("<p>Courses</p>", "https://c.example.edu/courses", "unknown"),
        ("<a href='preview_course_nopop.php?catoid=1&coid=2'>", "", "acalog"),
        ("<meta name=generator content='Acalog ACMS'>", "", "acalog"),
        ("<footer>Modern Campus Catalog</footer>", "", "acalog"),
        ("", "https://c.example.edu/content.php?catoid=8&navoid=9", "acalog"),
        ("<footer>Software by cleancatalog.com</footer>", "", "custom_html"),
        ("<footer>our clean catalog</footer>", "", "unknown"),
        ("<p>cleancatalog.com and coursedog</p>", "", "coursedog"),
        ("<p>cleancatalog.com and acalog</p>", "", "acalog"),
        ("<p>Welcome</p>", "https://www.example.edu/", "unknown"),
    ],
)
def test_detect_family_checks_coursedog_then_acalog_then_clean_catalog(
    html: str, url: str, family: str
) -> None:
    assert detect_family(html, url) == family


@pytest.mark.parametrize(
    ("url", "family", "expected"),
    [
        ("https://c.example.edu/courses/ENGL121", None, True),
        ("https://c.example.edu/courses/ENGL121/", "coursedog", True),
        ("https://c.example.edu/courses/LJdUL84T", "coursedog", False),
        ("https://c.example.edu/courses", "coursedog", False),
        (
            "https://c.example.edu/preview_course_nopop.php?catoid=8&coid=12",
            "acalog",
            True,
        ),
        ("https://c.example.edu/preview_course.php?catoid=8", "acalog", False),
        (
            "https://c.example.edu/content.php?catoid=8&navoid=9",
            "acalog",
            False,
        ),
        ("https://c.example.edu/english/engl101", "custom_html", True),
        ("https://c.example.edu/english", "custom_html", False),
        ("https://c.example.edu/english/engl101", None, True),
        ("https://c.example.edu/about/staff", None, False),
    ],
)
def test_is_course_detail_url_uses_the_family_pattern(
    url: str, family: str | None, expected: bool
) -> None:
    """A Coursedog document id like LJdUL84T is not a course code."""
    assert is_course_detail_url(url, family) is expected


@pytest.mark.parametrize(
    ("url", "normalized"),
    [
        (
            "https://c.example.edu/preview_course.php?catoid=8&coid=12"
            "&returnto=3#x",
            "https://c.example.edu/preview_course_nopop.php?catoid=8&coid=12",
        ),
        (
            "https://c.example.edu/preview_course_nopop.php?coid=12&catoid=8",
            "https://c.example.edu/preview_course_nopop.php?coid=12&catoid=8",
        ),
        (
            "https://c.example.edu/preview_course.php?catoid=8",
            "https://c.example.edu/preview_course.php?catoid=8",
        ),
        (
            "https://c.example.edu/courses/ENGL121/?tab=1#top",
            "https://c.example.edu/courses/ENGL121",
        ),
        (
            "https://c.example.edu/english/engl101/",
            "https://c.example.edu/english/engl101",
        ),
        ("https://c.example.edu/about#team", "https://c.example.edu/about"),
    ],
)
def test_normalize_course_url_gives_one_url_per_course(
    url: str, normalized: str
) -> None:
    assert normalize_course_url(url) == normalized


@pytest.mark.parametrize(
    ("url", "hint", "record_id"),
    [
        (
            "https://c.example.edu/courses/ENGL121",
            None,
            "brookdalecc-engl121-course",
        ),
        (
            "https://c.example.edu/preview_course_nopop.php?catoid=8&coid=1234",
            "ENG 101",
            "brookdalecc-coid-1234-course",
        ),
        (
            "https://c.example.edu/courses/x",
            "ENG 101",
            "brookdalecc-eng-101-course",
        ),
    ],
)
def test_record_id_prefers_the_acalog_coid_then_a_code_hint(
    url: str, hint: str | None, record_id: str
) -> None:
    assert record_id_for("brookdalecc", url, hint) == record_id


def test_page_id_drops_only_a_course_suffix() -> None:
    assert page_id_for("brookdalecc-engl121-course") == "brookdalecc-engl121"
    assert page_id_for("brookdalecc-link") == "brookdalecc-link"


@pytest.mark.parametrize(
    ("html", "institution"),
    [
        (
            '<meta property="og:site_name" content="  Brookdale   CC ">',
            "Brookdale CC",
        ),
        (
            '<meta name="og:site_name" content="Mercer County CC">',
            "Mercer County CC",
        ),
        (
            "<title>Atlantic Cape Community College Catalog | Home</title>",
            "Atlantic Cape Community College",
        ),
        (
            "<title>Raritan Valley CC - 2026 Catalog</title>",
            "Raritan Valley CC",
        ),
        ("<title>Catalog | Home</title>", "Fallback"),
        ("<title>Courses</title>", "Fallback"),
        # Attribute order matters: content before property is not read.
        (
            '<meta content="Brookdale" property="og:site_name">',
            "Fallback",
        ),
        ("<p>No title</p>", "Fallback"),
    ],
)
def test_institution_comes_from_site_name_then_the_title(
    html: str, institution: str
) -> None:
    assert institution_from_html(html, "Fallback") == institution


def test_a_course_page_title_names_the_course_not_the_college() -> None:
    """Harvest reads the seed page, which is a catalog home, for this."""
    html = "<title>English Composition | Atlantic Cape</title>"
    assert institution_from_html(html, "Fallback") == "English Composition"


@pytest.mark.parametrize(
    ("url", "key"),
    [
        ("https://c.example.edu/courses/ENGL121", "engl"),
        ("https://c.example.edu/english/engl101", "engl"),
        (
            "https://c.example.edu/preview_course_nopop.php?catoid=8&coid=1",
            "acalog",
        ),
        ("https://c.example.edu/courses/123", "123"),
    ],
)
def test_subject_key_buckets_by_subject_prefix(url: str, key: str) -> None:
    assert subject_key(url) == key


def coursedog(*codes: str) -> list[str]:
    return [f"https://c.example.edu/courses/{code}" for code in codes]


def test_sample_urls_round_robins_across_subjects() -> None:
    urls = coursedog("ENGL101", "ENGL102", "ENGL103", "MATH101", "MATH102")
    urls += coursedog("BIOL101")
    assert sample_urls(urls, 4) == coursedog(
        "ENGL101", "MATH101", "BIOL101", "ENGL102"
    )


def test_sample_urls_spreads_an_acalog_listing_evenly() -> None:
    urls = [
        f"https://c.example.edu/preview_course_nopop.php?catoid=8&coid={n}"
        for n in range(10)
    ]
    assert sample_urls(urls, 3) == [urls[0], urls[3], urls[6]]


@pytest.mark.parametrize("limit", [0, -1, 6, 10])
def test_sample_urls_keeps_everything_when_there_is_no_real_limit(
    limit: int,
) -> None:
    urls = coursedog("ENGL101", "ENGL102", "MATH101", "MATH102", "A101", "B101")
    sample = sample_urls(urls, limit)
    assert sample == urls
    assert sample is not urls
