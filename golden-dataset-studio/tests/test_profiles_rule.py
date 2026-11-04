"""Lists of objects, "not on the page" claims and the reviewer's answer in the golden dataset (sme-fixes spec §5, §6,
§7), on a four-page catalog shaped like AVC: ACCT199's four durations, DA107A's description, a course with a
prerequisite, and a page with no details box."""

from __future__ import annotations

import json

import pytest

from golden_datasets import crawls, engine, golden, profiles_rule, properties
from golden_datasets.cli import main
from golden_datasets.context import Ctx
from golden_datasets.storage import LocalRoot

CAT = "cuesta-curriqunet-com-catalog-iq-27137"
B = f"/api/catalogs/{CAT}"
JARED, ERIC = "Jared Diener", "Eric Riddoch"
DESC_KEY, TIME_KEY = "ceterms:description", "ceterms:timeRequired"

DURATIONS = {  # AVC's infocard: a label, then its hours (a range kept whole)
    0: [("Total Course In-Class (Contact) Hours", "54.0 - 432.0"), ("Total Course Out-of-Class Hours", "0.0 - 0.0"),
        ("Total Course Lecture Hours", "0.0"), ("Total Course Lab Hours", "432.0")],
    1: [("Total Course In-Class (Contact) Hours", "180.0"), ("Total Course Lab Hours", "135.0")],
    2: [("Total Course Lecture Hours", "54.0")],
    3: [],
}
CODES = {0: "ACCT 199", 1: "DA 107A", 2: "ATH 103L", 3: "ZZ 100"}
DA107A = ("Students will perform in a dance production. (R3)", "# Enrollment in any combination of DA 107A, DA 107B or "
          "DA 107C is limited to 4 times.")


def _html(i: int) -> str:
    cards = "".join(f'<div class="col"><h5>{label}</h5><div class="text"><p>{hours}</p></div></div>'
                    for label, hours in DURATIONS[i])
    desc = "\n".join(DA107A) if i == 1 else f"Course {i} description."
    details = "" if i == 3 else ('<div class="details"><span class="units">3.0 Units</span>'
                                 + ('<p class="prereq">Completion of ATH 100 and completion of or concurrent enrollment '
                                    'in ATH 103.</p>' if i == 2 else "") + "</div>")
    return (f"<html><head><title>{CODES[i]} title</title></head><body><h1>{CODES[i]}</h1>"
            f'<p class="desc">{desc}</p>{details}<div class="infocard">{cards}</div></body></html>')


