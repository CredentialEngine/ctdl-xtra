"""The property list (property-rules spec §4.1): properties.csv from the Phase 1 sheet, and its readers."""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import pytest

from golden_datasets import model, properties
from golden_datasets.errors import UserError

SHEET = Path(__file__).parents[1] / "docs" / "qrspi" / "property-rules" / "phase1-extraction.csv"


def _rows():
    with open(SHEET, newline="") as fh:
        return list(csv.reader(fh))


def test_the_3_nov_sheet_gives_43_properties_with_the_sheets_paths():
    rows, warnings = properties.from_sheet(_rows(), None)
    assert len(rows) == 43
    by_path = {r["path"]: r for r in rows}
    # W2: stored as the sheet writes them; P15: row 33 is read under Co-Prerequisite, with a note
    assert "ceterms:prerequisite>ceterms:targetLearningOpportunity" in by_path
    r33 = next(r for r in rows if r["sheet_row"] == 33)
    assert r33["path"] == "ceterms:coPrerequisite>ceterms:alternativeCondition"
    assert r33["sheet_path"] == "ceterms:prerequisite>ceterms:alternativeCondition" and r33["path_note"]
    # W3: row 44 is skipped; P4 / P14 warn
    assert "ceterms:learningOpportunityType" not in by_path
    assert any("row 44" in w for w in warnings) and any("P15" in w for w in warnings)
    assert any("row 27: no Single / Multiple; read as Single" in w for w in warnings)
    assert by_path["ceterms:estimatedDuration>ceterms:exactDuration"]["multiple"]  # P14
    # P6: names are unique, built from the parent for the condition children
    assert by_path["ceterms:corequisite>ceterms:description"]["label"] == "Corequisite: Description"
    assert by_path["ceterms:hasPart"]["label"] == "Has Part"
    # today's eight keep their ids; required and the course key
    assert by_path["ceterms:description"]["rule_id"] == "course-description"
    assert by_path["ceterms:codedNotation"]["course_key"] and by_path["ceterms:codedNotation"]["required"]
    assert {r["label"] for r in rows if r["required"]} == {
        "Coded Notation", "External Identifier", "Learning Type", "Learning Opportunity Name", "Description",
        "Subject Webpage", "Life Cycle Status Type", "Language"}
    assert by_path["ceterms:creditValue>schema:minValue"]["parent"] == "ceterms:creditValue"


def test_the_checked_in_file_is_the_3_nov_sheet():
    rows, _ = properties.from_sheet(_rows(), None)
    assert [(r["rule_id"], r["path"]) for r in properties.load()] == [(r["rule_id"], r["path"]) for r in rows]


def test_model_properties_are_a_view_of_the_file_in_the_rules_tab_order():
    labels = [label for label, _ in model.PROPERTIES]
    assert labels[:8] == ["Coded Notation", "External Identifier", "Learning Type", "Learning Opportunity Name",
                          "Description", "Subject Webpage", "Life Cycle Status Type", "Language"]
    assert len(labels) == 43 and model.CTDL_TERM["Credit Unit Min Value"] == "ceterms:creditValue>schema:minValue"
    assert len(model.FIRST_EIGHT) == 8  # import_v2 and old publications stay frozen


def test_sync_keeps_ids_never_removes_and_renames_only_when_accepted():
    old, _ = properties.from_sheet(_rows(), None)
    rows = _rows()
    changed = [r[:] for r in rows if not r[5].startswith("ceterms:hasPart")]
    for r in changed:
        if r[5] == "ceterms:isNonCredit":
            r[3] = "Non-Credit"
    new, _ = properties.from_sheet(changed, None)
    merged, diff, warnings = properties.merge(old, new, accept_renames=False)
    assert diff["removed"] == ["course-has-part"]
    assert next(r for r in merged if r["rule_id"] == "course-has-part")["status"] == "removed"
    assert next(r for r in merged if r["rule_id"] == "course-is-non-credit")["label"] == "Is Non-Credit"
    assert any("--accept-renames" in w for w in warnings)
    merged, diff, _ = properties.merge(old, new, accept_renames=True)
    assert next(r for r in merged if r["rule_id"] == "course-is-non-credit")["label"] == "Non-Credit"


def test_a_duplicate_path_is_refused():
    rows = _rows()
    rows.append(rows[3][:])
    with pytest.raises(UserError, match="twice"):
        properties.from_sheet(rows, None)


def _xlsx(tabs: dict[str, list[list[str]]]) -> bytes:
    """A minimal xlsx with inline strings."""
    buf = io.BytesIO()
    z = zipfile.ZipFile(buf, "w")
    sheets, rels = [], []
    for i, (name, rows) in enumerate(tabs.items(), start=1):
        xml = []
        for n, row in enumerate(rows, start=1):
            cells = "".join(f'<c r="{chr(65 + j)}{n}" t="inlineStr"><is><t>{v}</t></is></c>'
                            for j, v in enumerate(row) if v)
            xml.append(f'<row r="{n}">{cells}</row>')
        z.writestr(f"xl/worksheets/sheet{i}.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/'
                   f'2006/main"><sheetData>{"".join(xml)}</sheetData></worksheet>')
        sheets.append(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>')
        rels.append(f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml"/>')
    z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
               'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
               f'<sheets>{"".join(sheets)}</sheets></workbook>')
    z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
               f'relationships">{"".join(rels)}</Relationships>')
    z.close()
    return buf.getvalue()


def test_the_course_tabs_required_block_is_read_from_the_workbook():
    course = [["Property Label", "Term"], ["Required Properties"], ["External Identifier", "ceterms:identifier"],
              ["Learning Type", "", "The type of learning opportunity"], ["Language", "ceterms:inLanguage"], ["Availability and Offering"],
              ["Offered By", "ceterms:offeredBy"]]
    tabs = properties.read_xlsx(_xlsx({"Course": course, "Phase 1 Extraction": _rows()[:5]}))
    assert tabs["Phase 1 Extraction"][1][5] == "ceterms:identifier"
    assert properties.required_from_course_tab(tabs["Course"]) == {"ceterms:identifier", "ceterms:inLanguage"}


def test_paths_are_shown_with_arrows_and_old_field_rules_read_as_property_rules():
    assert properties.shown("ceterms:creditValue>schema:minValue") == "ceterms:creditValue → schema:minValue"
    assert model.current_kind({"kind": "field", "rule_id": "x"})["kind"] == "property"  # P13
    assert model.current_kind({"kind": "locator"})["kind"] == "locator"
