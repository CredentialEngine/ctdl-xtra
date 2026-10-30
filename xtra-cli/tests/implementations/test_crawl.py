from __future__ import annotations

import gzip
import json
import logging
import platform
import shutil
import threading
from importlib.metadata import version
from pathlib import Path

import pytest
from crawl_doubles import (
    CQ_CATALOG,
    LIST_LOADING,
    FakePage,
    button_row,
    cq_node,
    curriqunet_documents,
    fetcher_factory,
    list_page,
    list_site_page,
    no_site_documents,
    site_documents,
)

from common.keys import checkpoint_key, page_html_key, page_stem, state_key
from common.object_store import ObjectStore, open_store
from implementations.crawl import (
    CHECKPOINTS_KEPT,
    FRONTIER_ORDER,
    INDEX_INTERVAL_SECONDS,
    STATUS_COMPLETE,
    STATUS_INCOMPLETE,
    STATUS_LIMIT_REACHED,
    CrawlSettings,
    StrategyMismatchError,
    format_duration,
    is_retryable_status,
    run_crawl,
)
from implementations.crawl_browser import DEFAULT_TIMEOUT_MS, VIEWPORT
from implementations.crawl_curriqunet import INDEX_KIND
from implementations.crawl_list_pages import MAX_LIST_PAGES
from implementations.crawl_strategy import strategy_facts

SEED = "https://catalog.example.edu/"
FOLDER = "catalog-example-edu"
RUN = "2026-09-17T14:20:01Z"
RUN_PATH = "2026-09-17T14-20-01Z"

HOME = FakePage(
    html='<a href="/courses/engl101">ENGL</a><a href="/courses/math101">MATH</a>'
)
ENGL = FakePage(html="<h1>ENGL 101</h1><p>3 credits</p>")
MATH = FakePage(html="<h1>MATH 101</h1>")
PAGES = {
    SEED: HOME,
    "https://catalog.example.edu/courses/engl101": ENGL,
    "https://catalog.example.edu/courses/math101": MATH,
}


def crawl(
    tmp_path: Path,
    pages: dict,
    *,
    documents: dict | None = None,
    calls: list[str] | None = None,
    url_calls: list[str] | None = None,
    before=None,
    sleeps: list[float] | None = None,
    resolve_url=None,
    **settings,
):
    """Run one crawl into tmp_path with a fake browser and no network.

    `calls` records what the browser rendered and `url_calls` what was
    read without one: robots.txt, sitemaps, and the seed's page index.
    """
    store = open_store(str(tmp_path))
    settings.setdefault("min_interval_in_seconds", 0)
    settings.setdefault("max_interval_in_seconds", 1)
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
        fetcher_factory=fetcher_factory(pages, calls=calls, before=before),
        url_fetch=site_documents(documents or {}, calls=url_calls),
        resolve_url=resolve_url or (lambda url: url),
        sleep=sleeps.append if sleeps is not None else (lambda seconds: None),
    )


def run_dir(tmp_path: Path) -> Path:
    return tmp_path / FOLDER / RUN_PATH


def checkpoint_files(tmp_path: Path) -> list[Path]:
    return sorted((run_dir(tmp_path) / "checkpoints").glob("*.json"))


def newest_checkpoint(tmp_path: Path) -> dict:
    path = checkpoint_files(tmp_path)[-1]
    return json.loads(path.read_text(encoding="utf-8"))


def saved_state(tmp_path: Path) -> dict:
    return newest_checkpoint(tmp_path)["state"]


# --- what a crawl saves ----------------------------------------------------


def test_a_crawl_saves_html_and_a_sidecar_and_nothing_else(
    tmp_path: Path,
) -> None:
    outcome = crawl(tmp_path, PAGES)
    assert outcome.crawl_doc["status"] == STATUS_COMPLETE
    assert outcome.crawl_doc["pages_saved"] == 3
    assert outcome.exit_code == 0

    names = sorted(
        path.name for path in run_dir(tmp_path).rglob("*") if path.is_file()
    )
    assert [name for name in names if name.endswith(".txt")] == []
    assert "slots.json" not in names
    assert {"crawl.json", "failed.jsonl"} <= set(names)
    assert "state.json" not in names
    assert checkpoint_files(tmp_path)
    assert len([name for name in names if name.endswith(".html")]) == 3
    assert len([name for name in names if name.endswith(".meta.json")]) == 3


def test_crawl_json_has_no_family_template_or_institution(
    tmp_path: Path,
) -> None:
    doc = crawl(tmp_path, PAGES).crawl_doc
    assert doc["schema"] == "xtra-crawl-2"
    for gone in (
        "family",
        "source_family",
        "template_id",
        "institution_name",
        "slots",
        "kept",
        "discover_only",
    ):
        assert gone not in doc
    assert doc["run_id"] == RUN
    assert doc["catalog_folder"] == FOLDER


def test_the_sidecar_records_what_the_fetch_cost(tmp_path: Path) -> None:
    crawl(tmp_path, PAGES)
    stem = page_stem("https://catalog.example.edu/courses/engl101")
    meta = json.loads(
        (run_dir(tmp_path) / "pages" / f"{stem}.meta.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        meta["requested_url"] == "https://catalog.example.edu/courses/engl101"
    )
    assert meta["http_status"] == 200
    assert meta["bytes"] == len(ENGL.html.encode("utf-8"))
    assert meta["latency_ms"] == 7
    assert meta["attempts"] == 1
    assert meta["stem"] == stem
    assert len(meta["sha256"]) == 64
    assert "normalized" not in json.dumps(meta)


def test_the_sidecar_says_where_the_page_it_describes_is(
    tmp_path: Path,
) -> None:
    """A sidecar read on its own has to name the bytes it is about.

    The key is what every later stage looks the page up by; the path is
    the same key against the URI this run wrote to, so a person reading
    one sidecar can open the page without reconstructing the layout.
    """
    crawl(tmp_path, PAGES)
    stem = page_stem("https://catalog.example.edu/courses/engl101")
    meta = json.loads(
        (run_dir(tmp_path) / "pages" / f"{stem}.meta.json").read_text(
            encoding="utf-8"
        )
    )
    assert meta["html_key"] == page_html_key(FOLDER, RUN, stem)
    assert meta["html_path"] == f"{tmp_path}/{page_html_key(FOLDER, RUN, stem)}"
    assert Path(meta["html_path"]).is_file()


def test_the_get_line_names_the_url_status_size_time_and_destination(
    tmp_path: Path, caplog
) -> None:
    with caplog.at_level(logging.INFO):
        crawl(tmp_path, PAGES)
    gets = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("GET ")
    ]
    assert len(gets) == 3
    line = next(line for line in gets if "engl101" in line)
    assert "-> 200 " in line
    assert f"{len(ENGL.html.encode('utf-8'))} bytes" in line
    assert "7 ms ->" in line
    assert line.rstrip().endswith(
        page_html_key(
            FOLDER,
            RUN,
            page_stem("https://catalog.example.edu/courses/engl101"),
        )
    )


def test_progress_is_logged_with_elapsed_and_an_eta(
    tmp_path: Path, caplog
) -> None:
    with caplog.at_level(logging.INFO):
        crawl(tmp_path, PAGES)
    progress = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("PROGRESS ")
    ]
    assert progress
    assert "saved=3" in progress[-1]
    assert "elapsed=" in progress[-1] and "eta=" in progress[-1]


def test_format_duration() -> None:
    assert format_duration(0) == "00:00:00"
    assert format_duration(21670) == "06:01:10"
    assert format_duration(-5) == "00:00:00"


# --- scope -----------------------------------------------------------------


def test_off_site_and_downloadable_links_are_skipped(tmp_path: Path) -> None:
    pages = {
        SEED: FakePage(
            html=(
                '<a href="https://other.edu/x">off</a>'
                '<a href="/catalog.pdf">pdf</a>'
                '<a href="/courses/engl101">ENGL</a>'
            )
        ),
        "https://catalog.example.edu/courses/engl101": ENGL,
    }
    doc = crawl(tmp_path, pages).crawl_doc
    assert doc["pages_saved"] == 2
    assert doc["skipped_by_reason"]["out_of_scope"] == 1
    assert doc["skipped_by_reason"]["extension"] == 1


def test_the_same_page_under_two_urls_is_fetched_once(tmp_path: Path) -> None:
    pages = {
        SEED: FakePage(
            html=(
                '<a href="/courses/engl101">one</a>'
                '<a href="/courses/engl101#syllabus">two</a>'
                '<a href="http://catalog.example.edu/courses/engl101">three</a>'
            )
        ),
        "https://catalog.example.edu/courses/engl101": ENGL,
    }
    calls: list[str] = []
    doc = crawl(tmp_path, pages, calls=calls).crawl_doc
    assert doc["pages_saved"] == 2
    assert calls.count("https://catalog.example.edu/courses/engl101") == 1
    # The fragment copy is already gone when the links leave the page; the
    # http spelling is the one the frontier has to recognise as the same page.
    assert doc["skipped_by_reason"]["duplicate"] == 1


