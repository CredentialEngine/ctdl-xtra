from __future__ import annotations

import itertools
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from crawl_doubles import FakePage, fetcher_factory, list_page, site_documents

from common.clock import utc_timestamp
from common.keys import (
    crawl_key,
    navigation_key,
    page_html_key,
    page_meta_key,
    page_stem,
)
from common.object_store import open_store
from implementations.crawl import CrawlSettings, run_crawl
from implementations.crawl_list_pages import page_url
from implementations.crawl_navigation import (
    ALREADY_FOUND,
    BLOCKED_BY_ROBOTS,
    FILE,
    FOUND_BY_LINK,
    FOUND_BY_NOT_A_LINK,
    FOUND_BY_PAGE_BUTTON,
    FOUND_BY_SEED_FILE,
    FOUND_BY_START_URL,
    LEFT_OUT_BY_EXCLUDE_REGEX,
    LEFT_OUT_BY_INCLUDE_REGEX,
    NAVIGATION_SCHEMA,
    NEW,
    NOT_A_WEB_PAGE,
    OUTSIDE_SCOPE,
    STATUS_FAILED,
    STATUS_NOT_VISITED,
    STATUS_SAVED,
    STATUS_SKIPPED,
    NavigationError,
    build_navigation,
)

SITE = "https://catalog.example.edu"
SEED = f"{SITE}/"
COURSES = f"{SITE}/courses"
PROGRAMS = f"{SITE}/programs"
ENGL = f"{SITE}/courses/engl101"
FOLDER = "catalog-example-edu"
RUN = "2026-09-17T14:20:01Z"
NEXT = "2026-09-18T09:00:00Z"
ROBOTS = f"{SITE}/robots.txt"
SITEMAP = f"{SITE}/sitemap.xml"


def links(*pairs: tuple[str, str]) -> FakePage:
    return FakePage(
        html="".join(f'<a href="{href}">{text}</a>' for href, text in pairs)
    )


def ticking(step_seconds: int):
    """A clock that moves on by step_seconds each time it is read."""
    start = datetime(2026, 9, 17, 14, 20, 1, tzinfo=timezone.utc)
    reads = itertools.count()

    def now() -> str:
        return utc_timestamp(
            start + timedelta(seconds=next(reads) * step_seconds)
        )

    return now


def crawled(
    tmp_path: Path,
    pages: dict,
    *,
    documents: dict | None = None,
    resolve_url=None,
    run_id: str = RUN,
    step_seconds: int = 7,
    **settings,
):
    """One crawl into tmp_path with a fake browser, then its store."""
    settings.setdefault("min_interval_in_seconds", 0)
    settings.setdefault("max_interval_in_seconds", 1)
    settings.setdefault("pacing_jitter_fraction", 0)
    store = open_store(str(tmp_path))
    run_crawl(
        CrawlSettings(
            seed_url=settings.pop("seed_url", SEED),
            catalog_folder=FOLDER,
            run_id=run_id,
            target_uri=str(tmp_path),
            **settings,
        ),
        store=store,
        fetcher_factory=fetcher_factory(pages),
        url_fetch=site_documents(documents or {}),
        resolve_url=resolve_url or (lambda url: url),
        sleep=lambda seconds: None,
        now=ticking(step_seconds),
    )
    return store


def mapped(store, run_id: str = RUN, **kwargs) -> dict:
    _, doc = build_navigation(store, FOLDER, run_id, **kwargs)
    return doc


def by_url(doc: dict) -> dict[str, dict]:
    return {entry["url"]: entry for entry in doc["urls"]}


def skipped(entry: dict) -> dict[str, str]:
    return {
        target["url"]: target["result"]
        for target in entry.get("skipped_targets", [])
    }


HOME = links((COURSES, "Courses"), (PROGRAMS, "Programs"))
SITE_PAGES = {
    SEED: HOME,
    COURSES: links((ENGL, "ENGL 101"), (PROGRAMS, "Programs")),
    PROGRAMS: links((ENGL, "ENGL 101")),
    ENGL: FakePage(html="<h1>ENGL 101</h1>"),
}


