# Research Q4.2: can the Studio ask K2 whether the agent is still working?

Date: 2026-11-04. K2 source read at tag `v0.46.5` of `github.com/Alakazam-211/K2` (the version the K2 server runs).
Tags `v0.46.6` and `v0.46.7` have the same `/v1/w/<ws>/…` routes and an identical `v1_ws_message.rs`.
K2 paths below are relative to `crates/k2-daemon/src/` in that repo.

## Short answer

No. With an API key, K2 has no endpoint that reports the golden-rules agent's state (working, idle, errored) or
its last message. The October finding (`docs/qrspi/k2-runs/01-questions.md` B2) still holds in v0.46.5.

## What an API key can reach

An API key (`k2sk_…`) only ever authenticates `/v1/*` routes (`routes/http.rs:1641-1643`,
`routes/route_policy.rs:13-19`). These are every `/v1` route in v0.46.5 (`routes/dispatcher.rs:11920-12330`):

| Route | Capability | Says anything about the canonical agent? |
|---|---|---|
| `GET /v1/ping` | any key | No. Echoes the key and which API families are on. |
| `POST /v1/w/<ws>/message` | `canonical_message` | Only indirectly: `409 agent_busy` when it is working. Not a probe: if the agent is free, the text is delivered. |
| `GET/POST /v1/w/<ws>/host-sessions…` (list, status, messages, kill, queue) | `host_sessions` | No. The canonical session is refused with a 404 (`v1_host_sessions.rs:33-35`, `:1617`, `:1210`). |
| `/v1/sandboxes…`, `/v1/w/<ws>/sessions…` | `sandboxes` | No. Off on this server (`"sandboxes":"none"`). |
| `/v1/w/<ws>/context`, `/wiki/notes`, `/db…`, `/v1/w`, `/v1/agents/…`, `/v1/agent-teams/…` | various | No. Context layers, notes, a data sidecar, and the hire ledger. |
| `/v1/jwks`, `/v1/chat/jwks` | public | No. |

There is no `/v1/.../status`, no OpenAPI document, and no GET for a `deliveryId`. The only lookup of a delivery id
is `GET /cli/msg/who` (`hire_routes.rs:882`), a `/cli` route an API key can't open.

### The `message` door, for reference

`POST /v1/w/golden-rules/message` (`v1_ws_message.rs:75-182`):

```json
// request
{"text": "…", "from": "Golden Dataset Studio · Eric", "wake": true}

// 200, delivered (returns once the text is typed; it does not wait for the turn)
{"delivered": true, "mode": "live", "result": {"success": true, …}, "deliveryId": "m_…"}

// 200, the workspace doesn't accept remote messages
{"delivered": false, "mode": "declined", "reason": "remote_instruction_disabled"}

// 409, the agent is working or waiting on a permission prompt
{"delivered": false, "reason": "agent_busy", "agentStatus": "working" | "permission"}
```

Busy means K2's activity display is `working` or `waiting`. `idle`, `monitoring` (background work only) and
`unverifiable` all accept the message (`v1_ws_message.rs:43-55`). So a "probe" send costs a full agent turn whenever
the agent is not busy. It can't be used as a cheap health check.

## Checked against the K2 server

Read-only GETs with the Studio's key:

| Request | Answer |
|---|---|
| `GET /v1/ping` | `200 {"api":{"enabled":true,"hostSessions":true,"sandboxes":"none"},"ok":true,"principal":"<key id>"}` |
| `GET /v1/w/golden-rules/host-sessions` | `404 {"error":"no such workspace"}` (key lacks `host_sessions`) |
| `GET /v1/w/golden-rules/context` | `404 {"error":"no such workspace"}` |
| `GET /v1/w/golden-rules/status`, `/v1/openapi.json`, `/v1/agents/instances` | `404 {"error":"route not found"}` |
| `GET /cli/activity/snapshot?workspace=golden-rules` | `403 {"error":"invalid or missing token"}` |

The Studio's key can do exactly one thing: send a message. It can't read any status.

## Where K2 does keep the state (not reachable with an API key)