def test_a_redirect_off_the_site_is_not_saved(tmp_path: Path) -> None:
    pages = {
        SEED: FakePage(html='<a href="/courses/engl101">ENGL</a>'),
        "https://catalog.example.edu/courses/engl101": FakePage(
            html="<h1>moved</h1>",
            final_url="https://vendor.example.com/engl101",
        ),
    }
    doc = crawl(tmp_path, pages).crawl_doc
    assert doc["pages_saved"] == 1
    assert doc["skipped_by_reason"]["redirect_out_of_scope"] == 1


def test_a_non_html_response_is_skipped(tmp_path: Path) -> None:
    pages = {
        SEED: FakePage(html='<a href="/courses/plan">plan</a>'),
        "https://catalog.example.edu/courses/plan": FakePage(
            html="%PDF", content_type="application/pdf"
        ),
    }
    doc = crawl(tmp_path, pages).crawl_doc
    assert doc["pages_saved"] == 1
    assert doc["skipped_by_reason"]["non_html"] == 1


def test_a_navigation_that_starts_a_download_is_skipped(tmp_path: Path) -> None:
    pages = {
        SEED: FakePage(html='<a href="/courses/plan">plan</a>'),
        "https://catalog.example.edu/courses/plan": FakePage(
            raises="net::ERR_ABORTED", retryable=False, reason="non_html"
        ),
    }
    doc = crawl(tmp_path, pages).crawl_doc
    assert doc["skipped_by_reason"]["non_html"] == 1
    assert doc["pages_failed"] == 0


def test_an_include_regex_narrows_what_links_are_followed(
    tmp_path: Path,
) -> None:
    seed = "https://catalog.bergen.edu/"
    pages = {
        seed: FakePage(
            html=(
                '<a href="/content.php?catoid=13&navoid=1">this year</a>'
                '<a href="/content.php?catoid=12&navoid=1">last year</a>'
            )
        ),
        "https://catalog.bergen.edu/content.php?catoid=13&navoid=1": ENGL,
    }
    doc = crawl(
        tmp_path, pages, seed_url=seed, include_regex=("catoid=13",)
    ).crawl_doc
    assert doc["pages_saved"] == 2
    assert doc["skipped_by_reason"]["include_rule"] == 1


def test_the_seed_is_crawled_even_when_it_fails_its_own_include_regex(
    tmp_path: Path,
) -> None:
    """Otherwise --include-regex would leave the crawl nothing to start from."""
    seed = "https://catalog.bergen.edu/"
    pages = {
        seed: FakePage(html='<a href="/content.php?catoid=13">year</a>'),
        "https://catalog.bergen.edu/content.php?catoid=13": ENGL,
    }
    doc = crawl(
        tmp_path, pages, seed_url=seed, include_regex=("catoid=13",)
    ).crawl_doc
    assert doc["pages_saved"] == 2


def test_a_scope_prefix_keeps_the_crawl_inside_one_section(
    tmp_path: Path,
) -> None:
    pages = {
        SEED: FakePage(
            html='<a href="/courses/engl101">ENGL</a><a href="/athletics/x">A</a>'
        ),
        "https://catalog.example.edu/courses/engl101": ENGL,
    }
    doc = crawl(
        tmp_path,
        pages,
        scope_prefix="https://catalog.example.edu/courses/",
    ).crawl_doc
    # The seed itself is above the prefix, so only the course page is saved.
    assert doc["scope_prefix"] == "/courses/"
    assert doc["skipped_by_reason"]["out_of_scope"] >= 1


def test_extra_seed_urls_reach_pages_no_link_points_at(tmp_path: Path) -> None:
    hidden = "https://catalog.example.edu/hidden/engl999"
    pages = {SEED: FakePage(html="<p>no links</p>"), hidden: ENGL}
    doc = crawl(tmp_path, pages, seed_urls=(hidden,)).crawl_doc
    assert doc["pages_saved"] == 2


# --- robots and sitemaps ---------------------------------------------------


def test_robots_disallow_keeps_a_section_out_of_the_crawl(
    tmp_path: Path,
) -> None:
    documents = {
        "https://catalog.example.edu/robots.txt": b"User-agent: *\nDisallow: /private/\n"
    }
    pages = {
        SEED: FakePage(
            html='<a href="/private/x">no</a><a href="/courses/engl101">yes</a>'
        ),
        "https://catalog.example.edu/courses/engl101": ENGL,
    }
    calls: list[str] = []
    doc = crawl(tmp_path, pages, documents=documents, calls=calls).crawl_doc
    assert doc["robots_status"] == 200
    assert doc["skipped_by_reason"]["robots"] == 1
    assert "https://catalog.example.edu/private/x" not in calls


def test_a_robots_crawl_delay_raises_the_effective_minimum(
    tmp_path: Path,
) -> None:
    documents = {
        "https://catalog.example.edu/robots.txt": b"User-agent: *\nCrawl-delay: 7\n"
    }
    doc = crawl(
        tmp_path,
        PAGES,
        documents=documents,
        min_interval_in_seconds=3,
        max_interval_in_seconds=60,
    ).crawl_doc
    assert doc["robots_crawl_delay"] == 7.0
    assert doc["min_interval_in_seconds"] == 3
    assert doc["effective_min_interval_in_seconds"] == 7.0


def test_a_larger_min_interval_wins_over_a_smaller_crawl_delay(
    tmp_path: Path,
) -> None:
    documents = {
        "https://catalog.example.edu/robots.txt": b"User-agent: *\nCrawl-delay: 2\n"
    }
    doc = crawl(
        tmp_path,
        PAGES,
        documents=documents,
        min_interval_in_seconds=30,
        max_interval_in_seconds=60,
    ).crawl_doc
    assert doc["effective_min_interval_in_seconds"] == 30


def test_a_403_robots_is_recorded_and_treated_as_no_rules(
    tmp_path: Path,
) -> None:
    def forbidden(url: str) -> tuple[int, bytes]:
        return (403, b"nope") if url.endswith("robots.txt") else (404, b"")

    store = open_store(str(tmp_path))
    config = CrawlSettings(
        seed_url=SEED,
        catalog_folder=FOLDER,
        run_id=RUN,
        target_uri=str(tmp_path),
        min_interval_in_seconds=0,
        max_interval_in_seconds=1,
    )
    outcome = run_crawl(
        config,
        store=store,
        fetcher_factory=fetcher_factory(PAGES),
        url_fetch=forbidden,
        resolve_url=lambda url: url,
        sleep=lambda seconds: None,
    )
    assert outcome.crawl_doc["robots_status"] == 403
    assert outcome.crawl_doc["pages_saved"] == 3


def test_sitemap_urls_join_the_frontier_and_off_site_entries_do_not(
    tmp_path: Path,
) -> None:
    ns = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
    index = (
        f"<sitemapindex {ns}><sitemap>"
        "<loc>https://catalog.example.edu/sitemap-1.xml.gz</loc>"
        "</sitemap></sitemapindex>"
    ).encode()
    urlset = (
        f"<urlset {ns}>"
        "<url><loc>https://catalog.example.edu/hidden/a</loc></url>"
        "<url><loc>https://other.edu/elsewhere</loc></url>"
        "</urlset>"
    ).encode()
    documents = {
        "https://catalog.example.edu/robots.txt": b"User-agent: *\n",
        "https://catalog.example.edu/sitemap.xml": index,
        "https://catalog.example.edu/sitemap-1.xml.gz": gzip.compress(urlset),
    }
    pages = {
        SEED: FakePage(html="<p>no links</p>"),
        "https://catalog.example.edu/hidden/a": ENGL,
    }
    calls: list[str] = []
    doc = crawl(tmp_path, pages, documents=documents, calls=calls).crawl_doc
    assert doc["sitemap_urls_found"] == 2
    assert doc["pages_saved"] == 2
    assert "https://other.edu/elsewhere" not in calls


# --- pacing, retries, failures ---------------------------------------------


def test_is_retryable_status() -> None:
    assert is_retryable_status(429)
    assert is_retryable_status(500)
    assert is_retryable_status(503)
    assert not is_retryable_status(404)
    assert not is_retryable_status(200)
    assert not is_retryable_status(None)


def test_retries_back_off_from_the_minimum_up_to_the_maximum(
    tmp_path: Path,
) -> None:
    pages = {SEED: FakePage(status=503, html="")}
    sleeps: list[float] = []
    outcome = crawl(
        tmp_path,
        pages,
        sleeps=sleeps,
        min_interval_in_seconds=1,
        max_interval_in_seconds=5,
        max_retries=5,
    )
    assert sleeps == [1, 2, 4, 5, 5]
    assert outcome.crawl_doc["pages_failed"] == 1
    assert outcome.crawl_doc["failed_by_status"] == {"503": 1}
    assert outcome.exit_code == 1


