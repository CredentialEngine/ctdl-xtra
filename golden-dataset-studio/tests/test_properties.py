"""The property list (property-rules spec §4.1): properties.csv from the Phase 1 sheet, and its readers."""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import pytest

from golden_datasets import model, properties
from golden_datasets.errors import UserError

DOCS = Path(__file__).parents[1] / "docs" / "qrspi" / "learning-programs"
#: The sheet's two tabs as exported on 2026-11-23 (the snapshots the files were synced from).
TABS = {"course": DOCS / "course-properties-2026-11-23.csv",
        "learningprogram": DOCS / "learning-program-properties-2026-11-23.csv"}


def _rows(cls: str = "course"):
    with open(TABS[cls], newline="") as fh:
        return list(csv.reader(fh))


def test_the_course_tab_gives_37_properties_in_three_tiers():
    rows, warnings = properties.from_sheet(_rows(), "course")
    assert len(rows) == 37  # 41 rows, less the five Estimated Duration children, plus Learning Type
    by_path = {r["path"]: r for r in rows}
    assert all(r["path"] == r["sheet_path"] and not r["path_note"] for r in rows)
    # Estimated Duration's children are fields of its objects, not properties of their own (sme-fixes §5.1)
    assert by_path["ceterms:estimatedDuration"]["multiple"]
    assert not [p for p in by_path if p.startswith("ceterms:estimatedDuration>")]
    assert any("ceterms:estimatedDuration>ceterms:timeRequired skipped" in w for w in warnings)
    # P6: names are unique, built from the parent for the condition children
    assert by_path["ceterms:corequisite>ceterms:description"]["label"] == "Corequisite: Description"
    # today's ids; the record key is the External Identifier (issue #368)
    assert by_path["ceterms:description"]["rule_id"] == "course-description"
    assert [r["path"] for r in rows if r["record_key"]] == ["ceterms:identifier"]
    # approved items 3–4: Required, then Phase 1 (Coded Notation moved here), then Phase 2, from xTRA Status
    tiers = {r["label"]: properties.tier(r) for r in rows}
    assert {lb for lb, t in tiers.items() if t == "required"} == {
        "External Identifier", "Learning Type", "Learning Opportunity Name", "Description", "Subject Webpage",
        "Life Cycle Status Type", "Language"}
    assert {lb for lb, t in tiers.items() if t == "phase1"} == {
        "Coded Notation", "In Catalog", "Is Non-Credit", "Credit Value", "Credit Unit Value", "Credit Unit Min Value",
        "Credit Unit Max Value", "Credit Unit Type"}
    assert tiers["Prerequisite"] == "phase2" and tiers["Estimated Duration"] == "phase2"
    value = by_path["ceterms:creditValue>schema:value"]
    assert (value["rule_id"], value["label"], value["parent"], value["sheet_row"]) == (
        "course-credit-value-value", "Credit Unit Value", "ceterms:creditValue", 18)


def test_sync_reproduces_the_learning_program_tab():
    """Phase 1 check: `properties sync --class learningprogram` reproduces the tab snapshot row by row."""
    rows, warnings = properties.from_sheet(_rows("learningprogram"), "learningprogram")
    tab = [r for r in _rows("learningprogram")[1:] if len(r) > 5 and (r[4].strip() or r[5].strip())]
    kept = [r for r in tab if not (r[5].strip() or r[4].strip()).startswith("ceterms:estimatedDuration>")]
    assert [(r["label"] if not r["parent"] else r["label"].split(": ")[-1], r["phase"], r["multiple"])
            for r in rows[1:]] == [
        (properties.LABELS.get(t[5], t[3].strip()), t[0], t[12] == "Multiple") for t in kept]
    by_path = {r["path"]: r for r in rows}
    # Available At has a question in its CLI Extraction Label: its path is the CTDL Shorthand URI
    assert by_path["ceterms:availableAt"]["rule_id"] == "learningprogram-available-at"
    assert any("read ceterms:availableAt" in w for w in warnings)
    # Required is Course's without Coded Notation (ask 9's working answer); External Identifier is the record key
    assert [r["label"] for r in rows if properties.tier(r) == "required"] == [
        "Learning Type", "External Identifier", "Name", "Description", "Subject Webpage", "Life Cycle Status Type",
        "Language"]
    assert "ceterms:codedNotation" not in by_path
    assert by_path["ceterms:identifier"]["record_key"] and by_path["ceterms:identifier"]["multiple"]
    assert rows[0]["rule_id"] == "learningprogram-learning-type" and rows[0]["sample"] == "LearningProgram"
    # rule ids carry the class, and mirror Course's ids for the same property
    assert by_path["ceterms:name"]["rule_id"] == "learningprogram-name"
    assert by_path["ceterms:identifier"]["rule_id"] == "learningprogram-external-id"
    assert by_path["ceterms:entryCondition>ceterms:description"]["label"] == "Entry Condition: Description"


@pytest.mark.parametrize("cls", ["course", "learningprogram"])
def test_the_checked_in_files_are_the_tabs(cls):
    rows, _ = properties.from_sheet(_rows(cls), cls)
    assert [(r["rule_id"], r["path"], r["phase"], r["required"]) for r in properties.active(cls)] == [
        (r["rule_id"], r["path"], r["phase"], r["required"]) for r in rows]


