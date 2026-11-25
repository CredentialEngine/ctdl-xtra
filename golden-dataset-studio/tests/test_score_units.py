"""The xtra score in the Studio (sme-fixes spec §8): duration objects and "not on the page" in values.parquet (unit,
field, reason), every outcome counted and checked against xtra's reports, found / right / courses exact, and "Where
it's wrong" groups. ACCT199's durations are the worked example (rules A, B and C)."""

from __future__ import annotations

import json

import pytest

from golden_datasets import scores
from golden_datasets.storage import LocalRoot

CAT, CRAWL, STEM = "avc", "2026-10-12T20-59-13Z", "acct199"
DUR, DESC, TIME = "ceterms:estimatedDuration", "ceterms:description", "ceterms:timeRequired"
IN_CLASS, OUT_CLASS = "Total Course In-Class (Contact) Hours", "Total Course Out-of-Class Hours"
LECTURE, LAB = "Total Course Lecture Hours", "Total Course Lab Hours"
GOLDEN = [{DESC: IN_CLASS, TIME: "54.0 - 432.0"}, {DESC: OUT_CLASS, TIME: "0.0 - 0.0"}, {DESC: LECTURE, TIME: "0.0"},
          {DESC: LAB, TIME: "432.0"}]
RULE_A = [*GOLDEN, {DESC: "Minimum Credit Units", TIME: "1.0"}]
RULE_C = [{DESC: IN_CLASS, TIME: "0.0 - 0.0"}, {DESC: OUT_CLASS, TIME: "54.0 - 432.0"}, *GOLDEN[2:]]


def _field(prop: str, value, **kw) -> dict:
    return {"ctdl_property": prop, "value": value, "source_url": "https://avc/acct199", "property": prop, **kw}


def _pages(extra: list[dict] = ()) -> dict:
    fields = [_field("ceterms:name", "Work Experience Education"), *(_field(DUR, d) for d in GOLDEN), *extra]
    return {STEM: [{"golden_record_id": "ACCT199", "fields": fields}]}


def _score(tmp_path, expected: dict, pages: dict) -> tuple[list[dict], dict]:
    """xtra's scorer on these pages against one record, then the Studio's rows and result (both bases alike)."""
    out = tmp_path / "out"
    (out / "records").mkdir(parents=True)
    (out / "records" / f"{STEM}.json").write_text(json.dumps({"record_id": STEM, "expected": expected}))
    (out / "extract-report.json").write_text(json.dumps({"skipped": []}))
    records = scores.RecordsStore(LocalRoot(out), "", CAT, CRAWL)
    reports = scores.run_scorer(records, pages, CAT, CRAWL, "test")
    rows = scores.value_rows("rule", pages, reports)
    return rows, scores.result(pages, [], reports, rows)


def _durations(rows: list[dict]) -> dict:
    return scores.counts([r for r in rows if r["column"] == "estimatedDuration"])


def test_rule_b_exact(tmp_path):
    rows, res = _score(tmp_path, {"ceterms:name": "Work Experience Education", DUR: GOLDEN}, _pages())
    c = _durations(rows)
    assert (c["values"], c["extracted"], c["match"], c["found"], c["right"]) == (4, 4, 4, 1.0, 1.0)
    assert (c["courses"], c["courses_exact"], c["list"]) == (1, 1, True)
    assert {r["unit"] for r in rows if r["column"] == "estimatedDuration"} == {"object"}
    assert res["by_column"]["estimatedDuration"]["right"] == 1.0


def test_rule_a_extra_found_4_of_4_right_4_of_5(tmp_path):
    rows, res = _score(tmp_path, {"ceterms:name": "Work Experience Education", DUR: RULE_A}, _pages())
    c = _durations(rows)
    assert (c["match"], c["extra"], c["found"], c["right"], c["courses_exact"]) == (4, 1, 1.0, 0.8, 0)
    [extra] = [r for r in rows if r["outcome"] == "extra"]
    assert json.loads(extra["extracted_value"]) == {DESC: "Minimum Credit Units", TIME: "1.0"}
    assert (extra["golden_value"], extra["unit"], extra["reason"], extra["golden_record_id"]) == \
        (None, "object", "no golden value", "ACCT199")
    # values and exact_match_rate are the golden side's, as before; extras are counted apart
    assert res["values"] == 5 and res["exact_match_rate"] == 1.0 and res["outcomes"]["extra"] == 1
    assert res["found"] == 1.0 and res["right"] == round(5 / 6, 4)
    [group] = scores.wrong_groups(rows)
    assert (group["outcome"], group["by"], group["key"], group["units"]) == \
        ("extra", "description label", "Minimum Credit Units", 1)
    assert group["courses"] == 1 and group["targets"][0]["golden_record_id"] == "ACCT199"


