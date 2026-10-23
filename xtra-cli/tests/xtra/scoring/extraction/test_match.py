from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from common.keys import (
    baseline_record_key,
    extraction_match_report_key,
    record_key,
)
from common.object_store import open_store
from xtra.cli import cli

FOLDER = "catalog-example-edu"
RUN = "2026-09-17T14:20:01Z"
STEM = "engl101-aaaaaaaaaa"


def seed(tmp_path: Path, baseline_fields: list[dict] | None = None) -> None:
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
    if baseline_fields is not None:
        open_store(str(tmp_path / "baseline")).put_json(
            baseline_record_key(FOLDER, RUN, STEM),
            [{"fields": baseline_fields}],
        )


def field(prop: str, value: str) -> dict:
    return {"ctdl_property": prop, "value": value, "source_url": "x"}


def match(tmp_path: Path, *extra: str):
    return CliRunner().invoke(
        cli,
        [
            "score",
            "extraction",
            "match",
            "--source-uri",
            str(tmp_path / "data"),
            "--baseline-uri",
            str(tmp_path / "baseline"),
            "--catalog-id",
            FOLDER,
            "--run-id",
            RUN,
            *extra,
        ],
    )


def read_report(tmp_path: Path, mode: str) -> dict:
    return json.loads(
        (
            tmp_path / "data" / extraction_match_report_key(FOLDER, RUN, mode)
        ).read_text(encoding="utf-8")
    )


def test_exactly_writes_its_own_report_beside_the_records(
    tmp_path: Path,
) -> None:
    seed(
        tmp_path,
        [
            field("ceterms:name", "Composition"),
            field("ceterms:inLanguage", "English"),
        ],
    )

    result = match(tmp_path, "--exactly")

    assert result.exit_code == 0, result.output
    report = read_report(tmp_path, "exact")
    assert report["outcomes"] == {"match": 1, "mismatch": 0, "missing": 1}
    assert report["by_property"]["ceterms:inLanguage"]["missing"] == 1
    assert not (
        tmp_path / "data" / extraction_match_report_key(FOLDER, RUN, "partial")
    ).exists()


def test_partially_writes_its_own_report_and_skips_exact_matches(
    tmp_path: Path,
) -> None:
    seed(
        tmp_path,
        [
            field("ceterms:name", "Composition"),
            field("ceterms:codedNotation", "ENGL 101"),
        ],
    )

    result = match(tmp_path, "--partially")

    assert result.exit_code == 0, result.output
    report = read_report(tmp_path, "partial")
    assert report["excluded_exact"] == 1
    assert report["outcomes"] == {"partial": 1, "wrong": 0, "missing": 0}


def test_stdout_is_json_and_the_table_goes_to_stderr(tmp_path: Path) -> None:
    seed(tmp_path, [field("ceterms:name", "Composition")])

    result = match(tmp_path, "--exactly")

    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["mode"] == "exact"
    assert payload["exact_match_rate"] == 1.0
    assert payload["pages_scored"] == 1
    assert payload["outliers"] == 0
    assert "overall" not in payload
    assert "Extraction match (exact)" in result.stderr


def test_without_baseline_files_it_fails_loudly(tmp_path: Path) -> None:
    seed(tmp_path)

    result = match(tmp_path, "--exactly")

    assert result.exit_code != 0
    assert "no baseline files" in result.output


def test_it_requires_a_mode(tmp_path: Path) -> None:
    result = match(tmp_path)

    assert result.exit_code != 0
    assert "exactly one of --exactly or --partially" in result.output


def test_it_refuses_both_modes_at_once(tmp_path: Path) -> None:
    result = match(tmp_path, "--exactly", "--partially")

    assert result.exit_code != 0
    assert "exactly one of --exactly or --partially" in result.output


def test_source_and_baseline_take_their_own_connection_strings(
    tmp_path: Path, monkeypatch
) -> None:
    seed(tmp_path, [field("ceterms:name", "Composition")])
    opened: dict[str, str | None] = {}

    def recording_open_store(uri, *, azure_storage_connection_string=None):
        opened[uri] = azure_storage_connection_string
        return open_store(uri)

    monkeypatch.setattr(
        "xtra.scoring.extraction.match.open_store", recording_open_store
    )

    result = match(
        tmp_path,
        "--exactly",
        "--source-azure-storage-connection-string",
        "source-secret",
        "--baseline-azure-storage-connection-string",
        "baseline-secret",
    )

    assert result.exit_code == 0, result.output
    assert opened == {
        str(tmp_path / "data"): "source-secret",
        str(tmp_path / "baseline"): "baseline-secret",
    }


def test_without_a_baseline_uri_it_says_how_to_set_one(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "score",
            "extraction",
            "match",
            "--exactly",
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
    assert "--baseline-uri" in result.output
