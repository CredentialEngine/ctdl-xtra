
## Web (golden-dataset-studio/web), 2026-11-05

Built against [`05-api-contract.md`](05-api-contract.md) (first version). `npm run typecheck`, `npm test` and
`npm run build` pass: **246 tests** (215 before; 31 new). Seven existing assertions were updated because the spec
changes what they check: the run bar's text (no " · started by …", sentences instead), the fix bar's button label, and
one Rules tab selector (the sidebar row now has two `.rule-talk-btn` buttons, Improve and Discuss).

### What was built, file by file

- `rules/RowCard.tsx` (new): the Rules tab's row card, moved out of `RulesTab.tsx`: code, value box with its legend,
  course title, link buttons, strata chips, history line, ✓ ✕ comment controls. Without an `index` the card can't be
  selected or focused (the report). Options for the report: `stacked`, `lead` history items, `history` (items
  instead of the row's own), `below` (the left-out passages), `review={false}` (no human-reviewed line, which has
  " · "), and the ✓ / ✕ tooltips.
- `rules/RulesTab.tsx`: renders its rows with `RowCard` (same markup and classes as before; the Rules tab tests pass
  unchanged). Reads `&mark=wrong`: once the linked row loads, its ✕ expansion opens, then the parameter is dropped
  from the address. Passes ✦ Improve (not on an older ruleset, `?ext=`) and the AI status to the rule list.
- `rules/parts.tsx`: `HistoryLine` gets `stacked` (no " · ", one item per line; `.hist.stacked` in `rules.css`),
  `lead` and `items`, and renders Claude's comments as **Claude** (v10, [AI run Nov 6](?run=…)): …, in the Rules tab
  too. `Controls` gets `okTitle`, `wrongTitle` and `stacked`.
- `rules/logic.ts`: `historyItems` renders Claude's comments (`author_role: "ai"`, `run_id`, `ruleset_version`,
  `run_at`) with their run; new `reportHistory()` turns a report row's `history` events into history items, with
  "Jared Diener marked it correct, 10:04 AM, after this run." for `after_run` verdicts and "… 10:06 AM, after this
  run." on later comments. `monthDay`, `clockTime`.
- `rules/RuleList.tsx`: `onImprove` (✦ Improve, a `rule-talk-btn` like Discuss, inside the app's `Tip`, shown only on
  the hovered, focused or selected row: `.rule-improve` in `rules.css`) and `aiStat` (one more `.stat` counter).
