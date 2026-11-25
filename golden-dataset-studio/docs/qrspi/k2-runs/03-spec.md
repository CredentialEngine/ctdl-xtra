# S — Spec: Run Claude on K2 from the Studio ("agent runs")

Based on [`01-questions.md`](01-questions.md) and Eric's answers in its part C: use the **golden-rules** agent (it may
delegate to subagents), **one lock per catalog**, a UI that **leads with improving every rule at once**, and **anyone
can start a run** (Eric and Seth also get the prompt from the same button).
Branch: `golden-dataset-studio-k2` (off `golden-dataset-studio`; not for the main line yet).

## 1. What changes for the user

### Improve all rules, after labeling

Eric (2026-10-27): improving is one run over every rule, and it comes after labeling, so the UI should encourage doing
more labeling first.

- The Rules tab has a **fix bar at the bottom of the rule list** (after every rule) whenever any rule needs work (open
  *wrong* or *missing* verdicts, `Review.rule_status`):

  > **5 rules need work** · 23 wrong, 4 missing · 2 questions for the institution
  > **[ ✦ Improve all 5 rules with Claude ]**

  One click hands Claude every rule that needs work, with every open verdict, in one run (the existing "needs work"
  prompt). When nothing needs work, the bar says so: *Nothing to fix: no rule has open wrong or missing verdicts.*
- There is no per-rule run button and no run button in the top bar: one run improves every rule.
- **Generate rules** (catalog picker, catalog with no rules) runs on K2 the same way.
- **There is no Prompt tab** (Eric, 2026-10-27): the prompt is only ever the all-rules prompt, shown in a **modal**
  (Raw / Rendered, **Copy prompt**, **Download .md**). An old `#/c/<catalog>/prompt` link opens the Rules tab with the modal.
- Each Run asks once, with a gentle note: *"Generating updated rules based on your feedback takes a few minutes to
  run, so we recommend making a batch of several annotations before doing generation."*

### Who sees what

- **Everyone** can start a run, watch, cancel, and mark a run as ended. The run records who did each.
- **Eric Riddoch and Seth Alt** (a list in settings, `--prompt-users`) get every run button as a **split button**:
  the main part runs on K2, and its menu (▾) has **Run on K2** and **Open the prompt** (the prompt modal; the same
  scope, or the Generate rules prompt). They can run it from their own laptops instead.
- When runs are off (no K2 configured), every button falls back to opening the prompt, as today.

### When K2 can't be reached

If starting a run fails for any reason other than "the agent is busy" (K2 unreachable, a timeout, an error status, a
refused delivery such as `declined` or `no_agent_mode`), the Studio releases the lock and the button **takes the user
to the prompt** (the prompt modal, or the Generate rules prompt), with a warning admonition above it:

> ⚠ **We couldn't connect to the Remote AI rule generator** (*<short reason, e.g. "K2 didn't answer in 15 s">*).
> Copy this prompt and ask an engineer to run it in their own Claude Code.

The same fallback applies to a waiting run whose later send fails that way: it ends as `failed`, and its run bar
offers **Open the prompt** with the same admonition. "Remote AI rule generator" is the name users see; "K2" appears only
in links and technical details.

### Watching a run

- While a catalog has a run, every Studio showing that catalog has a **run bar** under the top bar:
  *"Claude is improving 5 rules · started by Eric Riddoch · 12 min · last update 40 s ago"* with **Watch** and
  **Cancel**. All run buttons for that catalog are disabled with that text as the reason.
- **Watch** opens a read-only panel: the agent's progress notes with times (*"Course description: the description
  lives in the second `<p>`, changing the locator"*), the rules it has touched, the state, and a link to the
  `golden-rules` agent in K2. When it ends: the outcome (*"Published ruleset v7: 4 rules changed, 1 left with a
  note"*) and a link to Compare v6 → v7.
- Reload, a closed laptop, or a second person opening the catalog all land on the same run bar: the run lives on the
  storage root.
- If the agent is busy with another catalog's run, the new run waits: *"Waiting for the golden-rules agent (busy with
  Los Rios) · queued 3 min"*.

## 2. How it works

```
Browser ─POST /api/catalogs/{c}/agent-runs {scope, author}─▶ any Studio
          1. lock: create agent-runs/{c}/current.json on the root (create-only)
          2. build the prompt (target "k2", with this run's id and how to report)
          3. POST K2 /v1/w/golden-rules/message {text, from: "Golden Rules Studio · <author>"}
               delivered → state "running"
               409 agent_busy → state "waiting"; retried on later polls until delivered or the deadline

golden-rules agent (Claude on K2, may delegate to subagents)
          golden-datasets run note  --run <id> "…"     ─▶ root: agent-runs/{c}/{id}/log.jsonl
          golden-datasets rules publish …              ─▶ root: new ruleset version
          golden-datasets run done  --run <id> --outcome "…" [--failed]

Browser ─GET /api/catalogs/{c}/agent-runs/current (every 3 s)─▶ any Studio
          reads current.json + log.jsonl; sends a waiting run; ends finished / timed-out runs
```

