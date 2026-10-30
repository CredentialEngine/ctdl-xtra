"""Records exported as xTRA scoring files. Expected values must still be
slices of the freeze."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import dynamic_slots
import pytest
from export_xtra import (
    _assert_in_freeze,
    _drop_nested_html_copy,
    _drop_stale_xtra_json,
    _drop_unused_freezes,
    _expected,
    _proof_folder,
    _transcription_method,
    export_xtra_courses,
)
from lib_doubles import course_record, example_slot

URL = "https://catalog.example.edu/english/engl101"
STEM = "catalog-example-edu-english-engl101"


def record_of(
    entity_type: str, *fields: tuple[str, object], links=None
) -> dict:
    return {
        "record_id": "r",
        "entity_type": entity_type,
        "source_expected": {
            "fields": [
                {"canonical_label": label, "value": value}
                for label, value in fields
            ]
        },
        "links_expected": links or [],
    }


@pytest.mark.parametrize(
    ("rec", "expected"),
    [
        (
            record_of(
                "Course",
                ("course_id", "ENGL101"),
                ("course_name", "Composition I"),
                ("course_description", "Writing."),
                ("course_school", "Humanities"),
                ("relationship_heading", "not a course field"),
            ),
            {
                "course_id": "ENGL101",
                "course_name": "Composition I",
                "course_description": "Writing.",
                "course_school": "Humanities",
            },
        ),
        (
            record_of(
                "LearningProgram",
                ("learning_program_name", "Nursing AAS"),
                ("learning_program_id", "NUR.AAS"),
            ),
            {
                "learning_program_name": "Nursing AAS",
                "learning_program_id": "NUR.AAS",
            },
        ),
        (
            record_of(
                "Credential",
                ("credential_name", "AAS"),
                ("credential_description", "Two years."),
            ),
            {"credential_name": "AAS", "credential_description": "Two years."},
        ),
        (
            record_of("Competency", ("competency_text", "Write clearly.")),
            {"text": "Write clearly."},
        ),
        (
            record_of(
                "CompetencyFramework", ("competency_framework_name", "Outcomes")
            ),
            {"competency_framework": "Outcomes"},
        ),
        (
            record_of(
                "Link",
                links=[
                    {
                        "predicate": "ceterms:resultsInCredential",
                        "subject_ref": "a-learning-program",
                        "object_ref": "a-credential",
                    }
                ],
            ),
            {
                "predicate": "ceterms:resultsInCredential",
                "subject_id": "a-learning-program",
                "object_id": "a-credential",
            },
        ),
    ],
)
def test_expected_keeps_the_printed_fields_each_type_is_scored_on(
    rec: dict, expected: dict
) -> None:
    assert _expected(rec) == expected


def test_a_course_without_its_name_or_an_unknown_type_is_refused() -> None:
    with pytest.raises(KeyError):
        _expected(record_of("Course", ("course_id", "ENGL101")))
    with pytest.raises(ValueError, match="Program"):
        _expected(record_of("Program"))


@pytest.mark.parametrize(
    ("snapshot", "folder"),
    [
        ("cache/2026-10-21/x.html", "cache/"),
        ("cache\\2026-10-21\\x.html", "cache/"),
        ("snapshots/x.html", "snapshots/"),
        ("handoff/x.html", "handoff/"),
        ("x.html", "the freeze file"),
    ],
)
def test_the_method_note_names_the_folder_the_proof_is_in(
    snapshot: str, folder: str
) -> None:
    assert _proof_folder(snapshot) == folder
    method = _transcription_method(snapshot)
    assert f"frozen HTML bytes in {folder};" in method
    assert "no LLM extract" in method


def test_every_printed_string_must_be_in_the_freeze(pack: Path) -> None:
    (pack / "normalized").mkdir()
    (pack / "normalized" / "x.txt").write_text(
        "ENGL101:\nComposition I\n", encoding="utf-8"
    )
    rec = {
        "record_id": "r",
        "source": {"normalized_text_path": "normalized/x.txt"},
    }
    _assert_in_freeze(
        rec,
        {"course_id": "ENGL101", "course_credits": 3, "predicate": "unprinted"},
    )
    with pytest.raises(ValueError, match="r course_name not in freeze"):
        _assert_in_freeze(rec, {"course_name": "Composition II"})


def test_the_old_nested_html_copy_is_removed(pack: Path) -> None:
    (pack / "html" / "x.html").mkdir(parents=True)
    _drop_nested_html_copy()
    assert not (pack / "html").exists()


def test_stale_scoring_files_are_removed_from_the_listed_folders(
    pack: Path,
) -> None:
    for name in ("keep.json", "old.json"):
        (pack / "courses").mkdir(exist_ok=True)
        (pack / "courses" / name).write_text("{}", encoding="utf-8")
    _drop_stale_xtra_json({"courses": {"keep.json"}, "links": set()})
    assert sorted(p.name for p in (pack / "courses").iterdir()) == ["keep.json"]


def test_unused_derived_files_go_but_the_dated_cache_stays(pack: Path) -> None:
    keep = example_slot()
    dynamic_slots.write_slots([keep])
    files = {
        "snapshots": [f"{STEM}.html", f"{STEM}.meta.json", "gone.html"],
        "normalized": [f"{STEM}.txt", "gone.txt"],
        "cache/2026-10-21": ["gone.html"],
    }
    for folder, names in files.items():
        (pack / folder).mkdir(parents=True)
        for name in names:
            (pack / folder / name).write_text("x", encoding="utf-8")
    (pack / "snapshots" / "freeze_report.json").write_text(
        "{}", encoding="utf-8"
    )
    _drop_unused_freezes()
    assert sorted(p.name for p in (pack / "snapshots").iterdir()) == [
        f"{STEM}.html",
        f"{STEM}.meta.json",
        "freeze_report.json",
    ]
    assert [p.name for p in (pack / "normalized").iterdir()] == [f"{STEM}.txt"]
    assert (pack / "cache" / "2026-10-21" / "gone.html").is_file()


def test_export_writes_one_scoring_file_and_one_csv_row_per_record(
    pack: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XTRA_PILE", "nj30")
    rec = course_record(pack)
    dynamic_slots.write_slots([example_slot()])
    (pack / "courses").mkdir()
    (pack / "courses" / "stale.json").write_text("{}", encoding="utf-8")
    snapshot = rec["source"]["snapshot_path"]
    dest = pack / "courses" / "example-engl101-course.json"
    assert export_xtra_courses() == [dest]
    assert json.loads(dest.read_text(encoding="utf-8")) == {
        "id": "example-engl101-course",
        "catalogue_type": "COURSES",
        "source_url": URL,
        "institution": "Example College",
        "retrieved_at": rec["source"]["retrieved_at"],
        "transcription_method": _transcription_method(snapshot),
        "proof_html": snapshot,
        "pile": "nj30",
        "expected": {
            "course_id": "ENGL101",
            "course_name": "Composition I",
            "course_credits": 3,
        },
    }
    assert not (pack / "courses" / "stale.json").exists()
    with (pack / "records.csv").open(encoding="utf-8", newline="") as handle:
        assert list(csv.DictReader(handle)) == [
            {
                "id": "example-engl101-course",
                "catalogue_type": "COURSES",
                "institution": "Example College",
                "source_url": URL,
                "pile": "nj30",
                "proof_html": snapshot,
            }
        ]
    assert capsys.readouterr().out.startswith("xtra courses")


def test_the_pile_defaults_to_the_pack_folder_name(pack: Path) -> None:
    course_record(pack)
    dynamic_slots.write_slots([example_slot()])
    [dest] = export_xtra_courses()
    assert json.loads(dest.read_text(encoding="utf-8"))["pile"] == pack.name
