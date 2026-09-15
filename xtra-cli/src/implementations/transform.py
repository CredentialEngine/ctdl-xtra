"""Map extracted labels to CTDL JSON-LD. Never invents CTIDs."""

from __future__ import annotations

from typing import Any

from implementations.engine import load_engine

load_engine()

from mapping import map_fields


def to_jsonld(record: dict[str, Any]) -> dict[str, Any]:
    ctdl = record.get("ctdl_expected") or map_fields(
        record.get("entity_type") or "Course",
        (record.get("source_expected") or {}).get("fields") or [],
    )
    node: dict[str, Any] = {
        "@context": "https://credreg.net/ctdl/schema/context/json",
        "@type": ctdl.get("class_uri"),
        "ceterms:subjectWebpage": record.get("source_url"),
    }
    for prop in ctdl.get("properties") or []:
        node[prop["property"]] = prop["value"]
    return node


def to_expected(record: dict[str, Any]) -> dict[str, Any]:
    fields = (record.get("source_expected") or {}).get("fields") or []
    expected = record.get("expected") or {
        field["canonical_label"]: field["value"]
        for field in fields
        if field.get("presence") == "present"
    }
    return {
        "id": record.get("id") or record.get("record_id"),
        "catalogue_type": record.get("catalogue_type") or "COURSES",
        "source_url": record.get("source_url"),
        "expected": expected,
    }
