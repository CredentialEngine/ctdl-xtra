"""Scores (Evals spec §4) on a three-page catalog: xtra's scorer, called in-process, on the human-reviewed values and
on every rule-matched value; the extract output copied when first seen; a pair scored once; the human-reviewed values
read live from the page files; slot names flagged; the durable job, the pending score and the routes."""

from __future__ import annotations

import json
import time

import pytest
from test_golden_versions import CAT, JARED, B, _mark, _rows, studio  # noqa: F401  (studio: the fixture)

from golden_datasets import golden, layout, scores
from golden_datasets.cli import main
from golden_datasets.context import Ctx
from golden_datasets.storage import LocalRoot

NAMES = {"page-0": "C 0", "page-1": "C 11", "page-2": None}  # golden names: C 0, C 1, C 2 → match, partial, missing


def _output(folder, crawl: str, names=NAMES, slot_names: bool = False, written: int | None = None) -> None:
    """An extract output as xtra writes it: records/<stem>.json and extract-report.json."""
    (folder / "records").mkdir(parents=True, exist_ok=True)
    for stem, name in names.items():
        expected = {"ceterms:codedNotation": f"C {stem[-1]}", **({"ceterms:name": name} if name else {})}
        if slot_names:
            expected = {"course_" + k.split(":")[1]: v for k, v in expected.items()}
        (folder / "records" / f"{stem}.json").write_text(json.dumps({"record_id": stem, "expected": expected}))
    (folder / "extract-report.json").write_text(json.dumps({
        "run_id": crawl, "discovery_run_id": "d-1", "records_written": len(names) if written is None else written,
        "skipped": []}))


@pytest.fixture
def scored(studio, tmp_path, monkeypatch):  # noqa: F811
    """ruleset v1 published (Coded Notation, Name) with one human-reviewed value, and xtra's extract output."""
    c, ctx, gold = studio
    monkeypatch.setenv("GOLDEN_DATASETS_XTRA_SOURCE", str(tmp_path / "xtra-cli-output"))
    _mark(c, JARED, "course-name", _rows(c, "course-name")["page-0"], "correct")
    golden.publish(ctx, str(gold), "test", allow_unapproved=True, properties=["Coded Notation", "Learning Opportunity Name"])
    _output(tmp_path / "xtra-cli-output" / CAT / ctx.crawl, ctx.crawl)
    return c, Ctx(ctx.root, CAT), tmp_path


def test_a_score_has_both_results_and_one_row_per_value(scored, capsys):
    c, ctx, tmp = scored
    assert main(["score", "--root", ctx.root.uri, "--catalog", CAT, "--ruleset", "1"]) == 0
    out = capsys.readouterr().out
    assert "sc-0001" in out and "human-reviewed  100.0% exact of 1 values" in out
    assert "rule-matched    66.7% exact of 6 values · match 4 · partial 1 · wrong 0 · missing 1" in out
    doc = scores.read(ctx, "sc-0001")
    assert doc["status"] == "done" and doc["golden"]["id"] == "ruleset-v1" and doc["golden"]["values"] == {"human": 1, "rule": 6}
    assert doc["columns"] == ["codedNotation", "name"] and doc["slot_names"] is False
    assert doc["results"]["rule"]["by_column"]["name"] == {"values": 3, "missing": 1, "wrong": 0, "partial": 1, "match": 1}
    assert doc["output"]["records"] == 3 and not doc["output"]["records_mismatch"]
    assert all(c.startswith("xtra score extraction match --exactly") for c in doc["commands"])
    for cmd, tree in zip(doc["commands"], ("human-reviewed", "rule-matched"), strict=True):  # one per tree
        assert f"--baseline-uri {tmp / 'golden'}/catalogs/{CAT}/versions/ruleset-v1/{tree} " in cmd
    rows = {(r["basis"], r["page_stem"], r["column"]): r for r in scores.values(ctx, "sc-0001")}
    assert len(rows) == 7
    assert (rows[("rule", "page-1", "name")]["outcome"], rows[("rule", "page-1", "name")]["extracted_value"]) == ("partial", "C 11")
    assert rows[("human", "page-0", "name")]["approved_by"] == JARED
    # the output was copied, and xtra's folder has nothing new in it
    copy = layout.extract_output_dir(CAT, ctx.crawl, doc["output"]["id"])
    assert ctx.root.exists(f"{copy}/records/page-0.json") and ctx.root.exists(f"{copy}/extract-report.json")
    assert sorted(p.name for p in (tmp / "xtra-cli-output" / CAT / ctx.crawl).iterdir()) == ["crawl.json", "extract-report.json", "pages", "records"]
    # a pair is scored once
    assert scores.score(Ctx(ctx.root, CAT), "ruleset-v1")["id"] == "sc-0001"


def test_human_reviewed_values_are_read_live_from_the_page_files(scored):
    c, ctx, _ = scored
    first = scores.score(ctx, scores.HUMAN_REVIEWED)
    assert first["golden"]["values"]["human"] == 1
    _mark(c, JARED, "course-name", _rows(c, "course-name")["page-2"], "correct")  # rewrites page-2's file only
    second = scores.score(Ctx(ctx.root, CAT), scores.HUMAN_REVIEWED)
    assert second["id"] != first["id"] and second["golden"]["values"]["human"] == 2
    assert second["results"]["human"]["outcomes"] == {"missing": 1, "wrong": 0, "partial": 0, "match": 1}


