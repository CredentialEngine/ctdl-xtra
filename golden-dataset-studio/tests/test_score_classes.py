"""Scoring by class (LearningProgram plan, Phase 3): records are filtered to the class before xtra's scorer pairs them
(approved item 23), so a page that holds a program and courses pairs each class with its own records; each score
writes its properties' results under the extract output and appends one history line per property, with golden
exact held to 90% and partial kept apart (approved items 25–28)."""

from __future__ import annotations

import json

from common.keys import page_stem
from test_golden_versions import CAT, JARED, _mark, _rows, studio  # noqa: F401  (studio: the fixture)
from test_scores import scored  # noqa: F401

from golden_datasets import golden, scores, xtra_paths
from golden_datasets.context import Ctx
from golden_datasets.storage import LocalRoot

CRAWL = "2026-11-24T10-00-00Z"
URL = "https://catalogs.wvu.edu/undergraduate/schoolofdentistry/"  # both a program page and a course page
STEM = page_stem(URL)


def _f(prop: str, value: str) -> dict:
    return {"ctdl_property": prop, "value": value, "source_url": URL, "property": prop}


#: The page's golden Course records: two courses (the program is LearningProgram's, not here).
COURSES = {STEM: [{"fields": [_f("ceterms:name", "Dental Anatomy"), _f("ceterms:codedNotation", "DENT 101")]},
                  {"fields": [_f("ceterms:name", "Oral Histology"), _f("ceterms:codedNotation", "DENT 102")]}]}
PROGRAMS = {STEM: [{"fields": [_f("ceterms:name", "Dental Hygiene, B.S.")]}]}


def _old_layout(folder) -> None:
    """An older output (`records/`): xtra's first record on the page is the program, then the courses."""
    (folder / "records").mkdir(parents=True)
    recs = {STEM: ("LearningProgram", {"ceterms:name": "Dental Hygiene, B.S."}),
            f"{STEM}--resource-002": ("Course", {"ceterms:name": "Dental Anatomy", "ceterms:codedNotation": "DENT 101"}),
            f"{STEM}--resource-003": ("Course", {"ceterms:name": "Oral Histology", "ceterms:codedNotation": "DENT 102"})}
    for rid, (entity, expected) in recs.items():
        (folder / "records" / f"{rid}.json").write_text(json.dumps(
            {"record_id": rid, "entity_type": entity, "source_url": URL, "expected": expected}))
    (folder / "extract-report.json").write_text(json.dumps({"skipped": []}))


def _new_layout(folder) -> None:
    """Today's output (`extraction_report/`): each file says its class; the page orders the three resources."""
    html = ("<html><body><h1 id='p'>Dental Hygiene, B.S.</h1><h2 id='a'>DENT 101 Dental Anatomy</h2>"
            "<h2 id='b'>DENT 102 Oral Histology</h2></body></html>")
    (folder / "pages").mkdir(parents=True)
    (folder / "pages" / f"{STEM}.html").write_text(html)
    rows = [("ceterms:LearningProgram", "wvu_program", "ceterms:name", "Dental Hygiene, B.S.", "#p"),
            ("ceterms:Course", "wvu_DENT101", "ceterms:name", "Dental Anatomy", "#a"),
            ("ceterms:Course", "wvu_DENT101", "ceterms:codedNotation", "DENT 101", "#a"),
            ("ceterms:Course", "wvu_DENT102", "ceterms:name", "Oral Histology", "#b"),
            ("ceterms:Course", "wvu_DENT102", "ceterms:codedNotation", "DENT 102", "#b")]
    for ctdl_type, rid, prop, value, css in rows:
        d = folder / "extraction_report" / "ceterms" / prop.replace(":", "_")
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{rid}.json").write_text(json.dumps({"type": ctdl_type, "resource_id": rid, "ctdl_property": prop,
                                                   "value": value, "source_url": URL, "notes": f"css={css}"}))
    for prop in ("ceterms_name", "ceterms_codedNotation"):
        (folder / f"extraction-{prop}-report.json").write_text(json.dumps({"property": prop, "run_id": CRAWL}))


def _outcomes(folder, cls, pages) -> dict:
    store = scores.RecordsStore(LocalRoot(folder), "", "wvu", CRAWL, cls)
    return scores.run_scorer(store, pages, "wvu", CRAWL, "test")["exact"]["outcomes"]


