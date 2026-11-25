"""Agent runs (docs/qrspi/k2-runs, then docs/qrspi/one-rule-runs/03-spec.md §3, §6, §7): Claude improves a set of a
catalog's rules in a fresh K2 host session, started from the Studio and watched there. Two runs work at once, across
catalogs; the rest wait in line.

Everything about a run lives on the storage root, so every Studio (the deployed one, anyone's laptop) sees the same
runs and any of them can move them forward:

    <catalog>/golden-dataset-studio/agent-runs/live.json         the catalog's live runs (ETag): {"runs": [run, …]}
    <catalog>/golden-dataset-studio/agent-runs/goals.json        rule → its latest run (the sidebar's AI status)
    <catalog>/golden-dataset-studio/agent-runs/last.json         the latest run that ended
    <catalog>/golden-dataset-studio/agent-runs/<run_id>/         run.json (once ended), prompt.md, log.jsonl, report…
    golden-dataset-studio/agent-slots.json                       the places (cap, live sessions), all catalogs (ETag)
    golden-dataset-studio/agent-runs-recent.json                 the last 10 ended runs' durations (the estimate)

A rule is the goal ("a rule to improve") of at most one live run: `live.json` is replaced with its ETag, so two
Studios never both claim it. Nothing is deleted (the agent's SAS token can write but not delete): a run that ends
leaves `live.json` and is written to its own `run.json`.

States: waiting (in line) → sending (the Studio is starting its K2 session) → running → finished | needs_you |
failed | cancelled | timed_out | ended. A sending run goes back to waiting when K2 is full (429).

K2 (§6.1): `POST /v1/w/<ws>/host-sessions` starts a fresh Claude per run, `GET …/<id>` says whether it still lives
(`live: false`, or 404, = the place is free), `POST …/<id>/kill` ends it. Starts happen in the Studio's background
loop (`Queue.tick`, every 5 s), never in a browser request: K2 may hold a start 30 s before it answers. A start whose
answer was lost is never sent again; the run's first note carries `$K2_SESSION_ID` instead. The Studio kills a
session at the deadline and when a run ends; a session that ended without `run done` gets 2 minutes, then fails.
"""

from __future__ import annotations

import heapq
import json
import os
import secrets
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from . import layout
from .context import Ctx
from .errors import ConflictError, UserError

LIVE = ("waiting", "sending", "running")
ENDED = ("finished", "needs_you", "failed", "cancelled", "timed_out", "ended")
ENDING_STATE = {"published": "finished", "needs_you": "needs_you", "failed": "failed"}  # report.json `ending`
RETRY_SECS = 20       # K2 was full: the run at the front tries again after this long (or when a place frees)
LOST_SECS = 120       # a start with no answer and no note, or a session gone without `run done`: then it fails
K2_TIMEOUT = 45       # K2 holds a start up to 30 s before it answers
TICK_SECS = 5
DEFAULT_CAP = 2
DEFAULT_MINUTES = 6   # the estimate's run length before any run has ended
RECENT_RUNS = 10
AGENT_NAME = "Remote AI rule generator"  # what users see; K2 appears only in links and technical details
STUDIO = "Golden Dataset Studio"
SLOTS = "agent-slots.json"         # in the Studio's root, for every catalog and class
RECENT = "agent-runs-recent.json"


def now() -> datetime:
    return datetime.now(UTC)


def iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


# =====================================================================================================
# K2 host sessions
# =====================================================================================================
class K2Full(Exception):
    """K2 answered 429 (`workspace-cell-cap`): no free place for another session."""


class K2Lost(Exception):
    """K2 may have started the session but its answer never came (a timeout, a dropped connection): never resend."""


class K2Unavailable(Exception):
    """K2 refused the Studio or can't be reached. `reason` is one short line for people."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class K2:
    """K2's host-sessions API on one workspace (`agent`, the K2 workspace of the golden-rules agent)."""

    url: str
    key: str
    agent: str = "golden-rules"
    timeout: float = K2_TIMEOUT

    @property
    def agent_url(self) -> str:
        return self.url.rstrip("/")

    def spawn(self, prompt: str, timeout_secs: int, client_request_id: str) -> str:
        """Start a fresh agent session with `prompt` as its first message; returns its session id. Raises K2Full,
        K2Lost (maybe started: never resend) or K2Unavailable."""
        code, doc = self._call("POST", "", {"prompt": prompt, "timeoutSecs": timeout_secs,
                                            "clientRequestId": client_request_id})
        if code == 200 and doc.get("sessionId"):
            return doc["sessionId"]
        if code == 429:
            raise K2Full(doc.get("code") or "full")
        raise self._refused(code, doc)

    def session(self, session_id: str) -> dict | None:
        """The session's state; None once it is over (404). A finished session may also answer `live: false`."""
        code, doc = self._call("GET", f"/{quote(session_id, safe='')}")
        if code == 404:
            return None
        if code == 200:
            return doc
        raise self._refused(code, doc)

    def kill(self, session_id: str) -> bool:
        """Stop the session; safe to repeat (`killed: false` once it is gone)."""
        code, doc = self._call("POST", f"/{quote(session_id, safe='')}/kill", {})
        if code in (200, 404):
            return bool(doc.get("killed"))
        raise self._refused(code, doc)

    def _call(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        try:
            with urllib.request.urlopen(self._request(method, path, body), timeout=self.timeout) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as exc:
            return exc.code, _error_doc(exc)
        except TimeoutError:
            raise K2Lost(self._no_answer()) from None
        except (urllib.error.URLError, OSError) as exc:
            raise self._connection_error(getattr(exc, "reason", exc)) from None
        except ValueError:
            raise K2Unavailable("K2 sent an answer the Studio can't read") from None

    def _request(self, method: str, path: str, body: dict | None) -> urllib.request.Request:
        return urllib.request.Request(
            f"{self.url.rstrip('/')}/v1/w/{quote(self.agent, safe='')}/host-sessions{path}",
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}, method=method)

    def _connection_error(self, reason) -> Exception:
        text = str(reason)
        if isinstance(reason, TimeoutError) or "timed out" in text:
            return K2Lost(self._no_answer())
        if isinstance(reason, ConnectionRefusedError) or any(w in text for w in ("refused", "nodename", "not known")):
            return K2Unavailable(f"couldn't reach K2 ({reason})")
        return K2Lost(f"the connection to K2 dropped ({reason})")

    def _no_answer(self) -> str:
        return f"K2 didn't answer in {self.timeout:g} s"

    def _refused(self, code: int, doc: dict) -> K2Unavailable:
        why = {401: "K2 refused the Studio's key", 403: "K2 refused the Studio's key",
               404: f"K2 has no workspace {self.agent!r} for this key"}
        return K2Unavailable(why.get(code, f"K2 answered {code}" + (f": {doc['error']}" if doc.get("error") else "")))


