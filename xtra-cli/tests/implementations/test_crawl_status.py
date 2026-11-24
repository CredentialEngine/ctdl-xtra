from __future__ import annotations

from pathlib import Path

from crawl_doubles import FakePage, fetcher_factory, site_documents

from common.object_store import open_store
from implementations.crawl import CrawlSettings, run_crawl
from implementations.crawl_status import (
    GROUP_FAILED,
    GROUP_SKIPPED,
    StatusRow,
    list_run_files,
    read_report,
    read_rows,
    render_csv,
    render_table,
    row_counts,
    run_started,
    totals_line,
)

SEED = "https://catalog.example.edu/"
FOLDER = "catalog-example-edu"
RUN = "2026-09-17T14:20:01Z"
LATER = "2026-09-18T09:00:00Z"
ENGL = "https://catalog.example.edu/courses/engl101"
GONE = "https://catalog.example.edu/courses/gone"
PDF = "https://catalog.example.edu/courses/handbook"
PAGES = {
    SEED: FakePage(
        html=(
            f'<a href="{ENGL}">e</a><a href="{GONE}">g</a><a href="{PDF}">p</a>'
        )
    ),
    ENGL: FakePage(html="<h1>ENGL 101</h1>"),
    PDF: FakePage(content_type="application/pdf", html=""),
}


def crawled(tmp_path: Path, run_id: str = RUN, **settings):
    store = open_store(str(tmp_path))
    run_crawl(
        CrawlSettings(
            seed_url=SEED,
            catalog_folder=FOLDER,
            run_id=run_id,
            target_uri=str(tmp_path),
            min_interval_in_seconds=0,
            max_interval_in_seconds=1,
            pacing_jitter_fraction=0,
            **settings,
        ),
        store=store,
        fetcher_factory=fetcher_factory(PAGES),
        url_fetch=site_documents({}),
        resolve_url=lambda url: url,
        sleep=lambda seconds: None,
    )
    return store


def rows_of(store, run_id: str = RUN, groups: frozenset = frozenset()):
    return read_rows(store, list_run_files(store, FOLDER, run_id), set(groups))


def line_of(store, run_id: str = RUN) -> str:
    return totals_line(
        list_run_files(store, FOLDER, run_id),
        read_report(store, FOLDER, run_id),
    )


def test_the_counts_come_from_the_pages_folder_alone(tmp_path: Path) -> None:
    files = list_run_files(crawled(tmp_path), FOLDER, RUN)
    assert files.counts() == {"failed": 1, "saved": 2, "skipped": 1}
    assert files.total() == 4


def test_the_totals_line_adds_what_crawl_json_says(tmp_path: Path) -> None:
    assert line_of(crawled(tmp_path)) == (
        "TOTAL failed=1 saved=2 skipped=1 urls=4 copied=0 fetched=2 "
        "run=complete frontier_remaining=0 updated_at="
        + read_report(open_store(str(tmp_path)), FOLDER, RUN)["updated_at"]
    )


def test_a_run_that_copied_says_from_where_and_how_many(
    tmp_path: Path,
) -> None:
    crawled(tmp_path)
    store = crawled(tmp_path, run_id=LATER, from_run_id=RUN)
    line = line_of(store, LATER)
    assert "saved=2" in line
    assert "copied=2 fetched=0" in line
    assert f"from_run={RUN}" in line


def test_every_url_asked_for_has_one_row(tmp_path: Path) -> None:
    rows = rows_of(crawled(tmp_path))
    results = {row.url: row.result for row in rows}
    assert results == {
        SEED: "saved",
        ENGL: "saved",
        GONE: "failed",
        PDF: "skipped-non_html",
    }
    assert row_counts(rows) == {
        "failed": 1,
        "saved": 2,
        "skipped-non_html": 1,
    }