def test_each_url_names_the_source_that_first_linked_to_it(
    tmp_path: Path,
) -> None:
    doc = mapped(crawled(tmp_path, SITE_PAGES))
    pages = by_url(doc)
    assert doc["schema"] == NAVIGATION_SCHEMA
    assert pages[SEED]["found_by"] == FOUND_BY_START_URL
    assert pages[SEED]["clicks"] == 0
    assert "source_url" not in pages[SEED]
    assert pages[SEED]["new_targets"] == [COURSES, PROGRAMS]
    assert pages[COURSES]["source_url"] == SEED
    assert pages[PROGRAMS]["source_url"] == SEED
    assert pages[ENGL]["source_url"] == COURSES
    assert pages[ENGL]["found_by"] == FOUND_BY_LINK
    assert pages[ENGL]["clicks"] == 2
    assert pages[ENGL]["link_text"] == "ENGL 101"


def test_the_file_speaks_of_urls_sources_and_targets(tmp_path: Path) -> None:
    """One vocabulary: a source URL links to target URLs."""
    doc = mapped(crawled(tmp_path, SITE_PAGES))
    assert set(doc["totals"]) == {
        "urls",
        "urls_by_status",
        "urls_by_found_by",
        "links_by_result",
    }
    allowed = {
        "url",
        "found_by",
        "source_url",
        "link_text",
        "clicks",
        "status",
        "http_status",
        "copied_from_run",
        "error",
        "retryable",
        "reason",
        "final_url",
        "redirected_to",
        "target_links",
        "page_button_targets",
        "source_count",
        "new_targets",
        "skipped_targets",
    }
    for entry in doc["urls"]:
        assert set(entry) <= allowed, set(entry) - allowed
    assert "pages" not in doc


def test_a_url_counts_the_sources_that_link_to_it(tmp_path: Path) -> None:
    pages = by_url(mapped(crawled(tmp_path, SITE_PAGES)))
    assert pages[ENGL]["source_count"] == 2
    assert pages[PROGRAMS]["source_count"] == 2
    assert pages[SEED]["source_count"] == 0


def test_the_totals_count_urls_and_links(tmp_path: Path) -> None:
    totals = mapped(crawled(tmp_path, SITE_PAGES))["totals"]
    assert totals["urls"] == 4
    assert totals["urls_by_status"] == {STATUS_SAVED: 4}
    assert totals["urls_by_found_by"] == {
        FOUND_BY_START_URL: 1,
        FOUND_BY_LINK: 3,
    }
    assert totals["links_by_result"] == {NEW: 3, ALREADY_FOUND: 2}


def test_link_text_is_what_a_reader_sees(tmp_path: Path) -> None:
    pages = {
        SEED: FakePage(
            html=f'<a href="{ENGL}"><img alt="Book"> ENGL\n <b>101</b></a>'
        ),
        ENGL: FakePage(html="<h1>ENGL 101</h1>"),
    }
    entry = by_url(mapped(crawled(tmp_path, pages)))[ENGL]
    assert entry["link_text"] == "Book ENGL 101"


def test_each_source_lists_the_targets_it_left_out_and_why(
    tmp_path: Path,
) -> None:
    left_out = (
        ("mailto:help@example.edu", "Email"),
        (f"{SITE}/handbook.pdf", "Handbook"),
        (f"{SITE}/print/courses", "Print"),
    )
    pages = {
        SEED: links((COURSES, "Courses"), *left_out),
        COURSES: links(*left_out),
    }
    doc = mapped(crawled(tmp_path, pages, exclude_regex=(r"/print/",)))
    expected = {
        "mailto:help@example.edu": NOT_A_WEB_PAGE,
        f"{SITE}/handbook.pdf": FILE,
        f"{SITE}/print/courses": LEFT_OUT_BY_EXCLUDE_REGEX,
    }
    entries = by_url(doc)
    assert skipped(entries[SEED]) == expected
    # Listed on every page that has it, not only the first.
    assert skipped(entries[COURSES]) == expected
    assert entries[SEED]["skipped_targets"][0]["link_text"] == "Email"


