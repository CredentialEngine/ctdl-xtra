# Q + R — Run Claude on K2 from the Studio: questions and findings

The ask (Eric, 2026-10-27): when someone presses a **generate** button in the Studio, don't open the prompt. Send it over
HTTP to the `golden-rules` agent on K2 (a self-hosted agent server) and let Claude do the work there. Runs take
tens of minutes, so the UI should show read-only progress, survive a reload or a closed laptop, and stop two people
from starting runs that collide.

This file lists the questions that decide the design, each with what research found. Code was read, not changed.
K2 citations are into `Alakazam-211/K2` at v0.46.5 (the version deployed); Studio citations are into this branch.

---

## A. The Studio today

**A1. Which buttons "generate"?**
Three, all of which end in a prompt for a human to paste into Claude Code:

| Button | Where | Today |
|---|---|---|
| **Generate rules** | Catalog picker, on a catalog with no rules (`web/src/catalogs/CatalogPicker.tsx:76`) | Opens `GenerateRulesModal` with the first-ruleset prompt (`GET /api/catalogs/{c}/prompt/first-rules`) |
| **Improve this rule** | Rules tab header (`web/src/rules/RuleHead.tsx:67`) | Links to the Prompt tab with the rule selected |
| **Copy prompt** | Prompt tab (`web/src/prompt/PromptTab.tsx:145`) | Copies one rule's prompt, or the "needs work" prompt (`GET /api/catalogs/{c}/prompt`) |

**A2. What does the server look like?** FastAPI (`server/app.py`), one router module per area. One `Studio` object
holds the storage root and a cached `Ctx` per catalog (`server/state.py`).

**A3. How many Studios share state?** Several: a deployed one and anyone's laptop
(`golden-datasets serve`), all on the same Azure root. **So any lock or run record has to live on the root, not in a
server's memory.**

**A4. Can the root do a lock?** Yes. `Root.write_bytes(path, data, if_none_match=True)` creates only if absent, and
`if_match=etag` replaces only if unchanged; both raise `ConflictError` (`storage.py:112-115`), on Azure and local
roots alike. `profiles.json` already uses this (`routes_profiles.py`).

**A5. Will the Studio notice what the agent publishes?** Yes. Each catalog's manifest is re-read every 3 s
(`Ctx(..., manifest_ttl=3.0)`, `state.py`), so a ruleset version the agent publishes shows up on its own.

**A6. Who is the user?** A profile (name + role `sme` / `engineer`) the browser remembers; there is no login beyond the
shared password (`routes_profiles.py`). Clients send `author` in request bodies.

**A7. Does the UI poll anything?** The catalog picker polls every 2 s (`CatalogPicker.tsx:36`). There is no SSE or
websocket anywhere; polling fits the codebase.

**A8. Does the prompt work as-is on K2?** Almost. It installs the CLI with `uv tool install` from this repo (uv is in
the K2 image) and, for Azure, says to `az login`. K2 has no `az`; it has SAS tokens in
`/var/lib/k2/work/golden-datasets.env`, which the CLI loads from any workspace under `/var/lib/k2/work/`
(`cli.py:26-38`, `storage.py:296`). The setup section needs a K2 variant.

## B. K2's API

**B1. Can the API message the existing `golden-rules` agent?** Yes, with one route and three switches.
`golden-rules` is a K2 workspace (handle `golden-rules`, path `/var/lib/k2/work/golden-rules`, default agent
`claude`), and `POST /v1/w/golden-rules/message` `{text, from}` types the text into that workspace's one
("canonical") agent, waking it if dormant (`v1_ws_message.rs:1-13, 143-174`). It needs:
- an API key with `--allow canonical-message` (off by default, `api_keys.rs:166-174`) and `--workspaces golden-rules`;
- the workspace's **"Let agents on other servers message this agent"** on (`allowRemoteInstruct`, now `0`), else
  `200 {"delivered": false, "mode": "declined"}`;
- the agent not busy, else **`409 {"reason": "agent_busy"}`**. K2 doesn't queue.

It returns once the text is typed (at most ~20 s for a wake). It does **not** wait for the turn.

**B2. Can we watch that agent's progress or know when it's done, over the API?** **No.** Every read door on `/v1`
(status, messages, terminal stream) refuses the canonical session with a 404, and an API key can't open `/cli/*`
routes, where K2 does track turn state from Claude's hooks (`turnEnded`, working / idle) (`route_policy.rs:13-19`,
`activity_events.rs`). The only signal is the `409 agent_busy` you get when trying to send.