**Why reports go through the root, not K2:** K2's API can send to the golden-rules agent but can't read its progress
or tell when its turn ends (questions B2). The agent already writes to the root (that's how it publishes), every Studio
reads the root (laptops and deployed Studios alike), and it needs no network path back to a Studio. Subagents the agent
delegates to report with the same command and run id.

## 3. Storage

Under `golden-dataset-studio/agent-runs/` on the root:

| Path | What |
|---|---|
| `{catalog}/current.json` | **The lock.** Exists only while a run is waiting or running. Written with ETags |
| `{catalog}/{run_id}/run.json` | The run record, kept after the run |
| `{catalog}/{run_id}/log.jsonl` | One JSON line per note: `{at, kind: "note" \| "done" \| "studio", text, by}`. Appended by the agent's CLI and by the Studio (`sent`, `cancelled`, `timed_out`) |
| `{catalog}/{run_id}/prompt.md` | The exact text sent |

```json
{"run_id": "20261028T031209Z-a1b2", "catalog": "avc", "scope": {"kind": "needs_work", "rules": ["…", "…"]},
 "started_by": "Eric Riddoch", "created_at": "…", "sent_at": "…", "deadline": "created_at + 90 min",
 "state": "waiting | running | finished | failed | cancelled | timed_out",
 "k2": {"url": "…", "workspace": "golden-rules", "delivery_id": "m_…"},
 "ruleset_before": 6, "ruleset_after": null, "outcome": null, "ended_at": null}
```

`log.jsonl` is append-only from several writers (the agent and its subagents, Studios). On Azure, appends use an
append blob; on a local root, `O_APPEND` writes. Both keep concurrent lines whole. (`storage.py` gains
`append_line(path, text)`; nothing else changes there.)

## 4. The lock (per catalog)

- **Take:** `write_json("{c}/current.json", run, if_none_match=True)`. `ConflictError` → `409` with the current run;
  the UI shows the run bar.
- **Update:** every change to `current.json` is `if_match=etag`; on `ConflictError`, re-read and re-decide, so two
  Studios polling the same run never both act on it.
- **Release:** whoever ends the run writes `run.json` (final state), then deletes `current.json` (`if_match`).
- **Never stuck:** past `deadline` (default 90 min), the next Studio that looks ends it as `timed_out` and releases.
  A Studio that died between taking the lock and sending leaves a `waiting` run, which the next poll sends or times out.
- **Several catalogs at once:** allowed by the lock, serialized by the agent. A run that finds the agent busy waits
  (§2). If the agent delegates and ends its turn quickly, the next catalog's run goes through sooner.

## 5. When does a run end?

| Signal | State |
|---|---|
| Cancel pressed | `cancelled`. The Studio sends the agent *"Stop work on run <id> (<catalog>): cancelled by <name>."* (best effort; if busy, it can't be delivered, and the run is still released) |
| `golden-datasets run done --run <id>` | `finished`, or `failed` with `--failed`; its outcome is shown |
| Past `deadline` | `timed_out` |

The Studio can't see whether the agent is still working (questions B2), so the run bar shows **last update** (the
newest note's time) to make silence visible. Engineers can end a run by hand (**Mark as ended**) when the agent has
clearly stopped without saying so. `ruleset_after` is the catalog's latest ruleset version when the run ends.

## 6. CLI (new `golden-datasets run` group, for the agent)

```
golden-datasets run note --run <id> "<one line>"                 # progress, shown live in the Studio
golden-datasets run done --run <id> --outcome "<one line>" [--failed]
golden-datasets run show --run <id>                               # the run record and notes (for the agent, too)
```

They need only the root and the catalog (from the usual flags or `golden-datasets.env`). `done` refuses a run that
isn't current, so a late or duplicated `done` can't end someone else's run.

## 7. API (new router `routes_agent.py`)

| Route | |
|---|---|
| `GET /api/agent-runs/config` | `{enabled, k2_agent_url, prompt_users}`; the UI falls back to the prompt when off, and gives `prompt_users` the split button |
| `POST /api/catalogs/{c}/agent-runs` | `{scope: {kind: "needs_work" \| "first_rules"}, author}` (no one-rule runs: `422`) → `201` run; `409` with the blocking run; `502 {"fallback": "prompt", "reason": "…"}` if K2 can't be reached or refuses for a reason other than busy (lock released; the UI opens the prompt modal with the admonition). K2 calls time out after 15 s. Any profile may start |
| `GET /api/catalogs/{c}/agent-runs/current?since=<n>` | `{run, notes}` or `{run: null}`; advances the run (§2, §5) |
| `POST /api/catalogs/{c}/agent-runs/{id}/cancel` | `{author}` |
| `POST /api/catalogs/{c}/agent-runs/{id}/end` | `{author, outcome}` (Mark as ended) |
| `GET /api/catalogs/{c}/agent-runs?limit=` | Past runs, newest first |

K2 calls and the run state machine live in `agent_runs.py` (no FastAPI), so tests use a fake K2 and a local root.

## 8. The message sent to the agent

`build_prompt` / `build_first_rules_prompt` get `target="k2"`. The text starts with a header the agent can't miss:

```
# Golden Rules Studio run 20261028T031209Z-a1b2 · AVC · improve 5 rules
Started by Eric Riddoch from the Studio. You're working unattended; people are watching your notes in the Studio.
```

Compared with the `azure` prompt:
- **Setup:** no `az login`. Azure access is ready: the CLI reads SAS tokens from
  `/var/lib/k2/work/golden-datasets.env`; run it from this workspace. Install the CLI with `uv tool install` from the
  same ref as now.
- **Reporting** (new): *"Report progress with `golden-datasets run note --run <id> "…"` after each step: what you're
  checking, what you changed, what you published. If you delegate to subagents, give them the run id and this
  command. Finish with `golden-datasets run done --run <id> --outcome "…"` (add `--failed` if you couldn't publish),
  then stop. Don't ask questions; nobody will answer. If a rule can't be fixed, leave it and say why in a note."*
- Everything else (rules, open verdicts, values marked correct, limits, publish rule) is unchanged.

## 9. Configuration

| Setting | Where | Example |
|---|---|---|
| `--k2-url` / `GOLDEN_DATASETS_K2_URL` | serve flag / env | the K2 server's URL, e.g. `https://k2.example.org` |
| `GOLDEN_DATASETS_K2_KEY` | env / `golden-datasets.env`, never sent to the browser or written to the root | `k2sk_…` |
| `--k2-agent` | serve flag | `golden-rules` (the K2 workspace) |
| `--agent-run-minutes` | serve flag | `90` |
| `--prompt-users` / `GOLDEN_DATASETS_PROMPT_USERS` | serve flag / env | `Eric Riddoch,Seth Alt` (the default): profiles that also get **Open the prompt** |

No URL or key → runs are off; the Studio behaves as today (fix bar shows **Copy prompt** instead of Run).

K2 setup (once):
- key: `k2 api-key create --label studio --workspaces golden-rules --allow canonical-message`;
- golden-rules workspace settings: **Agent** on, and **Let agents on other servers message this agent** on
  (questions B1, B8);
- a deployed Studio: whatever network access its K2 server requires.

## 10. Failure cases

| Case | Behaviour |
|---|---|
| Two people press Run on the same catalog | One takes the lock; the other sees the run bar (`409`) |
| Runs on two catalogs | The second waits while the agent is busy, then is sent |
| The starter closes the laptop | Other Studios keep advancing the run; reopening shows it |
| Every Studio closed for an hour | The agent keeps working and writing notes to the root; the next Studio shows them all |
| K2 unreachable or erroring when Run is pressed | No run; the user lands on the prompt with the *Remote AI rule generator* admonition |
| K2 unreachable when a waiting run retries | The run ends `failed`; its run bar offers **Open the prompt** with the admonition |
| K2 unreachable while a run is running | Unaffected: notes come through the root, not K2 |
| Agent never runs `done` | *Last update* shows the silence; ends at the deadline, or by **Mark as ended** |
| Someone types into the golden-rules chat in K2 mid-run | Claude folds it into its turn; not prevented |
| Someone pastes the prompt into their own Claude meanwhile | Not prevented; publish refuses a version that isn't higher, so one of them fails cleanly |
| Claude subscription limit | The agent can't proceed; it reports with `--failed`, or the run times out |

## 11. Tests

- `agent_runs.py` with a fake K2 and a local root: lock race (two threads, one wins), waiting → running on retry,
  `done` / `--failed`, cancel, deadline, mark-as-ended, `done` for a stale run refused, concurrent `append_line`.
- `golden-datasets run` CLI tests.
- Route tests with FastAPI's client.
- Fallback: fake K2 down / 500 / `declined` / `no_agent_mode` → `502` with `fallback: "prompt"`, lock released; busy →
  waiting (not a fallback). Web: the prompt modal shows the admonition when opened as the fallback.
- Web: fix bar (counts, disabled when nothing to fix), run bar, Watch panel, disabled buttons while locked; the
  split button for a prompt user and the plain button for everyone else.
- End to end, by hand: laptop Studio on the Azure root → K2 → **Improve all** on a test catalog.

## 12. Order of work

1. K2: key with `canonical-message`; golden-rules **Agent** on and remote messages allowed; one manual message to
   check the agent can run `golden-datasets` from its workspace.
2. `storage.append_line`, `agent_runs.py`, `golden-datasets run` CLI + tests.
3. `routes_agent.py` + `target="k2"` prompts + tests.
4. UI: fix bar + top-bar button, run bar, Watch panel, Run on K2 / Generate rules / Only this rule; split button
   for prompt users.
5. Run locally against the Azure root and K2; one real Improve all.
6. Deployed Studio: its K2 settings.
