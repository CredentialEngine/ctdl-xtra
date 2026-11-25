"""Findings, property status and discussion (LearningProgram plan, Phase 6), outside in: the HTTP API on a scored
Course catalog. Anyone sets Needs review, only the SME role sets Done; a finding covers Where-it's-wrong groups whose
units are counted live from the latest score; threads sit on findings and groups; the running notes' codes import."""

from __future__ import annotations

from test_golden_versions import CAT, ERIC, JARED, studio  # noqa: F401  (studio: the fixture)
from test_scores import scored  # noqa: F401

from golden_datasets import scores
from golden_datasets.cli import main
from golden_datasets.context import Ctx

P = "/api/properties/course/name"


def test_anyone_sets_needs_review_and_only_an_expert_sets_done(studio):  # noqa: F811
    c, _, _ = studio
    assert c.post(f"{P}/status", json={"status": "needs review", "author": ERIC}).status_code == 200
    r = c.post(f"{P}/status", json={"status": "done", "author": ERIC})
    assert r.status_code == 403 and "subject-matter expert" in r.json()["detail"]
    r = c.post(f"{P}/status", json={"status": "done", "author": JARED})
    assert r.status_code == 200
    s = c.get(f"{P}/review").json()["status"]
    assert (s["status"], s["by"], s["role"]) == ("done", JARED, "sme")
    assert [(h["status"], h["by"]) for h in s["history"]] == [("needs review", ERIC)]
    assert c.get("/api/property-status").json()["name"]["status"] == "done"
    assert c.get("/api/property-status", params={"class": "learningprogram"}).json() == {}
    assert c.post(f"{P}/status", json={"status": "finished", "author": JARED}).status_code == 422
    assert c.post("/api/properties/program/name/status", json={"status": "done", "author": JARED}).status_code == 422


def test_a_finding_is_saved_whole_and_a_person_marks_it_fixed(studio):  # noqa: F811
    c, _, _ = studio
    assert c.post(f"{P}/findings", json={"author": ERIC, "title": "no code"}).status_code == 422
    f = c.post(f"{P}/findings", json={"author": ERIC, "code": "N2", "title": "The card text instead of the heading",
                                      "whose": "extractor", "cause": "reads .course-title", "fix": "read the h1"}).json()
    assert (f["state"], f["kind"], f["created"]["by"]) == ("open", "mismatch", ERIC)
    assert c.post(f"{P}/findings", json={"author": ERIC, "code": "N2", "title": "again"}).status_code == 422
    assert c.put(f"{P}/findings/{f['id']}", json={"author": ERIC, "whose": "nobody"}).status_code == 422
    g = c.put(f"{P}/findings/{f['id']}", json={"author": JARED, "state": "fixed"}).json()
    assert (g["state"], g["author"], g["created"]["by"], g["fix"]) == ("fixed", JARED, ERIC, "read the h1")
    assert c.put(f"{P}/findings/fd-nope", json={"author": ERIC}).status_code == 404
    [one] = c.get(f"{P}/review").json()["findings"]
    assert one["state"] == "fixed" and one["live"] is None


def test_a_findings_units_are_counted_live_from_each_catalogs_latest_score(scored):  # noqa: F811
    c, ctx, _ = scored
    scores.score(Ctx(ctx.root, CAT), "ruleset-v1")
    sc = c.get(f"/api/catalogs/{CAT}/scores").json()[-1]["id"]
    [g] = [x for x in c.get(f"/api/catalogs/{CAT}/scores/{sc}/wrong",
                            params={"basis": "rule", "column": "name"}).json()["groups"] if x["outcome"] == "partial"]
    link = {"catalog": CAT, "outcome": "partial", "field": g["field"], "by": g["by"], "key": g["key"], "group_by": "auto"}
    f = c.post(f"{P}/findings", json={"author": ERIC, "code": "N9", "title": "A partial name", "links": [link]}).json()
    [got] = [x for x in c.get(f"{P}/review").json()["findings"] if x["id"] == f["id"]]
    assert got["live"]["counts"]["partial"] == [0, 1]  # golden 0, silver 1
    assert got["live"]["counts"]["wrong"] is None
    assert got["live"]["rows"] == [{"catalog": CAT, "outcome": "partial", "by": g["by"], "key": g["key"],
                                    "golden": 0, "silver": 1}]
    # a group no longer in the score: 0 units, still open until a person says it's fixed
    gone = {**link, "key": "something else"}
    c.put(f"{P}/findings/{f['id']}", json={"author": ERIC, "links": [gone]})
    [got] = [x for x in c.get(f"{P}/review").json()["findings"] if x["id"] == f["id"]]
    assert got["live"]["counts"]["partial"] == [0, 0] and got["state"] == "open"


