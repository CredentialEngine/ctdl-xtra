"""AI runs API (docs/qrspi/one-rule-runs/03-spec.md §7, contract in 05-api-contract.md): put a run on a set of
rules in line, watch the catalog's live runs and the queue, read a run's report and its rows as they are now, pick
rules, revert a version.

Runs move forward in the Studio's background loop (agent_runs.Queue), never in these requests: K2 may take 30 s to
answer a start. A Studio whose loop isn't running (a test, or runs off) shows the runs as they are.

Routes are declared in the order FastAPI must match them (`agent-runs/current` before `agent-runs/{run_id}`).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .. import telemetry
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


class RevertBody(BaseModel):
    author: str


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


@router.get("/catalogs/{catalog}/agent-runs/current")
def current(request: Request, catalog: str, since: int = 0) -> dict:
    """{runs, recent, slots, now}: the catalog's live runs (with their notes and place in line), each rule's latest
    ended run, and the places across catalogs. `run`, `last`, `notes`, `since`: the shape older Studios poll."""
    st = studio(request)
    ar = st.agent_runs(catalog)
    v, live, goals, last = _read_at_once(st.queue.view, ar.live_runs, ar.goals, ar.last)
    runs = [dict(r, notes=ar.notes(r["run_id"]), queue=_queue_of(v, r)) for r in live]
    return {"runs": runs, "recent": _recent_runs(goals), "slots": _slots(v), "now": iso(now()),
            **_legacy_view(ar, runs, last, since)}


@router.post("/catalogs/{catalog}/agent-runs", status_code=201)
def start(request: Request, catalog: str, body: StartBody):
    st = studio(request)
    _describe_start(st, body.scope)
    if st.k2 is None:
        return JSONResponse({"detail": f"runs are off: {st.agent_off}", "fallback": "prompt",
                             "reason": st.agent_off}, status_code=503)
    _require_author(body.author)
    scope, names = _run_scope(st, catalog, body.scope)
    try:
        run = st.agent_runs(catalog).start(scope, body.author.strip(), rule_names=names,
                                           studio_url=_studio_url(request, body.studio_url))
    except RunConflict as exc:
        return _conflict_response(exc, names)
    except UserError as exc:
        raise HTTPException(400, str(exc)) from None
    return {"run": run, "queue": _place_in_line(st, run)}


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
    st = studio(request)
    runs = st.agent_runs(catalog)
    run = _run_or_404(runs, catalog, run_id)
    return {"run": run, "notes": runs.notes(run_id), "summary": runs.summary(run_id),
            "report": _with_revert_state(st, catalog, runs.report(run_id))}


@router.get("/catalogs/{catalog}/agent-runs/{run_id}/rows")
def run_rows(request: Request, catalog: str, run_id: str) -> dict:
    """The report's rows as they are now: verdict, byline, history (with Claude's comments), and how much feedback
    people gave on the rules the run touched since it read the annotations (spec §1.6)."""
    st = studio(request)
    runs = st.agent_runs(catalog)
    run = _run_or_404(runs, catalog, run_id)
    as_of = run.get("annotations_as_of") or run.get("created_at")
    touched = _rules_touched(run)
    rv = _latest(st, catalog)
    rows = _report_rows(rv, runs.report(run_id) or {}, as_of)
    return {"run_id": run_id, "annotations_as_of": as_of, "rules_touched": touched,
            "new_feedback": _count_new_feedback(rv, touched, as_of), "rows": rows}


@router.get("/catalogs/{catalog}/agent-runs/{run_id}/prompt")
def run_prompt(request: Request, catalog: str, run_id: str) -> dict:
    """The exact text the agent was sent."""
    text = studio(request).agent_runs(catalog).prompt(run_id)
    if text is None:
        raise not_found(f"no prompt for run {run_id}")
    return {"text": text}


@router.get("/catalogs/{catalog}/rules/picker")
def picker(request: Request, catalog: str) -> dict:
    """The "Run with Claude?" dialog's rules: ticked by default when they have open annotations or feedback since
    their last run; held (and not tickable) while another live run is improving them."""
    from ..loop import ordered_rule_ids
    from ..report import rule_names

    st = studio(request)
    rv = _latest(st, catalog)
    ar = st.agent_runs(catalog)
    names, goals = rule_names(rv.snap.rules), ar.goals()
    feedback, held = _rules_with_feedback(rv, goals), _held_rules(ar)
    rows = [_picker_row(rv, rid, names, feedback[rid], held.get(rid), goals.get(rid))
            for rid in ordered_rule_ids(rv.snap.rules)]
    place = st.queue.next_place()
    return {"rules": rows, "total_rules": len(rows), "ticked": sum(r["ticked"] for r in rows), "queue": place,
            "note": Queue.note_for(place)}


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
    st = studio(request)
    _require_author(body.author)
    plan, _ = _revert_plan(st, catalog, version)
    if plan["blocked"]:
        raise HTTPException(409, plan["blocked"])
    return _publish_revert(st.ctx(catalog), version, body.author.strip())


# ---- the live view --------------------------------------------------------------------------------------------

def _read_at_once(*readers) -> list:
    """Small files read side by side, not one round trip after another."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(telemetry.in_this_request(read)) for read in readers]
        return [future.result() for future in futures]


