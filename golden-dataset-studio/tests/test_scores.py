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


def test_evals_rows_map_to_their_studio_match_and_notes_keep_the_comparison(scored):
    """Evals step 4: each scored value carries its Studio match (through the lineage), so a note on it lands on the
    row the Rules tab shows, with what it was compared with; the list of golden datasets, outcomes per score, groups."""
    c, ctx, _ = scored
    o = c.get(f"{B}/extract-outputs").json()
    assert [(g["id"], g["kind"], g["latest"]) for g in o["goldens"]] == [("ruleset-v1", "version", True), ("rs-0001", "draft", False)]
    sid = (o["outputs"][0]["scores"] or c.get(f"{B}/scores").json())[0]["id"]
    _wait(c, sid)
    [brief] = c.get(f"{B}/extract-outputs").json()["outputs"][0]["scores"]
    assert brief["rule_outcomes"] == {"missing": 1, "wrong": 0, "partial": 1, "match": 4} and brief["golden_kind"] == "version"
    assert brief["human_outcomes"] == {"missing": 0, "wrong": 0, "partial": 0, "match": 1} and brief["golden_as_of"]

    v = c.get(f"{B}/scores/{sid}/values", params={"basis": "rule", "column": "name", "group": "subject"}).json()
    assert v["groups"] == [{"name": "C", "values": 3, "missing": 1, "wrong": 0, "partial": 1, "match": 1}]
    partial = next(r for r in v["rows"]["items"] if r["outcome"] == "partial")
    assert (partial["page_stem"], partial["rule_id"], partial["subject"]) == ("page-1", "course-name", "C")
    assert partial["occurrence_key"] == _rows(c, "course-name")["page-1"]["key"] and partial["value_index"] == 0
    assert c.get(f"{B}/scores/{sid}/values", params={"basis": "rule", "subject": "X"}).json()["rows"]["total"] == 0
    assert c.get(f"{B}/scores/{sid}/values", params={"group": "page"}).status_code == 422

    # a note on the diff: a comment on that match, with the comparison; /match returns the row with it
    cw = {"kind": "extract", "score": sid, "value": partial["extracted_value"]}
    r = c.post(f"{B}/annotations", json={"type": "comment", "author": JARED, "note": "xtra keeps the suffix",
                                         "compared_with": cw, "target": {"kind": "match", "rule_id": partial["rule_id"],
                                                                         "occurrence_key": partial["occurrence_key"]}})
    assert r.status_code == 200, r.text
    m = c.get(f"{B}/match", params={"rule": partial["rule_id"], "occ": partial["occurrence_key"]}).json()
    assert m["value"] == partial["golden_value"] and m["page_stem"] == "page-1"
    assert [(x["note"], x["compared_with"]) for x in m["comments"]] == [("xtra keeps the suffix", cw)]
    assert c.get(f"{B}/match", params={"rule": "course-name", "occ": "nowhere"}).status_code == 404

    # a draft's rows map through the lineage its extraction would publish
    d = c.post(f"{B}/scores", json={"golden": "rs-0001", "output": o["outputs"][0]["id"], "by": JARED}).json()
    _wait(c, d["id"])
    rows = c.get(f"{B}/scores/{d['id']}/values", params={"basis": "rule"}).json()["rows"]["items"]
    assert rows and all(r["rule_id"] and r["occurrence_key"] for r in rows)


def test_one_score_runs_per_catalog_at_a_time(scored):
    c, ctx, _ = scored
    jobs = c.app.state.scores
    jobs._busy[CAT] = "sc-0042"  # as while a score runs in its thread
    r = c.post(f"{B}/scores", json={"golden": "ruleset-v1", "by": JARED})
    assert (r.status_code, r.json()["detail"]) == (409, "sc-0042 is still running")
    assert jobs.after_publish(Ctx(ctx.root, CAT), JARED) is None  # approving still succeeds; its score is skipped
    jobs._busy.pop(CAT)
    assert c.post(f"{B}/scores", json={"golden": "nope", "by": JARED}).status_code == 400


def test_the_cli_scores_the_human_reviewed_values_and_a_draft(scored, capsys):
    _, ctx, _ = scored
    assert main(["score", "--root", ctx.root.uri, "--catalog", CAT, "--human-reviewed"]) == 0
    out = capsys.readouterr().out
    assert "vs human-reviewed [done]" in out and "human-reviewed  100.0% exact of 1 values" in out
    draft = Ctx(ctx.root, CAT).latest_extraction()
    assert main(["score", "--root", ctx.root.uri, "--catalog", CAT, "--draft", draft]) == 0
    doc = scores.all_scores(Ctx(ctx.root, CAT))[0]
    assert (doc["golden"]["id"], doc["golden"]["kind"], doc["commands"]) == (draft, "draft", [])  # a draft has no files


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