RULES = {"catalog": CAT, "settings": {"content_root": "body"}, "rules": [
    {"rule_id": "course-page", "kind": "page", "definition": {"url_regex": "/c/\\d+$", "label": "Course"}},
    {"rule_id": "locator-course-page", "kind": "locator",
     "definition": {"page_rules": ["course-page"], "scope": None, "repeat": None, "repeat_filter": None}},
    {"rule_id": "course-code", "kind": "property", "property_label": "Coded Notation",
     "ctdl_property": "ceterms:codedNotation",
     "definition": {"locator": "locator-course-page", "rule_type": "css", "selector": "h1"}},
    {"rule_id": "course-description", "kind": "property", "property_label": "Description",
     "ctdl_property": "ceterms:description",
     "definition": {"locator": "locator-course-page", "rule_type": "css", "selector": "p.desc",
                    "transforms": ["strip"]}},
    {"rule_id": "course-prerequisite-description", "kind": "property", "property_label": "Prerequisite: Description",
     "ctdl_property": "ceterms:prerequisite>ceterms:description",
     "definition": {"locator": "locator-course-page", "rule_type": "css", "selector": "p.prereq",
                    "absent_if": {"within": ".details", "missing": ".prereq"}}},
    {"rule_id": "course-estimated-duration", "kind": "property", "property_label": "Estimated Duration",
     "ctdl_property": "ceterms:estimatedDuration",
     "definition": {"locator": "locator-course-page", "rule_type": "css+regex", "selector": ".infocard",
                    "multiple": {"split": "regex",
                                 "regex": "(Total Course [^\\n]*?Hours\\s*\\d[\\d.]*(?:\\s*-\\s*\\d[\\d.]*)?)"},
                    "transforms": ["strip", "collapse_ws"]}},
]}
#: The old shape: Estimated Duration's children read its items (`input: rule`), as on AVC before §5.1.
CHILDREN = [
    {"rule_id": "course-estimated-duration-description", "kind": "property",
     "property_label": "Estimated Duration Description", "ctdl_property": "ceterms:estimatedDuration>ceterms:description",
     "definition": {"locator": "locator-course-page", "rule_type": "regex",
                    "input": {"from": "rule", "rule": "course-estimated-duration"},
                    "multiple": {"split": "regex", "regex": "\\A\\s*(Total Course [\\s\\S]*?Hours)"},
                    "transforms": ["strip", "collapse_ws"]}},
    {"rule_id": "course-estimated-duration-time-required", "kind": "property", "property_label": "Time Required",
     "ctdl_property": "ceterms:estimatedDuration>ceterms:timeRequired",
     "definition": {"locator": "locator-course-page", "rule_type": "regex",
                    "input": {"from": "rule", "rule": "course-estimated-duration"},
                    "multiple": {"split": "regex", "regex": "Hours\\s*(\\d[\\d.]*(?:\\s*-\\s*\\d[\\d.]*)?)\\s*\\Z"},
                    "transforms": ["strip", "collapse_ws"]}},
    *[{"rule_id": f"course-estimated-duration-{x}-duration", "kind": "property", "property_label": f"{x.title()} Duration",
       "ctdl_property": f"ceterms:estimatedDuration>ceterms:{x}Duration",
       "definition": {"locator": "locator-course-page", "rule_type": "none"}} for x in ("exact", "minimum", "maximum")],
]
ACCT199 = [{DESC_KEY: d, TIME_KEY: t} for d, t in DURATIONS[0]]


def _crawl(base, crawl: str, seed: str) -> None:
    d = base / CAT / crawl
    (d / "pages").mkdir(parents=True)
    (d / "crawl.json").write_text(json.dumps({"seed_url": seed, "status": "complete", "pages_saved": 4,
                                              "started_at": "2026-10-01T00:00:00Z",
                                              "finished_at": f"{crawl[:10]}T12:00:00Z"}))
    for i in range(4):
        html = _html(i).encode()
        (d / "pages" / f"page-{i}.html").write_bytes(html)
        (d / "pages" / f"page-{i}.meta.json").write_text(json.dumps({
            "stem": f"page-{i}", "requested_url": f"{seed}c/{i}", "final_url": f"{seed}c/{i}", "http_status": 200,
            "retrieved_at": "2026-10-01T00:00:00Z", "bytes": len(html), "sha256": "x"}))


def _studio(tmp_path, capsys, monkeypatch, rules: dict):
    from fastapi.testclient import TestClient

    from golden_datasets.server.app import create_app

    monkeypatch.setenv("GOLDEN_DATASETS_GOLDEN_ROOT", str(tmp_path / "golden"))
    src, dst = LocalRoot(tmp_path / "xtra-cli-output"), tmp_path / "root"
    _crawl(src.base, "2026-10-21T10-00-00Z", "https://cuesta.curriqunet.com/catalog/iq/27137/")
    dst.mkdir()
    crawls.add_catalog(LocalRoot(dst), src, CAT, log=lambda *a, **k: None)
    draft = tmp_path / "first.json"
    draft.write_text(json.dumps(rules))
    assert main(["rule", "publish", "--root", str(dst), "--catalog", CAT, str(draft), "--note", "first"]) == 0
    capsys.readouterr()
    return TestClient(create_app(str(dst))), Ctx(LocalRoot(dst), CAT)


def _rows(c, rule: str) -> dict[str, dict]:
    return {r["page_stem"]: r for r in c.get(f"{B}/rules/{rule}/rows").json()["rows"]}


def _post(c, body: dict, status: int = 200) -> dict:
    r = c.post(f"{B}/annotations", json=body)
    assert r.status_code == status, r.text
    return r.json()


def _verdict(c, author: str, rule: str, row: dict, verdict: str, **more) -> dict:
    return _post(c, {"type": "verdict", "author": author, "verdict": verdict,
                     "target": {"kind": "match", "rule_id": rule, "occurrence_key": row["key"]}, **more})