def test_links_outside_the_scope_prefix_and_the_include_regex(
    tmp_path: Path,
) -> None:
    seed = f"{SITE}/catalog/"
    pages = {
        seed: links(
            (f"{SITE}/about/", "About"),
            (f"{SITE}/catalog/courses", "Courses"),
            (f"{SITE}/catalog/news", "News"),
        ),
        f"{SITE}/catalog/courses": FakePage(html="<p>courses</p>"),
    }
    store = crawled(
        tmp_path, pages, seed_url=seed, include_regex=(r"/courses",)
    )
    assert skipped(by_url(mapped(store))[seed]) == {
        f"{SITE}/about/": OUTSIDE_SCOPE,
        f"{SITE}/catalog/news": LEFT_OUT_BY_INCLUDE_REGEX,
    }


def test_links_to_other_websites_are_counted_once_per_host(
    tmp_path: Path,
) -> None:
    facebook = ("https://www.facebook.com/college", "Facebook")
    pages = {
        SEED: links((COURSES, "Courses"), facebook),
        COURSES: links(facebook, ("https://www.facebook.com/other", "FB")),
    }
    doc = mapped(crawled(tmp_path, pages))
    assert doc["other_websites"] == [
        {
            "host": "www.facebook.com",
            "links": 3,
            "sources": 2,
            "first_source_url": SEED,
            "first_target_url": "https://www.facebook.com/college",
        }
    ]
    assert "skipped_targets" not in by_url(doc)[SEED]


ROBOTS_RULES = {ROBOTS: b"User-agent: *\nDisallow: /private/\n"}


def test_a_link_robots_txt_refused_is_marked_when_the_run_finished(
    tmp_path: Path,
) -> None:
    pages = {SEED: links((f"{SITE}/private/staff", "Staff"))}
    doc = mapped(crawled(tmp_path, pages, documents=ROBOTS_RULES))
    entries = by_url(doc)
    assert skipped(entries[SEED]) == {
        f"{SITE}/private/staff": BLOCKED_BY_ROBOTS
    }
    assert f"{SITE}/private/staff" not in entries
    assert any("robots.txt is not saved" in note for note in doc["notes"])


def test_a_run_that_stopped_early_cannot_tell_robots_from_waiting(
    tmp_path: Path,
) -> None:
    pages = {SEED: links((f"{SITE}/private/staff", "Staff"), (COURSES, "C"))}
    store = crawled(tmp_path, pages, documents=ROBOTS_RULES, limit=1)
    doc = mapped(store)
    entries = by_url(doc)
    assert entries[f"{SITE}/private/staff"]["status"] == STATUS_NOT_VISITED
    assert entries[COURSES]["status"] == STATUS_NOT_VISITED
    assert any("can't tell" in note for note in doc["notes"])


def test_without_robots_rules_nothing_is_blamed_on_robots(
    tmp_path: Path,
) -> None:
    pages = {SEED: links((COURSES, "Courses"))}
    doc = mapped(crawled(tmp_path, pages, limit=1))
    assert by_url(doc)[COURSES]["status"] == STATUS_NOT_VISITED
    note = next(n for n in doc["notes"] if STATUS_NOT_VISITED in n)
    assert "robots" not in note


def test_failed_and_skipped_pages_carry_what_their_record_says(
    tmp_path: Path,
) -> None:
    gone = f"{SITE}/gone"
    pdf = f"{SITE}/download"
    leaves = f"{SITE}/leaves"
    pages = {
        SEED: links((gone, "Gone"), (pdf, "Download"), (leaves, "Leaves")),
        gone: FakePage(status=404, html=""),
        pdf: FakePage(content_type="application/pdf", html="%PDF"),
        leaves: FakePage(final_url="https://elsewhere.example.org/x"),
    }
    entries = by_url(mapped(crawled(tmp_path, pages)))
    assert entries[gone]["status"] == STATUS_FAILED
    assert entries[gone]["http_status"] == 404
    assert entries[gone]["error"] == "HTTP 404"
    assert entries[gone]["retryable"] is False
    assert entries[pdf]["status"] == STATUS_SKIPPED
    assert entries[pdf]["reason"] == "non_html"
    assert entries[leaves]["status"] == STATUS_SKIPPED
    assert entries[leaves]["reason"] == "redirect_out_of_scope"
    assert entries[leaves]["final_url"] == "https://elsewhere.example.org/x"
    assert entries[gone]["source_url"] == SEED


