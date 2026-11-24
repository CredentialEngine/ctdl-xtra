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


def test_the_catalog_lists_its_classes_with_their_rules_and_records(lp):
    """The class menu (w4-class-menu): each class, its rules and records, Course first; a class with no rules says so."""
    c, _, _ = lp
    d = c.get(f"/api/catalogs/{programs.WVU}", params=LP).json()
    assert d["cls"] == "learningprogram"
    got = {x["slug"]: x for x in d["classes"]}
    assert list(got) == ["course", "learningprogram"]
    assert got["course"]["ruleset_version"] is None and got["course"]["rules_total"] == 0
    p = got["learningprogram"]
    assert (p["name"], p["noun"], p["ruleset_version"], p["records"], p["rules_approved"]) == (
        "LearningProgram", ["program", "programs"], 1, 2, 0)
    assert p["rules_total"] >= 5
    # Course has no rules here: its catalog answer is empty, not an error
    assert c.get(f"/api/catalogs/{programs.WVU}").json()["extraction"] is None


def test_the_record_key_says_where_it_came_from(lp):
    """The External Identifier card (w2-rules-id-card, w2-rules-id-generated): the code the page prints, quoted, or
    how a generated one was made; and the page rule with its URL pattern."""
    c, _, _ = lp
    rows = c.get(f"/api/catalogs/{programs.WVU}/rules/learningprogram-name/rows", params=LP).json()["rows"]
    occ = next(r["occurrence_key"] for r in rows if r["record_external_identifier"] == "2166")
    k = c.get(f"/api/catalogs/{programs.WVU}/key-source", params={**LP, "occ": occ}).json()
    assert (k["identifier"], k["rule_id"], k["generated"]) == ("2166", "learningprogram-external-id", False)
    assert k["from_code"] is False  # read by the External Identifier rule, not a Coded Notation one
    assert k["text"] == "In-Person Major Code: 2166"  # the smallest element that prints it, not the whole tab
    assert (k["page_rule"], k["url_pattern"]) == ("Program pages", "/(undergraduate|graduate)/")
    rows = c.get(f"/api/catalogs/{programs.AVC}/rules/learningprogram-name/rows", params=LP).json()["rows"]
    assert [r["key_generated"] for r in rows] == [True]
    k = c.get(f"/api/catalogs/{programs.AVC}/key-source", params={**LP, "occ": rows[0]["occurrence_key"]}).json()
    assert (k["identifier"], k["from_code"], k["generated"]) == ("program-accounting-a.a.", False, True)


def test_programs_are_listed_by_name(lp):
    """The Records list (w2-records-lp): a program's name over its identifier, sorted by name."""
    c, _, _ = lp
    hits = c.get(f"/api/catalogs/{programs.WVU}/courses", params=LP).json()
    assert [(h["name"], h["record_external_identifier"], h["pages"]) for h in hits] == [
        ("Accountancy, B.S.B.A.", "2166", 1), ("Mining Engineering, B.S.Min.E.", "5542", 1)]


def test_a_program_run_takes_its_place_in_the_shared_queue(lp):
    """Each catalog and class has its own runs and lock, and every run shares the queue's places: a LearningProgram run
    is in the queue, saying its class."""
    from test_agent_runs import FakeK2

    c, _, _ = lp
    st = c.app.state.studio
    st.k2 = st.queue.k2 = FakeK2()
    B = f"/api/catalogs/{programs.WVU}"
    rows = c.get(f"{B}/rules/learningprogram-name/rows", params=LP).json()["rows"]
    r = c.post(f"{B}/annotations", params=LP, json={
        "type": "verdict", "author": "Jared Diener", "verdict": "wrong",
        "target": {"kind": "match", "rule_id": "learningprogram-name", "occurrence_key": rows[0]["occurrence_key"]}})
    assert r.status_code == 200, r.text
    r = c.post(f"{B}/agent-runs", params=LP,
               json={"scope": {"kind": "rules", "rules": ["learningprogram-name"]}, "author": "Jared Diener"})
    assert r.status_code == 201, r.text
    assert r.json()["run"]["class"] == "learningprogram"
    q = c.get("/api/agent-runs/queue").json()
    [mine] = [x for x in q["working"] + q["waiting"] if x["run"] == r.json()["run"]["run_id"]]
    assert (mine["catalog"], mine["class"], mine["rules"]) == ("wvu", "learningprogram", ["learningprogram-name"])
    # the run is the class's: Course's run list doesn't have it
    assert c.get(f"{B}/agent-runs").json() == []
    assert [x["run_id"] for x in c.get(f"{B}/agent-runs", params=LP).json()] == [r.json()["run"]["run_id"]]