def _golden(ctx: Ctx, stem: str) -> list[dict]:
    rv = golden.LOADER.review(Ctx(ctx.root, CAT))
    [rec] = golden.plan(rv)["pages"][stem]
    return rec["fields"]


def _of(fields: list[dict], prop: str) -> list[dict]:
    return [f for f in fields if f["ctdl_property"] == prop]


@pytest.fixture
def profile_studio(tmp_path, capsys, monkeypatch):
    rules = json.loads(json.dumps(RULES))
    rules["rules"][-1]["definition"]["profile"] = {
        "fields": {DESC_KEY: {"rule_type": "regex", "regex": "\\A\\s*(Total Course [\\s\\S]*?Hours)",
                              "transforms": ["strip", "collapse_ws"]},
                   TIME_KEY: {"rule_type": "regex", "regex": "Hours\\s*(\\d[\\d.]*(?:\\s*-\\s*\\d[\\d.]*)?)\\s*\\Z",
                              "transforms": ["strip", "collapse_ws"]}},
        "key": DESC_KEY}
    c, ctx = _studio(tmp_path, capsys, monkeypatch, rules)
    properties.apply(Ctx(ctx.root, CAT), "test")  # every property of properties.csv has a rule (`check` asks)
    return c, ctx


# --- §5.1 extraction --------------------------------------------------------------------------------------------
def test_a_profile_rule_gives_acct199_four_objects_with_each_fields_place():
    rules = json.loads(json.dumps(RULES))
    d = rules["rules"][-1]["definition"]
    d["profile"] = {"fields": {DESC_KEY: {"regex": "\\A\\s*(Total Course [\\s\\S]*?Hours)", "transforms": ["strip"]},
                               TIME_KEY: {"regex": "Hours\\s*(\\S.*)\\Z", "transforms": ["strip"]}},
                    "key": DESC_KEY}
    doc = engine.parse(_html(0))
    body = engine.select_one(doc, "body", True)
    paths = engine.Paths()
    got = engine.run_property(d, body, "u", paths, paths(body))
    assert [json.loads(r["value"]) for r in got] == ACCT199
    assert got[0]["value"] == json.dumps(ACCT199[0], separators=(",", ":"))  # canonical JSON, keys sorted
    loc = json.loads(got[0]["fields"])
    text = engine.text_content(engine.select_one(body, ".infocard"))
    for key in (DESC_KEY, TIME_KEY):  # each field's offsets point at its words on the page
        assert text[loc[key]["char_start"]:loc[key]["char_end"]] == ACCT199[0][key]
    # a draft's examples check objects too
    assert engine.values_of_text(d, "Total Course Lab Hours 432.0") == [{DESC_KEY: "Total Course Lab Hours",
                                                                         TIME_KEY: "432.0"}]
    # a page with no items: the item rule's own outcome
    empty = engine.parse(_html(3))
    body3 = engine.select_one(empty, "body", True)
    assert [r["status"] for r in engine.run_property(d, body3, "u", paths, paths(body3))] == ["empty"]


def test_absent_if_claims_not_on_the_page_only_when_the_container_is_there():
    d = RULES["rules"][4]["definition"]
    paths = engine.Paths()

    def status(i: int) -> tuple[str, str | None]:
        body = engine.select_one(engine.parse(_html(i)), "body", True)
        r = engine.run_property(d, body, "u", paths, paths(body))[0]
        return r["status"], r["css_path"]

    assert status(0) == ("absent", "div:nth-of-type(1)")  # the details box is there, with no prerequisite: a claim
    assert status(2)[0] == "found"
    assert status(3) == ("no_match", None)  # no details box: the rule made no claim
    # `missing` as a label's words: the same claim
    by_label = {**d, "absent_if": {"within": ".details", "missing": {"label": "Completion of"}}}
    body = engine.select_one(engine.parse(_html(0)), "body", True)
    assert engine.run_property(by_label, body, "u", paths, paths(body))[0]["status"] == "absent"
    body2 = engine.select_one(engine.parse(_html(2)), "body", True)
    no_sel = {**by_label, "selector": "p.nothing"}
    assert engine.run_property(no_sel, body2, "u", paths, paths(body2))[0]["status"] == "no_match"


