"""Candidate records assembled from a freeze and its transcription, and the
pack files written around them."""

from __future__ import annotations

import json
from pathlib import Path

import build
import dynamic_slots
import export_xtra
import pytest
from inventory import csv_text
from lib_doubles import DAY, example_slot, write_freeze, write_normalized
from normalize import normalize_html
from slots import Slot
from transcribe_lib import TranscriptionError
from validate import validate_record

D8 = (
    "D8: build_pack deletes registry/summary.json, which lookup_pack wrote, "
    "because 'summary' is not a record id"
)
STEM = "catalog-example-edu-english-engl101"
LINK_ID = "example-nursing-link-results-in-credential"


@pytest.fixture
def frozen(pack: Path, engl101_html: str) -> Slot:
    """The ENGL101 fixture page frozen, normalized and queued."""
    slot = example_slot()
    write_freeze(pack, slot, engl101_html)
    write_normalized(pack, slot, normalize_html(engl101_html))
    dynamic_slots.write_slots([slot])
    return slot


def test_the_page_title_is_the_first_line_that_is_not_site_chrome(
    frozen: Slot,
) -> None:
    text = (
        "Skip to main content\nHome\nCatalog Search\nENGL101:\nComposition I\n"
    )
    page = build._page(frozen, text)
    assert page["title"] == "ENGL101:"
    assert page["canonical_url"] == frozen.requested_url
    assert page["classification"] == "detail"
    assert [e["provisional_id"] for e in page["entities_observed"]] == [
        "example-engl101-course"
    ]
    assert build._page(frozen, "Home\nBreadcrumb\n")["title"] is None


def test_the_scope_names_the_entity_and_any_bundle_or_slot_notes() -> None:
    plain = build._scope(example_slot(), "")
    assert (
        plain["entity_boundary"] == "Single course detail block on this freeze."
    )
    assert plain["mode"] == "complete"
    noted = build._scope(
        example_slot(multi_entity_bundle=True, notes="Two sections."), ""
    )
    assert noted["entity_boundary"].startswith(
        "Declared multi-entity competency bundle"
    )
    assert noted["entity_boundary"].endswith(
        "Single course detail block on this freeze. Two sections."
    )
    with pytest.raises(KeyError):
        build._scope(example_slot(entity_type="Program"), "")


def test_a_link_id_names_its_subject_and_object_records() -> None:
    assert build._link_endpoints(example_slot(record_id=LINK_ID)) == (
        "example-nursing-learning-program",
        "example-nursing-credential",
    )
    with pytest.raises(TranscriptionError, match="must end with"):
        build._link_endpoints(example_slot(record_id="example-nursing-link"))


def test_only_a_link_record_has_links_and_it_needs_its_heading() -> None:
    heading = {
        "field_id": "src_001",
        "canonical_label": "relationship_heading",
        "value": "Nursing AAS",
        "evidence": [{"evidence_id": "ev_001"}],
    }
    assert build._links(example_slot(), [heading]) == []
    link_slot = example_slot(record_id=LINK_ID, entity_type="Link")
    with pytest.raises(TranscriptionError, match="relationship_heading"):
        build._links(link_slot, [])
    [link] = build._links(link_slot, [heading])
    assert link["predicate"] == "ceterms:resultsInCredential"
    assert link["subject_ref"] == "example-nursing-learning-program"
    assert link["object_ref"] == "example-nursing-credential"
    assert link["object_label"] == "Nursing AAS"
    assert link["source_field_refs"] == ["src_001"]
    assert link["evidence_refs"] == ["ev_001"]


