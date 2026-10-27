"""Strata of a rule's rows, and the sample orders built on them (the Rules tab's and Compare's "Sample" drawer).

Each row is cut along several dimensions at once: its value's length (an equal-width histogram), paragraphs, leading
label (`Prerequisite:`, `Advisory:` …), distinct value or shape, course subject, URL pattern, courses on the page,
signals, review state and, on Compare, how the value changed.

- `histograms`: each dimension's buckets with how many rows of the list fall in each (a dimension's own filter is
  left out of its counts, so its other buckets stay pickable); a dimension whose rows all fall in one bucket is
  `uniform` and set aside.
- Filters (manual select): `{dimension: {bucket, …}}`. Buckets of one dimension are ORed, dimensions are ANDed.
- `auto_strata`: cross the dimensions that split the rows most evenly (`pick_cross`), deal `per_cell` rows from
  each combination, the rarest combinations first, then the rest of the rows the same way. Empty combinations
  don't exist, so they never show.
- `shuffle`: a seeded random order.

Pure functions, so they are tested without a catalog; the callers (routes_review.py, routes_compare.py) build the
items.

An item is a dict: `key`, `value`, `status`, `course_key`, `page_stem`, `signals` (names), `url`, and optionally
`state` (review state), `on_page` (courses on its page), `rule` (rule id), `change` and `before` (Compare: how the
value changed, and the value in A).
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

from .strata import FEW_VALUES, shape, subject, url_pattern

MAX_BUCKETS = 12          # categorical dimensions keep their 11 biggest buckets, the rest go to "other"
BINS = 10                 # a length histogram has about this many bars
OTHER, EMPTY, NONE = "other", "empty", "none"
LEAD = re.compile(r"^\s*([A-Z][A-Za-z/()&'-]*(?: [A-Za-z/()&'-]+){0,3})\s*:")  # a label of 1–4 words
STATE_NAME = {None: "unreviewed", "correct": "marked correct", "wrong": "marked wrong", "fixed": "fixed",
              "still-wrong": "still wrong", "changed-since-correct": "changed since correct", "question": "question",
              "missing": "missing"}


def item(row: dict, url: str | None, **extra) -> dict:
    """A snapshot row as a facet item."""
    return {"key": row["key"], "value": row["value"], "status": row["status"], "course_key": row.get("course_key"),
            "page_stem": row["page_stem"], "signals": [s["signal"] for s in row.get("signals") or []], "url": url,
            **extra}


def nice_step(span: float, bins: int = BINS) -> int:
    """1, 2, 5, 10, 20, 50 … so that `span` fits in about `bins` bars."""
    raw = max(1.0, span / bins)
    mag = 10 ** math.floor(math.log10(raw))
    return int(next(m * mag for m in (1, 2, 5, 10) if m * mag >= raw))


def histogram(values: dict[str, int | None], unit: str) -> tuple[dict[str, list[str]], list[str]]:
    """Equal-width bars over the 1st–99th percentile; the tail goes to the last bar ("≥ 1,400 chars")."""
    nums = sorted(v for v in values.values() if v is not None)
    if not nums:
        return {k: [EMPTY] for k in values}, [EMPTY]
    lo, hi = nums[0], nums[min(len(nums) - 1, (99 * len(nums)) // 100)]
    step = nice_step(hi - lo + 1)
    start = (lo // step) * step
    last = start + step * max(0, (hi - start) // step)

    def name(v: int) -> str:
        if v >= last and nums[-1] >= last + step:
            return f"≥ {last:,} {unit}"
        b = start + step * ((v - start) // step)
        if step == 1:
            return f"{b:,} {unit[:-1] if b == 1 and unit.endswith('s') else unit}"
        return f"{b:,}–{b + step - 1:,} {unit}"

    out = {k: [name(v) if v is not None else EMPTY] for k, v in values.items()}
    order, seen = [], set()
    for v in nums:
        n = name(v)
        if n not in seen:
            seen.add(n)
            order.append(n)
    return out, order + ([EMPTY] if any(v is None for v in values.values()) else [])


def _categorical(values: dict[str, list[str]], cap: int = MAX_BUCKETS) -> tuple[dict[str, list[str]], list[str]]:
    """Biggest buckets first; past `cap`, the smallest are merged into "other"."""
    c = Counter(b for bs in values.values() for b in bs)
    order = sorted(c, key=lambda b: (-c[b], b))
    if len(order) > cap:
        keep = set(order[:cap - 1])
        values = {k: sorted({b if b in keep else OTHER for b in bs}) for k, bs in values.items()}
        order = order[:cap - 1] + [OTHER]
    return values, order


def _has(item: dict) -> bool:
    return item["status"] == "found" and bool((item["value"] or "").strip())


def _label(text: str) -> str:
    """'LIMITATION ON ENROLLMENT' and 'Limitation on Enrollment' are the same label."""
    t = " ".join(text.split()).lower()
    return t[:1].upper() + t[1:] + ":"


def _paragraphs(v: str) -> str:
    n = len([p for p in re.split(r"\n\s*\n|\n", v) if p.strip()])
    return f"{n} paragraph{'s' if n != 1 else ''}" if n < 4 else "4+ paragraphs"


def dimensions(kind: str, items: list[dict]) -> list[dict]:
    """[{id, label, help, values: {key: [bucket, …]}, order: [bucket, …]}] for these items (one rule, or several on
    Compare). Dimensions that don't apply to this kind of rule, or have no data, are left out."""
    dims: list[dict] = []

    def add(did: str, label: str, help_: str, values: dict[str, list[str]], order: list[str]) -> None:
        dims.append({"id": did, "label": label, "help": help_, "values": values, "order": order})

    keys = [i["key"] for i in items]
    if len({i.get("rule") for i in items}) > 1:
        add("rule", "Rule", "which rule the record belongs to",
            *_categorical({i["key"]: [i["rule"]] for i in items}, cap=50))
    if any("change" in i for i in items):
        add("change", "Change", "how the value changed from A to B",
            *_categorical({i["key"]: [i.get("change") or "unchanged"] for i in items}))
    if kind != "page":
        add("length", "Length", "characters in the value (an equal-width histogram)",
            *histogram({i["key"]: len(i["value"].strip()) if _has(i) else None for i in items}, "chars"))
    if kind == "field":
        found = [i for i in items if _has(i)]
        add("paragraphs", "Paragraphs", "lines of text in the value",
            {i["key"]: [_paragraphs(i["value"]) if _has(i) else EMPTY] for i in items},
            [f"{n} paragraph{'s' if n != 1 else ''}" for n in (1, 2, 3)] + ["4+ paragraphs", EMPTY])
        lead = {i["key"]: [_label(m.group(1)) if (m := LEAD.match(i["value"] or "")) else NONE] for i in items}
        add("lead", "Leading label", "a label at the start of the value, like “Prerequisite:”", *_categorical(lead))
        if any("before" in i for i in items):
            lead_a = {i["key"]: [_label(m.group(1)) if (m := LEAD.match(i.get("before") or "")) else NONE]
                      for i in items}
            add("lead_a", "Leading label in A", "the label at the start of the value before the change",
                *_categorical(lead_a))
        distinct = {(i["value"] or "").strip() for i in found}
        shapes = {shape(i["value"]) for i in found}
        if len(distinct) <= FEW_VALUES:
            add("value", "Value", "the value itself",
                *_categorical({i["key"]: [f"“{i['value'].strip()[:40]}”" if _has(i) else EMPTY] for i in items}))
        elif len(shapes) <= FEW_VALUES:
            add("shape", "Shape", "letters → A, digits → 9",
                *_categorical({i["key"]: [f"“{shape(i['value'])[:40]}”" if _has(i) else EMPTY] for i in items}))
    if any(i.get("course_key") for i in items):
        add("subject", "Subject", "the letters of the course code",
            *_categorical({i["key"]: [subject(i) or "—"] for i in items}))
    add("url", "URL pattern", "the page's URL path, numbers → 9, last part → *",
        *_categorical({i["key"]: [url_pattern(i.get("url") or "")] for i in items}))
    if any(i.get("on_page") is not None for i in items):
        add("on_page", "Courses on the page", "how many courses the page holds",
            *histogram({i["key"]: i.get("on_page") for i in items}, "courses"))
    add("signals", "Signals", "the signals on the record (a record can have several)",
        *_categorical({i["key"]: sorted(set(i.get("signals") or [])) or ["no signal"] for i in items}))
    if any("state" in i for i in items):
        add("review", "Review", "the record's review state",
            *_categorical({i["key"]: [STATE_NAME.get(i.get("state"), i.get("state") or "unreviewed")] for i in items}))
    for d in dims:  # every key has a bucket
        for k in keys:
            d["values"].setdefault(k, [EMPTY])
    return dims


