"""Findings, property status and discussion (LearningProgram plan, Phase 6; `findings.py`), per class and property:

- `GET  /properties/{cls}/{column}/review`: the status, the findings with their units counted live (golden / silver per
  outcome and catalog, from each linked catalog's latest score), and each thread's comment count;
- `POST /properties/{cls}/{column}/status`: Needs review (anyone) or Done (the SME role: 403 otherwise);
- `POST /properties/{cls}/{column}/findings` and `PUT …/findings/{id}`: save a finding (fields, state, links);
- `GET|POST /properties/{cls}/{column}/threads`: a thread's comments, and a new one;
- `GET  /property-status?class=`: every property's status, for the score views' rows.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request

from .. import classes, findings, scores
from ..catalogs import resolve
from ..errors import UserError
from ..profiles import roles
from .routes_evals import _rows
from .state import REQUEST_CLASS, studio

router = APIRouter(prefix="/api")


@router.get("/properties/{cls}/{column}/review")
def review(request: Request, cls: str, column: str) -> dict:
    cls = _cls(cls)
    root = _root(request)
    threads: dict[str, int] = {}
    for c in findings.comments(root, cls, column):
        k = findings.thread_key(c["target"])
        threads[k] = threads.get(k, 0) + 1
    out = []
    for f in findings.findings(root, cls, column):
        live = _live(request, cls, column, f.get("links") or [])
        out.append({**f, "live": live, "comments": threads.get(f"finding:{f['id']}", 0)})
    return {"cls": cls, "column": column, "status": findings.status(root, cls, column), "findings": out,
            "threads": threads}


@router.post("/properties/{cls}/{column}/status")
def set_status(request: Request, cls: str, column: str, body: Annotated[dict, Body()]) -> dict:
    cls = _cls(cls)
    author = body.get("author") or ""
    try:
        return findings.set_status(_root(request), cls, column, body.get("status"), author, _role(request, author))
    except PermissionError as e:
        raise HTTPException(403, str(e)) from None
    except UserError as e:
        raise HTTPException(422, str(e)) from None


@router.post("/properties/{cls}/{column}/findings")
def add_finding(request: Request, cls: str, column: str, body: Annotated[dict, Body()]) -> dict:
    return _save(request, cls, column, body, None)


@router.put("/properties/{cls}/{column}/findings/{finding_id}")
def update_finding(request: Request, cls: str, column: str, finding_id: str, body: Annotated[dict, Body()]) -> dict:
    return _save(request, cls, column, body, finding_id)


@router.get("/properties/{cls}/{column}/threads")
def thread(request: Request, cls: str, column: str, key: str) -> list[dict]:
    cls = _cls(cls)
    return [c for c in findings.comments(_root(request), cls, column) if findings.thread_key(c["target"]) == key]


@router.post("/properties/{cls}/{column}/threads")
def comment(request: Request, cls: str, column: str, body: Annotated[dict, Body()]) -> dict:
    cls = _cls(cls)
    try:
        return findings.add_comment(_root(request), cls, column, body.get("author") or "", body.get("note") or "",
                                    body.get("target") or {})
    except KeyError:
        raise HTTPException(404, "no such finding") from None
    except UserError as e:
        raise HTTPException(422, str(e)) from None


@router.get("/property-status")
def property_status(request: Request) -> dict:
    return findings.statuses(_root(request), REQUEST_CLASS.get())


def _save(request: Request, cls: str, column: str, body: dict, finding_id: str | None) -> dict:
    cls = _cls(cls)
    try:
        return findings.save_finding(_root(request), cls, column, body.get("author") or "", body, finding_id)
    except KeyError:
        raise HTTPException(404, f"no finding {finding_id}") from None
    except UserError as e:
        raise HTTPException(422, str(e)) from None


# --- A finding's live units -------------------------------------------------------------------------------------


def _live(request: Request, cls: str, column: str, links: list[dict]) -> dict | None:
    """The units a finding's linked groups have in each catalog's latest score: {outcome: [golden, silver]} and the
    rows by catalog. None when it links no group."""
    if not links:
        return None
    st = studio(request)
    rows = [row for link in links if (row := link_units(request, st, cls, column, link)) is not None]
    totals = {o: [0, 0] for o in findings.COUNTED}
    for r in rows:
        if r["outcome"] in totals:
            totals[r["outcome"]] = [totals[r["outcome"]][0] + r["golden"], totals[r["outcome"]][1] + r["silver"]]
    return {"counts": {o: (v if v != [0, 0] or any(r["outcome"] == o for r in rows) else None)
                       for o, v in totals.items()}, "rows": rows}


def link_units(request: Request, st, cls: str, column: str, link: dict) -> dict | None:
    """One linked group's units in its catalog's latest scores; None when the catalog can't be opened."""
    try:
        ctx = st.ctx(resolve(link["catalog"]), cls)
    except (UserError, KeyError):
        return None
    golden, silver = (group_units(request, st, ctx, column, link, basis) for basis in ("human", "rule"))
    return {"catalog": link["catalog"], "outcome": link.get("outcome"), "by": link.get("by"),
            "key": link.get("key"), "golden": golden, "silver": silver}


def group_units(request: Request, st, ctx, column: str, link: dict, basis: str) -> int:
    sid = _newest(st, ctx, basis)
    if not sid:
        return 0
    doc = scores.read(ctx, sid)
    mine = [r for r in _rows(request, ctx, doc, sid) if r["basis"] == basis and r["column"] == column]
    units = 0
    for g in scores.wrong_groups(mine, link.get("group_by") or "auto"):
        if findings.link_key({**g, "catalog": link["catalog"]}) == findings.link_key(link):
            units = g["units"]
    return units


def _newest(st, ctx, basis: str) -> str | None:
    """The score a finding's units are counted in: the latest extract output's against the latest golden dataset,
    else the newest finished score on that basis (an output not scored yet doesn't zero every finding)."""
    sc = scores.latest_score(ctx, basis, st.cache)
    if sc:
        return sc["id"]
    for sid in reversed(scores.score_ids(ctx)):
        doc = scores.read(ctx, sid)
        if doc["status"] == "done" and (doc.get("results") or {}).get(basis):
            return sid
    return None


# --- Request details --------------------------------------------------------------------------------------------


def _cls(cls: str) -> str:
    try:
        return classes.get(cls).slug
    except UserError as e:
        raise HTTPException(422, str(e)) from None


def _root(request: Request):
    return studio(request).root


def _role(request: Request, author: str) -> str | None:
    return findings_role(_root(request), author)


def findings_role(root, author: str) -> str | None:
    try:
        return roles(root).get(author)
    except FileNotFoundError:
        return None