def test_slot_names_and_a_record_count_that_disagrees_are_flagged(scored, capsys):
    _, ctx, tmp = scored
    _output(tmp / "old", ctx.crawl, slot_names=True, written=5)
    assert main(["score", "--root", ctx.root.uri, "--catalog", CAT, "--output", str(tmp / "old")]) == 0
    out = capsys.readouterr().out
    assert scores.SLOT_NAMES in out and "3 records in the folder, the report says 5" in out
    doc = scores.read(Ctx(ctx.root, CAT), "sc-0001")
    assert doc["slot_names"] and doc["results"]["rule"]["outcomes"]["match"] == 0


def test_store_adapters_map_the_scorers_keys():
    root = LocalRoot("/nonexistent")
    store = scores.RecordsStore(root, "a/b/extract-outputs/x", "cat", "crawl")
    assert store._path("cat/crawl/records/p.json") == "a/b/extract-outputs/x/records/p.json"
    assert store.list_keys("other/crawl/records") == []
    g = scores.GoldenStore({"p1": [{"fields": []}]}, "cat", "crawl", "here")
    assert g.list_keys("cat/crawl") == ["cat/crawl/p1/p1.json"] and g.get_json("cat/crawl/p1/p1.json")
    with pytest.raises(FileNotFoundError):
        g.get_json("cat/crawl/p2/p2.json")


def test_a_tree_keeps_the_scorers_positional_pairing():
    def f(v, approval="rule", term="ceterms:codedNotation"):
        return {"ctdl_property": term, "value": v, "approval": approval}

    pages = {"p1": [{"fields": [f("A", "human"), f("Course", term=None)]}],
             "p2": [{"fields": [f("B")]}, {"fields": [f("B2", "human")]}],
             "p3": [{"fields": [f("C", "human")]}, {"fields": [f("C2")]}],
             "p4": [{"fields": [f("Course", term=None)]}]}
    t = golden.trees(pages)
    rule = t[golden.RULE_MATCHED]
    assert [x["value"] for x in rule["p1"][0]["fields"]] == ["A"]  # no CTDL term: the scorer would reject the page
    assert rule["p1"][0]["approval"] == "human" and "p4" not in rule
    human, left = golden.tree_pages(rule, golden.HUMAN_REVIEWED)
    assert human == t[golden.HUMAN_REVIEWED] and len(human["p3"]) == 1 and human["p3"][0]["approval"] == "human"
    assert "p2" not in human and left[0]["stem"] == "p2"


def _wait(c, sid: str) -> dict:
    for _ in range(100):
        doc = c.get(f"{B}/scores/{sid}").json()
        if doc["status"] != "running":
            return doc
        time.sleep(0.05)
    raise AssertionError(f"{sid} still running")


def test_the_api_runs_a_score_as_a_durable_job(scored):
    c, ctx, tmp = scored
    outs = c.get(f"{B}/extract-outputs").json()  # first sight: copied, and scored against the latest golden dataset
    [o] = outs["outputs"]
    assert outs["latest_golden"] == "ruleset-v1" and o["records"] == 3
    sid = (o["scores"] or c.get(f"{B}/scores").json())[0]["id"]
    assert _wait(c, sid)["status"] == "done"
    r = c.post(f"{B}/scores", json={"golden": "ruleset-v1", "output": o["id"], "by": JARED})
    assert r.status_code == 200 and r.json()["id"] == sid  # scored once
    doc = c.post(f"{B}/scores", json={"golden": "human-reviewed", "output": o["id"], "by": JARED}).json()
    assert doc["status"] == "running" and doc["by"] == JARED
    assert _wait(c, doc["id"])["results"]["human"]["values"] == 1
    v = c.get(f"{B}/scores/{sid}/values", params={"basis": "rule", "column": "name"}).json()
    assert v["total"]["values"] == 6 and v["outcomes"]["values"] == 3
    assert [r["outcome"] for r in v["rows"]["items"]] == ["missing", "partial", "match"]
    assert [s["id"] for s in c.get(f"{B}/scores").json()] == [doc["id"], sid]
    assert c.get(f"{B}/scores/sc-0099").status_code == 404

    # a restart leaves a score running: it becomes interrupted
    fresh = Ctx(ctx.root, CAT)
    left = scores.begin(fresh, scores.prepare(fresh, "ruleset-v1", o["id"]), "x", "test")
    c.app.state.scores.recover(c.app.state.studio)
    assert scores.read(Ctx(ctx.root, CAT), left["id"])["status"] == "interrupted"


def test_the_pending_score_runs_when_due(scored):
    c, ctx, _ = scored
    jobs, st = c.app.state.scores, c.app.state.studio
    path = layout.pending_score(CAT, ctx.crawl)
    ctx.root.write_json(path, {"due_at": "2999-01-01T00:00:00Z", "reason": "later"})
    jobs.tick(st)  # sees the extract output and scores it against ruleset v1; the pending score isn't due
    while jobs.busy(CAT):
        time.sleep(0.05)
    assert ctx.root.exists(path) and [d["golden"]["id"] for d in scores.all_scores(Ctx(ctx.root, CAT))] == ["ruleset-v1"]
    ctx.root.write_json(path, {"due_at": "2000-01-01T00:00:00Z", "reason": "Jared marked course-name correct"})
    jobs.tick(st)
    while jobs.busy(CAT):
        time.sleep(0.05)
    assert not ctx.root.exists(path)
    latest = scores.all_scores(Ctx(ctx.root, CAT))[0]
    assert (latest["golden"]["id"], latest["reason"], latest["status"]) == ("human-reviewed", "Jared marked course-name correct", "done")
