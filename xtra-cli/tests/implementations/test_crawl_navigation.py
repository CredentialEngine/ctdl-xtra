from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path

import pytest
from crawl_doubles import FakePage, fetcher_factory, site_documents

from common.keys import page_stem
from common.object_store import open_store
from implementations.crawl import CrawlSettings, run_crawl
from implementations.crawl_navigation import (
    MAX_NESTED_CLICKS,
    NavigationError,
    build_navigation,
)

SEED = "https://catalog.example.edu/"
FOLDER = "catalog-example-edu"
RUN = "2026-10-29T14:00:00Z"
RUN_PATH = "2026-10-29T14-00-00Z"
BUILT_AT = "2026-10-29T14:21:07Z"
ROBOTS = {
    "https://catalog.example.edu/robots.txt": (
        b"User-agent: *\nDisallow: /search/\n"
    )
}


def url(path: str) -> str:
    return f"https://catalog.example.edu{path}"


def crawl(tmp_path: Path, pages: dict, *, documents=None, **settings):
    store = open_store(str(tmp_path))
    settings.setdefault("min_interval_in_seconds", 0)
    settings.setdefault("max_interval_in_seconds", 1)
    resolve_url = settings.pop("resolve_url", lambda url: url)
    config = CrawlSettings(
        seed_url=settings.pop("seed_url", SEED),
        catalog_folder=FOLDER,
        run_id=RUN,
        target_uri=str(tmp_path),
        **settings,
    )
    return run_crawl(
        config,
        store=store,
        fetcher_factory=fetcher_factory(pages),
        url_fetch=site_documents(documents or {}),
        resolve_url=resolve_url,
        sleep=lambda seconds: None,
        now=lambda: BUILT_AT,
    )


def run_dir(tmp_path: Path) -> Path:
    return tmp_path / FOLDER / RUN_PATH


def navigation(tmp_path: Path) -> dict:
    path = run_dir(tmp_path) / "navigation.json"
    return json.loads(path.read_text(encoding="utf-8"))


def rebuild(tmp_path: Path) -> dict:
    store = open_store(str(tmp_path))
    return build_navigation(store, store, FOLDER, RUN, now=lambda: BUILT_AT)


def entries(tree: list[dict]) -> list[dict]:
    """Every page in a tree, top to bottom."""
    out: list[dict] = []
    stack = list(reversed(tree))
    while stack:
        entry = stack.pop()
        out.append(entry)
        stack.extend(reversed(entry.get("pages_found_here", [])))
    return out


def entry_for(doc: dict, page_url: str) -> dict:
    return next(e for e in entries(doc["tree"]) if e["url"] == page_url)


# A small site: the home page has 5 links and only "Courses" is a new page.
GUIDE_SITE = {
    SEED: FakePage(
        html=(
            '<a href="https://www.example.edu/apply">Apply Now</a>'
            '<a href="/">Home</a>'
            '<a href="mailto:catalog@example.edu">Email us</a>'
            '<a href="/courses/">Courses</a>'
            '<a href="/search/">Course Search</a>'
        )
    ),
    url("/courses/"): FakePage(
        html=(
            '<a href="/">Home</a>'
            '<a href="/courses/a/">Course A</a>'
            '<a href="/courses/b/">Course B</a>'
            '<a href="/courses/catalog.pdf">Catalog (PDF)</a>'
            '<a href="/courses/?page=2">Next page</a>'
        )
    ),
    url("/courses/a/"): FakePage(
        html='<h1>Course A</h1><a href="/courses/">All courses</a>'
    ),
    url("/courses/b/"): FakePage(status=404, html=""),
    url("/courses/?page=2"): FakePage(
        html=(
            '<a href="/courses/">Previous page</a>'
            '<a href="/courses/c/">Course C</a>'
        )
    ),
    url("/courses/c/"): FakePage(html="<h1>Course C</h1>"),
}

