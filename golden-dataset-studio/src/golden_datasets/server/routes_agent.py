"""AI runs API (docs/qrspi/one-rule-runs/03-spec.md §7, contract in 05-api-contract.md): put a run on a set of
rules in line, watch the catalog's live runs and the queue, read a run's report and its rows as they are now, pick
rules, revert a version.

Runs move forward in the Studio's background loop (agent_runs.Queue), never in these requests: K2 may take 30 s to
answer a start. A Studio whose loop isn't running (a test, or runs off) shows the runs as they are.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..agent_runs import AGENT_NAME, LIVE, Queue, RunConflict, iso, now, parse
from ..errors import ConflictError, UserError
from .state import Studio, not_found, studio

router = APIRouter(prefix="/api")


class Scope(BaseModel):
    """The rules to improve (`rules`), every rule that needs work (`needs_work`, made into a `rules` scope), or a new
    catalog's first rules."""
    kind: Literal["rules", "needs_work", "first_rules"]
    rules: list[str] | None = None


class StartBody(BaseModel):
    scope: Scope
    author: str
    studio_url: str | None = None  # the browser's address of this Studio: the run's report links back to it


class ByBody(BaseModel):
    author: str
    outcome: str | None = None


def _studio_url(request: Request, sent: str | None) -> str | None:
    """Where people open this Studio, for the report's links: what the browser sent (http(s) only), else its Origin."""
    for u in (sent, request.headers.get("origin")):
        if u and u.startswith(("https://", "http://")):
            u = u.split("#")[0].split("?")[0]
            return u if u.endswith("/") else u + "/"
    return None


def _latest(st: Studio, catalog: str):
    """The catalog's latest extraction and the annotation log."""
    from ..review import LOADER

    ctx = st.ctx(catalog)
    try:
        ext = ctx.latest_extraction()
    except UserError as exc:
        raise not_found(str(exc)) from None
    if not ext:
        raise not_found(f"{catalog}: no extraction yet")
    return LOADER.review(ctx, ext)


@router.get("/agent-runs/config")
def config(request: Request) -> dict:
    st = studio(request)
    return {"enabled": st.k2 is not None, "off_reason": st.agent_off, "agent_name": AGENT_NAME,
            "k2_url": st.k2.url if st.k2 else None, "agent": st.k2.agent if st.k2 else None,
            "minutes": st.agent_minutes, "prompt_users": st.prompt_users, "cap": st.agent_cap}


@router.get("/agent-runs/queue")
def queue(request: Request) -> dict:
    """Working runs and the line, across catalogs, with the estimate (spec §1.7)."""
    v = studio(request).queue.view()
    return {k: v[k] for k in ("cap", "working", "waiting", "median_min", "from_runs", "note")}


def _queue_of(v: dict, run: dict) -> dict:
    for w in v["working"]:
        if w["run"] == run["run_id"]:
            return {"place": None, "start_in_min": None, "left_min": w["left_min"],
                    "minutes_so_far": w["minutes_so_far"]}
    for w in v["waiting"]:
        if w["run"] == run["run_id"]:
            return {"place": w["place"], "start_in_min": w["start_in_min"], "left_min": None, "minutes_so_far": None}
    return {"place": None, "start_in_min": None, "left_min": None, "minutes_so_far": None}


@router.get("/catalogs/{catalog}/agent-runs/current")
def current(request: Request, catalog: str, since: int = 0) -> dict:
    """{runs, recent, slots, now}: the catalog's live runs (with their notes and place in line), each rule's latest
    ended run, and the places across catalogs. `run`, `last`, `notes`, `since`: the shape older Studios poll."""
    st = studio(request)
    ar = st.agent_runs(catalog)
    v = st.queue.view()
    runs = [dict(r, notes=ar.notes(r["run_id"]), queue=_queue_of(v, r)) for r in ar.live_runs()]
    recent = {rule: {k: x for k, x in b.items() if k != "rule_names"}
              | {"rule_name": (b.get("rule_names") or {}).get(rule, rule)}
              for rule, b in ar.goals().items() if b.get("state") not in LIVE}
    slots = {"cap": v["cap"], "live": v["slots"]["live"],
             "waiting": [{"run": w["run"], "catalog": w["catalog"], "since": w["since"], "place": w["place"]}
                         for w in v["waiting"]]}
    run = runs[0] if runs else None
    last = ar.last()  # the latest run that ended, live runs or not (the run bar shows its outcome)
    shown = run or last
    legacy = {"run": {k: x for k, x in run.items() if k not in ("notes", "queue")} if run else None, "last": last,
              "notes": ar.notes(shown["run_id"], since) if shown else [], "since": since}
    return {"runs": runs, "recent": recent, "slots": slots, "now": iso(now()), **legacy}