def _error_doc(exc: urllib.error.HTTPError) -> dict:
    try:
        return json.loads(exc.read() or b"{}")
    except ValueError:
        return {}


# =====================================================================================================
# A catalog's runs
# =====================================================================================================
class RunConflict(Exception):
    """A rule of the new run is already the goal of a live run (or a first-rules run holds the catalog)."""

    def __init__(self, run: dict | None, rule: str | None = None):
        super().__init__("a run is in progress")
        self.run = run
        self.rule = rule


def brief(run: dict) -> dict:
    """What goals.json and `recent` keep of a run."""
    return {k: run.get(k) for k in ("run_id", "state", "outcome", "started_by", "created_at", "ended_at",
                                    "to_do_count", "annotations_as_of", "rule_names", "held")}


@dataclass
class AgentRuns:
    ctx: Ctx
    k2: K2 | None = None
    minutes: int = 90
    clock: Callable[[], datetime] = field(default=now)
    prompter: Callable[[dict], dict] | None = None  # builds a run's prompt ({text, rules}) when it is sent

    @property
    def root(self):
        return self.ctx.root

    @property
    def cat(self) -> str:
        return self.ctx.catalog

    def _path(self, name: str) -> str:
        return f"{layout.agent_runs_dir(self.cat, self.ctx.cls)}/{name}"

    def _dir(self, run_id: str) -> str:
        return layout.agent_run_dir(self.cat, self.ctx.cls, run_id)

    # -- reads -------------------------------------------------------------------------------------------
    def live_runs(self) -> list[dict]:
        """The catalog's live runs, oldest first."""
        try:
            doc = self.root.read_json(self._path("live.json"))
        except FileNotFoundError:
            return []
        return sorted((r for r in doc.get("runs", []) if r.get("state") in LIVE), key=lambda r: r["created_at"])

    def live_run(self, run_id: str) -> dict | None:
        return next((r for r in self.live_runs() if r["run_id"] == run_id), None)

    def last(self) -> dict | None:
        try:
            return self.root.read_json(self._path("last.json"))
        except FileNotFoundError:
            return None

    def goals(self) -> dict[str, dict]:
        """rule → the latest run that had it as a rule to improve."""
        try:
            return self.root.read_json(self._path("goals.json"))
        except FileNotFoundError:
            return {}

    def notes(self, run_id: str, since: int = 0) -> list[dict]:
        try:
            text = self.root.read_text(f"{self._dir(run_id)}/log.jsonl")
        except FileNotFoundError:
            return []
        out = []
        for line in text.splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out[since:]

    def _read(self, run_id: str, name: str, as_json: bool = False):
        try:
            path = f"{self._dir(run_id)}/{name}"
            return self.root.read_json(path) if as_json else self.root.read_text(path)
        except FileNotFoundError:
            return None

    def summary(self, run_id: str) -> str | None:
        """The run's report as Markdown (`summary.md`; older runs have only this)."""
        return self._read(run_id, "summary.md")

    def report(self, run_id: str) -> dict | None:
        """The resolved report (`report.resolved.json`) the Studio renders."""
        return self._read(run_id, "report.resolved.json", as_json=True)

    def prompt(self, run_id: str) -> str | None:
        return self._read(run_id, "prompt.md")

    def run(self, run_id: str) -> dict | None:
        """One run's record: the live one from `live.json`, an ended one from its `run.json`."""
        return self.live_run(run_id) or self._read(run_id, "run.json", as_json=True)

    def history(self, limit: int = 20, rule: str | None = None) -> list[dict]:
        """Runs, newest first, live ones included. `rule`: only runs that had it as a goal or changed it."""
        live = {r["run_id"]: r for r in self.live_runs()}
        out = []
        for run_id in sorted(set(self.root.list_dirs(layout.agent_runs_dir(self.cat, self.ctx.cls))) | set(live), reverse=True):
            run = live.get(run_id) or self._read(run_id, "run.json", as_json=True)
            if run is None:
                continue
            if rule and rule not in ((run.get("scope") or {}).get("rules") or []) \
                    and rule not in (run.get("also_changed") or []):
                continue
            out.append(run)
            if len(out) >= limit:
                break
        return out

    # -- writes ------------------------------------------------------------------------------------------
    def log(self, run_id: str, kind: str, text: str, by: str, **extra) -> None:
        line = {"at": iso(self.clock()), "kind": kind, "text": " ".join(text.split()), "by": by, **extra}
        self.root.append(f"{self._dir(run_id)}/log.jsonl", (json.dumps(line, ensure_ascii=False) + "\n").encode())

    def _update(self, fn: Callable[[list[dict]], object]):
        """Change `live.json` under its ETag: `fn(runs)` mutates the list of live runs and returns a result."""
        box = {}

        def change(doc):
            runs = [r for r in (doc or {}).get("runs", []) if r.get("state") in LIVE]
            box["result"] = fn(runs)
            return {"runs": runs}
        update_json(self.root, self._path("live.json"), change)
        return box.get("result")

    def change(self, run_id: str, expect: tuple[str, ...] | None = None, **fields) -> dict | None:
        """Set fields of a live run (None when it isn't live, or isn't in one of the `expect` states)."""
        def fn(runs):
            run = next((r for r in runs if r["run_id"] == run_id), None)
            if run is None or (expect and run["state"] not in expect):
                return None
            for k, v in fields.items():
                if isinstance(v, dict) and isinstance(run.get(k), dict):
                    run[k] = {**run[k], **v}
                else:
                    run[k] = v
            run["updated_at"] = iso(self.clock())
            return dict(run)
        return self._update(fn)

    def _versions_after(self, run_id: str) -> dict:
        """`ruleset_after`: the last version this run published (its `published.json`), else the latest. With two runs
        at once the latest may be another run's. `ruleset_base`: what its first publish was built on (a rebase moves it
        past `ruleset_before`), so Compare shows only this run's changes."""
        try:
            pubs = self.root.read_json(f"{self._dir(run_id)}/published.json").get("publishes") or []
        except FileNotFoundError:
            pubs = []
        if not pubs:
            return {"ruleset_after": self._latest_ruleset()}
        return {"ruleset_after": pubs[-1]["version"], "ruleset_base": pubs[0]["base"]}

    def _latest_ruleset(self) -> int | None:
        self.ctx.invalidate()
        v = self.ctx.ruleset_versions()
        return v[-1] if v else None

    def start(self, scope: dict, author: str, studio_url: str | None = None,
              rule_names: dict[str, str] | None = None) -> dict:
        """Put a run in line (state waiting). Claims its rules to improve: raises RunConflict if one is already the
        goal of a live run, or a first-rules run holds the catalog (or any run blocks a first-rules run)."""
        if self.k2 is None:
            raise UserError("runs on the remote agent are off for this Studio")
        run = self._new_run(scope, author, studio_url, rule_names or {})
        self._update(lambda runs: _join_live_runs(runs, run))
        self.log(run["run_id"], "studio", f"Started by {author}", by=STUDIO)
        if run["scope"]["rules"]:
            update_json(self.root, self._path("goals.json"), lambda doc: _claim_goals(doc, run))
        return run

    def _new_run(self, scope: dict, author: str, studio_url: str | None, rule_names: dict[str, str]) -> dict:
        from .catalogs import info

        t = self.clock()
        rules = list(scope.get("rules") or [])
        return {"run_id": _new_run_id(t), "catalog": self.cat, "catalog_short": info(self.cat)["short"],
                "class": self.ctx.cls, "scope": {"kind": scope["kind"], "rules": rules, "added": []},
                "rule_names": {r: rule_names.get(r, r) for r in rules}, "started_by": author,
                "state": "waiting", "created_at": iso(t), "updated_at": iso(t), "sending_at": None, "sent_at": None,
                "deadline": None, "next_try_at": None,
                "k2": {"url": self.k2.agent_url, "agent": self.k2.agent, "session_id": None},
                "annotations_as_of": None, "ruleset_before": self._latest_ruleset(), "ruleset_after": None,
                "rulesets_published": [], "also_changed": [], "outcome": None, "ended_at": None, "ended_by": None,
                "fallback_reason": None, "studio_url": studio_url, "to_do_count": None, "report_version": None,
                "session_ended_at": None}

    def note(self, run_id: str, text: str, by: str, session: str | None = None) -> None:
        """A progress line. The first one carries the K2 session (`$K2_SESSION_ID`): the Studio learns a session
        whose start answer was lost, and kills one that turns up for a run that already ended."""
        if not text.strip():
            raise UserError("a note needs some text")
        run = self.live_run(run_id)
        if run is None:
            if session:
                Queue.kill_later(self.root, session)
            raise UserError(f"run {run_id} isn't a live run of {self.cat}")
        if session and not (run.get("k2") or {}).get("session_id"):
            self.change(run_id, k2={"session_id": session})
            self.log(run_id, "note", text, by=by, session=session)
            return
        self.log(run_id, "note", text, by=by)

    def _end(self, run_id: str, state: str, outcome: str | None, by: str, **extra) -> dict:
        """End a live run: out of `live.json`, into its `run.json`, `last.json`, goals.json and the durations."""
        t = self.clock()
        run = self._update(lambda runs: self._take_out(runs, run_id))
        run = dict(run, state=state, outcome=outcome, ended_at=iso(t), ended_by=by,
                   **self._versions_after(run_id), updated_at=iso(t), **extra)
        self._keep_ended(run)
        if run.get("sent_at"):
            Queue.record_duration(self.root, run)
        self.log(run_id, "studio" if by == STUDIO else "done", _ending_line(state, outcome, by), by=by)
        return run

    def _take_out(self, runs: list[dict], run_id: str) -> dict:
        run = next((r for r in runs if r["run_id"] == run_id), None)
        if run is None:
            raise UserError(f"run {run_id} isn't a live run of {self.cat}")
        runs.remove(run)
        return run

    def _keep_ended(self, run: dict) -> None:
        """Into its `run.json`, `last.json` and goals.json."""
        self.root.write_json(f"{self._dir(run['run_id'])}/run.json", run)
        self.root.write_json(self._path("last.json"), run)
        if run["scope"].get("rules"):
            update_json(self.root, self._path("goals.json"), lambda doc: _release_goals(doc, run))

    def done(self, run_id: str, outcome: str, failed: bool, by: str, summary: str | None = None) -> dict:
        self._require_live(run_id)
        if summary and summary.strip():
            self.root.write_text(f"{self._dir(run_id)}/summary.md", summary.strip() + "\n")
        return self._end(run_id, "failed" if failed else "finished", outcome, by=by)

    def done_report(self, run_id: str, facts: dict, by: str) -> tuple[dict, str]:
        """End the run with Claude's `report.json` (report.py): check every reference and quote, append Claude's row
        comments to the annotation log, write `report.resolved.json` and `summary.md`, and end the run in the state
        its `ending` names. Returns (run, summary.md). UserError lists every problem; nothing is written then."""
        from .report import build_known, markdown, resolve

        run = self._require_live(run_id)
        known = build_known(self.ctx, run)
        _check_report(facts, known)
        self._append_row_comments(run_id, facts, known)
        resolved = resolve(facts, known)
        md = markdown(resolved, run.get("studio_url"))
        self._write_report(run_id, facts, resolved, md)
        return self._end_with_report(run, facts, known, resolved, by), md

    def _require_live(self, run_id: str) -> dict:
        run = self.live_run(run_id)
        if run is None:
            raise UserError(f"run {run_id} isn't a live run of {self.cat}")
        return run

    def _append_row_comments(self, run_id: str, facts: dict, known) -> None:
        from .review import LOADER

        events = [self._row_comment(run_id, row, known) for row in facts.get("rows") or []]
        if events:
            log = LOADER.log(self.ctx)
            log.append_many(events)
            known.events = log.events()

    def _row_comment(self, run_id: str, r: dict, known) -> dict:
        from .log import new_id

        row = known.row(r["rule"], r["course"])
        return {"annotation_id": new_id(), "type": "comment", "at": iso(self.clock()), "author": "Claude",
                "author_role": "ai", "catalog": self.cat, "crawl": self.ctx.crawl,
                "target": {"kind": "match", "rule_id": r["rule"],
                           "rule_version_seen": known.rules[r["rule"]]["version"], "extraction_seen": known.ext,
                           "occurrence_key": row["occurrence_key"],
                           "record_external_identifier": row["record_external_identifier"],
                           "page_stem": row["page_stem"], "value_index": 0, "value_seen": row["value"]},
                "verdict": None, "expected": None, "note": " ".join(r["comment"].split()),
                "supersedes": None, "run_id": run_id,
                "ruleset_version": known.published[-1] if known.published else known.ruleset_before}

    def _write_report(self, run_id: str, facts: dict, resolved: dict, md: str) -> None:
        d = self._dir(run_id)
        self.root.write_json(f"{d}/report.json", facts)
        self.root.write_json(f"{d}/report.resolved.json", resolved)
        self.root.write_text(f"{d}/summary.md", md)

    def _end_with_report(self, run: dict, facts: dict, known, resolved: dict, by: str) -> dict:
        from .report import held_rules

        also = [a["rule"] for a in facts.get("also_changed") or []]
        return self._end(run["run_id"], ENDING_STATE[facts["ending"]], resolved["outcome"], by=by,
                         to_do_count=len(facts.get("to_do") or []), also_changed=also, held=held_rules(facts),
                         rule_names={**(run.get("rule_names") or {}), **{r: known.names.get(r, r) for r in also}},
                         rulesets_published=known.published, report_version=2)

    def cancel(self, run_id: str, by: str) -> dict:
        """Cancel a live run. The Studio's loop kills its K2 session and frees the place."""
        return self._end(run_id, "cancelled", None, by=by)

    def end(self, run_id: str, by: str, outcome: str | None = None) -> dict:
        return self._end(run_id, "ended", outcome, by=by)

    # -- sending -----------------------------------------------------------------------------------------
    def send(self, run: dict, k2: K2) -> dict | None:
        """Build the run's prompt and start its K2 session (the caller holds a place for it). Returns the run as it
        is now, or None when it ended."""
        t = self.clock()
        run = self.change(run["run_id"], expect=("waiting",), state="sending", sending_at=iso(t))
        if run is None:
            return None  # cancelled, or another Studio took it
        prompt = self._build_prompt(run)
        if prompt is None:
            return None
        run = self._keep_prompt(run, prompt, t)
        return self._spawn(run, prompt["text"], k2)

    def _build_prompt(self, run: dict) -> dict | None:
        try:
            return (self.prompter or _rules_only_prompt)(run)
        except Exception as exc:  # noqa: BLE001 - any failure to build ends the run with its reason
            self._end(run["run_id"], "failed", f"Couldn't build the prompt: {exc}", by=STUDIO)
            return None

    def _keep_prompt(self, run: dict, prompt: dict, t: datetime) -> dict:
        run_id = run["run_id"]
        self.root.write_text(f"{self._dir(run_id)}/prompt.md", prompt["text"])
        return self.change(run_id, annotations_as_of=iso(t), ruleset_before=self._latest_ruleset(),
                           scope={"rules": prompt.get("rules", run["scope"]["rules"])}) or run

    def _spawn(self, run: dict, text: str, k2: K2) -> dict | None:
        run_id = run["run_id"]
        try:
            session = k2.spawn(text, self.minutes * 60, run_id)
        except K2Full:
            return self._wait_for_place(run)
        except K2Unavailable as exc:
            self._end(run_id, "failed", f"Couldn't connect to the {AGENT_NAME}: {exc.reason}", by=STUDIO,
                      fallback_reason=exc.reason)
            return None
        except K2Lost as exc:
            self.log(run_id, "studio", f"No answer from K2 to the start ({exc}); waiting for Claude's first note",
                     by=STUDIO)
            return self.live_run(run_id)
        return self._running(run_id, session)

    def _wait_for_place(self, run: dict) -> dict | None:
        first = not run.get("next_try_at")
        waiting = self.change(run["run_id"], state="waiting", sending_at=None,
                              next_try_at=iso(self.clock() + timedelta(seconds=RETRY_SECS)))
        if first:
            self.log(run["run_id"], "studio", "K2 has no free place yet; the run waits its turn", by=STUDIO)
        return waiting

    def _running(self, run_id: str, session: str, sent: datetime | None = None) -> dict | None:
        t = sent or self.clock()
        run = self.change(run_id, expect=("sending",), state="running", sent_at=iso(t), next_try_at=None,
                          deadline=iso(t + timedelta(minutes=self.minutes)), k2={"session_id": session})
        if run is not None:
            self.log(run_id, "studio", f"Sent to K2 ({self.k2.agent if self.k2 else 'golden-rules'})", by=STUDIO)
        return run


