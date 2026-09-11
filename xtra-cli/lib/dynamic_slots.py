"""Load Course slots from pack/slots.json for generic college captures."""

from __future__ import annotations

import json
from pathlib import Path

from config import PACK
from slots import Slot


def slots_path() -> Path:
    return PACK / "slots.json"


def slot_from_dict(row: dict) -> Slot:
    copy = row.get("copy_html")
    return Slot(
        row["record_id"],
        row.get("entity_type", "Course"),
        row["requested_url"],
        row["institution_name"],
        row["source_family"],
        row["template_id"],
        str(row.get("template_version") or "1"),
        row.get("page_id") or row["record_id"],
        Path(copy) if copy else None,
        row.get("retrieved_at"),
        bool(row.get("multi_entity_bundle") or False),
        row.get("notes") or "",
    )


def load_slots() -> list[Slot]:
    path = slots_path()
    if not path.is_file():
        raise FileNotFoundError(f"missing {path}; run capture_college_courses.py discover first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("slots") if isinstance(payload, dict) else payload
    return [slot_from_dict(row) for row in rows]


def unique_pages() -> list[Slot]:
    seen: set[str] = set()
    out: list[Slot] = []
    for slot in load_slots():
        if slot.stem in seen:
            continue
        seen.add(slot.stem)
        out.append(slot)
    return out


def write_slots(slots: list[Slot], *, extra: dict | None = None) -> Path:
    path = slots_path()
    payload = {
        "schema": "xtra-slots-1",
        "slots": [
            {
                "record_id": s.record_id,
                "entity_type": s.entity_type,
                "requested_url": s.requested_url,
                "institution_name": s.institution_name,
                "source_family": s.source_family,
                "template_id": s.template_id,
                "template_version": s.template_version,
                "page_id": s.page_id,
                "copy_html": str(s.copy_html) if s.copy_html else None,
                "retrieved_at": s.retrieved_at,
                "multi_entity_bundle": s.multi_entity_bundle,
                "notes": s.notes,
            }
            for s in slots
        ],
    }
    if extra:
        payload.update(extra)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
