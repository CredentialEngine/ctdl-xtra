"""AI runs (agent_runs.py, routes_agent.py; one-rule-runs spec §3.5, §6, §7): goal claims, the queue across catalogs
driven by the background loop against a fake K2 (cap 2, a 429, a lost start answer, a session that ended, the
deadline), the estimate, Claude's notes through the root, and the K2 host-sessions client against a local server."""

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
    SLOTS,
    AgentRuns,
    K2Full,
    K2Lost,
    K2Unavailable,
    Queue,
    RunConflict,
    cmd_done,
    cmd_note,
    estimate,
)
from golden_datasets.context import Ctx
from golden_datasets.errors import UserError
from golden_datasets.server.app import create_app
from golden_datasets.storage import LocalRoot

PROMPT = {"text": "# Improve 1 rule\n", "rules": ["course-description"]}


class FakeK2:
    """K2's host sessions with a cap, like the server: `next` scripts the answer to the next starts ("ok", "full",
    "lost": started but the answer never came, "down")."""

    agent = "golden-rules"
    url = agent_url = "http://k2.test"

    def __init__(self, cap: int = 2):
        self.cap = cap
        self.sessions: dict[str, dict] = {}  # id → {"live": bool, "prompt", "client"}
        self.next: list[str] = []
        self.starts: list[str] = []
        self.killed: list[str] = []
        self.gone: set[str] = set()  # answer 404 instead of live: false

    def live_count(self) -> int:
        return sum(s["live"] for s in self.sessions.values())

    def spawn(self, prompt: str, timeout_secs: int, client_request_id: str) -> str:
        step = self.next.pop(0) if self.next else "ok"
        self.starts.append(client_request_id)
        if step == "down":
            raise K2Unavailable("K2 refused the Studio's key")
        if step == "full" or self.live_count() >= self.cap:
            raise K2Full("workspace-cell-cap")
        sid = f"s{len(self.sessions) + 1}"
        self.sessions[sid] = {"live": True, "prompt": prompt, "client": client_request_id, "timeout": timeout_secs}
        if step == "lost":
            raise K2Lost("K2 didn't answer in 45 s")
        return sid

    def session(self, sid: str) -> dict | None:
        if sid in self.gone or sid not in self.sessions:
            return None
        live = self.sessions[sid]["live"]
        return {"live": live, "phase": "working" if live else "finished"}

    def kill(self, sid: str) -> bool:
        self.killed.append(sid)
        was = self.sessions.get(sid, {}).get("live", False)
        if sid in self.sessions:
            self.sessions[sid]["live"] = False
        return was


