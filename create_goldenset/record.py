"""Candidate record shell. Never sets human_signed."""

from __future__ import annotations

from datetime import datetime, timezone

from config import MAPPING_VERSION, NORMALIZER_TOOL, NORMALIZER_VERSION, SCHEMA_RELEASE
from slots import Slot

ANNOTATOR = {
    "person_id": "golden-set-v4-candidate-builder",
    "display_name": "golden-set candidate builder",
    "completed_at": None,
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def empty_checklist() -> dict:
    return {
        "frozen_source_opened": False,
        "side_by_side_source_check": False,
        "all_values_evidence_backed": False,
        "no_unsupported_inference": False,
        "ctdl_mapping_checked": False,
        "registry_result_checked": False,
        "links_checked": False,
        "scope_completeness_checked": False,
    }


def candidate_stage_reviews() -> list[dict]:
    return [
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


def not_checked_registry() -> dict:
    return {
        "status": "not_checked",
        "checked_at": None,
        "registry_ctid": None,
        "registry_url": None,
        "registry_snapshot_path": None,
        "registry_resource_sha256": None,
        "property_comparisons": [],
        "notes": "No frozen published Registry response was supplied for this candidate pack.",
    }


def empty_ctdl(entity_type: str) -> dict:
    class_uri = {
        "Course": "ceterms:Course",
        "LearningProgram": "ceterms:LearningProgram",
        "Credential": "ceterms:Credential",
        "CompetencyFramework": "ceasn:CompetencyFramework",
        "Competency": "ceasn:Competency",
        "Link": None,
    }[entity_type]
    return {
        "class_uri": class_uri,
        "schema_release": SCHEMA_RELEASE,
        "mapping_version": MAPPING_VERSION,
        "properties": [],
        "unmapped_source_field_refs": [],
    }


def locator(strategy: str, value: str, occurrence: int | None = None) -> dict:
    return {
        "strategy": strategy,
        "value": value,
        "occurrence": occurrence,
        "page_number": None,
        "bbox": None,
    }


def shell(slot: Slot, *, source: dict, page: dict, annotation_scope: dict) -> dict:
    completed = _now()
    annotator = dict(ANNOTATOR)
    annotator["completed_at"] = completed
    return {
        "schema_version": "2.0.0",
        "record_id": slot.record_id,
        "entity_type": slot.entity_type,
        "source": source,
        "page": page,
        "annotation_scope": annotation_scope,
        "verification": {
            "status": "candidate",
            "annotator": annotator,
            "reviewer_1": None,
            "reviewer_2": None,
            "signed_at": None,
            "stage_reviews": candidate_stage_reviews(),
            "checklist": empty_checklist(),
            "notes": (
                "Model/builder candidate only. Dual named human review is still required "
                "before promotion. Checklist items remain false."
            ),
        },
        "publisher_inputs": [],
        "source_expected": {"fields": []},
        "ctdl_expected": empty_ctdl(slot.entity_type),
        "registry_expected": not_checked_registry(),
        "links_expected": [],
    }


def source_block(
    slot: Slot,
    *,
    snapshot_rel: str,
    snapshot_sha256: str,
    normalized_rel: str,
    normalized_sha256: str,
    meta: dict,
) -> dict:
    return {
        "institution_name": slot.institution_name,
        "institution_identifier": None,
        "catalog_name": None,
        "catalog_version": None,
        "requested_url": slot.requested_url,
        "final_url": meta.get("final_url") or slot.requested_url,
        "source_kind": "html",
        "media_type": "text/html",
        "retrieved_at": meta.get("retrieved_at") or slot.retrieved_at,
        "snapshot_path": snapshot_rel,
        "snapshot_sha256": snapshot_sha256,
        "normalized_text_path": normalized_rel,
        "normalized_text_sha256": normalized_sha256,
        "source_family": slot.source_family,
        "template_id": slot.template_id,
        "template_version": slot.template_version,
        "acquisition": {
            "http_status": meta.get("http_status"),
            "content_type": meta.get("content_type"),
            "redirect_chain": meta.get("redirect_chain") or [],
            "etag": meta.get("etag"),
            "last_modified": meta.get("last_modified"),
        },
        "normalization": {
            "tool": NORMALIZER_TOOL,
            "version": NORMALIZER_VERSION,
            "options": {"nbsp": "preserve", "visible_text": "html.parser"},
        },
        "pdf": None,
        "script_provenance": None,
    }