def test_a_retry_after_header_lengthens_one_wait_but_not_past_the_maximum(
    tmp_path: Path,
) -> None:
    pages = {
        SEED: [
            FakePage(status=429, html="", retry_after=3),
            FakePage(status=429, html="", retry_after=900),
            HOME,
        ],
        "https://catalog.example.edu/courses/engl101": ENGL,
        "https://catalog.example.edu/courses/math101": MATH,
    }
    sleeps: list[float] = []
    outcome = crawl(
        tmp_path,
        pages,
        sleeps=sleeps,
        min_interval_in_seconds=1,
        max_interval_in_seconds=5,
        max_retries=5,
    )
    assert sleeps[:2] == [3, 5]
    assert outcome.crawl_doc["pages_saved"] == 3
    assert outcome.exit_code == 0


def test_a_404_is_not_retried(tmp_path: Path) -> None:
    pages = {
        SEED: FakePage(html='<a href="/courses/gone">gone</a>'),
        "https://catalog.example.edu/courses/gone": FakePage(
            status=404, html=""
        ),
    }
    calls: list[str] = []
    sleeps: list[float] = []
    outcome = crawl(tmp_path, pages, calls=calls, sleeps=sleeps, max_retries=5)
    assert calls.count("https://catalog.example.edu/courses/gone") == 1
    assert sleeps == []
    assert outcome.crawl_doc["failed_by_status"] == {"404": 1}


def test_a_retry_line_names_the_attempt_and_the_wait(
    tmp_path: Path, caplog
) -> None:
    pages = {SEED: [FakePage(status=429, html=""), FakePage(html="<p>ok</p>")]}
    with caplog.at_level(logging.INFO):
        crawl(
            tmp_path,
            pages,
            min_interval_in_seconds=1,
            max_interval_in_seconds=5,
        )
    retries = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("RETRY ")
    ]
    assert retries == [
        f"RETRY {SEED} attempt 2 of 6 after HTTP 429, waiting 1 s"
    ]


def test_a_fail_line_names_the_attempts_and_the_reason(
    tmp_path: Path, caplog
) -> None:
    with caplog.at_level(logging.WARNING):
        crawl(tmp_path, {SEED: FakePage(status=503, html="")}, max_retries=5)
    fails = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("FAIL ")
    ]
    assert fails == [f"FAIL {SEED} after 6 attempts: HTTP 503"]


