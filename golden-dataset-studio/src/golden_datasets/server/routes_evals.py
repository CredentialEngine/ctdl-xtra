"""Evals API (docs/qrspi/evals): xtra runs, evals, the jobs that make them, and one view of an eval.

The view answers everything the tab draws for one eval, one golden (hand / full) and a set of segment filters:
outcomes by property for both goldens, the similarity histogram, each dimension's buckets, a heatmap of one
dimension × property, the segments that disagree most, and a page of rows, worst first. An eval has a few thousand
rows per golden, so it is read once (fields.parquet is immutable) and cut in Python.

Filters are `dim=bucket` strings: buckets of one dimension are ORed, dimensions are ANDed (as in the Sample drawer).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Query, Request

from .. import evals, model
from ..errors import UserError
from .jobs import Jobs
from .state import not_found, studio

router = APIRouter(prefix="/api")
COUNTED = ("exact", "partial", "wrong", "missing")
BINS = 20
MIN_SEGMENT = 5   # "disagree most" ignores smaller segments
DISAGREE_SHOWN = 8


def _sim(r: dict) -> str:
    if r["outcome"] == "exact":
        return "1 (exact)"
    if r["outcome"] == "missing":
        return "missing"
    s = r["similarity"] or 0.0
    return "0.95–1" if s >= 0.95 else "0.90–0.95" if s >= 0.9 else "0.80–0.90" if s >= 0.8 else \
        "0.50–0.80" if s >= 0.5 else "< 0.50"


def _level(r: dict) -> str:
    m = re.search(r"\d+", r["golden_record_id"] or "")
    if not m:
        return "?"
    d = m.group(0)
    return f"{d[0]}00s" if len(d) >= 3 else "< 100"


def _length(r: dict) -> str:
    n = len(r["golden_value"] or "")
    return "< 20 chars" if n < 20 else "20–99" if n < 100 else "100–499" if n < 500 else "500+"


def _on_page(r: dict) -> str:
    n = r["courses_on_page"] or 1
    return "1" if n == 1 else "2–5" if n <= 5 else "6+"


# id, label, bucket of a row. Order is the order of the filter menus.
DIMS = [
    ("property", "Property", lambda r: r["property"]),
    ("outcome", "Outcome", lambda r: r["outcome"]),
    ("similarity", "Similarity", _sim),
    ("approval", "Value approved by", lambda r: r["approval"] or "?"),
    ("record_approval", "Record approved by", lambda r: r["record_approval"] or "?"),
    ("approved_by", "Approver", lambda r: r["approved_by"] or "—"),
    ("template", "Extractor (template)", lambda r: r["template_id"] or "(no record)"),
    ("page_status", "Page status", lambda r: r["page_status"]),
    ("subject", "Subject", lambda r: (re.match(r"[A-Za-z]+", r["golden_record_id"] or "") or [None])[0] or "?"),
    ("level", "Course level", _level),
    ("courses_on_page", "Courses on the page", _on_page),
    ("length", "Golden value length", _length),
]
DIM = {d[0]: d for d in DIMS}
NOT_SEGMENTS = ("property", "outcome", "similarity")  # outcomes, not segments: left out of "disagree most"


def _jobs(request: Request) -> Jobs:
    app = request.app
    if not hasattr(app.state, "jobs"):
        app.state.jobs = Jobs()
    return app.state.jobs


def _allowed(request: Request) -> None:
    if not getattr(request.app.state, "allow_runs", False):
        raise HTTPException(403, "starting runs is off: restart the Studio with `golden-datasets serve --allow-runs`")


def _rows(st, ctx, eid: str) -> list[dict]:
    key = ("eval-rows", ctx.catalog, eid)
    if key not in st.cache:
        rows = ctx.rows(f"{evals.eval_dir(ctx, eid)}/fields.parquet")
        for r in rows:
            r["_b"] = {d: f(r) for d, _, f in DIMS}
        st.cache[key] = rows
    return st.cache[key]


def _parse(filters: list[str]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for f in filters:
        d, _, b = f.partition("=")
        if d in DIM:
            out[d].add(b)
    return out


def _keep(r: dict, flt: dict[str, set[str]], skip: str | None = None) -> bool:
    return all(r["_b"][d] in bs for d, bs in flt.items() if d != skip)


def _by_property(rows: list[dict]) -> list[dict]:
    acc: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        acc[r["property"]][r["outcome"]] += 1
    order = model.PROPERTY_ORDER
    return [{"property": p, "fields": sum(c[o] for o in COUNTED), **{o: c[o] for o in COUNTED}}
            for p, c in sorted(acc.items(), key=lambda kv: (order.get(kv[0], 99), kv[0]))]


def _rate(rows: list[dict]) -> float | None:
    return round(sum(r["outcome"] == "exact" for r in rows) / len(rows), 4) if rows else None


@router.get("/catalogs/{catalog}/evals")
def evals_index(request: Request, catalog: str) -> dict:
    st = studio(request)
    ctx = st.ctx(catalog)
    run_docs = [ctx.read_json(f"{r['path']}/run.json") for r in evals.runs(ctx)]
    eval_docs = [ctx.read_json(f"{e['path']}/eval.json") for e in evals.evals(ctx)]
    jobs = _jobs(request)
    return {"runs": run_docs[::-1], "evals": eval_docs[::-1], "goldens": evals.golden_options(ctx),
            "default_ref": evals.DEFAULT_XTRA_REF, "allow_runs": bool(getattr(request.app.state, "allow_runs", False)),
            "jobs": [j.doc(tail=40) for j in jobs.recent(ctx.catalog)]}


@router.post("/catalogs/{catalog}/xtra-runs")
def start_run(request: Request, catalog: str, body: Annotated[dict, Body()]) -> dict:
    _allowed(request)
    ctx = studio(request).ctx(catalog)
    ref, sample = body.get("ref") or evals.DEFAULT_XTRA_REF, bool(body.get("sample"))
    then_eval, by, imp = body.get("then_eval"), body.get("by") or "", bool(body.get("import"))

    def work(job) -> dict:
        hook = lambda p: setattr(job, "proc", p)  # noqa: E731
        if imp:
            doc = evals.import_run(ctx, by=by, log=job.log)
        else:
            doc = evals.extract_run(ctx, ref, sample=sample, discovery_run=body.get("discovery_run"), by=by,
                                    log=job.log, proc_hook=hook)
        out = {"run": doc["id"]}
        if then_eval and not job.cancelled:
            out["eval"] = evals.run_eval(ctx, doc["id"], then_eval, by=by, log=job.log, proc_hook=hook)["id"]
        return out

    label = "Import records/" if imp else f"xtra extract ({'golden sample' if sample else 'all pages'}) at {ref}"
    try:
        return _jobs(request).start(ctx.catalog, "xtra-run", label, work).doc()
    except UserError as e:
        raise HTTPException(409, str(e)) from None


@router.post("/catalogs/{catalog}/evals")
def start_eval(request: Request, catalog: str, body: Annotated[dict, Body()]) -> dict:
    _allowed(request)
    ctx = studio(request).ctx(catalog)
    run, golden, by = body.get("xtra_run"), body.get("golden") or "published", body.get("by") or ""
    if not run:
        raise HTTPException(400, "xtra_run is required")

    def work(job) -> dict:
        return {"eval": evals.run_eval(ctx, run, golden, by=by, log=job.log,
                                       proc_hook=lambda p: setattr(job, "proc", p))["id"]}

    try:
        return _jobs(request).start(ctx.catalog, "eval", f"Eval {run} vs {golden}", work).doc()
    except UserError as e:
        raise HTTPException(409, str(e)) from None


@router.get("/jobs/{jid}")
def job(request: Request, jid: str) -> dict:
    j = _jobs(request).get(jid)
    if not j:
        raise not_found(f"{jid}: no such job")
    return j.doc()


@router.post("/jobs/{jid}/cancel")
def cancel(request: Request, jid: str) -> dict:
    _allowed(request)
    j = _jobs(request).cancel(jid)
    if not j:
        raise not_found(f"{jid}: no such job")
    return j.doc()


@router.get("/catalogs/{catalog}/evals/{eid}")
def view(request: Request, catalog: str, eid: str, golden: str = "full",
         f: Annotated[list[str] | None, Query()] = None, dim: str = "template", offset: int = 0,
         limit: int = 50) -> dict:
    st = studio(request)
    ctx = st.ctx(catalog)
    if eid not in {e["id"] for e in evals.evals(ctx)}:
        raise not_found(f"{eid}: no such eval")
    doc = ctx.read_json(f"{evals.eval_dir(ctx, eid)}/eval.json")
    every = [r for r in _rows(st, ctx, eid) if r["outcome"] in COUNTED]
    flt = _parse(f or [])
    dim = dim if dim in DIM else "template"
    mine = [r for r in every if r["golden"] == golden]
    kept = [r for r in mine if _keep(r, flt)]

    goldens = {}
    for g in evals.KINDS:
        rows = [r for r in every if r["golden"] == g and _keep(r, flt)]
        goldens[g] = {"fields": len(rows), "exact_match_rate": _rate(rows), "by_property": _by_property(rows),
                      "unfiltered_fields": sum(r["golden"] == g for r in every)}

    hist = [{"lo": i / BINS, "hi": (i + 1) / BINS, "partial": 0, "wrong": 0} for i in range(BINS)]
    for r in kept:
        if r["outcome"] in ("partial", "wrong") and r["similarity"] is not None:
            hist[min(int(r["similarity"] * BINS), BINS - 1)][r["outcome"]] += 1

    dims = []
    for d, label, _ in DIMS:
        c = Counter(r["_b"][d] for r in mine if _keep(r, flt, skip=d))
        dims.append({"id": d, "label": label, "selected": sorted(flt.get(d, [])),
                     "buckets": [{"bucket": b, "n": n} for b, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))]})

    props = [p["property"] for p in _by_property(kept)]
    base = {p: 1 - (_rate([r for r in kept if r["property"] == p]) or 0) for p in props}
    cells: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for r in kept:
        c = cells[r["_b"][dim]][r["property"]]
        c["n"] += 1
        c["bad"] += r["outcome"] != "exact"
    heat = sorted(({"bucket": b, "n": sum(c["n"] for c in pc.values()), "bad": sum(c["bad"] for c in pc.values()),
                    "cells": {p: {"n": c["n"], "bad": c["bad"]} for p, c in pc.items()}} for b, pc in cells.items()),
                  key=lambda h: (-h["n"], h["bucket"]))

    seg: dict[tuple, Counter] = defaultdict(Counter)
    for r in kept:
        for d, _, _ in DIMS:
            if d in NOT_SEGMENTS or d in flt:
                continue
            c = seg[(d, r["_b"][d], r["property"])]
            c["n"] += 1
            c["bad"] += r["outcome"] != "exact"
    disagree = []
    for (d, b, p), c in seg.items():
        rate = c["bad"] / c["n"]
        if c["n"] >= MIN_SEGMENT and rate > base[p] and c["n"] < sum(r["property"] == p for r in kept):
            disagree.append({"dim": d, "dim_label": DIM[d][1], "bucket": b, "property": p, "n": c["n"],
                             "bad": c["bad"], "rate": round(rate, 4), "base": round(base[p], 4),
                             "excess": round(c["bad"] - base[p] * c["n"], 1)})
    disagree.sort(key=lambda x: -x["excess"])

    def order(r: dict) -> tuple:
        o = r["outcome"]
        return (o != "missing", o == "exact", r["similarity"] if r["similarity"] is not None else 0, r["page_stem"])

    page = sorted(kept, key=order)[offset:offset + limit]
    items = [{k: v for k, v in r.items() if k != "_b"} for r in page]
    return {"eval": doc, "golden": golden, "filters": {d: sorted(b) for d, b in flt.items()}, "goldens": goldens,
            "histogram": hist, "dims": dims, "heatmap": {"dim": dim, "label": DIM[dim][1], "properties": props,
                                                         "base": base, "rows": heat},
            "disagree": disagree[:DISAGREE_SHOWN], "rows": {"total": len(kept), "offset": offset, "items": items}}
