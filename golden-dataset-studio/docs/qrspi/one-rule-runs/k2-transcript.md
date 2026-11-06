# K2 host-sessions: a real transcript (2026-11-05)

Recorded against a **K2 v0.46.5 daemon started on a laptop just for this test** (its own home folder, listening on
127.0.0.1:7499, nothing connected to k2.dev). K2 v0.46.5 is the version the K2 server runs. Nothing was created on the
K2 server. Setup on the test daemon:
- a workspace `golden-rules`;
- a stand-in agent instead of Claude: a script that logs what it receives and works for 240 s;
- `host-session-cell-cap` 2;
- an API key limited to `golden-rules` and `host-sessions`.

Tokens are redacted. "took" is how long K2 took to answer. Steps 1–12 ran in one go; 13–18 right after. The last
section is a separate test of the workspace's guest policy.

```text

### 1. start run A  (t+0s, took 0.1s)
POST /v1/w/golden-rules/host-sessions
{"prompt": "# Golden Dataset Studio run run-A (test prompt)", "timeoutSecs": 600, "clientRequestId": "run-A"}
→ 200
{
 "agentName": "api-b62ace7c-1117-4e45-ac5d-49e6fe922b8f-5b14034a-5bed-4eb4-9bc8-2cc1a14995fe",
 "modelApplied": null,
 "modelSource": "none",
 "sandbox": "none",
 "sessionId": "df01d0f9-571f-41c1-aa7b-a93e22903f85",
 "stream": {
  "grid": "/cli/sessions/grid?session=df01d0f9-571f-41c1-aa7b-a93e22903f85&token=k2st_<redacted>"
 },
 "workspace": "golden-rules"
}

### 2. start run B  (t+0s, took 0.0s)
POST /v1/w/golden-rules/host-sessions
{"prompt": "# Golden Dataset Studio run run-B (test prompt)", "timeoutSecs": 600, "clientRequestId": "run-B"}
→ 200
{
 "agentName": "api-b62ace7c-1117-4e45-ac5d-49e6fe922b8f-2d6341c9-d2e1-4d5d-b8d7-db43e2661405",
 "modelApplied": null,
 "modelSource": "none",
 "sandbox": "none",
 "sessionId": "7ab5f05d-1769-4402-9aaf-f0bd2c59528f",
 "stream": {
  "grid": "/cli/sessions/grid?session=7ab5f05d-1769-4402-9aaf-f0bd2c59528f&token=k2st_<redacted>"
 },
 "workspace": "golden-rules"
}

### 3. start run A again, same clientRequestId (a retried start)  (t+0s, took 30.0s)
POST /v1/w/golden-rules/host-sessions
{"prompt": "# Golden Dataset Studio run run-A (test prompt)", "timeoutSecs": 600, "clientRequestId": "run-A"}
→ 429
{
 "code": "workspace-cell-cap",
 "error": "concurrent host-session limit reached for this workspace"
}

### 4. start run C: the workspace cap is 2  (t+30s, took 30.0s)
POST /v1/w/golden-rules/host-sessions
{"prompt": "# Golden Dataset Studio run run-C (test prompt)", "timeoutSecs": 600, "clientRequestId": "run-C"}
→ 429
{
 "code": "workspace-cell-cap",
 "error": "concurrent host-session limit reached for this workspace"
}

### 5. list the workspace's sessions  (t+60s, took 0.0s)
GET /v1/w/golden-rules/host-sessions
→ 200
{
 "sessions": [],
 "workspace": "golden-rules"
}

### 6. one session's state  (t+60s, took 0.0s)
GET /v1/w/golden-rules/host-sessions/df01d0f9-571f-41c1-aa7b-a93e22903f85
→ 200
{
 "agentName": null,
 "durable": false,
 "latest_seq": 0,
 "live": true,
 "phase": "working",
 "reaper": "working",
 "sessionId": "df01d0f9-571f-41c1-aa7b-a93e22903f85",
 "started": true,
 "workspace": "golden-rules"
}

### 7. kill run A (run done / cancel)  (t+60s, took 0.1s)
POST /v1/w/golden-rules/host-sessions/df01d0f9-571f-41c1-aa7b-a93e22903f85/kill
→ 200
{
 "killed": true,
 "resumable": true,
 "sessionId": "df01d0f9-571f-41c1-aa7b-a93e22903f85"
}

### 8. start run C again after A was killed  (t+60s, took 0.0s)
POST /v1/w/golden-rules/host-sessions
{"prompt": "# Golden Dataset Studio run run-C (test prompt)", "timeoutSecs": 600, "clientRequestId": "run-C"}
→ 200
{
 "agentName": "api-b62ace7c-1117-4e45-ac5d-49e6fe922b8f-cd609db9-df79-43c7-abb0-c0d62071643f",
 "modelApplied": null,
 "modelSource": "none",
 "sandbox": "none",
 "sessionId": "13a02348-fd4b-4fc0-84ac-693c310b3108",
 "stream": {
  "grid": "/cli/sessions/grid?session=13a02348-fd4b-4fc0-84ac-693c310b3108&token=k2st_<redacted>"
 },
 "workspace": "golden-rules"
}

### 9. run C's state  (t+60s, took 0.0s)
GET /v1/w/golden-rules/host-sessions/13a02348-fd4b-4fc0-84ac-693c310b3108
→ 200
{
 "agentName": null,
 "durable": false,
 "latest_seq": 0,
 "live": true,
 "phase": "working",
 "reaper": "working",
 "sessionId": "13a02348-fd4b-4fc0-84ac-693c310b3108",
 "started": true,
 "workspace": "golden-rules"
}

### 10. wrong key  (t+60s, took 0.0s)
POST /v1/w/golden-rules/host-sessions
{"prompt": "x"}
→ 401
{
 "error": "invalid or missing API key"
}

### 11. a workspace the key can't use  (t+60s, took 0.0s)
POST /v1/w/nope/host-sessions
{"prompt": "x"}
→ 404
{
 "error": "no such workspace"
}

### 12. clean up  (t+60s, took 0.1s)
POST /v1/w/golden-rules/host-sessions/7ab5f05d-1769-4402-9aaf-f0bd2c59528f/kill
→ 200
{
 "killed": true,
 "resumable": true,
 "sessionId": "7ab5f05d-1769-4402-9aaf-f0bd2c59528f"
}

### 12. clean up  (t+60s, took 0.1s)
POST /v1/w/golden-rules/host-sessions/13a02348-fd4b-4fc0-84ac-693c310b3108/kill
→ 200
{
 "killed": true,
 "resumable": true,
 "sessionId": "13a02348-fd4b-4fc0-84ac-693c310b3108"
}

### 13. start run D with a 20 s deadline (t+0s, took 0.0s)
POST /v1/w/golden-rules/host-sessions
{"prompt": "# Golden Dataset Studio run run-D (deadline test)", "timeoutSecs": 20, "clientRequestId": "run-D"}
→ 200
{
 "agentName": "api-b62ace7c-1117-4e45-ac5d-49e6fe922b8f-7c942f00-58b3-4579-a3ab-83a89fac8787",
 "modelApplied": null,
 "modelSource": "none",
 "sandbox": "none",
 "sessionId": "20bc1be0-775a-4395-b967-8080d19042eb",
 "stream": {
  "grid": "/cli/sessions/grid?session=20bc1be0-775a-4395-b967-8080d19042eb&token=k2st_<redacted>"
 },
 "workspace": "golden-rules"
}

### 14. run D at 10 s (t+10s, took 0.0s)
GET /v1/w/golden-rules/host-sessions/20bc1be0-775a-4395-b967-8080d19042eb
→ 200
{
 "agentName": null,
 "durable": false,
 "latest_seq": 0,
 "live": true,
 "phase": "working",
 "reaper": "working",
 "sessionId": "20bc1be0-775a-4395-b967-8080d19042eb",
 "started": true,
 "workspace": "golden-rules"
}

### 14. run D at 25 s (t+25s, took 0.0s)
GET /v1/w/golden-rules/host-sessions/20bc1be0-775a-4395-b967-8080d19042eb
→ 200
{
 "agentName": null,
 "durable": false,
 "latest_seq": 0,
 "live": true,
 "phase": "working",
 "reaper": "working",
 "sessionId": "20bc1be0-775a-4395-b967-8080d19042eb",
 "started": true,
 "workspace": "golden-rules"
}

### 14. run D at 40 s (t+40s, took 0.0s)
GET /v1/w/golden-rules/host-sessions/20bc1be0-775a-4395-b967-8080d19042eb
→ 200
{
 "agentName": null,
 "durable": false,
 "latest_seq": 0,
 "live": true,
 "phase": "working",
 "reaper": "working",
 "sessionId": "20bc1be0-775a-4395-b967-8080d19042eb",
 "started": true,
 "workspace": "golden-rules"
}

### 15. start run E (deadline 600 s): is D's slot free again? (t+40s, took 0.0s)
POST /v1/w/golden-rules/host-sessions
{"prompt": "# Golden Dataset Studio run run-E", "timeoutSecs": 600, "clientRequestId": "run-E"}
→ 200
{
 "agentName": "api-b62ace7c-1117-4e45-ac5d-49e6fe922b8f-fbf5a753-4f79-4af3-9b91-cb9dffe85724",
 "modelApplied": null,
 "modelSource": "none",
 "sandbox": "none",
 "sessionId": "a59a467f-7012-40ce-a554-b55a39bbc7ae",
 "stream": {
  "grid": "/cli/sessions/grid?session=a59a467f-7012-40ce-a554-b55a39bbc7ae&token=k2st_<redacted>"
 },
 "workspace": "golden-rules"
}

### 16. kill run E (t+40s, took 0.1s)
POST /v1/w/golden-rules/host-sessions/a59a467f-7012-40ce-a554-b55a39bbc7ae/kill
→ 200
{
 "killed": true,
 "resumable": true,
 "sessionId": "a59a467f-7012-40ce-a554-b55a39bbc7ae"
}

### 17. kill run E again (already gone) (t+40s, took 0.0s)
POST /v1/w/golden-rules/host-sessions/a59a467f-7012-40ce-a554-b55a39bbc7ae/kill
→ 200
{
 "indexCleared": false,
 "killed": false,
 "reason": "not_live",
 "sessionId": "a59a467f-7012-40ce-a554-b55a39bbc7ae"
}

### 18. run E after kill (t+40s, took 0.0s)
GET /v1/w/golden-rules/host-sessions/a59a467f-7012-40ce-a554-b55a39bbc7ae
→ 200
{
 "agentName": null,
 "durable": false,
 "latest_seq": 0,
 "live": false,
 "phase": "gone",
 "reaper": "none",
 "sessionId": "a59a467f-7012-40ce-a554-b55a39bbc7ae",
 "started": false,
 "workspace": "golden-rules"
}
```

