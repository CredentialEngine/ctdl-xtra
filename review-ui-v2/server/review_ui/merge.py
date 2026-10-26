"""Merge per-page entities into records, one record per course code.

A course can be seen on its own page and again as a stub in several program
pages. Each field value keeps its source_url, and each gets a stable
``field_id`` so a reviewer's decision about "this value on this page" survives
re-extraction.
"""

from __future__ import annotations

from collections import defaultdict

from .normalize import normalize_value, record_id_from_code, safe_filename
from .template import TemplateProperty

CODE_LABEL = "Coded Notation"
DERIVED_TYPES = ("constant", "source_url")


def field_id(record_id: str, label: str, source_url: str, occurrence: int) -> str:
    return f"{record_id}::{label}::{source_url}::{occurrence}"


def label_id(source_url: str, label: str, rule_id: str) -> str:
    return f"label::{source_url}::{label}::{rule_id}"


def _entity_record_id(entity: dict, stem: str) -> str:
    for field in entity["fields"]:
        if field["canonical_label"] == CODE_LABEL and field["presence"] == "present":
            return safe_filename(record_id_from_code(field["value"]))
    # No code found: keep the entity visible rather than dropping it silently.
    return safe_filename(f"UNCODED-{stem}-{entity['label_rule_id']}-{entity['index']}")


def merge_pages(
    page_results: list[dict], properties: list[TemplateProperty]
) -> dict[str, dict]:
    """page_results: engine.run_page output, each with an added ``stem``."""
    order = {prop.name: i for i, prop in enumerate(properties)}
    required = [prop.name for prop in properties if prop.required]
    term_of = {prop.name: prop.term for prop in properties}

    present: dict[str, list[dict]] = defaultdict(list)
    sources: dict[str, list[str]] = defaultdict(list)  # first-seen page order
    seen: set[tuple] = set()
    occurrence: dict[tuple, int] = defaultdict(int)

    for page in sorted(page_results, key=lambda p: p["url"]):
        for entity in page["entities"]:
            rid = _entity_record_id(entity, page["stem"])
            if page["url"] not in sources[rid]:
                sources[rid].append(page["url"])
            for field in entity["fields"]:
                if field["presence"] != "present":
                    continue
                identity = (
                    rid,
                    field["canonical_label"],
                    page["url"],
                    normalize_value(field["value"]),
                )
                if identity in seen:  # same value listed twice on one page
                    continue
                seen.add(identity)
                slot = (rid, field["canonical_label"], page["url"])
                n = occurrence[slot]
                occurrence[slot] += 1
                present[rid].append(
                    {
                        **field,
                        "source_url": page["url"],
                        "field_id": field_id(
                            rid, field["canonical_label"], page["url"], n
                        ),
                    }
                )

    records: dict[str, dict] = {}
    for rid, fields in present.items():
        have = {f["canonical_label"] for f in fields}
        for label in required:
            if label not in have:
                url = sources[rid][0]
                fields.append(
                    {
                        "canonical_label": label,
                        "ctdl_property": term_of.get(label),
                        "rule_id": None,
                        "rule_type": None,
                        "presence": "absent",
                        "value": None,
                        "raw_text": None,
                        "location": None,
                        "source_url": url,
                        "field_id": field_id(rid, label, url, 0),
                    }
                )
        fields.sort(
            key=lambda f: (
                order.get(f["canonical_label"], 10_000),
                f["source_url"],
                f["field_id"],
            )
        )
        records[rid] = {
            "record_id": rid,
            "catalogue_type": "COURSES",
            "entity_type": "Course",
            "source_urls": sources[rid],
            "source_expected": {"fields": fields},
            "conflicts": _conflicts(fields),
        }
    return records


def _loose_key(value: str) -> str:
    """Spelling-insensitive key: 'MUSC 124A' == 'MUSC124A', '1.0' == '1'."""
    squashed = "".join(value.split()).lower()
    try:
        return format(float(squashed), "g")
    except ValueError:
        return squashed


def _conflicts(fields: list[dict]) -> list[dict]:
    """Labels whose values genuinely differ between sources."""
    by_label: dict[str, dict[str, dict]] = defaultdict(dict)
    for f in fields:
        if f["presence"] != "present" or f["rule_type"] in DERIVED_TYPES:
            continue
        entry = by_label[f["canonical_label"]].setdefault(
            _loose_key(f["value"]), {"value": f["value"], "source_urls": []}
        )
        entry["source_urls"].append(f["source_url"])
    return [
        {"canonical_label": label, "values": list(values.values())}
        for label, values in by_label.items()
        if len(values) > 1
    ]