def parse_filters(raw: list[str] | None) -> dict[str, set[str]]:
    """`["length:0–99 chars", "lead:Prerequisite:"]` → {dimension: {bucket}} (split on the first colon)."""
    out: dict[str, set[str]] = {}
    for f in raw or []:
        did, sep, bucket = f.partition(":")
        if sep and did:
            out.setdefault(did, set()).add(bucket)
    return out


def matches(dims: list[dict], filters: dict[str, set[str]]) -> set[str] | None:
    """Keys that pass every filter; None when there is no filter. A filter on an unknown dimension matches nothing."""
    if not filters:
        return None
    by_id = {d["id"]: d for d in dims}
    keys: set[str] | None = None
    for did, want in filters.items():
        d = by_id.get(did)
        hit = {k for k, bs in d["values"].items() if want & set(bs)} if d else set()
        keys = hit if keys is None else keys & hit
    return keys or set()


def histograms(dims: list[dict], keys: list[str] | set[str], filters: dict[str, set[str]] | None = None) -> list[dict]:
    """[{id, label, help, uniform, spread, buckets: [{id, count, on}]}] over `keys` (the list before filtering).
    A dimension's counts apply every filter but its own. `spread` (0–1, normalized entropy) says how evenly the rows
    split; dimensions come most evenly split first, uniform ones last."""
    filters = filters or {}
    keys = set(keys)
    out = []
    for d in dims:
        others = {k: v for k, v in filters.items() if k != d["id"]}
        allowed = keys if not others else keys & (matches(dims, others) or set())
        c = Counter(b for k in allowed for b in set(d["values"].get(k, [])))
        every = Counter(b for k in keys for b in set(d["values"].get(k, [])))
        used = [b for b in d["order"] if every[b]]
        total = sum(every[b] for b in used)
        ps = [every[b] / total for b in used] if total else []
        spread = round(-sum(p * math.log(p) for p in ps if p) / math.log(len(ps)), 4) if len(ps) > 1 else 0.0
        out.append({"id": d["id"], "label": d["label"], "help": d["help"], "uniform": len(used) <= 1,
                    "spread": spread, "buckets": [{"id": b, "count": c[b], "on": b in filters.get(d["id"], set())}
                                                  for b in used]})
    out.sort(key=lambda h: (h["uniform"], -h["spread"]))
    return out