# --- §5.1 the ruleset change: six rules → one ---------------------------------------------------------------------
def test_properties_apply_folds_the_six_duration_rules_into_one_profile_rule(tmp_path, capsys, monkeypatch):
    rules = json.loads(json.dumps(RULES))
    rules["rules"] += CHILDREN
    c, ctx = _studio(tmp_path, capsys, monkeypatch, rules)
    assert set(_rows(c, "course-estimated-duration-description")) == {"page-0", "page-1", "page-2", "page-3"}
    out = properties.apply(Ctx(ctx.root, CAT), "test")
    assert out["folded"] == ["course-estimated-duration"]
    assert out["removed"] == sorted(r["rule_id"] for r in CHILDREN)
    _, now = Ctx(ctx.root, CAT).ruleset_rules(2)
    assert not [rid for rid in now if rid.startswith("course-estimated-duration-")]
    d = now["course-estimated-duration"]["definition"]
    assert now["course-estimated-duration"]["version"] == 2 and d["profile"]["key"] == DESC_KEY
    assert d["profile"]["fields"][TIME_KEY]["regex"].startswith("Hours")  # the child's split regex, as a plain regex
    assert "input" not in d["profile"]["fields"][DESC_KEY]
    snap = golden.LOADER.review(Ctx(ctx.root, CAT)).snap  # the new extraction (the server keeps its manifest a while)
    row = next(r for r in snap.rows("course-estimated-duration") if r["page_stem"] == "page-0")
    assert [json.loads(i["value"]) for i in row["items"]] == ACCT199
    assert row["value"].split("\n")[0] == "Total Course In-Class (Contact) Hours · 54.0 - 432.0"
    assert properties.apply(Ctx(ctx.root, CAT), "again") is None
    assert main(["check", "--root", ctx.root.uri, "-c", CAT]) == 0
    capsys.readouterr()
    # the rule drafts the children's fields could be read from stay out: the folded parent alone
    keep, drafts, removed = profiles_rule.fold_rules(now)
    assert not drafts and not removed


# --- §5.2, §5.3 review: a verdict per object, an object added by labels -------------------------------------------
def test_each_object_has_its_own_verdict_and_an_added_object_is_labelled_field_by_field(profile_studio, capsys):
    c, ctx = profile_studio
    row = _rows(c, "course-estimated-duration")["page-0"]
    items = row["items"]
    assert [i["fields"][DESC_KEY]["text"] for i in items] == [d for d, _ in DURATIONS[0]]
    assert items[0]["fields"][TIME_KEY]["css_path"].startswith("html > body")  # document-root paths for the pane

    def item(verdict: str, value_index=None, expected=None, author=JARED) -> dict:
        return _post(c, {"type": "verdict", "author": author, "verdict": verdict, "expected": expected,
                         "target": {"kind": "match", "rule_id": "course-estimated-duration",
                                    "occurrence_key": row["key"], "item": True, "value_index": value_index}})

    for i in (0, 1, 2):
        item("correct", i)
    out = item("wrong", 3)
    assert out["rule"]["open_wrong"] == 1 and out["rule"]["status"] == "needs work"  # one ✕ makes the row wrong
    added = {"objects": [{"fields": {
        DESC_KEY: {"text": "Total Course Field Hours", "css_path": items[0]["css_path"], "char_start": 0, "char_end": 5},
        TIME_KEY: {"text": "12.0", "css_path": items[0]["css_path"], "char_start": 6, "char_end": 9}}}]}
    out = item("missing", expected=added)
    assert out["event"]["expected"]["text"] == json.dumps({DESC_KEY: "Total Course Field Hours", TIME_KEY: "12.0"},
                                                          separators=(",", ":"))
    got = _rows(c, "course-estimated-duration")["page-0"]
    assert [i["state"] for i in got["items"]] == ["correct", "correct", "correct", "wrong"]
    assert got["missing_items"][0]["expected"]["objects"][0]["fields"][TIME_KEY]["text"] == "12.0"
    # the annotation log's DuckDB view reads the objects
    capsys.readouterr()
    assert main(["sql", "--root", ctx.root.uri, "-c", CAT, "--format", "json",
                 "SELECT count(*) n FROM annotations WHERE expected.objects IS NOT NULL"]) == 0
    assert json.loads(capsys.readouterr().out.strip())["n"] == 1

    # §5.4: one golden field per object; the ✕'d object is left out, the added one is in, approved by its reviewer
    dur = _of(_golden(ctx, "page-0"), "ceterms:estimatedDuration")
    assert [f["value"] for f in dur] == [*ACCT199[:3], {DESC_KEY: "Total Course Field Hours", TIME_KEY: "12.0"}]
    assert [f["approval"] for f in dur] == ["human", "human", "human", "human"]
    assert set(dur[0]["location"]) == {DESC_KEY, TIME_KEY} and dur[0]["location"][DESC_KEY]["char_start"] is not None
    assert dur[3]["approved_by"] == JARED
    # another course's objects: the rule's
    assert [f["approval"] for f in _of(_golden(ctx, "page-1"), "ceterms:estimatedDuration")] == ["rule", "rule"]
    assert main(["check", "--root", ctx.root.uri, "-c", CAT]) == 0
    capsys.readouterr()