def _queue_of(v: dict, run: dict) -> dict:
    for w in v["working"]:
        if w["run"] == run["run_id"]:
            return {"place": None, "start_in_min": None, "left_min": w["left_min"],
                    "minutes_so_far": w["minutes_so_far"]}
    for w in v["waiting"]:
        if w["run"] == run["run_id"]:
            return {"place": w["place"], "start_in_min": w["start_in_min"], "left_min": None, "minutes_so_far": None}
    return {"place": None, "start_in_min": None, "left_min": None, "minutes_so_far": None}


def _recent_runs(goals: dict) -> dict:
    return {rule: {k: x for k, x in b.items() if k != "rule_names"}
            | {"rule_name": (b.get("rule_names") or {}).get(rule, rule)}
            for rule, b in goals.items() if b.get("state") not in LIVE}


def _slots(v: dict) -> dict:
    return {"cap": v["cap"], "live": v["slots"]["live"],
            "waiting": [{"run": w["run"], "catalog": w["catalog"], "since": w["since"], "place": w["place"]}
                        for w in v["waiting"]]}


def _legacy_view(ar, runs: list[dict], last: dict | None, since: int) -> dict:
    """`last` is the latest run that ended, live runs or not (the run bar shows its outcome)."""
    run = runs[0] if runs else None
    shown = run or last
    return {"run": {k: x for k, x in run.items() if k not in ("notes", "queue")} if run else None, "last": last,
            "notes": ar.notes(shown["run_id"], since) if shown else [], "since": since}


# ---- starting a run -------------------------------------------------------------------------------------------

def _describe_start(st: Studio, scope: Scope) -> None:
    telemetry.set({"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": st.k2.agent if st.k2 else None,
                   "ce.agent_run.scope": scope.kind, "ce.agent_run.rules": len(scope.rules or [])})


def _require_author(author: str) -> None:
    if not author.strip():
        raise HTTPException(400, "pick who you are first")


def _run_scope(st: Studio, catalog: str, scope: Scope) -> tuple[dict, dict]:
    """The scope the run gets and the names of its catalog's rules."""
    if scope.kind == "first_rules":
        if st.ctx(catalog).ruleset_versions():
            raise HTTPException(400, f"{catalog} already has rules: improve them instead")
        return {"kind": "first_rules", "rules": []}, {}
    from ..report import rule_names

    rv = _latest(st, catalog)
    feedback = _rules_with_feedback(rv, st.agent_runs(catalog).goals())
    rules = _picked_rules(rv, scope, feedback)
    _require_feedback(rules, feedback)
    return {"kind": "rules", "rules": rules}, rule_names(rv.snap.rules)