def test_a_page_with_a_program_and_courses_pairs_each_class_with_its_own_records(tmp_path):
    for name, make in (("old", _old_layout), ("new", _new_layout)):
        out = tmp_path / name
        make(out)
        # without the class, the page's first record (the program) is paired with the first golden course
        assert _outcomes(out, None, COURSES)["match"] < 4, name
        # with it, the courses meet the courses, and the program the program
        assert _outcomes(out, "course", COURSES) == {"match": 4, "mismatch": 0, "missing": 0, "unsure": 0}, name
        assert _outcomes(out, "learningprogram", PROGRAMS)["match"] == 1, name
        store = scores.RecordsStore(LocalRoot(out), "", "wvu", CRAWL, "learningprogram")
        assert len(store.records()) == 1, name


def test_a_score_records_each_property_and_appends_its_history(scored):  # noqa: F811
    c, ctx, tmp = scored
    doc = scores.score(Ctx(ctx.root, CAT), "ruleset-v1", trigger="new-output")
    assert doc["status"] == "done" and doc["recorded"] == ["codedNotation", "name"]
    xtra = tmp / "xtra-cli-output"
    out = doc["output"]["id"]
    for tree in ("golden", "silver"):
        f = xtra / xtra_paths.property_score_dir(CAT, ctx.crawl, out, f"ruleset-v1-{tree}", "course",
                                                 "ceterms_name") / "score.json"
        got = json.loads(f.read_text())
        assert got["baseline"] == f"ruleset-v1-{tree}" and got["property"] == "ceterms:name"
    [line] = scores.history(Ctx(ctx.root, CAT), "name")
    assert line == json.loads((xtra / "scores" / "course" / "ceterms_name" / f"{CAT}.jsonl").read_text())
    assert (line["catalog"], line["class"], line["extract_run"], line["golden_version"], line["trigger"],
            line["score"]) == (CAT, "course", out, "ruleset-v1", "new-output", doc["id"])
    # golden: 1 value, matched; silver: 3 values, exact and partial kept apart, partial never counted towards 90%
    assert (line["golden"]["values"], line["golden"]["match"], line["golden"]["exact"],
            line["golden"]["meets_target"]) == (1, 1, 1.0, True)
    assert (line["silver"]["values"], line["silver"]["match"], line["silver"]["partial"], line["silver"]["exact"],
            line["silver"]["partial_share"]) == (3, 1, 1, round(1 / 3, 4), round(1 / 3, 4))
    assert "meets_target" not in line["silver"]
    assert line["scored_with"]["xtra_cli_version"] and "xtra_cli_commit" in line["scored_with"]
    assert "extracted_with" in line
    # the same pair again: no new score, no new line
    assert scores.score(Ctx(ctx.root, CAT), "ruleset-v1")["id"] == doc["id"]
    assert len(scores.history(Ctx(ctx.root, CAT), "name")) == 1


def test_a_score_for_some_properties_records_only_those(scored):  # noqa: F811
    _, ctx, _ = scored
    doc = scores.score(Ctx(ctx.root, CAT), "ruleset-v1", trigger="golden-published", properties=["name"])
    assert doc["columns"] == ["codedNotation", "name"] and doc["recorded"] == ["name"]
    assert scores.history(Ctx(ctx.root, CAT), "codedNotation") == []
    assert [h["trigger"] for h in scores.history(Ctx(ctx.root, CAT), "name")] == ["golden-published"]


def test_verdicts_gather_their_columns_for_the_pending_score(studio):  # noqa: F811
    c, ctx, _ = studio
    _mark(c, JARED, "course-name", _rows(c, "course-name")["page-0"], "correct")
    _mark(c, JARED, "course-code", _rows(c, "course-code")["page-1"], "correct")
    pending = ctx.root.read_json(f"{CAT}/{ctx.crawl}/course/scores-pending.json")
    assert pending["columns"] == ["codedNotation", "name"]
    golden.request_score(Ctx(ctx.root, CAT), "every column")  # None: every column
    assert ctx.root.read_json(f"{CAT}/{ctx.crawl}/course/scores-pending.json")["columns"] is None