# --- §6 not on the page -----------------------------------------------------------------------------------------------
def test_absent_claims_and_why_wrong_reasons_reach_the_golden_dataset(profile_studio):
    c, ctx = profile_studio
    rule = "course-prerequisite-description"
    rows = _rows(c, rule)
    assert {k: r["status"] for k, r in rows.items()} == {"page-0": "absent", "page-1": "absent", "page-2": "found",
                                                         "page-3": "no_match"}
    assert rows["page-0"]["css_path"].endswith("div:nth-of-type(1)")  # where the rule looked
    # the rule's claim, approved by its rule: an absent field
    [f] = _of(_golden(ctx, "page-0"), "ceterms:prerequisite>ceterms:description")
    assert (f["value"], f["absent"], f["approval"]) == (None, True, "rule")
    # an expert's ✓ on the claim makes it human-reviewed
    _verdict(c, JARED, rule, rows["page-0"], "correct")
    [f] = _of(_golden(ctx, "page-0"), "ceterms:prerequisite>ceterms:description")
    assert (f["absent"], f["approval"], f["approved_by"]) == (True, "human", JARED)
    # ✕ on a claim with no answer selected: nothing is published for it
    _verdict(c, JARED, rule, rows["page-1"], "wrong")
    assert _of(_golden(ctx, "page-1"), "ceterms:prerequisite>ceterms:description") == []
    # "Nothing found" ✓: the reviewer checked, it isn't on the page
    _verdict(c, ERIC, rule, rows["page-3"], "correct")
    [f] = _of(_golden(ctx, "page-3"), "ceterms:prerequisite>ceterms:description")
    assert (f["value"], f["absent"], f["approval"], f["approved_by"]) == (None, True, "human", ERIC)
    # ✕ with the reason "not on the page" on a found value: absent, the reviewer's answer
    out = _verdict(c, JARED, rule, rows["page-2"], "wrong", reasons=["not_on_page"])
    assert out["event"]["reasons"] == ["not_on_page"]
    assert _rows(c, rule)["page-2"]["verdict"]["reasons"] == ["not_on_page"]
    [f] = _of(_golden(ctx, "page-2"), "ceterms:prerequisite>ceterms:description")
    assert (f["value"], f["absent"], f["approval"]) == (None, True, "human")
    # reasons belong to a ✕ and name a known flag
    r = c.post(f"{B}/annotations", json={"type": "verdict", "author": JARED, "verdict": "correct",
                                         "reasons": ["not_on_page"], "target": {
                                             "kind": "match", "rule_id": rule, "occurrence_key": rows["page-2"]["key"]}})
    assert r.status_code == 400
    r = c.post(f"{B}/annotations", json={"type": "verdict", "author": JARED, "verdict": "wrong", "reasons": ["typo"],
                                         "target": {"kind": "match", "rule_id": rule,
                                                    "occurrence_key": rows["page-2"]["key"]}})
    assert r.status_code == 400


