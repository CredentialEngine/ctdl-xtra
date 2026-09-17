from __future__ import annotations

import gzip
import json
import logging
import threading
from pathlib import Path

import pytest
from crawl_doubles import (
    FakePage,
    fetcher_factory,
    no_site_documents,
    site_documents,
)

from common.keys import page_html_key, page_stem, state_key
from common.object_store import open_store
from implementations.crawl import (
    STATUS_COMPLETE,
    STATUS_INCOMPLETE,
    STATUS_LIMIT_REACHED,
    CrawlSettings,
    format_duration,
    is_retryable_status,
    run_crawl,
)

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
    before=None,
    sleeps: list[float] | None = None,
    resolve_url=None,
    **settings,
):
    """Run one crawl into tmp_path with a fake browser and no network."""
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
        url_fetch=site_documents(documents) if documents else no_site_documents,
        resolve_url=resolve_url or (lambda url: url),
        sleep=sleeps.append if sleeps is not None else (lambda seconds: None),
    )


def run_dir(tmp_path: Path) -> Path:
    return tmp_path / FOLDER / RUN_PATH


# --- what a crawl saves ----------------------------------------------------


def test_a_crawl_saves_html_and_a_sidecar_and_nothing_else(tmp_path: Path) -> None:
    outcome = crawl(tmp_path, PAGES)
    assert outcome.crawl_doc["status"] == STATUS_COMPLETE
    assert outcome.crawl_doc["pages_saved"] == 3
    assert outcome.exit_code == 0

    names = sorted(path.name for path in run_dir(tmp_path).rglob("*") if path.is_file())
    assert [name for name in names if name.endswith(".txt")] == []
    assert "slots.json" not in names
    assert {"crawl.json", "state.json", "failed.jsonl"} <= set(names)
    assert len([name for name in names if name.endswith(".html")]) == 3
    assert len([name for name in names if name.endswith(".meta.json")]) == 3


def test_crawl_json_has_no_family_template_or_institution(tmp_path: Path) -> None:
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
        (run_dir(tmp_path) / "pages" / f"{stem}.meta.json").read_text(encoding="utf-8")
    )
    assert meta["requested_url"] == "https://catalog.example.edu/courses/engl101"
    assert meta["http_status"] == 200
    assert meta["bytes"] == len(ENGL.html.encode("utf-8"))
    assert meta["latency_ms"] == 7
    assert meta["attempts"] == 1
    assert meta["stem"] == stem
    assert len(meta["sha256"]) == 64
    assert "normalized" not in json.dumps(meta)


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
        page_html_key(FOLDER, RUN, page_stem("https://catalog.example.edu/courses/engl101"))
    )


def test_progress_is_logged_with_elapsed_and_an_eta(tmp_path: Path, caplog) -> None:
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
            html="<h1>moved</h1>", final_url="https://vendor.example.com/engl101"
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


def test_an_include_regex_narrows_what_links_are_followed(tmp_path: Path) -> None:
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


def test_a_scope_prefix_keeps_the_crawl_inside_one_section(tmp_path: Path) -> None:
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


def test_robots_disallow_keeps_a_section_out_of_the_crawl(tmp_path: Path) -> None:
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


def test_a_robots_crawl_delay_raises_the_effective_minimum(tmp_path: Path) -> None:
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


def test_a_larger_min_interval_wins_over_a_smaller_crawl_delay(tmp_path: Path) -> None:
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


def test_a_403_robots_is_recorded_and_treated_as_no_rules(tmp_path: Path) -> None:
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
        f'<sitemapindex {ns}><sitemap>'
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


def test_retries_back_off_from_the_minimum_up_to_the_maximum(tmp_path: Path) -> None:
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
        "https://catalog.example.edu/courses/gone": FakePage(status=404, html=""),
    }
    calls: list[str] = []
    sleeps: list[float] = []
    outcome = crawl(tmp_path, pages, calls=calls, sleeps=sleeps, max_retries=5)
    assert calls.count("https://catalog.example.edu/courses/gone") == 1
    assert sleeps == []
    assert outcome.crawl_doc["failed_by_status"] == {"404": 1}


def test_a_retry_line_names_the_attempt_and_the_wait(tmp_path: Path, caplog) -> None:
    pages = {SEED: [FakePage(status=429, html=""), FakePage(html="<p>ok</p>")]}
    with caplog.at_level(logging.INFO):
        crawl(tmp_path, pages, min_interval_in_seconds=1, max_interval_in_seconds=5)
    retries = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("RETRY ")
    ]
    assert retries == [f"RETRY {SEED} attempt 2 of 6 after HTTP 429, waiting 1 s"]


def test_a_fail_line_names_the_attempts_and_the_reason(tmp_path: Path, caplog) -> None:
    with caplog.at_level(logging.WARNING):
        crawl(tmp_path, {SEED: FakePage(status=503, html="")}, max_retries=5)
    fails = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("FAIL ")
    ]
    assert fails == [f"FAIL {SEED} after 6 attempts: HTTP 503"]


def test_failed_urls_are_written_one_json_object_per_line(tmp_path: Path) -> None:
    crawl(tmp_path, {SEED: FakePage(status=503, html="")}, max_retries=1)
    lines = (run_dir(tmp_path) / "failed.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
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


def test_three_workers_fetch_three_pages_at_the_same_time(tmp_path: Path) -> None:
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
    """Storage, not state.json, is what proves the page was already fetched."""
    crawl(tmp_path, PAGES, limit=1)
    (tmp_path / state_key(FOLDER, RUN)).unlink()

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
        "https://catalog.example.edu/courses/engl101": FakePage(status=503, html=""),
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


def test_the_checkpoint_carries_the_frontier_and_the_seen_set(tmp_path: Path) -> None:
    crawl(tmp_path, PAGES, limit=1)
    state = json.loads(
        (tmp_path / state_key(FOLDER, RUN)).read_text(encoding="utf-8")
    )
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


def test_the_coverage_count_groups_urls_by_their_top_folder(tmp_path: Path) -> None:
    doc = crawl(tmp_path, PAGES).crawl_doc
    assert doc["discovered_by_first_path_segment"] == {"courses": 2, "(root)": 1}


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
