from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from crawl_doubles import FakePage, fetcher_factory, no_site_documents

from xtra.catalog.crawl import read_seed_urls
from xtra.cli import cli
from xtra.config.settings import StoredConfig, save_config

SEED = "https://catalog.example.edu/"
FOLDER = "catalog-example-edu"
RUN = "2026-09-17T14:20:01Z"
RUN_PATH = "2026-09-17T14-20-01Z"

PAGES = {
    SEED: FakePage(html='<a href="/courses/engl101">ENGL</a>'),
    "https://catalog.example.edu/courses/engl101": FakePage(
        html="<h1>ENGL 101</h1>"
    ),
}


def patch_crawl(
    monkeypatch,
    pages: dict,
    *,
    calls: list[str] | None = None,
    resolve_url=None,
) -> None:
    """Run the real crawler with a fake browser and no network."""
    from implementations import crawl as engine

    real = engine.run_crawl

    def fake(settings, **kwargs):
        kwargs["fetcher_factory"] = fetcher_factory(pages, calls=calls)
        kwargs.setdefault("url_fetch", no_site_documents)
        kwargs.setdefault("resolve_url", resolve_url or (lambda url: url))
        kwargs.setdefault("sleep", lambda seconds: None)
        return real(settings, **kwargs)

    monkeypatch.setattr("xtra.catalog.crawl.run_crawl", fake)


def invoke(tmp_path: Path, *extra: str):
    return CliRunner().invoke(
        cli,
        [
            "catalog",
            "crawl",
            "--with-playwright",
            "--url",
            SEED,
            "--target-uri",
            str(tmp_path),
            "--run-id",
            RUN,
            "--min-interval-in-seconds",
            "0",
            "--max-interval-in-seconds",
            "1",
            *extra,
        ],
    )


def test_crawl_saves_pages_under_the_catalog_folder(
    tmp_path: Path, monkeypatch
) -> None:
    patch_crawl(monkeypatch, PAGES)
    result = invoke(tmp_path)
    assert result.exit_code == 0, result.output

    doc = json.loads(result.output)
    assert doc["schema"] == "xtra-crawl-2"
    assert doc["catalog_folder"] == FOLDER
    assert doc["run_id"] == RUN
    assert doc["pages_saved"] == 2
    assert doc["status"] == "complete"

    run_dir = tmp_path / FOLDER / RUN_PATH
    assert (run_dir / "crawl.json").is_file()
    assert (run_dir / "state.json").is_file()
    assert len(list((run_dir / "pages").glob("*.html"))) == 2
    assert list((run_dir / "pages").glob("*.txt")) == []
    assert not (run_dir / "slots.json").exists()


def test_the_catalog_folder_comes_from_the_url_as_typed(
    tmp_path: Path, monkeypatch
) -> None:
    pages = {"https://catalog.atlanticcape.edu/": FakePage(html="<p>hi</p>")}
    patch_crawl(monkeypatch, pages)
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "crawl",
            "--with-playwright",
            "--url",
            "https://catalog.atlanticcape.edu/",
            "--target-uri",
            str(tmp_path),
            "--run-id",
            RUN,
            "--min-interval-in-seconds",
            "0",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "catalog-atlanticcape-edu" / RUN_PATH).is_dir()


def test_a_run_id_with_hyphens_is_accepted_and_reported_with_colons(
    tmp_path: Path, monkeypatch
) -> None:
    patch_crawl(monkeypatch, PAGES)
    result = invoke(tmp_path)
    assert json.loads(result.output)["run_id"] == RUN

    hyphen = CliRunner().invoke(
        cli,
        [
            "catalog",
            "crawl",
            "--with-playwright",
            "--url",
            SEED,
            "--target-uri",
            str(tmp_path),
            "--run-id",
            RUN_PATH,
            "--min-interval-in-seconds",
            "0",
        ],
    )
    assert hyphen.exit_code == 0, hyphen.output
    assert json.loads(hyphen.output)["run_id"] == RUN


def test_a_run_id_that_is_not_a_timestamp_is_rejected(tmp_path: Path) -> None:
    result = invoke(tmp_path.parent, "--run-id", "yesterday")
    assert result.exit_code != 0
    assert "2026-09-17T14:20:01Z" in result.output


def test_the_limit_caps_the_run(tmp_path: Path, monkeypatch) -> None:
    patch_crawl(monkeypatch, PAGES)
    result = invoke(tmp_path, "--limit", "1")
    assert result.exit_code == 0, result.output
    doc = json.loads(result.output)
    assert doc["pages_saved"] == 1
    assert doc["status"] == "limit_reached"
    assert doc["limit"] == 1