def test_rule_c_pairs_by_description_found_2_of_4_right_2_of_4(tmp_path):
    rows, _ = _score(tmp_path, {"ceterms:name": "Work Experience Education", DUR: RULE_C}, _pages())
    c = _durations(rows)
    assert (c["match"], c["wrong"], c["found"], c["right"]) == (2, 2, 0.5, 0.5)
    wrong = [r for r in rows if r["outcome"] == "wrong"]
    assert {r["field"] for r in wrong} == {"timeRequired"} and {r["reason"] for r in wrong} == {"different"}
    [group] = scores.wrong_groups(rows)
    assert (group["outcome"], group["field"], group["by"], group["key"], group["units"]) == \
        ("wrong", "timeRequired", "value shape", "9.9 - 9.9 → 9.9 - 9.9", 2)
    assert json.loads(group["example"]["golden_value"])[DESC] == IN_CLASS


def test_a_time_cut_short_groups_by_its_shape(tmp_path):
    cut = [{DESC: IN_CLASS, TIME: "54.0"}, *GOLDEN[1:]]
    rows, _ = _score(tmp_path, {DUR: cut}, _pages())
    [w] = [r for r in rows if r["outcome"] == "wrong"]
    assert (w["field"], w["reason"]) == ("timeRequired", "cut short")
    g = next(g for g in scores.wrong_groups(rows) if g["outcome"] == "wrong")
    assert g["key"] == "9.9 - 9.9 → 9.9"
    assert scores.wrong_groups(rows, "diff")[0]["key"] in ("cut short", "nothing extracted")
    assert {g["by"] for g in scores.wrong_groups(rows, "subject")} == {"course subject"}


def test_not_on_the_page_match_unsure_missing_and_extra(tmp_path):
    absent = [_field("ceterms:prerequisite", None, absent=True, location=None),
              _field("ceterms:corequisite", None, absent=True, location=None),
              _field("ceterms:recommends", None, absent=True, location=None),
              _field("ceterms:requires", "ATH 100")]
    expected = {DUR: GOLDEN, "ceterms:prerequisite": None, "ceterms:recommends": "Grade Mode: Normal",
                "ceterms:requires": None}
    rows, res = _score(tmp_path, expected, _pages(absent))
    by = {r["column"]: r for r in rows if r["column"] not in ("estimatedDuration",) and r["outcome"] != "extra"}
    assert (by["prerequisite"]["outcome"], by["prerequisite"]["unit"]) == ("match", "absent")
    assert (by["corequisite"]["outcome"], by["corequisite"]["reason"]) == ("unsure", "no claim")
    assert (by["recommends"]["outcome"], by["recommends"]["reason"]) == \
        ("missing", "a value where golden says not on the page")
    assert (by["requires"]["outcome"], by["requires"]["reason"]) == ("missing", "claimed not on the page")
    extras = {r["column"]: r for r in rows if r["outcome"] == "extra"}
    assert extras["recommends"]["reason"] == "golden says not on the page"
    assert (extras["requires"]["unit"], extras["requires"]["reason"]) == ("absent", "claimed not on the page")
    assert res["outcomes"]["unsure"] == 1 and res["outcomes"]["extra"] == 2
    assert "prerequisite" not in res["implied"]  # an absent field is scored, not implied


def test_the_rebuilt_counts_are_checked_against_the_reports(tmp_path):
    pages = _pages()
    rows, _ = _score(tmp_path, {DUR: RULE_A}, pages)
    reports = scores.run_scorer(scores.RecordsStore(LocalRoot(tmp_path / "out"), "", CAT, CRAWL), pages, CAT, CRAWL,
                                "test")
    reports["exact"]["outcomes"]["unsure"] = 1  # a report that disagrees with the rows
    with pytest.raises(Exception, match="rebuilt counts"):
        scores.value_rows("rule", pages, reports)


@pytest.mark.parametrize(("golden", "extracted", "kind"), [
    ("54.0 - 432.0", "54.0", "cut short"),
    ("Total Course Lab Hours", "Total Course Lab Hours 54.0", "extra text"),
    ("Lecture", "Lab", "different"),
    ("Same", "same", "different"),
])
def test_diff_kind(golden, extracted, kind):
    assert scores.diff_kind(golden, extracted) == kind


def test_counts_of_old_rows_have_no_extras():
    rows = [{"outcome": o, "page_stem": "p", "entity": 0} for o in ("match", "partial", "missing")]
    c = scores.counts(rows)
    assert (c["values"], c["extracted"], c["extra"], c["unsure"], c["found"], c["right"]) == (3, 2, 0, 0, 0.3333, 0.5)
    assert c["list"] is True and c["courses_exact"] == 0
