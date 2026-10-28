"""Agent runs (docs/qrspi/k2-runs/03-spec.md): Claude improves a catalog's rules on the remote agent (the
golden-rules agent on K2), started from the Studio and watched there.

Everything about a run lives on the storage root, so every Studio (the deployed one, anyone's laptop) sees the same
run and any of them can move it forward:

    <catalog>/golden-dataset-studio/agent-runs/current.json     the lock: held while its run's state is live
    <catalog>/golden-dataset-studio/agent-runs/last.json        the latest run that ended (its outcome stays visible)
    <catalog>/golden-dataset-studio/agent-runs/<run_id>/run.json, prompt.md, log.jsonl, summary.md

`current.json` is only ever created if absent or replaced with its ETag, so two Studios never both start a run on
one catalog or both act on the same run. Nothing is deleted: a run releases the lock by writing its ended state into
`current.json`, and the next run replaces it. (The agent's SAS token can add and write but not delete.) K2's API can deliver the prompt but can't say what the agent is doing or
when it's done, so the agent reports through the root itself (`golden-datasets run note|done`, `log.jsonl`).

States: sending → running → finished | failed | cancelled | timed_out | ended, with sending ⇄ waiting while the agent
is busy. A live run past its deadline ends as timed_out the next time anyone looks.
"""

from __future__ import annotations

import json
import secrets
import sys
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

LIVE = ("sending", "waiting", "running")
ENDED = ("finished", "failed", "cancelled", "timed_out", "ended")
RETRY_SECS = 20     # a busy agent is asked again this often
SENDING_STALE = 60  # a Studio that died while sending: the run is sent again after this long
K2_TIMEOUT = 15
AGENT_NAME = "Remote AI rule generator"  # what users see; K2 appears only in links and technical details


def now() -> datetime:
    return datetime.now(UTC)


def iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


# =====================================================================================================
# K2
# =====================================================================================================
class K2Busy(Exception):
    """The agent is working on something else (K2 answered 409 agent_busy, or the send stalled): try again later."""


class K2Unavailable(Exception):
    """K2 can't be reached or won't deliver. `reason` is one short line for people."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class K2:
    """`POST /v1/w/<agent>/message` on a K2 server: types `text` into the agent's chat (K2's canonical door)."""

    url: str
    key: str
    agent: str = "golden-rules"
    timeout: float = K2_TIMEOUT

    @property
    def agent_url(self) -> str:
        return self.url.rstrip("/")

    def send(self, text: str, sender: str) -> str | None:
        """Deliver `text`; returns K2's delivery id. Raises K2Busy or K2Unavailable."""
        req = urllib.request.Request(
            f"{self.url.rstrip('/')}/v1/w/{quote(self.agent, safe='')}/message",
            data=json.dumps({"text": text, "from": sender}).encode(),
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                body = json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                raise K2Busy("the agent is busy") from None
            why = {401: "K2 refused the Studio's key", 404: f"K2 has no agent {self.agent!r} for this key"}
            raise K2Unavailable(why.get(exc.code, f"K2 answered {exc.code}")) from None
        except TimeoutError:
            raise K2Unavailable(f"K2 didn't answer in {self.timeout:g} s") from None
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, TimeoutError) or "timed out" in str(reason):
                raise K2Unavailable(f"K2 didn't answer in {self.timeout:g} s") from None
            raise K2Unavailable(f"couldn't reach K2 ({reason})") from None
        except ValueError:
            raise K2Unavailable("K2 sent an answer the Studio can't read") from None
        if body.get("delivered"):
            return body.get("deliveryId")
        if body.get("mode") == "declined":
            raise K2Unavailable(f"the {self.agent} agent doesn't accept messages from the Studio "
                                "(in K2: Let agents on other servers message this agent)")
        reason = (body.get("result") or {}).get("reason") or "not delivered"
        if reason in ("pty_stalled", "hitl_gate_open"):  # transient: the agent is mid-send or waiting on a person
            raise K2Busy(reason)
        raise K2Unavailable(f"K2 couldn't deliver the message ({reason})")


# =====================================================================================================
# Runs
# =====================================================================================================
class RunConflict(Exception):
    """Another run holds this catalog's lock."""

    def __init__(self, run: dict | None):
        super().__init__("a run is in progress")
        self.run = run


class Fallback(Exception):
    """The run couldn't be handed to the agent: the user should get the prompt instead."""

    def __init__(self, run: dict, reason: str):
        super().__init__(reason)
        self.run = run
        self.reason = reason


