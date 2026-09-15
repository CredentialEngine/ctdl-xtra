from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from common.keys import record_key
from common.object_store import open_store
from xtra.cli import cli

RUN_ID = "2026-09-14T18:12:00Z"
CATALOG_ID = "example"


def test_transform_ctdl_writes_jsonld_without_ctid(tmp_path: Path) -> None:
    store = open_store(str(tmp_path))
    store.put_json(
        record_key(CATALOG_ID, RUN_ID, "example-engl101-course"),
        {
            "id": "example-engl101-course",
            "record_id": "example-engl101-course",
            "catalogue_type": "COURSES",
            "entity_type": "Course",
            "source_url": "https://catalog.example.edu/english/engl101",
            "source_expected": {
                "fields": [
                    {
                        "field_id": "f_001",
                        "canonical_label": "course_id",
                        "presence": "present",
                        "value": "ENGL101",
                    },
                    {
                        "field_id": "f_002",
                        "canonical_label": "course_name",
                        "presence": "present",
                        "value": "Composition I",
                    },
                ]
            },
        },
    )
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "transform",
            "--with-ctdl",
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
    node = json.loads(
        (
            tmp_path
            / CATALOG_ID
            / RUN_ID
            / "jsonld"
            / "example-engl101-course.json"
        ).read_text(encoding="utf-8")
    )
    assert node["@type"] == "ceterms:Course"
    assert "ceterms:ctid" not in node
    assert node["ceterms:codedNotation"] == "ENGL101"
    expected = json.loads(
        (
            tmp_path
            / CATALOG_ID
            / RUN_ID
            / "expected"
            / "example-engl101-course.json"
        ).read_text(encoding="utf-8")
    )
    assert expected["catalogue_type"] == "COURSES"
    assert expected["expected"]["course_id"] == "ENGL101"


def test_transform_requires_strategy(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "transform",
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
    assert "--with-ctdl" in result.output


def test_transform_ai_agent_is_stub(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "transform",
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
