"""Runtime checks JSON Schema cannot express."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from config import SLOTS_NAME
from inventory import INVENTORY
from normalize import sha256_bytes, sha256_text

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None

PLACEHOLDERS = {"unknown", "n/a", "none", "tbd", "not provided", ""}
TYPES = {
    "Course",
    "LearningProgram",
    "Credential",
    "CompetencyFramework",
    "Competency",
    "Link",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_record(rec: dict, *, pack: Path) -> list[str]:
    errors: list[str] = []
    if rec.get("schema_version") != "2.0.0":
        errors.append("schema_version must be 2.0.0")
    et = rec.get("entity_type")
    if et not in TYPES:
        errors.append(f"bad entity_type {et}")
    if rec.get("verification", {}).get("status") == "human_signed":
        errors.append("builder must not emit human_signed")
    if Draft202012Validator is not None:
        schema_path = pack / "record.schema.json"
        if schema_path.is_file():
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            for err in Draft202012Validator(schema).iter_errors(rec):
                errors.append(f"schema: {err.message}")
    ver = rec.get("verification", {})
    if ver.get("reviewer_1") is not None or ver.get("reviewer_2") is not None:
        errors.append("candidate must leave reviewers null")
    if ver.get("signed_at") is not None:
        errors.append("candidate must leave signed_at null")
    stages = ver.get("stage_reviews") or []
    if len(stages) != 4:
        errors.append("stage_reviews must have exactly 4 entries")
    elif {s.get("stage") for s in stages} != {
        "extraction",
        "mapping",
        "registry_reconciliation",
        "linking",
    }:
        errors.append("stage_reviews must cover all four stages")
    elif any(s.get("status") != "candidate" for s in stages):
        errors.append("candidate pack stage_reviews must stay candidate")

    snap = pack / rec["source"]["snapshot_path"]
    norm = pack / rec["source"]["normalized_text_path"]
    if not snap.is_file():
        errors.append(f"missing snapshot {snap}")
        return errors
    if not norm.is_file():
        errors.append(f"missing normalized {norm}")
        return errors
    html = snap.read_bytes()
    text = norm.read_text(encoding="utf-8")
    if sha256_bytes(html) != rec["source"]["snapshot_sha256"]:
        errors.append("snapshot_sha256 mismatch")
    if sha256_text(text) != rec["source"]["normalized_text_sha256"]:
        errors.append("normalized_text_sha256 mismatch")

    seen_fields: set[str] = set()
    for field in rec.get("source_expected", {}).get("fields", []):
        fid = field.get("field_id")
        if fid in seen_fields:
            errors.append(f"duplicate field_id {fid}")
        seen_fields.add(fid)
        label = field.get("canonical_label")
        if label not in INVENTORY:
            errors.append(f"{fid} label {label} not in FIELD_INVENTORY")
        elif et not in INVENTORY[label][0]:
            errors.append(f"{fid} label {label} not allowed for {et}")
        val = field.get("value")
        if isinstance(val, str) and val.strip().lower() in PLACEHOLDERS:
            errors.append(f"placeholder value on {fid}")
        if field.get("presence") != "present":
            continue
        evs = field.get("evidence") or []
        if not evs:
            errors.append(f"present field {fid} has no evidence")
        for ev in evs:
            start, end = ev.get("char_start"), ev.get("char_end")
            excerpt = ev.get("excerpt")
            eid = ev.get("evidence_id")
            if start is None or end is None or excerpt is None:
                errors.append(f"{eid} missing offsets/excerpt")
                continue
            if text[start:end] != excerpt:
                errors.append(f"{eid} excerpt != normalized[start:end]")
            if ev.get("excerpt_sha256") != sha256_text(excerpt):
                errors.append(f"{eid} excerpt_sha256 mismatch")
            if ev.get("snapshot_sha256") != rec["source"]["snapshot_sha256"]:
                errors.append(f"{eid} snapshot hash drift")
            if ev.get("normalized_text_sha256") != rec["source"]["normalized_text_sha256"]:
                errors.append(f"{eid} normalized hash drift")
            if excerpt not in text:
                errors.append(f"{eid} excerpt not in normalized text")
    return errors


def validate_pack(pack: Path, *, strict_promotion: bool = False) -> list[str]:
    rec_dir = pack / "records"
    files = sorted(rec_dir.glob("*.json"))
    errors: list[str] = []
    records = []
    for path in files:
        rec = _load(path)
        records.append(rec)
        rec_errs = validate_record(rec, pack=pack)
        errors.extend(f"{path.name}: {e}" for e in rec_errs)
    n = len(records)
    import os

    mode = os.environ.get("GOLDEN_SET_MODE", "")
    types = {r["entity_type"] for r in records}
    college_pack = (
        mode == "college"
        or SLOTS_NAME in {"dynamic", "courses_30"}
        or types == {"Course"}
    )
    if college_pack:
        if n < 1:
            errors.append("pack has 0 records")
    elif n != 30:
        errors.append(f"pack has {n} records, required 30")
    if types == {"Course"}:
        pass
    else:
        missing = TYPES - types
        if missing:
            errors.append(f"missing entity types: {sorted(missing)}")
    inst = Counter(r["source"]["institution_name"] for r in records)
    if not college_pack:
        for name, count in inst.items():
            if count > 6:
                errors.append(f"{name} has {count} records (max 6)")
    ids = [r["record_id"] for r in records]
    if len(ids) != len(set(ids)):
        errors.append("duplicate record_id")
    hashes = Counter(r["source"]["snapshot_sha256"] for r in records)
    page_counts = Counter()
    for r in records:
        page_counts[r["source"]["snapshot_sha256"]] += 1
    for rec in records:
        sha = rec["source"]["snapshot_sha256"]
        if page_counts[sha] > 3:
            notes = rec.get("annotation_scope", {}).get("entity_boundary", "")
            if "multi-entity" not in notes.lower() and "multi_entity" not in notes.lower():
                errors.append(
                    f"{rec['record_id']}: page has {page_counts[sha]} records; "
                    "mark multi-entity bundle in annotation_scope.entity_boundary or keep ≤3"
                )
                break
    templates = Counter(r["source"]["template_id"] for r in records)
    if college_pack and not strict_promotion:
        pass
    elif strict_promotion:
        for tid, count in templates.items():
            if count < 5 or count > 10:
                errors.append(f"template_id {tid} has {count} records (need 5-10)")
        errors.append("strict-promotion also requires dual human reviewers; this pack is candidate-only")
    else:
        for tid, count in templates.items():
            if count < 5 or count > 10:
                errors.append(f"warning-as-error: template_id {tid} has {count} records (need 5-10 for promotion)")
    return errors
