"""Strata and the BubbleUp over them (facets.py)."""

from __future__ import annotations

from golden_datasets import facets


def it(i: int, value: str, **kw) -> dict:
    return {"key": f"k{i}", "value": value, "status": "found" if value else "no_match", "course_key": kw.pop("ck", f"ABC{i}"),
            "page_stem": f"p{i}", "signals": kw.pop("signals", []), "url": "https://x/catalog/2026/course/a", **kw}


def test_histogram_has_equal_width_bars_and_a_tail():
    values = {f"k{i}": v for i, v in enumerate([5, 12, 18, 25, 33, 41, 47, 52, 58, 66] * 10 + [5000])}
    values["empty"] = None
    label, order = facets.histogram(values, "chars")
    assert order == ["0–9 chars", "10–19 chars", "20–29 chars", "30–39 chars", "40–49 chars", "50–59 chars",
                     "≥ 60 chars", "empty"]
    assert label["k100"] == ["≥ 60 chars"] and label["empty"] == ["empty"]
    assert facets.nice_step(70) == 10 and facets.nice_step(9) == 1 and facets.nice_step(1500) == 200


def test_histograms_count_the_list_and_set_aside_uniform_strata():
    items = [it(i, "Prerequisite: X.\nText" if i < 20 else "Plain text here", signals=["label"] if i < 20 else [])
             for i in range(100)]
    dims = facets.dimensions("field", items)
    assert {"length", "paragraphs", "lead", "subject", "url", "signals"} <= {d["id"] for d in dims}
    keys = [i["key"] for i in items]
    hs = {h["id"]: h for h in facets.histograms(dims, keys)}
    assert [(b["id"], b["count"]) for b in hs["lead"]["buckets"]] == [("none", 80), ("Prerequisite:", 20)]
    assert hs["url"]["uniform"] and facets.histograms(dims, keys)[-1]["uniform"]
    # a stratum's own filter is left out of its counts, the others' apply
    f = {"lead": {"Prerequisite:"}}
    hs = {h["id"]: h for h in facets.histograms(dims, keys, f)}
    assert [(b["id"], b["count"], b["on"]) for b in hs["lead"]["buckets"]] == [("none", 80, False), ("Prerequisite:", 20, True)]
    assert sum(b["count"] for b in hs["paragraphs"]["buckets"]) == 20


def test_auto_strata_deals_three_per_combination_rarest_first():
    items = [it(i, "Prerequisite: X.\nText" if i < 4 else ("Advisory: y" if i < 14 else "Plain")) for i in range(60)]
    dims = facets.dimensions("field", items)
    keys = [i["key"] for i in items]
    assert "lead" in facets.pick_cross(dims, keys) and "signals" not in facets.pick_cross(dims, keys)
    order, cells = facets.auto_strata(dims, keys, ["lead"], per_cell=3, seed=1)
    assert [c["rows"] for c in cells] == [4, 10, 46] and sorted(order) == sorted(keys)
    lead = {d["id"]: d for d in dims}["lead"]["values"]
    assert [lead[k][0] for k in order[:9]] == ["Prerequisite:"] * 3 + ["Advisory:"] * 3 + ["none"] * 3
    assert lead[order[9]] == ["Prerequisite:"]  # round 2
    assert facets.shuffle(keys, 1) != facets.shuffle(keys, 2) and sorted(facets.shuffle(keys, 1)) == sorted(keys)
    listed, info = facets.sample_order(dims, keys, {"lead": {"Advisory:"}}, "auto", ["length"], 0)
    assert len(listed) == 10 and info["tag_dims"] == ["length", "lead"] and info["listed"] == 10
    assert facets.tags(dims, listed[0], info["tag_dims"])[1] == {"dim": "lead", "label": "Leading label", "bucket": "Advisory:"}


def test_labels_are_normalised_and_filters_and_or():
    items = [it(0, "LIMITATION ON ENROLLMENT: a"), it(1, "Limitation on Enrollment: b"), it(2, "Advisory: c", ck="XYZ1"),
             it(3, "")]
    dims = facets.dimensions("field", items)
    lead = next(d for d in dims if d["id"] == "lead")
    assert lead["values"]["k0"] == lead["values"]["k1"] == ["Limitation on enrollment:"]
    f = facets.parse_filters(["lead:Limitation on enrollment:", "lead:Advisory:"])
    assert f == {"lead": {"Limitation on enrollment:", "Advisory:"}}
    assert facets.matches(dims, f) == {"k0", "k1", "k2"}
    assert facets.matches(dims, f | {"subject": {"ABC"}}) == {"k0", "k1"}
    assert facets.matches(dims, {}) is None and facets.matches(dims, {"nope": {"x"}}) == set()


def test_compare_items_get_change_and_rule_dimensions():
    items = [it(0, "short", rule="r1", change="shorter", before="Prerequisite: long"),
             it(1, "same", rule="r2", change="unchanged", before="same")]
    ids = [d["id"] for d in facets.dimensions("field", items)]
    assert ids[:2] == ["rule", "change"] and "lead_a" in ids
