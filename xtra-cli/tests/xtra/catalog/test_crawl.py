from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from implementations.crawl import harvest_from_html, slot_to_dict
from xtra.cli import cli
from xtra.config.settings import StoredConfig, save_config

SEED = "https://catalog.example.edu"
RUN_ID = "2026-09-14T18:12:00Z"


def test_crawl_requires_strategy(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "crawl",
            "--url",
            SEED,
            "--target-uri",
            str(tmp_path),
        ],
    )
    assert result.exit_code != 0
    assert "--with-playwright" in result.output


def test_unimplemented_ai_agent_strategy(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "crawl",
            "--with-ai-agent",
            "--url",
            SEED,
            "--target-uri",
            str(tmp_path),
            "--min-interval",
            "0",
        ],
    )
    assert result.exit_code != 0
    assert "not implemented" in result.output.lower()


def test_crawl_playwright_writes_slots_without_pack(
    tmp_path: Path, catalog_home_html: str, monkeypatch
) -> None:
    def fake_harvest(seed_url, **kwargs):
        return harvest_from_html(catalog_home_html, seed_url, limit=5)

    monkeypatch.setattr("xtra.catalog.crawl.harvest_playwright", fake_harvest)

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
            "--run-id",
            RUN_ID,
            "--limit",
            "5",
            "--discover-only",
            "--min-interval",
            "0",
            "--backoff-base",
            "0",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["run_id"] == RUN_ID
    assert payload["catalog_id"] == "example"
    assert payload["kept"] >= 1
    assert "pack" not in payload

    slots_path = tmp_path / "example" / RUN_ID / "slots.json"
    assert slots_path.is_file()
    slots = json.loads(slots_path.read_text(encoding="utf-8"))
    urls = [row["requested_url"] for row in slots["slots"]]
    assert "https://catalog.example.edu/english/engl101" in urls


def test_slot_to_dict_round_trip(catalog_home_html: str) -> None:
    report = harvest_from_html(catalog_home_html, SEED, limit=2)
    as_dict = slot_to_dict(report["slots"][0])
    assert as_dict["entity_type"] == "Course"
    assert as_dict["requested_url"].startswith("https://catalog.example.edu/")


def test_crawl_errors_when_no_course_urls(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "xtra.catalog.crawl.harvest_playwright",
        lambda *args, **kwargs: {
            "slots": [],
            "discovered": 0,
            "family": "custom_html",
            "institution_name": "Example",
        },
    )
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
            "--discover-only",
            "--min-interval",
            "0",
        ],
    )
    assert result.exit_code != 0
    assert "no course urls" in result.output.lower()


def test_crawl_without_target_uri_or_environment_explains_itself() -> None:
    result = CliRunner().invoke(
        cli,
        ["catalog", "crawl", "--with-playwright", "--url", SEED, "--discover-only"],
    )
    assert result.exit_code != 0
    assert "--target-uri is required" in result.output
    assert "xtra environment set" in result.output


def test_crawl_writes_to_the_active_environment(
    tmp_path: Path, catalog_home_html: str, monkeypatch
) -> None:
    monkeypatch.setattr(
        "xtra.catalog.crawl.harvest_playwright",
        lambda seed_url, **kwargs: harvest_from_html(catalog_home_html, seed_url, limit=1),
    )
    save_config(StoredConfig(env_name="test", data_uri=str(tmp_path)))

    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "crawl",
            "--with-playwright",
            "--url",
            SEED,
            "--run-id",
            RUN_ID,
            "--discover-only",
            "--min-interval",
            "0",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "example" / RUN_ID / "slots.json").is_file()


def test_crawl_env_flag_overrides_the_active_environment(
    tmp_path: Path, catalog_home_html: str, monkeypatch
) -> None:
    monkeypatch.setattr(
        "xtra.catalog.crawl.harvest_playwright",
        lambda seed_url, **kwargs: harvest_from_html(catalog_home_html, seed_url, limit=1),
    )
    save_config(StoredConfig(env_name="prod", data_uri=str(tmp_path)))

    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "crawl",
            "--with-playwright",
            "--env",
            "sandbox",
            "--url",
            SEED,
            "--discover-only",
            "--min-interval",
            "0",
        ],
    )
    assert result.exit_code != 0
    assert "environment set sandbox" in result.output
    assert not list(tmp_path.iterdir())


def test_crawl_downloads_pages_when_not_discover_only(
    tmp_path: Path, catalog_home_html: str, engl101_html: str, monkeypatch
) -> None:
    def fake_harvest(seed_url, **kwargs):
        return harvest_from_html(catalog_home_html, seed_url, limit=1)

    def fake_download(url, **kwargs):
        stem = "catalog-example-edu-english-engl101"
        return engl101_html, {"http_status": 200, "requested_url": url}, "ENGL101:\n", stem

    monkeypatch.setattr("xtra.catalog.crawl.harvest_playwright", fake_harvest)
    monkeypatch.setattr("xtra.catalog.crawl.download_one", fake_download)
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
            "--run-id",
            RUN_ID,
            "--limit",
            "1",
            "--min-interval",
            "0",
            "--backoff-base",
            "0",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["downloaded"] == 1
    pages = list((tmp_path / "example" / RUN_ID / "pages").glob("*.html"))
    assert pages
