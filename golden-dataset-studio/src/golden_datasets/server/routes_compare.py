"""Compare API (W5): two ruleset versions on the same crawl, scored by the library `rule try` uses (spec §7.4)."""

from __future__ import annotations

import hashlib
import time
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from .. import facets, scorecard
from ..review import LOADER, norm
from .routes_review import rule_title
from .state import not_found, studio

router = APIRouter(prefix="/api")

#: Rows kept per signal's lost / gained list (`lost_total` / `gained_total` are always complete). Enough to expand a
#: signal; all 274 rows of AVC's contains-label-text would make the response 710 KB instead of ~300 KB.
SIGNAL_ROWS = 100
TOTAL_KEYS = ("fixed", "still_wrong", "newly_wrong", "unchanged")
#: Changed records per page of `/compare/records` (the page-size menu goes up to MAX_PAGE).
PAGE, MAX_PAGE = 50, 500


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

    snap_a, snap_b, rv, offset, cards = _cards(st, ctx, ea, eb)

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


def _cards(st, ctx, ea: str, eb: str) -> tuple:
    """(snapshot A, snapshot B, review, log offset, every changed rule's card), cached per log offset."""
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
    return snap_a, snap_b, rv, offset, st.cache[key]["rules"]


def change_kind(x: dict, y: dict) -> str:
    """How a record's value changed from A to B, in a few words (the `change` stratum)."""
    xv, yv = (x["value"] or "").strip(), (y["value"] or "").strip()
    if norm(x["value"]) == norm(y["value"]) and x["status"] == y["status"]:
        return "unchanged"
    if xv and not yv:
        return "emptied"
    if yv and not xv:
        return "filled"
    if len(yv) < len(xv):
        return "much shorter (< ½)" if len(yv) < len(xv) / 2 else "shorter"
    if len(yv) > len(xv):
        return "much longer (> 1½×)" if len(yv) > len(xv) * 1.5 else "longer"
    return "same length, edited"


@router.get("/catalogs/{catalog}/compare/records")
def compare_records(request: Request, catalog: str, a: int, b: int, rule: str | None = None, offset: int = 0,
                    limit: int = PAGE, f: Annotated[list[str] | None, Query()] = None, order: str = "shuffle",
                    cross: Annotated[list[str] | None, Query()] = None, seed: int = 0) -> dict:
    """Every changed record without a verdict ("other changed records"), a page at a time. The Sample drawer
    (facets.py): `f` filters by strata, `order` is `shuffle` (seeded by `seed`) or `auto` (Autostratify over `cross`).
    `sample`: the strata histograms of these records, the crossed strata and their combinations; records carry
    `tags`: their bucket in each crossed or filtered stratum."""
    t0 = time.perf_counter()
    st = studio(request)
    ctx = st.ctx(catalog)
    ea, eb = ctx.extraction_for(a), ctx.extraction_for(b)
    if not ea or not eb:
        raise not_found("that ruleset version has no extraction on this crawl")
    limit = max(1, min(limit, MAX_PAGE))
    snap_a, snap_b, rv, log_offset, cards = _cards(st, ctx, ea, eb)
    ckey = ("compare-records", ctx.catalog, ea, eb, log_offset, rule)
    if ckey not in st.cache:
        rule_ids = [c["rule_id"] for c in cards if rule is None or c["rule_id"] == rule]
        annotated = {(c["rule_id"], r["key"]) for c in cards for r in c["annotated_rows"]}
        items, others, kinds = [], [], set()
        for rid in rule_ids:
            kinds.add((snap_b.rules.get(rid) or snap_a.rules[rid])["kind"])
            a_rows = snap_a.rows(rid) if rid in snap_a.rules else []
            b_rows = snap_b.rows(rid) if rid in snap_b.rules else []
            pairs, _new, _gone = scorecard.pair_rows(a_rows, b_rows)
            for x, y in pairs:
                k = f"{rid}\t{y['key']}"
                ch = change_kind(x, y)
                items.append(facets.item(y, snap_b.page[y["page_stem"]]["url"], rule=rid, change=ch,
                                    before=x["value"]) | {"key": k})
                if ch != "unchanged" and (rid, y["key"]) not in annotated:
                    others.append((k, rid, x, y))
        others.sort(key=lambda o: hashlib.sha1(f"compare:{o[3]['key']}".encode()).hexdigest())
        kind = next(iter(kinds)) if len(kinds) == 1 else ("field" if "field" in kinds else "locator")
        _evict(st.cache, "compare-records", ctx.catalog, ea, eb, log_offset)
        dims = facets.dimensions(kind, items)
        mine = {o[0] for o in others}  # the strata describe the listed records, not the unchanged ones
        for d in dims:
            d["values"] = {k: v for k, v in d["values"].items() if k in mine}
        st.cache[ckey] = {"dims": dims, "others": others}
    cached = st.cache[ckey]
    if order not in ("auto", "shuffle"):
        raise HTTPException(status_code=422, detail="order must be auto or shuffle")
    by_key = {o[0]: o for o in cached["others"]}
    keys, sample = facets.sample_order(cached["dims"], list(by_key), facets.parse_filters(f), order,
                                       None if cross is None else [c for c in cross if c], seed)
    page = [scorecard._brief(x, y) | {"rule_id": rid, "tags": facets.tags(cached["dims"], k, sample["tag_dims"])}
            for k, rid, x, y in (by_key[k] for k in keys[offset:offset + limit])]
    return {"total": len(keys), "all": len(by_key), "offset": offset, "limit": limit, "records": page,
            "sample": sample, "elapsed_ms": round(1000 * (time.perf_counter() - t0), 1)}


def _evict(cache: dict, kind: str, catalog: str, ea: str, eb: str, offset: int) -> None:
    """Drop comparisons of the same pair at older log offsets (each new verdict makes a new key)."""
    kinds = (kind, "compare-rule") if kind == "compare" else (kind,)
    for k in [k for k in cache if isinstance(k, tuple) and len(k) >= 5 and k[0] in kinds
              and k[1:4] == (catalog, ea, eb) and k[4] != offset]:
        del cache[k]
