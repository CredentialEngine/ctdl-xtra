"""Export schema-2 records into xTRA scoring goldens. Expected values stay freeze slices."""

from __future__ import annotations

import csv
import json
import os
import shutil
from pathlib import Path

from config import PACK, RECORD_DIR, SLOTS_NAME

COURSE_PACK = SLOTS_NAME in {"courses_30", "dynamic"} or os.environ.get("GOLDEN_SET_MODE") == "college"

FOLDER = {
    "Course": "courses",
    "LearningProgram": "learning_programs",
    "Credential": "credentials",
    "Competency": "competencies",
    "CompetencyFramework": "competency_frameworks",
    "Link": "links",
}

CATALOGUE = {
    "Course": "COURSES",
    "LearningProgram": "LEARNING_PROGRAMS",
    "Credential": "CREDENTIALS",
    "Competency": "COMPETENCIES",
    "CompetencyFramework": "COMPETENCY_FRAMEWORKS",
    "Link": "LINKS",
}


def _fields(rec: dict) -> dict:
    return {f["canonical_label"]: f["value"] for f in rec["source_expected"]["fields"]}


def _expected(rec: dict) -> dict:
    et = rec["entity_type"]
    src = _fields(rec)
    if et == "Course":
        out = {
            "course_id": src["course_id"],
            "course_name": src["course_name"],
        }
        if "course_description" in src:
            out["course_description"] = src["course_description"]
        extra = (
            "course_credits",
            "course_credits_min",
            "course_credits_max",
            "course_prerequisites",
            "course_corequisites",
            "course_lecture_hours",
            "course_lab_hours",
            "course_program",
            "course_department",
            "course_school",
            "course_division",
            "course_subject_code",
            "course_number",
            "course_long_title",
            "course_academic_level",
            "course_general_education",
        )
        if COURSE_PACK:
            for key in extra:
                if key in src:
                    out[key] = src[key]
        else:
            if "course_credits" in src:
                out["course_credits_min"] = src["course_credits"]
            if "course_prerequisites" in src:
                out["course_prerequisites"] = src["course_prerequisites"]
        return out
    if et == "LearningProgram":
        out = {"learning_program_name": src["learning_program_name"]}
        if "learning_program_id" in src:
            out["learning_program_id"] = src["learning_program_id"]
        if "learning_program_description" in src:
            out["learning_program_description"] = src["learning_program_description"]
        return out
    if et == "Credential":
        out = {"credential_name": src["credential_name"]}
        if "credential_description" in src:
            out["credential_description"] = src["credential_description"]
        return out
    if et == "Competency":
        return {"text": src["competency_text"]}
    if et == "CompetencyFramework":
        return {"competency_framework": src["competency_framework_name"]}
    if et == "Link":
        link = rec["links_expected"][0]
        return {
            "predicate": link["predicate"],
            "subject_id": link["subject_ref"],
            "object_id": link["object_ref"],
        }
    raise ValueError(et)


SKIP_FREEZE_CHECK = {"predicate", "subject_id", "object_id"}


def _assert_in_freeze(rec: dict, expected: dict) -> None:
    text = (PACK / rec["source"]["normalized_text_path"]).read_text(encoding="utf-8")
    for key, val in expected.items():
        if key in SKIP_FREEZE_CHECK:
            continue
        if not isinstance(val, str):
            continue
        if val not in text:
            raise ValueError(f"{rec['record_id']} {key} not in freeze: {val[:120]!r}")


def _drop_nested_html_copy() -> None:
    """Course goldens read snapshots/. Nested html/{stem}.html/{stem}.html is not proof."""
    html_dir = PACK / "html"
    if html_dir.exists():
        shutil.rmtree(html_dir)


def _drop_stale_xtra_json(keep: dict[str, set[str]]) -> None:
    for folder_name, names in keep.items():
        folder = PACK / folder_name
        if not folder.is_dir():
            continue
        for path in folder.glob("*.json"):
            if path.name not in names:
                path.unlink()


def _drop_unused_freezes() -> None:
    from active import unique_pages

    keep_stems = {s.stem for s in unique_pages()}
    for folder in (PACK / "snapshots", PACK / "normalized"):
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if path.name == "freeze_report.json":
                continue
            name = path.name
            stem = name
            for suf in (".meta.json", ".html", ".txt"):
                if name.endswith(suf):
                    stem = name[: -len(suf)]
                    break
            if stem not in keep_stems:
                path.unlink()


def export_xtra_goldens() -> list[Path]:
    _drop_nested_html_copy()
    written: list[Path] = []
    rows = []
    keep: dict[str, set[str]] = {name: set() for name in FOLDER.values()}
    for path in sorted(RECORD_DIR.glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        et = rec["entity_type"]
        folder = PACK / FOLDER[et]
        folder.mkdir(parents=True, exist_ok=True)
        snap = rec["source"]["snapshot_path"]
        gold = {
            "id": rec["record_id"],
            "catalogue_type": CATALOGUE[et],
            "source_url": rec["source"]["requested_url"],
            "institution": rec["source"]["institution_name"],
            "retrieved_at": rec["source"]["retrieved_at"],
            "transcription_method": (
                "verbatim copy from frozen HTML bytes in snapshots/; "
                "no LLM extract; omit fields the freeze does not print; "
                + (
                    "a single printed credit is course_credits; min/max only if the freeze prints a range"
                    if COURSE_PACK
                    else "a single printed credit is course_credits_min only"
                )
            ),
            "proof_html": snap,
            "pile": (
                os.environ.get("GOLDEN_SET_PILE")
                or ("courses_30" if SLOTS_NAME == "courses_30" else PACK.name)
                if COURSE_PACK
                else "core_30"
            ),
            "expected": _expected(rec),
        }
        _assert_in_freeze(rec, gold["expected"])
        dest = folder / f"{rec['record_id']}.json"
        dest.write_text(json.dumps(gold, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(dest)
        keep[FOLDER[et]].add(dest.name)
        rows.append(
            {
                "id": gold["id"],
                "catalogue_type": gold["catalogue_type"],
                "institution": gold["institution"],
                "source_url": gold["source_url"],
                "pile": gold["pile"],
                "proof_html": gold["proof_html"],
            }
        )
        print(f"xtra {dest.relative_to(PACK)}")

    _drop_stale_xtra_json(keep)
    _drop_unused_freezes()
    csv_path = PACK / "records.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["id", "catalogue_type", "institution", "source_url", "pile", "proof_html"],
        )
        w.writeheader()
        w.writerows(rows)
    return written
