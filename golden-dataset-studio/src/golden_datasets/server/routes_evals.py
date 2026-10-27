"""Evals API (docs/qrspi/evals), in `xtra score`'s words: extractions (xtra runs), baselines, and scores.

- A **baseline** is what an extraction is scored against: `full` (every record of a Studio golden version: an
  extraction rs-NNNN or what is published), `hand` (only the values a person confirmed, from the same version), or
  `verified` (the xtra-golden-sets-verified container, all hand-checked).
- A **score** is one extraction against one baseline. An eval (ev-NNNN) holds the scores of one extraction against a
  golden version: `hand` and `full`, or just `verified`.

The score view answers what the tab draws for one score and three plain controls (a property, an outcome, and a
group by with one group picked): the match rate, the property table, the outcome counts, the groups, and a page of
rows, worst first. An eval has a few thousand rows per baseline, read once (fields.parquet is immutable) and cut in
Python.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request

from .. import evals, model
from ..errors import UserError
from .jobs import Jobs
from .state import not_found, studio

router = APIRouter(prefix="/api")
OUTCOMES = ("missing", "wrong", "partial", "match")  # ascending, as the legend reads
PAGE = 50


def _level(r: dict) -> str:
    m = re.search(r"\d+", r["golden_record_id"] or "")
    if not m:
        return "?"
    d = m.group(0)
    return f"{d[0]}00-level" if len(d) >= 3 else "under 100"


def _length(r: dict) -> str:
    n = len(r["golden_value"] or "")
    return "under 20 characters" if n < 20 else "20–99 characters" if n < 100 else "100–499 characters" if n < 500 \
        else "500+ characters"


# Group-by choices: id, label, the group of a row
GROUPS = [
    ("subject", "Subject", lambda r: (re.match(r"[A-Za-z]+", r["golden_record_id"] or "") or [None])[0] or "?"),
    ("level", "Course level", _level),
    ("length", "Length of the baseline value", _length),
    ("template", "xtra extractor", lambda r: r["template_id"] or "(no record)"),
    ("on_page", "Courses on the page", lambda r: "one" if (r["courses_on_page"] or 1) == 1 else "several"),
    ("approval", "Who approved the value", lambda r: f"a person ({r['approved_by']})" if r["approval"] == "human"
     else "its rule"),
]
GROUP = {g[0]: g for g in GROUPS}


def _outcome(r: dict) -> str:
    return "match" if r["outcome"] == "exact" else r["outcome"]


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
        rows = [r for r in ctx.rows(f"{evals.eval_dir(ctx, eid)}/fields.parquet")
                if r["outcome"] in ("exact", "partial", "wrong", "missing")]
        for r in rows:
            r["_o"] = _outcome(r)
            r["_g"] = {g: f(r) for g, _, f in GROUPS}
            r["key"] = f"{r['page_stem']}|{r['entity']}|{r['ctdl_property']}|{r['value_index']}"
        st.cache[key] = rows
    return st.cache[key]


def _baseline_id(kind: str, golden: str) -> str:
    return "verified" if golden == "verified" else kind


def _scores(eval_docs: list[dict]) -> list[dict]:
    out = []
    for e in eval_docs:
        g = e["golden"]["golden"]
        for kind, s in e["summary"].items():
            if g == "verified" and kind != "hand":
                continue  # older evals scored the verified container twice
            out.append({"eval": e["id"], "kind": kind, "baseline": _baseline_id(kind, g), "version": g,
                        "extraction": e["xtra_run"], "match_rate": s.get("exact_match_rate"),
                        "fields": s.get("fields_total"), "created_at": e["created_at"], "approved": e["golden"]["approved"]})
    return out


def _run_label(r: dict) -> dict:
    if r["kind"] == "import":
        title, detail = "Copied from xtra-cli-output", "the records/ xtra-cli last wrote for this crawl"
    else:
        title = f"xtra-cli {(r.get('ref') or '').removeprefix('origin/')} @ {(r.get('commit') or '')[:7]}"
        detail = "xtra-cli extract, run by the Studio"
    scope = {"sample": "review sample", "golden sample": "review sample", "all": "all course pages",
             "all pages": "all course pages"}.get(r.get("scope"), r.get("scope"))
    return {"id": r["id"], "kind": r["kind"], "title": title, "detail": detail, "scope": scope,
            "records": r.get("records_written"), "commit": r.get("commit"), "ref": r.get("ref"),
            "created_at": r.get("finished_at"), "commands": r.get("commands", [])}


@router.get("/catalogs/{catalog}/evals")
def evals_index(request: Request, catalog: str) -> dict:
    st = studio(request)
    ctx = st.ctx(catalog)
    run_docs = [ctx.read_json(f"{r['path']}/run.json") for r in evals.runs(ctx)]
    eval_docs = [ctx.read_json(f"{e['path']}/eval.json") for e in evals.evals(ctx)]
    key = ("extract-options", ctx.catalog)
    if key not in st.cache:
        st.cache[key] = evals.extract_options(ctx)
    versions = [{"id": g["id"], "label": g["label"], "approved": g["approved"]}
                for g in evals.golden_options(ctx) if g["id"] != "verified"]
    return {"extractions": [_run_label(r) for r in run_docs][::-1], "versions": versions,
            "scores": _scores(eval_docs)[::-1], "extract_options": st.cache[key],
            "default_ref": evals.DEFAULT_XTRA_REF, "allow_runs": bool(getattr(request.app.state, "allow_runs", False)),
            "jobs": [j.doc(tail=40) for j in _jobs(request).recent(ctx.catalog)]}


@router.get("/catalogs/{catalog}/evals/baseline")
def baseline_info(request: Request, catalog: str, baseline: str = "full", version: str | None = None) -> dict:
    """What one baseline holds: records, fields and the fields per property (cached per golden version)."""
    st = studio(request)
    ctx = st.ctx(catalog)
    golden = "verified" if baseline == "verified" else (version or ctx.latest_extraction())
    pubs = ctx.crawl_entry().get("golden", [])
    stamp = pubs[-1]["publication"] if golden == "published" and pubs else golden
    key = ("golden-pages", ctx.catalog, stamp)
    try:
        if key not in st.cache:
            st.cache[key] = evals.load_golden(ctx, golden, log=lambda _: None)
        pages, meta = st.cache[key]
    except UserError as e:
        raise not_found(str(e)) from None
    kind = "hand" if baseline in ("hand", "verified") else "full"
    return {"baseline": baseline, "version": golden, "approved": meta.get("approved", True),
            "from": meta.get("from") or meta.get("extraction"), **evals.baseline_stats(pages, kind)}


@router.post("/catalogs/{catalog}/xtra-runs")
def start_run(request: Request, catalog: str, body: Annotated[dict, Body()]) -> dict:
    _allowed(request)
    ctx = studio(request).ctx(catalog)
    ref, sample = body.get("ref") or evals.DEFAULT_XTRA_REF, body.get("scope", "sample") == "sample"
    then, by, use_latest = body.get("then_score"), body.get("by") or "", body.get("source") == "latest"

    def work(job) -> dict:
        hook = lambda p: setattr(job, "proc", p)  # noqa: E731
        if use_latest:
            doc = evals.import_run(ctx, by=by, log=job.log)
        else:
            doc = evals.extract_run(ctx, ref, sample=sample, by=by, log=job.log, proc_hook=hook)
        out = {"run": doc["id"]}
        if then and not job.cancelled:
            out["eval"] = evals.run_eval(ctx, doc["id"], then, by=by, log=job.log, proc_hook=hook)["id"]
        return out

    label = "Copy xtra-cli's latest records/" if use_latest else \
        f"xtra extract, {'review sample' if sample else 'all course pages'}, at {ref.removeprefix('origin/')}"
    try:
        return _jobs(request).start(ctx.catalog, "xtra-run", label, work).doc()
    except UserError as e:
        raise HTTPException(409, str(e)) from None


@router.post("/catalogs/{catalog}/evals")
def start_eval(request: Request, catalog: str, body: Annotated[dict, Body()]) -> dict:
    """Score an extraction against a golden version (`verified`, `published` or rs-NNNN)."""
    _allowed(request)
    ctx = studio(request).ctx(catalog)
    run, golden, by = body.get("xtra_run"), body.get("golden") or "published", body.get("by") or ""
    if not run:
        raise HTTPException(400, "xtra_run is required")

    def work(job) -> dict:
        return {"eval": evals.run_eval(ctx, run, golden, by=by, log=job.log,
                                       proc_hook=lambda p: setattr(job, "proc", p))["id"]}

    try:
        return _jobs(request).start(ctx.catalog, "eval", f"Score {run} against {golden}", work).doc()
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


def _counts(rows: list[dict]) -> dict:
    c = Counter(r["_o"] for r in rows)
    return {"fields": len(rows), **{o: c[o] for o in OUTCOMES}}


@router.get("/catalogs/{catalog}/evals/{eid}")
def view(request: Request, catalog: str, eid: str, kind: str = "full", property: str | None = None,
         outcome: str | None = None, group: str | None = None, value: str | None = None, offset: int = 0) -> dict:
    st = studio(request)
    ctx = st.ctx(catalog)
    if eid not in {e["id"] for e in evals.evals(ctx)}:
        raise not_found(f"{eid}: no such eval")
    doc = ctx.read_json(f"{evals.eval_dir(ctx, eid)}/eval.json")
    mine = [r for r in _rows(st, ctx, eid) if r["golden"] == kind]
    group = group if group in GROUP else None
    in_group = [r for r in mine if not (group and value is not None) or r["_g"][group] == value]
    in_prop = [r for r in in_group if not property or r["property"] == property]
    kept = [r for r in in_prop if not outcome or r["_o"] == outcome]

    order = model.PROPERTY_ORDER
    by_prop: dict[str, list[dict]] = defaultdict(list)
    for r in in_group:
        by_prop[r["property"]].append(r)
    groups = []
    if group:
        acc: dict[str, list[dict]] = defaultdict(list)
        for r in in_prop:
            acc[r["_g"][group]].append(r)
        groups = sorted(({"value": g, **_counts(rs)} for g, rs in acc.items()),
                        key=lambda x: (-(x["fields"] - x["match"]) / x["fields"], -x["fields"], x["value"]))

    def worst(r: dict) -> tuple:
        return (OUTCOMES.index(r["_o"]), r["similarity"] if r["similarity"] is not None else 0, r["page_stem"])

    page = sorted(kept, key=worst)[offset:offset + PAGE]
    records = {(r["page_stem"], r["entity"]) for r in mine}
    return {
        "eval": doc, "kind": kind, "baseline": _baseline_id(kind, doc["golden"]["golden"]),
        "total": {**_counts(mine), "records": len(records), "match_rate": doc["summary"][kind].get("exact_match_rate")},
        "properties": [{"property": p, **_counts(rs)} for p, rs in
                       sorted(by_prop.items(), key=lambda kv: (order.get(kv[0], 99), kv[0]))],
        "outcomes": _counts(in_prop), "groups": groups,
        "group_choices": [{"id": g, "label": label} for g, label, _ in GROUPS],
        "rows": {"total": len(kept), "offset": offset, "page": PAGE,
                 "items": [{k: v for k, v in r.items() if k not in ("_g",)} for r in page]},
    }
