"""The per-verdict work stays small on big catalogs: a verdict rewrites one page's golden file from that page alone,
the "Annotated by" counts are reused until a rule's own annotations change, and a score can run in a process of its
own."""

from __future__ import annotations

import json

from test_golden_versions import CAT, ERIC, JARED, RULES, B, _mark, _rows, studio  # noqa: F401  (studio: the fixture)
from test_scores import _wait, scored  # noqa: F401  (scored: the fixture)

from golden_datasets import golden
from golden_datasets.cli import main
from golden_datasets.context import Ctx
from golden_datasets.review import LOADER, PEOPLE_CACHE, Review


def test_a_pages_plan_is_that_page_of_the_whole_plan(studio):  # noqa: F811
    c, ctx, _ = studio
    rows = _rows(c, "course-name")
    _mark(c, ERIC, "course-name", rows["page-0"], "correct")
    _mark(c, JARED, "course-name", rows["page-1"], "correct")
    c.post(f"{B}/annotations", json={"type": "verdict", "author": JARED, "verdict": "wrong",
                                     "expected": {"text": "Another name"},
                                     "target": {"kind": "match", "rule_id": "course-name",
                                                "occurrence_key": rows["page-2"]["key"]}})
    rv = LOADER.review(Ctx(ctx.root, CAT))
    for props in (None, {"Coded Notation", "Learning Opportunity Name"}):
        whole = golden.plan(rv, props)
        assert whole["pages"]
        for stem, records in whole["pages"].items():
            assert golden.plan(rv, props, stems={stem})["pages"] == {stem: records}
    for rid in rv.snap.rules:  # a page's rows, and their states (history too), are those of the whole rule
        whole = rv.row_states(rid, rv.snap.rows(rid))
        for stem in {r["page_stem"] for r in rv.snap.rows(rid)}:
            rows = rv.snap.rows_on(rid, {stem})
            assert rows == [r for r in rv.snap.rows(rid) if r["page_stem"] == stem]
            rv.snap._rows.clear()  # built for the page alone this time
            assert rv.snap.rows_on(rid, {stem}) == rows
            assert {k: vars(st) for k, st in rv.row_states(rid, rows, {stem}).items()} == {
                r["key"]: vars(whole[r["key"]]) for r in rows}


def test_annotated_by_counts_are_reused_until_a_rule_changes(studio, monkeypatch):  # noqa: F811
    c, _, _ = studio
    rows = _rows(c, "course-name")
    _mark(c, JARED, "course-name", rows["page-0"], "correct")
    calls: list[str] = []
    real = Review.annotations

    def counting(self, rule_id):
        calls.append(rule_id)
        return real(self, rule_id)
    monkeypatch.setattr(Review, "annotations", counting)
    PEOPLE_CACHE.clear()
    first = c.get(f"{B}/annotators", params={"verdict": "correct"}).json()
    assert first["rules"]["course-name"] == 1 and calls
    calls.clear()
    assert c.get(f"{B}/annotators", params={"verdict": "correct"}).json() == first
    assert calls == []  # the same log: nothing is worked out again
    _mark(c, JARED, "course-name", rows["page-1"], "correct")
    after = c.get(f"{B}/annotators", params={"verdict": "correct"}).json()
    assert after["rules"]["course-name"] == 2 and set(calls) == {"course-name"}  # only the rule that changed
    assert next(p for p in after["people"] if p["name"] == JARED)["values"] == 2


def test_a_score_can_run_in_its_own_process(scored, monkeypatch):  # noqa: F811
    c, _, _ = scored
    monkeypatch.setenv("GOLDEN_DATASETS_SCORE_PROCESS", "1")
    d = c.post(f"{B}/scores", json={"golden": "ruleset-v1", "by": JARED}).json()
    doc = _wait_long(c, d["id"])
    assert doc["status"] == "done", doc.get("error")
    assert doc["golden"]["values"] == {"human": 1, "rule": 6}


def _wait_long(c, sid: str) -> dict:
    import time

    for _ in range(600):  # a spawned process imports the package first
        doc = c.get(f"{B}/scores/{sid}").json()
        if doc["status"] != "running":
            return doc
        time.sleep(0.1)
    raise AssertionError(f"{sid} still running")