def test_failed_urls_are_written_one_json_object_per_line(
    tmp_path: Path,
) -> None:
    crawl(tmp_path, {SEED: FakePage(status=503, html="")}, max_retries=1)
    lines = (
        (run_dir(tmp_path) / "failed.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["url"] == SEED
    assert record["http_status"] == 503
    assert record["retryable"] is True


def test_a_min_above_the_max_is_rejected() -> None:
    with pytest.raises(ValueError, match="--min-interval-in-seconds"):
        CrawlSettings(
            seed_url=SEED,
            catalog_folder=FOLDER,
            run_id=RUN,
            target_uri=".",
            min_interval_in_seconds=600,
            max_interval_in_seconds=60,
        )


def test_twenty_failures_in_a_row_stop_the_crawl(tmp_path: Path) -> None:
    links = "".join(f'<a href="/courses/gone{n}">g</a>' for n in range(25))
    pages = {SEED: FakePage(html=links)}
    outcome = crawl(tmp_path, pages, max_retries=1)
    doc = outcome.crawl_doc
    assert doc["status"] == STATUS_INCOMPLETE
    assert doc["pages_failed"] == 20
    assert doc["frontier_remaining"] == 5
    assert outcome.exit_code == 1
    assert "rerun with the same --run-id" in outcome.reason


def test_a_success_clears_the_run_of_failures(tmp_path: Path) -> None:
    links = "".join(f'<a href="/courses/gone{n}">g</a>' for n in range(19))
    pages = {
        SEED: FakePage(html=links + '<a href="/courses/engl101">ENGL</a>'),
        "https://catalog.example.edu/courses/engl101": ENGL,
    }
    doc = crawl(tmp_path, pages, max_retries=1).crawl_doc
    assert doc["status"] == STATUS_COMPLETE
    assert doc["pages_failed"] == 19


# --- concurrency ------------------------------------------------------------


def test_three_workers_fetch_three_pages_at_the_same_time(
    tmp_path: Path,
) -> None:
    """The barrier only releases when all three are inside fetch at once."""
    gate = threading.Barrier(3, timeout=10)
    pages = {
        SEED: FakePage(html="<p>no links</p>"),
        "https://catalog.example.edu/a": ENGL,
        "https://catalog.example.edu/b": MATH,
    }
    made: list = []
    store = open_store(str(tmp_path))
    config = CrawlSettings(
        seed_url=SEED,
        catalog_folder=FOLDER,
        run_id=RUN,
        target_uri=str(tmp_path),
        concurrency_limit=3,
        min_interval_in_seconds=0,
        max_interval_in_seconds=1,
        seed_urls=(
            "https://catalog.example.edu/a",
            "https://catalog.example.edu/b",
        ),
    )
    outcome = run_crawl(
        config,
        store=store,
        fetcher_factory=fetcher_factory(
            pages, before=lambda url: gate.wait(), made=made
        ),
        url_fetch=no_site_documents,
        resolve_url=lambda url: url,
        sleep=lambda seconds: None,
    )
    assert outcome.crawl_doc["pages_saved"] == 3
    assert outcome.crawl_doc["concurrency_limit"] == 3
    assert len(made) == 3
    assert all(fetcher.closed for fetcher in made)


# --- limit and resume -------------------------------------------------------


def test_the_limit_stops_the_run_and_a_higher_limit_continues_it(
    tmp_path: Path,
) -> None:
    first = crawl(tmp_path, PAGES, limit=2)
    assert first.crawl_doc["status"] == STATUS_LIMIT_REACHED
    assert first.crawl_doc["pages_saved"] == 2
    assert first.exit_code == 0

    calls: list[str] = []
    second = crawl(tmp_path, PAGES, limit=5, calls=calls)
    assert second.crawl_doc["pages_saved"] == 3
    assert second.crawl_doc["status"] == STATUS_COMPLETE
    # The two pages of the first run came back from storage, not the site.
    assert len(calls) == 1


def test_a_resume_reads_saved_pages_from_storage_and_never_refetches_them(
    tmp_path: Path, caplog
) -> None:
    crawl(tmp_path, PAGES, limit=1)
    calls: list[str] = []
    with caplog.at_level(logging.INFO):
        outcome = crawl(tmp_path, PAGES, limit=5, calls=calls)
    assert SEED not in calls
    assert sorted(calls) == [
        "https://catalog.example.edu/courses/engl101",
        "https://catalog.example.edu/courses/math101",
    ]
    assert outcome.crawl_doc["pages_saved"] == 3
    assert f"FROM-STORAGE {SEED} (already saved, no GET)" in caplog.text


def test_a_saved_page_still_hands_over_its_links_when_the_checkpoint_is_gone(
    tmp_path: Path,
) -> None:
    """Storage, not the checkpoint, is what proves the page was fetched."""
    crawl(tmp_path, PAGES, limit=1)
    shutil.rmtree(run_dir(tmp_path) / "checkpoints")

    calls: list[str] = []
    outcome = crawl(tmp_path, PAGES, calls=calls)
    assert SEED not in calls
    assert sorted(calls) == [
        "https://catalog.example.edu/courses/engl101",
        "https://catalog.example.edu/courses/math101",
    ]
    assert outcome.crawl_doc["pages_saved"] == 3


def test_a_resume_queues_a_retryable_failure_once_more(tmp_path: Path) -> None:
    pages = {
        SEED: FakePage(html='<a href="/courses/engl101">ENGL</a>'),
        "https://catalog.example.edu/courses/engl101": FakePage(
            status=503, html=""
        ),
    }
    first = crawl(tmp_path, pages, max_retries=1)
    assert first.crawl_doc["pages_failed"] == 1

    healed = dict(pages)
    healed["https://catalog.example.edu/courses/engl101"] = ENGL
    calls: list[str] = []
    second = crawl(tmp_path, healed, max_retries=1, calls=calls)
    assert calls == ["https://catalog.example.edu/courses/engl101"]
    assert second.crawl_doc["pages_failed"] == 0
    assert second.crawl_doc["pages_saved"] == 2
    assert second.exit_code == 0


def test_the_checkpoint_carries_the_frontier_and_the_seen_set(
    tmp_path: Path,
) -> None:
    crawl(tmp_path, PAGES, limit=1)
    state = saved_state(tmp_path)
    assert state["schema"] == "xtra-crawl-state-1"
    assert state["run_id"] == RUN
    assert state["saved"] == [SEED]
    assert sorted(state["frontier"]) == [
        "https://catalog.example.edu/courses/engl101",
        "https://catalog.example.edu/courses/math101",
    ]
    assert "catalog.example.edu/" in state["seen"]


def test_a_run_id_typed_with_hyphens_lands_in_the_same_folder(
    tmp_path: Path,
) -> None:
    store = open_store(str(tmp_path))
    config = CrawlSettings(
        seed_url=SEED,
        catalog_folder=FOLDER,
        run_id=RUN_PATH,
        target_uri=str(tmp_path),
        min_interval_in_seconds=0,
        max_interval_in_seconds=1,
    )
    outcome = run_crawl(
        config,
        store=store,
        fetcher_factory=fetcher_factory(PAGES),
        url_fetch=no_site_documents,
        resolve_url=lambda url: url,
        sleep=lambda seconds: None,
    )
    assert run_dir(tmp_path).is_dir()
    assert outcome.crawl_doc["run_id"] == RUN


def test_the_coverage_count_groups_urls_by_their_top_folder(
    tmp_path: Path,
) -> None:
    doc = crawl(tmp_path, PAGES).crawl_doc
    assert doc["discovered_by_first_path_segment"] == {
        "courses": 2,
        "(root)": 1,
    }


# --- a catalog that answers somewhere else ---------------------------------


def test_a_site_that_answers_on_another_host_is_crawled_there(
    tmp_path: Path, caplog
) -> None:
    """A renamed college redirects its whole catalog to the new host.

    Scoping to the typed host fetched every page and then threw it away as
    an off-site redirect, so the crawl saved nothing.
    """
    typed = "https://catalog.oldname.edu"
    answers = "https://catalog.newname.edu/"
    pages = {
        answers: FakePage(html='<a href="/courses/engl101">ENGL</a>'),
        "https://catalog.newname.edu/courses/engl101": ENGL,
    }
    with caplog.at_level(logging.WARNING):
        outcome = crawl(
            tmp_path,
            pages,
            seed_url=typed,
            resolve_url=lambda url: answers,
        )
    doc = outcome.crawl_doc
    assert doc["pages_saved"] == 2
    assert doc["seed_url"] == typed
    assert doc["resolved_seed_url"] == answers
    assert doc["skipped_by_reason"].get("redirect_out_of_scope") is None
    assert outcome.exit_code == 0
    assert "answers as" in caplog.text


def test_the_catalog_folder_still_comes_from_the_url_as_typed(
    tmp_path: Path,
) -> None:
    """Storage is named for what the operator asked for, redirect or not."""
    outcome = crawl(
        tmp_path,
        {"https://catalog.newname.edu/": FakePage(html="<p>hi</p>")},
        seed_url="https://catalog.oldname.edu",
        resolve_url=lambda url: "https://catalog.newname.edu/",
    )
    assert outcome.crawl_doc["catalog_folder"] == FOLDER
    assert run_dir(tmp_path).is_dir()


def test_the_frontier_and_seen_set_move_to_the_host_that_answers(
    tmp_path: Path,
) -> None:
    """Otherwise one page could be saved twice, once under each host."""
    from implementations.crawl import Crawler

    crawler = Crawler(
        CrawlSettings(
            seed_url="https://catalog.oldname.edu/",
            catalog_folder=FOLDER,
            run_id=RUN,
            target_uri=str(tmp_path),
            min_interval_in_seconds=0,
            max_interval_in_seconds=1,
        ),
        store=open_store(str(tmp_path)),
        fetcher_factory=fetcher_factory({}),
        url_fetch=no_site_documents,
        resolve_url=lambda url: "https://catalog.newname.edu/",
        sleep=lambda seconds: None,
    )
    crawler.enqueue("https://catalog.oldname.edu/courses/engl101")
    crawler.saved = ["https://catalog.oldname.edu/a"]
    crawler._saved_set = set(crawler.saved)

    crawler.resolve_entry_point()

    assert crawler.scope.host == "catalog.newname.edu"
    assert list(crawler.frontier) == [
        "https://catalog.newname.edu/courses/engl101"
    ]
    assert crawler.saved == ["https://catalog.newname.edu/a"]
    assert crawler.seen == {"catalog.newname.edu/courses/engl101"}


def test_a_seed_that_answers_where_it_was_asked_changes_nothing(
    tmp_path: Path, caplog
) -> None:
    with caplog.at_level(logging.WARNING):
        doc = crawl(tmp_path, PAGES, resolve_url=lambda url: SEED).crawl_doc
    assert doc["resolved_seed_url"] == SEED
    assert doc["pages_saved"] == 3
    assert "answers as" not in caplog.text


def test_a_stale_sitemap_on_the_old_host_still_feeds_the_crawl(
    tmp_path: Path,
) -> None:
    """The site kept the old name in its sitemap after being renamed."""
    typed = "https://catalog.oldname.edu"
    answers = "https://catalog.newname.edu/"
    ns = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
    urlset = (
        f"<urlset {ns}>"
        "<url><loc>https://catalog.oldname.edu/courses/engl101</loc></url>"
        "</urlset>"
    ).encode()
    documents = {
        "https://catalog.newname.edu/robots.txt": b"User-agent: *\n",
        "https://catalog.newname.edu/sitemap.xml": urlset,
    }
    pages = {
        answers: FakePage(html="<p>no links</p>"),
        "https://catalog.newname.edu/courses/engl101": ENGL,
    }
    calls: list[str] = []
    doc = crawl(
        tmp_path,
        pages,
        documents=documents,
        calls=calls,
        seed_url=typed,
        resolve_url=lambda url: answers,
    ).crawl_doc
    assert doc["sitemap_urls_found"] == 1
    assert doc["pages_saved"] == 2
    assert calls == [answers, "https://catalog.newname.edu/courses/engl101"]
    assert doc["skipped_by_reason"].get("out_of_scope") is None


# --- the manifest a run leaves behind ---------------------------------------


def test_a_checkpoint_exists_before_the_first_get_and_after_the_first_page(
    tmp_path: Path,
) -> None:
    """A run killed at page two still has to describe itself."""
    seen: dict[str, dict] = {}

    def snapshot(url: str) -> None:
        seen[url] = newest_checkpoint(tmp_path)
        report = run_dir(tmp_path) / "crawl.json"
        seen[url]["report_written"] = report.exists()

    crawl(tmp_path, PAGES, before=snapshot)

    at_start = seen[SEED]
    assert at_start["schema"] == "xtra-crawl-checkpoint-1"
    assert at_start["crawl"]["status"] == STATUS_INCOMPLETE
    assert at_start["crawl"]["pages_saved"] == 0
    assert at_start["state"]["schema"] == "xtra-crawl-state-1"
    assert at_start["report_written"] is False

    after_one = seen["https://catalog.example.edu/courses/engl101"]
    assert after_one["crawl"]["status"] == STATUS_INCOMPLETE
    assert after_one["crawl"]["pages_saved"] == 1
    assert after_one["state"]["saved"] == [SEED]
    assert after_one["state"]["frontier"]
    assert after_one["report_written"] is False


def test_a_startup_checkpoint_alone_is_not_something_to_resume_from(
    tmp_path: Path,
) -> None:
    """The seed still has to be queued after a run that saved nothing."""
    store = open_store(str(tmp_path))
    store.put_json(
        checkpoint_key(FOLDER, RUN, 1),
        {
            "schema": "xtra-crawl-checkpoint-1",
            "crawl": {},
            "state": {
                "schema": "xtra-crawl-state-1",
                "strategy": "playwright",
                "frontier": [],
                "seen": [],
                "saved": [],
                "failed": [],
            },
        },
    )
    outcome = crawl(tmp_path, PAGES)
    assert outcome.crawl_doc["pages_saved"] == 3
    assert outcome.crawl_doc["status"] == STATUS_COMPLETE


def test_a_crawl_writes_each_file_once_and_keeps_the_newest_checkpoints(
    tmp_path: Path, monkeypatch
) -> None:
    """A checkpoint is never rewritten; older ones are deleted instead."""
    monkeypatch.setattr("implementations.crawl.CHECKPOINT_EVERY", 1)
    written: list[str] = []
    put_bytes = ObjectStore.put_bytes

    def recording_put(self, key, data, content_type="application/octet-stream"):
        written.append(key)
        return put_bytes(self, key, data, content_type)

    monkeypatch.setattr(ObjectStore, "put_bytes", recording_put)
    crawl(tmp_path, PAGES)
    assert len(written) == len(set(written))
    checkpoints = [
        key.rsplit("/", 1)[-1] for key in written if "/checkpoints/" in key
    ]
    # At startup, after each of the three pages, and at the end.
    assert checkpoints == [f"{n:06d}.json" for n in range(1, 6)]
    kept = [path.name for path in checkpoint_files(tmp_path)]
    assert kept == checkpoints[-CHECKPOINTS_KEPT:]


def test_a_resume_skips_a_checkpoint_it_cannot_read(
    tmp_path: Path, caplog
) -> None:
    """A run killed while writing one loses only what came after the last."""
    crawl(tmp_path, PAGES, limit=1)
    damaged = checkpoint_files(tmp_path)[-1]
    damaged.write_text('{"schema": "xtra-crawl-check', encoding="utf-8")
    stray = damaged.parent / "notes.txt"
    stray.write_text("not a checkpoint", encoding="utf-8")

    calls: list[str] = []
    with caplog.at_level(logging.WARNING):
        doc = crawl(tmp_path, PAGES, calls=calls).crawl_doc
    assert sorted(calls) == [
        "https://catalog.example.edu/courses/engl101",
        "https://catalog.example.edu/courses/math101",
    ]
    assert doc["pages_saved"] == 3
    assert f"CHECKPOINT {FOLDER}/{RUN_PATH}/checkpoints/{damaged.name} " in (
        caplog.text
    )
    assert damaged.read_text(encoding="utf-8") == '{"schema": "xtra-crawl-check'
    assert checkpoint_files(tmp_path)[-1].name > damaged.name
    assert stray.read_text(encoding="utf-8") == "not a checkpoint"


def test_a_run_from_before_checkpoint_files_resumes_from_its_state_json(
    tmp_path: Path,
) -> None:
    crawl(tmp_path, PAGES, limit=1)
    legacy = tmp_path / state_key(FOLDER, RUN)
    legacy.write_text(json.dumps(saved_state(tmp_path)), encoding="utf-8")
    shutil.rmtree(run_dir(tmp_path) / "checkpoints")
    before = legacy.read_bytes()

    calls: list[str] = []
    doc = crawl(tmp_path, PAGES, calls=calls).crawl_doc
    assert sorted(calls) == [
        "https://catalog.example.edu/courses/engl101",
        "https://catalog.example.edu/courses/math101",
    ]
    assert doc["pages_saved"] == 3
    assert legacy.read_bytes() == before
    assert checkpoint_files(tmp_path)


# --- which backend fetched which page ---------------------------------------


def test_the_sidecar_names_the_backend_that_fetched_the_page(
    tmp_path: Path,
) -> None:
    crawl(tmp_path, PAGES, strategy="crawl4ai")
    stem = page_stem("https://catalog.example.edu/courses/engl101")
    meta = json.loads(
        (run_dir(tmp_path) / "pages" / f"{stem}.meta.json").read_text(
            encoding="utf-8"
        )
    )
    assert meta["strategy"] == "crawl4ai"


def test_crawl_json_records_the_versions_that_actually_ran(
    tmp_path: Path,
) -> None:
    """Read from the installed packages, so it cannot drift from reality."""
    doc = crawl(tmp_path, PAGES).crawl_doc
    assert doc["strategy_version"]["python"] == platform.python_version()
    assert doc["strategy_version"]["playwright"] == version("playwright")


def test_crawl_json_records_what_the_backend_was_given(tmp_path: Path) -> None:
    settings = crawl(tmp_path, PAGES).crawl_doc["strategy_settings"]
    assert settings["timeout_ms"] == DEFAULT_TIMEOUT_MS
    assert settings["viewport"] == VIEWPORT
    assert settings["user_agent"]


def test_crawl_json_says_what_the_backend_only_approximates(
    tmp_path: Path,
) -> None:
    notes = crawl(tmp_path, PAGES).crawl_doc["strategy_notes"]
    assert notes
    assert all(isinstance(note, str) for note in notes)
    assert notes == list(strategy_facts("playwright").notes)


def test_a_resume_with_another_backend_is_refused(tmp_path: Path) -> None:
    """One run folder is one rendered source, or nothing downstream holds."""
    crawl(tmp_path, PAGES, limit=1, strategy="playwright")
    assert saved_state(tmp_path)["strategy"] == "playwright"

    with pytest.raises(StrategyMismatchError) as refused:
        crawl(tmp_path, PAGES, strategy="crawl4ai")
    message = str(refused.value)
    assert "--with-playwright" in message
    assert "--with-crawl4ai" in message

    resumed = crawl(tmp_path, PAGES, strategy="playwright")
    assert resumed.crawl_doc["pages_saved"] == 3


# --- saying so when the folder or the scope does not match the catalog ------


def test_a_folder_named_after_a_host_that_does_not_answer_says_so(
    tmp_path: Path, caplog
) -> None:
    typed = "https://catalog.oldname.edu"
    answers = "https://catalog.newname.edu/"
    with caplog.at_level(logging.WARNING):
        doc = crawl(
            tmp_path,
            {answers: FakePage(html="<p>one page</p>")},
            seed_url=typed,
            resolve_url=lambda url: answers,
        ).crawl_doc
    folder = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("FOLDER ")
    ]
    assert len(folder) == 1
    assert FOLDER in folder[0]
    assert "catalog.oldname.edu" in folder[0]
    assert "catalog.newname.edu" in folder[0]
    assert doc["catalog_folder_matches_resolved_host"] is False
    assert doc["resolved_seed_url"] == answers


def test_a_folder_that_matches_the_host_that_answers_says_nothing(
    tmp_path: Path, caplog
) -> None:
    with caplog.at_level(logging.WARNING):
        doc = crawl(tmp_path, PAGES).crawl_doc
    assert doc["catalog_folder_matches_resolved_host"] is True
    assert not [
        record
        for record in caplog.records
        if record.getMessage().startswith("FOLDER ")
    ]


def test_a_scope_narrower_than_the_site_root_says_so(
    tmp_path: Path, caplog
) -> None:
    seed = "https://catalog.example.edu/psychology/psyc101"
    with caplog.at_level(logging.WARNING):
        doc = crawl(
            tmp_path, {seed: FakePage(html="<p>one page</p>")}, seed_url=seed
        ).crawl_doc
    scope = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("SCOPE ")
    ]
    assert len(scope) == 1
    assert "the scope prefix is /psychology/" in scope[0]
    assert "--scope-prefix https://catalog.example.edu/" in scope[0]
    assert doc["scope_prefix"] == "/psychology/"