def _rules_with_feedback(rv, goals: dict) -> dict[str, dict]:
    """Per rule: open annotations, comments, verdicts and comments since its last run."""
    out = {}
    for rid in rv.snap.rules:
        st = rv.rule_status(rid)
        last = goals.get(rid) or {}
        since = last.get("annotations_as_of") or last.get("ended_at") if last.get("state") not in LIVE else None
        events = [e for e in rv.live if e["target"].get("rule_id") == rid and e["type"] in ("verdict", "comment")
                  and e.get("author_role") != "ai"]
        out[rid] = {"open": st["open_wrong"] + st["open_missing"],
                    "comments": sum(1 for e in events if e["type"] == "comment"),
                    "new_since_run": sum(1 for e in events if since and e["at"] > since),
                    "status": st["status"], "reviewed": st["reviewed"], "total": st["total"]}
    return out


@router.post("/catalogs/{catalog}/agent-runs", status_code=201)
def start(request: Request, catalog: str, body: StartBody):
    st = studio(request)
    if st.k2 is None:
        return JSONResponse({"detail": f"runs are off: {st.agent_off}", "fallback": "prompt",
                             "reason": st.agent_off}, status_code=503)
    if not body.author.strip():
        raise HTTPException(400, "pick who you are first")
    ctx = st.ctx(catalog)
    sc = body.scope
    names = {}
    scope = {"kind": "first_rules", "rules": []}
    if sc.kind == "first_rules":
        if ctx.ruleset_versions():
            raise HTTPException(400, f"{catalog} already has rules: improve them instead")
    else:
        from ..report import rule_names

        rv = _latest(st, catalog)
        names = rule_names(rv.snap.rules)
        ar = st.agent_runs(catalog)
        feedback = _rules_with_feedback(rv, ar.goals())
        if sc.kind == "needs_work":
            rules = [rid for rid in rv.snap.rules if feedback[rid]["status"] == "needs work"]
        else:
            rules = list(dict.fromkeys(sc.rules or []))
            unknown = [r for r in rules if r not in rv.snap.rules]
            if unknown:
                raise HTTPException(400, f"no rule {unknown[0]} in ruleset v{rv.snap.ruleset_version}")
        if not rules:
            raise HTTPException(400, "Nothing to improve: no rule was picked")
        if not any(feedback[r]["open"] or feedback[r]["new_since_run"] for r in rules):
            raise HTTPException(400, "Nothing to improve: none of these rules has open annotations or feedback "
                                     "since its last run")
        scope = {"kind": "rules", "rules": rules}
    ar = st.agent_runs(catalog)
    try:
        run = ar.start(scope, body.author.strip(), studio_url=_studio_url(request, body.studio_url),
                       rule_names=names)
    except RunConflict as exc:
        if exc.rule:
            name = names.get(exc.rule, exc.rule)
            return JSONResponse({"detail": f"{name} is being improved in {exc.run['started_by']}'s run",
                                 "rule": exc.rule, "rule_name": name, "run": exc.run}, status_code=409)
        return JSONResponse({"detail": "a run is in progress on this catalog", "run": exc.run}, status_code=409)
    except UserError as exc:
        raise HTTPException(400, str(exc)) from None
    st.queue.forget()
    v = st.queue.view()
    q = _queue_of(v, run)
    free = len(v["working"]) < v["cap"] and q["place"] == 1
    return {"run": run, "queue": {"place": q["place"], "start_in_min": 0 if free else q["start_in_min"]}}


def _act(request: Request, catalog: str, fn) -> dict:
    st = studio(request)
    try:
        out = {"run": fn(st.agent_runs(catalog))}
    except UserError as exc:
        raise HTTPException(409, str(exc)) from None
    except ConflictError:
        raise HTTPException(409, "the run changed meanwhile; look again") from None
    st.queue.forget()
    return out


