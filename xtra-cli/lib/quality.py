"""Strict freeze-backed checks for course packs."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from html_text import pack_join


def cross_check_pack(pack: Path) -> list[str]:
    errors: list[str] = []
    rec_dir = pack / "records"
    for path in sorted(rec_dir.glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        fields = {f["canonical_label"]: f for f in rec.get("source_expected", {}).get("fields", [])}
        labels = set(fields)
        rid = rec["record_id"]
        if rec.get("entity_type") != "Course":
            errors.append(f"{rid}: generic college pack only accepts Course")
            continue
        if rec.get("verification", {}).get("status") == "human_signed":
            errors.append(f"{rid}: builder must not emit human_signed")
        if "course_id" not in labels or "course_name" not in labels:
            errors.append(f"{rid}: missing course_id or course_name")
        if "course_credits" in labels and (
            "course_credits_min" in labels or "course_credits_max" in labels
        ):
            errors.append(f"{rid}: single course_credits cannot also have min/max")
        if "course_credits_min" in labels and "course_credits_max" not in labels:
            errors.append(f"{rid}: min without printed max")
        if "course_credits_max" in labels and "course_credits_min" not in labels:
            errors.append(f"{rid}: max without printed min")
        name = fields.get("course_name", {}).get("value")
        cid = fields.get("course_id", {}).get("value")
        if isinstance(name, str) and isinstance(cid, str) and name.strip() == cid.strip():
            errors.append(f"{rid}: course_name is the code; split the heading")
        if isinstance(name, str) and re_has_glued_credit(name):
            errors.append(f"{rid}: course_name still contains glued credits")
        text_path = pack_join(pack, rec["source"]["normalized_text_path"])
        text = text_path.read_text(encoding="utf-8") if text_path.is_file() else ""
        for field in fields.values():
            val = field.get("value")
            if isinstance(val, str) and val and val not in text:
                errors.append(f"{rid} {field['canonical_label']}: value not in freeze")
            for ev in field.get("evidence") or []:
                excerpt = ev.get("excerpt") or ""
                if excerpt and excerpt not in text:
                    errors.append(f"{rid} {field['field_id']}: excerpt not in freeze")
    errors.extend(check_xtra_course_exports(pack))
    return errors


def check_xtra_course_exports(pack: Path) -> list[str]:
    """Wrapper rules for courses/*.json: one freeze file, no null edition, no mid-label prereq."""
    errors: list[str] = []
    course_dir = pack / "courses"
    if not course_dir.is_dir():
        return errors
    for path in sorted(course_dir.glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        rid = row.get("id") or path.stem
        if "catalog_edition" in row:
            errors.append(f"{rid}: omit catalog_edition instead of storing null")
        if "proof_snapshot" in row:
            errors.append(f"{rid}: omit proof_snapshot; proof_html is the freeze")
        proof = (row.get("proof_html") or "").replace("\\", "/")
        if not proof:
            errors.append(f"{rid}: missing proof_html")
            continue
        if (
            Path(proof).is_absolute()
            or proof.startswith("~")
            or proof.startswith("/")
            or (len(proof) >= 2 and proof[1] == ":")
        ):
            errors.append(f"{rid}: proof_html must be pack-relative, not a machine path")
            continue
        parts = PurePosixPath(proof).parts
        if proof.startswith("html/") or (len(parts) >= 2 and parts[-1] == parts[-2]):
            errors.append(f"{rid}: doubled proof path {proof}")
        dest = pack_join(pack, proof)
        if not dest.is_file():
            errors.append(f"{rid}: proof_html {proof} is not a file")
        pre = (row.get("expected") or {}).get("course_prerequisites")
        if isinstance(pre, str) and pre.lstrip().lower().startswith("and corequisite"):
            errors.append(f"{rid}: course_prerequisites starts mid-label")
    return errors


def re_has_glued_credit(name: str) -> bool:
    import re

    return bool(re.search(r"\d+ Credit", name))
