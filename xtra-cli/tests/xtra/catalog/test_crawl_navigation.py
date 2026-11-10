from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner
from crawl_doubles import FakePage, fetcher_factory, site_documents

from common.keys import navigation_key
from common.object_store import open_store
from implementations.crawl import CrawlSettings, run_crawl
from xtra.cli import cli

SEED = "https://catalog.example.edu/"
FOLDER = "catalog-example-edu"
RUN = "2026-09-17T14:20:01Z"
ENGL = "https://catalog.example.edu/courses/engl101"


def crawled(tmp_path: Path) -> None:
    run_crawl(
        CrawlSettings(
            seed_url=SEED,
            catalog_folder=FOLDER,
            run_id=RUN,
            target_uri=str(tmp_path),
            min_interval_in_seconds=0,
            max_interval_in_seconds=1,
            pacing_jitter_fraction=0,
        ),
        store=open_store(str(tmp_path)),
        fetcher_factory=fetcher_factory(
            {
                SEED: FakePage(html=f'<a href="{ENGL}">ENGL 101</a>'),
                ENGL: FakePage(html="<h1>ENGL 101</h1>"),
            }
        ),
        url_fetch=site_documents({}),
        resolve_url=lambda url: url,
        sleep=lambda seconds: None,
    )


def navigation(tmp_path: Path, *extra: str, run_id: str = RUN):
    return CliRunner().invoke(
        cli,
        [
            "catalog",
            "crawl",
            "navigation",
            "--url",
            SEED,
            "--run-id",
            run_id,
            "--target-uri",
            str(tmp_path),
            *extra,
        ],
    )


def stored(tmp_path: Path) -> dict:
    doc = open_store(str(tmp_path)).get_json(navigation_key(FOLDER, RUN))
    assert isinstance(doc, dict)
    return doc


def test_it_writes_navigation_json_and_prints_where(tmp_path: Path) -> None:
    crawled(tmp_path)
    result = navigation(tmp_path)
    assert result.exit_code == 0, result.output
    printed = json.loads(result.stdout)
    assert printed["navigation"] == navigation_key(FOLDER, RUN)
    assert printed["totals"]["urls"] == 2
    pages = {entry["url"]: entry for entry in stored(tmp_path)["urls"]}
    assert pages[ENGL]["source_url"] == SEED
    assert pages[ENGL]["link_text"] == "ENGL 101"


def test_the_run_id_may_be_given_in_its_folder_form(tmp_path: Path) -> None:
    crawled(tmp_path)
    result = navigation(tmp_path, run_id="2026-09-17T14-20-01Z")
    assert result.exit_code == 0, result.output
    assert stored(tmp_path)["run_id"] == RUN


def test_a_second_build_is_refused_without_force(tmp_path: Path) -> None:
    crawled(tmp_path)
    assert navigation(tmp_path).exit_code == 0
    again = navigation(tmp_path)
    assert again.exit_code == 1
    assert "--force" in again.output
    assert navigation(tmp_path, "--force").exit_code == 0


def test_a_run_that_does_not_exist_says_so(tmp_path: Path) -> None:
    result = navigation(tmp_path)
    assert result.exit_code == 1
    assert "no crawl.json and no manifest.json" in result.output


def test_a_run_id_that_is_not_a_timestamp_is_a_usage_error(
    tmp_path: Path,
) -> None:
    result = navigation(tmp_path, run_id="yesterday")
    assert result.exit_code == 2
    assert "not a UTC timestamp" in result.output


def test_crawl_options_before_navigation_are_refused(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "crawl",
            "--url",
            SEED,
            "navigation",
            "--url",
            SEED,
            "--run-id",
            RUN,
            "--target-uri",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 2
    assert "came before 'navigation'" in result.output


def test_crawl_help_names_the_navigation_command() -> None:
    result = CliRunner().invoke(cli, ["catalog", "crawl", "--help"])
    assert result.exit_code == 0
    assert "navigation" in result.output