def studio_prompter(ctx: Ctx, azure_root: str | None) -> Callable[[dict], dict]:
    """The prompt a Studio run gets: its rules to improve, or a new catalog's first rules."""
    def build(run: dict) -> dict:
        from .loop import current_review
        from .prompt import build_first_rules_prompt, build_prompt

        ctx.invalidate()
        if run["scope"]["kind"] == "first_rules":
            return build_first_rules_prompt(ctx, target="k2", azure_root=azure_root, run=run)
        return build_prompt(ctx, rules=run["scope"]["rules"], rv=current_review(ctx), target="k2",
                            azure_root=azure_root, run=run)
    return build


def _new_run_id(t: datetime) -> str:
    return f"{t.strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(2)}"


def _join_live_runs(runs: list[dict], run: dict) -> None:
    """Claim the run's rules among the live runs, or raise RunConflict."""
    rules = run["scope"]["rules"]
    for other in runs:
        if run["scope"]["kind"] == "first_rules" or other["scope"]["kind"] == "first_rules":
            raise RunConflict(other)
        held = [r for r in rules if r in other["scope"].get("rules", [])]
        if held:
            raise RunConflict(other, held[0])
    runs.append(run)


def _claim_goals(doc: dict | None, run: dict) -> dict:
    doc = doc or {}
    for r in run["scope"]["rules"]:
        doc[r] = brief(run)
    return doc