GUIDE_NAVIGATION = {
    "schema": "xtra-navigation-1",
    "catalog_folder": "catalog-example-edu",
    "run_id": "2026-10-29T14:00:00Z",
    "built_by": "crawl",
    "built_at": "2026-10-29T14:21:07Z",
    "crawl_status": "limit_reached",
    "totals": {
        "pages_by_status": {"saved": 4, "failed": 1, "not_visited": 1},
        "links_by_result": {
            "new": 5,
            "already_found": 4,
            "other_website": 1,
            "not_a_web_page": 1,
            "file": 1,
            "blocked_by_robots": 1,
        },
    },
    "notes": [],
    "tree": [
        {
            "url": "https://catalog.example.edu/",
            "found_by": "start_url",
            "status": "saved",
            "links_on_page": 5,
            "skipped_links": [
                {
                    "link_text": "Apply Now",
                    "url": "https://www.example.edu/apply",
                    "result": "other_website",
                },
                {
                    "link_text": "Email us",
                    "url": "mailto:catalog@example.edu",
                    "result": "not_a_web_page",
                },
                {
                    "link_text": "Course Search",
                    "url": "https://catalog.example.edu/search/",
                    "result": "blocked_by_robots",
                },
            ],
            "pages_found_here": [
                {
                    "url": "https://catalog.example.edu/courses/",
                    "found_on": "https://catalog.example.edu/",
                    "link_text": "Courses",
                    "status": "saved",
                    "links_on_page": 5,
                    "skipped_links": [
                        {
                            "link_text": "Catalog (PDF)",
                            "url": "https://catalog.example.edu/courses/catalog.pdf",
                            "result": "file",
                        }
                    ],
                    "pages_found_here": [
                        {
                            "url": "https://catalog.example.edu/courses/a/",
                            "found_on": "https://catalog.example.edu/courses/",
                            "link_text": "Course A",
                            "status": "saved",
                            "links_on_page": 1,
                        },
                        {
                            "url": "https://catalog.example.edu/courses/b/",
                            "found_on": "https://catalog.example.edu/courses/",
                            "link_text": "Course B",
                            "status": "failed",
                            "error": "HTTP 404",
                        },
                        {
                            "url": "https://catalog.example.edu/courses/?page=2",
                            "found_on": "https://catalog.example.edu/courses/",
                            "link_text": "Next page",
                            "status": "saved",
                            "links_on_page": 2,
                            "pages_found_here": [
                                {
                                    "url": "https://catalog.example.edu/courses/c/",
                                    "found_on": "https://catalog.example.edu/courses/?page=2",
                                    "link_text": "Course C",
                                    "status": "not_visited",
                                }
                            ],
                        },
                    ],
                }
            ],
        }
    ],
}


def test_the_guide_example_gives_the_file_the_guide_shows(
    tmp_path: Path,
) -> None:
    outcome = crawl(
        tmp_path, GUIDE_SITE, documents=ROBOTS, limit=4, with_navigation=True
    )
    assert outcome.crawl_doc["status"] == "limit_reached"
    assert navigation(tmp_path) == GUIDE_NAVIGATION


def test_everything_is_in_one_file(tmp_path: Path) -> None:
    crawl(tmp_path, GUIDE_SITE, documents=ROBOTS, with_navigation=True)
    names = {path.name for path in run_dir(tmp_path).iterdir()}
    assert names == {
        "crawl.json",
        "state.json",
        "failed.jsonl",
        "pages",
        "navigation.json",
    }


def test_without_the_flag_nothing_new_is_written(tmp_path: Path) -> None:
    crawl(tmp_path, GUIDE_SITE, documents=ROBOTS)
    assert not (run_dir(tmp_path) / "navigation.json").exists()


def test_the_link_totals_match_what_the_crawl_counted(tmp_path: Path) -> None:
    doc = crawl(
        tmp_path, GUIDE_SITE, documents=ROBOTS, with_navigation=True
    ).crawl_doc
    totals = navigation(tmp_path)["totals"]
    crawl_name = {
        "already_found": "duplicate",
        "other_website": "out_of_scope",
        "outside_scope": "out_of_scope",
        "not_a_web_page": "scheme",
        "file": "extension",
        "blocked_by_robots": "robots",
    }
    counted: Counter = Counter()
    for result, count in totals["links_by_result"].items():
        if result != "new":
            counted[crawl_name[result]] += count
    assert dict(counted) == doc["skipped_by_reason"]
    pages = sum(totals["pages_by_status"].values())
    assert totals["links_by_result"]["new"] + 1 == pages


