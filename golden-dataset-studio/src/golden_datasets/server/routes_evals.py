"""Evals API (Evals spec §4): extract outputs, and scores of one against a golden dataset.

- `GET  /catalogs/{c}/extract-outputs`: the outputs the Studio has seen (copied), newest first, with their scores;
  a new one is copied and scored against the latest golden dataset.
- `POST /catalogs/{c}/scores` `{golden, output, by}`: the score of that pair (the existing one, or `running`).
- `GET  /catalogs/{c}/scores`, `/scores/{id}`, `/scores/{id}/values` (one basis, narrowed by a column and an outcome,
  worst first, a page at a time).
"""

from __future__ import annotations

from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request

from .. import scores
from ..errors import UserError
from .jobs import ScoreJobs
from .state import not_found, studio

router = APIRouter(prefix="/api")
PAGE = 50


def jobs(request: Request) -> ScoreJobs:
    return request.app.state.scores


def _brief(doc: dict) -> dict:
    res = doc.get("results") or {}
    return {"id": doc["id"], "status": doc["status"], "golden": doc["golden"]["id"], "output": doc["output"]["id"],
            "created_at": doc["created_at"], "error": doc.get("error"),
            **{f"{b}_rate": (res.get(b) or {}).get("exact_match_rate") for b in scores.BASES},
            **{f"{b}_values": (res.get(b) or {}).get("values") for b in scores.BASES}}


@router.get("/catalogs/{catalog}/extract-outputs")
def extract_outputs(request: Request, catalog: str) -> dict:
    ctx = studio(request).ctx(catalog)
    error = None
    try:
        entry, new = scores.see_output(ctx)
        if new and scores.latest_golden(ctx):
            jobs(request)._quietly(ctx, None, "the Studio", f"a new extract output, {entry['id']}")
    except UserError as e:
        error = str(e)
    by_output: dict[str, list[dict]] = {}
    for doc in scores.all_scores(ctx):
        by_output.setdefault(doc["output"]["id"], []).append(_brief(doc))
    return {"outputs": [{**o, "scores": by_output.get(o["id"], [])} for o in reversed(scores.outputs(ctx))],
            "latest_golden": scores.latest_golden(ctx), "error": error, "running": jobs(request).busy(ctx.catalog)}


@router.get("/catalogs/{catalog}/scores")
def list_scores(request: Request, catalog: str) -> list[dict]:
    return [_brief(d) for d in scores.all_scores(studio(request).ctx(catalog))]


@router.post("/catalogs/{catalog}/scores")
def start_score(request: Request, catalog: str, body: Annotated[dict, Body()]) -> dict:
    """`golden`: ruleset-vN (default: the latest), human-reviewed or a draft rs-NNNN; `output`: a copy's id (default:
    the latest)."""
    ctx = studio(request).ctx(catalog)
    try:
        return jobs(request).start(ctx, body.get("golden"), body.get("output"), by=body.get("by") or "",
                                   reason="Score in the Studio")
    except UserError as e:
        raise HTTPException(409 if "still running" in str(e) else 400, str(e)) from None


def _doc(request: Request, catalog: str, sid: str):
    ctx = studio(request).ctx(catalog)
    try:
        return ctx, scores.read(ctx, sid)
    except UserError as e:
        raise not_found(str(e)) from None


@router.get("/catalogs/{catalog}/scores/{sid}")
def get_score(request: Request, catalog: str, sid: str) -> dict:
    return _doc(request, catalog, sid)[1]


def _counts(rows: list[dict]) -> dict:
    c = Counter(r["outcome"] for r in rows)
    return {"values": len(rows), **{o: c[o] for o in scores.OUTCOMES}}


@router.get("/catalogs/{catalog}/scores/{sid}/values")
def score_values(request: Request, catalog: str, sid: str, basis: str = "human", column: str | None = None,
                 outcome: str | None = None, offset: int = 0) -> dict:
    ctx, doc = _doc(request, catalog, sid)
    if doc["status"] != "done":
        raise HTTPException(409, f"{sid} is {doc['status']}")
    st = studio(request)
    key = ("score-values", ctx.catalog, sid)
    if key not in st.cache:  # values.parquet doesn't change once the score is done
        rows, seen = scores.values(ctx, sid), Counter()
        for r in rows:  # a stable key per value: page, course, column, and which of its values
            k = (r["basis"], r["page_stem"], r["entity"], r["column"])
            r["key"] = f"{r['page_stem']}|{r['entity']}|{r['column']}|{seen[k]}"
            seen[k] += 1
        st.cache[key] = rows
    mine = [r for r in st.cache[key] if r["basis"] == basis]
    in_col = [r for r in mine if not column or r["column"] == column]
    kept = [r for r in in_col if not outcome or r["outcome"] == outcome]
    by_col: dict[str, list[dict]] = {}
    for r in mine:
        by_col.setdefault(r["column"], []).append(r)
    order = {o: i for i, o in enumerate(scores.OUTCOMES)}
    page = sorted(kept, key=lambda r: (order[r["outcome"]], r["similarity"] if r["similarity"] is not None else 0,
                                       r["page_stem"], r["entity"]))[offset:offset + PAGE]
    return {"basis": basis, "result": doc["results"].get(basis), "total": _counts(mine),
            "columns": [{"column": c, **_counts(rs)} for c, rs in sorted(by_col.items())], "outcomes": _counts(in_col),
            "rows": {"total": len(kept), "offset": offset, "page": PAGE,
                     "items": page}}
