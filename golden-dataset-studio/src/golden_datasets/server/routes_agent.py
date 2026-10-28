"""Agent runs API (docs/qrspi/k2-runs/03-spec.md §7): start a run of Claude on the remote agent (the golden-rules
agent on K2), watch it, cancel it. The state lives on the root (agent_runs.py), so every Studio shows the same run,
and each poll of `current` also moves the run forward (sends a waiting run, ends one past its deadline).

A start that can't reach the agent answers 502 with `fallback: "prompt"`: the UI then opens the prompt with a warning
that the Remote AI rule generator couldn't be reached.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..agent_runs import AGENT_NAME, AgentRuns, Fallback, RunConflict, iso, now
from ..errors import ConflictError, UserError
from ..loop import current_review
from ..prompt import build_first_rules_prompt, build_prompt, scope_rules
from .state import Studio, not_found, studio

router = APIRouter(prefix="/api")


class Scope(BaseModel):
    """Every rule that needs work, or a new catalog's first rules. (A run always covers every rule: there is no
    one-rule run.)"""
    kind: Literal["needs_work", "first_rules"]


class StartBody(BaseModel):
    scope: Scope
    author: str


class ByBody(BaseModel):
    author: str
    outcome: str | None = None


def _runs(st: Studio, catalog: str) -> AgentRuns:
    return AgentRuns(st.ctx(catalog), st.k2, st.agent_minutes)


@router.get("/agent-runs/config")
def config(request: Request) -> dict:
    st = studio(request)
    return {"enabled": st.k2 is not None, "off_reason": st.agent_off, "agent_name": AGENT_NAME,
            "k2_url": st.k2.url if st.k2 else None, "agent": st.k2.agent if st.k2 else None,
            "minutes": st.agent_minutes, "prompt_users": st.prompt_users}


@router.get("/catalogs/{catalog}/agent-runs/current")
def current(request: Request, catalog: str, since: int = 0) -> dict:
    """{run, last, notes, now}: the live run (moved forward first) or null; when none is live, the latest that
    ended; and the notes of whichever is shown, from line `since`."""
    runs = _runs(studio(request), catalog)
    try:
        run = runs.advance()
    except ConflictError:
        run = runs.live()[0]
    last = None if run else runs.last()
    shown = run or last
    return {"run": run, "last": last, "notes": runs.notes(shown["run_id"], since) if shown else [],
            "since": since, "now": iso(now())}


def _check_scope(st: Studio, catalog: str, scope: Scope) -> None:
    """Refuse a run with nothing to do before taking the lock."""
    ctx = st.ctx(catalog)
    if scope.kind == "first_rules":
        if ctx.ruleset_versions():
            raise HTTPException(400, f"{catalog} already has rules: improve them instead")
        return
    if not scope_rules(current_review(ctx), None, True):
        raise HTTPException(400, "Nothing to fix: no rule has open wrong or missing verdicts")


@router.post("/catalogs/{catalog}/agent-runs", status_code=201)
def start(request: Request, catalog: str, body: StartBody):
    st = studio(request)
    if st.k2 is None:
        return JSONResponse({"detail": f"runs are off: {st.agent_off}", "fallback": "prompt",
                                  "reason": st.agent_off}, status_code=503)
    if not body.author.strip():
        raise HTTPException(400, "pick who you are first")
    try:
        _check_scope(st, catalog, body.scope)
    except UserError as exc:
        raise not_found(str(exc)) from None
    ctx = st.ctx(catalog)
    sc = body.scope

    def build(run: dict) -> dict:
        if sc.kind == "first_rules":
            return build_first_rules_prompt(ctx, target="k2", azure_root=st.azure_root, run=run)
        return build_prompt(ctx, None, True, rv=current_review(ctx), target="k2", azure_root=st.azure_root, run=run)

    runs = _runs(st, catalog)
    try:
        run = runs.start(sc.model_dump(), body.author.strip(), build)
    except RunConflict as exc:
        return JSONResponse({"detail": "a run is in progress on this catalog", "run": exc.run}, status_code=409)
    except Fallback as exc:
        return JSONResponse({"detail": exc.reason, "fallback": "prompt", "reason": exc.reason, "run": exc.run}, status_code=502)
    except UserError as exc:
        raise HTTPException(400, str(exc)) from None
    return {"run": run}


def _act(request: Request, catalog: str, fn) -> dict:
    runs = _runs(studio(request), catalog)
    try:
        return {"run": fn(runs)}
    except UserError as exc:
        raise HTTPException(409, str(exc)) from None
    except ConflictError:
        raise HTTPException(409, "the run changed meanwhile; look again") from None


@router.post("/catalogs/{catalog}/agent-runs/{run_id}/cancel")
def cancel(request: Request, catalog: str, run_id: str, body: ByBody) -> dict:
    return _act(request, catalog, lambda r: r.cancel(run_id, by=body.author))


@router.post("/catalogs/{catalog}/agent-runs/{run_id}/end")
def end(request: Request, catalog: str, run_id: str, body: ByBody) -> dict:
    return _act(request, catalog, lambda r: r.end(run_id, by=body.author, outcome=body.outcome))


@router.get("/catalogs/{catalog}/agent-runs")
def history(request: Request, catalog: str, limit: int = 20) -> list[dict]:
    return _runs(studio(request), catalog).history(limit)


@router.get("/catalogs/{catalog}/agent-runs/{run_id}")
def detail(request: Request, catalog: str, run_id: str) -> dict:
    """One run, live or past: its record, every progress note, and the agent's final report (Markdown) if it left one."""
    runs = _runs(studio(request), catalog)
    run = runs.run(run_id)
    if run is None:
        raise not_found(f"no run {run_id} on {catalog}")
    return {"run": run, "notes": runs.notes(run_id), "summary": runs.summary(run_id)}


@router.get("/catalogs/{catalog}/agent-runs/{run_id}/prompt")
def run_prompt(request: Request, catalog: str, run_id: str) -> dict:
    """The exact text the agent was sent."""
    text = _runs(studio(request), catalog).prompt(run_id)
    if text is None:
        raise not_found(f"no prompt for run {run_id}")
    return {"text": text}