def test_the_sync_command_writes_the_class_file(tmp_path, monkeypatch, capsys):
    from golden_datasets.cli import main

    monkeypatch.setattr(properties, "FOLDER", tmp_path)
    assert main(["properties", "sync", "--class", "learningprogram", "--from", str(TABS["learningprogram"])]) == 0
    assert "properties/learningprogram.csv: 30 properties, added 30" in capsys.readouterr().out
    assert [r["rule_id"] for r in properties.active("learningprogram")] == [
        r["rule_id"] for r in properties.from_sheet(_rows("learningprogram"), "learningprogram")[0]]
    assert main(["properties", "list", "--class", "learningprogram"]) == 0
    out = capsys.readouterr().out
    assert "learningprogram-external-id" in out and "record key" in out and "Phase 2" in out
    with pytest.raises(SystemExit):  # --class is required, with no default
        main(["properties", "list"])


def test_model_properties_are_a_view_of_the_file_in_the_tier_order():
    labels = [label for label, _ in model.properties_of("course")]
    assert labels[:8] == ["External Identifier", "Learning Type", "Learning Opportunity Name", "Description",
                          "Subject Webpage", "Life Cycle Status Type", "Language", "Coded Notation"]
    assert len(labels) == 37 and model.ctdl_term("course")["Credit Unit Min Value"] == "ceterms:creditValue>schema:minValue"
    tiers = [properties.tier(r) for r in model.property_rows("course")]
    assert tiers == sorted(tiers, key=["required", "phase1", "phase2"].index)
    assert [label for label, _ in model.properties_of("learningprogram")][:3] == [
        "External Identifier", "Learning Type", "Name"]
    assert len(model.FIRST_EIGHT) == 8  # old publications stay frozen


def test_sync_keeps_ids_never_removes_and_renames_only_when_accepted():
    old, _ = properties.from_sheet(_rows(), "course")
    rows = _rows()
    changed = [r[:] for r in rows if not r[5].startswith("ceterms:inCatalog")]
    for r in changed:
        if r[5] == "ceterms:isNonCredit":
            r[3] = "Non-Credit"
    new, _ = properties.from_sheet(changed, "course")
    merged, diff, warnings = properties.merge(old, new, accept_renames=False)
    assert diff["removed"] == ["course-in-catalog"]
    assert next(r for r in merged if r["rule_id"] == "course-in-catalog")["status"] == "removed"
    assert next(r for r in merged if r["rule_id"] == "course-is-non-credit")["label"] == "Is Non-Credit"
    assert any("--accept-renames" in w for w in warnings)
    merged, diff, _ = properties.merge(old, new, accept_renames=True)
    assert next(r for r in merged if r["rule_id"] == "course-is-non-credit")["label"] == "Non-Credit"


def test_a_duplicate_path_is_refused():
    rows = _rows()
    rows.append(rows[3][:])
    with pytest.raises(UserError, match="twice"):
        properties.from_sheet(rows, "course")


def test_a_required_column_on_the_tab_is_read_when_there_is_one():
    rows = [r[:] + [""] for r in _rows("learningprogram")]
    rows[0][-1] = "Required"
    for r in rows[1:]:
        if r[5] in ("ceterms:identifier", "ceterms:name"):
            r[-1] = "Yes"
    out, warnings = properties.from_sheet(rows, "learningprogram")
    assert {r["path"] for r in out if r["required"]} == {"", "ceterms:identifier", "ceterms:name"}
    assert not any("no Required column" in w for w in warnings)


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


def test_the_class_tab_is_read_from_the_workbook(tmp_path):
    f = tmp_path / "sheet.xlsx"
    f.write_bytes(_xlsx({"Course Properties": _rows()[:5], "Learning Program Properties": _rows("learningprogram")[:4]}))
    assert properties.sheet_rows(str(f), "learningprogram")[1][5] == "ceterms:identifier"
    assert len(properties.sheet_rows(str(f), "course")) == 5
    with pytest.raises(UserError, match="no 'Course Properties' tab"):
        g = tmp_path / "other.xlsx"
        g.write_bytes(_xlsx({"Phase 1 Extraction": _rows()[:2]}))
        properties.sheet_rows(str(g), "course")


def test_paths_are_shown_with_arrows_and_old_field_rules_read_as_property_rules():
    assert properties.shown("ceterms:creditValue>schema:minValue") == "ceterms:creditValue → schema:minValue"
    assert model.current_kind({"kind": "field", "rule_id": "x"})["kind"] == "property"  # P13
    assert model.current_kind({"kind": "locator"})["kind"] == "locator"


def test_xlsx_cells_read_as_the_sheet_shows_them():
    assert properties._cell_text("1", "b", False) == "TRUE" and properties._cell_text("0", "b", False) == "FALSE"
    assert properties._cell_text("46266", None, True) == "2026-09-01"
    assert properties._cell_text("3.0", "n", False) == "3" and properties._cell_text("2.5", None, False) == "2.5"