def test_a_skipped_link_is_listed_once_where_it_was_first_seen(
    tmp_path: Path,
) -> None:
    footer = '<a href="https://www.example.edu/">College home</a>'
    pages = {
        SEED: FakePage(html=f'<a href="/a">A</a>{footer}'),
        url("/a"): FakePage(html=f'<a href="/">Home</a>{footer}'),
    }
    crawl(tmp_path, pages, with_navigation=True)
    built = navigation(tmp_path)
    assert entry_for(built, SEED)["skipped_links"] == [
        {
            "link_text": "College home",
            "url": "https://www.example.edu/",
            "result": "other_website",
        }
    ]
    page_a = entry_for(built, url("/a"))
    assert page_a["links_on_page"] == 2
    assert "skipped_links" not in page_a
    assert built["totals"]["links_by_result"]["other_website"] == 2


def test_a_rebuild_gives_the_same_tree_as_the_crawl(tmp_path: Path) -> None:
    built_dir, plain_dir = tmp_path / "built", tmp_path / "plain"
    crawl(
        built_dir, GUIDE_SITE, documents=ROBOTS, limit=4, with_navigation=True
    )
    crawl(plain_dir, GUIDE_SITE, documents=ROBOTS, limit=4)

    rebuilt = rebuild(plain_dir)
    built = navigation(built_dir)
    assert rebuilt["built_by"] == "rebuild"
    assert built["built_by"] == "crawl"
    assert rebuilt["tree"] == built["tree"]
    assert rebuilt["totals"] == built["totals"]
    assert any("robots.txt was not saved" in note for note in rebuilt["notes"])


def test_a_rebuild_never_replaces_a_tree_the_crawl_built(
    tmp_path: Path,
) -> None:
    crawl(tmp_path, GUIDE_SITE, documents=ROBOTS, with_navigation=True)
    with pytest.raises(NavigationError, match="built by the crawl"):
        rebuild(tmp_path)


def test_a_rebuild_may_replace_an_earlier_rebuild(tmp_path: Path) -> None:
    crawl(tmp_path, GUIDE_SITE, documents=ROBOTS)
    first = rebuild(tmp_path)
    assert rebuild(tmp_path)["tree"] == first["tree"]


def test_a_rebuild_needs_a_crawl(tmp_path: Path) -> None:
    with pytest.raises(NavigationError, match="no state.json"):
        rebuild(tmp_path)


def test_a_resumed_crawl_gives_the_same_tree(tmp_path: Path) -> None:
    once, twice = tmp_path / "once", tmp_path / "twice"
    crawl(once, GUIDE_SITE, documents=ROBOTS, with_navigation=True)
    crawl(twice, GUIDE_SITE, documents=ROBOTS, limit=2, with_navigation=True)
    crawl(twice, GUIDE_SITE, documents=ROBOTS, with_navigation=True)
    assert navigation(twice) == navigation(once)


SITEMAP = (
    b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    b"<url><loc>https://catalog.example.edu/</loc></url>"
    b"<url><loc>https://catalog.example.edu/courses/</loc></url>"
    b"<url><loc>https://catalog.example.edu/hidden/</loc></url>"
    b"<url><loc>https://other.example.org/elsewhere/</loc></url>"
    b"</urlset>"
)

SITEMAP_SITE = {
    SEED: FakePage(html='<a href="/courses/">Courses</a>'),
    url("/courses/"): FakePage(html="<h1>Courses</h1>"),
    url("/hidden/"): FakePage(html="<h1>Hidden</h1>"),
}


def test_sitemap_pages_are_found_by_the_sitemap(tmp_path: Path) -> None:
    documents = {url("/sitemap.xml"): SITEMAP}
    crawl(tmp_path, SITEMAP_SITE, documents=documents, with_navigation=True)
    tree = navigation(tmp_path)["tree"]
    assert [(entry["url"], entry["found_by"]) for entry in tree] == [
        (SEED, "start_url"),
        (url("/courses/"), "sitemap"),
        (url("/hidden/"), "sitemap"),
    ]
    assert tree[0]["links_on_page"] == 1
    assert "pages_found_here" not in tree[0]
    assert "found_on" not in tree[1]


def test_a_rebuild_says_it_cannot_tell_sitemap_pages(tmp_path: Path) -> None:
    documents = {url("/sitemap.xml"): SITEMAP}
    crawl(tmp_path, SITEMAP_SITE, documents=documents)
    rebuilt = rebuild(tmp_path)
    tree = rebuilt["tree"]
    assert [(entry["url"], entry["found_by"]) for entry in tree] == [
        (SEED, "start_url"),
        (url("/hidden/"), "not_from_a_link"),
    ]
    assert tree[0]["pages_found_here"][0]["url"] == url("/courses/")
    assert any("from the sitemap" in note for note in rebuilt["notes"])