def test_rerunning_the_same_run_reads_saved_pages_back(
    tmp_path: Path, monkeypatch
) -> None:
    patch_crawl(monkeypatch, PAGES)
    invoke(tmp_path, "--limit", "1")

    calls: list[str] = []
    patch_crawl(monkeypatch, PAGES, calls=calls)
    result = invoke(tmp_path, "--limit", "5")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["pages_saved"] == 2
    assert SEED not in calls


def test_a_seed_urls_file_adds_start_urls(tmp_path: Path, monkeypatch) -> None:
    hidden = "https://catalog.example.edu/hidden/engl999"
    pages = dict(PAGES)
    pages[hidden] = FakePage(html="<h1>ENGL 999</h1>")
    seeds = tmp_path / "seeds.txt"
    seeds.write_text(f"# extra entry points\n\n{hidden}\n", encoding="utf-8")
    patch_crawl(monkeypatch, pages)
    result = invoke(tmp_path, "--seed-urls-file", str(seeds))
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["pages_saved"] == 3


def test_read_seed_urls_ignores_blanks_and_comments(tmp_path: Path) -> None:
    path = tmp_path / "seeds.txt"
    path.write_text(
        "# note\n\n  https://a.edu/x  \nhttps://a.edu/y\n", encoding="utf-8"
    )
    assert read_seed_urls(path) == ("https://a.edu/x", "https://a.edu/y")
    assert read_seed_urls(None) == ()


def test_include_and_exclude_regexes_are_recorded(
    tmp_path: Path, monkeypatch
) -> None:
    patch_crawl(monkeypatch, PAGES)
    result = invoke(
        tmp_path, "--include-regex", "courses", "--exclude-regex", "print=1"
    )
    assert result.exit_code == 0, result.output
    doc = json.loads(result.output)
    assert doc["include_regex"] == ["courses"]
    assert doc["exclude_regex"] == ["print=1"]


def test_a_broken_regex_is_a_usage_error(tmp_path: Path) -> None:
    result = invoke(tmp_path, "--include-regex", "cat(oid")
    assert result.exit_code != 0
    assert "--include-regex" in result.output


def test_a_min_above_the_max_is_a_usage_error(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "crawl",
            "--with-playwright",
            "--url",
            SEED,
            "--target-uri",
            str(tmp_path),
            "--min-interval-in-seconds",
            "600",
            "--max-interval-in-seconds",
            "60",
        ],
    )
    assert result.exit_code != 0
    assert "--min-interval-in-seconds" in result.output
    assert "--max-interval-in-seconds" in result.output


def test_a_scope_prefix_on_another_host_is_a_usage_error(
    tmp_path: Path,
) -> None:
    result = invoke(tmp_path, "--scope-prefix", "https://other.edu/courses/")
    assert result.exit_code != 0
    assert "one host" in result.output


def test_a_failed_page_gives_a_non_zero_exit_and_one_line(
    tmp_path: Path, monkeypatch
) -> None:
    pages = {
        SEED: FakePage(html='<a href="/courses/gone">gone</a>'),
        "https://catalog.example.edu/courses/gone": FakePage(
            status=404, html=""
        ),
    }
    patch_crawl(monkeypatch, pages)
    result = invoke(tmp_path, "--max-retries", "1")
    assert result.exit_code == 1
    assert "failed.jsonl" in result.output


def test_crawl_writes_to_the_active_environment(
    tmp_path: Path, monkeypatch
) -> None:
    save_config(StoredConfig(env_name="dev", data_uri=str(tmp_path)))
    patch_crawl(monkeypatch, PAGES)
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "crawl",
            "--with-playwright",
            "--url",
            SEED,
            "--run-id",
            RUN,
            "--min-interval-in-seconds",
            "0",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / FOLDER / RUN_PATH / "crawl.json").is_file()


def test_crawl_without_target_uri_or_environment_explains_itself() -> None:
    result = CliRunner().invoke(
        cli, ["catalog", "crawl", "--with-playwright", "--url", SEED]
    )
    assert result.exit_code != 0
    assert "--target-uri is required" in result.output
    assert "xtra environment set" in result.output


def test_crawl_requires_a_strategy(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli, ["catalog", "crawl", "--url", SEED, "--target-uri", str(tmp_path)]
    )
    assert result.exit_code != 0
    assert "--with-playwright" in result.output


