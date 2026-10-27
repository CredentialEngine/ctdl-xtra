"""Review API (W4): what the Rules and Records tabs need beyond the W3 read model.

The fast tests cover pure helpers. The `slow` ones run the API on a synced copy of the demo root
(`.data/root-demo`: AVC with ruleset v1 → v2 published), never writing to it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from golden_datasets.server.routes_review import _find_row, rule_title

DEMO = Path(__file__).resolve().parents[1] / ".data" / "root-demo"
AVC = "avc-elumenapp-com-catalog-2026-27-welcome"
GEOG_PROGRAM = "avc-elumenapp-com-catalog-2026-27-program-computer-engineering-as-fall-2026-5a1e6e1354"


def test_find_row_by_key_course_or_page():
    ordered = [({"key": "p1@a", "occurrence_key": "p1@a", "course_key": "GEOG222", "page_stem": "p1"}, None),
               ({"key": "p2@b", "occurrence_key": "p2@b", "course_key": "MATH150", "page_stem": "p2"}, None)]
    assert _find_row(ordered, "p2@b") == 1
    assert _find_row(ordered, "MATH150") == 1
    assert _find_row(ordered, "geog 222") == 0
    assert _find_row(ordered, "p2") == 1
    assert _find_row(ordered, "nope") is None


def test_plain_subtitles_for_page_rules_and_locators():
    r = {"rule_id": "locator-program-requirement", "kind": "locator", "what": "long prose", "definition": {}}
    assert rule_title(r) == ("One course per requirement line", "Where each course starts and ends on a program page")
    r = {"rule_id": "page-x", "kind": "page", "what": "Pages at /x", "definition": {}}
    assert rule_title(r) == ("page-x", "Pages at /x")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    if not (DEMO / AVC).exists():
        pytest.skip("demo root not available (.data/root-demo)")
    from fastapi.testclient import TestClient

    from golden_datasets.server.app import create_app
    from golden_datasets.storage import LocalRoot
    from golden_datasets.sync import sync_catalog

    root = LocalRoot(tmp_path_factory.mktemp("w4") / "root")
    sync_catalog(LocalRoot(DEMO), root, AVC, None, "link", False, False)
    c = TestClient(create_app(root.uri))
    c.root_path_ = Path(root.uri.removeprefix("file://"))
    return c


B = "/api/catalogs/avc"


@pytest.mark.slow
def test_rows_focus_extends_the_page(client):
    r = client.get(f"{B}/rules/course-description/rows", params={"limit": 5, "focus": "GEOG222"}).json()
    i = r["focus_index"]
    assert i is not None and r["rows"][i]["course_key"] == "GEOG222"
    assert r["rows"][i]["state"] == "fixed"  # ruleset v2 fixed Jared's wrong verdict
    deep = client.get(f"{B}/rules/course-description/rows", params={"limit": 5}).json()["total"]
    assert deep == 1062
    # a row far down the order is still reachable
    last = client.get(f"{B}/rules/course-description/rows", params={"offset": 1061, "limit": 1}).json()["rows"][0]
    r = client.get(f"{B}/rules/course-description/rows", params={"limit": 5, "focus": last["key"]}).json()
    assert r["focus_index"] == 1061 and len(r["rows"]) == 1062


@pytest.mark.slow
def test_rows_carry_other_pages_and_page_questions(client):
    r = client.get(f"{B}/rules/course-description/rows", params={"focus": "GEOG222", "limit": 5}).json()
    row = r["rows"][r["focus_index"]]
    assert any("geographic-information-systems" in p["page_stem"] for p in row["other_pages"])
    pr = client.get(f"{B}/rules/program-page-with-courses/rows", params={"focus": GEOG_PROGRAM}).json()
    row = pr["rows"][pr["focus_index"]]
    assert row["page_questions"] and row["page_questions"][0]["verdict"] == "question"
    rules = client.get(f"{B}/rules").json()
    pwc = next(x for x in rules["groups"][0]["rules"] if x["rule_id"] == "program-page-with-courses")
    assert pwc["page_questions"] >= 7


@pytest.mark.slow
def test_overlay_for_a_page_rule_outlines_its_locators_blocks(client):
    ov = client.get(f"{B}/pages/{GEOG_PROGRAM}/overlay", params={"rule": "program-page-with-courses"}).json()
    assert len(ov["blocks"]) > 5 and ov["marks"] == []


@pytest.mark.slow
def test_page_search_and_courses_flags(client):
    hits = client.get(f"{B}/page-search", params={"q": "geographic", "rule": "course-page"}).json()
    assert hits and all("geographic" in (h["title"] + h["url"]).lower() for h in hits)
    courses = client.get(f"{B}/courses").json()
    assert courses[0]["annotated"] is True  # courses someone looked at come first
    assert any(c["course_key"] == "GEOG222" for c in client.get(f"{B}/courses", params={"q": "geog 222"}).json())


@pytest.mark.slow
def test_verdict_with_supersedes_and_missing_are_appended(client):
    r = client.get(f"{B}/rules/course-name/rows", params={"limit": 1}).json()["rows"][0]
    t = {"kind": "match", "rule_id": "course-name", "occurrence_key": r["occurrence_key"], "page_stem": r["page_stem"]}
    first = client.post(f"{B}/annotations", json={"type": "verdict", "verdict": "correct", "author": "Test",
                                                  "target": t}).json()["event"]
    second = client.post(f"{B}/annotations", json={"type": "verdict", "verdict": "wrong", "author": "Test", "target": t,
                                                   "supersedes": first["annotation_id"], "note": "n",
                                                   "expected": {"text": "x", "css_path": None, "char_start": None,
                                                                "char_end": None}}).json()
    assert second["rule"]["status"] == "needs work"
    row = client.get(f"{B}/rules/course-name/rows", params={"focus": r["key"], "limit": 1}).json()
    assert row["rows"][row["focus_index"]]["state"] == "wrong"
    m = client.post(f"{B}/annotations", json={
        "type": "verdict", "verdict": "missing", "author": "Test",
        "target": {"kind": "occurrence", "rule_id": "locator-program-requirement", "occurrence_key": None,
                   "page_stem": GEOG_PROGRAM},
        "expected": {"text": "CS 999 fulfils nothing", "css_path": "html > body:nth-of-type(1) > p:nth-of-type(99)",
                     "char_start": 0, "char_end": 10}})
    assert m.status_code == 200
    rows = client.get(f"{B}/rules/locator-program-requirement/rows", params={"limit": 1}).json()
    assert any(x["page_stem"] == GEOG_PROGRAM for x in rows["missing"])
    # approve is refused while a course is wrong
    a = client.post(f"{B}/annotations", json={"type": "approve", "author": "Test",
                                              "target": {"kind": "rule", "rule_id": "course-name"}})
    assert a.status_code == 409
    log = client.root_path_ / AVC / "golden-dataset-studio" / "annotations.jsonl"
    ids = [json.loads(line)["annotation_id"] for line in log.read_text().splitlines()]
    assert first["annotation_id"] in ids and second["event"]["annotation_id"] in ids
