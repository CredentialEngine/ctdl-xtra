"""The candidate record shell. A builder never signs a record."""

from __future__ import annotations

import json
import re
from pathlib import Path

import config
import pytest
import record
from lib_doubles import (
    COURSE_HTML,
    COURSE_TEXT,
    NOW,
    course_record,
    example_slot,
)
from normalize import normalize_html


def schema(lib_dir: Path) -> dict:
    return json.loads(
        (lib_dir / "record.schema.json").read_text(encoding="utf-8")
    )


def test_the_shared_course_fixture_is_what_its_page_normalizes_to() -> None:
    assert normalize_html(COURSE_HTML) == COURSE_TEXT


def test_the_empty_checklist_has_every_schema_item_unticked(
    lib_dir: Path,
) -> None:
    checklist = record.empty_checklist()
    required = schema(lib_dir)["$defs"]["verification"]["properties"][
        "checklist"
    ]["required"]
    assert sorted(checklist) == sorted(required)
    assert set(checklist.values()) == {False}


def test_each_review_stage_starts_as_an_unreviewed_candidate() -> None:
    assert record.candidate_stage_reviews() == [
        {
            "stage": stage,
            "status": "candidate",
            "reviewer_1": None,
            "reviewer_2": None,
            "notes": None,
        }
        for stage in (
            "extraction",
            "mapping",
            "registry_reconciliation",
            "linking",
        )
    ]


def test_an_unchecked_registry_block_claims_nothing() -> None:
    block = record.not_checked_registry()
    assert block["status"] == "not_checked"
    assert block["checked_at"] is None
    assert block["registry_ctid"] is None
    assert block["property_comparisons"] == []


@pytest.mark.parametrize(
    ("entity_type", "class_uri"),
    [
        ("Course", "ceterms:Course"),
        ("LearningProgram", "ceterms:LearningProgram"),
        ("Credential", "ceterms:Credential"),
        ("CompetencyFramework", "ceasn:CompetencyFramework"),
        ("Competency", "ceasn:Competency"),
        ("Link", None),
    ],
)
def test_an_empty_ctdl_block_names_the_class_and_the_pinned_release(
    entity_type: str, class_uri: str | None
) -> None:
    assert record.empty_ctdl(entity_type) == {
        "class_uri": class_uri,
        "schema_release": config.SCHEMA_RELEASE,
        "mapping_version": config.MAPPING_VERSION,
        "properties": [],
        "unmapped_source_field_refs": [],
    }


def test_an_unknown_entity_type_has_no_ctdl_class() -> None:
    with pytest.raises(KeyError):
        record.empty_ctdl("Program")


def test_a_locator_has_no_page_or_box_for_html() -> None:
    assert record.locator("text_anchor", "h1", 2) == {
        "strategy": "text_anchor",
        "value": "h1",
        "occurrence": 2,
        "page_number": None,
        "bbox": None,
    }


def test_now_is_an_rfc3339_utc_second() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", record._now())


def test_the_shell_is_a_candidate_with_no_reviewer_or_signature(
    fixed_clock: str,
) -> None:
    shell = record.shell(
        example_slot(), source={}, page={}, annotation_scope={}
    )
    verification = shell["verification"]
    assert shell["schema_version"] == "2.0.0"
    assert shell["record_id"] == "example-engl101-course"
    assert verification["status"] == "candidate"
    assert verification["reviewer_1"] is None
    assert verification["reviewer_2"] is None
    assert verification["signed_at"] is None
    assert verification["annotator"]["completed_at"] == NOW
    assert record.ANNOTATOR["completed_at"] is None
    assert shell["registry_expected"] == record.not_checked_registry()


def test_two_shells_share_no_mutable_parts() -> None:
    first = record.shell(
        example_slot(), source={}, page={}, annotation_scope={}
    )
    second = record.shell(
        example_slot(), source={}, page={}, annotation_scope={}
    )
    first["verification"]["checklist"]["links_checked"] = True
    first["source_expected"]["fields"].append({})
    assert second["verification"]["checklist"]["links_checked"] is False
    assert second["source_expected"]["fields"] == []


def test_the_source_block_falls_back_to_the_slot_where_meta_is_silent() -> None:
    slot = example_slot()
    block = record.source_block(
        slot,
        snapshot_rel="cache/2026-10-21/x.html",
        snapshot_sha256="a" * 64,
        normalized_rel="normalized/x.txt",
        normalized_sha256="b" * 64,
        meta={"http_status": 200, "redirect_chain": None},
    )
    assert block["final_url"] == slot.requested_url
    assert block["retrieved_at"] == slot.retrieved_at
    assert block["acquisition"] == {
        "http_status": 200,
        "content_type": None,
        "redirect_chain": [],
        "etag": None,
        "last_modified": None,
    }
    assert block["normalization"]["tool"] == config.NORMALIZER_TOOL
    assert block["normalization"]["version"] == config.NORMALIZER_VERSION


def test_a_built_record_satisfies_the_record_schema(
    pack: Path, lib_dir: Path
) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    rec = course_record(pack)
    validator = jsonschema.Draft202012Validator(schema(lib_dir))
    assert [error.message for error in validator.iter_errors(rec)] == []
