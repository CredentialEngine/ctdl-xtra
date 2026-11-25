"""Compare API (W5): two ruleset versions on the same crawl, scored by the library `rule try` uses (spec §7.4)."""

from __future__ import annotations

import hashlib
import time
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from .. import facets, scorecard, telemetry
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


@router.get("/catalogs/{catalog}/compare")
def compare(request: Request, catalog: str, a: int | None = None, b: int | None = None,
            rule: str | None = None) -> dict:
    """`a` / `b` are ruleset versions (default: the latest two that have an extraction). `rule` narrows the
    comparison to one rule; the summary of every changed rule is always returned for the left column.

    With a single ruleset version (or a == b) the response has that version on both sides and no changed rules."""
    t0 = time.perf_counter()
    st = studio(request)
    ctx = st.ctx(catalog)
    head = compare_head(ctx, catalog, a, b)
    if head["a_extraction"] == head["b_extraction"]:
        return {**head, "changed_rules": [], "records_changed": 0, "totals": dict.fromkeys(TOTAL_KEYS, 0),
                "rules": [], "elapsed_ms": _elapsed_ms(t0)}
    loaded = _cards(st, ctx, head["a_extraction"], head["b_extraction"])
    cards = loaded[-1]
    selected = cards if rule is None else selected_cards(st, ctx, catalog, head, rule, loaded)
    describe_span(cards, selected)
    return {**head, "changed_rules": [changed_rule(c) for c in cards],
            "records_changed": sum(scorecard.records_changed(c) for c in selected),
            "totals": {k: sum(c["annotated"][k] for c in selected) for k in TOTAL_KEYS},
            "rules": selected, "elapsed_ms": _elapsed_ms(t0)}


def compare_head(ctx, catalog: str, a: int | None, b: int | None) -> dict:
    """The two versions compared (default: the latest and the one before it), their extractions, and every version."""
    versions = [v for v in ctx.ruleset_versions() if ctx.extraction_for(v)]
    if not versions:
        raise not_found(f"{catalog}: nothing extracted yet")
    b = b or versions[-1]
    a = a or max([v for v in versions if v < b], default=b)  # the version before B
    ea, eb = extractions(ctx, a, b)
    version_list = [{"version": v, "extraction": ctx.extraction_for(v), "note": ctx.ruleset(v).get("note")}
                    for v in versions]
    return {"a": a, "b": b, "a_extraction": ea, "b_extraction": eb, "versions": version_list}


def selected_cards(st, ctx, catalog: str, head: dict, rule: str, loaded: tuple) -> list[dict]:
    """The one rule's card; a rule that didn't change is still scored, so a link to it shows "no change"."""
    snap_a, snap_b, rv, offset, cards = loaded
    selected = [c for c in cards if c["rule_id"] == rule]
    if selected:
        return selected
    if rule not in snap_a.rules and rule not in snap_b.rules:
        raise not_found(f"{catalog}: no rule {rule!r} in ruleset v{head['a']} or v{head['b']}")
    one = ("compare-rule", ctx.catalog, head["a_extraction"], head["b_extraction"], offset, rule)
    if one not in st.cache:
        st.cache[one] = _titled(scorecard.rule_scorecard(rule, snap_a, snap_b, rv, signal_rows=SIGNAL_ROWS),
                                snap_a, snap_b)
    return [st.cache[one]]


def describe_span(cards: list[dict], selected: list[dict]) -> None:
    telemetry.set({"ce.compare.changed_rules": len(cards), "ce.compare.rules_shown": len(selected),
                   "ce.compare.records_changed": sum(scorecard.records_changed(c) for c in selected)})


def changed_rule(c: dict) -> dict:
    return {"rule_id": c["rule_id"], "title": c["title"], "subtitle": c["subtitle"],
            "kind": c["kind"], "ctdl_property": c["ctdl_property"], "property_label": c["property_label"],
            "a_version": c["a_version"], "b_version": c["b_version"],
            "records_changed": scorecard.records_changed(c)}


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
    ea, eb = extractions(ctx, a, b)
    limit = max(1, min(limit, MAX_PAGE))
    cached = changed_records(st, ctx, ea, eb, rule)
    if order not in ("auto", "shuffle"):
        raise HTTPException(status_code=422, detail="order must be auto or shuffle")
    by_key = {o[0]: o for o in cached["others"]}
    keys, sample = facets.sample_order(cached["dims"], list(by_key), facets.parse_filters(f), order,
                                       None if cross is None else [c for c in cross if c], seed)
    page = record_page(cached["dims"], by_key, keys[offset:offset + limit], sample)
    telemetry.set({"ce.compare.records_total": len(keys), "ce.rows.returned": len(page)})
    return {"total": len(keys), "all": len(by_key), "offset": offset, "limit": limit, "records": page,
            "sample": sample, "elapsed_ms": _elapsed_ms(t0)}


