"""The per-verdict work stays small on big catalogs: a verdict rewrites one page's golden file from that page alone,
the "Annotated by" counts are reused until a rule's own annotations change, and a score can run in a process of its
own."""

from __future__ import annotations

from test_golden_versions import CAT, ERIC, JARED, B, _mark, _rows, studio  # noqa: F401  (studio: the fixture)
from test_scores import _wait, scored  # noqa: F401  (scored: the fixture)

import threading

from golden_datasets import golden, review
from golden_datasets.context import Ctx
from golden_datasets.review import LOADER, PEOPLE_CACHE, Review, Snapshot


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


def test_the_rule_list_and_its_annotated_by_counts_share_one_pass_over_the_rules(studio, monkeypatch):  # noqa: F811
    """Opening the Rules tab asks for every rule's status (/rules) and every rule's "Annotated by" counts (/annotators)
    at once. Each rule's rows and row states are built once, for both: on Marshall the two requests used to do it
    all twice, side by side on one core (13 s and 12 s)."""
    c, ctx, _ = studio
    _mark(c, JARED, "course-name", _rows(c, "course-name")["page-0"], "correct")
    review.STATUS_CACHE.clear()
    PEOPLE_CACHE.clear()
    built: list[str] = []
    real = Review._row_states

    def counting(self, rule_id, rows, stems=None):
        if stems is None:
            built.append(rule_id)
        return real(self, rule_id, rows, stems)
    monkeypatch.setattr(Review, "_row_states", counting)
    monkeypatch.setattr(review._Recent, "RULES_KEPT", 1)  # the per-rule cache can't keep rules between the two
    LOADER.forget_reviews()
    answers: dict = {}
    threads = [threading.Thread(target=lambda p=p: answers.__setitem__(p, c.get(f"{B}/{p}").json()))
               for p in ("rules", "annotators")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    rules = LOADER.review(Ctx(ctx.root, CAT)).snap.rules
    assert sorted(built) == sorted(rules)  # each rule once, for both requests
    assert next(p for p in answers["annotators"]["people"] if p["name"] == JARED)["values"] == 1
    assert {r["rule_id"] for g in answers["rules"]["groups"] for r in g["rules"]} == set(rules)


def test_choosing_an_annotated_by_filter_reuses_the_counts_of_every_filter(studio, monkeypatch):  # noqa: F811
    """The rule list's count for any "Annotated by" choice comes from the one pass that counted them all; it is the
    count a row-by-row check gives."""
    c, ctx, _ = studio
    rows = _rows(c, "course-name")
    _mark(c, JARED, "course-name", rows["page-0"], "correct")
    _mark(c, ERIC, "course-name", rows["page-1"], "correct")
    c.post(f"{B}/annotations", json={"type": "verdict", "author": JARED, "verdict": "wrong",
                                     "expected": {"text": "Another name"},
                                     "target": {"kind": "match", "rule_id": "course-name",
                                                "occurrence_key": rows["page-2"]["key"]}})
    assert c.get(f"{B}/annotators").status_code == 200  # counted once, with the rule list
    rv = LOADER.review(Ctx(ctx.root, CAT))
    for rid in rv.snap.rules:
        annotations = rv.annotations(rid)
        for by in (*review.FILTER_WHO, JARED, ERIC, "Somebody Else"):
            for verdict in review.FILTER_VERDICTS:
                expected = sum(1 for a in annotations.values() if review.annotated_match(a, by, verdict))
                assert rv.annotated_count(rid, by, verdict) == expected, (rid, by, verdict)
    calls: list[str] = []
    real = Review.annotations
    monkeypatch.setattr(Review, "annotations", lambda self, rid: calls.append(rid) or real(self, rid))
    for by, verdict in ((review.EXPERTS, None), (JARED, "wrong"), (review.NOBODY, None)):
        assert c.get(f"{B}/annotators", params={"by": by, "verdict": verdict}).status_code == 200
    assert calls == []


def test_the_server_works_out_each_catalogs_rule_list_when_it_starts(studio, monkeypatch):  # noqa: F811
    """After the home page, the server works out every catalog's rule statuses and "Annotated by" counts, so the
    first visit to a catalog's Rules tab after a restart doesn't."""
    c, _, _ = studio
    review.STATUS_CACHE.clear()
    PEOPLE_CACHE.clear()
    warm = c.app.state.studio.warm_home()
    warm.join(timeout=60)
    assert not warm.is_alive()
    worked_out: list[str] = []
    real = Review._rule_status

    def counting(self, rule_id, states=None):
        worked_out.append(rule_id)
        return real(self, rule_id, states)
    monkeypatch.setattr(Review, "_rule_status", counting)
    assert c.get(f"{B}/rules").status_code == 200 and c.get(f"{B}/annotators").status_code == 200
    assert worked_out == []


def test_a_loaded_snapshot_is_out_of_the_collectors_sight_until_it_is_evicted(studio):  # noqa: F811
    """A full garbage collection walked every loaded snapshot's rows (millions of objects) a few times per Rules tab:
    a loaded snapshot is frozen, and an eviction unfreezes before it collects, so nothing frozen is kept for good."""
    import gc
    import weakref

    c, ctx, _ = studio
    gc.unfreeze()
    LOADER._snaps.clear()
    LOADER.review(Ctx(ctx.root, CAT))
    assert gc.get_freeze_count() > 0

    class Node:
        pass
    a, b = Node(), Node()
    a.other, b.other = b, a  # a cycle: only a collection frees it, never refcounting
    gone = weakref.ref(a)
    review.freeze_loaded()
    del a, b
    review.release_memory()
    assert gone() is None and gc.get_freeze_count() > 0
    gc.unfreeze()


def test_the_servers_contexts_download_the_manifest_once_until_it_changes(studio, monkeypatch):  # noqa: F811
    """The home page reads every catalog and class: each context used to download its own copy of the manifest (six
    or seven 130 KB downloads per visit); they share one, and only a change (its ETag) downloads it again."""
    from golden_datasets import manifest

    c, ctx, _ = studio
    st = c.app.state.studio
    root = st.ctx(CAT).root
    downloads: list[str] = []
    real = type(root).read_bytes

    def counting(self, path, *a, **k):
        if path == manifest.PATH:
            downloads.append(path)
        return real(self, path, *a, **k)
    monkeypatch.setattr(type(root), "read_bytes", counting)
    st._ctx.clear()
    first = [st.ctx(CAT, cls).manifest() for cls in ("course", "learningprogram")]
    assert len(downloads) == 1 and first[0] is first[1]
    manifest.update(root, lambda doc: doc.setdefault("note", "changed"))  # a write from elsewhere (the CLI, a score)
    downloads.clear()
    st._ctx.clear()
    assert st.ctx(CAT).manifest()["note"] == "changed" and len(downloads) >= 1


def test_an_older_golden_versions_counts_are_read_once_per_publication(monkeypatch):
    """Datasets lists every version with its values: an older version's files no longer change, so its
    golden.parquet is counted once per publication, not downloaded again on every visit."""
    from collections import Counter
    from types import SimpleNamespace

    from golden_datasets.server import routes_golden

    reads: list[str] = []
    monkeypatch.setattr(routes_golden, "_count_values", lambda ctx, path: reads.append(path) or Counter(values=3))
    st = SimpleNamespace(cache={})
    doc = {"published_at": "2026-11-01T00:00:00Z"}
    for _ in range(3):
        assert routes_golden._values_then(st, None, "golden/ruleset-v1", doc)["values"] == 3
    assert reads == ["golden/ruleset-v1"]
    routes_golden._values_then(st, None, "golden/ruleset-v1", {"published_at": "2026-11-02T00:00:00Z"})
    assert len(reads) == 2  # published again: counted again


def test_the_server_collects_less_often(monkeypatch):
    import gc

    before = gc.get_threshold()
    try:
        review.tune_gc()
        assert gc.get_threshold() == review.GC_THRESHOLDS
    finally:
        gc.set_threshold(*before)


def test_one_record_builds_its_rules_rows_on_its_own_pages_only(studio, monkeypatch):  # noqa: F811
    """A record's page shows each property's value and state on that record: its rules' rows are built on the
    record's pages, not over the whole catalog (every property rule's rows took 10 s+ on the big catalogs)."""
    c, ctx, _ = studio
    rows = _rows(c, "course-name")
    _mark(c, JARED, "course-name", rows["page-0"], "correct")
    record = rows["page-0"]["record_external_identifier"]
    before = c.get(f"{B}/courses/{record}").json()
    whole: list[str] = []
    real = Snapshot._build_rows

    def watching(self, rule_id, stems=None):
        if stems is None:
            whole.append(rule_id)
        return real(self, rule_id, stems)
    monkeypatch.setattr(Snapshot, "_build_rows", watching)
    LOADER.review(Ctx(ctx.root, CAT)).snap._rows.clear()
    after = c.get(f"{B}/courses/{record}").json()
    assert whole == []
    assert after == before
    name = next(p for o in after["occurrences"] for p in o["properties"] if p["rule_id"] == "course-name")
    assert name["state"] == "correct" and JARED in name["annotators"]