## Session D (`timeoutSecs: 20`), polled every 10 s

```text
22:08:34  spawned
22:09:31 … 22:12:32  GET → phase "working", live true   (the 20 s deadline was not enforced)
22:12:34  the stand-in agent exits by itself (240 s)  → K2 log: "released concurrent-cell quota slot"
22:12:42 … 22:13:43  GET → 404 {"error": "no such workspace"}
```

## What the agent received (stand-in agent's log, session A)

```text
argv: --dangerously-skip-permissions
env:  K2_SESSION_ID=df01d0f9-…, K2_API_CELL=1, K2_PORT=7499, K2_HOOK_SOCK=…/cells/df01d0f9-….sock, K2_HOOK_TOKEN=<redacted>
got:  [K2 API] You were invoked through the K2 API. Report progress and results back to the caller by running: k2 respond '<your message>' — and send your final answer with: k2 respond --final '<your answer…
got:  [K2 API guest policy] The external API client is NOT the workspace owner. Prefer read-only work; do not modify files, wiki notes, or secrets unless a tool explicitly allows it for this call. Report pr…
got:  # Golden Dataset Studio run run-A (test prompt)
```

## With a workspace guest policy set (`k2 workspace api-guest-policy set golden-rules "…"`)

```text
got:  [K2 API] You were invoked through the K2 API. Report progress … k2 respond …
got:  [Golden Dataset Studio] This session is a Golden Dataset Studio run. Follow the prompt below; it may change files in its run folder and publish through golden-datasets. Report only with golden-datasets run note / run done, not k2 respond.
got:  # Golden Dataset Studio run run-F (policy test)
POST /v1/w/golden-rules/host-sessions/30bc4af9-…/kill → 200 {"killed": true, "resumable": true, "sessionId": "30bc4af9-…"}
```