@router.post("/catalogs/{catalog}/agent-runs/{run_id}/cancel")
def cancel(request: Request, catalog: str, run_id: str, body: ByBody) -> dict:
    return _act(request, catalog, lambda r: r.cancel(run_id, by=body.author))


@router.post("/catalogs/{catalog}/agent-runs/{run_id}/end")
def end(request: Request, catalog: str, run_id: str, body: ByBody) -> dict:
    return _act(request, catalog, lambda r: r.end(run_id, by=body.author, outcome=body.outcome))


@router.get("/catalogs/{catalog}/agent-runs")
def history(request: Request, catalog: str, limit: int = 20, rule: str | None = None) -> list[dict]:
    return studio(request).agent_runs(catalog).history(limit, rule=rule)


@router.get("/catalogs/{catalog}/agent-runs/{run_id}")
def detail(request: Request, catalog: str, run_id: str) -> dict:
    """One run, live or past: its record, every progress note, its report as Markdown (`summary`) and, for runs that
    left one, the resolved report the Studio renders (`report`)."""
    runs = studio(request).agent_runs(catalog)
    run = runs.run(run_id)
    if run is None:
        raise not_found(f"no run {run_id} on {catalog}")
    return {"run": run, "notes": runs.notes(run_id), "summary": runs.summary(run_id), "report": runs.report(run_id)}


@router.get("/catalogs/{catalog}/agent-runs/{run_id}/rows")
def run_rows(request: Request, catalog: str, run_id: str) -> dict:
    """The report's rows as they are now: verdict, byline, history (with Claude's comments), and how much feedback
    people gave on the rules the run touched since it read the annotations (spec §1.6)."""
    from ..report import row_keys
    from .routes_review import _event_brief, _review_state

    st = studio(request)
    runs = st.agent_runs(catalog)
    run = runs.run(run_id)
    if run is None:
        raise not_found(f"no run {run_id} on {catalog}")
    rep = runs.report(run_id) or {}
    as_of = run.get("annotations_as_of") or run.get("created_at")
    touched = list(dict.fromkeys(((run.get("scope") or {}).get("rules") or []) + (run.get("also_changed") or [])))
    rv = _latest(st, catalog)
    out = []
    by_course: dict[str, dict] = {}
    for rid, course in row_keys(rep):
        if rid not in rv.snap.rules:
            continue
        if rid not in by_course:
            rows = rv.snap.rows(rid)
            states = rv.row_states(rid, rows)
            by_course[rid] = {r["course_key"]: (r, states[r["key"]]) for r in reversed(rows) if r.get("course_key")}
        r, s = by_course[rid].get(course, (None, None))
        if r is None:
            continue

        def b(e: dict) -> dict:
            return _event_brief(e) | {"after_run": bool(as_of and e["at"] > as_of)}
        out.append({"rule": rid, "course": course, "page_stem": r["page_stem"], "key": r["key"],
                    "occurrence_key": r["occurrence_key"], "value": r["value"], "status": r["status"],
                    "state": s.state, "verdict": b(s.verdict) if s.verdict else None, **_review_state(s),
                    "history": [b(e) for e in s.events]})
    new = sum(1 for e in rv.live if e["type"] in ("verdict", "comment") and e.get("author_role") != "ai"
              and e["target"].get("rule_id") in touched and as_of and e["at"] > as_of)
    return {"run_id": run_id, "annotations_as_of": as_of, "rules_touched": touched, "new_feedback": new, "rows": out}


@router.get("/catalogs/{catalog}/agent-runs/{run_id}/prompt")
def run_prompt(request: Request, catalog: str, run_id: str) -> dict:
    """The exact text the agent was sent."""
    text = studio(request).agent_runs(catalog).prompt(run_id)
    if text is None:
        raise not_found(f"no prompt for run {run_id}")
    return {"text": text}