def test_a_built_record_passes_every_runtime_and_schema_check(
    pack: Path, frozen: Slot
) -> None:
    rec = build.build_record(frozen)
    assert validate_record(rec, pack=pack) == []
    fields = rec["source_expected"]["fields"]
    assert [f["canonical_label"] for f in fields] == [
        "course_id",
        "course_name",
        "course_credits",
        "course_lecture_hours",
        "course_description",
    ]
    assert [f["evidence"][0]["evidence_id"] for f in fields] == [
        f"ev_{n:03d}" for n in range(1, 6)
    ]
    assert rec["source"]["snapshot_path"] == f"cache/{DAY}/{STEM}.html"
    assert rec["source"]["normalized_text_path"] == f"normalized/{STEM}.txt"
    assert rec["ctdl_expected"]["class_uri"] == "ceterms:Course"
    assert rec["links_expected"] == []
    assert rec["verification"]["status"] == "candidate"


def test_build_pack_writes_good_records_and_reports_the_rest(
    pack: Path, frozen: Slot
) -> None:
    unfrozen = example_slot(
        record_id="example-math101-course",
        requested_url="https://catalog.example.edu/math/math101",
    )
    dynamic_slots.write_slots([frozen, unfrozen])
    (pack / "records").mkdir()
    (pack / "records" / "old-course.json").write_text("{}", encoding="utf-8")
    (pack / "registry").mkdir()
    (pack / "registry" / "old-course.json").write_text("{}", encoding="utf-8")
    errors = build.build_pack()
    assert len(errors) == 1
    assert errors[0].startswith("example-math101-course: ")
    assert sorted(p.name for p in (pack / "records").iterdir()) == [
        "example-engl101-course.json"
    ]
    assert not (pack / "registry" / "old-course.json").exists()
    assert (pack / "FIELD_INVENTORY.csv").read_text(encoding="utf-8") == (
        csv_text()
    )


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=D8)
def test_rebuilding_keeps_the_registry_summary(
    pack: Path, frozen: Slot
) -> None:
    (pack / "registry").mkdir()
    (pack / "registry" / "summary.json").write_text("[]", encoding="utf-8")
    build.build_pack()
    assert (pack / "registry" / "summary.json").is_file()


def test_hydrate_finds_each_excerpt_again_after_the_text_moves(
    pack: Path, frozen: Slot
) -> None:
    build.build_pack()
    path = pack / "records" / "example-engl101-course.json"
    before = json.loads(path.read_text(encoding="utf-8"))
    normalized = pack / "normalized" / f"{STEM}.txt"
    prefix = "Skip to main content\n"
    normalized.write_text(
        prefix + normalized.read_text(encoding="utf-8"), encoding="utf-8"
    )
    assert build.hydrate_pack() == []
    after = json.loads(path.read_text(encoding="utf-8"))
    starts = [
        (f["evidence"][0]["char_start"], g["evidence"][0]["char_start"])
        for f, g in zip(
            before["source_expected"]["fields"],
            after["source_expected"]["fields"],
            strict=True,
        )
    ]
    assert all(new == old + len(prefix) for old, new in starts)


def test_hydrate_reports_a_record_whose_excerpt_is_gone(
    pack: Path, frozen: Slot
) -> None:
    build.build_pack()
    (pack / "normalized" / f"{STEM}.txt").write_text(
        "rewritten\n", encoding="utf-8"
    )
    [error] = build.hydrate_pack()
    assert error.startswith("example-engl101-course.json: excerpt not found")


def test_the_manifest_lists_every_record_and_triggers_the_export(
    pack: Path, frozen: Slot, monkeypatch: pytest.MonkeyPatch
) -> None:
    exported: list[bool] = []
    monkeypatch.setattr(
        export_xtra, "export_xtra_courses", lambda: exported.append(True)
    )
    build.build_pack()
    path = build.assemble_manifest()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert path == pack / "MANIFEST.json"
    assert manifest["pack_id"] == "pack"
    assert manifest["status"] == "candidate"
    assert manifest["record_count"] == 1
    assert manifest["records"][0]["record_id"] == "example-engl101-course"
    assert manifest["records"][0]["verification.status"] == "candidate"
    assert exported == [True]
