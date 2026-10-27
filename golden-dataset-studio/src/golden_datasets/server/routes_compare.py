"""Compare API (W5): two ruleset versions on the same crawl, scored by the library `rule try` uses (spec §7.4)."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

from .. import scorecard
from ..review import LOADER
from .routes_review import rule_title
from .state import not_found, studio

router = APIRouter(prefix="/api")

#: Rows kept per signal's lost / gained list (`lost_total` / `gained_total` are always complete). Enough to expand a
#: signal; all 274 rows of AVC's contains-label-text would make the response 710 KB instead of ~300 KB.
SIGNAL_ROWS = 100
TOTAL_KEYS = ("fixed", "still_wrong", "newly_wrong", "unchanged")


def _titled(card: dict, snap_a, snap_b) -> dict:
    rule_doc = snap_b.rules.get(card["rule_id"]) or snap_a.rules[card["rule_id"]]
    card["title"], card["subtitle"] = rule_title(rule_doc)
    return card


@router.get("/catalogs/{catalog}/compare")
def compare(request: Request, catalog: str, a: int | None = None, b: int | None = None,
            rule: str | None = None) -> dict:
    """`a` / `b` are ruleset versions (default: the latest two that have an extraction). `rule` narrows the
    comparison to one rule; the summary of every changed rule is always returned for the left column.

    With a single ruleset version (or a == b) the response has that version on both sides and no changed rules."""
    t0 = time.perf_counter()
    st = studio(request)
    ctx = st.ctx(catalog)
    versions = [v for v in ctx.ruleset_versions() if ctx.extraction_for(v)]
    if not versions:
        raise not_found(f"{catalog}: nothing extracted yet")
    b = b or versions[-1]
    a = a or max([v for v in versions if v < b], default=b)  # the version before B
    ea, eb = ctx.extraction_for(a), ctx.extraction_for(b)
    if not ea or not eb:
        raise not_found("that ruleset version has no extraction on this crawl")
    version_list = [{"version": v, "extraction": ctx.extraction_for(v), "note": ctx.ruleset(v).get("note")}
                    for v in versions]
    head = {"a": a, "b": b, "a_extraction": ea, "b_extraction": eb, "versions": version_list}
    if ea == eb:
        return {**head, "changed_rules": [], "records_changed": 0, "totals": dict.fromkeys(TOTAL_KEYS, 0),
                "rules": [], "elapsed_ms": round(1000 * (time.perf_counter() - t0), 1)}

    snap_a, snap_b = LOADER.snapshot(ctx, ea), LOADER.snapshot(ctx, eb)
    rv = LOADER.review(ctx, eb, with_parent=False)  # reads the log's new lines, so the offset below is current
    offset = LOADER.log(ctx).offset
    key = ("compare", ctx.catalog, ea, eb, offset)
    if key not in st.cache:
        result = scorecard.compare(snap_a, snap_b, rv, signal_rows=SIGNAL_ROWS)
        for c in result["rules"]:
            _titled(c, snap_a, snap_b)
        _evict(st.cache, "compare", ctx.catalog, ea, eb, offset)
        st.cache[key] = result
    cards = st.cache[key]["rules"]

    if rule is None:
        selected = cards
    else:
        selected = [c for c in cards if c["rule_id"] == rule]
        if not selected:  # a rule that didn't change: still score it, so a link to it shows "no change"
            if rule not in snap_a.rules and rule not in snap_b.rules:
                raise not_found(f"{catalog}: no rule {rule!r} in ruleset v{a} or v{b}")
            one = ("compare-rule", ctx.catalog, ea, eb, offset, rule)
            if one not in st.cache:
                st.cache[one] = _titled(scorecard.rule_scorecard(rule, snap_a, snap_b, rv, signal_rows=SIGNAL_ROWS),
                                        snap_a, snap_b)
            selected = [st.cache[one]]
    totals = {k: sum(c["annotated"][k] for c in selected) for k in TOTAL_KEYS}
    return {**head,
            "changed_rules": [{"rule_id": c["rule_id"], "title": c["title"], "subtitle": c["subtitle"],
                               "kind": c["kind"], "ctdl_property": c["ctdl_property"],
                               "property_label": c["property_label"],
                               "a_version": c["a_version"], "b_version": c["b_version"],
                               "records_changed": scorecard.records_changed(c)}
                              for c in cards],
            "records_changed": sum(scorecard.records_changed(c) for c in selected),
            "totals": totals, "rules": selected, "elapsed_ms": round(1000 * (time.perf_counter() - t0), 1)}


def _evict(cache: dict, kind: str, catalog: str, ea: str, eb: str, offset: int) -> None:
    """Drop comparisons of the same pair at older log offsets (each new verdict makes a new key)."""
    for k in [k for k in cache if isinstance(k, tuple) and len(k) >= 5 and k[0] in (kind, "compare-rule")
              and k[1:4] == (catalog, ea, eb) and k[4] != offset]:
        del cache[k]