- `agent/api.ts`: the contract's types (run record additions, `current`'s `runs`/`recent`/`slots`, queue, picker,
  `report.resolved.json`, `…/rows`), `agentApi2` (queue, picker, detail with `report`, rows, a rule's runs, revert,
  start with `{kind: "rules"}` and the 409 `{rule, rule_name}`), `waitingWords`, `ordinal`, `ruleNames`, `andNames`;
  `endedWords` names the rules ("Claude published Credit Value in ruleset v10", "Claude needs 1 decision before it can
  publish Description"); `openRuns(run?, rule?)`.
- `agent/state.tsx`: the poll keeps `runs` (every live run, each with notes and queue place), `recent`, `slots`; an
  older server's single `run` becomes a one-item `runs`.
- `agent/RunDialog.tsx` (new): "Run with Claude?" with the picker (mockup 1c): each rule as its `.rule-item` with a
  checkbox, "Need work" then "Nothing open", held rules disabled with the server's reason, the server's `note` in
  `.run-note`, **✦ Run on N rules**. `openRunDialog(rules?)` opens it from anywhere (`RunDialogHost` in `App.tsx`);
  with runs off it opens the prompt, as today. Without the picker route it falls back to `/rules` (ticked = open
  wrong or missing).
- `agent/FixBar.tsx`, `agent/RunButton.tsx`: the button is **Improve rules with AI…** and opens the picker
  (`RunButton`'s new `onAsk`; a live run no longer disables it, since runs queue). The prompt users' split menu
  stays. `first_rules` keeps the old confirm.
- `agent/AiStat.tsx` (new): the sidebar counter: pulsing dot and minutes for a working run, "◷ 2nd" for a run in line
  (tooltip "Waiting for a free place: 2nd in line, about 6 min"), amber "? 1" when the last run needs decisions.
  Click: the rule's AI runs, or that report.
- `agent/RunBar.tsx`: sentences, no " · ": "Claude is working on Credit Value. Your run on Description is 2nd in line.
  It should start in about 6 min." Who started it and the last update moved to the text's tooltip. Buttons: Watch,
  **See the queue**, Mark as ended, Cancel (your run in line first). Ended: "Claude published Credit Value in ruleset
  v10. It also changed Credit Unit Type. 2 rows have new feedback since." The Watch panel shows the resolved report
  when the run has one, else `summary.md` as before.
- `agent/Report.tsx` (new): the report from `report.resolved.json` (mockups 2, 3, 5, 7): outcome band and Compare,
  facts (`dl.run-facts`), values Claude worked out (first open, the rest folded), what you need to decide (open as the
  CLI says, never more than 3), a section per rule to improve and per "Also changed" rule with **Values changed** and
  its Compare link, Claude's notes and progress notes folded, and the footer: Past AI runs, the new-feedback line,
  **Revert vN** (confirm with the CLI's text), **View the prompt**, **✦ Run again** (only when `new_feedback` > 0;
  opens the picker with the run's rules ticked). Row cards: ✓ posts a ✓, or for an inferred value with
  `saves: "expected"` a ✕ with `expected.text` and `supersedes` (spec §2.4); comments post on the row; ✕ and **Open in
  Rules →** open a new tab pinned with `ext` (the row's `links`, else built from `ruleset.ext`). The rows are refetched
  on open, window focus and `visibilitychange`.
- `agent/RunsPanel.tsx`: "Working now: 2 of 2 places" and "Waiting" above the past runs when the queue has runs
  (mockup 8), with the server's estimate note; a rule filter ("AI runs on Subject Webpage", with **✦ Improve Subject
  Webpage** and "Every AI run on this catalog"); a run's resolved report, or `summary.md` for older runs; meta lines
  without " · ".
- `App.tsx`: `RunDialogHost`; the runs panel takes a rule.
- `tour/steps.tsx`, `rules/logic.ts` (approve hint): "Improve rules with AI…" instead of "Improve all rules".
- CSS (only where nothing existed): `.hist.stacked`, `.rule-improve` visibility, the clickable `.stat`, the picker row
  layout (`.run-pick`, `.run-pick-list`), row cards inside `.runs-sec`, the left-out passages, the report footer's
  right side, the queue rows (`div.runs-item`).

### Tests (new)

- `agent/report.test.tsx` (16): band, facts, rule sections with Values changed and Compare, row cards; stacked
  history (In v9, the note, Claude with its run link, "after this run"); first inferred open and the rest folded;
  at most 3 to-dos open; the set's course codes with the `Tip`; no `·` in the rendered report; ✓ on an inferred value
  for both cases (spec §2.4); a comment from the report; Open in Rules and ✕ in a new tab with `ext` and
  `mark=wrong` (from `links`, and built when absent); refetch on open, focus and visibility; Run again only with new
  feedback, through the dialog; the revert confirm; no Revert when nothing was published; View the prompt; the runs
  panel with a resolved report and with an older `summary.md`.
- `agent/picker.test.tsx` (12): the picker's defaults, a held rule disabled, the start request, the asked-for rule
  ticked, the `/rules` fallback, `openRunDialog`; ✦ Improve (class, `Tip` text, opens the picker); the sidebar's
  working, waiting and "? 1" counters; the queue's wording, run bar and runs panel; no "goal" in any UI string (scans
  every non-test source file's strings and JSX text).
- `rules/RulesTab.test.tsx` (+3): `&mark=wrong` opens ✕, none without it, Claude's comment in the Rules tab's history.

### Deviations from the spec or mockups

- **Facts order:** the contract puts the CLI's facts after Started / Ran; the mockups put "Rules to improve", "Also
  changed" and "Checked" first and "Ruleset" last. The web follows the mockups.
- **Sentences the Studio writes:** "Jared Diener marked ACCT199 wrong and said why:" before a to-do's row (mockup 3),
  "Eric Riddoch marked BIOL110 wrong without selecting the right text. Claude worked out the value below from the
  notes and the page." for an inferred value (mockup 5), "3 courses marked correct, like GEOG222:" before a set. They
  come from the row's verdict, not from Claude. A to-do quote whose note is already on a shown row card isn't
  repeated. A to-do's `effect` and the options' `link` aren't shown (the mockups don't show them); `together` isn't
  rendered.
- **✦ Improve on a sidebar row opens the picker with that one rule ticked**, instead of starting at once: a person
  confirms every start (as Run again, pass 6), and the dialog shows the queue line.
- **A rule's AI runs** (§1.5): reached from the sidebar's AI counter. Not built: "Open the prompt" for a new run on that
  rule (needs a per-rule prompt route) and the entry in the rule header's ⋯ menu.
- The fix bar's "Nothing to fix" state is unchanged (no picker button there). The fix bar's own count line keeps
  its " · " (existing text; P5: no change to the Rules tab).
- The dialog's note line is the server's `picker.note`; the web doesn't estimate on its own.
- The Watch panel's "Runs on" fact says "(open K2)" in parentheses instead of after " · ".

### Fields the contract lacked

Written under "Web requests" in `05-api-contract.md`: keep `last` in `current` (the ended-run bar needs the full
record), `rule_name` in `recent` entries (the run bar's "needs 1 decision from you" sentence), and `rule_names`
covering `also_changed`. Each is handled when absent.

## Backend (golden-dataset-studio/src), 2026-11-05

Built to [`03-spec.md`](03-spec.md) §2–§7 and [`05-api-contract.md`](05-api-contract.md), with the live K2 results at
the end of [`k2-transcript.md`](k2-transcript.md). `uv run pytest -q`: **206 passed** (38 tests new or rewritten).
`uv run ruff check src tests bench`: clean. The slow suite (`-m slow`, local mirror present): **10 failed, 11 passed,
13 skipped**. The same 10 fail on an untouched export of `HEAD`: the mirror's v1 build imports no annotations
(0 reviewed, 0 golden values), and some prompt assertions were already out of date. So the failures come from the
data, not this work. The slow assertions about text this work changed were updated anyway.

### What was built, file by file

- `suite.py` (new): the whole golden suite (§3.3). Golden values = latest ✓ (`value_seen`), ✕ with an expected value,
  and inferred values. A regression is a golden value that matched before and doesn't now, or fewer matches for a
  rule. Also counts values changed per rule (changed, new, gone). It prints the first line ("Whole suite: 44 rules,
  244 golden values. 1 now right (1 inferred), 0 got worse."), then a "Changed:" line and detail only where
  something moved. It also writes the report's Checked fact.
- `loop.py`: `rule try` and `rule publish` rerun **every** rule (`extract.compute` without a parent) and run the
  suite. A publish refuses on any regression (`--force` still overrides). `inferred.json` is read (default
  `./inferred.json`, or `--inferred`); each item must answer a live ✕ without an expected value. `last-try.json` v2
  keeps the suite, values changed per rule, the inferred values and what the draft produces for them. `rule publish`
  takes the publish lock, then rebases or refuses. In a run it records `run_id` and `started_by` in the ruleset,
  appends to `published.json`, and writes progress notes ("Publishing: waiting for …", "Rebased on v11 (…)",
  "Redoing on v11: …"). New: `rule downstream`, `ruleset revert`. The rule try cards no longer use `·`.
- `publishing.py` (new): the publish lock `<catalog>/golden-dataset-studio/publish.json` (ETag, 10 min expiry,
  released by writing `holder: null`, "waiting for run … to finish publishing (12 s)"). Rebase or refuse: *mine*
  is the draft's rules that differ from its `base_ruleset`; *theirs* is every version's `changed_rules` since. On a
  rebase only *mine* go on top, so a draft never overwrites another run's change to a rule it merely contains. Also
  `revert_plan` / `revert` / `revert_text`, and `downstream`.
- `report.py` (rewritten, report v2): references and quotes are checked (`check`): `…` joins ordered pieces, and
  curly quotes and dashes are made plain. `rules` must cover each rule to improve, with outcomes checked against
  what the run published. `also_changed` must equal exactly the other rules this run's versions changed. Inferred
  values must equal the published value, or the last try's. `resolve` writes `report.resolved.json` as the contract
  gives it: row cards with `value_before`, `inferred.saves`, history with Claude's comment, and `links` pinned with
  `ext`; also facts, `values_changed`, to-dos with sets and option sentences, `together`, and the revert text.
  `markdown` writes `summary.md`. Page passages and context use the page body, one line per block.
- `agent_runs.py` (rewritten):
  - Runs live in `agent-runs/live.json` (ETag) instead of the single-run `current.json`. Claiming a rule to improve
    is done in that same write. `goals.json` keeps each rule's latest run.
  - The K2 host-sessions client: `spawn` (429 → `K2Full`; timeout or dropped connection → `K2Lost`, never resent;
    401/404/refused → `K2Unavailable`), `session` (404 → over; `live: false` also means over), `kill`. The timeout is
    45 s.
  - `Queue`: the slots file `golden-dataset-studio/agent-slots.json` (ETag; `kill` holds sessions to kill later),
    `agent-runs-recent.json`, the estimate, the `tick()` background loop and its 5 s `loop()`.
  - A lost start fails after 2 min unless Claude's note names its session. A gone session gets 2 min of grace, then
    "Claude stopped without finishing". The Studio kills at the deadline and when a run ends.
  - `run note` records `$K2_SESSION_ID`. A session that turns up after its run ended is queued for a kill.
  - `run done --report` appends Claude's row comments (`author: "Claude"`, `author_role: "ai"`, `run_id`,
    `ruleset_version`) only after the report passes.
  - `run context`.
- `prompt.py`: `build_prompt(ctx, rules=[…])`. It covers the goal and surgical edits, the whole-suite publish rule,
  inferred values, rebase/redo, `also_changed`, a "Read by" row per rule, and the rule's last run (k2). The run
  section has the report v2 references, fields and a short example; row comments ("don't tell people what to
  press"); plain writing (no `·`); and "don't use `k2 respond`". For k2, the run installs its own CLI
  (`UV_TOOL_DIR=<run>/.tools UV_TOOL_BIN_DIR=<run>/bin`) and every command is `./bin/golden-datasets`.
- `log.py`: `author_role` may be `ai`. `routes_review._event_brief`: `run_id`, `ruleset_version`, `run_at` (read
  from the run id).
- `server/routes_agent.py` (rewritten): every route in contract §2. It is registered before `routes_review`, so
  `rules/picker` isn't read as a rule id. `server/routes_prompt.py`: `?rules=a,b`. `server/state.py`:
  `Studio.queue`, `agent_runs()`, `agent_cap`. `server/app.py`: `serve` starts the queue loop thread. `cli.py`:
  `--k2-max-runs`, `--inferred`, `rule downstream`, `ruleset revert`, `run context`.

### Deviations from the spec, and why

- **Goal claims live in `live.json`, not `agent-runs/goals/<rule>.json`.** One ETag write claims a whole set of rules
  atomically; per-rule files can't do that. `goals.json` (one file) is the "latest run per rule" index.
- **The prompt is built when the run is sent**, not when it is queued, so `annotations_as_of` is what Claude read.
  Until then a waiting run has no `prompt.md`.
- **No 502 fallback from POST.** K2 is only called from the loop. A run K2 refuses ends as `failed` with
  `fallback_reason`.
- **400 rule:** a set is refused when none of its rules has open annotations *or* feedback since its last run. This
  is the picker's own default, so **Run again** works after a ✓ or a comment.
- **Revert publishes even when golden values got worse** (a person chose to go back). It runs the suite, and the
  response and CLI say what moved. It refuses only when a later version changed one of the rules again. That
  includes a later revert of the same version.
- **A first-rules run** doesn't have to list every rule under `also_changed`.
- **A 429 blocks the line**: the front run waits 20 s, and the runs behind it don't jump ahead.
- `·` was removed from everything this work writes (reports, suite, publish/revert, run commands, rule try cards).
  Older CLI text (the `rule list` header, scores) still has it.
- Old reports (v1 `report.json`) aren't re-checked; their `summary.md` is shown as before.

### For the end-to-end test

- Serve on the **Azure root** (runs are off on a local root), with
  `GOLDEN_DATASETS_K2_URL=<K2 url>` (or `--k2-url`), `GOLDEN_DATASETS_K2_KEY=<key>`, workspace `--k2-agent
  golden-rules` (default), and `--k2-max-runs 2` (or `GOLDEN_DATASETS_K2_MAX_RUNS`, default 2, the same as K2's
  `host_session_cell_cap`). `--agent-run-minutes` (default 90) sets each session's deadline and `timeoutSecs`.
- The key needs `host-sessions` (the earlier key had only `canonical-message`). The workspace's guest policy is still
  K2's default ("prefer read-only work"); real publishing runs need the Studio's text (k2-transcript step 3).
- The run installs the CLI from the branch on GitHub (`GOLDEN_DATASETS_GIT_REF`, else the checkout's branch). Push
  this branch before a real run.
- With the loop running, a POST returns `waiting`, and the run starts within about 5 s.

### Left undone

- K2 never got a real call: the client and the loop were tested against a fake K2 and a local HTTP server only.
- Golden values cover property rules' row verdicts. List items' verdicts (`target.item`) and page/locator verdicts
  aren't in the suite (the existing scorecard skips them too).
- A run that publishes twice (v10 then v12) reports `values_changed` from the last publish that changed each rule.
