"""The per-verdict work stays small on big catalogs: a verdict rewrites one page's golden file from that page alone,
the "Annotated by" counts are reused until a rule's own annotations change, and a score can run in a process of its
own."""

from __future__ import annotations

from test_golden_versions import CAT, ERIC, JARED, B, _mark, _rows, studio  # noqa: F401  (studio: the fixture)
from test_scores import _wait, scored  # noqa: F401  (scored: the fixture)

from golden_datasets import golden
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


def test_a_plan_reads_the_property_order_once_not_per_course(studio, monkeypatch):  # noqa: F811
    """The property order checks the class's properties file each call; called in the plan's per-course sort, it was
    a file check per course (~650k on the biggest catalog) whenever the home page worked out a catalog's counts."""
    from golden_datasets import model

    _, ctx, _ = studio
    rv = LOADER.review(Ctx(ctx.root, CAT))
    calls: list[str] = []
    real = model.property_rows

    def counting(cls="course"):
        calls.append(cls)
        return real(cls)
    monkeypatch.setattr(model, "property_rows", counting)
    assert golden.plan(rv)["courses"] > 1
    assert len(calls) == 1


def test_the_server_works_out_the_home_page_when_it_starts(studio, monkeypatch):  # noqa: F811
    """Cold, the home page's table loads every catalog's extraction and plans its golden dataset (over a minute on
    the biggest catalogs): the server does it once when it starts, so the first visit only reads the cache."""
    c, _, _ = studio
    st = c.app.state.studio
    st.cache.clear()
    warm = st.warm_home()
    warm.join(timeout=60)
    assert not warm.is_alive()
    planned: list[str] = []
    real = golden.plan

    def counting(rv, *a, **k):
        planned.append(rv.snap.ctx.catalog)
        return real(rv, *a, **k)
    monkeypatch.setattr(golden, "plan", counting)
    course = c.get("/api/catalogs-summary").json()
    lp = c.get("/api/catalogs-summary", params={"class": "learningprogram"}).json()
    assert CAT in course["catalogs"] and course["catalogs"][CAT]["columns"] and lp["cls"] == "learningprogram"
    assert planned == []  # warm: nothing is worked out again
    st.cache.clear()
    c.get("/api/catalogs-summary")
    assert planned == [CAT]  # (cold, a visit works it out)


def test_each_classs_home_page_counts_are_kept_apart(studio, tmp_path, capsys, monkeypatch):  # noqa: F811
    """The home page asks for every class's table at once. A catalog's LearningProgram counts used to replace its
    Course counts in the cache (the key had no class), so every visit worked out the biggest catalog's Course counts
    again (over a minute on WVU)."""
    import json

    import programs
    from golden_datasets.cli import main

    c, ctx, _ = studio
    draft = tmp_path / "lp.json"
    draft.write_text(json.dumps({**programs._rules(programs.AVC), "catalog": CAT}))
    assert main(["rule", "publish", "--class", "learningprogram", "--root", str(ctx.root.base), "--catalog", CAT,
                 str(draft), "--note", "first LearningProgram rules"]) == 0
    capsys.readouterr()
    planned: list[tuple[str, str]] = []
    real = golden.plan

    def counting(rv, *a, **k):
        planned.append((rv.snap.ctx.catalog, rv.snap.ctx.cls))
        return real(rv, *a, **k)
    monkeypatch.setattr(golden, "plan", counting)
    c.app.state.studio.cache.clear()
    course = c.get("/api/catalogs-summary").json()["catalogs"][CAT]
    lp = c.get("/api/catalogs-summary", params={"class": "learningprogram"}).json()["catalogs"][CAT]
    assert sorted(planned) == [(CAT, "course"), (CAT, "learningprogram")]
    assert c.get("/api/catalogs-summary").json()["catalogs"][CAT] == course
    assert c.get("/api/catalogs-summary", params={"class": "learningprogram"}).json()["catalogs"][CAT] == lp
    assert len(planned) == 2  # both kept: nothing is worked out again
    assert course["columns"] != lp["columns"]
