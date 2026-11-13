from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from common.keys import (
    baseline_record_key,
    extract_resource_key,
    extraction_match_report_key,
    page_stem,
    property_extract_report_key,
    records_prefix,
)
from common.object_store import open_store
from xtra.cli import cli

FOLDER = "catalog-example-edu"
RUN = "2026-09-17T14:20:01Z"
URL = "https://catalog.example.edu/engl101"
STEM = page_stem(URL)


def extracted(prop: str, value: str) -> dict:
    """One extraction_report/ file, as xtra catalog extract writes it."""
    return {
        "type": "ceterms:Course",
        "resource_id": f"{FOLDER}_ENGL101",
        "ctdl_property": prop,
        "value": value,
        "catalog_id": FOLDER,
        "source_url": URL,
        "retrieved_at": None,
        "notes": "strategy=profile_title platform=- css=-",
    }


def seed(tmp_path: Path, baseline_fields: list[dict] | None = None) -> None:
    data = open_store(str(tmp_path / "data"))
    for prop, value in (
        ("ceterms:name", "Composition"),
        ("ceterms:codedNotation", "ENGL101"),
    ):
        data.put_json(
            extract_resource_key(FOLDER, RUN, prop, f"{FOLDER}_ENGL101"),
            extracted(prop, value),
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


def test_a_page_a_whole_catalog_run_never_wrote_is_missing(
    tmp_path: Path,
) -> None:
    seed(tmp_path, [field("ceterms:name", "Composition")])
    data = open_store(str(tmp_path / "data"))
    for prop in ("ceterms:name", "ceterms:codedNotation"):
        data.put_json(
            property_extract_report_key(FOLDER, RUN, prop),
            {"only_golden_sample": False, "limit": None},
        )
    open_store(str(tmp_path / "baseline")).put_json(
        baseline_record_key(FOLDER, RUN, "never-written-0000000000"),
        [{"fields": [field("ceterms:name", "Rhetoric")]}],
    )

    result = match(tmp_path, "--exactly")

    assert result.exit_code == 0, result.output
    report = read_report(tmp_path, "exact")
    assert report["outcomes"] == {"match": 1, "mismatch": 0, "missing": 1}
    assert report["pages_not_extracted"] == 1
    assert json.loads(result.stdout)["pages_not_extracted"] == 1


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
        "xtra.score.extraction.match.open_store", recording_open_store
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


def test_nothing_is_written_to_records(tmp_path: Path) -> None:
    seed(tmp_path, [field("ceterms:name", "Composition")])

    result = match(tmp_path, "--exactly")

    assert result.exit_code == 0, result.output
    data = open_store(str(tmp_path / "data"))
    assert list(data.list_keys(records_prefix(FOLDER, RUN))) == []


def test_without_extraction_report_files_it_says_to_run_extraction(
    tmp_path: Path,
) -> None:
    open_store(str(tmp_path / "baseline")).put_json(
        baseline_record_key(FOLDER, RUN, STEM),
        [{"fields": [field("ceterms:name", "Composition")]}],
    )

    result = match(tmp_path, "--exactly")

    assert result.exit_code != 0
    assert "Run xtra catalog extract first" in result.output
