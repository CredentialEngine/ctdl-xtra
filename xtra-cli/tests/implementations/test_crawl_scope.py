from __future__ import annotations

from urllib.robotparser import RobotFileParser

import pytest

from implementations.crawl_scope import (
    QUIET_REASONS,
    REASON_DUPLICATE,
    REASON_EXCLUDE_RULE,
    REASON_EXTENSION,
    REASON_INCLUDE_RULE,
    REASON_NON_HTML,
    REASON_OUT_OF_SCOPE,
    REASON_ROBOTS,
    REASON_SCHEME,
    Scope,
    content_type_is_html,
    directory_of,
    extension_of,
    extract_links,
    first_path_segment,
)

SEED = "https://catalog.example.edu/courses/index.html"


@pytest.mark.parametrize(
    ("path", "directory"),
    [
        ("/courses/index.html", "/courses/"),
        ("/courses/", "/courses/"),
        ("/index.html", "/"),
        ("/courses", "/"),
        ("", "/"),
    ],
)
def test_directory_of(path: str, directory: str) -> None:
    assert directory_of(path) == directory


def test_the_default_scope_is_the_directory_of_the_seed() -> None:
    scope = Scope.from_seed(SEED)
    assert scope.host == "catalog.example.edu"
    assert scope.path_prefix == "/courses/"
    assert scope.allows("https://catalog.example.edu/courses/engl101")
    assert scope.rejection("https://catalog.example.edu/about") == (
        REASON_OUT_OF_SCOPE
    )


def test_a_whole_host_is_in_scope_when_the_seed_is_the_home_page() -> None:
    scope = Scope.from_seed("https://catalog.example.edu")
    assert scope.path_prefix == "/"
    assert scope.allows("https://catalog.example.edu/anything/at/all")


def test_scope_prefix_overrides_the_default_path() -> None:
    scope = Scope.from_seed(
        "https://catalog.example.edu/",
        scope_prefix="https://catalog.example.edu/programs/",
    )
    assert scope.path_prefix == "/programs/"
    assert scope.allows("https://catalog.example.edu/programs/nursing")
    assert not scope.allows("https://catalog.example.edu/courses/engl101")


def test_http_and_https_are_the_same_site() -> None:
    scope = Scope.from_seed("https://catalog.example.edu/")
    assert scope.allows("http://catalog.example.edu/a")
    assert scope.allows("https://catalog.example.edu/a")


def test_another_host_and_a_non_web_scheme_are_out() -> None:
    scope = Scope.from_seed("https://catalog.example.edu/")
    assert scope.rejection("https://other.edu/a") == REASON_OUT_OF_SCOPE
    assert scope.rejection("mailto:registrar@example.edu") == REASON_SCHEME
    assert scope.rejection("javascript:void(0)") == REASON_SCHEME


@pytest.mark.parametrize(
    "url",
    [
        "https://catalog.example.edu/catalog.pdf",
        "https://catalog.example.edu/a/plan.XLSX",
        "https://catalog.example.edu/assets/site.css",
        "https://catalog.example.edu/assets/app.js",
        "https://catalog.example.edu/feed.xml",
        "https://catalog.example.edu/logo.png",
    ],
)
def test_downloadable_extensions_are_skipped(url: str) -> None:
    scope = Scope.from_seed("https://catalog.example.edu/")
    assert scope.rejection(url) == REASON_EXTENSION


def test_include_and_exclude_regexes_apply_to_the_whole_url() -> None:
    scope = Scope.from_seed(
        "https://catalog.bergen.edu/",
        include_regex=("catoid=13",),
        exclude_regex=("print=1",),
    )
    assert scope.allows("https://catalog.bergen.edu/content.php?catoid=13&n=1")
    assert scope.rejection(
        "https://catalog.bergen.edu/content.php?catoid=12"
    ) == (REASON_INCLUDE_RULE)
    assert (
        scope.rejection(
            "https://catalog.bergen.edu/content.php?catoid=13&print=1"
        )
        == REASON_EXCLUDE_RULE
    )


def test_robots_disallow_is_honoured() -> None:
    robots = RobotFileParser()
    robots.parse(["User-agent: *", "Disallow: /private/"])
    scope = Scope.from_seed("https://catalog.example.edu/").with_robots(robots)
    assert (
        scope.rejection("https://catalog.example.edu/private/x")
        == REASON_ROBOTS
    )
    assert scope.allows("https://catalog.example.edu/public/x")


def test_extension_of_and_first_path_segment() -> None:
    assert extension_of("/a/b.PDF") == "pdf"
    assert extension_of("/a/b") == ""
    assert extension_of("/") == ""
    assert first_path_segment("https://x.edu/courses/engl101") == "courses"
    assert first_path_segment("https://x.edu/") == "(root)"


def test_content_type_is_html() -> None:
    assert content_type_is_html("text/html; charset=utf-8")
    assert content_type_is_html("application/xhtml+xml")
    assert not content_type_is_html("application/pdf")
    assert not content_type_is_html("")


def test_links_come_from_anchors_areas_and_rel_next() -> None:
    html = """
    <a href="/courses/engl101">ENGL</a>
    <area href="math101">MATH</area>
    <link rel="next" href="?page=2">
    <link rel="stylesheet" href="/site.css">
    <a href="mailto:x@y.z">mail</a>
    <a>no href</a>
    """
    links = extract_links(
        html, "https://catalog.example.edu/courses/index.html"
    )
    assert links == [
        "https://catalog.example.edu/courses/engl101",
        "https://catalog.example.edu/courses/math101",
        "https://catalog.example.edu/courses/index.html?page=2",
        "mailto:x@y.z",
    ]


def test_a_base_href_decides_where_relative_links_point() -> None:
    """Including the fragment-only link, which resolves against the base."""
    html = (
        '<base href="https://catalog.example.edu/v2/">'
        '<a href="a">A</a><a href="#top">T</a>'
    )
    links = extract_links(
        html, "https://catalog.example.edu/courses/index.html"
    )
    assert links == [
        "https://catalog.example.edu/v2/a",
        "https://catalog.example.edu/v2/",
    ]


def test_a_fragment_link_without_a_base_is_the_page_itself() -> None:
    links = extract_links(
        '<a href="#top">T</a>', "https://catalog.example.edu/courses/index.html"
    )
    assert links == ["https://catalog.example.edu/courses/index.html"]


def test_the_same_link_twice_is_returned_once() -> None:
    html = '<a href="/a">one</a><a href="/a#x">two</a>'
    assert extract_links(html, "https://catalog.example.edu/") == [
        "https://catalog.example.edu/a"
    ]


def test_only_scope_decisions_are_quiet() -> None:
    """Surprises stay at INFO so an operator sees them without a rerun."""
    assert REASON_OUT_OF_SCOPE in QUIET_REASONS
    assert REASON_DUPLICATE in QUIET_REASONS
    assert REASON_ROBOTS not in QUIET_REASONS
    assert REASON_NON_HTML not in QUIET_REASONS