def test_a_crawl_of_a_whole_site_says_nothing_about_the_scope(
    tmp_path: Path, caplog
) -> None:
    with caplog.at_level(logging.WARNING):
        crawl(tmp_path, PAGES)
    assert not [
        record
        for record in caplog.records
        if record.getMessage().startswith("SCOPE ")
    ]


# --- what the frontier reaches first ----------------------------------------

SITEMAP_NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
HANDBOOK_LINKS = (
    '<a href="/handbook/1">1</a><a href="/handbook/2">2</a>'
    '<a href="/handbook/3">3</a>'
)


def urlset(*paths: str) -> bytes:
    entries = "".join(
        f"<url><loc>https://catalog.example.edu{path}</loc></url>"
        for path in paths
    )
    return f"<urlset {SITEMAP_NS}>{entries}</urlset>".encode()


def handbook_and_courses() -> dict:
    pages = {SEED: FakePage(html=HANDBOOK_LINKS)}
    for path in ("/handbook/1", "/handbook/2", "/handbook/3"):
        pages[f"https://catalog.example.edu{path}"] = FakePage(html="<p>h</p>")
    for path in ("/courses/a", "/courses/b", "/courses/c"):
        pages[f"https://catalog.example.edu{path}"] = ENGL
    return pages


def test_the_sitemap_is_reached_before_links_found_on_the_way(
    tmp_path: Path,
) -> None:
    """A limited run spends its pages on the site's own index of content."""
    documents = {
        "https://catalog.example.edu/robots.txt": b"User-agent: *\n",
        "https://catalog.example.edu/sitemap.xml": urlset(
            "/courses/a", "/courses/b", "/courses/c"
        ),
    }
    calls: list[str] = []
    doc = crawl(
        tmp_path,
        handbook_and_courses(),
        documents=documents,
        calls=calls,
        limit=4,
    ).crawl_doc
    assert doc["pages_saved"] == 4
    assert calls == [
        SEED,
        "https://catalog.example.edu/courses/a",
        "https://catalog.example.edu/courses/b",
        "https://catalog.example.edu/courses/c",
    ]
    assert doc["frontier_order"] == FRONTIER_ORDER


def test_a_resume_puts_sitemap_urls_ahead_of_the_old_frontier(
    tmp_path: Path,
) -> None:
    """The first pass queued one section; the sitemap must not wait for it."""
    pages = handbook_and_courses()
    first = crawl(tmp_path, pages, limit=1)
    assert first.crawl_doc["frontier_remaining"] == 3

    documents = {
        "https://catalog.example.edu/robots.txt": b"User-agent: *\n",
        "https://catalog.example.edu/sitemap.xml": urlset(
            "/courses/a", "/courses/b", "/courses/c"
        ),
    }
    calls: list[str] = []
    doc = crawl(
        tmp_path, pages, documents=documents, calls=calls, limit=3
    ).crawl_doc
    assert calls == [
        "https://catalog.example.edu/courses/a",
        "https://catalog.example.edu/courses/b",
    ]
    assert doc["pages_saved"] == 3


def test_a_seed_urls_file_is_queued_after_the_sitemap(tmp_path: Path) -> None:
    documents = {
        "https://catalog.example.edu/robots.txt": b"User-agent: *\n",
        "https://catalog.example.edu/sitemap.xml": urlset("/courses/a"),
    }
    pages = handbook_and_courses()
    calls: list[str] = []
    crawl(
        tmp_path,
        pages,
        documents=documents,
        calls=calls,
        limit=3,
        seed_urls=("https://catalog.example.edu/courses/b",),
    )
    assert calls == [
        SEED,
        "https://catalog.example.edu/courses/a",
        "https://catalog.example.edu/courses/b",
    ]


# --- a catalog that lists its pages in its own shell -------------------------

ROBOTS = "https://catalog.example.edu/robots.txt"
SITEMAP = "https://catalog.example.edu/sitemap.xml"
INDEXED = (
    "https://catalog.example.edu/iq/10",
    "https://catalog.example.edu/iq/20",
)


