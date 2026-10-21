"""Freeze-backed checks on a course pack and on its xTRA scoring files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from lib_doubles import course_record
from quality import (
    check_xtra_course_exports,
    cross_check_pack,
    re_has_glued_credit,
)

RANGE_TEXT = "ENGL101:\nComposition I\nCredits\n3\nMin\n1\nMax\n4\n"


def labelled(*rows: tuple[str, object, str]) -> list[tuple[str, object, str]]:
    return [
        ("course_id", "ENGL101", "ENGL101:"),
        ("course_name", "Composition I", "Composition I"),
        *rows,
    ]


def test_a_built_course_pack_passes(pack: Path) -> None:
    course_record(pack)
    assert cross_check_pack(pack) == []


def test_only_courses_belong_in_a_college_pack(pack: Path) -> None:
    course_record(pack, entity_type="Credential")
    assert cross_check_pack(pack) == [
        "example-engl101-course: generic college pack only accepts Course"
    ]


def test_a_builder_never_signs(pack: Path) -> None:
    rec = course_record(pack, write=False)
    rec["verification"]["status"] = "human_signed"
    (pack / "records").mkdir(exist_ok=True)
    (pack / "records" / "x.json").write_text(json.dumps(rec), encoding="utf-8")
    assert "example-engl101-course: builder must not emit human_signed" in (
        cross_check_pack(pack)
    )


def test_a_course_needs_both_its_code_and_its_name(pack: Path) -> None:
    course_record(pack, fields=[("course_id", "ENGL101", "ENGL101:")])
    assert cross_check_pack(pack) == [
        "example-engl101-course: missing course_id or course_name"
    ]


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (
            [
                ("course_credits", 3, "Credits\n3"),
                ("course_credits_min", 1, "Min\n1"),
            ],
            "single course_credits cannot also have min/max",
        ),
        ([("course_credits_min", 1, "Min\n1")], "min without printed max"),
        ([("course_credits_max", 4, "Max\n4")], "max without printed min"),
    ],
)
def test_credits_are_one_value_or_a_printed_range(
    pack: Path, extra: list, message: str
) -> None:
    course_record(pack, fields=labelled(*extra), text=RANGE_TEXT)
    assert f"example-engl101-course: {message}" in cross_check_pack(pack)


def test_a_name_that_is_the_code_or_has_credits_glued_on_is_flagged(
    pack: Path,
) -> None:
    text = "ENGL101\nComposition I3 Credit(s)\n"
    course_record(
        pack,
        fields=[
            ("course_id", "ENGL101", "ENGL101"),
            ("course_name", "ENGL101", "ENGL101"),
        ],
        text=text,
    )
    assert cross_check_pack(pack) == [
        "example-engl101-course: course_name is the code; split the heading"
    ]
    course_record(
        pack,
        fields=[
            ("course_id", "ENGL101", "ENGL101"),
            (
                "course_name",
                "Composition I3 Credit(s)",
                "Composition I3 Credit(s)",
            ),
        ],
        text=text,
    )
    assert cross_check_pack(pack) == [
        "example-engl101-course: course_name still contains glued credits"
    ]


def test_every_value_and_excerpt_must_be_in_the_freeze(pack: Path) -> None:
    rec = course_record(pack, write=False)
    rec["source_expected"]["fields"][1]["value"] = "Composition II"
    rec["source_expected"]["fields"][0]["evidence"][0]["excerpt"] = "ENG 101:"
    (pack / "records").mkdir(exist_ok=True)
    (pack / "records" / "x.json").write_text(json.dumps(rec), encoding="utf-8")
    assert cross_check_pack(pack) == [
        "example-engl101-course src_001: excerpt not in freeze",
        "example-engl101-course course_name: value not in freeze",
    ]


def test_a_missing_normalized_text_fails_every_value(pack: Path) -> None:
    course_record(pack)
    for path in (pack / "normalized").iterdir():
        path.unlink()
    errors = cross_check_pack(pack)
    assert "example-engl101-course course_id: value not in freeze" in errors
    assert "example-engl101-course course_name: value not in freeze" in errors


def write_export(pack: Path, **row: object) -> None:
    folder = pack / "courses"
    folder.mkdir(exist_ok=True)
    proof = pack / "cache" / "2026-10-21" / "x.html"
    proof.parent.mkdir(parents=True, exist_ok=True)
    proof.write_text("<p>x</p>", encoding="utf-8")
    body = {"id": "x", "proof_html": "cache/2026-10-21/x.html", "expected": {}}
    body.update(row)
    (folder / "x.json").write_text(json.dumps(body), encoding="utf-8")


def test_a_clean_export_passes(pack: Path) -> None:
    write_export(pack)
    assert check_xtra_course_exports(pack) == []


def test_no_courses_folder_means_nothing_to_check(pack: Path) -> None:
    assert check_xtra_course_exports(pack) == []


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (
            {"catalog_edition": None},
            "omit catalog_edition instead of storing null",
        ),
        (
            {"proof_snapshot": "x"},
            "omit proof_snapshot; proof_html is the freeze",
        ),
        ({"proof_html": ""}, "missing proof_html"),
        ({"proof_html": "/abs/x.html"}, "proof_html must be pack-relative"),
        ({"proof_html": "~/x.html"}, "proof_html must be pack-relative"),
        ({"proof_html": "C:/packs/x.html"}, "proof_html must be pack-relative"),
        (
            {"proof_html": "C:\\packs\\x.html"},
            "proof_html must be pack-relative",
        ),
        ({"proof_html": "html/x.html"}, "doubled proof path html/x.html"),
        ({"proof_html": "cache/x.html/x.html"}, "doubled proof path"),
        ({"proof_html": "cache/2026-10-21/gone.html"}, "is not a file"),
        (
            {"expected": {"course_prerequisites": " and Corequisite: ENG 102"}},
            "course_prerequisites starts mid-label",
        ),
    ],
)
def test_each_export_wrapper_rule_is_reported(
    pack: Path, row: dict, message: str
) -> None:
    write_export(pack, **row)
    errors = check_xtra_course_exports(pack)
    assert [e for e in errors if message in e] != [], errors


def test_export_errors_reach_the_pack_check(pack: Path) -> None:
    course_record(pack)
    write_export(pack, catalog_edition=None)
    assert "x: omit catalog_edition instead of storing null" in (
        cross_check_pack(pack)
    )


@pytest.mark.parametrize(
    ("name", "glued"),
    [
        ("Composition I3 Credit(s)", True),
        ("Topics 3 Credits", True),
        ("Composition I", False),
        ("Credit for prior learning", False),
    ],
)
def test_glued_credit_detection(name: str, glued: bool) -> None:
    assert re_has_glued_credit(name) is glued