class Clock:
    def __init__(self):
        self.t = datetime(2026, 11, 6, 15, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.t

    def tick(self, **kw) -> None:
        self.t += timedelta(**kw)


@pytest.fixture
def world(tmp_path):
    root, k2, clock = LocalRoot(tmp_path), FakeK2(), Clock()

    def runs_for(cat: str) -> AgentRuns:
        return AgentRuns(Ctx(root, cat), k2, 90, clock, prompter=lambda run: PROMPT | {"rules": run["scope"]["rules"]})
    q = Queue(root, k2, runs_for, lambda: ["avc", "marshall"], cap=2, clock=clock)
    return root, k2, clock, runs_for, q


def start(ar: AgentRuns, *rules: str, author="Jared Diener"):
    return ar.start({"kind": "rules", "rules": list(rules) or ["course-description"]}, author)


def states(ar: AgentRuns) -> list[str]:
    return [r["state"] for r in ar.live_runs()]


# -- goal claims ----------------------------------------------------------------------------------------
def test_a_rule_is_the_goal_of_one_live_run_at_a_time(world):
    _, _, _, runs_for, _ = world
    avc = runs_for("avc")
    a = start(avc, "course-credit-value", "course-subject-webpage")
    assert a["state"] == "waiting" and a["scope"] == {"kind": "rules", "rules": ["course-credit-value",
                                                                              "course-subject-webpage"], "added": []}
    with pytest.raises(RunConflict) as exc:
        start(avc, "course-subject-webpage", author="Seth Alt")
    assert exc.value.rule == "course-subject-webpage" and exc.value.run["run_id"] == a["run_id"]
    b = start(avc, "course-description", author="Seth Alt")  # another rule: fine, two live runs on one catalog
    assert [r["run_id"] for r in avc.live_runs()] == [a["run_id"], b["run_id"]]
    assert start(runs_for("marshall"), "course-subject-webpage")  # the claim is per catalog
    with pytest.raises(RunConflict):  # a first-rules run needs the catalog to itself
        avc.start({"kind": "first_rules"}, "Eric Riddoch")
    avc.cancel(a["run_id"], by="Jared Diener")
    assert start(avc, "course-subject-webpage", author="Seth Alt")["state"] == "waiting"  # freed when it ended
    assert avc.goals()["course-credit-value"]["state"] == "cancelled"


def test_only_one_of_simultaneous_claims_on_a_rule_wins(world):
    _, _, _, runs_for, _ = world
    wins, conflicts = [], []

    def go(name: str) -> None:
        try:
            wins.append(start(runs_for("avc"), "course-description", author=name))
        except RunConflict:
            conflicts.append(name)
    threads = [threading.Thread(target=go, args=(f"P{i}",)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(wins) == 1 and len(conflicts) == 5


# -- the queue -----------------------------------------------------------------------------------------
def test_cap_2_across_catalogs_and_a_kill_frees_the_place(world):
    root, k2, clock, runs_for, q = world
    avc, mar = runs_for("avc"), runs_for("marshall")
    a = start(avc, "course-description")
    clock.tick(seconds=1)
    b = start(mar, "course-description")
    clock.tick(seconds=1)
    c = start(avc, "course-credit-value")
    q.tick()
    assert states(avc) == ["running", "waiting"] and states(mar) == ["running"]
    assert k2.starts == [a["run_id"], b["run_id"]] and k2.live_count() == 2  # the 3rd never asked K2
    slots = root.read_json(SLOTS)
    assert slots["cap"] == 2 and [(e["run"], e["session"]) for e in slots["live"]] == [(a["run_id"], "s1"),
                                                                                       (b["run_id"], "s2")]
    run = avc.run(a["run_id"])
    assert run["k2"]["session_id"] == "s1" and run["annotations_as_of"] and avc.prompt(a["run_id"]) == PROMPT["text"]
    assert run["deadline"] == "2026-11-06T16:30:02Z" and k2.sessions["s1"]["timeout"] == 5400
    v = q.compute()
    assert [w["place"] for w in v["waiting"]] == [1] and v["waiting"][0]["run"] == c["run_id"]
    # Claude ends run A: the loop kills its session, frees the place, and starts C
    avc.done(a["run_id"], "Published", failed=False, by="golden-rules agent")
    clock.tick(seconds=5)
    q.tick()
    assert "s1" in k2.killed and states(avc) == ["running"] and avc.live_runs()[0]["run_id"] == c["run_id"]
    assert [e["run"] for e in root.read_json(SLOTS)["live"]] == [b["run_id"], c["run_id"]]


def test_a_429_puts_the_run_back_in_line_and_it_tries_again(world):
    _, k2, clock, runs_for, q = world
    avc = runs_for("avc")
    a = start(avc, "course-description")
    k2.next = ["full"]  # K2 is full with sessions from elsewhere
    q.tick()
    run = avc.run(a["run_id"])
    assert run["state"] == "waiting" and run["next_try_at"] == "2026-11-06T15:00:20Z"
    assert [n["text"] for n in avc.notes(a["run_id"])][-1] == "K2 has no free place yet; the run waits its turn"
    clock.tick(seconds=5)
    q.tick()
    assert len(k2.starts) == 1  # not due yet
    clock.tick(seconds=20)
    q.tick()
    assert avc.run(a["run_id"])["state"] == "running" and len(k2.starts) == 2
    assert run["created_at"] == avc.run(a["run_id"])["created_at"]  # same place in line


def test_a_lost_start_answer_is_never_resent_and_the_first_note_names_the_session(world):
    root, k2, clock, runs_for, q = world
    avc = runs_for("avc")
    a, b = start(avc, "course-description"), start(avc, "course-code")
    k2.next = ["lost", "lost"]
    q.tick()
    assert states(avc) == ["sending", "sending"] and len(k2.starts) == 2
    clock.tick(seconds=30)
    q.tick()
    assert len(k2.starts) == 2  # never sent again
    # A's Claude writes its first note with $K2_SESSION_ID: the Studio learns the session
    avc.note(a["run_id"], "Starting: reading the annotations", by="golden-rules agent", session="s1")
    q.tick()
    run = avc.run(a["run_id"])
    assert run["state"] == "running" and run["k2"]["session_id"] == "s1"
    assert {e["run"]: e["session"] for e in root.read_json(SLOTS)["live"]}[a["run_id"]] == "s1"
    # B never writes a note: after 2 minutes it fails, and its place frees
    clock.tick(seconds=100)
    q.tick()
    assert avc.run(b["run_id"])["state"] == "failed" and "no note came" in avc.run(b["run_id"])["outcome"]
    assert [e["run"] for e in root.read_json(SLOTS)["live"]] == [a["run_id"]]
    # a session that turns up for a run that already ended is killed
    with pytest.raises(UserError):
        avc.note(b["run_id"], "Starting", by="golden-rules agent", session="s2")
    q.tick()
    assert "s2" in k2.killed and root.read_json(SLOTS)["kill"] == []


@pytest.mark.parametrize("how", ["live-false", "404"])
def test_a_session_that_ended_without_run_done_fails_after_2_minutes(world, how):
    _, k2, clock, runs_for, q = world
    avc = runs_for("avc")
    a = start(avc, "course-description")
    q.tick()
    if how == "404":
        k2.gone.add("s1")
    else:
        k2.sessions["s1"]["live"] = False  # the K2 server answers 200 {"live": false, "phase": "finished"}
    clock.tick(seconds=5)
    q.tick()
    assert avc.run(a["run_id"])["state"] == "running" and avc.run(a["run_id"])["session_ended_at"]
    clock.tick(seconds=60)
    q.tick()
    assert avc.run(a["run_id"])["state"] == "running"  # a late `run done` may still come
    clock.tick(seconds=61)
    q.tick()
    ended = avc.run(a["run_id"])
    assert ended["state"] == "failed" and ended["outcome"] == "Claude stopped without finishing"


def test_the_studio_kills_a_session_at_the_deadline(world):
    root, k2, clock, runs_for, q = world
    avc = runs_for("avc")
    a = start(avc, "course-description")
    q.tick()
    clock.tick(minutes=89)
    q.tick()
    assert avc.run(a["run_id"])["state"] == "running"
    clock.tick(minutes=2)
    q.tick()
    assert avc.run(a["run_id"])["state"] == "timed_out" and k2.killed == ["s1"]
    assert root.read_json(SLOTS)["live"] == [] and not k2.sessions["s1"]["live"]


def test_cancel_kills_the_session_and_k2_refusing_the_key_fails_the_run(world):
    root, k2, clock, runs_for, q = world
    avc = runs_for("avc")
    a = start(avc, "course-description")
    q.tick()
    avc.cancel(a["run_id"], by="Cadence Calixto")
    q.tick()
    assert k2.killed == ["s1"] and root.read_json(SLOTS)["live"] == []
    b = start(avc, "course-description")
    k2.next = ["down"]
    q.tick()
    run = avc.run(b["run_id"])
    assert run["state"] == "failed" and run["fallback_reason"] == "K2 refused the Studio's key"
    assert root.read_json(SLOTS)["live"] == []


def test_two_studios_never_start_the_same_run(world):
    root, k2, clock, runs_for, q = world
    for i in range(3):
        start(runs_for("avc"), f"rule-{i}")
    q2 = Queue(root, k2, runs_for, lambda: ["avc", "marshall"], cap=2, clock=clock)
    threads = [threading.Thread(target=x.tick) for x in (q, q2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(k2.starts) == len(set(k2.starts)) == 2 and k2.live_count() == 2


# -- the estimate ------------------------------------------------------------------------------------------
def test_the_estimate():
    assert estimate(2, [], 1, 6) == ([], [0])  # no history: 6 min a run; a free place
    assert estimate(2, [4], 2, 6) == ([2], [0, 2])  # one working: one place free now, the next in 2 min
    left, starts = estimate(2, [4, 1], 2, 6)  # two working, two waiting
    assert left == [2, 5] and starts == [2, 5]
    assert estimate(2, [10, 1], 3, 6)[1] == [1, 5, 7]  # a run past d has at least 1 min left; places reused


def test_the_queue_view_uses_the_last_10_runs(world):
    root, k2, clock, runs_for, q = world
    v = q.compute()
    assert v["median_min"] == 6 and v["from_runs"] == 0 and v["note"].startswith("Estimates assume 6 min")
    avc = runs_for("avc")
    for minutes in (2, 4, 9):
        a = start(avc, "course-description")
        q.tick()
        clock.tick(minutes=minutes)
        avc.done(a["run_id"], "x", failed=False, by="agent")
        q.tick()
    a, b, c = start(avc, "r1"), start(avc, "r2"), start(avc, "r3")
    q.tick()
    clock.tick(minutes=1)
    v = q.compute()
    assert v["median_min"] == 4 and v["from_runs"] == 3
    assert v["note"] == "Estimates use the last 3 runs, which took 4 min each (median). Two runs work at a time."
    assert [(w["run"], w["left_min"]) for w in v["working"]] == [(a["run_id"], 3), (b["run_id"], 3)]
    assert [(w["run"], w["place"], w["start_in_min"]) for w in v["waiting"]] == [(c["run_id"], 1, 3)]
    p = q.next_place(v)
    assert p["place"] == 2 and Queue.note_for(p) == "2 AI runs are working. This one would be 2nd in line, about 3 min."
    assert Queue.note_for({"cap": 2, "working": 1, "waiting": 0, "place": 1, "start_in_min": 0}) == \
        "1 of 2 AI runs is working, so this one starts now."


# -- notes and done from the CLI ---------------------------------------------------------------------------
def test_cli_note_records_the_session_and_done_ends_the_run(world, monkeypatch, capsys):
    root, k2, clock, runs_for, q = world
    avc = runs_for("avc")
    a = start(avc, "course-description")
    k2.next = ["lost"]
    q.tick()

    class A:
        pass
    args = A()
    args.root, args.catalog, args.crawl, args.run, args.by = root.uri, "avc", None, a["run_id"], "golden-rules agent"
    args.text = ["Starting:", "reading", "20 pages"]
    monkeypatch.setenv("K2_SESSION_ID", "s1")
    assert cmd_note(args) == 0
    note = AgentRuns(Ctx(root, "avc")).notes(a["run_id"])[-1]
    assert note["text"] == "Starting: reading 20 pages" and note["session"] == "s1"
    assert avc.run(a["run_id"])["k2"]["session_id"] == "s1"
    args.report, args.outcome, args.failed, args.summary_file = None, "Couldn't publish", True, None
    assert cmd_done(args) == 0 and avc.run(a["run_id"])["state"] == "failed"
    assert [h["run_id"] for h in avc.history(rule="course-description")] == [a["run_id"]]
    assert avc.history(rule="course-code") == []


class NoDeleteRoot(LocalRoot):
    """The agent's SAS token: add, create, write, list; no delete."""

    def delete(self, path: str) -> None:
        raise PermissionError("AuthorizationPermissionMismatch")


def test_runs_never_delete(tmp_path):
    root, k2, clock = NoDeleteRoot(tmp_path), FakeK2(), Clock()
    ar = AgentRuns(Ctx(root, "avc"), k2, 90, clock, prompter=lambda r: PROMPT)
    q = Queue(root, k2, lambda c: ar, lambda: ["avc"], clock=clock)
    a = start(ar)
    q.tick()
    ar.done(a["run_id"], "Couldn't publish", failed=True, by="agent", summary="## Report\n")
    q.tick()
    assert ar.summary(a["run_id"]) == "## Report\n" and ar.run(a["run_id"])["state"] == "failed"


# -- K2 client ----------------------------------------------------------------------------------------
class _K2Handler(BaseHTTPRequestHandler):
    seen: list[dict] = []

    def _answer(self, code: int, doc: dict) -> None:
        data = json.dumps(doc).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        type(self).seen.append({"path": self.path, "auth": self.headers["Authorization"], "body": body})
        if self.headers["Authorization"] != "Bearer k2sk_test":
            return self._answer(401, {"error": "invalid or missing API key"})
        if "/w/nope/" in self.path:
            return self._answer(404, {"error": "no such workspace"})
        if self.path.endswith("/kill"):
            return self._answer(200, {"killed": True, "resumable": True})
        mode = body.get("prompt")
        if mode == "full":
            return self._answer(429, {"code": "workspace-cell-cap",
                                      "error": "concurrent host-session limit reached for this workspace"})
        if mode == "slow":
            time.sleep(1.5)
        return self._answer(200, {"sessionId": "df01d0f9", "agentName": "api-x", "workspace": "golden-rules"})

    def do_GET(self):  # noqa: N802
        if self.path.endswith("/gone"):
            return self._answer(404, {"error": "no such workspace"})
        if self.path.endswith("/done"):
            return self._answer(200, {"live": False, "phase": "finished"})
        return self._answer(200, {"live": True, "phase": "working"})

    def log_message(self, *a):
        pass


@pytest.fixture
def k2_server():
    _K2Handler.seen = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _K2Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_k2_client_maps_k2s_answers(k2_server):
    k2 = K2(k2_server, "k2sk_test", "golden-rules", timeout=1)
    assert k2.spawn("# run", 5400, "run-A") == "df01d0f9"
    seen = _K2Handler.seen[0]
    assert seen["path"] == "/v1/w/golden-rules/host-sessions" and seen["auth"] == "Bearer k2sk_test"
    assert seen["body"] == {"prompt": "# run", "timeoutSecs": 5400, "clientRequestId": "run-A"}
    with pytest.raises(K2Full):
        k2.spawn("full", 60, "run-B")
    with pytest.raises(K2Lost):  # maybe started: never resend
        k2.spawn("slow", 60, "run-C")
    assert k2.session("df01d0f9") == {"live": True, "phase": "working"}
    assert k2.session("done")["live"] is False and k2.session("gone") is None
    assert k2.kill("df01d0f9") is True and _K2Handler.seen[-1]["path"].endswith("/host-sessions/df01d0f9/kill")
    with pytest.raises(K2Unavailable, match="refused the Studio's key"):
        K2(k2_server, "wrong", timeout=1).spawn("x", 60, "r")
    with pytest.raises(K2Unavailable, match="no workspace 'nope'"):
        K2(k2_server, "k2sk_test", "nope", timeout=1).spawn("x", 60, "r")
    with pytest.raises(K2Unavailable, match="couldn't reach K2"):
        K2("http://127.0.0.1:9", "k", timeout=1).spawn("x", 60, "r")


# -- routes ---------------------------------------------------------------------------------------------
def test_routes_fall_back_to_the_prompt_when_runs_are_off(tmp_path):
    c = TestClient(create_app(str(tmp_path)))
    cfg = c.get("/api/agent-runs/config").json()
    assert cfg["enabled"] is False and "no K2 server" in cfg["off_reason"] and cfg["cap"] == 2
    r = c.post("/api/catalogs/avc/agent-runs", json={"scope": {"kind": "rules", "rules": ["x"]}, "author": "Jared"})
    assert r.status_code == 503 and r.json()["fallback"] == "prompt"
    d = c.get("/api/catalogs/avc/agent-runs/current").json()
    assert d["runs"] == [] and d["recent"] == {} and d["slots"]["cap"] == 2 and d["last"] is None
    q = c.get("/api/agent-runs/queue").json()
    assert q["working"] == [] and q["waiting"] == [] and q["median_min"] == 6


def test_routes_watch_cancel_and_queue(tmp_path):
    app = create_app(str(tmp_path), agent={"prompt_users": "Eric Riddoch, Seth Alt", "max_runs": 1})
    st = app.state.studio
    st.k2 = st.queue.k2 = FakeK2(cap=1)
    c = TestClient(app)
    ar = st.agent_runs("avc")
    a = ar.start({"kind": "rules", "rules": ["course-description"]}, "Jared Diener",
                 rule_names={"course-description": "Description"})
    b = ar.start({"kind": "rules", "rules": ["course-code"]}, "Seth Alt")
    ar.prompter = None
    st.queue.runs_for = lambda f: ar
    st.queue.catalogs = lambda: ["avc"]
    st.queue.tick()
    d = c.get("/api/catalogs/avc/agent-runs/current").json()
    assert [(r["run_id"], r["state"]) for r in d["runs"]] == [(a["run_id"], "running"), (b["run_id"], "waiting")]
    assert d["runs"][1]["queue"]["place"] == 1 and d["runs"][0]["queue"]["left_min"] == 6
    assert d["slots"]["cap"] == 1 and d["slots"]["waiting"][0]["run"] == b["run_id"]
    assert d["runs"][0]["notes"][0]["text"] == "Started by Jared Diener"
    q = c.get("/api/agent-runs/queue").json()
    assert q["working"][0]["rule_names"] == ["Description"] and q["waiting"][0]["start_in_min"] == 6
    r = c.post(f"/api/catalogs/avc/agent-runs/{a['run_id']}/cancel", json={"author": "Cadence Calixto"})
    assert r.json()["run"]["state"] == "cancelled"
    d = c.get("/api/catalogs/avc/agent-runs/current").json()
    assert d["last"]["state"] == "cancelled"
    assert d["recent"]["course-description"]["rule_name"] == "Description"
    assert c.post("/api/catalogs/avc/agent-runs/nope/cancel", json={"author": "x"}).status_code == 409
    assert [h["run_id"] for h in c.get("/api/catalogs/avc/agent-runs?rule=course-description").json()] == [a["run_id"]]
    one = c.get(f"/api/catalogs/avc/agent-runs/{a['run_id']}").json()
    assert one["run"]["state"] == "cancelled" and one["report"] is None and one["summary"] is None
    assert c.get("/api/catalogs/avc/agent-runs/nope").status_code == 404