def test_the_catalogs_summary_has_each_columns_status_and_the_latest_score(scored):
    """Evals step 5: the home page's catalogs table, from small files only (score.json, publication.json, the log)."""
    c, ctx, tmp = scored
    s = c.get("/api/catalogs-summary").json()
    assert s["basis"] == "human" and s["columns"] == ["codedNotation", "identifier", "name", "description",
                                                      "subjectWebpage", "lifeCycleStatusType", "inLanguage"]
    assert s["not_in_studio"] == ["creditValue", "creditUnitType", "prerequisite"]
    cat = s["catalogs"][CAT]
    # each column's values in the golden dataset (human-reviewed + rule-labelled) of the values its rule found
    assert cat["columns"]["codedNotation"] == {"status": "published", "ruleset": 1, "human": 0, "rule": 3, "found": 3}
    assert cat["columns"]["name"] == {"status": "published", "ruleset": 1, "human": 1, "rule": 2, "found": 3}  # Jared checked one
    assert cat["score"] is None  # the extract output isn't scored yet
    statuses = {k: v["status"] for k, v in cat["columns"].items()}
    assert set(statuses) <= set(s["columns"]) and statuses.get("description", "in review") == "in review"

    assert main(["score", "--root", ctx.root.uri, "--catalog", CAT, "--ruleset", "1"]) == 0
    c.app.state.studio.ctx(CAT).invalidate()  # the server re-reads the manifest every few seconds
    human = c.get("/api/catalogs-summary", params={"basis": "human"}).json()["catalogs"][CAT]["score"]
    assert (human["id"], human["golden"], human["values"], human["outcomes"]["match"]) == ("sc-0001", "ruleset-v1", 1, 1)
    rule = c.get("/api/catalogs-summary", params={"basis": "rule"}).json()["catalogs"][CAT]["score"]
    assert rule["values"] == 6 and rule["by_column"]["name"] == {"values": 3, "missing": 1, "wrong": 0, "partial": 1, "match": 1}
    assert c.get("/api/catalogs-summary", params={"basis": "x"}).status_code == 422



def test_a_column_with_values_marked_wrong_has_known_wrong_values(studio):  # noqa: F811
    c, ctx, gold = studio
    assert c.get("/api/catalogs-summary").json()["catalogs"][CAT]["columns"]["codedNotation"]["status"] == "in review"
    _mark(c, JARED, "course-code", _rows(c, "course-code")["page-1"], "wrong")
    _mark(c, JARED, "course-code", _rows(c, "course-code")["page-2"], "correct")
    golden.publish(ctx, str(gold), "test", allow_unapproved=True, properties=["Learning Opportunity Name"])
    c.app.state.studio.ctx(CAT).invalidate()
    cols = c.get("/api/catalogs-summary").json()["catalogs"][CAT]["columns"]
    # an unpublished column has only its human-reviewed values in the golden dataset
    assert cols == {"codedNotation": {"status": "needs work", "ruleset": None, "human": 1, "rule": 0, "found": 3},
                    "name": {"status": "published", "ruleset": 1, "human": 0, "rule": 3, "found": 3}}


def test_check_resolves_each_scores_provenance_and_reports_a_score_left_running(scored):
    """Evals step 7: `check` follows a score to its golden dataset and kept extract output, and its values to pages."""
    from golden_datasets import check

    _, ctx, _ = scored
    doc = scores.score(ctx, "ruleset-v1")

    def failed(ctx: Ctx) -> list[str]:
        return sorted(r[2] for r in check.run(ctx) if r[3] and r[0] in ("score", "score values", "extract output",
                                                                         "pending score"))

    rows = [r for r in check.run(Ctx(ctx.root, CAT)) if r[0] in ("score", "score values", "extract output")]
    assert len(rows) == 7 and not failed(Ctx(ctx.root, CAT))
    path = f"{layout.score_dir(CAT, ctx.crawl, doc['id'])}/score.json"
    ctx.root.write_json(path, {**doc, "status": "running", "created_at": "2000-01-01T00:00:00Z",
                               "golden": {**doc["golden"], "id": "ruleset-v9"},
                               "output": {**doc["output"], "report_etag": "elsewhere"}})
    ctx.root.write_json(layout.pending_score(CAT, ctx.crawl), {"due_at": "soon"})
    assert failed(Ctx(ctx.root, CAT)) == [
        "golden → a version, human-reviewed as of a time, or a draft extraction",
        f"none left running (> {check.STALE_RUNNING // 60} min; a server start marks it interrupted)",
        "output → a kept extract output (same report ETag)",
        "scores/pending.json is {due_at: ISO time, reason}",
    ]
