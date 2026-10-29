"""Approving publishes (Evals spec §4.1, §6.6) on a three-page catalog: approving a column's rule publishes it into
its ruleset's golden dataset (the first approval creates the version, later ones rewrite it with the extra column),
then scores xtra's latest extract output against it; other rules approve as before; a column with no CTDL term is
approved but not written. The Golden datasets API is a read-only record of the versions and their files."""

from __future__ import annotations

import json

from test_golden_versions import CAT, JARED, RULES, B, _mark, _page, _rows, studio  # noqa: F401  (studio: the fixture)
from test_scores import _output, _wait

from golden_datasets import golden
from golden_datasets.cli import main
from golden_datasets.context import Ctx


def _approve(c, rule: str) -> dict:
    r = c.post(f"{B}/annotations", json={"type": "approve", "author": JARED, "target": {"kind": "rule", "rule_id": rule}})
    assert r.status_code == 200, r.text
    return r.json()


def test_approving_a_column_publishes_it_then_scores_it(studio, tmp_path, monkeypatch):  # noqa: F811
    c, ctx, gold = studio
    monkeypatch.setenv("GOLDEN_DATASETS_XTRA_SOURCE", str(tmp_path / "xtra-cli-output"))
    _output(tmp_path / "xtra-cli-output" / CAT / ctx.crawl, ctx.crawl)
    _mark(c, JARED, "course-name", _rows(c, "course-name")["page-0"], "correct")  # creates ruleset v1 (no columns)

    pre = c.get(f"{B}/golden/approve/course-code").json()
    assert (pre["publishes"], pre["golden"], pre["creates"], pre["column"]) == (True, "ruleset-v1", False, "codedNotation")
    assert (pre["now"], pre["after"]) == ([], ["codedNotation"])
    assert (pre["values"], pre["human"], pre["rule"]) == (3, 0, 3)
    assert pre["where"].endswith(f"/catalogs/{CAT}/versions/ruleset-v1/")
    assert c.get(f"{B}/golden/approve/course-page").json() == {"publishes": False, "rule_id": "course-page"}
    assert c.get(f"{B}/golden/approve/nope").status_code == 404

    out = _approve(c, "course-code")
    assert out["rule"]["status"] == "approved"
    assert out["published"] | {"files": 0} == {"written": True, "publication": "ruleset-v1", "created": False,
                                               "column": "codedNotation", "columns": ["codedNotation"], "files": 0}
    assert out["score"]["golden"] == "ruleset-v1" and _wait(c, out["score"]["id"])["status"] == "done"
    [rec] = _page(gold, ctx, "page-0", 1)
    assert [f["property"] for f in rec["fields"]] == ["Coded Notation", "Learning Opportunity Name"]
    [hr] = _page(gold, ctx, "page-0", 1, golden.HUMAN_REVIEWED)
    assert [f["property"] for f in hr["fields"]] == ["Learning Opportunity Name"]

    # the next column rewrites the same version with the extra column, and is scored again
    pre = c.get(f"{B}/golden/approve/course-name").json()
    assert (pre["now"], pre["after"], pre["values"], pre["human"]) == (["codedNotation"], ["codedNotation", "name"], 3, 1)
    out = _approve(c, "course-name")
    assert out["published"]["columns"] == ["codedNotation", "name"] and out["published"]["publication"] == "ruleset-v1"
    done = _wait(c, out["score"]["id"])
    assert done["columns"] == ["codedNotation", "name"] and done["results"]["rule"]["values"] == 6

    # a rule that isn't a column's approves as before
    out = _approve(c, "locator-course-page")
    assert (out["published"], out["score"]) == (None, None)

    # the Golden datasets tab's record
    g = c.get(f"{B}/golden").json()
    [v] = g["versions"]
    assert (v["id"], v["latest"], v["columns"], v["values"], v["human"]) == ("ruleset-v1", True, ["codedNotation", "name"], 6, 1)
    assert v["score"] | {"id": "", "finished_at": "", "output": ""} == {
        "id": "", "status": "done", "basis": "human", "rate": 1.0, "values": 1, "match": 1, "finished_at": "", "output": ""}
    assert v["where"]["version"] == f"catalogs/{CAT}/versions/ruleset-v1/" and v["where"]["latest"] == golden.latest_prefix(ctx)
    assert v["where"]["trees"][golden.HUMAN_REVIEWED]["pages"] == 1 and v["where"]["root"] == str(gold)


def test_a_column_with_no_ctdl_term_is_approved_but_not_written(studio, tmp_path, capsys):  # noqa: F811
    c, ctx, gold = studio
    rules = json.loads(json.dumps(RULES))
    rules["rules"].append({"rule_id": "course-learning-type", "kind": "field", "property_label": "Learning Type",
                           "ctdl_property": None, "definition": {"locator": "locator-course-page", "rule_type": "constant",
                                                                 "value": "Course"}})
    draft = tmp_path / "v2.json"
    draft.write_text(json.dumps(rules))
    assert main(["rule", "publish", "--root", ctx.root.uri, "--catalog", CAT, str(draft), "--note", "v2", "--force"]) == 0
    capsys.readouterr()
    pre = c.get(f"{B}/golden/approve/course-learning-type").json()
    assert (pre["publishes"], pre["property"], pre["column"]) == (False, "Learning Type", None)
    out = _approve(c, "course-learning-type")
    assert out["rule"]["status"] == "approved"
    assert out["published"] == {"written": False, "column": None, "property": "Learning Type"} and out["score"] is None
    assert not Ctx(ctx.root, CAT).crawl_entry().get("golden")


def test_the_golden_datasets_files_are_samples_of_what_a_version_wrote(studio):  # noqa: F811
    c, ctx, gold = studio
    _mark(c, JARED, "course-name", _rows(c, "course-name")["page-0"], "correct")
    _approve(c, "course-code")
    v = f"{B}/golden/ruleset-v1"
    assert c.get(f"{v}/stems").json() == ["page-0", "page-1", "page-2"]
    assert c.get(f"{v}/stems", params={"tree": golden.HUMAN_REVIEWED}).json() == ["page-0"]
    assert c.get(f"{v}/stems", params={"tree": "x"}).status_code == 422
    page = c.get(f"{v}/files/page/page-1.json").json()
    assert page["records"] == 1 and json.loads(page["text"])[0]["fields"][0]["value"] == "C 1"
    latest = c.get(f"{v}/files/page/page-1.json", params={"tree": "latest"}).json()
    assert latest["text"] == page["text"] and latest["path"].endswith(f"{golden.latest_prefix(ctx)}page-1/page-1.json")
    assert c.get(f"{v}/files/page/page-1.json", params={"tree": golden.HUMAN_REVIEWED}).status_code == 404
    assert "<h1>" in c.get(f"{v}/files/page/page-1.html").json()["text"]
    pub = json.loads(c.get(f"{v}/files/publication.json").json()["text"])
    assert pub["publication"] == "ruleset-v1" and pub["properties"] == ["Coded Notation"]
    lin = c.get(f"{v}/files/lineage.parquet", params={"limit": 2}).json()
    assert lin["total"] == 4 and len(lin["rows"]) == 2 and lin["columns"][0] == "publication"
    gp = c.get(f"{v}/files/golden.parquet", params={"q": "page-2"}).json()
    assert gp["matched"] == 1 and "ctdl_property" in gp["columns"]
    assert c.get(f"{v}/files/other.parquet").status_code == 404
    assert c.get(f"{B}/golden/ruleset-v9/stems").status_code == 404
    assert c.post(f"{B}/golden/publish", json={"author": JARED, "properties": ["Coded Notation"]}).status_code in (404, 405)