def _picked_rules(rv, scope: Scope, feedback: dict) -> list[str]:
    if scope.kind == "needs_work":
        return [rid for rid in rv.snap.rules if feedback[rid]["status"] == "needs work"]
    rules = list(dict.fromkeys(scope.rules or []))
    unknown = [r for r in rules if r not in rv.snap.rules]
    if unknown:
        raise HTTPException(400, f"no rule {unknown[0]} in ruleset v{rv.snap.ruleset_version}")
    return rules


def _require_feedback(rules: list[str], feedback: dict) -> None:
    if not rules:
        raise HTTPException(400, "Nothing to improve: no rule was picked")
    if not any(feedback[r]["open"] or feedback[r]["new_since_run"] for r in rules):
        raise HTTPException(400, "Nothing to improve: none of these rules has open annotations or feedback "
                                 "since its last run")


def _conflict_response(exc: RunConflict, names: dict) -> JSONResponse:
    if exc.rule:
        name = names.get(exc.rule, exc.rule)
        return JSONResponse({"detail": f"{name} is being improved in {exc.run['started_by']}'s run",
                             "rule": exc.rule, "rule_name": name, "run": exc.run}, status_code=409)
    return JSONResponse({"detail": "a run is in progress on this catalog", "run": exc.run}, status_code=409)


def _place_in_line(st: Studio, run: dict) -> dict:
    st.queue.forget()
    v = st.queue.view()
    q = _queue_of(v, run)
    free = len(v["working"]) < v["cap"] and q["place"] == 1
    telemetry.set({"ce.agent_run.id": run.get("run_id"), "ce.agent_run.queue_place": q["place"],
                   "ce.agent_run.working": len(v["working"]), "ce.agent_run.cap": v["cap"]})
    return {"place": q["place"], "start_in_min": 0 if free else q["start_in_min"]}


def _studio_url(request: Request, sent: str | None) -> str | None:
    """Where people open this Studio, for the report's links: what the browser sent (http(s) only), else its Origin."""
    for u in (sent, request.headers.get("origin")):
        if u and u.startswith(("https://", "http://")):
            u = u.split("#")[0].split("?")[0]
            return u if u.endswith("/") else u + "/"
    return None


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


# ---- one run and its rows -------------------------------------------------------------------------------------

def _run_or_404(runs, catalog: str, run_id: str) -> dict:
    run = runs.run(run_id)
    if run is None:
        raise not_found(f"no run {run_id} on {catalog}")
    return run


def _with_revert_state(st: Studio, catalog: str, rep: dict | None) -> dict | None:
    """A report whose version was reverted since offers no Revert; it says which version reverted it."""
    v = ((rep or {}).get("revert") or {}).get("version")
    if v is None:
        return rep
    ctx = st.ctx(catalog)
    for later in ctx.ruleset_versions():
        if later > v and ctx.ruleset(later).get("reverts") == v:
            return {**rep, "revert": None, "reverted_in": later}
    return rep


def _rules_touched(run: dict) -> list[str]:
    return list(dict.fromkeys(((run.get("scope") or {}).get("rules") or []) + (run.get("also_changed") or [])))


def _report_rows(rv, rep: dict, as_of: str | None) -> list[dict]:
    from ..report import row_keys

    by_course: dict[str, dict] = {}
    rows = []
    for rid, course in row_keys(rep):
        if rid not in rv.snap.rules:
            continue
        if rid not in by_course:
            by_course[rid] = _rows_by_course(rv, rid)
        r, s = by_course[rid].get(course, (None, None))
        if r is not None:
            rows.append(_report_row(rid, course, r, s, as_of))
    return rows


def _rows_by_course(rv, rid: str) -> dict[str, tuple]:
    rows = rv.snap.rows(rid)
    states = rv.row_states(rid, rows)
    return {r["record_external_identifier"]: (r, states[r["key"]])
            for r in reversed(rows) if r.get("record_external_identifier")}


def _report_row(rid: str, course: str, r: dict, s, as_of: str | None) -> dict:
    from .routes_review import _review_state

    def b(e: dict) -> dict:
        return _brief_after_run(e, as_of)
    return {"rule": rid, "course": course, "page_stem": r["page_stem"], "key": r["key"],
            "occurrence_key": r["occurrence_key"], "value": r["value"], "status": r["status"],
            "state": s.state, "verdict": b(s.verdict) if s.verdict else None, **_review_state(s),
            "history": [b(e) for e in s.events]}


