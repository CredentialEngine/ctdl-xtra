"""The allowed source labels and the FIELD_INVENTORY.csv written from them."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from inventory import CSV_HEADER, INVENTORY, allowed_for, csv_text
from mapping import DIRECT

D5 = (
    "D5: csv_text() leaves the commas in '(Min, range start)' and "
    "'(Max, range end)' unquoted, so those rows have six columns"
)
D6 = (
    "D6: lib/FIELD_INVENTORY.csv is stale: it lacks course_ceu_credits, "
    "and it carries D5's unquoted commas"
)


def test_the_csv_has_a_header_and_one_line_per_label_in_order() -> None:
    lines = csv_text().splitlines(keepends=True)
    assert lines[0] == CSV_HEADER
    assert [line.split(",", 1)[0] for line in lines[1:]] == list(INVENTORY)


def test_notes_explain_the_credit_labels_and_never_invent_a_range() -> None:
    rows = {line.split(",", 1)[0]: line for line in csv_text().splitlines()}
    assert "Single printed credit is one value" in rows["course_credits"]
    assert "Do not treat CEUs as course_credits" in rows["course_ceu_credits"]
    assert "Never invent min/max" in rows["course_name"]


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=D5)
def test_every_csv_row_parses_into_the_five_header_columns() -> None:
    rows = list(csv.reader(io.StringIO(csv_text())))
    assert len(rows) == len(INVENTORY) + 1
    assert [len(row) for row in rows if len(row) != 5] == []


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=D6)
def test_the_checked_in_inventory_is_what_csv_text_writes(
    lib_dir: Path,
) -> None:
    checked_in = (lib_dir / "FIELD_INVENTORY.csv").read_text(encoding="utf-8")
    assert checked_in == csv_text()


def test_course_labels_are_allowed_only_on_courses() -> None:
    course = allowed_for("Course")
    assert len(course) == 20
    assert all(label.startswith("course_") for label in course)
    assert allowed_for("Link") == {"relationship_heading"}
    assert allowed_for("Competency") == {"competency_text"}
    assert allowed_for("Program") == set()


def test_every_label_mapping_knows_is_in_the_inventory() -> None:
    assert set(DIRECT) - set(INVENTORY) == set()


def test_each_entry_is_a_known_kind_and_a_namespaced_property() -> None:
    for label, (classes, kind, prop) in INVENTORY.items():
        assert classes, label
        assert kind in {"string", "number"}, label
        assert prop is None or prop.startswith(("ceterms:", "ceasn:")), label
