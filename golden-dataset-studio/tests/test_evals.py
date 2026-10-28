"""Evals (docs/qrspi/evals): the baselines written for xtra's scorer, and the per-field rows rebuilt from its reports.
Pure functions, no catalog needed."""

from __future__ import annotations

import pytest

from golden_datasets.errors import UserError
from golden_datasets.evals import baseline, baseline_stats, fields_rows, mask


def f(prop, value, approval="rule", by=None):
    return {"ctdl_property": prop, "property": None, "value": value, "source_url": "u", "approval": approval,
            "approved_by": by, "approved_at": None}


PAGES = {
    "p1": [{"golden_record_id": "A1", "approval": "mixed", "fields": [
        f("ceterms:codedNotation", "A 1", "human", "Jared"), f(None, "Course"), f("ceterms:description", "Long text")]}],
    "p2": [{"golden_record_id": "B1", "approval": "rule", "fields": [f("ceterms:codedNotation", "B 1")]},
           {"golden_record_id": "B2", "approval": "human", "fields": [f("ceterms:codedNotation", "B 2", "human")]}],
    "p3": [{"golden_record_id": "C1", "approval": "human", "fields": [f("ceterms:codedNotation", "C 1", "human")]},
           {"golden_record_id": "C2", "approval": "rule", "fields": [f("ceterms:codedNotation", "C 2")]}],
}


def test_full_baseline_drops_fields_without_a_ctdl_term():
    base, left = baseline(PAGES, "full")
    assert [x["ctdl_property"] for x in base["p1"][0]["fields"]] == ["ceterms:codedNotation", "ceterms:description"]
    assert set(base) == {"p1", "p2", "p3"} and not left


def test_hand_baseline_keeps_only_values_a_person_confirmed():
    base, left = baseline(PAGES, "hand")
    assert [x["value"] for x in base["p1"][0]["fields"]] == ["A 1"]
    # p3: the trailing course has no hand-checked value, so it's dropped; p2: an earlier one is empty, so the scorer's
    # positional pairing would shift, and the page is left out
    assert len(base["p3"]) == 1
    assert "p2" not in base and left == [{"stem": "p2", "why": "an earlier course on the page has no values in this "
                                                              "baseline"}]


def report(mode, outliers, fields_total, outcomes, pages=("p1",)):
    return {"mode": mode, "fields_total": fields_total, "outcomes": outcomes, "outliers": outliers,
            "pages": [{"stem": s, "status": "scored"} for s in pages], "out_of_scope": [], "malformed": []}


def test_fields_rows_rebuilds_every_field_and_checks_the_counts():
    base, _ = baseline({"p1": PAGES["p1"]}, "full")
    miss = {"stem": "p1", "entity": 0, "ctdl_property": "ceterms:description", "baseline_value": "Long text",
            "extracted_value": "Long tex", "similarity": 0.94, "outcome": "mismatch"}
    exact = report("exact", [miss], 2, {"match": 1, "mismatch": 1, "missing": 0})
    partial = report("partial", [miss | {"outcome": "partial"}], 1, {"partial": 1, "wrong": 0, "missing": 0})
    rows = fields_rows("ev-0001", "full", base, {"exact": exact, "partial": partial},
                       {"p1": [{"template_id": "markup"}]})
    by = {r["ctdl_property"]: r for r in rows}
    assert by["ceterms:codedNotation"]["outcome"] == "exact"
    assert by["ceterms:codedNotation"]["xtra_value"] == "A 1" and by["ceterms:codedNotation"]["approved_by"] == "Jared"
    assert (by["ceterms:description"]["outcome"], by["ceterms:description"]["similarity"]) == ("partial", 0.94)
    assert {r["template_id"] for r in rows} == {"markup"}

    wrong_counts = report("exact", [miss], 2, {"match": 0, "mismatch": 2, "missing": 0})
    with pytest.raises(UserError, match="don't match the scorer"):
        fields_rows("ev-0001", "full", base, {"exact": wrong_counts, "partial": partial}, {})


def test_implied_values_are_not_scored():
    # a value the golden data says isn't on the page (location: null) is skipped by xtra's scorer (xtra-cli #343)
    pages = {"p1": [{"golden_record_id": "A1", "approval": "rule", "fields": [
        f("ceterms:codedNotation", "A 1") | {"location": {"css_path": "h3", "char_start": 0, "char_end": 3}},
        f("ceterms:inLanguage", "English") | {"location": None}]}]}
    base, _ = baseline(pages, "full")
    exact = report("exact", [], 1, {"match": 1, "mismatch": 0, "missing": 0})
    partial = report("partial", [], 0, {"partial": 0, "wrong": 0, "missing": 0})
    rows = fields_rows("ev-0001", "full", base, {"exact": exact, "partial": partial}, {})
    assert {r["ctdl_property"]: r["outcome"] for r in rows} == {"ceterms:codedNotation": "exact",
                                                                 "ceterms:inLanguage": "implied"}
    stats = baseline_stats(pages, "full")
    assert stats["fields"] == 1 and stats["not_scored"] == [{"property": "Language", "fields": 1,
                                                              "why": "implied: not read from the page"}]


def test_connection_strings_are_masked_in_logs():
    assert mask("AccountName=x;AccountKey=abc123==;EndpointSuffix=y") == "AccountName=x;AccountKey=***;EndpointSuffix=y"