def curriqunet_site(seed: str = SEED) -> dict[str, bytes]:
    """A CurriQunet shell at the seed whose index lists two pages."""
    roots = [
        cq_node(10, "10", "root", text="Cover"),
        cq_node(20, "20", "root", text="Programs"),
    ]
    return curriqunet_documents(seed, roots)


def indexed_pages() -> dict:
    """The handbook site, plus the two pages the index lists."""
    pages = handbook_and_courses()
    for url in INDEXED:
        pages[url] = FakePage(html="<p>rendered by the browser</p>")
    return pages


def test_index_pages_come_after_the_sitemap_and_before_seed_urls(
    tmp_path: Path,
) -> None:
    documents = {
        ROBOTS: b"User-agent: *\n",
        SITEMAP: urlset("/courses/a"),
        **curriqunet_site(),
    }
    calls: list[str] = []
    crawl(
        tmp_path,
        indexed_pages(),
        documents=documents,
        calls=calls,
        limit=5,
        seed_urls=("https://catalog.example.edu/courses/b",),
    )
    assert calls == [
        SEED,
        "https://catalog.example.edu/courses/a",
        *INDEXED,
        "https://catalog.example.edu/courses/b",
    ]


def test_crawl_json_records_the_index_the_seed_declared(
    tmp_path: Path,
) -> None:
    doc = crawl(
        tmp_path, indexed_pages(), documents=curriqunet_site()
    ).crawl_doc
    index = doc["site_index"]
    assert index["kind"] == INDEX_KIND
    assert index["catalog_id"] == CQ_CATALOG
    assert index["url_base"] == "https://catalog.example.edu/iq/"
    assert index["urls_found"] == 2
    assert index["errors"] == 0
    assert doc["schema"] == "xtra-crawl-2"
    assert doc["pages_saved"] == 6


def test_the_index_walk_is_paced_between_its_requests(tmp_path: Path) -> None:
    sleeps: list[float] = []
    doc = crawl(
        tmp_path, indexed_pages(), documents=curriqunet_site(), sleeps=sleeps
    ).crawl_doc
    requests = doc["site_index"]["requests"]
    assert requests > 1
    assert sleeps.count(INDEX_INTERVAL_SECONDS) == requests - 1


def test_a_site_without_an_index_records_null_after_one_get_of_the_seed(
    tmp_path: Path,
) -> None:
    url_calls: list[str] = []
    doc = crawl(tmp_path, PAGES, url_calls=url_calls).crawl_doc
    assert doc["site_index"] is None
    assert url_calls == [ROBOTS, SITEMAP, SEED]


def test_a_seed_robots_disallows_is_not_read_for_an_index_either(
    tmp_path: Path,
) -> None:
    documents = {ROBOTS: b"User-agent: *\nDisallow: /\n", **curriqunet_site()}
    url_calls: list[str] = []
    doc = crawl(
        tmp_path, indexed_pages(), documents=documents, url_calls=url_calls
    ).crawl_doc
    assert SEED not in url_calls
    assert doc["site_index"] is None
    assert doc["pages_saved"] == 0


def test_index_pages_outside_the_scope_prefix_are_skipped(
    tmp_path: Path,
) -> None:
    seed = "https://catalog.example.edu/catalog/view/"
    roots = [
        cq_node(10, "10", "root", text="Cover"),
        cq_node(20, "20", "root", text="Programs"),
    ]
    children = {20: [cq_node(21, "20/21"), cq_node(22, "20/22")]}
    base = "https://catalog.example.edu/catalog/view/iq/"
    pages = {seed: HOME}
    for path in ("10", "20", "20/21", "20/22"):
        pages[base + path] = FakePage(html="<p>page</p>")
    calls: list[str] = []
    doc = crawl(
        tmp_path,
        pages,
        documents=curriqunet_documents(seed, roots, children),
        calls=calls,
        seed_url=seed,
        scope_prefix=base + "20/",
    ).crawl_doc
    assert doc["site_index"]["urls_found"] == 4
    assert calls == [base + "20/21", base + "20/22"]
    # The seed, the cover, and the programs page sit above the prefix.
    assert doc["skipped_by_reason"]["out_of_scope"] == 3


def test_a_resume_reads_the_index_and_puts_it_ahead_of_the_old_frontier(
    tmp_path: Path,
) -> None:
    """A run started before the index was read still gets its pages first."""
    pages = indexed_pages()
    first = crawl(tmp_path, pages, limit=1)
    assert first.crawl_doc["site_index"] is None
    assert first.crawl_doc["frontier_remaining"] == 3

    calls: list[str] = []
    doc = crawl(
        tmp_path, pages, documents=curriqunet_site(), calls=calls, limit=3
    ).crawl_doc
    assert calls == list(INDEXED)
    assert doc["site_index"]["urls_found"] == 2
    assert doc["pages_saved"] == 3


# --- what the backend says about how it rendered -----------------------------


def test_the_render_record_lands_in_the_sidecar(tmp_path: Path) -> None:
    render = {"waited_for": "network_idle", "capped": False, "waited_ms": 840}
    pages = dict(PAGES)
    pages[SEED] = FakePage(html=HOME.html, render=render)
    crawl(tmp_path, pages)

    def meta(url: str) -> dict:
        path = run_dir(tmp_path) / "pages" / f"{page_stem(url)}.meta.json"
        return json.loads(path.read_text(encoding="utf-8"))

    assert meta(SEED)["render"] == render
    assert "render" not in meta("https://catalog.example.edu/courses/engl101")


# --- a firewall's interstitial is not a page ---------------------------------

# What AWS WAF served, with HTTP 202, for every page of one Acalog catalog.
AWS_WAF_PAGE = (
    "<html><head><script>window.gokuProps = {};</script>"
    '<script src="https://x.token.awswaf.com/x/challenge.js"></script>'
    '</head><body><div id="challenge-container"></div>'
    "<script>AwsWafIntegration.getToken()</script></body></html>"
)
CLOUDFLARE_PAGE = (
    "<html><head><title>Just a moment...</title></head><body>"
    "<script>window._cf_chl_opt={cvId:'3'};</script></body></html>"
)