def _release_goals(doc: dict | None, run: dict) -> dict:
    """The run becomes each rule's latest run, unless a newer run already claimed the rule."""
    doc = doc or {}
    for r in run["scope"]["rules"]:
        if (doc.get(r) or {}).get("run_id") in (None, run["run_id"]):
            doc[r] = brief(run)
    return doc


def _ending_line(state: str, outcome: str | None, by: str) -> str:
    return {"finished": outcome or "Finished", "failed": outcome or "Failed", "needs_you": outcome or "Needs you",
            "cancelled": f"Cancelled by {by}", "timed_out": outcome or "Timed out",
            "ended": f"Marked as ended by {by}" + (f": {outcome}" if outcome else "")}[state]


def _check_report(facts: dict, known) -> None:
    from .report import check

    problems = check(facts, known)
    if problems:
        raise UserError("the report has problems (nothing was written); fix report.json and run this again:\n  "
                        + "\n  ".join(problems))


def _rules_only_prompt(run: dict) -> dict:
    return {"text": "", "rules": run["scope"]["rules"]}


# =====================================================================================================
# The queue (all catalogs): places, the background loop, the estimate
# =====================================================================================================
def estimate(cap: int, so_far: list[float], waiting: int, d: float) -> tuple[list[float], list[float]]:
    """(minutes left for each working run, minutes until each waiting run starts), spec §1.7: a working run has
    max(1, d − time so far) left; the k-th run in line takes the k-th place to free up, which it holds for d."""
    left = [max(1.0, d - m) for m in so_far]
    free = sorted(left + [0.0] * max(0, cap - len(so_far)))
    heapq.heapify(free)
    starts = []
    for _ in range(waiting):
        t = heapq.heappop(free) if free else 0.0
        starts.append(t)
        heapq.heappush(free, t + d)
    return left, starts