@pytest.mark.parametrize("flag", ["--with-ai-agent", "--with-third-party"])
def test_the_reserved_strategies_fail_closed(tmp_path: Path, flag: str) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "crawl",
            flag,
            "--url",
            SEED,
            "--target-uri",
            str(tmp_path),
        ],
    )
    assert result.exit_code != 0
    assert "not implemented" in result.output.lower()


def test_the_removed_flags_are_gone(tmp_path: Path) -> None:
    help_text = CliRunner().invoke(cli, ["catalog", "crawl", "--help"]).output
    for flag in (
        "--all",
        "--discover-only",
        "--institution",
        "--catalog-id",
        "--backoff-base",
        "--backoff-max",
    ):
        assert flag not in help_text
    for flag in (
        "--limit",
        "--concurrency-limit",
        "--min-interval-in-seconds",
        "--max-interval-in-seconds",
        "--max-retries",
        "--scope-prefix",
        "--include-regex",
        "--exclude-regex",
        "--seed-urls-file",
    ):
        assert flag in help_text


# --- choosing a backend -----------------------------------------------------


def test_the_help_offers_three_working_strategies() -> None:
    help_text = CliRunner().invoke(cli, ["catalog", "crawl", "--help"]).output
    for flag in ("--with-playwright", "--with-crawl4ai", "--with-firecrawl"):
        assert flag in help_text
    assert "--firecrawl-api-key" in help_text
    assert "--firecrawl-api-url" in help_text


def test_the_strategy_chosen_is_recorded_in_crawl_json(
    tmp_path: Path, monkeypatch
) -> None:
    """Two small runs are comparable only if each says which backend ran."""
    patch_crawl(monkeypatch, PAGES)
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "crawl",
            "--with-crawl4ai",
            "--url",
            SEED,
            "--target-uri",
            str(tmp_path),
            "--run-id",
            RUN,
            "--min-interval-in-seconds",
            "0",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["strategy"] == "crawl4ai"


def test_firecrawl_without_a_key_is_a_usage_error(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "crawl",
            "--with-firecrawl",
            "--url",
            SEED,
            "--target-uri",
            str(tmp_path),
        ],
    )
    assert result.exit_code != 0
    assert "--firecrawl-api-key" in result.output


def test_firecrawl_takes_its_key_from_the_environment(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-from-env")
    patch_crawl(monkeypatch, PAGES)
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "crawl",
            "--with-firecrawl",
            "--url",
            SEED,
            "--target-uri",
            str(tmp_path),
            "--run-id",
            RUN,
            "--min-interval-in-seconds",
            "0",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["strategy"] == "firecrawl"


def test_the_api_key_never_reaches_the_run_report(
    tmp_path: Path, monkeypatch
) -> None:
    patch_crawl(monkeypatch, PAGES)
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "crawl",
            "--with-firecrawl",
            "--firecrawl-api-key",
            "fc-secret-value",
            "--url",
            SEED,
            "--target-uri",
            str(tmp_path),
            "--run-id",
            RUN,
            "--min-interval-in-seconds",
            "0",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "fc-secret-value" not in result.output
    stored = (tmp_path / FOLDER / RUN_PATH / "crawl.json").read_text(
        encoding="utf-8"
    )
    assert "fc-secret-value" not in stored


def test_a_resume_with_another_backend_is_a_clean_error(
    tmp_path: Path, monkeypatch
) -> None:
    """Naming both backends is the whole point: one of them is a typo."""
    patch_crawl(monkeypatch, PAGES)
    assert invoke(tmp_path, "--limit", "1").exit_code == 0
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "crawl",
            "--with-crawl4ai",
            "--url",
            SEED,
            "--target-uri",
            str(tmp_path),
            "--run-id",
            RUN,
            "--min-interval-in-seconds",
            "0",
        ],
    )
    assert result.exit_code != 0
    assert "--with-playwright" in result.output
    assert "--with-crawl4ai" in result.output
    assert "Traceback" not in result.output


def test_crawl_json_carries_the_versions_and_settings_of_the_backend(
    tmp_path: Path, monkeypatch
) -> None:
    patch_crawl(monkeypatch, PAGES)
    doc = json.loads(invoke(tmp_path).output)
    assert doc["strategy"] == "playwright"
    assert doc["strategy_version"]["playwright"]
    assert doc["strategy_settings"]["headless"] is True
    assert doc["strategy_notes"]
    assert doc["frontier_order"] == "sitemap_first"
    assert doc["catalog_folder_matches_resolved_host"] is True
