"""The runtime checks JSON Schema cannot express: hashes against the frozen
files, evidence spans, labels, and the candidate-pack gates."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import validate
from lib_doubles import (
    course_record,
    example_slot,
    make_record,
    numbered_slot_fields,
    write_record,
)
from validate import validate_pack, validate_record


def first_field(rec: dict) -> dict:
    return rec["source_expected"]["fields"][0]


def first_evidence(rec: dict) -> dict:
    return first_field(rec)["evidence"][0]


def set_stage_count(rec: dict) -> None:
    rec["verification"]["stage_reviews"].pop()


def set_stage_names(rec: dict) -> None:
    rec["verification"]["stage_reviews"][0]["stage"] = "linking"


def set_stage_status(rec: dict) -> None:
    rec["verification"]["stage_reviews"][1]["status"] = "reviewed"


def duplicate_field(rec: dict) -> None:
    rec["source_expected"]["fields"][1]["field_id"] = "src_001"


def drop_offsets(rec: dict) -> None:
    first_evidence(rec)["char_start"] = None


def shift_offsets(rec: dict) -> None:
    first_evidence(rec)["char_start"] += 1


def wrong_excerpt_hash(rec: dict) -> None:
    first_evidence(rec)["excerpt_sha256"] = "0" * 64


def drift_snapshot(rec: dict) -> None:
    first_evidence(rec)["snapshot_sha256"] = "0" * 64


def drift_text(rec: dict) -> None:
    first_evidence(rec)["normalized_text_sha256"] = "0" * 64


def foreign_excerpt(rec: dict) -> None:
    first_evidence(rec)["excerpt"] = "Not printed"


RULES = [
    pytest.param(
        lambda rec: rec.update(schema_version="1.0.0"),
        "schema_version must be 2.0.0",
        id="schema-version",
    ),
    pytest.param(
        lambda rec: rec.update(entity_type="Program"),
        "bad entity_type Program",
        id="entity-type",
    ),
    pytest.param(
        lambda rec: rec["verification"].update(status="human_signed"),
        "builder must not emit human_signed",
        id="human-signed",
    ),
    pytest.param(
        lambda rec: rec["verification"].update(reviewer_2={"person_id": "x"}),
        "candidate must leave reviewers null",
        id="reviewer",
    ),
    pytest.param(
        lambda rec: rec["verification"].update(
            signed_at="2026-10-21T00:00:00Z"
        ),
        "candidate must leave signed_at null",
        id="signed-at",
    ),
    pytest.param(
        set_stage_count,
        "stage_reviews must have exactly 4 entries",
        id="stage-count",
    ),
    pytest.param(
        set_stage_names,
        "stage_reviews must cover all four stages",
        id="stage-names",
    ),
    pytest.param(
        set_stage_status,
        "candidate pack stage_reviews must stay candidate",
        id="stage-status",
    ),
    pytest.param(
        lambda rec: rec["source"].update(snapshot_sha256="0" * 64),
        "snapshot_sha256 mismatch",
        id="snapshot-hash",
    ),
    pytest.param(
        lambda rec: rec["source"].update(normalized_text_sha256="0" * 64),
        "normalized_text_sha256 mismatch",
        id="normalized-hash",
    ),
    pytest.param(
        duplicate_field, "duplicate field_id src_001", id="duplicate-field"
    ),
    pytest.param(
        lambda rec: first_field(rec).update(canonical_label="course_title"),
        "src_001 label course_title not in FIELD_INVENTORY",
        id="unknown-label",
    ),
    pytest.param(
        lambda rec: first_field(rec).update(canonical_label="credential_name"),
        "src_001 label credential_name not allowed for Course",
        id="label-for-another-type",
    ),
    pytest.param(
        lambda rec: first_field(rec).update(value=" N/A "),
        "placeholder value on src_001",
        id="placeholder",
    ),
    pytest.param(
        lambda rec: first_field(rec).update(evidence=[]),
        "present field src_001 has no evidence",
        id="no-evidence",
    ),
    pytest.param(drop_offsets, "ev_001 missing offsets/excerpt", id="offsets"),
    pytest.param(
        shift_offsets, "ev_001 excerpt != normalized[start:end]", id="span"
    ),
    pytest.param(
        wrong_excerpt_hash, "ev_001 excerpt_sha256 mismatch", id="excerpt-hash"
    ),
    pytest.param(
        drift_snapshot, "ev_001 snapshot hash drift", id="ev-snapshot"
    ),
    pytest.param(drift_text, "ev_001 normalized hash drift", id="ev-text"),
    pytest.param(
        foreign_excerpt,
        "ev_001 excerpt not in normalized text",
        id="foreign-excerpt",
    ),
]


def test_a_freshly_built_record_passes(pack: Path) -> None:
    assert validate_record(course_record(pack, write=False), pack=pack) == []


@pytest.mark.parametrize(("break_it", "message"), RULES)
def test_each_broken_rule_is_reported(
    pack: Path, break_it: Callable[[dict], None], message: str
) -> None:
    rec = course_record(pack, write=False)
    break_it(rec)
    assert message in validate_record(rec, pack=pack)


def test_a_missing_snapshot_stops_the_file_checks(pack: Path) -> None:
    rec = course_record(pack, write=False)
    rec["source"]["snapshot_path"] = "cache/2026-10-21/gone.html"
    rec["source"]["normalized_text_sha256"] = "0" * 64
    errors = validate_record(rec, pack=pack)
    assert [e for e in errors if e.startswith("missing snapshot")] != []
    assert "normalized_text_sha256 mismatch" not in errors


def test_a_missing_normalized_text_stops_the_file_checks(pack: Path) -> None:
    rec = course_record(pack, write=False)
    rec["source"]["normalized_text_path"] = "normalized/gone.txt"
    errors = validate_record(rec, pack=pack)
    assert [e for e in errors if e.startswith("missing normalized")] != []
    assert not [e for e in errors if e.startswith("ev_")]


def test_a_field_not_marked_present_needs_no_evidence(pack: Path) -> None:
    rec = course_record(pack, write=False)
    first_field(rec).update(presence="not_present", value=None, evidence=[])
    assert validate_record(rec, pack=pack) == []


def test_schema_errors_are_reported_when_the_pack_carries_the_schema(
    pack: Path,
) -> None:
    pytest.importorskip("jsonschema")
    rec = course_record(pack, write=False)
    rec["unexpected"] = 1
    errors = validate_record(rec, pack=pack)
    assert [e for e in errors if e.startswith("schema:")] == [
        "schema: Additional properties are not allowed ('unexpected' was "
        "unexpected)"
    ]


@pytest.mark.parametrize("why", ["no-jsonschema", "no-schema-file"])
def test_without_a_validator_or_schema_file_only_runtime_checks_run(
    pack: Path, monkeypatch: pytest.MonkeyPatch, why: str
) -> None:
    if why == "no-jsonschema":
        monkeypatch.setattr(validate, "Draft202012Validator", None)
    else:
        (pack / "record.schema.json").unlink()
    rec = course_record(pack, write=False)
    rec["unexpected"] = 1
    assert validate_record(rec, pack=pack) == []


def credential_record(pack: Path, n: int) -> dict:
    return make_record(
        pack,
        example_slot(
            entity_type="Credential",
            template_id="markup_v1",
            **numbered_slot_fields(n),
        ),
        html="<p>Associate in Applied Science</p>",
        text="Associate in Applied Science\n",
        fields=[
            (
                "credential_name",
                "Associate in Applied Science",
                "Associate in Applied Science",
            )
        ],
    )


def test_a_college_pack_needs_at_least_one_record(pack: Path) -> None:
    """An empty pack is also missing every entity type."""
    errors = validate_pack(pack)
    assert errors[0] == "pack has 0 records"
    assert errors[1].startswith("missing entity types: ['Competency'")
    course_record(pack)
    assert validate_pack(pack) == []


def test_a_mixed_pack_must_hold_thirty_records_of_every_type(
    pack: Path,
) -> None:
    course_record(pack)
    credential_record(pack, 1)
    errors = validate_pack(pack)
    assert "pack has 2 records, required 30" in errors
    assert (
        "missing entity types: ['Competency', 'CompetencyFramework', "
        "'LearningProgram', 'Link']"
    ) in errors


def test_college_mode_relaxes_the_thirty_record_rule(
    pack: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course_record(pack)
    credential_record(pack, 1)
    monkeypatch.setenv("XTRA_MODE", "college")
    assert "pack has 2 records, required 30" not in validate_pack(pack)


def test_a_mixed_pack_caps_each_institution_at_six_records(pack: Path) -> None:
    credential_record(pack, 0)
    for n in range(1, 7):
        course_record(pack, **numbered_slot_fields(n))
    assert "Example College has 7 records (max 6)" in validate_pack(pack)


def test_a_record_id_may_appear_only_once(pack: Path) -> None:
    write_record(pack, course_record(pack), name="copy")
    assert "duplicate record_id" in validate_pack(pack)


def test_more_than_three_records_on_one_page_need_a_bundle_note(
    pack: Path,
) -> None:
    records = [course_record(pack, **numbered_slot_fields(n)) for n in range(4)]
    errors = validate_pack(pack)
    assert [e for e in errors if "page has 4 records" in e] != []
    for rec in records:
        rec["annotation_scope"]["entity_boundary"] = (
            "Declared multi-entity set."
        )
        write_record(pack, rec)
    assert [e for e in validate_pack(pack) if "page has" in e] == []


def test_strict_promotion_needs_five_to_ten_per_template_and_two_reviewers(
    pack: Path,
) -> None:
    course_record(pack)
    errors = validate_pack(pack, strict_promotion=True)
    assert errors == [
        "template_id clean_catalog_course_detail has 1 records (need 5-10)",
        "strict-promotion also requires dual human reviewers; this pack is "
        "candidate-only",
    ]


def test_a_mixed_pack_applies_the_template_gate_as_an_error(pack: Path) -> None:
    course_record(pack)
    credential_record(pack, 1)
    assert (
        "warning-as-error: template_id markup_v1 has 1 records (need 5-10 for "
        "promotion)"
    ) in validate_pack(pack)


def test_record_errors_are_prefixed_with_their_file(pack: Path) -> None:
    rec = course_record(pack)
    rec["schema_version"] = "1.0.0"
    path = write_record(pack, rec)
    assert f"{path.name}: schema_version must be 2.0.0" in validate_pack(pack)
