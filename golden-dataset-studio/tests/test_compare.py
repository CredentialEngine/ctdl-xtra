"""W5 Compare: the scorecard pieces behind the Compare tab, and (slow) the API on a copy of `.data/root-demo`."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from golden_datasets.scorecard import compare, format_card, records_changed, rule_scorecard, verdict_order

DEMO = Path(__file__).resolve().parents[1] / ".data" / "root-demo"
AVC = "avc-elumenapp-com-catalog-2026-27-welcome"


# --- fakes: just what rule_scorecard reads --------------------------------------------------------------------
class Snap:
    def __init__(self, ext: str, version: int, rows: list[dict], content_hash: str = "h"):
        self.ext, self.ruleset_version = ext, version
        self.rules = {"course-description": {"kind": "field", "version": version, "content_hash": content_hash,
                                             "ctdl_property": "ceterms:description", "property_label": "Description",
                                             "why": f"why v{version}"}}
        self._rows = rows

    def rows(self, rule_id: str) -> list[dict]:
        return self._rows


class Rev:
    def __init__(self, events: list[dict]):
        self.events = events

    def verdicts_for(self, rule_id: str) -> dict:
        return {"latest": {e["target"]["occurrence_key"]: e for e in self.events}, "comments": {}}


def row(ck: str, value: str, signals=(), key: str | None = None) -> dict:
    return {"key": key or f"p-{ck}@div", "course_key": ck, "page_stem": f"p-{ck}", "value": value, "status": "found",
            "css_path": None, "char_start": None, "char_end": None,
            "signals": [{"signal": s, "severity": "medium", "detail": ""} for s in signals]}


def verdict(ck: str, v: str, expected: str | None = None, note: str | None = None) -> dict:
    return {"annotation_id": f"ann-{ck}", "type": "verdict", "verdict": v, "author": "Jared", "note": note,
            "at": "2026-10-20T00:00:00Z", "expected": {"text": expected} if expected else None,
            "target": {"kind": "match", "rule_id": "course-description", "occurrence_key": f"p-{ck}@div",
                       "course_key": ck, "page_stem": f"p-{ck}"}}


A = [row("FIX1", "Prerequisite: X. Body one", ["contains-label-text"]),
     row("STILL1", "Prerequisite: Y. Body two", ["contains-label-text"]),
     row("OK1", "Stays the same"),
     row("REGR1", "Was right"),
     row("OTHER1", "Prerequisite: Z. Other", ["contains-label-text"]),
     row("GONE1", "Advisory: gone", ["contains-label-text"])]
B = [row("FIX1", "Body one"),
     row("STILL1", "Body two plus"),
     row("OK1", "Stays the same"),
     row("REGR1", "Now broken", ["length-outlier"]),
     row("OTHER1", "Other"),
     row("NEW1", "Units: new", ["contains-label-text"])]
EVENTS = [verdict("OK1", "correct"), verdict("FIX1", "wrong", "Body one", "Prerequisite is separate."),
          verdict("REGR1", "correct"), verdict("STILL1", "wrong", "Body two")]


@pytest.fixture
def card():
    return rule_scorecard("course-description", Snap("rs-0001", 1, A, "h1"), Snap("rs-0002", 2, B, "h2"),
                          Rev(EVENTS), signal_rows=1)


def test_earlier_verdicts_follow_history_signals(card):
    """A4.1: changed-since-correct first, then previously-wrong (still wrong, fixed), then unchanged rows."""
    got = [(r["course_key"], r["outcome"], r["history"]) for r in card["annotated_rows"]]
    assert got == [("REGR1", "newly wrong", "changed-since-correct"),
                   ("STILL1", "still wrong", "previously-wrong"),
                   ("FIX1", "fixed", "previously-wrong"),
                   ("OK1", "unchanged", "previously-correct")]
    assert card["annotated"] == {"rows": 4, "fixed": 1, "still_wrong": 1, "newly_wrong": 1, "unchanged": 1}
    assert card["annotated_rows"][2]["note"] == "Prerequisite is separate."
    assert card["verdict"].startswith("WORSE")


def test_verdict_order_puts_wrong_before_correct_within_an_outcome():
    rows = [{"outcome": "unchanged", "verdict": "correct", "course_key": "A", "key": "a"},
            {"outcome": "unchanged", "verdict": "wrong", "course_key": "B", "key": "b"}]
    assert [r["key"] for r in sorted(rows, key=verdict_order)] == ["b", "a"]


def test_signals_count_lost_and_gained_including_new_and_vanished_rows(card):
    sig = {s["signal"]: s for s in card["signals"]}
    clt = sig["contains-label-text"]
    assert (clt["a"], clt["b"]) == (4, 1)
    assert clt["lost_total"] == 4 and clt["gained_total"] == 1          # FIX1, STILL1, OTHER1, GONE1 / NEW1
    assert clt["b"] - clt["a"] == clt["gained_total"] - clt["lost_total"]
    assert len(clt["lost"]) == 1                                         # capped by signal_rows; totals are not
    assert {s["signal"]: (s["a"], s["b"], s["gained_total"]) for s in card["signals"]}["length-outlier"] == (0, 1, 1)
    gained = clt["gained"][0]
    assert gained["course_key"] == "NEW1" and gained["a_value"] is None and gained["b_value"] == "Units: new"


def test_signal_lists_are_complete_without_a_cap():
    c = rule_scorecard("course-description", Snap("rs-0001", 1, A, "h1"), Snap("rs-0002", 2, B, "h2"), Rev(EVENTS))
    clt = next(s for s in c["signals"] if s["signal"] == "contains-label-text")
    assert len(clt["lost"]) == clt["lost_total"] == 4


def test_values_sample_and_records_changed(card):
    assert card["values"] == {"changed": 4, "total": 6, "new": 1, "vanished": 1}
    assert records_changed(card) == 6
    assert card["sample_total"] == 1 and [r["course_key"] for r in card["sample"]] == ["OTHER1"]
    assert [r["course_key"] for r in card["new_rows"]] == ["NEW1"]
    assert [r["course_key"] for r in card["vanished_rows"]] == ["GONE1"]


def test_compare_keeps_the_rule_try_contract():
    a, b = Snap("rs-0001", 1, A, "h1"), Snap("rs-0002", 2, B, "h2")
    out = compare(a, b, Rev(EVENTS), rules=["course-description"])
    assert out["records_changed"] == 6 and out["totals"]["newly_wrong"] == 1
    text = format_card(out["rules"][0], "v2")
    assert "course-description  v1 → v2" in text and "contains-label-text 4→1" in text


# --- slow: the API on a synced copy of the demo root ----------------------------------------------------------
@pytest.fixture(scope="module")
def client(tmp_path_factory):
    if not (DEMO / AVC).exists():
        pytest.skip(".data/root-demo not available")
    from fastapi.testclient import TestClient

    from golden_datasets.server.app import create_app
    from golden_datasets.storage import LocalRoot
    from golden_datasets.sync import sync_catalog

    root = tmp_path_factory.mktemp("compare") / "root"
    sync_catalog(LocalRoot(str(DEMO)), LocalRoot(str(root)), AVC, None, "link", False, False, log=lambda *a: None)
    return TestClient(create_app(str(root)))


@pytest.mark.slow
def test_avc_compare_v1_to_v2(client):
    t0 = time.perf_counter()
    r = client.get("/api/catalogs/avc/compare")
    cold = time.perf_counter() - t0
    assert r.status_code == 200
    d = r.json()
    assert (d["a"], d["b"], d["a_extraction"], d["b_extraction"]) == (1, 2, "rs-0001", "rs-0002")
    assert [c["rule_id"] for c in d["changed_rules"]] == ["course-description"]
    cr = d["changed_rules"][0]
    assert (cr["ctdl_property"], cr["title"], cr["a_version"], cr["b_version"], cr["records_changed"]) == \
        ("ceterms:description", "Description", 1, 2, 278)
    assert d["records_changed"] == 278
    assert d["totals"] == {"fixed": 5, "still_wrong": 0, "newly_wrong": 0, "unchanged": 9}
    card = d["rules"][0]
    rows = card["annotated_rows"]
    assert len(rows) == 14
    assert {r["course_key"] for r in rows[:5]} == {"AUTO230", "DFST202", "ENGR955", "GEOG222", "PHYS102"}
    assert all(r["outcome"] == "fixed" and r["history"] == "previously-wrong" for r in rows[:5])
    assert all(r["outcome"] == "unchanged" and r["verdict"] == "correct" for r in rows[5:])
    sig = {s["signal"]: s for s in card["signals"]}
    assert (sig["contains-label-text"]["a"], sig["contains-label-text"]["b"]) == (547, 273)
    assert sig["contains-label-text"]["lost_total"] == 274
    assert (sig["duplicate-value"]["a"], sig["duplicate-value"]["b"], sig["duplicate-value"]["gained_total"]) == (35, 37, 2)
    assert (sig["length-outlier"]["a"], sig["length-outlier"]["b"]) == (18, 19)
    assert card["sample_total"] == 273 and len(card["sample"]) == 12
    assert cold < 2.0  # spec §10, cold (in-process; bench/bench_compare.py measures a fresh server)

    t0 = time.perf_counter()
    assert client.get("/api/catalogs/avc/compare?a=1&b=2").json()["totals"]["fixed"] == 5
    assert time.perf_counter() - t0 < 0.3  # warm


@pytest.mark.slow
def test_avc_compare_rule_filter_and_edges(client):
    d = client.get("/api/catalogs/avc/compare?rule=course-description").json()
    assert [c["rule_id"] for c in d["rules"]] == ["course-description"] and d["records_changed"] == 278
    d = client.get("/api/catalogs/avc/compare?rule=course-name").json()   # unchanged rule: scored, nothing changed
    assert len(d["changed_rules"]) == 1 and d["rules"][0]["values"]["changed"] == 0 and d["records_changed"] == 0
    assert client.get("/api/catalogs/avc/compare?rule=no-such-rule").status_code == 404
    d = client.get("/api/catalogs/avc/compare?a=2&b=2").json()
    assert d["changed_rules"] == [] and d["rules"] == [] and d["records_changed"] == 0
    assert client.get("/api/catalogs/avc/compare?a=9").status_code == 404
