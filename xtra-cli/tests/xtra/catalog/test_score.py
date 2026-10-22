from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from common.keys import (
    extraction_score_report_key,
    golden_record_key,
    record_key,
)
from common.object_store import open_store
from xtra.cli import cli

FOLDER = "catalog-example-edu"
RUN = "2026-09-17T14:20:01Z"
STEM = "engl101-aaaaaaaaaa"


def seed(tmp_path: Path, golden_fields: list[dict] | None = None) -> None:
    records = open_store(str(tmp_path / "data"))
    records.put_json(
        record_key(FOLDER, RUN, STEM),
        {
            "record_id": STEM,
            "source_url": f"https://catalog.example.edu/{STEM}",
            "ctdl_expected": {
                "properties": [
                    {"property": "ceterms:name", "value": "Composition"},
                    {"property": "ceterms:codedNotation", "value": "ENGL101"},
                ]
            },
        },
    )
    if golden_fields is not None:
        open_store(str(tmp_path / "golden")).put_json(
            golden_record_key(FOLDER, RUN, STEM), [{"fields": golden_fields}]
        )


def field(prop: str, value: str) -> dict:
    return {"ctdl_property": prop, "value": value, "source_url": "x"}


def score(tmp_path: Path, *extra: str):
    return CliRunner().invoke(
        cli,
        [
            "catalog",
            "score",
            "--extraction",
            "--source-uri",
            str(tmp_path / "data"),
            "--golden-uri",
            str(tmp_path / "golden"),
            "--catalog-id",
            FOLDER,
            "--run-id",
            RUN,
            *extra,
        ],
    )


def test_score_writes_the_report_beside_the_records(tmp_path: Path) -> None:
    seed(
        tmp_path,
        [
            field("ceterms:name", "Composition"),
            field("ceterms:inLanguage", "English"),
        ],
    )

    result = score(tmp_path)

    assert result.exit_code == 0, result.output
    report = json.loads(
        (
            tmp_path / "data" / extraction_score_report_key(FOLDER, RUN)
        ).read_text(encoding="utf-8")
    )
    assert report["overall"] == 0.5
    assert report["by_property"]["ceterms:inLanguage"]["missing"] == 1


def test_stdout_is_json_and_the_table_goes_to_stderr(tmp_path: Path) -> None:
    seed(tmp_path, [field("ceterms:name", "Composition")])

    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "score",
            "--extraction",
            "--source-uri",
            str(tmp_path / "data"),
            "--golden-uri",
            str(tmp_path / "golden"),
            "--catalog-id",
            FOLDER,
            "--run-id",
            RUN,
        ],
    )

    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["overall"] == 1.0
    assert payload["pages_scored"] == 1
    assert "Extraction score: 1.0000" in result.stderr


def test_score_without_golden_files_fails_loudly(tmp_path: Path) -> None:
    seed(tmp_path)

    result = score(tmp_path)

    assert result.exit_code != 0
    assert "no golden files" in result.output


def test_score_requires_a_stage(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "score",
            "--source-uri",
            str(tmp_path),
            "--golden-uri",
            str(tmp_path),
            "--catalog-id",
            FOLDER,
            "--run-id",
            RUN,
        ],
    )

    assert result.exit_code != 0
    assert "--extraction" in result.output


def test_score_without_a_golden_uri_says_how_to_set_one(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "score",
            "--extraction",
            "--env",
            "test",
            "--source-uri",
            str(tmp_path),
            "--catalog-id",
            FOLDER,
            "--run-id",
            RUN,
        ],
    )

    assert result.exit_code != 0
    assert "--golden-uri" in result.output
