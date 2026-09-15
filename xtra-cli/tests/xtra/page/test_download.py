from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from common.keys import slots_key
from common.object_store import open_store
from implementations.engine import load_engine
from xtra.cli import cli

load_engine()
from html_text import slug_url

RUN_ID = "2026-09-14T18:12:00Z"
CATALOG_ID = "example"
URL = "https://catalog.example.edu/english/engl101"


def test_page_download_playwright_uses_polite_fetcher(
    tmp_path: Path, engl101_html: str, monkeypatch
) -> None:
    store = open_store(str(tmp_path))
    store.put_json(
        slots_key(CATALOG_ID, RUN_ID),
        {
            "schema": "xtra-slots-1",
            "slots": [
                {
                    "record_id": "example-engl101-course",
                    "entity_type": "Course",
                    "requested_url": URL,
                    "institution_name": "Example College",
                    "source_family": "custom_html",
                    "template_id": "clean_catalog_course_detail",
                    "template_version": "1",
                    "page_id": "example-engl101",
                    "copy_html": None,
                    "retrieved_at": RUN_ID,
                    "multi_entity_bundle": False,
                    "notes": "",
                }
            ],
        },
    )

    def fake_fetch(url: str):
        assert url == URL
        return engl101_html, {
            "requested_url": url,
            "final_url": url,
            "http_status": 200,
            "retrieved_at": RUN_ID,
            "capture": "test_fixture",
            "media_type": "text/html",
        }

    monkeypatch.setattr("xtra.page.download.fetch_html_playwright", fake_fetch)

    result = CliRunner().invoke(
        cli,
        [
            "page",
            "download",
            "--with-playwright",
            "--source-uri",
            str(tmp_path),
            "--target-uri",
            str(tmp_path),
            "--catalog-id",
            CATALOG_ID,
            "--run-id",
            RUN_ID,
            "--min-interval",
            "0",
            "--backoff-base",
            "0",
            "--limit",
            "5",
        ],
    )
    assert result.exit_code == 0, result.output
    stem = slug_url(URL)
    html_path = tmp_path / CATALOG_ID / RUN_ID / "pages" / f"{stem}.html"
    assert html_path.read_text(encoding="utf-8") == engl101_html
    payload = json.loads(result.output)
    assert payload["downloaded"] == [stem]


def test_page_download_requires_strategy(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "page",
            "download",
            "--source-uri",
            str(tmp_path),
            "--target-uri",
            str(tmp_path),
            "--catalog-id",
            CATALOG_ID,
            "--run-id",
            RUN_ID,
        ],
    )
    assert result.exit_code != 0
    assert "--with-playwright" in result.output


def test_page_download_ai_agent_is_stub(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "page",
            "download",
            "--with-ai-agent",
            "--source-uri",
            str(tmp_path),
            "--target-uri",
            str(tmp_path),
            "--catalog-id",
            CATALOG_ID,
            "--run-id",
            RUN_ID,
            "--min-interval",
            "0",
        ],
    )
    assert result.exit_code != 0
    assert "not implemented" in result.output.lower()