def test_threads_sit_on_a_finding_or_a_group(studio):  # noqa: F811
    c, _, _ = studio
    f = c.post(f"{P}/findings", json={"author": ERIC, "code": "N1", "title": "Whitespace"}).json()
    assert c.post(f"{P}/threads", json={"author": JARED, "note": "Agreed.",
                                        "target": {"kind": "finding", "id": f["id"]}}).status_code == 200
    group = {"kind": "group", "catalog": "avc", "outcome": "wrong", "by": "word diff", "key": "cut short"}
    assert c.post(f"{P}/threads", json={"author": ERIC, "note": "Cut at a line break?", "target": group}).status_code == 200
    assert c.post(f"{P}/threads", json={"author": ERIC, "note": "x", "target": {"kind": "finding", "id": "fd-no"}}).status_code == 404
    assert c.post(f"{P}/threads", json={"author": ERIC, "note": " ", "target": group}).status_code == 422
    rv = c.get(f"{P}/review").json()
    assert rv["findings"][0]["comments"] == 1
    assert rv["threads"] == {f"finding:{f['id']}": 1, "group:avc|wrong||word diff|cut short": 1}
    [cm] = c.get(f"{P}/threads", params={"key": "group:avc|wrong||word diff|cut short"}).json()
    assert (cm["type"], cm["author"], cm["note"]) == ("comment", ERIC, "Cut at a line break?")


def test_the_running_notes_codes_import_verbatim(studio, capsys):  # noqa: F811
    c, ctx, _ = studio
    assert main(["findings", "seed", "--class", "course", "--root", ctx.root.uri]) == 0
    assert "14 findings added (D1, D1b, D2, D3, D4, D5, D6, D7, D8, D9, M1, M2, M3, M4)" in capsys.readouterr().out
    assert main(["findings", "seed", "--class", "course", "--root", ctx.root.uri]) == 0
    assert "every code was there already" in capsys.readouterr().out
    fs = {f["code"]: f for f in c.get("/api/properties/course/description/review").json()["findings"]}
    d8 = fs["D8"]
    assert d8["title"] == "A requisite lead-in with no colon (\"Prerequisite Completion of…\") isn't dropped"
    assert (d8["whose"], d8["kind"], d8["counts"]["partial"], d8["catalogs"]) == ("extractor", "mismatch", [0, 1],
                                                                                 "AVC (FTEC 295A)")
    assert d8["assessment"] == "This is a real miss." and d8["author"] == "Seth Alt"
    assert fs["M4"]["kind"] == "missing" and fs["M4"]["counts"]["missing"] == [0, 319]
    assert main(["findings", "seed", "--class", "learningprogram", "--root", ctx.root.uri]) == 2  # Course's codes


def test_uark_is_known_by_its_short_name_and_isnt_a_program_source():
    """UARK, added from the picker, has a short name for the score tables and the address, and says it has no
    programs, with no hand edits (catalogs.KNOWN)."""
    from golden_datasets.catalogs import info, resolve

    folder = "training-uark-edu-portal-training"
    assert resolve("uark") == folder and resolve(folder) == folder
    meta = info(folder)
    assert (meta["short"], meta["name"], tuple(meta["not_sources"])) == ("uark", "UARK", ("learningprogram",))