K2 tracks each session from Claude's hooks and transcript: `working`, `monitoring`, `waiting`, `idle`,
`unverifiable` (`k2-core/src/activity/row.rs:179-196`). Two doors expose it:

| Door | Credential | Answer |
|---|---|---|
| `GET /cli/activity/snapshot?workspace=<ws>` | a person's K2 login or the owner token (Member floor, `routes/route_policy.rs:114`) | every activity row and the workspace rollup |
| same route, guest view (`activity_routes.rs:96-142`) | an App pass (`k2skn_…`) whose room is `golden-rules` with `activity:read` | `{"workspace":"golden-rules","status":"working"\|"permission"\|"idle"\|"unknown","since":<ms>,"serverNow":<ms>,"sessions":[{"agentName","status","since","counts":{…}}]}` |

Neither returns the agent's last assistant message. The App "Thread" (`GET /cli/thread`, `thread:read`) carries
posts in the room, not Claude's transcript, so an agent that only explains an error in its own chat leaves nothing
there. An App pass also needs a K2 App, a guest login in it, and a room grant: a new credential to create, rotate,
and store, for a status word.

Even the status word would not have caught the 2026-11-04 failure. After the agent explained the Azure error and
stopped, K2 would have said `idle`. "Idle" looks the same as "finished but forgot `run done`", and the Studio still
wouldn't know why.

## The fallback: "Not responding" after 5 minutes without a note

The UI already has everything it needs. No server or K2 change is required.

| Data | Where | Notes |
|---|---|---|
| `sent_at` | `agent_runs.py:289` (set when K2 accepts the message); `AgentRun` in `web/src/agent/api.ts:14` | The right start for the 5-minute clock. `created_at` would count time spent `waiting` while the agent was busy. |
| `created_at`, `deadline` | `agent_runs.py:251-252` (deadline = start + 90 min) | `deadline` stays the hard end (`advance()`, `agent_runs.py:303-306`). |
| `state` | `running` only after delivery (`agent_runs.py:289`) | Show "Not responding" only in `running`, never in `sending`/`waiting`. |
| `notes` with `kind` and `at` | `log.jsonl`, read by `notes()` (`agent_runs.py:182-193`); `RunNote` in `api.ts:19` | The Studio writes `kind: "studio"` lines ("Started by…", "Sent to…"); the agent writes `kind: "note"`. Count only `note` (and `done`). `headline()` already does this (`RunBar.tsx:35`). |
| `now` | server time, `routes_agent.py:66`, polled every 3 s (`state.tsx`, `POLL_MS`) | Server time, so every Studio and browser agrees, whatever the laptop clock says. |

The rule, in `headline()` (`RunBar.tsx:31-38`):

```ts
const lastAgentLine = [...notes].reverse().find((n) => n.kind === "note");
const silentFor = Date.parse(now) - Date.parse(lastAgentLine?.at ?? run.sent_at ?? run.created_at);
if (run.state === "running" && !lastAgentLine && silentFor > 5 * 60_000) { /* "Not responding" */ }
```

What the bar can offer when it shows "Not responding": **Open K2** (the Watch panel already links it,
`RunBar.tsx:115`), **Mark as ended** (`RunBar.tsx:95-101`), and **Cancel**. The run stays live until someone acts or
the 90-minute deadline ends it.

Open choices for the spec:
- Only "no note yet", or also "no new note for N minutes" later in the run? The agent may legitimately be quiet
  during a long step, so a later threshold should be longer (say 15 minutes).
- Whether the agent's prompt should require a first note within the first minute ("Starting: …"). That makes a
  5-minute silence a much stronger signal, at no extra cost.

## Recommendation

Do the UI-only fallback: once a run is `running`, show "Not responding" when no `note` has arrived 5 minutes after
`sent_at`, with Open K2, Mark as ended and Cancel next to it. K2 v0.46.5 has no API-key endpoint for the canonical
agent's state or last message, and the only status door (an App pass on `/cli/activity/snapshot`) would need a new
credential and would still only say `idle`, not why. Pair it with a prompt rule that the agent's first action is a
`run note`, so silence really means something went wrong.