def test_a_rebuild_still_lists_sitemap_pages_never_reached(
    tmp_path: Path,
) -> None:
    documents = {url("/sitemap.xml"): SITEMAP}
    crawl(tmp_path, SITEMAP_SITE, documents=documents, limit=1)
    hidden = rebuild(tmp_path)["tree"][-1]
    assert hidden["url"] == url("/hidden/")
    assert hidden["found_by"] == "not_from_a_link"
    assert hidden["status"] == "not_visited"


def test_a_link_to_where_a_page_landed_is_already_found(tmp_path: Path) -> None:
    pages = {
        SEED: FakePage(html='<a href="/old/">Old</a>'),
        url("/old/"): FakePage(
            html='<a href="/new/">This page</a>', final_url=url("/new/")
        ),
    }
    crawl(tmp_path, pages, with_navigation=True)
    old = entry_for(navigation(tmp_path), url("/old/"))
    assert old["redirected_to"] == url("/new/")
    assert old["links_on_page"] == 1
    assert "pages_found_here" not in old
    assert "skipped_links" not in old


def test_a_typed_host_that_answers_elsewhere_rebuilds_the_same(
    tmp_path: Path,
) -> None:
    pages = {
        SEED: FakePage(html='<a href="https://old.example.edu/courses/">C</a>'),
        url("/courses/"): FakePage(html="<h1>Courses</h1>"),
    }
    settings = {
        "seed_url": "https://old.example.edu/",
        "resolve_url": lambda typed: SEED,
    }
    crawl(tmp_path / "built", pages, with_navigation=True, **settings)
    crawl(tmp_path / "plain", pages, **settings)

    built = navigation(tmp_path / "built")
    assert [entry["url"] for entry in entries(built["tree"])] == [
        SEED,
        url("/courses/"),
    ]
    assert rebuild(tmp_path / "plain")["tree"] == built["tree"]


def test_links_outside_the_crawl_say_why(tmp_path: Path) -> None:
    start = url("/catalog/")
    pages = {
        start: FakePage(
            html=(
                '<a href="/about/">About</a>'
                '<a href="/catalog/a?print=1">Print</a>'
                '<a href="/catalog/a">A</a>'
            )
        ),
        url("/catalog/a"): FakePage(html="<h1>A</h1>"),
    }
    crawl(
        tmp_path,
        pages,
        seed_url=start,
        exclude_regex=("print",),
        with_navigation=True,
    )
    entry = navigation(tmp_path)["tree"][0]
    assert [link["result"] for link in entry["skipped_links"]] == [
        "outside_scope",
        "left_out_by_exclude_regex",
    ]
    assert entry["pages_found_here"][0]["url"] == url("/catalog/a")


def test_a_page_dropped_when_opened_is_skipped_with_its_reason(
    tmp_path: Path,
) -> None:
    pages = {
        SEED: FakePage(html='<a href="/download">Download</a>'),
        url("/download"): FakePage(content_type="application/pdf"),
    }
    crawl(tmp_path, pages, with_navigation=True)
    entry = navigation(tmp_path)["tree"][0]["pages_found_here"][0]
    assert entry["status"] == "skipped"
    assert entry["reason"] == "download"


def test_pages_skipped_for_more_than_one_reason_say_so_in_notes(
    tmp_path: Path,
) -> None:
    pages = {
        SEED: FakePage(html='<a href="/download">D</a><a href="/moved">M</a>'),
        url("/download"): FakePage(content_type="application/pdf"),
        url("/moved"): FakePage(final_url="https://other.example.org/x"),
    }
    crawl(tmp_path, pages, with_navigation=True)
    built = navigation(tmp_path)
    skipped = built["tree"][0]["pages_found_here"]
    assert [entry["status"] for entry in skipped] == ["skipped", "skipped"]
    assert all("reason" not in entry for entry in skipped)
    assert any("only counts" in note for note in built["notes"])