---

## Live test plan on the K2 server (pass 6; run 2026-11-05, results below)

Eric approved a test on the K2 server with a cap of 2. **Run on 2026-11-05 ~16:25 MST; results in the next section.** The main session runs it after
Eric confirms these exact steps. It changes **three things** on the server (a key and two workspace settings), and
each one has its undo below. It starts at most **two real Claude sessions**, for a few minutes, with a harmless
prompt. It doesn't touch the canonical `golden-rules` agent, its chat, the storage root or any catalog.

All calls run **inside the pod**, against the daemon on `127.0.0.1:7420`. The owner token never leaves the pod;
`deploy.sh` reaches the daemon the same way (`deploy.sh:30-33`). The `k2` CLI isn't used, because it needs
`python3`, which the image lacks.

```sh
x()   { kubectl -n k2 exec -i k2-0 -c k2-daemon -- "$@"; }
# owner routes (/cli/...): the daemon's owner token, read inside the pod
cli() { x sh -c "curl -sS -H 'Content-Type: application/json' ${2:+--data-binary @-} \"http://127.0.0.1:7420$1\$(case '$1' in *\?*) echo '&';; *) echo '?';; esac)token=\$(cat .k2/daemon.token)\""; }
# /v1 routes: the test key, passed on stdin so it isn't in the process list
v1()  { x sh -c 'read -r K; curl -sS -w "\n[%{http_code} in %{time_total}s]\n" -H "Authorization: Bearer $K" -H "Content-Type: application/json" "$@"' sh "$@"; }
WS=/var/lib/k2/work/golden-rules
```