# =====================================================================================================
# The rule picker and revert
# =====================================================================================================
@router.get("/catalogs/{catalog}/rules/picker")
def picker(request: Request, catalog: str) -> dict:
    """The "Run with Claude?" dialog's rules: ticked by default when they have open annotations or feedback since
    their last run; held (and not tickable) while another live run is improving them."""
    from ..loop import ordered_rule_ids
    from ..publishing import downstream
    from ..report import rule_names

    st = studio(request)
    rv = _latest(st, catalog)
    ar = st.agent_runs(catalog)
    names = rule_names(rv.snap.rules)
    goals = ar.goals()
    feedback = _rules_with_feedback(rv, goals)
    held = {}
    t = now()
    for run in ar.live_runs():
        for r in run["scope"].get("rules") or []:
            held[r] = {"run_id": run["run_id"], "started_by": run["started_by"], "state": run["state"],
                       "since": run["created_at"], "minutes": int((t - parse(run["created_at"])).total_seconds() // 60)}
    out = []
    for rid in ordered_rule_ids(rv.snap.rules):
        f = feedback[rid]
        h = held.get(rid)
        last = goals.get(rid)
        ticked = h is None and bool(f["open"] or f["new_since_run"])
        if h:
            why = f"Being improved in {h['started_by']}'s run, {h['minutes']} min"
        else:
            bits = []
            if f["open"]:
                bits.append(f"{f['open']} open")
            if f["comments"]:
                bits.append(f"{f['comments']} comment{'' if f['comments'] == 1 else 's'}")
            if f["new_since_run"]:
                bits.append(f"{f['new_since_run']} new since its last run")
            why = ", ".join(bits) or "nothing open"
        down = downstream(rv.snap.rules, rid)
        out.append({"rule": rid, "name": names[rid], "kind": rv.snap.rules[rid]["kind"], "status": f["status"],
                    "reviewed": f["reviewed"], "total": f["total"], "open": f["open"], "comments": f["comments"],
                    "new_since_run": f["new_since_run"], "ticked": ticked, "why": why, "downstream": down,
                    "downstream_names": [names.get(d, d) for d in down], "held_by": h,
                    "last_run": {k: last.get(k) for k in ("run_id", "state", "ended_at")}
                    if last and last.get("state") not in LIVE else None})
    p = st.queue.next_place()
    return {"rules": out, "total_rules": len(out), "ticked": sum(r["ticked"] for r in out), "queue": p,
            "note": Queue.note_for(p)}


class RevertBody(BaseModel):
    author: str


def _revert_plan(st: Studio, catalog: str, version: int) -> tuple[dict, dict]:
    from ..publishing import revert_plan
    from ..report import rule_names

    ctx = st.ctx(catalog)
    ctx.invalidate()
    try:
        plan = revert_plan(ctx, version)
    except FileNotFoundError as exc:
        raise not_found(str(exc)) from None
    except UserError as exc:
        raise HTTPException(400, str(exc)) from None
    _, before = ctx.ruleset_rules(plan["parent"])
    _, now_rules = ctx.ruleset_rules(version)
    return plan, rule_names({**before, **now_rules})


@router.get("/catalogs/{catalog}/rulesets/{version}/revert")
def revert_preview(request: Request, catalog: str, version: int) -> dict:
    """What reverting this version would publish (writes nothing): the confirm's text."""
    from ..publishing import revert_text

    plan, names = _revert_plan(studio(request), catalog, version)
    return {"version": version, "next_version": plan["next_version"], "parent": plan["parent"],
            "rules": [r | {"name": names.get(r["rule"], r["rule"])} for r in plan["rules"]],
            "blocked": plan["blocked"], "text": revert_text(plan, names)}


@router.post("/catalogs/{catalog}/rulesets/{version}/revert")
def revert(request: Request, catalog: str, version: int, body: RevertBody) -> dict:
    """Publish one new version with every rule this version changed back to how it was (spec §3.6). Anyone may."""
    from ..publishing import LockBusy
    from ..publishing import revert as do_revert

    st = studio(request)
    if not body.author.strip():
        raise HTTPException(400, "pick who you are first")
    plan, _ = _revert_plan(st, catalog, version)
    if plan["blocked"]:
        raise HTTPException(409, plan["blocked"])
    try:
        return do_revert(st.ctx(catalog), version, f"{body.author.strip()} via the Studio UI (revert)",
                         say=lambda m: None, wait_s=60)
    except LockBusy as exc:
        raise HTTPException(409, f"{exc}; try again in a minute") from None
    except UserError as exc:
        raise HTTPException(409, str(exc)) from None

