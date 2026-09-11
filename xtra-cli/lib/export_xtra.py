"""Export schema-2 records into xTRA scoring JSON. Expected values stay freeze slices."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from config import PACK, RECORD_DIR, env_get
from html_text import pack_join

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
        for key in extra:
            if key in src:
                out[key] = src[key]
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


def _proof_folder(snap: str) -> str:
    proof = snap.replace("\\", "/")
    if proof.startswith("cache/"):
        return "cache/"
    if proof.startswith("snapshots/"):
        return "snapshots/"
    if "/" in proof:
        return proof.split("/", 1)[0] + "/"
    return "the freeze file"


def _transcription_method(snap: str) -> str:
    return (
        f"verbatim copy from frozen HTML bytes in {_proof_folder(snap)}; "
        "no LLM extract; omit fields the freeze does not print; "
        "a single printed credit is course_credits; min/max only if the freeze prints a range"
    )


def _assert_in_freeze(rec: dict, expected: dict) -> None:
    text = pack_join(PACK, rec["source"]["normalized_text_path"]).read_text(encoding="utf-8")
    for key, val in expected.items():
        if key in SKIP_FREEZE_CHECK:
            continue
        if not isinstance(val, str):
            continue
        if val not in text:
            raise ValueError(f"{rec['record_id']} {key} not in freeze: {val[:120]!r}")


def _drop_nested_html_copy() -> None:
    """Course scoring JSON reads cache/ or snapshots/. Nested html/{stem}.html/{stem}.html is not proof."""
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
    """Prune derived files for pages no longer in the pack.

    cache/ is deliberately NOT pruned. A dated cache entry is the immutable
    record of what a URL served on a given day, so a page dropped from this
    pack keeps its bytes for any later run or audit. Only the legacy flat
    snapshots/ folder and the derived normalized/ text are cleaned up.
    """
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


def export_xtra_courses() -> list[Path]:
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
        row = {
            "id": rec["record_id"],
            "catalogue_type": CATALOGUE[et],
            "source_url": rec["source"]["requested_url"],
            "institution": rec["source"]["institution_name"],
            "retrieved_at": rec["source"]["retrieved_at"],
            "transcription_method": _transcription_method(snap),
            "proof_html": snap,
            "pile": env_get("XTRA_PILE") or PACK.name,
            "expected": _expected(rec),
        }
        _assert_in_freeze(rec, row["expected"])
        dest = folder / f"{rec['record_id']}.json"
        dest.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(dest)
        keep[FOLDER[et]].add(dest.name)
        rows.append(
            {
                "id": row["id"],
                "catalogue_type": row["catalogue_type"],
                "institution": row["institution"],
                "source_url": row["source_url"],
                "pile": row["pile"],
                "proof_html": row["proof_html"],
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