@dataclass
class Queue:
    root: object
    k2: K2 | None
    runs_for: Callable[[str], AgentRuns]          # catalog folder → its AgentRuns (with the prompter)
    catalogs: Callable[[], list[str]]             # the catalog folders to look at
    cap: int = DEFAULT_CAP
    clock: Callable[[], datetime] = field(default=now)
    _view: tuple[float, dict] | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # -- files ---------------------------------------------------------------------------------------------
    def slots(self) -> dict:
        try:
            doc = self.root.read_json(SLOTS)
        except FileNotFoundError:
            doc = {}
        return {"cap": doc.get("cap", self.cap), "live": doc.get("live", []), "kill": doc.get("kill", [])}

    def _slots_update(self, fn: Callable[[dict], object]):
        box = {}

        def change(doc):
            doc = {"cap": self.cap, "live": (doc or {}).get("live", []), "kill": (doc or {}).get("kill", [])}
            box["result"] = fn(doc)
            return doc
        update_json(self.root, SLOTS, change)
        return box.get("result")

    @staticmethod
    def kill_later(root, session: str) -> None:
        """A session that turned up for a run that already ended: the loop kills it."""
        def change(doc):
            doc = doc or {"live": [], "kill": []}
            if session not in doc.setdefault("kill", []):
                doc["kill"].append(session)
            return doc
        update_json(root, SLOTS, change)

    @staticmethod
    def record_duration(root, run: dict) -> None:
        minutes = (parse(run["ended_at"]) - parse(run["sent_at"])).total_seconds() / 60

        def change(doc):
            runs = [r for r in (doc or {}).get("runs", []) if r["run"] != run["run_id"]]
            runs.append({"run": run["run_id"], "catalog": run.get("catalog_short") or run["catalog"],
                         "sent_at": run["sent_at"], "ended_at": run["ended_at"], "minutes": round(minutes, 2)})
            return {"runs": sorted(runs, key=lambda r: r["ended_at"])[-RECENT_RUNS:]}
        update_json(root, RECENT, change)

    def median(self) -> tuple[float, int]:
        """(minutes a run takes, how many ended runs that is from): the median of the last 10, else 6."""
        try:
            runs = self.root.read_json(RECENT).get("runs", [])
        except FileNotFoundError:
            runs = []
        mins = [r["minutes"] for r in runs[-RECENT_RUNS:]]
        return (statistics.median(mins) if mins else float(DEFAULT_MINUTES)), len(mins)

    def live(self) -> list[tuple[AgentRuns, dict]]:
        """Every live run of every catalog, oldest first."""
        from concurrent.futures import ThreadPoolExecutor

        from . import telemetry

        def live_of(item) -> list[tuple[AgentRuns, dict]]:  # a catalog folder, or (folder, class): each class has its own runs
            ar = self.runs_for(*item) if isinstance(item, tuple) else self.runs_for(item)
            return [(ar, {**r, "class": r.get("class") or ar.ctx.cls}) for r in ar.live_runs()]
        # one live.json per catalog and class, read at once: one after another they took 3-4 s from Azure, longer
        # than the 3 s between the web app's polls of /agent-runs/current
        with ThreadPoolExecutor(max_workers=8) as pool:
            found = pool.map(telemetry.in_this_request(live_of), self.catalogs())
            out = [x for runs in found for x in runs]
        return sorted(out, key=lambda x: x[1]["created_at"])

    # -- the view the routes show --------------------------------------------------------------------------
    def view(self, max_age: float = 2.0) -> dict:
        """The queue as people see it (`GET /api/agent-runs/queue`), cached for `max_age` seconds."""
        with self._lock:
            if self._view and time.monotonic() - self._view[0] < max_age:
                return self._view[1]
        v = self.compute()
        with self._lock:
            self._view = (time.monotonic(), v)
        return v

    def forget(self) -> None:
        with self._lock:
            self._view = None

    def compute(self) -> dict:
        t = self.clock()
        d, n = self.median()
        live = self.live()
        working = [r for _, r in live if r["state"] in ("sending", "running")]
        waiting = [r for _, r in live if r["state"] == "waiting"]
        so_far = [_minutes_working(r, t) for r in working]
        left, starts = estimate(self.cap, so_far, len(waiting), d)
        return {"cap": self.cap, "working": _working_rows(working, so_far, left),
                "waiting": _waiting_rows(waiting, starts), "median_min": round(d), "from_runs": n,
                "note": self._estimate_note(d, n), "slots": self.slots(), "_d": d, "_so_far": so_far}

    def _estimate_note(self, d: float, n: int) -> str:
        at_once = {1: "One run works", 2: "Two runs work", 3: "Three runs work"}.get(self.cap, f"{self.cap} runs work")
        return (f"Estimates use the last {n} run{'' if n == 1 else 's'}, which took {round(d)} min each (median). "
                if n else f"Estimates assume {DEFAULT_MINUTES} min per run until runs have ended. ") + f"{at_once} at a time."

    def next_place(self, view: dict | None = None) -> dict:
        """Where a run started now would stand: {cap, working, waiting, place, start_in_min}."""
        v = view or self.view()
        _, starts = estimate(self.cap, v["_so_far"], len(v["waiting"]) + 1, v["_d"])
        return {"cap": self.cap, "working": len(v["working"]), "waiting": len(v["waiting"]),
                "place": len(v["waiting"]) + 1, "start_in_min": round(starts[-1])}

    @staticmethod
    def note_for(p: dict) -> str:
        """The "Run with Claude?" dialog's note line."""
        if p["working"] + p["waiting"] < p["cap"]:  # a free place for it too, even behind a run about to start
            if p["waiting"]:
                busy = p["working"] + p["waiting"]
                return f"{busy} of {p['cap']} places {'is' if busy == 1 else 'are'} taken, so this one starts now."
            if p["working"] == 0:
                return "No AI run is working, so this one starts now."
            return f"{p['working']} of {p['cap']} AI runs {'is' if p['working'] == 1 else 'are'} working, " \
                   "so this one starts now."
        return (f"{p['working']} AI run{' is' if p['working'] == 1 else 's are'} working. This one would be "
                f"{ordinal(p['place'])} in line, about {max(1, p['start_in_min'])} min.")

    # -- the loop --------------------------------------------------------------------------------------------
    def tick(self) -> None:
        """Move every run forward once: end runs past their deadline or whose session is gone, free the places of
        runs that ended (killing their sessions), then start waiting runs while places are free."""
        if self.k2 is None:
            return
        t = self.clock()
        for ar, run in self.live():
            try:
                self._advance(ar, run, t)
            except (UserError, ConflictError):
                continue  # another Studio moved it first
        self._free()
        self._start()
        self.forget()

    def _advance(self, ar: AgentRuns, run: dict, t: datetime) -> None:
        if run["state"] == "running" and run.get("deadline") and t >= parse(run["deadline"]):
            ar._end(run["run_id"], "timed_out", f"Claude didn't finish in {ar.minutes} minutes", by=STUDIO)
        elif run["state"] == "sending":
            self._confirm_start(ar, run, t)
        elif run["state"] == "running" and _session_of(run):
            self._check_session(ar, run, t)

    def _confirm_start(self, ar: AgentRuns, run: dict, t: datetime) -> None:
        session = _session_of(run)
        if session:  # the start's answer was lost, but Claude's first note named its session
            ar._running(run["run_id"], session, sent=parse(run["sending_at"]) if run.get("sending_at") else t)
        elif run.get("sending_at") and (t - parse(run["sending_at"])).total_seconds() > LOST_SECS:
            ar._end(run["run_id"], "failed", "K2 didn't confirm the start, and no note came from Claude in 2 minutes",
                    by=STUDIO)

    def _check_session(self, ar: AgentRuns, run: dict, t: datetime) -> None:
        try:
            alive = self._session_alive(_session_of(run))
        except (K2Lost, K2Unavailable):
            return
        if not alive:
            _fail_when_gone_too_long(ar, run, t)
        elif run.get("session_ended_at"):
            ar.change(run["run_id"], session_ended_at=None)

    def _session_alive(self, session: str) -> bool:
        s = self.k2.session(session)
        return s is not None and bool(s.get("live", True))

    def _free(self) -> None:
        """Kill the sessions of runs that ended and give their places back."""
        live = {r["run_id"]: r for _, r in self.live()}
        doc = self.slots()
        ended, learned = self._places_to_free(doc["live"], live)
        killed = [s for s in doc["kill"] if self._kill(s)]
        if ended or learned or killed:
            self._slots_update(lambda d: _give_places_back(d, ended, learned, killed))

    def _places_to_free(self, places: list[dict], live: dict[str, dict]) -> tuple[list[str], dict[str, str]]:
        """(runs whose place is free now, run → the session a place learned from its run)."""
        t = self.clock()
        ended, learned = [], {}
        for e in places:
            run = live.get(e["run"])
            if run is None or _is_stale(run, e, t):
                if self._kill_session_of(e, run):
                    ended.append(e["run"])
            elif not e.get("session") and _session_of(run):
                learned[e["run"]] = _session_of(run)
        return ended, learned

    def _kill_session_of(self, place: dict, run: dict | None) -> bool:
        session = place.get("session") or _session_of(run or {})
        return not session or self._kill(session)

    def _kill(self, session: str) -> bool:
        try:
            self.k2.kill(session)
            return True
        except (K2Lost, K2Unavailable):
            return False

    def _start(self) -> None:
        t = self.clock()
        for ar, run in self.live():
            if run["state"] != "waiting":
                continue
            if run.get("next_try_at") and t < parse(run["next_try_at"]):
                break  # the front of the line waits for K2; the runs behind it wait too
            place = self._slots_update(lambda d, run=run: _take_place(d, run, self.cap, t))
            if place == "full":
                break
            if place == "mine" and not self._send(ar, run):
                break  # K2 was full: keep the line's order

    def _send(self, ar: AgentRuns, run: dict) -> bool:
        """Send a run that holds a place; False when K2 was full."""
        sent = ar.send(run, self.k2)
        if sent is None or sent["state"] == "waiting":
            self._slots_update(lambda d: _drop_place(d, run["run_id"]))
            return sent is None
        if _session_of(sent):
            self._slots_update(lambda d: _note_session(d, sent))
        return True

    def loop(self, stop: threading.Event, every: float = TICK_SECS) -> None:
        while not stop.is_set():
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001 - the loop keeps going; the next tick tries again
                print(f"agent runs: {exc}", file=sys.stderr)
            stop.wait(every)