def _brief_after_run(e: dict, as_of: str | None) -> dict:
    """An event with its author's full name, as the report has them."""
    from ..report import brief

    return brief(e) | {"after_run": bool(as_of and e["at"] > as_of)}


def _count_new_feedback(rv, touched: list[str], as_of: str | None) -> int:
    return sum(1 for e in rv.live if e["type"] in ("verdict", "comment") and e.get("author_role") != "ai"
               and e["target"].get("rule_id") in touched and as_of and e["at"] > as_of)


# ---- the rule picker ------------------------------------------------------------------------------------------

def _held_rules(ar) -> dict[str, dict]:
    """Rules another live run is improving, with who started it and for how long."""
    held = {}
    t = now()
    for run in ar.live_runs():
        for r in run["scope"].get("rules") or []:
            held[r] = {"run_id": run["run_id"], "started_by": run["started_by"], "state": run["state"],
                       "since": run["created_at"], "minutes": int((t - parse(run["created_at"])).total_seconds() // 60)}
    return held


def _picker_row(rv, rid: str, names: dict, f: dict, h: dict | None, last: dict | None) -> dict:
    from ..publishing import downstream

    down = downstream(rv.snap.rules, rid)
    return {"rule": rid, "name": names[rid], "kind": rv.snap.rules[rid]["kind"], "status": f["status"],
            "reviewed": f["reviewed"], "total": f["total"], "open": f["open"], "comments": f["comments"],
            "new_since_run": f["new_since_run"], "ticked": h is None and bool(f["open"] or f["new_since_run"]),
            "why": _why_ticked(f, h), "downstream": down,
            "downstream_names": [names.get(d, d) for d in down], "held_by": h,
            "last_run": {k: last.get(k) for k in ("run_id", "state", "ended_at")}
            if last and last.get("state") not in LIVE else None}


def _why_ticked(f: dict, h: dict | None) -> str:
    if h:
        return f"Being improved in {h['started_by']}'s run, {h['minutes']} min"
    bits = []
    if f["open"]:
        bits.append(f"{f['open']} open")
    if f["comments"]:
        bits.append(f"{f['comments']} comment{'' if f['comments'] == 1 else 's'}")
    if f["new_since_run"]:
        bits.append(f"{f['new_since_run']} new since its last run")
    return ", ".join(bits) or "nothing open"


# ---- revert ---------------------------------------------------------------------------------------------------

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


def _publish_revert(ctx, version: int, author: str) -> dict:
    from ..publishing import LockBusy
    from ..publishing import revert as do_revert

    try:
        return do_revert(ctx, version, f"{author} via the Studio UI (revert)", say=lambda m: None, wait_s=60)
    except LockBusy as exc:
        raise HTTPException(409, f"{exc}; try again in a minute") from None
    except UserError as exc:
        raise HTTPException(409, str(exc)) from None


# ---- shared reads ---------------------------------------------------------------------------------------------

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
    rv = LOADER.review(ctx, ext)
    rv.report_sizes()
    return rv


def _rules_with_feedback(rv, goals: dict) -> dict[str, dict]:
    """Per rule: open annotations, comments, verdicts and comments since its last run."""
    return {rid: _rule_feedback(rv, rid, goals.get(rid) or {}) for rid in rv.snap.rules}


def _rule_feedback(rv, rid: str, last: dict) -> dict:
    st = rv.rule_status(rid)
    since = last.get("annotations_as_of") or last.get("ended_at") if last.get("state") not in LIVE else None
    events = [e for e in rv.live if e["target"].get("rule_id") == rid and e["type"] in ("verdict", "comment")
              and e.get("author_role") != "ai"]
    return {"open": st["open_wrong"] + st["open_missing"],
            "comments": sum(1 for e in events if e["type"] == "comment"),
            "new_since_run": sum(1 for e in events if since and e["at"] > since),
            "status": st["status"], "reviewed": st["reviewed"], "total": st["total"]}