@pytest.mark.parametrize(
    ("status", "html", "kind"),
    [(202, AWS_WAF_PAGE, "aws-waf"), (200, CLOUDFLARE_PAGE, "cloudflare")],
)
def test_a_challenge_page_is_retried_and_never_saved(
    tmp_path: Path, status: int, html: str, kind: str
) -> None:
    calls: list[str] = []
    sleeps: list[float] = []
    outcome = crawl(
        tmp_path,
        {SEED: FakePage(status=status, html=html)},
        calls=calls,
        sleeps=sleeps,
        max_retries=2,
        min_interval_in_seconds=1,
        max_interval_in_seconds=5,
    )
    assert calls == [SEED, SEED, SEED]
    assert sleeps == [1, 2]
    assert outcome.crawl_doc["pages_saved"] == 0
    assert outcome.exit_code == 1
    assert not list((run_dir(tmp_path) / "pages").glob("*.html"))
    lines = (
        (run_dir(tmp_path) / "failed.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    record = json.loads(lines[0])
    assert record["url"] == SEED
    assert record["error"] == f"{kind} challenge page"
    assert record["http_status"] == status
    # Retryable, so a resume asks for the page again.
    assert record["retryable"] is True


def test_a_challenge_followed_by_the_real_page_saves_the_real_page(
    tmp_path: Path, caplog
) -> None:
    pages = dict(PAGES)
    pages[SEED] = [FakePage(status=202, html=AWS_WAF_PAGE), HOME]
    with caplog.at_level(logging.INFO):
        doc = crawl(tmp_path, pages).crawl_doc
    assert doc["pages_saved"] == 3
    assert doc["pages_failed"] == 0
    saved = (run_dir(tmp_path) / "pages" / f"{page_stem(SEED)}.html").read_text(
        encoding="utf-8"
    )
    assert saved == HOME.html
    assert f"RETRY {SEED} attempt 2 of 6 after aws-waf challenge page" in (
        caplog.text
    )


# --- a challenge page an older crawl saved is fetched again ------------------

ENGL_URL = "https://catalog.example.edu/courses/engl101"
MATH_URL = "https://catalog.example.edu/courses/math101"
POISONED = {**PAGES, ENGL_URL: FakePage(status=202, html=AWS_WAF_PAGE)}


def crawl_before_challenges_were_caught(
    tmp_path: Path, pages: dict, **settings
):
    """A run made by code that saved challenge pages as if they were pages.

    That code is gone, so it is played by switching the check off.
    """
    with pytest.MonkeyPatch.context() as old_code:
        old_code.setattr(
            "implementations.crawl.challenge_kind", lambda *args: None
        )
        return crawl(tmp_path, pages, **settings)


def saved_html(tmp_path: Path, url: str) -> str:
    path = run_dir(tmp_path) / "pages" / f"{page_stem(url)}.html"
    return path.read_text(encoding="utf-8")


def test_a_resume_fetches_a_stored_challenge_page_again_and_counts_it_once(
    tmp_path: Path, caplog
) -> None:
    first = crawl_before_challenges_were_caught(tmp_path, POISONED).crawl_doc
    assert first["pages_saved"] == 3
    assert saved_html(tmp_path, ENGL_URL) == AWS_WAF_PAGE

    calls: list[str] = []
    with caplog.at_level(logging.INFO):
        doc = crawl(tmp_path, PAGES, calls=calls).crawl_doc
    assert calls == [ENGL_URL]
    assert doc["status"] == STATUS_COMPLETE
    assert doc["pages_saved"] == 3
    assert doc["total_bytes"] == sum(
        len(page.html.encode("utf-8")) for page in PAGES.values()
    )
    assert saved_html(tmp_path, ENGL_URL) == ENGL.html
    assert sorted(saved_state(tmp_path)["saved"]) == sorted(PAGES)

    refetch = [
        record
        for record in caplog.records
        if record.getMessage().startswith("REFETCH ")
    ]
    assert len(refetch) == 1
    assert refetch[0].levelno == logging.WARNING
    assert (
        refetch[0]
        .getMessage()
        .startswith(
            f"REFETCH {ENGL_URL} stored page is a bot challenge (aws-waf)"
        )
    )
    assert f"FROM-STORAGE {SEED} " in caplog.text
    assert f"FROM-STORAGE {ENGL_URL} " not in caplog.text


def test_a_stored_challenge_page_still_challenged_is_a_failure_not_a_page(
    tmp_path: Path,
) -> None:
    crawl_before_challenges_were_caught(tmp_path, POISONED)

    still = crawl(tmp_path, POISONED, max_retries=1)
    assert still.crawl_doc["pages_saved"] == 2
    assert still.crawl_doc["pages_failed"] == 1
    assert still.exit_code == 1
    state = saved_state(tmp_path)
    assert ENGL_URL not in state["saved"]
    assert [record["url"] for record in state["failed"]] == [ENGL_URL]
    assert state["failed"][0]["error"] == "aws-waf challenge page"
    assert state["failed"][0]["retryable"] is True

    # Counted once when it finally comes through, not once per resume.
    calls: list[str] = []
    healed = crawl(tmp_path, PAGES, calls=calls)
    assert calls == [ENGL_URL]
    assert healed.crawl_doc["pages_saved"] == 3
    assert healed.crawl_doc["pages_failed"] == 0
    assert healed.exit_code == 0


def test_a_limited_resume_counts_only_the_real_pages(tmp_path: Path) -> None:
    """Counting the challenge page would have spent the limit before it."""
    crawl_before_challenges_were_caught(tmp_path, POISONED)
    calls: list[str] = []
    doc = crawl(tmp_path, PAGES, calls=calls, limit=3).crawl_doc
    assert calls == [ENGL_URL]
    assert doc["pages_saved"] == 3
    assert doc["status"] == STATUS_COMPLETE


def test_repairing_a_run_still_checkpoints_every_so_many_saves(
    tmp_path: Path, caplog, monkeypatch
) -> None:
    """Each repair takes a page off the total and puts it back.

    A checkpoint due at a total the run already had was never reached,
    so a long repair went without a checkpoint or a PROGRESS line.
    """
    monkeypatch.setattr("implementations.crawl.CHECKPOINT_EVERY", 2)
    leaves = [f"https://catalog.example.edu/courses/c{n}" for n in range(6)]
    seed = FakePage(html="".join(f'<a href="{url}">c</a>' for url in leaves))
    walled = {url: FakePage(status=202, html=AWS_WAF_PAGE) for url in leaves}
    crawl_before_challenges_were_caught(tmp_path, {SEED: seed, **walled})

    real = {url: FakePage(html=f"<h1>{url}</h1>") for url in leaves}
    caplog.clear()
    with caplog.at_level(logging.INFO):
        doc = crawl(tmp_path, {SEED: seed, **real}).crawl_doc
    assert doc["pages_saved"] == 7
    progress = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("PROGRESS ")
    ]
    # One every two of the six repairs, and the one at the end.
    assert len(progress) == 4


def test_pages_read_back_from_storage_do_not_hide_a_site_that_blocks_every_fetch(
    tmp_path: Path,
) -> None:
    """A replay is not a GET, so it must not reset the failures in a row."""
    links: list[str] = []
    pages: dict = {}
    for n in range(21):
        real = f"https://catalog.example.edu/courses/r{n}"
        walled = f"https://catalog.example.edu/courses/c{n}"
        links += [real, walled]
        pages[real] = FakePage(html=f"<h1>R{n}</h1>")
        pages[walled] = FakePage(status=202, html=AWS_WAF_PAGE)
    pages[SEED] = FakePage(
        html="".join(f'<a href="{url}">x</a>' for url in links)
    )
    crawl_before_challenges_were_caught(tmp_path, pages)

    outcome = crawl(tmp_path, pages, max_retries=0)
    assert outcome.crawl_doc["status"] == STATUS_INCOMPLETE
    assert outcome.crawl_doc["pages_failed"] == 20
    assert outcome.exit_code == 1


def test_ctrl_c_keeps_the_page_being_fetched_for_the_resume(
    tmp_path: Path,
) -> None:
    """The page in flight was in seen but in no list, so it was lost."""
    from concurrent.futures import wait as real_wait

    engl_in_flight = threading.Event()

    def note_engl(url: str) -> None:
        if url == ENGL_URL:
            engl_in_flight.set()

    def ctrl_c_once_engl_is_in_flight(*args, **kwargs):
        done = real_wait(*args, **kwargs)
        if engl_in_flight.is_set():
            raise KeyboardInterrupt
        return done

    with pytest.MonkeyPatch.context() as keyboard:
        keyboard.setattr(
            "implementations.crawl.wait_for_futures",
            ctrl_c_once_engl_is_in_flight,
        )
        stopped = crawl(tmp_path, PAGES, before=note_engl)
    assert stopped.exit_code == 130
    assert stopped.crawl_doc["frontier_remaining"] == 2
    state = saved_state(tmp_path)
    assert state["saved"] == [SEED]
    assert state["frontier"] == [ENGL_URL, MATH_URL]

    calls: list[str] = []
    resumed = crawl(tmp_path, PAGES, calls=calls)
    assert calls == [ENGL_URL, MATH_URL]
    assert resumed.crawl_doc["pages_saved"] == 3
    assert resumed.exit_code == 0


def test_ctrl_c_checkpoints_before_waiting_for_the_browsers_to_close(
    tmp_path: Path,
) -> None:
    """Closing waits for the fetch in flight, and the run can die meanwhile.

    ENGL is saved after the first-page checkpoint and MATH is in flight
    when Ctrl+C lands, so only a checkpoint written before the close
    names both.
    """
    from concurrent.futures import wait as real_wait

    from implementations.crawl_browser import WorkerPool

    math_in_flight = threading.Event()

    def note_math(url: str) -> None:
        if url == MATH_URL:
            math_in_flight.set()

    def ctrl_c_once_math_is_in_flight(*args, **kwargs):
        done = real_wait(*args, **kwargs)
        if math_in_flight.is_set():
            raise KeyboardInterrupt
        return done

    class KilledWhileClosing(WorkerPool):
        def close(self) -> None:
            super().close()
            raise RuntimeError("killed while the browsers close")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            "implementations.crawl.wait_for_futures",
            ctrl_c_once_math_is_in_flight,
        )
        patch.setattr("implementations.crawl.WorkerPool", KilledWhileClosing)
        with pytest.raises(RuntimeError, match="killed while the browsers"):
            crawl(tmp_path, PAGES, before=note_math)
    state = saved_state(tmp_path)
    assert state["saved"] == [SEED, ENGL_URL]
    assert state["frontier"] == [MATH_URL]
    assert state["pages_saved"] == 2


def test_a_page_listed_as_saved_and_queued_goes_back_once_on_resume(
    tmp_path: Path,
) -> None:
    """A checkpoint written before a page is read back lists it twice.

    Every resume's startup checkpoint does, and so does each one written
    while a repair is still reading pages back. Queued twice, a stored
    challenge page was fetched twice and, with two workers, counted twice.
    """
    crawl_before_challenges_were_caught(tmp_path, POISONED)
    path = checkpoint_files(tmp_path)[-1]
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["state"]["frontier"] = list(doc["state"]["saved"])
    path.write_text(json.dumps(doc), encoding="utf-8")

    calls: list[str] = []
    doc = crawl(tmp_path, PAGES, calls=calls, concurrency_limit=2).crawl_doc
    assert calls == [ENGL_URL]
    assert doc["pages_saved"] == 3
    assert doc["total_bytes"] == sum(
        len(page.html.encode("utf-8")) for page in PAGES.values()
    )
    assert sorted(saved_state(tmp_path)["saved"]) == sorted(PAGES)


