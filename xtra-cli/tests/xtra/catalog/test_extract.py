from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from common.keys import page_html_key, slots_key
from common.object_store import open_store
from implementations.crawl import harvest_from_html, slot_to_dict
from xtra.cli import cli

SEED = "https://catalog.example.edu"
RUN_ID = "2026-09-14T18:12:00Z"
CATALOG_ID = "example"


def _seed_run(tmp_path: Path, engl101_html: str, catalog_home_html: str) -> None:
    store = open_store(str(tmp_path))
    report = harvest_from_html(catalog_home_html, SEED, limit=1)
    slot = report["slots"][0]
    # Point the only slot at the ENGL101 fixture URL/html.
    raw = slot_to_dict(slot)
    raw["requested_url"] = "https://catalog.example.edu/english/engl101"
    raw["record_id"] = "example-engl101-course"
    raw["page_id"] = "example-engl101"
    raw["template_id"] = "clean_catalog_course_detail"
    raw["source_family"] = "custom_html"
    from html_text import slug_url

    stem = slug_url(raw["requested_url"])
    raw["stem"] = stem
    store.put_json(
        slots_key(CATALOG_ID, RUN_ID),
        {
            "schema": "xtra-slots-1",
            "catalog_id": CATALOG_ID,
            "run_id": RUN_ID,
            "slots": [raw],
        },
    )
    store.put_text(
        page_html_key(CATALOG_ID, RUN_ID, stem),
        engl101_html,
        "text/html",
    )


def test_extract_template_writes_candidate_record(
    tmp_path: Path, engl101_html: str, catalog_home_html: str
) -> None:
    _seed_run(tmp_path, engl101_html, catalog_home_html)
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "extract",
            "--with-template",
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
    assert result.exit_code == 0, result.output
    record_path = tmp_path / CATALOG_ID / RUN_ID / "records" / "example-engl101-course.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["verification"]["status"] == "candidate"
    labels = {
        field["canonical_label"]: field["value"]
        for field in record["source_expected"]["fields"]
    }
    assert labels["course_id"] == "ENGL101"
    assert labels["course_name"] == "Composition I"
    assert labels["course_credits"] == 3


def test_extract_ai_agent_is_stub(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "extract",
            "--with-ai-agent",
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
    assert "not implemented" in result.output.lower()


def test_extract_requires_strategy(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "extract",
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
    assert "--with-template" in result.output
