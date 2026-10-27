"""M1 on AVC, from the read-only mirror into a fresh local root: sync --link, init, import-v2, extract, check.
Then the prototype's course-description v2 is published and extracted incrementally (rs-0002).

Marked `slow` (reads ~/review-ui-v3-data/xtra-cli-output; never writes to it).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from golden_datasets import check, engine, extract, rulesets
from golden_datasets.context import Ctx
from golden_datasets.import_v2 import import_v2
from golden_datasets.query import connect
from golden_datasets.storage import LocalRoot
from golden_datasets.sync import sync_catalog

MIRROR = Path.home() / "review-ui-v3-data" / "xtra-cli-output"
AVC = "avc-elumenapp-com-catalog-2026-27-welcome"
DESCRIPTION_V2_REGEX = (r"\A\s*(?:(?i:pre-?requisites?|co-?requisites?)\s*:[^\n]*?(?:\.[ \t]+(?=[A-Z(])|\n|\Z)\s*)*"
                        r"(\S[\s\S]*?)\s*\Z")


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    if not (MIRROR / AVC).exists():
        pytest.skip("local mirror not available")
    root = LocalRoot(tmp_path_factory.mktemp("avc") / "root")
    sync_catalog(LocalRoot(MIRROR), root, AVC, None, "link", False, False)
    c = Ctx(root, "avc")
    extract.init(c)
    out = import_v2(c, str(MIRROR), None, log=lambda *a: None)
    c.import_result = out
    return c


@pytest.mark.slow
def test_m1_counts_match_the_prototype(ctx):
    out = ctx.import_result
    assert (out["annotations"], out["correct"], out["wrong (reject + missing joined)"], out["page rule correct"],
            out["page rule wrong"], out["question (page flag)"], out["approve (constant/URL rule)"]) == \
        (153, 107, 5, 21, 7, 8, 5)
    con = connect(ctx)
    counts = con.execute("""SELECT (SELECT count(*) FROM pages), (SELECT count(*) FROM page_labels),
        (SELECT count(*) FROM occurrences), (SELECT count(*) FROM raw_matches)""").fetchone()
    assert counts == (1467, 4401, 3813, 19500)
    sig = dict(con.execute("SELECT signal, count(*) FROM signals GROUP BY ALL").fetchall())
    assert {k: sig[k] for k in ("contains-label-text", "duplicate-value", "unclassified-page-with-codes",
                                "duplicate-occurrence", "length-outlier", "shape-outlier", "uncovered-code")} == \
        {"contains-label-text": 547, "duplicate-value": 397, "unclassified-page-with-codes": 129,
         "duplicate-occurrence": 114, "length-outlier": 88, "shape-outlier": 33, "uncovered-code": 18}
    # `sql` answers "every value of rule X"
    n = con.execute("SELECT count(*) FROM matches WHERE rule_id = 'course-description' AND status = 'found'").fetchone()[0]
    assert n == 1062


@pytest.mark.slow
def test_incremental_extract_of_description_v2(ctx):
    rs, rules = ctx.ruleset_rules(1)
    draft = {rid: {k: v for k, v in r.items()} for rid, r in rules.items()}
    draft["course-description"] = {**draft["course-description"],
                                   "definition": {**rules["course-description"]["definition"],
                                                  "regex": DESCRIPTION_V2_REGEX, "group": 1}}
    new_rules = rulesets.plan_versions(ctx, draft, rules)
    assert new_rules["course-description"]["version"] == 2 and new_rules["course-code"]["version"] == 1
    doc = rulesets.publish(ctx, new_rules, rs["settings"], "course-description v2", "test")
    assert doc["version"] == 2 and doc["changed_rules"] == ["course-description"]
    meta = extract.extract(ctx, 2)
    assert meta["extraction"] == "rs-0002" and meta["parent_extraction"] == "rs-0001"
    assert meta["rerun_rules"] == ["course-description"] and meta["rerun_pages"] == 1062
    assert len(meta["copied_rules"]) == 16
    con = connect(ctx)
    changed = con.execute("""SELECT count(*) FROM raw_matches a JOIN raw_matches b USING (rule_id, occurrence_key)
        WHERE a.extraction = 'rs-0001' AND b.extraction = 'rs-0002' AND a.rule_id = 'course-description'
        AND a.value IS DISTINCT FROM b.value""").fetchone()[0]
    assert changed == 278
    label = con.execute("""SELECT count(*) FROM signals WHERE extraction = 'rs-0002'
        AND signal = 'contains-label-text'""").fetchone()[0]
    assert label == 273
    start, end, value, rel, occ = con.execute("""SELECT char_start, char_end, value, css_path, occurrence_key
        FROM raw_matches WHERE extraction = 'rs-0002' AND rule_id = 'course-description'
        AND occurrence_key LIKE '%course-geog222-%'""").fetchone()
    # Offsets are DOM textContent positions in the element the path names (spec §4.2): the prerequisite is skipped.
    stem, occ_path = occ.split("@", 1)
    doc = engine.parse(ctx.page_path(stem).read_bytes())
    text = engine.text_content(engine.select_one(doc, f"{occ_path} > {rel}", True))
    assert start > 60 and text[start:end] == value and value.startswith("This course provides a general survey")
    assert rulesets.publish(ctx, new_rules, rs["settings"], "again", "test") is None  # unchanged hash: no-op


@pytest.mark.slow
def test_check_passes(ctx):
    results = check.run(ctx)
    failed = [r for r in results if r[3] > 0 and r[0] not in ("page_assets", "assets")]
    assert not failed, failed


@pytest.mark.slow
def test_api_rules_rows_compare_and_verdict(ctx):
    from fastapi.testclient import TestClient

    from golden_datasets.server.app import create_app

    c = TestClient(create_app(ctx.root.uri))
    cats = {x["name"]: x for x in c.get("/api/catalogs").json()}
    assert (cats["AVC"]["pages"], cats["AVC"]["rules_total"]) == (1467, 17)
    rules = c.get("/api/catalogs/avc/rules").json()
    desc = next(r for g in rules["groups"] for r in g["rules"] if r["rule_id"] == "course-description")
    assert desc["version"] == 2 and desc["status"] == "in review"  # v2 fixed all 5 wrong rows
    rows = c.get("/api/catalogs/avc/rules/course-description/rows?limit=5").json()
    assert rows["total"] == 1062 and {r["state"] for r in rows["rows"]} == {"fixed"}
    cmp = c.get("/api/catalogs/avc/compare").json()
    assert (cmp["a"], cmp["b"], cmp["records_changed"]) == (1, 2, 278)
    assert cmp["totals"] == {"fixed": 5, "still_wrong": 0, "newly_wrong": 0, "unchanged": 9}
    row = rows["rows"][0]
    r = c.post("/api/catalogs/avc/annotations", json={
        "type": "verdict", "author": "Test", "verdict": "correct",
        "target": {"kind": "match", "rule_id": "course-description", "occurrence_key": row["occurrence_key"]}})
    assert r.status_code == 200 and r.json()["event"]["target"]["value_seen"] == row["value"]
    again = c.get(f"/api/catalogs/avc/rules/course-description/rows?q={row['course_key']}").json()
    mine = next(x for x in again["rows"] if x["key"] == row["key"])
    assert mine["state"] == "correct" and mine["verdict"]["author"] == "Test"
    approve = c.post("/api/catalogs/avc/annotations", json={
        "type": "approve", "author": "Test", "target": {"kind": "rule", "rule_id": "program-page-with-courses"}})
    assert approve.status_code == 409  # 7 wrong verdicts: Approve is refused


@pytest.mark.slow
def test_api_strata_on_rows_and_compare_records(ctx):
    from fastapi.testclient import TestClient

    from golden_datasets.server.app import create_app

    c = TestClient(create_app(ctx.root.uri))
    url = "/api/catalogs/avc/rules/course-description/rows"
    first = c.get(url, params={"limit": 5}).json()
    sm = first["sample"]
    assert sm["total"] == sm["listed"] == 1062 and sm["order"] == "review"
    by_id = {h["id"]: h for h in sm["histograms"]}
    assert {"length", "paragraphs", "lead", "subject", "url", "signals", "review"} <= set(by_id)
    assert by_id["url"]["uniform"]
    bucket = by_id["length"]["buckets"][0]
    filtered = c.get(url, params={"limit": 5, "f": f"length:{bucket['id']}"}).json()
    assert filtered["total"] == bucket["count"] and filtered["rows"][0]["tags"][0]["bucket"] == bucket["id"]
    auto = c.get(url, params={"limit": 5, "order": "auto"}).json()
    assert auto["total"] == 1062 and auto["sample"]["cross"] and len(auto["rows"][0]["tags"]) == len(auto["sample"]["cross"])
    assert c.get(url, params={"offset": 5, "limit": 5}).json()["sample"] is None  # only the first page has it
    assert c.get(url, params={"order": "nope"}).status_code == 422
    # a comment on one field puts the course first in another field's list, tagged with where it was reviewed
    some = c.get("/api/catalogs/avc/rules/course-name/rows", params={"limit": 400}).json()["rows"]
    target = next(r for r in reversed(some) if r["state"] is None and not r["comments"])
    desc = next(r for r in c.get(url, params={"q": target["course_key"]}).json()["rows"]
                if r["course_key"] == target["course_key"])
    assert c.post("/api/catalogs/avc/annotations", json={
        "type": "comment", "author": "Test", "note": "looks odd",
        "target": {"kind": "match", "rule_id": "course-description", "occurrence_key": desc["occurrence_key"]}}).status_code == 200
    first = c.get("/api/catalogs/avc/rules/course-name/rows", params={"limit": 50, "prior": "true"}).json()
    n = first["sample"]["elsewhere"]
    lead = first["rows"][:n]
    assert n >= 1 and all(r["tags"][-1]["dim"] == "elsewhere" for r in lead)
    mine = next(r for r in lead if r["course_key"] == target["course_key"])
    assert mine["tags"][-1] == {"dim": "elsewhere", "label": "Reviewed in", "bucket": "Description"}
    assert not any(t["dim"] == "elsewhere" for r in first["rows"][n:] for t in r["tags"])

    cmp = c.get("/api/catalogs/avc/compare").json()
    if cmp["a"] == cmp["b"]:
        return
    rec = c.get("/api/catalogs/avc/compare/records", params={"a": cmp["a"], "b": cmp["b"], "limit": 500}).json()
    others = sum(r["sample_total"] for r in cmp["rules"])
    assert rec["total"] == rec["all"] == others == len(rec["records"])
    page2 = c.get("/api/catalogs/avc/compare/records", params={"a": cmp["a"], "b": cmp["b"], "offset": 50}).json()
    assert page2["limit"] == 50 and page2["records"][0]["key"] == rec["records"][50]["key"]
    assert rec["sample"]["listed"] == others and rec["sample"]["order"] == "shuffle"


@pytest.mark.slow
def test_dropping_rules_leaves_nothing_of_them(ctx):
    """The learning-program rules dropped from a ruleset (out of scope): the next extraction, copied from its parent,
    keeps no labels, occurrences, matches or signals of theirs, and every key still holds."""
    drop = {"program-page", "program-page-with-courses", "locator-program-requirement",
            "stub-code", "stub-external-id", "stub-learning-type", "stub-name"}
    rs, rules = ctx.ruleset_rules(ctx.latest_ruleset())
    doc = rulesets.publish(ctx, {k: r for k, r in rules.items() if k not in drop}, rs["settings"], "drop programs", "t")
    meta = extract.extract(ctx, doc["version"])
    ext = meta["extraction"]
    ids = {
        "page_labels": set(ctx.table(ext, "page_labels").column("rule_id").to_pylist()),
        "occurrences": set(ctx.table(ext, "occurrences").column("locator_rule_id").to_pylist()),
        "matches": set(ctx.table(ext, "matches").column("rule_id").to_pylist()),
        "signals": set(ctx.table(ext, "signals").column("rule_id").to_pylist()) - {None},
    }
    for name, seen in ids.items():
        assert not seen & drop, (name, seen & drop)
    assert ids["occurrences"] == {"locator-course-page"} and "course-page" in ids["page_labels"]
    failed = [r for r in check.run(ctx) if r[3] > 0 and r[0] not in ("page_assets", "assets")]
    assert not failed, failed


@pytest.mark.slow
def test_rule_and_ruleset_comments(ctx):
    """Comments on a whole rule and on the ruleset: stored, listed for the sidebar, kept off the rows, in the prompt."""
    from fastapi.testclient import TestClient

    from golden_datasets.prompt import build_prompt
    from golden_datasets.server.app import create_app

    c = TestClient(create_app(ctx.root.uri))
    post = lambda body: c.post("/api/catalogs/avc/annotations", json={"type": "comment", "author": "Eric", **body})  # noqa: E731
    r = post({"note": "Is a separate Advisory rule worth it?", "topic": "question-rule",
              "target": {"kind": "rule", "rule_id": "course-description"}})
    assert r.status_code == 200 and r.json()["rule"]["rule_comments"] == 1
    assert post({"note": "Add a rule for prerequisites", "topic": "new-rule", "target": {"kind": "ruleset"}}).status_code == 200
    assert post({"note": "x", "topic": "nope", "target": {"kind": "ruleset"}}).status_code == 400
    assert c.post("/api/catalogs/avc/annotations", json={"type": "verdict", "verdict": "correct", "author": "E",
                                                          "target": {"kind": "ruleset"}}).status_code == 400
    d = c.get("/api/catalogs/avc/discussion").json()
    assert [e["note"] for e in d["ruleset"]] == ["Add a rule for prerequisites"] and d["ruleset"][0]["topic"] == "new-rule"
    assert d["rules"]["course-description"][0]["topic"] == "question-rule"
    rows = c.get("/api/catalogs/avc/rules/course-description/rows", params={"limit": 2000}).json()["rows"]
    assert not any(cm.get("note") == "Is a separate Advisory rule worth it?" for r in rows for cm in r["comments"])
    text = build_prompt(Ctx(ctx.root, "avc"), "course-description")["text"]
    assert "### Comments on this rule (1)" in text and "questions this rule" in text
    assert "Someone questions whether this rule should exist" in text
    assert "## Comments on the ruleset" in text and "suggests a new rule" in text