def test_a_saved_page_missing_from_storage_is_fetched_and_counted_once(
    tmp_path: Path,
) -> None:
    """Saving a URL the run already counted replaces it, not adds to it."""
    crawl(tmp_path, PAGES)
    (run_dir(tmp_path) / "pages" / f"{page_stem(ENGL_URL)}.html").unlink()

    calls: list[str] = []
    doc = crawl(tmp_path, PAGES, calls=calls).crawl_doc
    assert calls == [ENGL_URL]
    assert doc["pages_saved"] == 3
    assert saved_html(tmp_path, ENGL_URL) == ENGL.html


def test_pages_read_back_without_a_checkpoint_still_checkpoint_as_they_go(
    tmp_path: Path, caplog, monkeypatch
) -> None:
    """With the checkpoints gone, pages read back are this run's saves."""
    monkeypatch.setattr("implementations.crawl.CHECKPOINT_EVERY", 2)
    leaves = [f"https://catalog.example.edu/courses/l{n}" for n in range(4)]
    pages = {
        SEED: FakePage(
            html="".join(f'<a href="{url}">l</a>' for url in leaves)
        ),
        **{url: FakePage(html=f"<h1>{url}</h1>") for url in leaves},
    }
    crawl(tmp_path, pages)
    shutil.rmtree(run_dir(tmp_path) / "checkpoints")

    calls: list[str] = []
    caplog.clear()
    with caplog.at_level(logging.INFO):
        doc = crawl(tmp_path, pages, calls=calls).crawl_doc
    assert calls == []
    assert doc["pages_saved"] == 5
    progress = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("PROGRESS ")
    ]
    # After the 2nd and 4th pages read back past the first, and at the end.
    assert len(progress) == 3


LIST = "https://catalog.example.edu/courses"


def course_url(code: str) -> str:
    return f"https://catalog.example.edu/courses/{code}"


def button_list_site(*, opens_by_number: bool = True) -> dict:
    """A home page that links to a course list of three button-paged pages.

    Each list page names two courses and lands where the site rewrites it
    to, ?page=N&cq=. A list that does not open by number shows its first
    page whatever the address asks for.
    """
    pages = {SEED: FakePage(html='<a href="/courses">Courses</a>')}
    for asked in (1, 2, 3):
        shown = asked if opens_by_number else 1
        codes = [f"C{shown}{i}" for i in (1, 2)]
        pages[LIST if asked == 1 else f"{LIST}?page={asked}"] = FakePage(
            html=list_page(shown, 3, codes),
            final_url=f"{LIST}?page={shown}&cq=",
        )
        for code in codes:
            pages[course_url(code)] = FakePage(html=f"<h1>{code}</h1>")
    return pages


def list_lines(caplog, level: int = logging.INFO) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= level and record.getMessage().startswith("LIST ")
    ]


def test_a_list_is_crawled_through_its_page_buttons(
    tmp_path: Path, caplog
) -> None:
    calls: list[str] = []
    with caplog.at_level(logging.INFO):
        doc = crawl(tmp_path, button_list_site(), calls=calls).crawl_doc
    courses = [course_url(f"C{n}{i}") for n in (1, 2, 3) for i in (1, 2)]
    assert doc["status"] == STATUS_COMPLETE
    assert doc["pages_saved"] == 10
    assert sorted(calls) == sorted(
        [SEED, LIST, f"{LIST}?page=2", f"{LIST}?page=3", *courses]
    )
    # The next list page goes ahead of the courses of the page that leads
    # to it, so a limited run goes down the list.
    assert calls[:3] == [SEED, LIST, f"{LIST}?page=2"]
    assert list_lines(caplog) == [
        f"LIST {LIST} is page 1 of 3; queued page 2 to check the list opens "
        "by page number",
        f"LIST {LIST}?page=2 opened as page 2 of 3; queued 1 more page(s) of "
        "the list",
    ]


def test_a_list_that_ignores_page_numbers_costs_one_page_and_a_warning(
    tmp_path: Path, caplog
) -> None:
    calls: list[str] = []
    with caplog.at_level(logging.INFO):
        doc = crawl(
            tmp_path, button_list_site(opens_by_number=False), calls=calls
        ).crawl_doc
    assert f"{LIST}?page=2" in calls
    assert f"{LIST}?page=3" not in calls
    # The home page, the list under two addresses, and its two courses.
    assert doc["pages_saved"] == 5
    assert list_lines(caplog, logging.WARNING) == [
        f"LIST {LIST}?page=2 asked for page 2 and the site showed page 1, so "
        "this list does not open by page number and the rest of it is not "
        "queued"
    ]


def test_list_pages_are_built_from_the_address_asked_for(
    tmp_path: Path,
) -> None:
    """Not from where the site rewrote it, which a resume never sees."""
    site = button_list_site()
    site[LIST] = FakePage(
        html=site[LIST].html, final_url=f"{LIST}?page=1&sort=code"
    )
    calls: list[str] = []
    crawl(tmp_path, site, calls=calls)
    assert f"{LIST}?page=2" in calls
    assert not [url for url in calls if "sort=code" in url]


def test_a_resume_builds_the_same_list_pages_and_fetches_none_twice(
    tmp_path: Path, caplog
) -> None:
    site = button_list_site()
    first: list[str] = []
    crawl(tmp_path, site, limit=3, calls=first)
    assert first == [SEED, LIST, f"{LIST}?page=2"]

    second: list[str] = []
    caplog.clear()
    with caplog.at_level(logging.INFO):
        doc = crawl(tmp_path, site, calls=second).crawl_doc
    assert not set(first) & set(second)
    assert len(second) == len(set(second)) == 7
    assert doc["pages_saved"] == 10
    assert doc["status"] == STATUS_COMPLETE
    # Reading the saved list pages back queues nothing new, so says nothing.
    assert list_lines(caplog) == []


def test_an_include_regex_still_decides_whether_list_pages_are_followed(
    tmp_path: Path,
) -> None:
    site = button_list_site()
    # Landing where it was asked keeps the seed inside "/courses/": the
    # address the site rewrites it to is tested against the regex too.
    site[LIST] = FakePage(html=site[LIST].html)
    calls: list[str] = []
    doc = crawl(
        tmp_path,
        site,
        seed_url=LIST,
        include_regex=("/courses/",),
        calls=calls,
    ).crawl_doc
    assert sorted(calls) == sorted([LIST, course_url("C11"), course_url("C12")])
    assert doc["skipped_by_reason"]["include_rule"] >= 1


def test_a_run_narrowed_to_the_course_list_still_pages_through_it(
    tmp_path: Path,
) -> None:
    """--include-regex /courses keeps /courses?page=N and /courses/CODE."""
    calls: list[str] = []
    doc = crawl(
        tmp_path, button_list_site(), include_regex=("/courses",), calls=calls
    ).crawl_doc
    assert doc["pages_saved"] == 10
    assert f"{LIST}?page=3" in calls
    assert doc["skipped_by_reason"].get("redirect_out_of_scope", 0) == 0


def test_a_list_saved_before_it_loaded_is_warned_about(
    tmp_path: Path, caplog
) -> None:
    pages = {
        SEED: FakePage(html='<a href="/courses">Courses</a>'),
        LIST: FakePage(html=list_site_page(LIST_LOADING)),
    }
    with caplog.at_level(logging.WARNING):
        doc = crawl(tmp_path, pages).crawl_doc
    assert doc["pages_saved"] == 2
    assert list_lines(caplog, logging.WARNING) == [
        f"LIST {LIST} was saved before its list loaded (Loading results...), "
        "so the pages after it are not known"
    ]


def test_a_row_that_marks_no_page_is_warned_about(
    tmp_path: Path, caplog
) -> None:
    row = (
        button_row(1, 3)
        .replace("btn-primary", "btn-secondary")
        .replace(' disabled=""', "")
    )
    pages = {
        SEED: FakePage(html='<a href="/courses">Courses</a>'),
        LIST: FakePage(html=list_site_page(row)),
    }
    calls: list[str] = []
    with caplog.at_level(logging.WARNING):
        crawl(tmp_path, pages, calls=calls)
    assert calls == [SEED, LIST]
    assert list_lines(caplog, logging.WARNING) == [
        f"LIST {LIST} has page buttons up to 3 but none marks the page on "
        "screen, so the rest of the list is not queued"
    ]


def test_a_list_longer_than_the_cap_is_queued_up_to_it_and_says_so(
    tmp_path: Path, caplog
) -> None:
    last = MAX_LIST_PAGES + 1
    pages = {
        SEED: FakePage(html='<a href="/courses">Courses</a>'),
        LIST: FakePage(html=list_page(1, last, ["C11"])),
        f"{LIST}?page=2": FakePage(html=list_page(2, last, ["C21"])),
    }
    with caplog.at_level(logging.WARNING):
        crawl(tmp_path, pages, limit=3)
    assert list_lines(caplog, logging.WARNING) == [
        f"LIST {LIST}?page=2 says the list has {last} pages; only pages up "
        f"to {MAX_LIST_PAGES} are queued"
    ]
    queued = [url for url in saved_state(tmp_path)["frontier"] if "?" in url]
    assert len(queued) == MAX_LIST_PAGES - 2
    assert queued[-1] == f"{LIST}?page={MAX_LIST_PAGES}"
