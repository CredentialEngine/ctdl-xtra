"""LearningProgram, outside in (LearningProgram plan, Phase 1): the real CLI and HTTP API on the program fixture
(`programs.py`: two WVU program pages, one AVC). Records are keyed by their External Identifier (issue #368): the
printed code, else `program-<normalized name>`; `--class learningprogram` reads the LearningProgram property list."""

from __future__ import annotations

import json

import programs
import pytest

from golden_datasets import golden, properties
from golden_datasets.cli import main
from golden_datasets.context import Ctx
from golden_datasets.storage import LocalRoot


@pytest.fixture
def lp(tmp_path, capsys, monkeypatch):
    from fastapi.testclient import TestClient

    from golden_datasets.server.app import create_app

    monkeypatch.setenv("GOLDEN_DATASETS_GOLDEN_ROOT", str(tmp_path / "golden"))
    root = programs.build(tmp_path)
    capsys.readouterr()
    return TestClient(create_app(str(root))), root, tmp_path


LP = {"class": "learningprogram"}  # the API's class (Course when a request names none)


def _ctx(root, catalog: str) -> Ctx:
    return Ctx(LocalRoot(root), catalog, cls="learningprogram")


def test_records_are_keyed_by_their_external_identifier(lp):
    c, root, _ = lp
    for catalog, ids in programs.EXPECTED_IDS.items():
        rows = c.get(f"/api/catalogs/{catalog}/rules/learningprogram-name/rows", params=LP).json()["rows"]
        assert sorted(r["record_external_identifier"] for r in rows) == ids
        records = c.get(f"/api/catalogs/{catalog}/courses", params=LP).json()
        assert sorted(x["record_external_identifier"] for x in records) == ids
    one = c.get(f"/api/catalogs/{programs.AVC}/courses/program-accounting-a.a.", params=LP).json()
    assert one["record_external_identifier"] == "program-accounting-a.a."
    names = {p["property_label"]: p["value"] for o in one["occurrences"] for p in o["properties"] if p.get("value")}
    assert names["Name"] == "Accounting, A.A." and names["External Identifier"] == "program-accounting-a.a."


def test_apply_and_check_use_the_learning_program_list(lp, capsys):
    _, root, _ = lp
    assert main(["properties", "apply", "--class", "learningprogram", "--root", str(root), "-c", programs.WVU]) == 0
    assert "adds 26 property rules with no rule yet" in capsys.readouterr().out
    rs, rules = _ctx(root, programs.WVU).ruleset_rules(2)
    assert rs["note"] == "added 26 property rules from the sheet's Learning Program Properties tab"
    assert {r["rule_id"] for r in properties.active("learningprogram")} <= set(rules)
    assert rules["learningprogram-available-at"]["definition"] == {
        "locator": "locator-learningprogram-page", "rule_type": "none"}
    assert not [rid for rid in rules if rid.startswith("course-")]
    assert main(["check", "--class", "learningprogram", "--root", str(root), "-c", programs.WVU]) == 0
    # Course has nothing in this catalog: its data is in learningprogram/ (approved item 20)
    assert Ctx(LocalRoot(root), programs.WVU, cls="course").ruleset_versions() == []
    assert (root / programs.WVU / "learningprogram" / "rulesets" / "v0002.json").exists()
    assert not (root / programs.WVU / "course").exists()


def test_the_api_names_its_class(lp):
    c, _, _ = lp
    assert c.get(f"/api/catalogs/{programs.WVU}/rules/learningprogram-name/rows").status_code == 404  # Course
    assert c.get(f"/api/catalogs/{programs.WVU}/rules", params={"class": "program"}).status_code == 422


def test_a_golden_publish_keys_records_by_external_identifier(lp):
    _, root, tmp = lp
    ctx = _ctx(root, programs.AVC)
    doc = golden.publish(ctx, str(tmp / "golden"), "test", allow_unapproved=True,
                         properties=["External Identifier", "Name", "Description"])
    assert doc["properties"] == ["External Identifier", "Name", "Description"]  # the class's tier order
    files = list((tmp / "golden").rglob("program-0.json"))
    assert files and all("/golden/learningprogram/" in str(f) for f in files)  # its own part of the golden root
    [rec] = json.loads(files[0].read_text())
    assert rec["golden_record_id"] == "program-accounting-a.a."
    assert [f["property"] for f in rec["fields"]] == ["External Identifier", "Name", "Description"]


def test_the_prompt_names_the_class(lp, capsys):
    _, root, _ = lp
    assert main(["prompt", "--class", "learningprogram", "--root", str(root), "-c", programs.WVU,
                 "--target", "local"]) == 0
    out = capsys.readouterr().out
    assert "GOLDEN_DATASETS_CLASS=learningprogram" in out