def test_a_redirect_is_shown_and_where_it_landed_counts_as_found(
    tmp_path: Path,
) -> None:
    old = f"{SITE}/old"
    new = f"{SITE}/new"
    pages = {
        SEED: links((old, "Old"), (COURSES, "Courses")),
        old: FakePage(final_url=new),
        COURSES: links((new, "New")),
    }
    entries = by_url(mapped(crawled(tmp_path, pages)))
    assert entries[old]["redirected_to"] == new
    assert new not in entries


def test_a_page_only_the_sitemap_listed_is_not_from_a_link(
    tmp_path: Path,
) -> None:
    hidden = f"{SITE}/hidden"
    documents = {
        SITEMAP: (
            b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            b"<url><loc>https://catalog.example.edu/hidden</loc></url>"
            b"</urlset>"
        )
    }
    pages = {SEED: FakePage(html="<p>home</p>"), hidden: links((ENGL, "E"))}
    doc = mapped(crawled(tmp_path, pages, documents=documents))
    entries = by_url(doc)
    assert entries[hidden]["found_by"] == FOUND_BY_NOT_A_LINK
    assert entries[hidden]["clicks"] == 0
    assert entries[ENGL]["source_url"] == hidden
    assert any("listed 1 pages" in note for note in doc["notes"])


def test_a_seed_file_page_starts_a_branch_of_its_own(tmp_path: Path) -> None:
    extra = f"{SITE}/extra"
    pages = {SEED: FakePage(html="<p>home</p>"), extra: links((ENGL, "E"))}
    entries = by_url(mapped(crawled(tmp_path, pages, seed_urls=(extra,))))
    assert entries[extra]["found_by"] == FOUND_BY_SEED_FILE
    assert entries[ENGL]["source_url"] == extra


def test_the_next_page_of_a_list_is_found_by_its_page_button(
    tmp_path: Path,
) -> None:
    second = page_url(COURSES, 2)
    pages = {
        SEED: links((COURSES, "Courses")),
        COURSES: FakePage(html=list_page(1, 3, ["engl101"])),
        second: FakePage(html=list_page(2, 3, ["math101"])),
    }
    entries = by_url(mapped(crawled(tmp_path, pages)))
    assert entries[second]["found_by"] == FOUND_BY_PAGE_BUTTON
    assert entries[second]["source_url"] == COURSES
    assert entries[second]["link_text"] == "page 2"
    assert entries[COURSES]["page_button_targets"] == 1


def test_a_run_that_copied_its_pages_maps_the_same_way(tmp_path: Path) -> None:
    crawled(tmp_path, SITE_PAGES)
    store = crawled(tmp_path, SITE_PAGES, run_id=NEXT, from_run_id=RUN)
    first = by_url(mapped(store, RUN))
    copied = by_url(mapped(store, NEXT))
    assert copied[ENGL]["copied_from_run"] == RUN
    for url, entry in first.items():
        assert copied[url].get("source_url") == entry.get("source_url")


def test_links_to_the_typed_host_land_on_the_host_that_answered(
    tmp_path: Path,
) -> None:
    answers = "https://catalog.newname.edu/"
    pages = {
        answers: links(("https://catalog.oldname.edu/courses", "Courses")),
        "https://catalog.newname.edu/courses": FakePage(html="<p>c</p>"),
    }
    store = crawled(
        tmp_path,
        pages,
        seed_url="https://catalog.oldname.edu",
        resolve_url=lambda url: answers,
    )
    doc = mapped(store)
    entries = by_url(doc)
    assert (
        entries["https://catalog.newname.edu/courses"]["source_url"] == answers
    )
    assert doc["crawl"]["scope_host"] == "catalog.newname.edu"