def test_a_row_carries_what_its_meta_json_says(tmp_path: Path) -> None:
    rows = {row.url: row for row in rows_of(crawled(tmp_path))}
    assert rows[ENGL].http_status == 200
    assert rows[ENGL].bytes == len(b"<h1>ENGL 101</h1>")
    assert rows[ENGL].detail == ""
    assert rows[GONE].http_status == 404
    assert rows[GONE].detail == "HTTP 404"
    assert rows[PDF].detail == "non_html"


def test_a_copied_page_says_which_run_it_came_from(tmp_path: Path) -> None:
    crawled(tmp_path)
    store = crawled(tmp_path, run_id=LATER, from_run_id=RUN)
    rows = {row.url: row for row in rows_of(store, LATER)}
    assert rows[ENGL].detail == f"copied from {RUN}"
    assert rows[GONE].result == "failed"


def test_a_run_with_nothing_yet_has_no_rows_and_no_report(
    tmp_path: Path,
) -> None:
    store = open_store(str(tmp_path))
    assert rows_of(store) == []
    assert read_report(store, FOLDER, RUN) is None
    assert line_of(store) == "TOTAL urls=0 run=unknown (no such run yet)"


def test_a_run_that_is_going_says_so_and_keeps_its_counts_live(
    tmp_path: Path,
) -> None:
    store = crawled(tmp_path)
    (tmp_path / FOLDER / "2026-09-17T14-20-01Z" / "crawl.json").unlink()
    line = totals_line(
        list_run_files(store, FOLDER, RUN),
        read_report(store, FOLDER, RUN),
        started=run_started(store, FOLDER, RUN),
    )
    assert line == (
        "TOTAL failed=1 saved=2 skipped=1 urls=4 "
        "run=running (crawl.json is written when it ends)"
    )


def test_a_limited_run_counts_what_it_left_to_fetch(tmp_path: Path) -> None:
    store = crawled(tmp_path, limit=1)
    assert [row.url for row in rows_of(store)] == [SEED]
    line = line_of(store)
    assert "saved=1" in line
    assert "run=limit_reached" in line
    assert "frontier_remaining=3" in line


def test_filters_combine_and_none_means_all(tmp_path: Path) -> None:
    store = crawled(tmp_path)
    assert len(rows_of(store)) == 4
    assert {row.url for row in rows_of(store, groups={GROUP_FAILED})} == {GONE}
    both = rows_of(store, groups={GROUP_FAILED, GROUP_SKIPPED})
    assert {row.url for row in both} == {GONE, PDF}


def test_files_outside_the_three_groups_are_not_counted(
    tmp_path: Path,
) -> None:
    store = crawled(tmp_path)
    pages = tmp_path / FOLDER / "2026-09-17T14-20-01Z" / "pages"
    (pages / "other").mkdir()
    (pages / "other" / "x.meta.json").write_text("{}", encoding="utf-8")
    (pages / "failed" / "notes.txt").write_text("", encoding="utf-8")
    assert list_run_files(store, FOLDER, RUN).total() == 4


def test_the_table_lines_up_and_shortens_a_long_error() -> None:
    rows = [
        StatusRow("saved", "https://x.edu/a", 200, 1, 10, "t1", ""),
        StatusRow("failed", "https://x.edu/bb", None, 6, None, "t2", "e" * 100),
    ]
    lines = render_table(rows).splitlines()
    assert lines[0].split() == [
        "RESULT",
        "HTTP_STATUS",
        "ATTEMPTS",
        "BYTES",
        "AT",
        "URL",
        "DETAIL",
    ]
    column = lines[1].index("https://x.edu/a")
    assert lines[2].index("https://x.edu/bb") == column
    assert lines[2].endswith("...")
    assert len(lines[2].split()[-1]) == 60


def test_csv_has_a_header_and_one_line_per_row() -> None:
    rows = [StatusRow("saved", "https://x.edu/a,b", 200, 1, 10, "t1", "")]
    assert render_csv(rows).splitlines() == [
        "result,http_status,attempts,bytes,at,url,detail",
        'saved,200,1,10,t1,"https://x.edu/a,b",',
    ]