def test_a_rebuild_of_a_damaged_run_says_what_is_missing(
    tmp_path: Path, caplog
) -> None:
    crawl(tmp_path, GUIDE_SITE, documents=ROBOTS)
    (run_dir(tmp_path) / "crawl.json").unlink()
    page = run_dir(tmp_path) / "pages" / f"{page_stem(url('/courses/a/'))}.html"
    page.unlink()

    with caplog.at_level(logging.INFO):
        rebuilt = rebuild(tmp_path)
    assert rebuilt["crawl_status"] is None
    assert any("could not be read" in note for note in rebuilt["notes"])
    course_a = entry_for(rebuilt, url("/courses/a/"))
    assert course_a["status"] == "saved"
    assert "links_on_page" not in course_a
    assert (
        f"NAVIGATION could not read the saved page {url('/courses/a/')}, so "
        "its links are left out"
    ) in caplog.text
    assert "NAVIGATION note: 1 saved pages could not be read" in caplog.text


def navigation_lines(caplog) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("NAVIGATION ")
    ]


def test_the_log_says_what_the_link_tree_is_doing(
    tmp_path: Path, caplog, monkeypatch
) -> None:
    monkeypatch.setattr("implementations.crawl_navigation.PROGRESS_EVERY", 2)
    with caplog.at_level(logging.INFO):
        crawl(tmp_path, GUIDE_SITE, documents=ROBOTS, with_navigation=True)

    lines = navigation_lines(caplog)
    assert lines[0] == (
        "NAVIGATION on: the link tree will be built when the crawl ends"
    )
    assert lines[1] == (
        "NAVIGATION building the link tree for catalog-example-edu run "
        "2026-10-29T14:00:00Z from 5 saved pages"
    )
    assert lines[2].startswith("NAVIGATION read 2 of 5 saved pages, ")
    assert lines[3].startswith("NAVIGATION read 4 of 5 saved pages, ")
    assert lines[4].startswith("NAVIGATION done in ")
    assert lines[4].endswith(
        ": 6 pages (saved=5 failed=1), 13 links (new=5 already_found=4 "
        "other_website=1 not_a_web_page=1 file=1 blocked_by_robots=1)"
    )
    assert lines[5].startswith("NAVIGATION wrote ")
    assert lines[5].endswith("navigation.json")
    assert len(lines) == 6


def test_a_rebuild_logs_its_notes(tmp_path: Path, caplog) -> None:
    crawl(tmp_path, GUIDE_SITE, documents=ROBOTS)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        rebuild(tmp_path)
    assert any(
        line.startswith("NAVIGATION note: robots.txt was not saved")
        for line in navigation_lines(caplog)
    )


def test_a_very_deep_crawl_nests_only_so_far(tmp_path: Path) -> None:
    depth = MAX_NESTED_CLICKS + 5
    chain = [SEED] + [url(f"/p{n}") for n in range(1, depth + 1)]
    pages = {
        page: FakePage(html=f'<a href="{chain[n + 1]}">next</a>')
        for n, page in enumerate(chain[:-1])
    }
    pages[chain[-1]] = FakePage(html="<p>end</p>")
    crawl(tmp_path, pages, with_navigation=True)

    tree = navigation(tmp_path)["tree"]
    assert len(entries(tree)) == len(chain)
    # Every page past the cap is listed at the top, saying where it was found.
    assert len(tree) == 1 + depth - MAX_NESTED_CLICKS
    assert tree[1]["found_on"] == chain[MAX_NESTED_CLICKS]
    assert tree[-1]["found_on"] == chain[-2]


def test_an_interrupted_crawl_builds_nothing(tmp_path: Path, caplog) -> None:
    def ctrl_c(*args, **kwargs):
        raise KeyboardInterrupt

    with (
        pytest.MonkeyPatch.context() as patch,
        caplog.at_level(logging.WARNING),
    ):
        patch.setattr("implementations.crawl.wait_for_futures", ctrl_c)
        outcome = crawl(tmp_path, GUIDE_SITE, with_navigation=True)
    assert outcome.exit_code == 130
    assert not (run_dir(tmp_path) / "navigation.json").exists()
    assert "xtra catalog navigation" in caplog.text


def test_a_tree_that_cannot_be_built_does_not_fail_the_crawl(
    tmp_path: Path, caplog, monkeypatch
) -> None:
    def broken(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("implementations.crawl.build_navigation", broken)
    pages = {SEED: FakePage(html="<p>only page</p>")}
    with caplog.at_level(logging.ERROR):
        outcome = crawl(tmp_path, pages, with_navigation=True)
    assert outcome.exit_code == 0
    assert "NAVIGATION could not be built: disk full" in caplog.text
