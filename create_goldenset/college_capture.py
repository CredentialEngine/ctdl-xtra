"""Run a college-URL → candidate Course golden pack."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from config import HERE, PACK, RECORD_DIR
from catalog import college_slug
from discover import harvest_with_playwright
from dynamic_slots import write_slots
from freeze import freeze_all, meta_path, snapshot_path
from slots import Slot
from transcribe_courses import detect_template


def _is_dead_html(html: str, http_status: int | None) -> bool:
    if http_status in {404, 410}:
        return True
    title = ""
    low = html.lower()
    if "<title>" in low:
        title = html[low.find("<title>") + 7 : low.find("</title>", low.find("<title>"))].lower()
    return "404" in title or "not found" in title or "course not found" in title


def drop_dead_slots(slots: list[Slot]) -> list[Slot]:
    kept = []
    for slot in slots:
        snap = snapshot_path(slot.stem)
        if not snap.is_file():
            continue
        html = snap.read_text(encoding="utf-8", errors="replace")
        status = None
        mp = meta_path(slot.stem)
        if mp.is_file():
            status = json.loads(mp.read_text(encoding="utf-8")).get("http_status")
        if _is_dead_html(html, status):
            print(f"drop 404 {slot.requested_url}")
            continue
        kept.append(slot)
    return kept


def attach_templates(slots: list[Slot], normalized_dir: Path) -> list[Slot]:
    out = []
    for slot in slots:
        path = normalized_dir / f"{slot.stem}.txt"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        tid = detect_template(text)
        if not tid:
            print(f"drop unknown template {slot.requested_url}")
            continue
        out.append(
            Slot(
                slot.record_id,
                slot.entity_type,
                slot.requested_url,
                slot.institution_name,
                slot.source_family,
                tid,
                slot.template_version,
                slot.page_id,
                slot.copy_html,
                slot.retrieved_at,
                slot.multi_entity_bundle,
                slot.notes,
            )
        )
    return out


def harvest_seeds(
    seeds: list[str],
    *,
    per_college: int | None,
    total_limit: int | None,
    fetch_all: bool,
    institution: str | None,
) -> tuple[list[Slot], list[dict], int]:
    """Discover course URLs. Returns slots, discovery reports, and the per-college cap."""
    all_slots: list[Slot] = []
    reports: list[dict] = []
    n_colleges = len(seeds)
    if fetch_all:
        want_each = 10_000
    elif per_college is not None:
        want_each = per_college
    elif n_colleges == 1:
        want_each = total_limit or 30
    else:
        want_each = per_college or 5

    for seed in seeds:
        print(f"discover {seed}", flush=True)
        report = harvest_with_playwright(seed, want=max(want_each * 4, want_each), fetch_all=fetch_all)
        slots = report["slots"]
        if institution:
            slots = [
                Slot(
                    s.record_id,
                    s.entity_type,
                    s.requested_url,
                    institution,
                    s.source_family,
                    s.template_id,
                    s.template_version,
                    s.page_id,
                    s.copy_html,
                    s.retrieved_at,
                    s.multi_entity_bundle,
                    s.notes,
                )
                for s in slots
            ]
            report["institution_name"] = institution
        if not fetch_all and len(slots) > want_each * 4:
            slots = slots[: want_each * 4]
        report["slots"] = slots
        reports.append({k: v for k, v in report.items() if k != "slots"})
        all_slots.extend(slots)
        print(
            f"  family={report['family']} discovered={report['discovered']} "
            f"queued={len(slots)} institution={report['institution_name']}",
            flush=True,
        )
    return all_slots, reports, want_each


def run_college_capture(
    seeds: list[str],
    *,
    per_college: int | None,
    total_limit: int | None,
    fetch_all: bool,
    institution: str | None,
    skip_registry: bool = False,
) -> dict:
    from config import NORMALIZED_DIR
    from build import assemble_manifest, build_pack
    from cli import cmd_normalize
    from quality import cross_check_pack
    from validate import validate_pack

    all_slots, reports, want_each = harvest_seeds(
        seeds,
        per_college=per_college,
        total_limit=total_limit,
        fetch_all=fetch_all,
        institution=institution,
    )

    if not all_slots:
        raise SystemExit("no course URLs discovered")

    write_slots(all_slots, extra={"discovery": reports})
    freeze_all()
    all_slots = drop_dead_slots(all_slots)
    write_slots(all_slots, extra={"discovery": reports})

    NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)
    cmd_normalize(None)

    all_slots = attach_templates(all_slots, NORMALIZED_DIR)
    write_slots(all_slots, extra={"discovery": reports})

    if RECORD_DIR.is_dir():
        shutil.rmtree(RECORD_DIR)
    errors = build_pack()
    if errors:
        print("extract failures:", file=__import__("sys").stderr)
        for err in errors:
            print(f"  {err}", file=__import__("sys").stderr)
    ok_ids = {p.stem for p in RECORD_DIR.glob("*.json")}
    all_slots = [s for s in all_slots if s.record_id in ok_ids]
    if not fetch_all:
        by_seed: dict[str, list[Slot]] = {}
        for slot in all_slots:
            key = college_slug(slot.requested_url)
            by_seed.setdefault(key, []).append(slot)
        trimmed: list[Slot] = []
        for group in by_seed.values():
            trimmed.extend(group[:want_each])
        if total_limit:
            trimmed = trimmed[:total_limit]
        keep = {s.record_id for s in trimmed}
        for path in list(RECORD_DIR.glob("*.json")):
            if path.stem not in keep:
                path.unlink()
        all_slots = trimmed
    write_slots(all_slots, extra={"discovery": reports, "final": True, "dropped_extract_errors": errors})
    if not all_slots:
        raise SystemExit("every freeze failed transcription")

    from registry import lookup_pack

    if not skip_registry:
        lookup_pack()
    quality = cross_check_pack(PACK)
    runtime = validate_pack(PACK, strict_promotion=False)
    problems = quality + runtime
    assemble_manifest()
    (PACK / "CAPTURE_REPORT.json").write_text(
        json.dumps(
            {
                "seeds": seeds,
                "records": len(all_slots),
                "discovery": reports,
                "quality_errors": problems,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    schema_src = (HERE / "record.schema.json").absolute()
    if schema_src.is_file():
        shutil.copyfile(schema_src, PACK / "record.schema.json")
    return {"records": len(all_slots), "errors": problems, "pack": str(PACK)}