def _minutes_working(run: dict, t: datetime) -> float:
    started = run.get("sent_at") or run.get("sending_at") or run["created_at"]
    return max(0.0, (t - parse(started)).total_seconds() / 60)


def _working_rows(working: list[dict], so_far: list[float], left: list[float]) -> list[dict]:
    return [_queue_row(r) | {"since": r.get("sent_at") or r.get("sending_at"), "minutes_so_far": round(m),
                             "left_min": round(x)} for r, m, x in zip(working, so_far, left)]


def _waiting_rows(waiting: list[dict], starts: list[float]) -> list[dict]:
    return [_queue_row(r) | {"since": r["created_at"], "place": i + 1, "start_in_min": round(s)}
            for i, (r, s) in enumerate(zip(waiting, starts))]


def _queue_row(r: dict) -> dict:
    from .catalogs import info

    rules = (r.get("scope") or {}).get("rules") or []
    names = r.get("rule_names") or {}
    return {"run": r["run_id"], "catalog": r.get("catalog_short") or info(r["catalog"])["short"],
            "catalog_folder": r["catalog"], "catalog_name": info(r["catalog"])["name"], "rules": rules,
            "rule_names": [names.get(x, x) for x in rules], "started_by": r["started_by"], "state": r["state"],
            "class": r.get("class") or "course"}


