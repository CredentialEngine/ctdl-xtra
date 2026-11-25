from __future__ import annotations

import csv
import io
from pathlib import Path

from click.testing import CliRunner
from crawl_doubles import FakePage, fetcher_factory, site_documents

from common.object_store import open_store
from implementations.crawl import CrawlSettings, run_crawl
from xtra.cli import cli

SEED = "https://catalog.example.edu/"
RUN = "2026-09-17T14:20:01Z"
NEXT = "2026-09-18T09:00:00Z"
GONE = "https://catalog.example.edu/courses/gone"


def crawled(tmp_path: Path, run_id: str = RUN, **settings) -> None:
    run_crawl(
        CrawlSettings(
            seed_url=SEED,
            catalog_folder="catalog-example-edu",
            run_id=run_id,
            target_uri=str(tmp_path),
            min_interval_in_seconds=0,
            max_interval_in_seconds=1,
            pacing_jitter_fraction=0,
            **settings,
        ),
        store=open_store(str(tmp_path)),
        fetcher_factory=fetcher_factory(
            {SEED: FakePage(html=f'<a href="{GONE}">g</a>')}
        ),
        url_fetch=site_documents({}),
        resolve_url=lambda url: url,
        sleep=lambda seconds: None,
    )


def summary(tmp_path: Path, *extra: str, run_id: str = RUN):
    return CliRunner().invoke(
        cli,
        [
            "catalog",
            "crawl",
            "summary",
            "--url",
            SEED,
            "--run-id",
            run_id,
            "--target-uri",
            str(tmp_path),
            *extra,
        ],
    )


def test_the_table_shows_each_url_and_a_totals_line(tmp_path: Path) -> None:
    crawled(tmp_path)
    result = summary(tmp_path)
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0].startswith("RESULT")
    assert any(line.startswith("saved") and SEED in line for line in lines)
    assert any(line.startswith("failed") and GONE in line for line in lines)
    assert lines[-1].startswith("TOTAL failed=1 saved=1 urls=2")
    assert "run=complete" in lines[-1]


def test_failed_shows_only_the_failures(tmp_path: Path) -> None:
    crawled(tmp_path)
    lines = summary(tmp_path, "--failed").output.splitlines()
    rows = [line for line in lines[1:] if not line.startswith("TOTAL")]
    assert len(rows) == 1
    assert GONE in rows[0]


def test_csv_is_readable_and_has_no_totals_line(tmp_path: Path) -> None:
    crawled(tmp_path)
    result = summary(tmp_path, "--format", "csv")
    assert "TOTAL" not in result.output
    rows = list(csv.DictReader(io.StringIO(result.output)))
    assert {row["url"]: row["result"] for row in rows} == {
        SEED: "saved",
        GONE: "failed",
    }


def test_a_copied_page_says_which_run_it_came_from(tmp_path: Path) -> None:
    crawled(tmp_path)
    crawled(tmp_path, run_id=NEXT, from_run_id=RUN)
    result = summary(tmp_path, "--saved", run_id=NEXT)
    assert result.exit_code == 0, result.output
    assert f"copied from {RUN}" in result.output
    assert f"from_run={RUN}" in result.output.splitlines()[-1]


def test_a_run_with_nothing_fetched_says_so(tmp_path: Path) -> None:
    result = summary(tmp_path)
    assert result.exit_code == 0, result.output
    assert "No pages match." in result.output
    assert "no such run yet" in result.output


def test_a_run_id_that_is_not_a_timestamp_is_a_usage_error(
    tmp_path: Path,
) -> None:
    result = summary(tmp_path, run_id="yesterday")
    assert result.exit_code == 2
    assert "--run-id" in result.output


def test_summary_is_a_subcommand_of_crawl() -> None:
    crawl_help = CliRunner().invoke(cli, ["catalog", "crawl", "--help"])
    assert "summary" in crawl_help.output.split("Commands:")[1]


def test_an_option_written_before_summary_is_a_usage_error(
    tmp_path: Path,
) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "crawl",
            "--url",
            SEED,
            "summary",
            "--run-id",
            RUN,
            "--target-uri",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 2
    assert "--url came before 'summary'" in result.output