# --- §7 the reviewer's answer -----------------------------------------------------------------------------------------
def test_the_golden_dataset_publishes_the_reviewers_answer_da107a(profile_studio, capsys):
    c, ctx = profile_studio
    row = _rows(c, "course-description")["page-1"]
    assert row["value"] == DA107A[0] + "\n" + DA107A[1]
    # the rule drops the last line (as v8 does on AVC): Eric, an engineer, marks it ✕ and selects the whole text
    first = len(DA107A[0])
    expected = {"text": DA107A[0], "css_path": row["css_path"], "char_start": 0, "char_end": first,
                "segments": [{"text": DA107A[0], "css_path": row["css_path"], "char_start": 0, "char_end": first},
                             {"text": DA107A[1], "css_path": row["css_path"], "char_start": first + 1,
                              "char_end": first + 1 + len(DA107A[1])}]}
    expected["text"] = DA107A[0] + "\n" + DA107A[1] + " extra"  # a saved answer that differs from the rule's value
    _verdict(c, ERIC, "course-description", row, "wrong", expected=expected)
    [f] = _of(_golden(ctx, "page-1"), "ceterms:description")
    assert (f["value"], f["approval"], f["approved_by"]) == (expected["text"], "human", ERIC)
    assert f["location"]["char_start"] == 0
    # `out` segments are cut out of the answer
    row = _rows(c, "course-description")["page-1"]
    cut = {**expected, "segments": [{**expected["segments"][0], "polarity": "in"},
                                    {**expected["segments"][1], "polarity": "in"},
                                    {"text": "(R3)", "css_path": row["css_path"], "char_start": first - 4,
                                     "char_end": first, "polarity": "out"}]}
    _verdict(c, JARED, "course-description", row, "wrong", expected=cut, supersedes=row["verdict"]["annotation_id"])
    [f] = _of(_golden(ctx, "page-1"), "ceterms:description")
    assert f["value"] == DA107A[0][:-5] + "\n" + DA107A[1] and f["approved_by"] == JARED
    # a ✕ with an answer on a row where the rule found nothing: published too
    rows = _rows(c, "course-prerequisite-description")
    _verdict(c, JARED, "course-prerequisite-description", rows["page-3"], "wrong",
             expected={"text": "Consent of instructor", "css_path": "html > body:nth-of-type(1) > h1:nth-of-type(1)",
                       "char_start": 0, "char_end": 3})
    [f] = _of(_golden(ctx, "page-3"), "ceterms:prerequisite>ceterms:description")
    assert (f["value"], f["approval"]) == ("Consent of instructor", "human") and "absent" not in f
    assert main(["check", "--root", ctx.root.uri, "-c", CAT]) == 0
    capsys.readouterr()


def test_golden_parquet_and_page_files_hold_objects_and_absent_fields(profile_studio, capsys):
    import pyarrow.parquet as pq

    c, ctx = profile_studio
    for rid in ("course-code", "course-estimated-duration", "course-prerequisite-description"):
        assert c.post(f"{B}/annotations", json={"type": "approve", "author": JARED,
                                                "target": {"kind": "rule", "rule_id": rid}}).status_code == 200
    ctx = Ctx(ctx.root, CAT)
    doc = golden.publish(ctx, golden.default_target(ctx), "test")
    assert doc["publication"] == "ruleset-v2"  # properties apply made ruleset v2
    gold = ctx.root.base.parent / "golden"
    page = json.loads((gold / golden.version_prefix(ctx, 2) / "page-0" / "page-0.json").read_text())
    fields = page[0]["fields"]
    assert [f["value"] for f in _of(fields, "ceterms:estimatedDuration")] == ACCT199
    [absent] = _of(fields, "ceterms:prerequisite>ceterms:description")
    assert absent["value"] is None and absent["absent"] is True
    vers = golden.versions(Ctx(ctx.root, CAT))[2]
    t = pq.read_table(ctx.root.local_path(f"{vers['path']}/golden.parquet", mutable=True)).to_pylist()
    dur = [r for r in t if r["stem"] == "page-0" and r["ctdl_property"] == "ceterms:estimatedDuration"]
    assert [json.loads(r["value"]) for r in dur] == ACCT199 and dur[0]["location"]["char_start"] is not None
    assert main(["check", "--root", ctx.root.uri, "-c", CAT]) == 0
    capsys.readouterr()