def _fail_when_gone_too_long(ar: AgentRuns, run: dict, t: datetime) -> None:
    """A session gone without `run done` gets LOST_SECS, then the run fails."""
    if not run.get("session_ended_at"):
        ar.change(run["run_id"], expect=("running",), session_ended_at=iso(t))
    elif (t - parse(run["session_ended_at"])).total_seconds() >= LOST_SECS:
        ar._end(run["run_id"], "failed", "Claude stopped without finishing", by=STUDIO)


def _session_of(run: dict) -> str | None:
    return (run.get("k2") or {}).get("session_id")


def _is_stale(run: dict, place: dict, t: datetime) -> bool:
    """A Studio died between taking a place and sending."""
    return run["state"] == "waiting" and (t - parse(place["since"])).total_seconds() > LOST_SECS


def _give_places_back(d: dict, ended: list[str], learned: dict[str, str], killed: list[str]) -> None:
    for e in d["live"]:
        if e["run"] in learned:
            e["session"] = learned[e["run"]]
    d["live"] = [e for e in d["live"] if e["run"] not in ended]
    d["kill"] = [s for s in d["kill"] if s not in killed]


def _take_place(d: dict, run: dict, cap: int, t: datetime) -> str:
    if any(e["run"] == run["run_id"] for e in d["live"]):
        return "taken"
    if len(d["live"]) >= cap:
        return "full"
    d["live"].append({"run": run["run_id"], "catalog": run.get("catalog_short") or run["catalog"],
                      "session": None, "since": iso(t)})
    return "mine"


def _drop_place(d: dict, run_id: str) -> None:
    d["live"] = [e for e in d["live"] if e["run"] != run_id]


def _note_session(d: dict, run: dict) -> None:
    for e in d["live"]:
        if e["run"] == run["run_id"]:
            e["session"] = _session_of(run)


# =====================================================================================================
# CLI: `golden-datasets run note|done|show|context` (what Claude uses to report)
# =====================================================================================================
def _runs(args) -> AgentRuns:
    return AgentRuns(Ctx.from_args(args))


def _run_id(args) -> str:
    """`--run`, else the run this folder belongs to (`GOLDEN_DATASETS_RUN` in its golden-datasets.env)."""
    rid = args.run or os.environ.get("GOLDEN_DATASETS_RUN")
    if not rid:
        raise UserError("which run? pass --run <run id> (or set GOLDEN_DATASETS_RUN)")
    return rid


def cmd_note(args) -> int:
    _runs(args).note(_run_id(args), " ".join(args.text), by=args.by, session=os.environ.get("K2_SESSION_ID"))
    return 0


def cmd_done(args) -> int:
    args.run = _run_id(args)
    if getattr(args, "report", None):
        return _done_with_report(args)
    if not args.outcome:
        raise UserError("end the run with --report report.json (or, for an old prompt, --outcome \"…\")")
    summary = _read_summary(args.summary_file)
    run = _runs(args).done(args.run, args.outcome, args.failed, by=args.by, summary=summary)
    print(f"run {run['run_id']}: {run['state']} (ruleset v{run['ruleset_after']})")
    return 0


