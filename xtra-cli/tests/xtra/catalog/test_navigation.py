from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner
from crawl_doubles import FakePage, fetcher_factory, no_site_documents

from common.object_store import open_store
from implementations.crawl import CrawlSettings, run_crawl
from xtra.cli import cli

SEED = "https://catalog.example.edu/"
FOLDER = "catalog-example-edu"
RUN = "2026-09-17T14:20:01Z"
RUN_PATH = "2026-09-17T14-20-01Z"

PAGES = {
    SEED: FakePage(html='<a href="/courses/a">Course A</a>'),
    "https://catalog.example.edu/courses/a": FakePage(html="<h1>Course A</h1>"),
}


def crawl_into(tmp_path: Path, *, with_navigation: bool = False) -> None:
    run_crawl(
        CrawlSettings(
            seed_url=SEED,
            catalog_folder=FOLDER,
            run_id=RUN,
            target_uri=str(tmp_path),
            min_interval_in_seconds=0,
            max_interval_in_seconds=1,
            with_navigation=with_navigation,
        ),
        store=open_store(str(tmp_path)),
        fetcher_factory=fetcher_factory(PAGES),
        url_fetch=no_site_documents,
        resolve_url=lambda url: url,
        sleep=lambda seconds: None,
    )


def invoke(source: Path, target: Path | None = None, *extra: str):
    return CliRunner().invoke(
        cli,
        [
            "catalog",
            "navigation",
            "--catalog-id",
            FOLDER,
            "--run-id",
            RUN,
            "--source-uri",
            str(source),
            "--target-uri",
            str(target or source),
            *extra,
        ],
    )


def test_navigation_builds_the_tree_of_a_saved_crawl(tmp_path: Path) -> None:
    crawl_into(tmp_path)
    result = invoke(tmp_path)
    assert result.exit_code == 0, result.output

    summary = json.loads(result.output)
    assert summary["built_by"] == "rebuild"
    assert summary["totals"]["pages_by_status"] == {"saved": 2}
    assert "tree" not in summary
    assert summary["written_to"].endswith(f"{RUN_PATH}/navigation.json")

    run_dir = tmp_path / FOLDER / RUN_PATH
    tree = json.loads((run_dir / "navigation.json").read_text(encoding="utf-8"))
    assert [page["url"] for page in tree["tree"]] == [SEED]
    assert tree["tree"][0]["pages_found_here"][0]["link_text"] == "Course A"


def test_the_tree_can_be_written_somewhere_else(tmp_path: Path) -> None:
    source, target = tmp_path / "crawl", tmp_path / "out"
    crawl_into(source)
    result = invoke(source, target)
    assert result.exit_code == 0, result.output
    assert (target / FOLDER / RUN_PATH / "navigation.json").is_file()
    assert not (source / FOLDER / RUN_PATH / "navigation.json").exists()


def test_a_tree_the_crawl_built_is_left_alone(tmp_path: Path) -> None:
    crawl_into(tmp_path, with_navigation=True)
    result = invoke(tmp_path)
    assert result.exit_code != 0
    assert "built by the crawl" in result.output
    assert "Traceback" not in result.output


def test_a_run_that_was_never_crawled_explains_itself(tmp_path: Path) -> None:
    result = invoke(tmp_path)
    assert result.exit_code != 0
    assert "no state.json" in result.output


def test_a_run_id_that_is_not_a_timestamp_is_rejected(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "navigation",
            "--catalog-id",
            FOLDER,
            "--run-id",
            "yesterday",
            "--source-uri",
            str(tmp_path),
        ],
    )
    assert result.exit_code != 0
    assert "2026-09-17T14:20:01Z" in result.output
