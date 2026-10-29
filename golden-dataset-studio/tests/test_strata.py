"""strata.py: how a rule's rows are grouped for the spread sample, and the order they are dealt in."""

from __future__ import annotations

from golden_datasets import strata


def row(key, value, course_key="ABDY112", status="found", page_stem="p", context=None):
    return {"key": key, "value": value, "course_key": course_key, "status": status, "page_stem": page_stem,
            "context": context}


def test_shape_and_subject():
    assert strata.shape("ABDY 112") == "A 9" and strata.shape("3.0 units") == "9.9 A"
    assert strata.subject({"course_key": "MATH060S"}) == "MATH"
    assert strata.subject({"course_key": None, "value": "Aircraft Airframe AS"}) == "AIRCRAFT"
    assert strata.url_pattern("https://x.edu/catalog/2026-27/course/abdy112") == "/catalog/9-9/course/*"


def test_long_text_goes_in_word_count_buckets_with_real_shares():
    rows = [row(f"r{i}", " ".join(["w"] * (i + 1)), course_key=f"S{i % 3}X1") for i in range(100)]
    rows.append(row("empty", None, status="no_match"))
    by, label, order = strata.groups("field", rows)
    assert by.startswith("length") and len(order) == 6 and order[-1] == "no value"
    assert order[0] == "1–20 words (percentile 0–20)" and label["r0"] == order[0] and label["empty"] == "no value"


def test_few_values_group_by_value_rarest_first_and_codes_by_shape():
    rows = [row(f"e{i}", "English") for i in range(9)] + [row("s", "Spanish")]
    _, label, order = strata.groups("field", rows)
    assert order[0] == "“Spanish”" and label["e0"] == "“English”"
    codes = [row(f"c{i}", f"ABDY {100 + i}") for i in range(40)] + [row("odd", "ABDY 1A")]
    by, label, order = strata.groups("field", codes)
    assert by.startswith("shape") and order[0] == "shape “A 9A”"


def test_spread_deals_one_row_per_group_then_per_subject():
    rows = [row(f"short{i}", "a b", course_key=f"{s}1") for i, s in enumerate("AAAB")]
    rows += [row(f"long{i}", " ".join(["w"] * 50), course_key=f"{s}1") for i, s in enumerate("CCCD")]
    label = {r["key"]: ("short" if r["key"].startswith("short") else "long") for r in rows}
    out = strata.spread(rows, label, ["short", "long"], rnd=lambda r: r["key"])
    groups = [label[r["key"]] for r in out]
    assert groups[:4] == ["short", "long", "short", "long"]
    assert {out[0]["course_key"], out[2]["course_key"]} == {"A1", "B1"}  # both subjects before a second A


def test_locator_groups_by_page_only_when_pages_hold_several_courses():
    one_each = [row(f"o{i}", "x", course_key=f"{s}1", page_stem=f"p{i}") for i, s in enumerate("ABC")]
    assert strata.groups("locator", one_each)[0].startswith("subject")
    several = [row(f"o{i}", "x", page_stem=f"p{i // 3}", context=f"Program {i // 3}") for i in range(9)]
    by, label, _ = strata.groups("locator", several)
    assert by.startswith("page") and label["o4"] == "page “Program 1”"


def test_page_rules_fall_back_to_courses_on_the_page():
    rows = [row(f"p{i}", f"Program {i}", course_key=None, page_stem=f"p{i}",
                context=f"https://x.edu/catalog/2026-27/program/p{i}") for i in range(10)]
    by, label, order = strata.groups("page", rows, courses_on_page={f"p{i}": i for i in range(10)})
    assert by.startswith("courses") and label["p0"] == order[0]