def _done_with_report(args) -> int:
    facts = _read_report(args.report)
    run, md = _runs(args).done_report(args.run, facts, by=args.by)
    print(md)
    print(f"run {run['run_id']}: {run['state']} (ruleset v{run['ruleset_after']}). The Studio shows this report.")
    return 0


def _read_report(path: str) -> dict:
    try:
        return json.loads(sys.stdin.read() if path == "-" else Path(path).read_text())
    except OSError as exc:
        raise UserError(f"can't read the report: {exc}") from None
    except ValueError as exc:
        raise UserError(f"the report isn't valid JSON: {exc}") from None


def _read_summary(path: str | None) -> str | None:
    if not path:
        return None
    try:
        return sys.stdin.read() if path == "-" else Path(path).read_text()
    except OSError as exc:
        raise UserError(f"can't read the summary: {exc}") from None


def cmd_show(args) -> int:
    runs = _runs(args)
    run = runs.run(args.run)
    if run is None:
        raise UserError(f"no run {args.run} on {runs.cat}")
    print(json.dumps(run, indent=2))
    for n in runs.notes(args.run):
        print(f"{n['at']}  {n['by']}: {n['text']}")
    return 0


def context_lines(ar: AgentRuns, rule: str, names: dict[str, str], events: list[dict]) -> list[str]:
    """`run context`: a rule's last run (what it ended with) and the annotations since, for a fresh session."""
    lines = [f"## {names.get(rule, rule)} ({rule})", ""]
    last = _last_ended_run(ar, rule)
    if not last:
        return lines + ["No earlier run had this rule to improve."] + _annotation_lines(events, rule, None)
    run = ar.run(last["run_id"]) or last
    since = run.get("annotations_as_of") or run.get("ended_at")
    return lines + _last_run_lines(ar, run, rule) + _annotation_lines(events, rule, since)


def _last_ended_run(ar: AgentRuns, rule: str) -> dict | None:
    last = ar.goals().get(rule)
    if last and last.get("run_id") and last.get("state") in LIVE:
        return None  # this run itself (or another live one): not a past run
    return last


def _last_run_lines(ar: AgentRuns, run: dict, rule: str) -> list[str]:
    lines = [f"Last run {run['run_id']} by {run.get('started_by')}, ended {(run.get('ended_at') or '')[:16]} "
             f"as {run.get('state')}: {run.get('outcome') or 'no outcome'}"]
    report = ar.report(run["run_id"])
    if report:
        lines += _report_lines_for(report, rule)
    return lines


def _report_lines_for(report: dict, rule: str) -> list[str]:
    lines = []
    for s in report.get("rules", []) + report.get("also_changed", []):
        if s["rule"] == rule:
            lines += [f"  {x}" for x in (f"Outcome: {s.get('outcome')}", s.get("now") and f"Now: {s['now']}",
                                          s.get("why") and f"Why: {s['why']}") if x]
            lines += [f"  Claude on {c['course']}: {c['comment']}" for c in s["rows"] if c.get("comment")]
    for t in report.get("to_do", []):
        if t.get("rule") == rule or any(e["rule"] == rule for e in t.get("effect", [])):
            lines.append(f"  Asked people: {t['ask']}")
            lines += [f"    {o['text']}" for o in t["options"]]
    return lines


def _annotation_lines(events: list[dict], rule: str, since: str | None) -> list[str]:
    new = [e for e in events if (e.get("target") or {}).get("rule_id") == rule and e["type"] in ("verdict", "comment")
           and e.get("author_role") != "ai" and (since is None or e["at"] > since)]
    return (["", f"Annotations {'since then' if since else 'so far'}: {len(new)}"]
            + [_annotation_line(e) for e in new[-30:]] + [""])


def _annotation_line(e: dict) -> str:
    t = e["target"]
    what = f"marked {t.get('record_external_identifier') or t.get('page_stem') or 'it'} {e['verdict']}" if e["type"] == "verdict" \
        else f"commented on {t.get('record_external_identifier') or t.get('page_stem') or 'the rule'}"
    exp = (e.get("expected") or {}).get("text")
    return (f"- {e['at'][:16]} {e['author']} {what} ({e['annotation_id']})"
            + (f": {' '.join(e['note'].split())}" if e.get("note") else "")
            + (f" Expected: {exp!r}" if exp is not None else ""))


def cmd_context(args) -> int:
    from .report import rule_names
    from .review import LOADER

    ar = _runs(args)
    ctx = ar.ctx
    _, rules = ctx.ruleset_rules(ctx.latest_ruleset())
    names = rule_names(rules)
    events = LOADER.log(ctx).events()
    for rid in args.rule_ids:
        if rid not in rules:
            raise UserError(f"no rule {rid!r} in ruleset v{ctx.latest_ruleset()}")
        print("\n".join(context_lines(ar, rid, names, events)))
    return 0


# =====================================================================================================
# Helpers: ETag'd JSON documents, ordinals
# =====================================================================================================
def update_json(root, path: str, fn: Callable[[dict | None], dict | None], tries: int = 30):
    """Read-modify-write `path` with its ETag, retrying on conflicts. `fn(doc)` mutates and returns the new document
    (None = write nothing) and may stash a result in `doc["__result"]`, which is returned (and not written)."""
    for _ in range(tries):
        stat, doc = _read_with_etag(root, path)
        new = fn(json.loads(json.dumps(doc)) if doc is not None else None)
        if new is None:
            return None
        result = new.pop("__result", None)
        if _write_if_unchanged(root, path, new, stat):
            return result
        time.sleep(0.02)
    raise ConflictError(f"{path} kept changing; try again")


def _read_with_etag(root, path: str) -> tuple[object | None, dict | None]:
    stat = root.stat(path)
    if stat is None:
        return None, None
    try:
        return stat, root.read_json(path)
    except FileNotFoundError:
        return None, None


def _write_if_unchanged(root, path: str, doc: dict, stat) -> bool:
    try:
        if stat is None:
            root.write_json(path, doc, if_none_match=True)
        else:
            root.write_json(path, doc, if_match=stat.etag)
        return True
    except ConflictError:
        return False


def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