**B3. Is there an API door that does report progress and completion?** Yes: **host sessions**,
`POST /v1/w/golden-rules/host-sessions {prompt, timeout_secs}`. Each call starts a **fresh** Claude agent in the same
workspace (same folder, same `CLAUDE.md`, shown as its own tab in the K2 app) and returns a `sessionId`. Then:
- `GET …/host-sessions/<id>` → `phase` (`working`, `grace`, `finished`) and `latest_seq`;
- `GET …/host-sessions/<id>/messages?since=<seq>` → `{messages: [{seq, text, ts, final}], latest_seq}`: lines the
  agent itself sends with `k2 respond "<text>"`; `k2 respond --final` / `k2 done` mark the end;
- `POST …/host-sessions/<id>/kill` stops it;
- `POST …/host-sessions/<id>` `{prompt}` sends a follow-up into the live agent.

The messages buffer is in memory (1,000 lines; gone if the daemon restarts) (`sandbox_responses.rs`).

**B4. Do long runs get killed?** No. A working host session is never reaped; it is reaped only after `--final` /
`k2 done` plus 10 s, or `kill` (`sandbox_reaper.rs`). `timeout_secs` (30–86,400) only bounds callback-token lifetime.
The flip side: an agent that never says it's done stays up until we kill it.

**B5. What if two callers send at once?** Canonical: the busy check isn't atomic with the send, so two near-together
messages can both land; Claude then folds the second into its turn. Host sessions: two calls start two agents. **K2
does no locking for us; the Studio must.**

**B6. Can the agent call the Studio back?** Host sessions can carry `capabilities`: K2 mints short-lived signed tokens
for a URL, and the Studio verifies them against `GET /v1/jwks` (`docs/host-session-capability-envelope.md`). That
needs the agent to reach the Studio over the network, which works for a Studio next to K2 but not for a Studio on a
laptop. **The shared root is a channel every Studio can read and the agent can write** (it already has SAS tokens).

**B7. What does K2 need around it?** A Studio that can reach its HTTP API, and outbound access to Azure that the
`ceteststorage` firewall allows (a K2 whose address isn't allowed gets `AuthorizationFailure` on every blob). Claude on
K2 is signed in with a Claude subscription.

## C. Questions for Eric (answered 2026-10-27)

**C1. One shared agent, or a fresh agent per run?**

> **Answer:** We'll just keep using the golden-rules agent. It's welcome to hire or delegate the task to subagents.

**Note (Claude):** So runs go through `POST /v1/w/golden-rules/message` (B1), and the Studio can't read progress or
completion from K2 (B2). The spec gets both from the agent instead, through the storage root (B6): the agent reports
with `golden-datasets` commands, which every Studio can read. One agent also means one run at a time *in the agent*:
K2 answers `409 agent_busy` while it works (B1), so the Studio holds later runs until it's free.

**B8 (found after C1). What does K2 need for the canonical door?** The workspace must have an agent K2 can wake: a saved
canonical session or the workspace's **Agent** setting on (`projects.agent_enabled`); otherwise the send fails with
`no_agent_mode` (`workspace_msg.rs:1320-1338`). `golden-rules` has `agentMode: off` and `agentEnabled: 0`; Eric's open
Claude tab gives it a session, but turning Agent on is the safe setup.

**C2. What does the lock cover?**

> **Answer:** A lock per catalog is good.

**C3. Who can start and cancel a run?**

> **Answer:** Any user should be able to start a run. Honestly, if anyone shouldn't be able to launch a run from the
> button, it's engineers, because you can just give them the prompt and they can run it on their laptops. Eric and
> Seth should have a button dropdown that lets them either run it or take them to the prompt.

**Note (Claude):** So everyone gets **Run**; the profiles in a short list (Eric Riddoch, Seth Alt) get a split button
with **Run on K2** and **Open the prompt**. Cancel and Mark as ended are open to everyone too, recorded with the name.

**C4. How long before a run is given up?** Not answered. *Assumed: 90 minutes.*

**C5. Improve one rule or all of them?**

> **Answer:** The UI needs a more straightforward way to apply fixes to all rules at once. On one rule there's a button
> to improve just that rule, but there should be a UX that encourages improving all the rules, since an agent can do
> that, no problem.
