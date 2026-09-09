"""Assemble candidate records from freeze + transcriptions."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from config import PACK, RECORD_DIR, SLOTS_NAME
from evidence import hydrate_evidence
from freeze import meta_path, snapshot_path
from inventory import csv_text as inventory_csv
from mapping import map_fields
from normalize import sha256_bytes, sha256_text
from record import locator, shell, source_block
from active import active_slots
from transcribe import entities_for_page, transcribe_slot


def _meta(stem: str) -> dict:
    path = meta_path(stem)
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def build_record(slot) -> dict:
    snap = snapshot_path(slot.stem)
    norm = PACK / "normalized" / f"{slot.stem}.txt"
    html = snap.read_bytes()
    text = norm.read_text(encoding="utf-8")
    meta = _meta(slot.stem)
    rec = shell(
        slot,
        source=source_block(
            slot,
            snapshot_rel=f"snapshots/{slot.stem}.html",
            snapshot_sha256=sha256_bytes(html),
            normalized_rel=f"normalized/{slot.stem}.txt",
            normalized_sha256=sha256_text(text),
            meta=meta,
        ),
        page=_page(slot, text),
        annotation_scope=_scope(slot, text),
    )
    drafts = transcribe_slot(slot, text)
    fields = []
    for i, draft in enumerate(drafts, start=1):
        ev = hydrate_evidence(
            evidence_id=f"ev_{i:03d}",
            excerpt=draft.excerpt,
            snapshot_sha256=rec["source"]["snapshot_sha256"],
            normalized_text_sha256=rec["source"]["normalized_text_sha256"],
            locator_strategy=draft.locator_strategy,
            locator_value=draft.locator_value,
            occurrence=draft.occurrence,
            normalized=text,
        )
        fields.append(
            {
                "field_id": draft.field_id,
                "canonical_label": draft.canonical_label,
                "presence": "present",
                "value": draft.value,
                "raw_text": draft.raw_text,
                "evidence": [ev],
                "notes": draft.notes,
            }
        )
    rec["source_expected"]["fields"] = fields
    rec["ctdl_expected"] = map_fields(slot.entity_type, fields)
    rec["links_expected"] = _links(slot, fields)
    return rec


_CHROME = {
    "Skip to main content",
    "Skip to Main Content",
    "Skip to Content",
    "Skip to content",
    "Skip to Monsido PageAssist",
    "College Catalog",
    "Fulltext search",
    "Main navigation",
    "Breadcrumb",
    "Home",
    "Catalog HOME",
    "Catalog Search",
    "Global Search",
}


def _page(slot, text: str) -> dict:
    observed = entities_for_page(slot, text)
    heading = None
    for line in text.splitlines():
        s = line.strip()
        if not s or s in _CHROME:
            continue
        heading = s
        break
    return {
        "page_id": slot.page_id,
        "title": heading,
        "canonical_url": slot.requested_url,
        "classification": "detail",
        "classification_confidence": None,
        "entity_locator": locator("whole_document", "normalized-visible-text"),
        "entities_observed": observed,
        "entity_inventory_complete": None,
    }


def _scope(slot, text: str) -> dict:
    bundle = (
        "Declared multi-entity competency bundle for this freeze: "
        "the Flight Instructor learning program plus the four printed "
        "Upon completion outcome statements."
        if slot.multi_entity_bundle
        else ""
    )
    statements = {
        "Course": "Single course detail block on this freeze.",
        "LearningProgram": "Learning program identity and description printed on this freeze. Award/credential is a separate record when the heading names an award.",
        "Credential": "Named award/credential printed on this freeze. Not a substitute for the learning program record.",
        "CompetencyFramework": "Printed framework/outcomes heading only. Individual outcome statements are out of scope for this record and are not competency slots in this pack.",
        "Competency": "One atomic printed outcome from the Upon completion list on this freeze.",
        "Link": "One source-asserted program-to-award relationship from the printed heading that names both.",
    }
    boundary = statements[slot.entity_type]
    if bundle:
        boundary = bundle + " " + boundary
    if slot.notes:
        boundary = boundary + " " + slot.notes
    return {
        "mode": "complete",
        "entity_boundary": boundary,
        "included_regions": [locator("whole_document", "in-scope entity block")],
        "excluded_regions": [],
        "partial_reason": None,
        "completeness_attested": None,
    }


def _links(slot, fields: list[dict]) -> list[dict]:
    if slot.entity_type != "Link":
        return []
    mapping = {
        "brookdale-hospm-link-results-in-credential": (
            "brookdale-hospm-learning-program",
            "brookdale-hospm-credential",
        ),
        "raritan-medical-assistant-link-results-in-credential": (
            "raritan-medical-assistant-learning-program",
            "raritan-medical-assistant-credential",
        ),
        "raritan-automotive-link-results-in-credential": (
            "raritan-automotive-learning-program",
            "raritan-automotive-credential",
        ),
    }
    subj, obj = mapping[slot.record_id]
    heading = next(f for f in fields if f["canonical_label"] == "relationship_heading")
    ev_id = heading["evidence"][0]["evidence_id"]
    return [
        {
            "link_id": "link_001",
            "predicate": "ceterms:resultsInCredential",
            "subject_ref": subj,
            "object_ref": obj,
            "object_uri": None,
            "object_label": heading["value"],
            "link_kind": "inter_record",
            "source_field_refs": [heading["field_id"]],
            "publisher_input_refs": [],
            "evidence_refs": [ev_id],
            "notes": "Heading names the program and the award on the same freeze.",
        }
    ]


def build_pack() -> list[str]:
    RECORD_DIR.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    keep = {slot.record_id for slot in active_slots()}
    for slot in active_slots():
        try:
            rec = build_record(slot)
            dest = RECORD_DIR / f"{slot.record_id}.json"
            dest.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"wrote {dest.name}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{slot.record_id}: {exc}")
    for path in RECORD_DIR.glob("*.json"):
        if path.stem not in keep:
            path.unlink()
    registry_dir = PACK / "registry"
    if registry_dir.is_dir():
        for path in registry_dir.glob("*.json"):
            if path.stem not in keep:
                path.unlink()
    (PACK / "FIELD_INVENTORY.csv").write_text(inventory_csv(), encoding="utf-8")
    return errors


def hydrate_pack() -> list[str]:
    """Re-hydrate offsets after a normalize rerun."""
    errors = []
    for path in sorted(RECORD_DIR.glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        text = (PACK / rec["source"]["normalized_text_path"]).read_text(encoding="utf-8")
        try:
            for field in rec["source_expected"]["fields"]:
                for ev in field["evidence"]:
                    hydrated = hydrate_evidence(
                        evidence_id=ev["evidence_id"],
                        excerpt=ev["excerpt"],
                        snapshot_sha256=rec["source"]["snapshot_sha256"],
                        normalized_text_sha256=rec["source"]["normalized_text_sha256"],
                        locator_strategy=ev["locator"]["strategy"],
                        locator_value=ev["locator"]["value"],
                        occurrence=ev.get("occurrence") or ev["locator"].get("occurrence"),
                        normalized=text,
                    )
                    ev.update(hydrated)
            path.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path.name}: {exc}")
    return errors


def assemble_manifest() -> Path:
    records = []
    for path in sorted(RECORD_DIR.glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        records.append(
            {
                "record_id": rec["record_id"],
                "entity_type": rec["entity_type"],
                "institution_name": rec["source"]["institution_name"],
                "template_id": rec["source"]["template_id"],
                "source_family": rec["source"]["source_family"],
                "requested_url": rec["source"]["requested_url"],
                "snapshot_sha256": rec["source"]["snapshot_sha256"],
                "verification.status": rec["verification"]["status"],
            }
        )
    if SLOTS_NAME == "courses_30":
        notes = [
            "Courses-only candidate pack. Dual named human review is required before human_signed export.",
            "30 Course records from seven New Jersey colleges. Proof is snapshots/{stem}.html only.",
            "A single printed credit is course_credits. course_credits_min/max are omitted unless the freeze prints both bounds or a range.",
            "catalog_edition is omitted when the freeze does not print an edition. proof_snapshot is not written.",
            "Registry lookup uses exact ceterms:subjectWebpage = catalog URL. No name matching. Without an API key the status stays not_checked.",
            "Do not quote this pack as official extract accuracy. Do not use --signed-only.",
        ]
        pack_id = "golden_set_courses_30"
    elif SLOTS_NAME == "dynamic":
        notes = [
            "Generic college Course pack. Candidates only. Dual named human review is required before human_signed.",
            "Expected values are freeze slices. No LLM-invented fields.",
            "A single printed credit is course_credits. min/max only if the freeze prints a range.",
            "Registry lookup uses exact ceterms:subjectWebpage. Without an API key status is not_checked.",
            "Do not quote this pack as official extract accuracy. Do not use --signed-only.",
        ]
        pack_id = PACK.name
    else:
        notes = [
            "Candidates only. Dual named human review is required before human_signed.",
            "Expected values are freeze slices. No LLM-invented fields.",
            "Do not quote this pack as official extract accuracy. Do not use --signed-only.",
        ]
        pack_id = PACK.name
    manifest = {
        "pack_id": pack_id,
        "schema_version": "2.0.0",
        "status": "candidate",
        "record_count": len(records),
        "notes": notes,
        "records": records,
    }
    dest = PACK / "MANIFEST.json"
    dest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    from export_xtra import export_xtra_goldens

    export_xtra_goldens()
    return dest