### Step 0. Record what's there now (no change)

```sh
cli "/cli/settings?project=$WS"                       # note hostSessionCellCap and the api guest policy
x sh -c 'cat /sys/fs/cgroup/memory/memory.usage_in_bytes; ps -eo pid,rss,etime,args | grep -c "[c]laude"'
```

Expected: no cap set (K2's default, 15) and the default guest policy. Save the output: the undo steps restore exactly
these values.

### Step 1. Create a test key (change 1)

```sh
printf '%s' '{"label":"studio-host-sessions-test","workspaces":["golden-rules"],"allow":["host-sessions"]}' \
  | cli /cli/api-keys/create body
```

The response holds the key (`k2sk_…`, shown once) and its `id`. Keep the key in a local file with mode 600, outside
the repository; it is used below as `printf '%s\n' "$KEY" | v1 …`.
**Undo:** `printf '{"id":"<id>"}' | cli /cli/api-keys/revoke body`.

### Step 2. Cap the workspace at 2 live sessions (change 2)

```sh
printf '{"project":"%s","fields":{"host_session_cell_cap":"2"}}' "$WS" | cli /cli/workspace/set body
cli "/cli/settings?project=$WS"                       # hostSessionCellCap: 2
```

**Undo:** the same call with `"host_session_cell_cap":"default"`, which is what
`k2 workspace host-session-cell-cap set golden-rules default` sends. Use the value from step 0 if one was set.

### Step 3. The workspace's guest policy (change 3)

```sh
printf '{"project":"%s","fields":{"api_guest_policy":"[Golden Dataset Studio] This session is a Golden Dataset Studio run. Follow the prompt below; it may change files in its run folder and publish through golden-datasets. Report only with golden-datasets run note / run done, not k2 respond."}}' "$WS" \
  | cli /cli/workspace/set body
```

**Undo:** the same call with `"api_guest_policy":""` (what `--default` sends), or the text from step 0.

### Step 4. The queue, with real Claude sessions

The test prompt: *"K2 connection test for Golden Dataset Studio. Run `pwd` once, reply with its output in one line,
then stop. Don't change any file."*

| # | Request | Expect |
|---|---|---|
| 4a | `POST /v1/w/golden-rules/host-sessions` `{"prompt": "<test prompt>", "timeoutSecs": 600, "clientRequestId": "live-A"}` | **200**, a `sessionId` (A) |
| 4b | the same with `"clientRequestId": "live-B"` | **200**, session B |
| 4c | the same with `"clientRequestId": "live-C"` | **429** after about **30 s**, `{"code": "workspace-cell-cap"}`. **This proves the cap of 2.** |
| 4d | `GET /v1/w/golden-rules/host-sessions/<A>` and `<B>` | 200, `phase` `working`; or **404** if Claude already finished (it exited, so the slot is free) |
| 4e | in the pod: memory and processes, as in step 0 | 2 more `claude` processes, about +600 MB at most; no out-of-memory event (`memory.failcnt` 0) |
| 4f | `POST /v1/w/golden-rules/host-sessions/<A>/kill` `{}` | 200 `{"killed": true}`, or `{"killed": false, "reason": "not_live"}` if A already ended |
| 4g | start C again | **200**: the freed place is reused |
| 4h | kill B and C | 200 |
| 4i | the K2 app, Running Agents | the canonical `golden-rules` agent is unchanged; the host sessions show as API tabs, then go |

Also check:
- each session's first lines in the K2 app show the **Golden Dataset Studio** guest policy (step 3), not "Prefer
  read-only work";
- each session ran as `--dangerously-skip-permissions`, in `/var/lib/k2/work/golden-rules`;
- whether the canonical agent counts toward the cap (if 4b gets 429, it does, and the Studio's cap must be 1 + 2).

Example call: `printf '%s\n' "$KEY" | v1 -X POST -d '{"prompt":"…","timeoutSecs":600,"clientRequestId":"live-A"}' http://127.0.0.1:7420/v1/w/golden-rules/host-sessions`.

### Step 5. Undo, in this order

1. Kill any session still live (4f/4h; repeating a kill is safe).
2. Revoke the test key (step 1's undo). The Studio's real key is made later, when the code ships, with
   `"allow":["host-sessions","canonical-message"]`.
3. Decide with Eric whether to **keep** the cap of 2 and the guest policy, which the Studio will need, or restore step 0's
   values (steps 2 and 3's undo).
4. `cli "/cli/settings?project=$WS"` again, and compare with step 0.

Record the transcript (key redacted) below this plan, like the laptop transcript above.


## Live test results on the K2 server (2026-11-05, ~16:25 MST)

Eric decided: change only the cap (keep it at 2 afterwards); leave the guest policy as it is. So step 3 was **not**
done. Keys and stream tokens are redacted.

**Step 0 (before):** `hostSessionCellCap: null` (K2's default, 15); guest policy the K2 default ("[K2 API guest
policy] … Prefer read-only work …"); 3 `claude` processes already running (two 6 days old, one 1 day old); memory
use of the pod 3,440,705,536 bytes.

**Step 1:** created key `studio-host-sessions-test` (id `3f013305-…`), capabilities
`{"hostSessions": true, "canonicalMessage": false, "db": false, "hire": false, "sandboxes": false}`.

**Step 2:** `/cli/workspace/set {"host_session_cell_cap":"2"}` →
`{"actions":[{"field":"host_session_cell_cap","status":"done","value":"2"}],"changed":true,"ok":true}`; settings then
show `hostSessionCellCap = 2`.

**Step 4, first try (a quick prompt, "run pwd and stop"):**

| Request | Response |
|---|---|
| start A | `200` in 0.07 s, `sessionId a778ae62-…` |
| start B | `200` in 0.03 s, `sessionId 28d7a784-…` |
| start C | `200` in **23.9 s**: K2 held C until a place freed (A and B had already finished `pwd`) |
| status A, B | `200 {"live": false, "phase": "finished", …}` (on the server a finished session answers 200 `finished`; the laptop K2 answered 404) |
| status C | `200 {"live": true, "phase": "working", "reaper": "grace"}` |
| kill C | `200 {"killed": true, "resumable": true}` |

**Step 4, with sessions that stay busy (prompt: run `sleep 150`):**

| Request | Response |
|---|---|
| start A2 | `200` in 0.03 s, `sessionId 4e020266-…` |
| start B2 | `200` in 0.03 s, `sessionId 6a555324-…` (so the canonical `golden-rules` agent does **not** count toward the cap) |
| start C2, 20 s later | **`429` in 30.0 s, `{"code":"workspace-cell-cap","error":"concurrent host-session limit reached for this workspace"}`**: the cap of 2 works |
| memory | pod 3,780,149,248 bytes; 5 `claude` processes, 1,499 MB RSS together (the 3 old ones + A2 + B2) |
| kill A2 | `200 {"killed": true, "resumable": true}` |
| start C2 again | `200` in **0.03 s**: the freed place is reused at once |
| kill B2, kill C2 | `200 {"killed": true}` each |

**Step 5 (after):** test key revoked (`{"success":true}`; the key then gets `401 invalid or missing API key`);
`hostSessionCellCap = 2` **kept**, as Eric asked; guest policy unchanged (K2 default); only the 3 original `claude`
processes remain.

**What this means for the Studio:**
- The queue works as designed: a third start blocks up to 30 s and then gets `429`; a kill frees the place at once.
- K2 may also *accept* a start after a wait of up to 30 s (when a place frees during it), so the Studio's K2 timeout
  must be over 30 s (the spec uses 45 s), and starts run in the background loop, not in a browser request.
- A finished session answers `200 phase: finished`, not 404: treat `live: false` as "the place is free".
- Memory is tight: with two runs working, the pod was at ~3.8 GB of its 4 GiB limit, much of it the three idle
  Claude tabs (about 860 MB). Closing idle tabs, or raising the limit, gives real runs more room.
- The guest policy is still K2's default ("Prefer read-only work"). Real runs that publish need the Studio's text
  (step 3) before they ship.