#: Never crossed automatically: one bucket per rule or review state says nothing about the values, and a record
#: can have several signals.
NOT_CROSSED = ("rule", "review", "signals")
MAX_CROSS, MAX_CROSS_BUCKETS = 3, 8


def pick_cross(dims: list[dict], keys: list[str] | set[str]) -> list[str]:
    """The dimensions Autostratify crosses by default: the (up to 3) that split `keys` most evenly, among those with
    2–8 buckets."""
    hs = histograms(dims, keys)
    ok = [h for h in hs if not h["uniform"] and h["id"] not in NOT_CROSSED and len(h["buckets"]) <= MAX_CROSS_BUCKETS]
    return [h["id"] for h in ok[:MAX_CROSS]]


def _rnd(seed: str | int, key: str) -> str:
    return hashlib.sha1(f"{seed}:{key}".encode()).hexdigest()


def shuffle(keys: list[str], seed: str | int = 0) -> list[str]:
    return sorted(keys, key=lambda k: _rnd(seed, k))


def auto_strata(dims: list[dict], keys: list[str], cross: list[str], per_cell: int = 3,
                seed: str | int = 0) -> tuple[list[str], list[dict]]:
    """(keys in Autostratify order, cells: [{buckets: {dimension: bucket}, rows}] rarest first).

    Every combination of the crossed dimensions' buckets that has rows is a cell. Round 1 deals `per_cell` rows from
    each cell, rarest cell first (the combinations least like the bulk of the rows); then round 2 the next
    `per_cell`, and so on, so every row is listed once."""
    by_id = {d["id"]: d for d in dims}
    cross = [c for c in cross if c in by_id]
    cells: dict[tuple, list[str]] = {}
    for k in shuffle(keys, seed):
        cell = tuple((by_id[c]["values"].get(k) or [EMPTY])[0] for c in cross)
        cells.setdefault(cell, []).append(k)
    ranked = sorted(cells, key=lambda c: (len(cells[c]), _rnd(seed, "\t".join(c))))
    out, i = [], 0
    while len(out) < len(keys):
        for c in ranked:
            out.extend(cells[c][i:i + per_cell])
        i += per_cell
    return out, [{"buckets": dict(zip(cross, c)), "rows": len(cells[c])} for c in ranked]


def tags(dims: list[dict], key: str, dim_ids: list[str]) -> list[dict]:
    """[{dim, label, bucket}] of one row for these dimensions: why the row is in the list."""
    by_id = {d["id"]: d for d in dims}
    return [{"dim": i, "label": by_id[i]["label"], "bucket": ", ".join(by_id[i]["values"].get(key) or [EMPTY])}
            for i in dim_ids if i in by_id]


ORDERS = ("review", "auto", "shuffle")


def sample_order(dims: list[dict], keys: list[str], filters: dict[str, set[str]], order: str,
                 cross: list[str] | None, seed: int) -> tuple[list[str], dict]:
    """Filter `keys` (already in the caller's default order), order them, and describe it for the drawer:
    (keys, {order, cross, cells, seed, histograms, total, listed}). `order`: review (the caller's), auto, shuffle."""
    keep = matches(dims, filters)
    listed = [k for k in keys if keep is None or k in keep]
    info: dict = {"order": order, "seed": seed, "total": len(keys), "listed": len(listed),
                  "histograms": histograms(dims, keys, filters), "cross": [], "cells": []}
    if order == "shuffle":
        listed = shuffle(listed, seed)
    elif order == "auto":
        cross = [c for c in (cross if cross is not None else pick_cross(dims, listed))][:MAX_CROSS + 2]
        listed, cells = auto_strata(dims, listed, cross, seed=seed)
        info["cross"], info["cells"] = cross, cells[:200]
        info["cell_count"] = len(cells)
    info["tag_dims"] = list(dict.fromkeys([*info["cross"], *filters]))
    return listed, info