@dataclass
class AgentRuns:
    ctx: Ctx
    k2: K2 | None = None
    minutes: int = 90
    clock: Callable[[], datetime] = field(default=now)

    @property
    def root(self):
        return self.ctx.root

    @property
    def cat(self) -> str:
        return self.ctx.catalog

    def _current_path(self) -> str:
        return f"{layout.agent_runs_dir(self.cat)}/current.json"

    def _dir(self, run_id: str) -> str:
        return layout.agent_run_dir(self.cat, run_id)

    # -- reads -------------------------------------------------------------------------------------------
    def current(self) -> tuple[dict | None, str | None]:
        """`current.json` (the latest run, live or ended) and its ETag; (None, None) before the first run."""
        st = self.root.stat(self._current_path())
        if st is None:
            return None, None
        try:
            return self.root.read_json(self._current_path()), st.etag
        except FileNotFoundError:
            return None, None

    def live(self) -> tuple[dict | None, str | None]:
        """The run holding the lock, or None; with the ETag of `current.json` either way."""
        cur, etag = self.current()
        return (cur if cur and cur.get("state") in LIVE else None), etag

    def last(self) -> dict | None:
        try:
            return self.root.read_json(f"{layout.agent_runs_dir(self.cat)}/last.json")
        except FileNotFoundError:
            return None

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

    def summary(self, run_id: str) -> str | None:
        """The agent's final report (`run done --summary-file`), Markdown."""
        try:
            return self.root.read_text(f"{self._dir(run_id)}/summary.md")
        except FileNotFoundError:
            return None

    def prompt(self, run_id: str) -> str | None:
        try:
            return self.root.read_text(f"{self._dir(run_id)}/prompt.md")
        except FileNotFoundError:
            return None

    def run(self, run_id: str) -> dict | None:
        """One run's record: the live one from `current.json`, an ended one from its `run.json`."""
        cur, _ = self.current()
        if cur and cur["run_id"] == run_id:
            return cur
        try:
            return self.root.read_json(f"{self._dir(run_id)}/run.json")
        except FileNotFoundError:
            return None

    def history(self, limit: int = 20) -> list[dict]:
        out = []
        for run_id in sorted(self.root.list_dirs(layout.agent_runs_dir(self.cat)), reverse=True)[:limit]:
            try:
                out.append(self.root.read_json(f"{self._dir(run_id)}/run.json"))
            except FileNotFoundError:
                continue
        return out

    # -- writes ------------------------------------------------------------------------------------------
    def log(self, run_id: str, kind: str, text: str, by: str) -> None:
        line = {"at": iso(self.clock()), "kind": kind, "text": " ".join(text.split()), "by": by}
        self.root.append(f"{self._dir(run_id)}/log.jsonl", (json.dumps(line, ensure_ascii=False) + "\n").encode())

    def _put(self, run: dict, etag: str) -> str:
        run["updated_at"] = iso(self.clock())
        return self.root.write_json(self._current_path(), run, if_match=etag)

    def _latest_ruleset(self) -> int | None:
        self.ctx.invalidate()
        v = self.ctx.ruleset_versions()
        return v[-1] if v else None

    def start(self, scope: dict, author: str, build: Callable[[dict], dict]) -> dict:
        """Take the catalog's lock and hand the run to the agent. `build(run)` returns the prompt
        ({text, rules, …}, prompt.py) for this run. Raises RunConflict, Fallback, or UserError."""
        if self.k2 is None:
            raise UserError("runs on the remote agent are off for this Studio")
        cur, held = self.current()
        if cur is not None and cur.get("state") in LIVE:
            raise RunConflict(cur)
        t = self.clock()
        run_id = f"{t.strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(2)}"
        run = {"run_id": run_id, "catalog": self.cat, "scope": dict(scope), "started_by": author,
               "created_at": iso(t), "updated_at": iso(t), "deadline": iso(t + timedelta(minutes=self.minutes)),
               "state": "sending", "sent_at": None, "next_try_at": None,
               "k2": {"url": self.k2.agent_url, "agent": self.k2.agent, "delivery_id": None},
               "ruleset_before": self._latest_ruleset(), "ruleset_after": None,
               "outcome": None, "ended_at": None, "ended_by": None, "fallback_reason": None}
        try:
            etag = (self.root.write_json(self._current_path(), run, if_none_match=True) if cur is None
                    else self.root.write_json(self._current_path(), run, if_match=held))
        except ConflictError:
            raise RunConflict(self.live()[0]) from None
        try:
            prompt = build(run)
        except Exception as exc:
            self._end(run, etag, "failed", f"couldn't build the prompt: {exc}", by="Golden Rules Studio")
            raise
        run["scope"]["rules"] = prompt.get("rules", [])
        self.root.write_text(f"{self._dir(run_id)}/prompt.md", prompt["text"])
        self.log(run_id, "studio", f"Started by {author}", by="Golden Rules Studio")
        return self._send(run, etag)

    def _send(self, run: dict, etag: str) -> dict:
        text = self.root.read_text(f"{self._dir(run['run_id'])}/prompt.md")
        try:
            delivery = self.k2.send(text, f"Golden Rules Studio · {run['started_by']}")
        except K2Busy:
            first = run["state"] == "sending" and run.get("next_try_at") is None
            run.update(state="waiting", next_try_at=iso(self.clock() + timedelta(seconds=RETRY_SECS)))
            etag = self._put(run, etag)
            if first:
                self.log(run["run_id"], "studio", f"The {self.k2.agent} agent is busy; the run waits its turn",
                         by="Golden Rules Studio")
            return run
        except K2Unavailable as exc:
            run["fallback_reason"] = exc.reason
            ended = self._end(run, etag, "failed", f"Couldn't connect to the {AGENT_NAME}: {exc.reason}",
                              by="Golden Rules Studio")
            raise Fallback(ended, exc.reason) from None
        run.update(state="running", sent_at=iso(self.clock()), next_try_at=None)
        run["k2"]["delivery_id"] = delivery
        self._put(run, etag)
        self.log(run["run_id"], "studio", f"Sent to the {self.k2.agent} agent", by="Golden Rules Studio")
        return run

    def advance(self) -> dict | None:
        """Move the live run forward: send a waiting run when its turn comes, end one past its deadline.
        Safe to call from every Studio on every poll; returns the live run (None once it has ended)."""
        cur, etag = self.live()
        if cur is None:
            return None
        t = self.clock()
        try:
            if t >= parse(cur["deadline"]):
                self._end(cur, etag, "timed_out", f"No word from the agent after {self.minutes} minutes",
                          by="Golden Rules Studio")
                return None
            due = cur["state"] == "waiting" and cur.get("next_try_at") and t >= parse(cur["next_try_at"])
            stale = cur["state"] == "sending" and (t - parse(cur["updated_at"])).total_seconds() > SENDING_STALE
            if (due or stale) and self.k2 is not None:
                cur["state"] = "sending"
                etag = self._put(cur, etag)  # claim it: another Studio's poll now sees "sending" and leaves it
                try:
                    return self._send(cur, etag)
                except Fallback:
                    return None
        except ConflictError:
            return self.live()[0]  # another Studio moved it first
        return cur

    def _end(self, run: dict, etag: str, state: str, outcome: str | None, by: str) -> dict:
        run = dict(run, state=state, outcome=outcome, ended_at=iso(self.clock()), ended_by=by,
                   ruleset_after=self._latest_ruleset())
        self._put(run, etag)  # the end releases the lock; ConflictError if another Studio got there first
        self.root.write_json(f"{self._dir(run['run_id'])}/run.json", run)
        self.root.write_json(f"{layout.agent_runs_dir(self.cat)}/last.json", run)
        self.log(run["run_id"], "studio" if by == "Golden Rules Studio" else "done",
                 {"finished": outcome or "Finished", "failed": outcome or "Failed",
                  "cancelled": f"Cancelled by {by}", "timed_out": outcome or "Timed out",
                  "ended": f"Marked as ended by {by}" + (f": {outcome}" if outcome else "")}[state], by=by)
        return run

    def _live(self, run_id: str) -> tuple[dict, str]:
        cur, etag = self.live()
        if cur is None or cur["run_id"] != run_id:
            raise UserError(f"run {run_id} isn't the current run of {self.cat}"
                            + (f" (that is {cur['run_id']})" if cur else " (there is none)"))
        return cur, etag

    def note(self, run_id: str, text: str, by: str) -> None:
        self._live(run_id)
        if not text.strip():
            raise UserError("a note needs some text")
        self.log(run_id, "note", text, by=by)

    def done(self, run_id: str, outcome: str, failed: bool, by: str, summary: str | None = None) -> dict:
        cur, etag = self._live(run_id)
        if summary and summary.strip():
            self.root.write_text(f"{self._dir(run_id)}/summary.md", summary.strip() + "\n")
        return self._end(cur, etag, "failed" if failed else "finished", outcome, by=by)

    def cancel(self, run_id: str, by: str) -> dict:
        cur, etag = self._live(run_id)
        run = self._end(cur, etag, "cancelled", None, by=by)
        if self.k2 is not None and cur["state"] == "running":
            try:  # best effort: a working agent can't take messages (busy), so this often goes nowhere
                self.k2.send(f"Stop work on Golden Rules Studio run {run_id} ({self.cat}): {by} cancelled it. "
                             "Don't publish anything more for it.", f"Golden Rules Studio · {by}")
            except (K2Busy, K2Unavailable):
                pass
        return run

    def end(self, run_id: str, by: str, outcome: str | None = None) -> dict:
        cur, etag = self._live(run_id)
        return self._end(cur, etag, "ended", outcome, by=by)


# =====================================================================================================
# CLI: `golden-datasets run note|done|show` (what the agent uses to report)
# =====================================================================================================
def _runs(args) -> AgentRuns:
    return AgentRuns(Ctx.from_args(args))


def cmd_note(args) -> int:
    _runs(args).note(args.run, " ".join(args.text), by=args.by)
    return 0


def cmd_done(args) -> int:
    summary = None
    if args.summary_file:
        try:
            summary = sys.stdin.read() if args.summary_file == "-" else Path(args.summary_file).read_text()
        except OSError as exc:
            raise UserError(f"can't read the summary: {exc}") from None
    run = _runs(args).done(args.run, args.outcome, args.failed, by=args.by, summary=summary)
    print(f"run {run['run_id']}: {run['state']} (ruleset v{run['ruleset_after']})")
    return 0


def cmd_show(args) -> int:
    runs = _runs(args)
    run = runs.run(args.run)
    if run is None:
        raise UserError(f"no run {args.run} on {runs.cat}")
    print(json.dumps(run, indent=2))
    for n in runs.notes(args.run):
        print(f"{n['at']}  {n['by']}: {n['text']}")
    return 0

