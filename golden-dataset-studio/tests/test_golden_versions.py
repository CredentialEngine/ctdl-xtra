"""Golden dataset versions and human-reviewed values (Evals spec §4.1, §4.3), on a three-page catalog: every
publication writes the whole version (folder kept per ruleset, latest location replaced, golden.parquet); an
expert's verdict rewrites that page's file and asks for a score; an engineer's ✓ waits for an expert; the backfill
of publications made before versions."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from test_crawls import FIRST, _crawl

from golden_datasets import crawls, golden, layout
from golden_datasets.cli import main
from golden_datasets.context import Ctx
from golden_datasets.storage import LocalRoot

CAT = "cuesta-curriqunet-com-catalog-iq-27137"
B = f"/api/catalogs/{CAT}"
JARED, ERIC = "Jared Diener", "Eric Riddoch"  # sme, engineer (the default profiles)
RULES = json.loads(json.dumps(FIRST))
RULES["rules"][3]["definition"]["selector"] = "h1"  # the name: "C 0" (the content root has no <title>)


@pytest.fixture
def studio(tmp_path, capsys, monkeypatch):
    from fastapi.testclient import TestClient

    from golden_datasets.server.app import create_app

    monkeypatch.setenv("GOLDEN_DATASETS_GOLDEN_ROOT", str(tmp_path / "golden"))  # never the dev folder from the .env
    src, dst = LocalRoot(tmp_path / "xtra-cli-output"), tmp_path / "root"
    _crawl(src.base, CAT, "2026-10-21T10-00-00Z", "https://cuesta.curriqunet.com/catalog/iq/27137/", 3)
    dst.mkdir()
    crawls.add_catalog(LocalRoot(dst), src, CAT, log=lambda *a, **k: None)
    draft = tmp_path / "first.json"
    draft.write_text(json.dumps(RULES))
    assert main(["rule", "publish", "--root", str(dst), "--catalog", CAT, str(draft), "--note", "first"]) == 0
    capsys.readouterr()
    return TestClient(create_app(str(dst))), Ctx(LocalRoot(dst), CAT), tmp_path / "golden"


def _rows(c, rule: str) -> dict[str, dict]:
    return {r["page_stem"]: r for r in c.get(f"{B}/rules/{rule}/rows").json()["rows"]}


def _mark(c, author: str, rule: str, row: dict, verdict: str, supersedes: str | None = None) -> dict:
    r = c.post(f"{B}/annotations", json={"type": "verdict", "author": author, "verdict": verdict,
                                         "supersedes": supersedes, "target": {"kind": "match", "rule_id": rule,
                                                                              "occurrence_key": row["key"]}})
    assert r.status_code == 200, r.text
    return r.json()


def _page(gold, ctx: Ctx, stem: str, version: int | None = None, tree: str = golden.RULE_MATCHED) -> list[dict] | None:
    prefix = golden.version_prefix(ctx, version, tree) if version else golden.latest_prefix(ctx)
    path = gold / prefix / stem / f"{stem}.json"
    return json.loads(path.read_text()) if path.exists() else None


def test_an_engineers_check_waits_for_an_expert_whose_check_is_published_at_once(studio):
    c, ctx, gold = studio
    row = _rows(c, "course-name")["page-0"]
    out = _mark(c, ERIC, "course-name", row, "correct")
    assert out["event"]["author_role"] == "engineer" and out["published"] is None  # no golden dataset for it
    row = _rows(c, "course-name")["page-0"]
    assert (row["state"], row["engineer_checked"], row["human_reviewed"]) == ("correct", True, False)
    assert row["verdict"]["author_role"] == "engineer"

    out = _mark(c, JARED, "course-name", row, "correct", supersedes=row["verdict"]["annotation_id"])
    assert out["event"]["author_role"] == "sme"
    assert out["published"]["created"] and out["published"]["publication"] == "ruleset-v1"  # the first review creates it
    row = _rows(c, "course-name")["page-0"]
    assert (row["engineer_checked"], row["human_reviewed"]) == (False, True)
    for v, tree in ((None, None), (1, golden.RULE_MATCHED), (1, golden.HUMAN_REVIEWED)):  # latest, both trees
        [rec] = _page(gold, ctx, "page-0", v, tree)
        assert rec["fields"] == [{**rec["fields"][0], "property": "Learning Opportunity Name", "value": "C 0",
                                  "approval": "human", "approved_by": JARED}]
    assert (gold / golden.latest_prefix(ctx) / "page-0" / "page-0.html").exists()
    assert not (gold / golden.version_prefix(ctx, 1) / "page-0" / "page-0.html").exists()  # version trees: JSON only
    pending = ctx.root.read_json(layout.pending_score(CAT, ctx.crawl))
    due = datetime.strptime(pending["due_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    assert 280 < (due - datetime.now(UTC)).total_seconds() <= 300 and "course-name" in pending["reason"]

    # an engineer's later ✓ (beside the expert's) leaves the expert's standing; undoing the expert's ✓ takes it out
    out = _mark(c, ERIC, "course-name", row, "correct")
    assert out["published"] is None and _rows(c, "course-name")["page-0"]["human_reviewed"]
    row = _rows(c, "course-name")["page-0"]
    ann = c.get(f"{B}/annotations", params={"rule": "course-name"}).json()
    jared = next(e for e in ann if e["author"] == JARED)
    out = _mark(c, JARED, "course-name", row, "question", supersedes=jared["annotation_id"])
    assert len(out["published"]["files"]) == 3  # no values left: the page's file goes from all three places
    assert _page(gold, ctx, "page-0") is None and _page(gold, ctx, "page-0", 1) is None
    assert _page(gold, ctx, "page-0", 1, golden.HUMAN_REVIEWED) is None
    assert not (gold / golden.latest_prefix(ctx) / "page-0" / "page-0.html").exists()


def test_an_engineers_check_after_an_experts_leaves_it_human_reviewed(studio):
    """The UI sends an engineer's ✓ as superseding the row's verdict (the expert's): the expert's still stands."""
    c, ctx, gold = studio
    row = _rows(c, "course-name")["page-1"]
    _mark(c, JARED, "course-name", row, "correct")
    row = _rows(c, "course-name")["page-1"]
    _mark(c, ERIC, "course-name", row, "correct", supersedes=row["verdict"]["annotation_id"])
    row = _rows(c, "course-name")["page-1"]
    assert (row["human_reviewed"], row["engineer_checked"], row["human"]["author"]) == (True, False, JARED)
    assert row["checked"]["author"] == ERIC
    [rec] = _page(gold, ctx, "page-1")
    assert rec["fields"][0]["approval"] == "human"  # its page file keeps the expert's value
    # an expert's later verdict wins over an engineer's: Confirm (an expert's ✓) supersedes an engineer's check
    row2 = _rows(c, "course-name")["page-2"]
    _mark(c, ERIC, "course-name", row2, "correct")
    row2 = _rows(c, "course-name")["page-2"]
    _mark(c, JARED, "course-name", row2, "correct", supersedes=row2["verdict"]["annotation_id"])
    row2 = _rows(c, "course-name")["page-2"]
    assert (row2["human_reviewed"], row2["engineer_checked"], row2["checked"]["author"]) == (True, False, ERIC)


def test_annotated_by_filters_rows_courses_and_the_rule_list(studio):
    c, _, _ = studio
    rows = _rows(c, "course-name")
    _mark(c, ERIC, "course-name", rows["page-0"], "correct")
    _mark(c, JARED, "course-name", rows["page-1"], "wrong")
    c.post(f"{B}/annotations", json={"type": "comment", "author": JARED, "note": "hm", "target": {
        "kind": "match", "rule_id": "course-code", "occurrence_key": _rows(c, "course-code")["page-2"]["key"]}})
    a = c.get(f"{B}/annotators").json()
    people = {p["name"]: (p["role"], p["values"]) for p in a["people"]}
    assert people[JARED] == ("sme", 2) and people[ERIC] == ("engineer", 1) and people["Cadence Calixto"] == ("sme", 0)
    assert [p["name"] for p in a["people"]][:2] == [JARED, "Cadence Calixto"]  # experts first, most values first
    assert a["waiting"] == 1 and a["rules"] is None
    assert c.get(f"{B}/annotators", params={"by": "waiting"}).json()["rules"]["course-name"] == 1
    assert c.get(f"{B}/annotators", params={"by": JARED, "verdict": "note"}).json()["rules"] == {
        "course-page": 0, "locator-course-page": 0, "course-code": 1, "course-name": 0}

    def keys(**params) -> list[str]:
        return [r["page_stem"] for r in c.get(f"{B}/rules/course-name/rows", params=params).json()["rows"]]
    assert keys(by="waiting") == ["page-0"]
    assert keys(by=JARED) == ["page-1"] and keys(by=JARED, verdict="correct") == []
    assert keys(verdict="wrong") == ["page-1"] and sorted(keys(by="nobody")) == ["page-2"]
    courses = lambda **p: sorted(x["course_key"] for x in c.get(f"{B}/courses", params=p).json())  # noqa: E731
    assert len(courses(by=JARED)) == 2 and len(courses(by="waiting")) == 1 and len(courses(by="nobody")) == 0
    ck = courses(by="waiting")[0]
    fields = c.get(f"{B}/courses/{ck}").json()["occurrences"][0]["fields"]
    assert next(f for f in fields if f["rule_id"] == "course-name")["annotators"][ERIC]["kinds"] == ["correct"]


def test_an_engineers_cross_still_marks_the_rule_needs_work(studio):
    c, _, _ = studio
    out = _mark(c, ERIC, "course-code", _rows(c, "course-code")["page-1"], "wrong")
    assert out["rule"]["status"] == "needs work"


def test_events_without_a_role_take_the_authors_role_today(studio):
    c, ctx, _ = studio
    c.post("/api/profiles", json={"name": "Eric Riddoch", "role": "sme"})
    row = _rows(c, "course-name")["page-2"]
    out = _mark(c, "Eric", "course-name", row, "correct")  # first-name author: his full name's profile
    assert out["event"]["author_role"] == "sme"
    from golden_datasets.review import Review

    rv = Review.__new__(Review)
    rv.roles = {"Eric Riddoch": "engineer"}
    assert rv.role({"author": "Eric"}) == "engineer"  # an old event: the role he has now
    assert rv.role({"author": "Eric", "author_role": "sme"}) == "sme"  # a new event: the role it was written with
    assert c.post(f"{B}/annotations", json={"type": "comment", "author": "X", "author_role": "boss", "note": "n",
                                            "target": {"kind": "rule", "rule_id": "course-name"}}).status_code == 400


def test_comparisons_pass_through_the_log(studio):
    c, _, _ = studio
    row = _rows(c, "course-name")["page-1"]
    cw = {"kind": "extract", "score": "sc-0001", "value": "Course one"}
    r = c.post(f"{B}/annotations", json={"type": "comment", "author": JARED, "note": "xtra stops early",
                                         "compared_with": cw, "target": {"kind": "match", "rule_id": "course-name",
                                                                         "occurrence_key": row["key"]}}).json()
    assert r["event"]["compared_with"] == cw
    assert _rows(c, "course-name")["page-1"]["comments"][0]["compared_with"] == cw


def test_publishing_writes_the_whole_version_and_replaces_the_latest(studio, tmp_path, capsys):
    c, ctx, gold = studio
    _mark(c, JARED, "course-name", _rows(c, "course-name")["page-0"], "correct")
    c.post(f"{B}/annotations", json={"type": "approve", "author": JARED,
                                     "target": {"kind": "rule", "rule_id": "course-code"}})
    doc = golden.publish(ctx, str(gold), "test", properties=["Coded Notation"])
    assert (doc["publication"], doc["properties"], doc["latest"]) == ("ruleset-v1", ["Coded Notation"], True)
    rec = _page(gold, ctx, "page-0", 1)[0]
    assert [f["property"] for f in rec["fields"]] == ["Coded Notation", "Learning Opportunity Name"]
    assert [f["approval"] for f in rec["fields"]] == ["rule", "human"] and rec["approval"] == "mixed"
    [hr] = _page(gold, ctx, "page-0", 1, golden.HUMAN_REVIEWED)  # only the human-reviewed value, only its page
    assert [f["property"] for f in hr["fields"]] == ["Learning Opportunity Name"] and hr["approval"] == "human"
    assert _page(gold, ctx, "page-1", 1, golden.HUMAN_REVIEWED) is None
    assert _page(gold, ctx, "page-1") == _page(gold, ctx, "page-1", 1)
    assert not list((gold / "catalogs").rglob("*.html"))  # the HTML is only at the latest location
    assert doc["trees"] == {golden.RULE_MATCHED: {"prefix": golden.version_prefix(ctx, 1), "pages": 3},
                            golden.HUMAN_REVIEWED: {"prefix": golden.version_prefix(ctx, 1, golden.HUMAN_REVIEWED),
                                                    "pages": 1}}
    gdir = layout.golden_dir(CAT, ctx.crawl, "ruleset-v1")
    rows = pq.read_table(ctx.root.local_path(f"{gdir}/golden.parquet")).to_pylist()
    assert len(rows) == 4 and {r["stem"] for r in rows} == {"page-0", "page-1", "page-2"}
    assert {(r["property"], r["approval"]) for r in rows if r["stem"] == "page-0"} == {
        ("Coded Notation", "rule"), ("Learning Opportunity Name", "human")}
    assert rows[0]["location"]["css_path"] and rows[0]["catalog"] == CAT
    assert ctx.root.exists(f"{gdir}/lineage.parquet") and ctx.root.exists(f"{gdir}/publication.json")

    # ruleset v2: its own version, written whole, with v1's columns too (columns only grow; values from v2's own
    # extraction); v1's folder stays; the latest location is v2's, not merged
    draft = tmp_path / "v2.json"
    rules = json.loads(json.dumps(RULES))
    rules["rules"][3]["definition"] |= {"rule_type": "css+regex", "regex": "^C (\\d+)", "group": 1}  # the number only
    draft.write_text(json.dumps(rules))
    assert main(["rule", "publish", "--root", ctx.root.uri, "--catalog", CAT, str(draft), "--note", "v2", "--force"]) == 0
    capsys.readouterr()
    rv2 = golden.LOADER.review(Ctx(ctx.root, CAT))
    assert golden.approval_publishes(rv2, "course-name")["after"] == ["Coded Notation", "Learning Opportunity Name"]
    v2 = golden.publish(Ctx(ctx.root, CAT), str(gold), "test", allow_unapproved=True,
                        properties=["Learning Opportunity Name"])
    assert v2["publication"] == "ruleset-v2" and v2["properties"] == ["Coded Notation", "Learning Opportunity Name"]
    latest = _page(gold, ctx, "page-1")[0]
    assert [(f["property"], f["value"]) for f in latest["fields"]] == [("Coded Notation", "C 1"),
                                                                        ("Learning Opportunity Name", "1")]
    assert _page(gold, ctx, "page-1", 1)[0]["fields"][0]["property"] == "Coded Notation"
    assert {g["publication"] for g in Ctx(ctx.root, CAT).crawl_entry()["golden"]} == {"ruleset-v1", "ruleset-v2"}
    assert main(["check", "--root", ctx.root.uri, "--catalog", CAT]) == 0
    # a stray file in a tree is caught; writing the versions again in the current layout removes it
    stray = gold / golden.version_prefix(ctx, 1, golden.HUMAN_REVIEWED) / "page-2" / "page-2.json"
    stray.parent.mkdir(parents=True)
    stray.write_text(json.dumps(_page(gold, ctx, "page-2", 1)))
    assert main(["check", "--root", ctx.root.uri, "--catalog", CAT]) == 1
    assert main(["golden", "backfill", "--root", ctx.root.uri, "--catalog", CAT, "--to", str(gold), "--again"]) == 0
    out = capsys.readouterr().out
    assert "ruleset-v2 (Coded Notation, Learning Opportunity Name) written again" in out and not stray.exists()
    assert _page(gold, ctx, "page-1")[0]["fields"][1]["value"] == "1"  # v2 is still the latest


def test_backfill_rebuilds_old_publications_as_versions(studio, capsys):
    c, ctx, gold = studio
    from golden_datasets import manifest

    pub = "pub-2026-10-27-cuesta-rs-0001"
    gdir = layout.golden_dir(CAT, ctx.crawl, pub)
    ctx.root.write_bytes(f"{gdir}/lineage.parquet", _parquet({"golden_id": ["C0", "C1"],
                                                              "property": ["Coded Notation", "Coded Notation"]}))
    ctx.root.write_json(f"{gdir}/publication.json", {
        "publication": pub, "extraction": "rs-0001", "ruleset_version": 1, "published_at": "2026-10-27T01:02:29Z",
        "published_by": "Eric via the Studio UI", "to": "azure://https://x.blob.core.windows.net/xtra-golden-sets"})

    def change(m):
        k = manifest.crawl_entry(manifest.catalog_entry(m, CAT), ctx.crawl)
        k["golden"] = [{"publication": pub, "path": gdir, "to": "azure://…"}]

    manifest.update(ctx.root, change)
    assert main(["golden", "backfill", "--root", ctx.root.uri, "--catalog", CAT, "--to", str(gold)]) == 0
    out = capsys.readouterr().out
    assert "ruleset-v1 (Coded Notation) from pub-2026-10-27-cuesta-rs-0001: 3 pages" in out and " 0 bad" in out
    fresh = Ctx(ctx.root, CAT)
    assert [g["publication"] for g in fresh.crawl_entry()["golden"]] == ["ruleset-v1"]
    doc = fresh.read_json(f"{layout.golden_dir(CAT, ctx.crawl, 'ruleset-v1')}/publication.json", immutable=False)
    assert doc["published_at"] == "2026-10-27T01:02:29Z" and doc["backfilled_from"] == [pub]
    assert _page(gold, ctx, "page-2", 1)[0]["fields"][0]["value"] == "C 2"
    assert main(["golden", "backfill", "--root", ctx.root.uri, "--catalog", CAT, "--to", str(gold)]) == 0
    assert "nothing to backfill" in capsys.readouterr().out


def test_the_default_golden_root_is_local_for_a_local_studio(studio, monkeypatch):
    _, ctx, gold = studio
    monkeypatch.delenv("GOLDEN_DATASETS_GOLDEN_ROOT", raising=False)
    assert golden.default_target(ctx) == str(gold)
    monkeypatch.setenv("GOLDEN_DATASETS_GOLDEN_ROOT", "/elsewhere")
    assert golden.default_target(ctx) == "/elsewhere"


def _parquet(cols: dict) -> bytes:
    import io

    buf = io.BytesIO()
    pq.write_table(pa.table(cols), buf)
    return buf.getvalue()