def test_a_target_saved_in_the_same_second_as_its_source_keeps_it(
    tmp_path: Path,
) -> None:
    """Same-second pages are taken in URL order; /a sorts before /b."""
    a = f"{SITE}/a"
    b = f"{SITE}/b"
    pages = {SEED: links((b, "B")), b: links((a, "A")), a: FakePage()}
    doc = mapped(crawled(tmp_path, pages, step_seconds=0))
    assert by_url(doc)[a]["source_url"] == b
    assert any("share the second" in note for note in doc["notes"])


def test_urls_that_link_to_each_other_are_never_each_others_source(
    tmp_path: Path,
) -> None:
    x = f"{SITE}/x"
    y = f"{SITE}/y"
    documents = {
        SITEMAP: (
            b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            b"<url><loc>https://catalog.example.edu/x</loc></url>"
            b"<url><loc>https://catalog.example.edu/y</loc></url>"
            b"</urlset>"
        )
    }
    pages = {SEED: FakePage(), x: links((y, "Y")), y: links((x, "X"))}
    entries = by_url(
        mapped(crawled(tmp_path, pages, documents=documents, step_seconds=0))
    )
    assert entries[y]["source_url"] == x
    assert "source_url" not in entries[x]
    assert entries[y]["clicks"] == 1


def test_the_file_is_written_beside_crawl_json(tmp_path: Path) -> None:
    store = crawled(tmp_path, SITE_PAGES)
    key, doc = build_navigation(store, FOLDER, RUN)
    assert key == navigation_key(FOLDER, RUN)
    assert key.rsplit("/", 1)[0] == crawl_key(FOLDER, RUN).rsplit("/", 1)[0]
    assert store.get_json(key) == json.loads(json.dumps(doc))


def test_a_second_build_needs_force(tmp_path: Path) -> None:
    store = crawled(tmp_path, SITE_PAGES)
    mapped(store, now=lambda: "2026-09-20T00:00:00Z")
    with pytest.raises(NavigationError, match="--force"):
        mapped(store)
    mapped(store, force=True, now=lambda: "2026-09-21T00:00:00Z")
    stored = store.get_json(navigation_key(FOLDER, RUN))
    assert isinstance(stored, dict)
    assert stored["built_at"] == "2026-09-21T00:00:00Z"


def test_a_run_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    with pytest.raises(NavigationError, match="crawl status"):
        mapped(open_store(str(tmp_path)))


def test_a_broken_page_record_is_noted_and_the_rest_is_mapped(
    tmp_path: Path,
) -> None:
    pages = {
        SEED: links((COURSES, "Courses"), (f"{SITE}/private/x", "P")),
        COURSES: FakePage(),
    }
    store = crawled(tmp_path, pages, documents=ROBOTS_RULES)
    meta = tmp_path / page_meta_key(FOLDER, RUN, page_stem(COURSES))
    meta.write_text("{broken", encoding="utf-8")
    doc = mapped(store)
    entries = by_url(doc)
    assert entries[COURSES]["status"] == STATUS_NOT_VISITED
    # An unreadable record could be any URL, so robots.txt is not blamed.
    assert entries[f"{SITE}/private/x"]["status"] == STATUS_NOT_VISITED
    assert any("could not be read" in note for note in doc["notes"])


def test_a_saved_page_that_cannot_be_read_keeps_its_place(
    tmp_path: Path,
) -> None:
    store = crawled(tmp_path, SITE_PAGES)
    (tmp_path / page_html_key(FOLDER, RUN, page_stem(COURSES))).unlink()
    doc = mapped(store)
    entries = by_url(doc)
    assert entries[COURSES]["status"] == STATUS_SAVED
    assert "target_links" not in entries[COURSES]
    # ENGL is still found, through the programs page.
    assert entries[ENGL]["source_url"] == PROGRAMS
    assert any("saved pages could not be read" in n for n in doc["notes"])


def test_a_run_killed_before_crawl_json_is_mapped_from_its_manifest(
    tmp_path: Path,
) -> None:
    store = crawled(tmp_path, SITE_PAGES)
    (tmp_path / crawl_key(FOLDER, RUN)).unlink()
    doc = mapped(store)
    assert by_url(doc)[ENGL]["source_url"] == COURSES
    assert doc["crawl"]["status"] == ""
    assert any("no crawl.json" in note for note in doc["notes"])
