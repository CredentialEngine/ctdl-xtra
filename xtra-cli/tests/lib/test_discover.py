"""The old pack crawler's link harvester: its HTML helpers, and the crawl
itself driven through a fake browser."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from config import BROWSER_USER_AGENT
from crawl_doubles import FakePage
from discover import (
    HarvestError,
    acalog_course_urls,
    acalog_listing_url,
    acalog_max_page,
    clean_course_urls,
    clean_subject_urls,
    coursedog_course_urls,
    harvest_with_playwright,
    hrefs_from_html,
    iter_json_codes,
    make_slot,
    navigation_failure,
)
from lib_doubles import FakeSyncPlaywright
from slots import Slot

ORIGIN = "https://catalog.example.edu"
LISTING = ORIGIN + "/content.php?catoid=8&navoid=9"
Browser = Callable[..., FakeSyncPlaywright]


def links(*hrefs: str) -> str:
    return "".join(f'<a href="{href}">x</a>' for href in hrefs)


def test_a_dns_failure_says_the_host_was_not_found() -> None:
    exc = Exception(
        "net::ERR_NAME_NOT_RESOLVED at https://nope.example.edu/\nCall log:"
    )
    message = navigation_failure("https://nope.example.edu/", exc)
    assert message.startswith("cannot open https://nope.example.edu/: host")
    assert "catalog.brookdalecc.edu" in message


def test_any_other_failure_keeps_only_its_first_line() -> None:
    exc = Exception("Timeout 60000ms exceeded.\n=== logs ===\nnavigating")
    assert navigation_failure("https://c.example.edu", exc) == (
        "cannot open https://c.example.edu: Timeout 60000ms exceeded."
    )


def test_json_codes_come_from_printed_code_fields_only() -> None:
    payload = {
        "data": [
            {
                "id": "LJdUL84T",
                "code": " ENGL121 ",
                "courseId": "ENGL-121",
                "displayName": "English Composition",
            },
            {"code": "MATH 101", "nested": [{"courseId": "bio_110"}]},
        ]
    }
    found: list[str] = []
    iter_json_codes(payload, found)
    assert found == ["ENGL121", "ENGL-121", "bio_110"]


def test_hrefs_resolve_and_skip_scripts_mail_and_anything_with_a_fragment() -> (
    None
):
    html = links(
        "/courses/ENGL121",
        "javascript:void(0)",
        "mailto:registrar@example.edu",
        "#top",
        "/courses/ENGL122#prereqs",
        "https://other.example.org/a",
    )
    assert hrefs_from_html(html, ORIGIN + "/courses") == [
        ORIGIN + "/courses/ENGL121",
        "https://other.example.org/a",
    ]


def test_acalog_listing_prefers_the_courses_a_to_z_link() -> None:
    html = (
        '<a href="content.php?catoid=8&navoid=1">Programs</a>'
        + "." * 300
        + '<a href="content.php?catoid=8&navoid=9">Courses (A-Z)</a>'
    )
    assert acalog_listing_url(html, ORIGIN + "/index.php") == (
        ORIGIN + "/content.php?catoid=8&navoid=9"
    )


def test_acalog_listing_skips_a_by_discipline_courses_link() -> None:
    html = (
        '<a href="content.php?catoid=8&navoid=10">Courses</a> by discipline'
        + "." * 300
        + '<a href="content.php?catoid=8&navoid=9">Courses</a>'
    )
    assert acalog_listing_url(html, ORIGIN + "/index.php") == (
        ORIGIN + "/content.php?catoid=8&navoid=9"
    )


def test_acalog_listing_falls_back_to_an_escaped_courses_link() -> None:
    html = (
        '<a href="/content.php?catoid=8&amp;navoid=9" class="x">  Courses</a>'
    )
    assert acalog_listing_url(html, ORIGIN + "/index.php") == (
        ORIGIN + "/content.php?catoid=8&navoid=9"
    )


def test_acalog_listing_is_the_page_itself_when_it_is_a_listing() -> None:
    page = ORIGIN + "/content.php?catoid=8&navoid=9"
    assert acalog_listing_url("<p>no links</p>", page) == page
    assert acalog_listing_url("<p>no links</p>", ORIGIN + "/index.php") is None


def test_acalog_course_links_are_unescaped_normalized_and_deduplicated() -> (
    None
):
    html = (
        '<a href="preview_course_nopop.php?catoid=8&amp;coid=12">ENG 101</a>'
        "<a href='preview_course.php?catoid=8&coid=13&returnto=99'>ENG 102</a>"
        '<a href="preview_course_nopop.php?catoid=8&amp;coid=12">again</a>'
    )
    assert acalog_course_urls(html, ORIGIN + "/content.php?catoid=8") == [
        ORIGIN + "/preview_course_nopop.php?catoid=8&coid=12",
        ORIGIN + "/preview_course_nopop.php?catoid=8&coid=13",
    ]


@pytest.mark.parametrize(
    ("html", "last"),
    [
        ("filter[cpage]=2 filter%5Bcpage%5D=5 Page 1 of 7", 7),
        ("filter[cpage]=3", 3),
        ("<p>one page</p>", 1),
    ],
)
def test_acalog_max_page_reads_every_pager_style(html: str, last: int) -> None:
    assert acalog_max_page(html) == last


def test_clean_catalog_course_links_stay_on_the_catalog_host() -> None:
    html = links(
        "/english/engl101",
        "/english/engl102/",
        "https://other.example.org/english/engl103",
        "/english",
        "/english/engl101",
    )
    assert clean_course_urls(html, ORIGIN + "/english") == [
        ORIGIN + "/english/engl101",
        ORIGIN + "/english/engl102",
    ]


def test_clean_catalog_subject_pages_skip_site_sections() -> None:
    html = links(
        "/english",
        "/math-science",
        "/login",
        "/courses",
        "/english/engl101",
        "/ab",
        "/English",
        "https://other.example.org/history",
    )
    assert clean_subject_urls(html, ORIGIN + "/") == [
        ORIGIN + "/english",
        ORIGIN + "/math-science",
    ]


def test_coursedog_course_links_skip_document_ids_and_other_hosts() -> None:
    html = links(
        "/courses/ENGL121",
        "/courses/LJdUL84T",
        "/courses/ENGL121?tab=1",
        "https://other.example.org/courses/MATH101",
    )
    assert coursedog_course_urls(html, ORIGIN + "/courses") == [
        ORIGIN + "/courses/ENGL121"
    ]


def test_make_slot_queues_one_course_page_under_its_family() -> None:
    url = "https://catalog.brookdalecc.edu/courses/ENGL121"
    slot = make_slot(
        url, institution="Brookdale", family="coursedog", template_id=""
    )
    assert slot == Slot(
        "brookdalecc-engl121-course",
        "Course",
        url,
        "Brookdale",
        "coursedog",
        "coursedog",
        "1",
        "brookdalecc-engl121",
        None,
        None,
    )


# --- the crawl itself, through a fake browser ---------------------------------


def acalog_listing(*coids: int, pages: int = 0) -> str:
    rows = "".join(
        f'<a href="preview_course_nopop.php?catoid=8&amp;coid={coid}">c</a>'
        for coid in coids
    )
    pager = f"Page 1 of {pages}" if pages else ""
    return f"<p>Acalog ACMS</p>{rows}{pager}"


def urls_of(report: dict) -> list[str]:
    return [slot.requested_url for slot in report["slots"]]


def test_a_course_page_seed_is_harvested_as_itself(
    fake_browser: Browser,
) -> None:
    seed = "https://catalog.brookdalecc.edu/courses/ENGL121/"
    browser = fake_browser({seed: FakePage(html="<p>English Composition</p>")})
    report = harvest_with_playwright(seed, want=5, fetch_all=False)
    assert urls_of(report) == [
        "https://catalog.brookdalecc.edu/courses/ENGL121"
    ]
    assert report["family"] == "coursedog"
    assert report["institution_name"] == "Brookdalecc"
    assert (report["discovered"], report["kept"], report["sample"]) == (
        1,
        1,
        True,
    )
    assert browser.contexts[0]["user_agent"] == BROWSER_USER_AGENT
    assert browser.closed == ["browser"]


def test_an_acalog_catalog_is_walked_from_its_a_to_z_listing(
    fake_browser: Browser,
) -> None:
    home = ORIGIN + "/index.php"
    pages = {
        home: FakePage(
            html='acalog <a href="content.php?catoid=8&navoid=9">Courses (A-Z)</a>'
        ),
        LISTING: FakePage(html=acalog_listing(1, 2, pages=3)),
        f"{LISTING}&filter[cpage]=2": FakePage(html=acalog_listing(20)),
        f"{LISTING}&filter[cpage]=3": FakePage(html=acalog_listing(30)),
    }
    browser = fake_browser(pages)
    report = harvest_with_playwright(home, want=5, fetch_all=True)
    assert [url for url, _ in browser.gotos] == list(pages)
    assert urls_of(report) == [
        f"{ORIGIN}/preview_course_nopop.php?catoid=8&coid={coid}"
        for coid in (1, 2, 20, 30)
    ]
    assert report["family"] == "acalog"
    assert report["sample"] is False


def test_without_fetch_all_at_most_eight_listing_pages_are_read(
    fake_browser: Browser,
) -> None:
    browser = fake_browser(
        {LISTING: FakePage(html=acalog_listing(1, pages=12))}
    )
    harvest_with_playwright(LISTING, want=5, fetch_all=False)
    assert [url for url, _ in browser.gotos] == [LISTING] + [
        f"{LISTING}&filter[cpage]={n}" for n in range(2, 9)
    ]


def test_a_clean_catalog_home_is_walked_one_subject_at_a_time(
    fake_browser: Browser,
) -> None:
    home = ORIGIN + "/"
    browser = fake_browser(
        {
            home: FakePage(
                html="Software by cleancatalog.com"
                + links("/english", "/math", "/english/engl101")
            ),
            ORIGIN + "/english": FakePage(html=links("/english/engl102")),
            ORIGIN + "/math": FakePage(html=links("/math/math101")),
        }
    )
    report = harvest_with_playwright(home, want=5, fetch_all=True)
    assert [url for url, _ in browser.gotos] == [
        home,
        ORIGIN + "/english",
        ORIGIN + "/math",
    ]
    assert urls_of(report) == [
        ORIGIN + "/english/engl101",
        ORIGIN + "/english/engl102",
        ORIGIN + "/math/math101",
    ]
    assert report["family"] == "custom_html"


def test_coursedog_courses_come_from_links_json_codes_and_next_pages(
    fake_browser: Browser,
) -> None:
    """A JSON body the page cannot read must not stop the crawl."""
    courses = ORIGIN + "/courses"
    browser = fake_browser(
        {
            ORIGIN + "/": FakePage(
                html="<script src='/coursedog.js'></script>"
            ),
            courses: FakePage(html=links("/courses/ENGL121")),
        },
        json_responses={
            courses: [
                {"data": [{"id": "LJdUL84T", "code": "MATH101"}]},
                ValueError("not json after all"),
            ]
        },
        next_pages=[links("/courses/BIOL110")],
    )
    report = harvest_with_playwright(ORIGIN + "/", want=5, fetch_all=False)
    assert sorted(urls_of(report)) == [
        courses + "/BIOL110",
        courses + "/ENGL121",
        courses + "/MATH101",
    ]
    assert browser.wheels == 7


def test_an_unknown_catalog_tries_every_link_pattern(
    fake_browser: Browser,
) -> None:
    """The family is then taken from the first course URL kept."""
    fake_browser(
        {
            ORIGIN + "/": FakePage(
                html=links("/courses/ENGL121", "/english/engl101")
            )
        }
    )
    report = harvest_with_playwright(ORIGIN + "/", want=5, fetch_all=True)
    assert urls_of(report) == [
        ORIGIN + "/courses/ENGL121",
        ORIGIN + "/english/engl101",
    ]
    assert report["family"] == "coursedog"
    assert {slot.source_family for slot in report["slots"]} == {"coursedog"}


def test_a_seed_that_does_not_resolve_raises_harvest_error(
    fake_browser: Browser,
) -> None:
    seed = "https://nope.example.edu/"
    fake_browser(
        {seed: FakePage(raises=f"net::ERR_NAME_NOT_RESOLVED at {seed}")}
    )
    with pytest.raises(HarvestError, match="host not found"):
        harvest_with_playwright(seed, want=5, fetch_all=False)


def test_every_navigation_is_paced_and_retried_after_a_load_timeout(
    fake_browser: Browser,
) -> None:
    seed = "https://catalog.brookdalecc.edu/courses/ENGL121"
    browser = fake_browser(
        {seed: [FakePage(raises="Timeout 60000ms exceeded."), FakePage()]},
        chrome_missing=True,
        content_errors=2,
    )
    paced: list[int] = []
    harvest_with_playwright(
        seed, want=5, fetch_all=False, between_pages=lambda: paced.append(1)
    )
    assert paced == [1]
    assert browser.gotos == [(seed, "load"), (seed, "domcontentloaded")]
    assert [launch.get("channel") for launch in browser.launches] == [
        "chrome",
        None,
    ]


def test_a_page_whose_content_never_settles_is_a_harvest_error(
    fake_browser: Browser,
) -> None:
    seed = "https://catalog.brookdalecc.edu/courses/ENGL121"
    fake_browser({seed: FakePage()}, content_errors=3)
    with pytest.raises(HarvestError, match="Execution context was destroyed"):
        harvest_with_playwright(seed, want=5, fetch_all=False)