def changed_records(st, ctx, ea: str, eb: str, rule: str | None) -> dict:
    """{dims, others}: the strata of the changed records without a verdict, and those records; cached per log offset."""
    snap_a, snap_b, _rv, log_offset, cards = _cards(st, ctx, ea, eb)
    ckey = ("compare-records", ctx.catalog, ctx.cls, ea, eb, log_offset, rule)
    if ckey not in st.cache:
        items, others, kind = record_changes(snap_a, snap_b, cards, rule)
        _evict(st.cache, "compare-records", ctx.catalog, ea, eb, log_offset)
        st.cache[ckey] = {"dims": listed_dims(kind, items, others), "others": others}
    return st.cache[ckey]


def record_changes(snap_a, snap_b, cards: list[dict], rule: str | None) -> tuple[list[dict], list[tuple], str]:
    """(every paired record as a facets item, the changed ones without a verdict in shuffled order, the rules' kind)."""
    rule_ids = [c["rule_id"] for c in cards if rule is None or c["rule_id"] == rule]
    annotated = {(c["rule_id"], r["key"]) for c in cards for r in c["annotated_rows"]}
    items, others, kinds = [], [], set()
    for rid in rule_ids:
        kinds.add((snap_b.rules.get(rid) or snap_a.rules[rid])["kind"])
        rule_items, rule_others = rule_changes(snap_a, snap_b, rid, annotated)
        items += rule_items
        others += rule_others
    others.sort(key=lambda o: hashlib.sha1(f"compare:{o[3]['key']}".encode()).hexdigest())
    kind = next(iter(kinds)) if len(kinds) == 1 else ("property" if "property" in kinds else "locator")
    return items, others, kind


def rule_changes(snap_a, snap_b, rid: str, annotated: set[tuple]) -> tuple[list[dict], list[tuple]]:
    a_rows = snap_a.rows(rid) if rid in snap_a.rules else []
    b_rows = snap_b.rows(rid) if rid in snap_b.rules else []
    pairs, _new, _gone = scorecard.pair_rows(a_rows, b_rows)
    items, others = [], []
    for x, y in pairs:
        k = f"{rid}\t{y['key']}"
        ch = change_kind(x, y)
        items.append(facets.item(y, snap_b.page[y["page_stem"]]["url"], rule=rid, change=ch,
                                 before=x["value"]) | {"key": k})
        if ch != "unchanged" and (rid, y["key"]) not in annotated:
            others.append((k, rid, x, y))
    return items, others


def listed_dims(kind: str, items: list[dict], others: list[tuple]) -> list[dict]:
    dims = facets.dimensions(kind, items)
    mine = {o[0] for o in others}  # the strata describe the listed records, not the unchanged ones
    for d in dims:
        d["values"] = {k: v for k, v in d["values"].items() if k in mine}
    return dims


def record_page(dims: list[dict], by_key: dict, keys: list[str], sample: dict) -> list[dict]:
    return [scorecard._brief(x, y) | {"rule_id": rid, "tags": facets.tags(dims, k, sample["tag_dims"])}
            for k, rid, x, y in (by_key[k] for k in keys)]


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


# --- Shared ---------------------------------------------------------------------------------------------------


def _cards(st, ctx, ea: str, eb: str) -> tuple:
    """(snapshot A, snapshot B, review, log offset, every changed rule's card), cached per log offset."""
    snap_a, snap_b = LOADER.snapshot(ctx, ea), LOADER.snapshot(ctx, eb)
    rv = LOADER.review(ctx, eb, with_parent=False)  # reads the log's new lines, so the offset below is current
    rv.report_sizes()
    offset = LOADER.log(ctx).offset
    key = ("compare", ctx.catalog, ctx.cls, ea, eb, offset)
    if key not in st.cache:
        result = scorecard.compare(snap_a, snap_b, rv, signal_rows=SIGNAL_ROWS)
        for c in result["rules"]:
            _titled(c, snap_a, snap_b)
        _evict(st.cache, "compare", ctx.catalog, ea, eb, offset)
        st.cache[key] = result
    return snap_a, snap_b, rv, offset, st.cache[key]["rules"]


def extractions(ctx, a: int, b: int) -> tuple[str, str]:
    ea, eb = ctx.extraction_for(a), ctx.extraction_for(b)
    if not ea or not eb:
        raise not_found("that ruleset version has no extraction on this crawl")
    return ea, eb


def _titled(card: dict, snap_a, snap_b) -> dict:
    rule_doc = snap_b.rules.get(card["rule_id"]) or snap_a.rules[card["rule_id"]]
    card["title"], card["subtitle"] = rule_title(rule_doc)
    return card


def _evict(cache: dict, kind: str, catalog: str, ea: str, eb: str, offset: int) -> None:
    """Drop comparisons of the same pair at older log offsets (each new verdict makes a new key)."""
    kinds = (kind, "compare-rule") if kind == "compare" else (kind,)
    for k in [k for k in cache if isinstance(k, tuple) and len(k) >= 5 and k[0] in kinds
              and k[1:4] == (catalog, ea, eb) and k[4] != offset]:
        del cache[k]


def _elapsed_ms(t0: float) -> float:
    return round(1000 * (time.perf_counter() - t0), 1)