def test_a_course_is_read_from_its_own_pages_with_the_whole_rules_states(studio):  # noqa: F811
    """Opening a record builds each rule's rows on that course's pages only (WVU: ~22k rows per rule, ~40 rules, took
    ~13 s per record), and shows what the whole rule's rows say: state, verdict, comments, annotators."""
    c, ctx, _ = studio
    rows = _rows(c, "course-name")
    _mark(c, ERIC, "course-name", rows["page-0"], "correct")
    _mark(c, JARED, "course-name", rows["page-1"], "wrong")
    _mark(c, JARED, "course-code", _rows(c, "course-code")["page-1"], "correct")
    c.post(f"{B}/annotations", json={"type": "comment", "author": ERIC, "text": "check this",
                                     "target": {"kind": "match", "rule_id": "course-code",
                                                "occurrence_key": rows["page-2"]["key"]}})
    courses = [x["course_key"] for x in c.get(f"{B}/courses").json()]
    assert len(courses) == 3
    rv = LOADER.review(Ctx(ctx.root, CAT))
    for ck in courses:
        rv.snap._rows.clear()
        rv._states.clear()
        rv._annotations.clear()
        got = c.get(f"{B}/courses/{ck}").json()
        assert LOADER.review(Ctx(ctx.root, CAT)) is rv  # the same Review served the request
        assert not rv.snap._rows and not rv._states and not rv._annotations  # no rule's whole rows were built
        for occ in got["occurrences"]:
            for p in occ["properties"]:
                rid, key = p["rule_id"], occ["occurrence_key"]
                whole = rv.row_states(rid, rv.snap.rows(rid)).get(key)
                assert p["state"] == (whole.state if whole else None)
                assert (p["verdict"] or {}).get("annotation_id") == ((whole.verdict or {}).get("annotation_id")
                                                                     if whole else None)
                assert (p["human_reviewed"], p["engineer_checked"]) == (
                    (whole.human is not None, whole.engineer_checked) if whole else (False, False))
                assert [x["annotation_id"] for x in p["comments"]] == (
                    [x["annotation_id"] for x in whole.comments] if whole else [])
                assert p["annotators"] == (rv.annotations(rid).get(key) or {"people": {}})["people"]
    marked = [p for ck in courses for o in c.get(f"{B}/courses/{ck}").json()["occurrences"] for p in o["properties"]
              if p["state"] or p["comments"]]
    assert {(p["rule_id"], p["state"], len(p["comments"])) for p in marked} == {
        ("course-name", "correct", 0), ("course-name", "wrong", 0), ("course-code", "correct", 0),
        ("course-code", None, 1)}


def test_a_rows_state_alone_is_its_state_in_the_whole_rule(studio, tmp_path, capsys):  # noqa: F811
    """`row_states(..., stems, only=keys)`: the states of those rows alone, each as the whole rule's rows have it, with
    the parent's rows built for those keys alone (`rows_on(..., keys)`)."""
    c, ctx, _ = studio
    rows = _rows(c, "course-name")
    _mark(c, ERIC, "course-name", rows["page-0"], "correct")
    _mark(c, JARED, "course-code", _rows(c, "course-code")["page-1"], "wrong")
    draft = json.loads(json.dumps(RULES))
    draft["rules"][3]["definition"]["selector"] = "h1, h2"  # a second ruleset: its extraction has the first as parent
    (tmp_path / "second.json").write_text(json.dumps(draft))
    assert main(["rule", "publish", "--root", str(ctx.root.base), "--catalog", CAT, str(tmp_path / "second.json"),
                 "--note", "second"]) == 0
    capsys.readouterr()
    rv = LOADER.review(Ctx(ctx.root, CAT))
    assert rv.parent is not None
    for rid in rv.snap.rules:
        whole = rv.row_states(rid, rv.snap.rows(rid))
        for stem in {r["page_stem"] for r in rv.snap.rows(rid)}:
            on_page = rv.snap.rows_on(rid, {stem})
            for r in on_page:
                rv.snap._rows.clear()
                rv.parent._rows.clear()
                assert rv.snap.rows_on(rid, {stem}, {r["key"]}) == [r]
                one = rv.row_states(rid, on_page, {stem}, only={r["key"]})
                assert list(one) == [r["key"]] and vars(one[r["key"]]) == vars(whole[r["key"]])
