"""Agent runs (agent_runs.py, routes_agent.py): the per-catalog lock, the run states, the agent's reports through the
root, the fallback to the prompt, and the K2 client against a local HTTP server."""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from golden_datasets.agent_runs import (
    K2,
    AgentRuns,
    Fallback,
    K2Busy,
    K2Unavailable,
    RunConflict,
    cmd_done,
    cmd_note,
)
from golden_datasets.context import Ctx
from golden_datasets.errors import UserError
from golden_datasets.server.app import create_app
from golden_datasets.storage import LocalRoot

CAT = "avc"
PROMPT = {"text": "# Improve 2 rules\n", "rules": ["course-description", "course-code"]}


class FakeK2:
    """Answers `send` from a script: "ok", "busy", or "down"; records what was sent."""

    agent = "golden-rules"
    url = agent_url = "http://k2.test"

    def __init__(self, *script: str):
        self.script = list(script) or ["ok"]
        self.sent: list[tuple[str, str]] = []

    def send(self, text: str, sender: str) -> str:
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        self.sent.append((text, sender))
        if step == "busy":
            raise K2Busy("busy")
        if step == "down":
            raise K2Unavailable("K2 didn't answer in 15 s")
        return f"m_{len(self.sent)}"


class Clock:
    def __init__(self):
        self.t = datetime(2026, 10, 28, 3, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.t

    def tick(self, **kw) -> None:
        self.t += timedelta(**kw)


@pytest.fixture
def root(tmp_path):
    return LocalRoot(tmp_path)


def runs(root, k2=None, clock=None, minutes=90) -> AgentRuns:
    return AgentRuns(Ctx(root, CAT), k2, minutes, clock or Clock())


def start(r: AgentRuns, author="Jared Diener", kind="needs_work"):
    return r.start({"kind": kind}, author, lambda run: PROMPT)


def test_start_sends_and_holds_the_lock(root):
    k2 = FakeK2("ok")
    r = runs(root, k2)
    run = start(r)
    assert run["state"] == "running" and run["k2"]["delivery_id"] == "m_1"
    assert run["scope"] == {"kind": "needs_work", "rules": ["course-description", "course-code"]}
    assert k2.sent == [(PROMPT["text"], "Golden Dataset Studio · Jared Diener")]
    cur, etag = r.live()
    assert cur["run_id"] == run["run_id"] and etag
    assert [n["text"] for n in r.notes(run["run_id"])] == ["Started by Jared Diener", "Sent to the golden-rules agent"]
    with pytest.raises(RunConflict) as exc:
        start(r, author="Eric Riddoch")
    assert exc.value.run["run_id"] == run["run_id"]


def test_only_one_of_two_simultaneous_starts_wins(root):
    wins, conflicts = [], []

    def go(name: str) -> None:
        r = runs(root, FakeK2("ok"))
        try:
            wins.append(r.start({"kind": "needs_work"}, name, lambda run: (time.sleep(0.05), PROMPT)[1]))
        except RunConflict:
            conflicts.append(name)

    threads = [threading.Thread(target=go, args=(f"P{i}",)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(wins) == 1 and len(conflicts) == 5


def test_a_busy_agent_makes_the_run_wait_then_it_is_sent(root):
    clock, k2 = Clock(), FakeK2("busy", "busy", "ok")
    r = runs(root, k2, clock)
    run = start(r)
    assert run["state"] == "waiting" and len(k2.sent) == 1
    clock.tick(seconds=5)
    assert r.advance()["state"] == "waiting" and len(k2.sent) == 1  # not due yet
    clock.tick(seconds=20)
    assert r.advance()["state"] == "waiting" and len(k2.sent) == 2  # still busy
    clock.tick(seconds=21)
    assert r.advance()["state"] == "running" and len(k2.sent) == 3
    texts = [n["text"] for n in r.notes(run["run_id"])]
    assert texts.count("The golden-rules agent is busy; the run waits its turn") == 1
    assert texts[-1] == "Sent to the golden-rules agent"


def test_unreachable_k2_falls_back_and_frees_the_lock(root):
    r = runs(root, FakeK2("down"))
    with pytest.raises(Fallback) as exc:
        start(r)
    assert exc.value.reason == "K2 didn't answer in 15 s"
    assert r.live()[0] is None and r.current()[0]["state"] == "failed"  # released in place, not deleted
    last = r.last()
    assert last["state"] == "failed" and last["fallback_reason"] == "K2 didn't answer in 15 s"
    assert last["outcome"].startswith("Couldn't connect to the Remote AI rule generator")
    assert start(runs(root, FakeK2("ok")))["state"] == "running"  # the next start isn't blocked


def test_a_waiting_run_whose_retry_fails_ends_as_failed(root):
    clock = Clock()
    r = runs(root, FakeK2("busy", "down"), clock)
    run = start(r)
    clock.tick(seconds=30)
    assert r.advance() is None
    assert r.last()["run_id"] == run["run_id"] and r.last()["fallback_reason"]


def test_the_agent_reports_and_ends_the_run(root):
    r = runs(root, FakeK2("ok"))
    run = start(r)
    r.note(run["run_id"], "Course description:   reading 20 pages", by="golden-rules agent")
    done = r.done(run["run_id"], "Published ruleset v7: 2 rules changed", failed=False, by="golden-rules agent")
    assert done["state"] == "finished" and r.live()[0] is None
    assert r.last()["outcome"] == "Published ruleset v7: 2 rules changed"
    notes = r.notes(run["run_id"])
    assert notes[-2]["text"] == "Course description: reading 20 pages" and notes[-2]["kind"] == "note"
    assert notes[-1]["kind"] == "done"
    assert r.notes(run["run_id"], since=len(notes) - 1) == [notes[-1]]
    assert r.history()[0]["run_id"] == run["run_id"]
    with pytest.raises(UserError):  # a late or repeated done can't touch another run
        r.done(run["run_id"], "again", failed=False, by="x")
    with pytest.raises(UserError):
        r.note(run["run_id"], "late", by="x")


def test_deadline_cancel_and_mark_as_ended(root):
    clock = Clock()
    r = runs(root, FakeK2("ok"), clock, minutes=90)
    a = start(r)
    clock.tick(minutes=89)
    assert r.advance()["state"] == "running"
    clock.tick(minutes=2)
    assert r.advance() is None and r.last()["state"] == "timed_out"
    b = start(r)
    assert r.cancel(b["run_id"], by="Cadence Calixto")["state"] == "cancelled"
    c = start(r)
    ended = r.end(c["run_id"], by="Eric Riddoch", outcome="it stopped answering")
    assert ended["state"] == "ended" and ended["ended_by"] == "Eric Riddoch"
    assert a["run_id"] != b["run_id"] != c["run_id"]


def test_cli_note_and_done(root, capsys):
    r = runs(root, FakeK2("ok"))
    run = start(r)

    class A:
        pass

    a = A()
    a.root, a.catalog, a.run, a.by = root.uri, CAT, run["run_id"], "golden-rules agent"
    a.text = ["Trying", "the", "draft"]
    assert cmd_note(a) == 0
    a.outcome, a.failed = "Couldn't publish: a correct value changes", True
    (root.base / "summary.md").write_text("## Decisions for Eric\n\n1. Advisory text\n")
    a.summary_file = str(root.base / "summary.md")
    assert cmd_done(a) == 0
    assert r.summary(run["run_id"]) == "## Decisions for Eric\n\n1. Advisory text\n"
    assert "failed" in capsys.readouterr().out
    assert r.last()["state"] == "failed"


class NoDeleteRoot(LocalRoot):
    """The agent's SAS token: add, create, write, list; no delete."""

    def delete(self, path: str) -> None:
        raise PermissionError("AuthorizationPermissionMismatch")


def test_runs_never_delete_and_keep_the_agents_report(tmp_path):
    root, clock = NoDeleteRoot(tmp_path), Clock()
    r = runs(root, FakeK2("ok"), clock)
    a = start(r)
    report = "## What changed\n\n- Requisites after an Advisory line are skipped.\n"
    r.done(a["run_id"], "Couldn't publish: BIOL110 needs an expected value", failed=True, by="golden-rules agent",
           summary=report)
    assert r.summary(a["run_id"]) == report and r.prompt(a["run_id"]) == PROMPT["text"]
    assert r.run(a["run_id"])["state"] == "failed"
    clock.tick(minutes=5)
    b = start(r)  # the next run replaces the ended one in current.json
    assert r.live()[0]["run_id"] == b["run_id"] and r.run(a["run_id"])["outcome"].startswith("Couldn't publish")
    r.cancel(b["run_id"], by="Eric Riddoch")
    assert [h["run_id"] for h in r.history()] == [b["run_id"], a["run_id"]]


# -- K2 client ----------------------------------------------------------------------------------------
class _K2Handler(BaseHTTPRequestHandler):
    answers: dict[str, tuple[int, dict]] = {}
    seen: list[dict] = []

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).seen.append({"path": self.path, "auth": self.headers["Authorization"], "body": body})
        mode = body["text"]
        if mode == "slow":
            time.sleep(1.5)
        code, doc = self.answers.get(mode, (200, {"delivered": True, "deliveryId": "m_9"}))
        data = json.dumps(doc).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture
def k2_server():
    _K2Handler.answers = {
        "busy": (409, {"delivered": False, "reason": "agent_busy"}),
        "declined": (200, {"delivered": False, "mode": "declined", "reason": "remote_instruction_disabled"}),
        "noagent": (200, {"delivered": False, "mode": "live", "result": {"reason": "no_agent_mode"}}),
        "stalled": (200, {"delivered": False, "mode": "live", "result": {"reason": "pty_stalled"}}),
        "nokey": (401, {"error": "unauthorized"}),
    }
    _K2Handler.seen = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _K2Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_k2_client_maps_k2s_answers(k2_server):
    k2 = K2(k2_server, "k2sk_test", "golden-rules", timeout=1)
    assert k2.send("hello", "Golden Dataset Studio · Jared") == "m_9"
    seen = _K2Handler.seen[0]
    assert seen["path"] == "/v1/w/golden-rules/message" and seen["auth"] == "Bearer k2sk_test"
    assert seen["body"] == {"text": "hello", "from": "Golden Dataset Studio · Jared"}
    for mode in ("busy", "stalled"):
        with pytest.raises(K2Busy):
            k2.send(mode, "x")
    for mode, why in [("declined", "Let agents on other servers"), ("noagent", "no_agent_mode"),
                      ("nokey", "refused the Studio's key"), ("slow", "didn't answer in 1 s")]:
        with pytest.raises(K2Unavailable) as exc:
            k2.send(mode, "x")
        assert why in exc.value.reason
    with pytest.raises(K2Unavailable) as exc:
        K2("http://127.0.0.1:9", "k", timeout=1).send("x", "y")
    assert "couldn't reach K2" in exc.value.reason


# -- routes ---------------------------------------------------------------------------------------------
def test_routes_fall_back_to_the_prompt_when_runs_are_off(tmp_path):
    c = TestClient(create_app(str(tmp_path)))
    cfg = c.get("/api/agent-runs/config").json()
    assert cfg["enabled"] is False and "no K2 server" in cfg["off_reason"]
    assert cfg["agent_name"] == "Remote AI rule generator" and cfg["prompt_users"] == []
    r = c.post(f"/api/catalogs/{CAT}/agent-runs", json={"scope": {"kind": "needs_work"}, "author": "Jared"})
    assert r.status_code == 503 and r.json()["fallback"] == "prompt"
    assert c.get(f"/api/catalogs/{CAT}/agent-runs/current").json() == {
        "run": None, "last": None, "notes": [], "since": 0, "now": c.get(f"/api/catalogs/{CAT}/agent-runs/current").json()["now"]}


def test_routes_watch_cancel_and_end(tmp_path):
    app = create_app(str(tmp_path), agent={"prompt_users": "Eric Riddoch, Seth Alt"})
    st = app.state.studio
    st.k2 = FakeK2("ok")
    c = TestClient(app)
    assert c.get("/api/agent-runs/config").json()["prompt_users"] == ["Eric Riddoch", "Seth Alt"]
    one = c.post(f"/api/catalogs/{CAT}/agent-runs", json={"scope": {"kind": "rule", "rule_id": "x"}, "author": "Jared"})
    assert one.status_code == 422  # a run always covers every rule
    run = AgentRuns(st.ctx(CAT), st.k2, 90).start({"kind": "needs_work"}, "Jared Diener", lambda run: PROMPT)
    d = c.get(f"/api/catalogs/{CAT}/agent-runs/current").json()
    assert d["run"]["run_id"] == run["run_id"] and len(d["notes"]) == 2
    assert c.get(f"/api/catalogs/{CAT}/agent-runs/current?since=2").json()["notes"] == []
    assert c.post(f"/api/catalogs/{CAT}/agent-runs/nope/cancel", json={"author": "x"}).status_code == 409
    r = c.post(f"/api/catalogs/{CAT}/agent-runs/{run['run_id']}/cancel", json={"author": "Cadence Calixto"})
    assert r.json()["run"]["state"] == "cancelled"
    d = c.get(f"/api/catalogs/{CAT}/agent-runs/current").json()
    assert d["run"] is None and d["last"]["state"] == "cancelled" and d["notes"][-1]["text"] == "Cancelled by Cadence Calixto"
    assert [h["state"] for h in c.get(f"/api/catalogs/{CAT}/agent-runs").json()] == ["cancelled"]


def test_route_for_one_past_run(tmp_path):
    app = create_app(str(tmp_path))
    st = app.state.studio
    st.k2 = FakeK2("ok")
    r = AgentRuns(st.ctx(CAT), st.k2, 90)
    run = r.start({"kind": "needs_work"}, "Jared Diener", lambda run: PROMPT)
    r.note(run["run_id"], "Trying the draft", by="golden-rules agent")
    r.done(run["run_id"], "Published ruleset v7", failed=False, by="golden-rules agent", summary="# Report\n")
    c = TestClient(app)
    d = c.get(f"/api/catalogs/{CAT}/agent-runs/{run['run_id']}").json()
    assert d["run"]["state"] == "finished" and d["summary"] == "# Report\n"
    assert [n["text"] for n in d["notes"]][-2:] == ["Trying the draft", "Published ruleset v7"]
    assert c.get(f"/api/catalogs/{CAT}/agent-runs/{run['run_id']}/prompt").json() == {"text": PROMPT["text"]}
    assert c.get(f"/api/catalogs/{CAT}/agent-runs/nope").status_code == 404
