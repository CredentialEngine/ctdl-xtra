# API contract: one-rule runs (backend ↔ web), 2026-11-05

The exact JSON the web app gets from the server for [`03-spec.md`](03-spec.md) §1 and §7, and the shape of
`report.resolved.json`, which the CLI writes at `run done` and the server returns as a run's `report`. Examples use
AVC data (real course codes and annotations from the research; values for v10 are hypothetical).

## Changes

- 2026-11-05: first version.
- 2026-11-05: the web's requests (end of file): `last` in `current` is always the latest **ended** run, live runs or
  not (full record); each `recent` entry has `rule_name`; an ended run's `rule_names` also covers its `also_changed`
  ids. Added `GET …/rulesets/{v}/revert` (preview, `text` = the confirm) to §2.9.
- 2026-11-05: `GET /api/catalogs/{c}/prompt?rules=a,b` (§2.10): the prompt a new run on those rules would get, for
  "Open the prompt" on one rule.

- 2026-11-05 (pass 7, answers-pass6.md): a `ToDo` has `why`; each option has `label`, `button`, `do` (the
  per-course data to post: `mark`, `rule`, `words`, `event`, `count`, `courses[]` with `occurrence_key`,
  `page_stem` and `current`, the verdict to supersede), `done`, `then` (`publish[]` with `has_rule`, `run_again[]`,
  `text`), `effect` and `no_rule_yet`. Cards in a to-do have `lead`. A `set` has `others_lead`, and its `courses[]`
  have the same fields as `do.courses[]`. Authors are full names. `…/rows` also returns the courses that answers mark.
  Example: `web/src/agent/fixtures/b970-pass7.resolved.json` (the live run).

## Conventions

- Times are UTC ISO strings without fractions: `"2026-11-06T15:35:00Z"`. Durations are whole minutes (`*_min`).
- `catalog` in a path is the folder name or the short name (`avc`). Responses carry both: `catalog` (folder) and
  `catalog_short` (`avc`).
- Rule ids are the ruleset's (`course-credit-value`); every place that lists rule ids also gives
  `rule_names: {id: Studio name}` or a `name` beside the id, so the web never has to look names up.
- Hash links (`links.*`, `compare_url`) are relative to the Studio's address: `#/c/avc/...`. Prefix them with the
  Studio's own base when needed.
- No text the server or the CLI writes contains `·`.
- Errors are FastAPI's `{"detail": "..."}` unless a route says otherwise.

---

## 1. The run record

Every route that returns a run returns this object (`run.json` of an ended run; the live copy while it runs).

```json
{
  "run_id": "20261106T153500Z-4f2a",
  "catalog": "avc-elumenapp-com-catalog-2026-27-welcome",
  "catalog_short": "avc",
  "scope": {"kind": "rules", "rules": ["course-credit-value"], "added": []},
  "rule_names": {"course-credit-value": "Credit Value"},
  "started_by": "Jared Diener",
  "state": "waiting",
  "created_at": "2026-11-06T15:35:00Z",
  "updated_at": "2026-11-06T15:35:00Z",
  "sending_at": null,
  "sent_at": null,
  "deadline": null,
  "next_try_at": null,
  "k2": {"url": "https://k2.example", "agent": "golden-rules", "session_id": null},
  "annotations_as_of": null,
  "ruleset_before": 9,
  "ruleset_after": null,
  "rulesets_published": [],
  "also_changed": [],
  "outcome": null,
  "ended_at": null,
  "ended_by": null,
  "fallback_reason": null,
  "studio_url": "https://studio.example/",
  "to_do_count": null,
  "report_version": null
}
```

- `state`: `waiting` (in line for a place) → `sending` (the Studio is starting a K2 session) → `running` →
  `finished` | `needs_you` | `failed` | `cancelled` | `timed_out` | `ended`. A `sending` run can go back to `waiting`
  (K2 was full: 429). Live states: `waiting`, `sending`, `running`.
- `scope.kind`: `rules` (the rules to improve, "goal rules" internally), or `first_rules` (a catalog with no rules
  yet). Older runs have `needs_work` with the rules it covered in `scope.rules`; read them the same way.
- `deadline` is set when the run is sent (sent + the Studio's run minutes); a run waiting in line has none.
- `annotations_as_of`: when the run's prompt was built (its view of the annotations). Feedback after it is "new".
- `rulesets_published`: every ruleset version this run published, oldest first (usually one; a v10 → v12 sequence is
  possible). `ruleset_after` is the latest ruleset when the run ended.
- `also_changed`: rule ids the run changed that weren't rules to improve (from its report).
- `fallback_reason`: set when K2 refused the Studio (bad key, unknown workspace, unreachable). The UI offers the
  prompt, as today.
- `report_version`: `2` when the run left `report.resolved.json`; `null` for older runs (only `summary.md`).

## 2. Routes

### 2.1 `GET /api/agent-runs/config`

```json
{"enabled": true, "off_reason": null, "agent_name": "Remote AI rule generator", "k2_url": "https://k2.example",
 "agent": "golden-rules", "minutes": 90, "prompt_users": ["Eric Riddoch", "Seth Alt"], "cap": 2}
```

`cap` is new: how many runs work at once (all catalogs).

### 2.2 `POST /api/catalogs/{c}/agent-runs`

Request:

```json
{"scope": {"kind": "rules", "rules": ["course-credit-value", "course-subject-webpage"]},
 "author": "Jared Diener", "studio_url": "https://studio.example/"}
```

`{"kind": "first_rules"}` works as today. `{"kind": "needs_work"}` is still accepted and becomes a `rules` scope with
every rule that needs work.

Responses:
- **201** `{"run": <run record>, "queue": {"place": 1, "start_in_min": 0}}`. The run is always `waiting`: the
  Studio's background loop starts it within about 5 s when a place is free. `place` is 1-based across catalogs;
  `start_in_min` is the estimate of §2.8 (0 = a place is free now).
- **409** a rule is already being improved by a live run:
  `{"detail": "Credit Value is being improved in Seth Alt's run", "rule": "course-credit-value", "rule_name": "Credit Value", "run": <that run>}`.
  For `first_rules`: `{"detail": "a run is in progress on this catalog", "run": <run>}` (any live run blocks it, and it blocks every other run).
- **400** `{"detail": "Nothing to improve: none of these rules has open annotations or feedback since its last run"}`;
  also an unknown rule (`"no rule course-nope in ruleset v9"`) or an empty list.
- **503** runs are off: `{"detail": "runs are off: …", "fallback": "prompt", "reason": "…"}` (as today).

There is no 502 any more: K2 is called by the background loop, never in this request. A run K2 refused ends as
`failed` with `fallback_reason` set; the run bar offers the prompt then.

### 2.3 `GET /api/catalogs/{c}/agent-runs/current`

Polled every 3 s. Lists the catalog's live runs (each with its notes) and the queue.

```json
{
  "runs": [
    {"...run record...": "", "run_id": "20261106T153500Z-4f2a", "state": "running",
     "notes": [{"at": "2026-11-06T15:36:10Z", "kind": "studio", "text": "Started by Jared Diener", "by": "Golden Dataset Studio"},
               {"at": "2026-11-06T15:36:41Z", "kind": "note", "text": "Starting: reading the Credit Value annotations", "by": "golden-rules agent"}],
     "queue": {"place": null, "start_in_min": null, "left_min": 3, "minutes_so_far": 3}},
    {"...run record...": "", "run_id": "20261106T153900Z-91bc", "state": "waiting", "notes": [],
     "queue": {"place": 2, "start_in_min": 6, "left_min": null, "minutes_so_far": null}}
  ],
  "recent": {
    "course-subject-webpage": {"run_id": "20261105T200000Z-aa01", "state": "needs_you", "outcome": "1 decision before Claude can publish Subject Webpage",
                               "started_by": "Jared Diener", "created_at": "2026-11-05T20:00:00Z", "ended_at": "2026-11-05T20:07:00Z",
                               "to_do_count": 1, "annotations_as_of": "2026-11-05T20:00:40Z", "rule_name": "Subject Webpage"}
  },
  "slots": {"cap": 2,
            "live": [{"run": "20261106T153500Z-4f2a", "catalog": "avc", "session": "df01d0f9-571f-41c1-aa7b-a93e22903f85", "since": "2026-11-06T15:36:05Z"},
                     {"run": "20261106T152000Z-77de", "catalog": "marshall", "session": "7ab5f05d-1769-4402-9aaf-f0bd2c59528f", "since": "2026-11-06T15:20:30Z"}],
            "waiting": [{"run": "20261106T153900Z-91bc", "catalog": "avc", "since": "2026-11-06T15:39:00Z", "place": 2}]},
  "now": "2026-11-06T15:39:12Z",
  "run": null, "last": null, "notes": [], "since": 0
}
```

- `runs`: live runs of this catalog, oldest first. `queue.place`/`start_in_min` for `waiting` runs; `left_min` (about
  how long is left) and `minutes_so_far` for `sending`/`running` runs.
- `recent`: per rule, the latest **ended** run that had it as a rule to improve (for the sidebar's AI status and "?
  1"). Rules with no run are absent.
- `slots`: all catalogs. `live` = the places in use (`session` is null while starting); `waiting` = runs in line,
  oldest first, `place` 1-based.
- `last`: the latest run that **ended** (full run record), whether or not runs are live now; null before the first.
  The run bar shows its outcome.
- `run`, `notes`, `since`: the old shape (the first live run, and the notes of it or else of `last`), kept until the
  new web ships. Don't use them in new code.

### 2.4 `GET /api/catalogs/{c}/agent-runs/{run_id}`

```json
{"run": <run record>, "notes": [<note>, ...], "summary": "<summary.md, Markdown>" | null,
 "report": <report.resolved.json, §3> | null}
```

`report` is null for older runs and for runs that haven't ended; show `summary` as today then.

### 2.5 `GET /api/catalogs/{c}/agent-runs?rule=<id>&limit=20`

A list of run records, newest first, live runs included. With `rule`: only runs that had it as a rule to improve or
changed it (`also_changed`). Without: every run (as today).

### 2.6 `GET /api/catalogs/{c}/agent-runs/{run_id}/rows`

The report's rows, as they are **now** (refetch on open, window focus and visibility change).

```json
{
  "run_id": "20261106T153500Z-4f2a",
  "annotations_as_of": "2026-11-06T15:36:05Z",
  "rules_touched": ["course-credit-value", "course-credit-value-credit-unit-type"],
  "new_feedback": 2,
  "rows": [
    {"rule": "course-credit-value", "course": "ACCT199", "page_stem": "avc-elumenapp-com-catalog-2026-27-course-acct199",
     "key": "avc-elumenapp-com-catalog-2026-27-course-acct199@html > body", "occurrence_key": "avc-elumenapp-com-catalog-2026-27-course-acct199@html > body",
     "value": null, "status": "empty",
     "state": "correct",
     "verdict": {"annotation_id": "an-5d0c1e2f9a11", "type": "verdict", "verdict": "correct", "author": "Jared Diener",
                 "author_role": "sme", "at": "2026-11-07T17:04:00Z", "note": null, "expected": null,
                 "rule_version_seen": 3, "value_seen": null, "run_id": null, "ruleset_version": null, "run_at": null,
                 "after_run": true},
     "human_reviewed": true, "engineer_checked": false, "role": "sme", "human": {"...": "event brief"}, "checked": null,
     "history": [
       {"annotation_id": "an-718755f023ce", "type": "verdict", "verdict": "wrong", "author": "Jared Diener", "author_role": "sme",
        "at": "2026-11-04T16:20:00Z", "note": "There should be no values for this property. ceterms:creditValue takes the sub-class Value Profile.",
        "expected": null, "run_id": null, "ruleset_version": null, "run_at": null, "after_run": false},
       {"annotation_id": "an-c1a0de4b7f20", "type": "comment", "verdict": null, "author": "Claude", "author_role": "ai",
        "at": "2026-11-06T15:44:00Z", "note": "Empty is the value Jared's note asks for.",
        "run_id": "20261106T153500Z-4f2a", "ruleset_version": 10, "run_at": "2026-11-06T15:35:00Z", "after_run": false},
       {"annotation_id": "an-5d0c1e2f9a11", "type": "verdict", "verdict": "correct", "author": "Jared Diener", "author_role": "sme",
        "at": "2026-11-07T17:04:00Z", "note": null, "run_id": null, "ruleset_version": null, "run_at": null, "after_run": true}
     ]}
  ]
}
```

- One entry per (rule, course) the report shows (row cards anywhere in the report, including to-do evidence and
  sets). `value`/`status` are the course's value in the **latest** extraction (the row as the Rules tab shows it
  now).
- `verdict`, `state`, `human_reviewed`, `engineer_checked`, `role`, `human`, `checked`: exactly as the Rules tab's
  rows route gives them (`GET …/rules/{rule}/rows`), so `Controls` and the byline work unchanged.
- `history`: every live verdict and comment on the row, oldest first (what `HistoryLine` shows), with Claude's
  comments in place. `after_run: true` = made after `annotations_as_of` (render "…, after this run").
- An event brief has `run_id`, `ruleset_version` and `run_at` (the run's start, from its id) on Claude's comments;
  `null` on people's. Render Claude's as **Claude** (v10, AI run Nov 6), the run linked with `?run=<run_id>`.
- `new_feedback`: verdicts and comments by people (not `author_role: "ai"`) made after `annotations_as_of` on any
  row of the rules in `rules_touched` (the rules to improve plus `also_changed`). Show **Run again** when > 0.
- 404 when the run doesn't exist; `rows: []` when it has no resolved report.

The same three fields (`run_id`, `ruleset_version`, `run_at`) now appear on every event brief the server returns
(the Rules tab's rows, `match`, courses), so the Rules tab's history line can show Claude's comments the same way.

### 2.7 `GET /api/catalogs/{c}/rules/picker`

```json
{
  "rules": [
    {"rule": "course-credit-value", "name": "Credit Value", "kind": "property", "status": "needs work",
     "reviewed": 2, "total": 1062, "open": 1, "comments": 0, "new_since_run": 0,
     "ticked": true, "why": "1 open",
     "downstream": ["course-credit-value-credit-unit-type"], "downstream_names": ["Credit Unit Type"],
     "held_by": null, "last_run": null},
    {"rule": "course-subject-webpage", "name": "Subject Webpage", "kind": "property", "status": "needs work",
     "reviewed": 14, "total": 1062, "open": 1, "comments": 1, "new_since_run": 0,
     "ticked": false, "why": "Being improved in Jared Diener's run, 4 min",
     "downstream": [], "downstream_names": [],
     "held_by": {"run_id": "20261106T153500Z-4f2a", "started_by": "Jared Diener", "state": "running", "since": "2026-11-06T15:35:00Z", "minutes": 4},
     "last_run": {"run_id": "20261105T200000Z-aa01", "state": "needs_you", "ended_at": "2026-11-05T20:07:00Z"}},
    {"rule": "course-code", "name": "Coded Notation", "kind": "property", "status": "in review",
     "reviewed": 30, "total": 1062, "open": 0, "comments": 0, "new_since_run": 0,
     "ticked": false, "why": "nothing open", "downstream": [], "downstream_names": [], "held_by": null, "last_run": null}
  ],
  "total_rules": 44,
  "ticked": 6,
  "queue": {"cap": 2, "working": 1, "waiting": 0, "place": 1, "start_in_min": 0},
  "note": "1 of 2 AI runs is working, so this one starts now."
}
```

- Order: the sidebar's (page rules, locators, properties).
- `ticked` (default): open annotations > 0, or verdicts/comments on the rule newer than its last run (`new_since_run`).
  A rule held by a live run is never ticked; disable its checkbox and show `why`.
- `why`: the grey line: `"3 open, 4 comments"`, `"2 new since its last run"`, `"nothing open"`, or the held reason.
- `downstream`: the rules that read this one, directly or not (blast radius; information only).
- `note`: the dialog's `.run-note` line. Variants: `"No AI run is working, so this one starts now."`,
  `"1 of 2 AI runs is working, so this one starts now."`, `"2 AI runs are working. This one would be 1st in line, about 2 min."`.

### 2.8 `GET /api/agent-runs/queue`

```json
{
  "cap": 2,
  "working": [
    {"run": "20261106T152000Z-77de", "catalog": "marshall", "catalog_name": "Marshall", "rules": ["course-description"],
     "rule_names": ["Description"], "started_by": "Seth Alt", "since": "2026-11-06T15:20:30Z", "minutes_so_far": 4, "left_min": 2},
    {"run": "20261106T153500Z-4f2a", "catalog": "avc", "catalog_name": "AVC", "rules": ["course-credit-value"],
     "rule_names": ["Credit Value"], "started_by": "Jared Diener", "since": "2026-11-06T15:36:05Z", "minutes_so_far": 1, "left_min": 5}
  ],
  "waiting": [
    {"run": "20261106T153900Z-91bc", "catalog": "avc", "catalog_name": "AVC", "rules": ["course-description"],
     "rule_names": ["Description"], "started_by": "Eric Riddoch", "since": "2026-11-06T15:39:00Z", "place": 1, "start_in_min": 2},
    {"run": "20261106T154000Z-0c3e", "catalog": "ualr", "catalog_name": "UALR", "rules": ["course-prerequisite-description"],
     "rule_names": ["Prerequisite: Description"], "started_by": "Cadence Calixto", "since": "2026-11-06T15:40:00Z", "place": 2, "start_in_min": 5}
  ],
  "median_min": 6,
  "from_runs": 10,
  "note": "Estimates use the last 10 runs, which took 6 min each (median). Two runs work at a time."
}
```

The estimate (spec §1.7): *d* = median minutes of the last 10 ended runs (`sent_at` → `ended_at`), 6 when there are
none (`from_runs: 0`, note "Estimates assume 6 min per run until runs have ended. …"). A working run has
`max(1, d − minutes_so_far)` left. Waiting runs take the places as they free up, in order, each holding its place for
*d*. All values are whole minutes; show "about N min". A `sending` run counts as working.

### 2.9 `POST /api/catalogs/{c}/rulesets/{v}/revert`

Request: `{"author": "Jared Diener"}`. Anyone may call it; the UI asks first: "Revert v10? This publishes v11 with
Credit Value and Credit Unit Type back to how they were in v9."

- **200**
  ```json
  {"version": 11, "reverted": 10, "extraction": "rs-0011",
   "rules": [{"rule": "course-credit-value", "name": "Credit Value", "from_version": 3, "to_version": 2},
             {"rule": "course-credit-value-credit-unit-type", "name": "Credit Unit Type", "from_version": 3, "to_version": 2}],
   "suite": {"rules": 44, "golden": 244, "now_right": 0, "got_worse": 1,
             "line": "Whole suite: 44 rules, 244 golden values. 0 now right, 1 got worse."}}
  ```
  A revert is published even when values got worse (a person chose to go back); `suite` says what moved.
- **409** a later version changed one of the rules again: `{"detail": "Credit Unit Type was changed again in v11; revert v11 first, or change it by hand"}`;
  or another publish holds the catalog's publish lock for more than 60 s.
- **400** v1 (nothing before it) or a version that changed no rules; **404** an unknown version.

To build the confirm text before calling, `GET /api/catalogs/{c}/rulesets/{v}/revert` (same path, GET) returns
`{"version": 10, "next_version": 11, "rules": [...as above...], "parent": 9, "blocked": null | "<the 409 detail>",
"text": "Revert v10? This publishes v11 with Credit Value and Credit Unit Type back to how they were in v9."}` and
writes nothing.

### 2.10 `GET /api/catalogs/{c}/prompt?rules=course-credit-value,course-subject-webpage`

The prompt a new run on these rules would get (the rules to improve, their downstream rules, and the same limits),
in today's `PromptResponse` shape (`{text, chars, tokens, rules, annotations, scope, target, root, warning,
studio_root}`). It is the Azure version (as the existing `?rule=` route), so it lacks only the run's own header,
per-run install and report section, which exist once a run has an id; a sent run's exact text stays at
`…/agent-runs/{id}/prompt`. 404 for an unknown rule.

### 2.11 Unchanged

`POST …/agent-runs/{id}/cancel` and `…/end` (`{"author"}` → `{"run"}`), `GET …/agent-runs/{id}/prompt`,
`POST /api/catalogs/{c}/annotations` (the report's ✓ and comment use it; see §3.6 for what to send).

---

## 3. `report.resolved.json` (the run's `report`)

Written by `golden-datasets run done --report report.json` next to `report.json` and `summary.md`. Everything the
report shows is in it, already looked up by the CLI; the web lays it out (spec §1.4) and refetches only the rows'
verdicts and history (§2.6).

### 3.1 Top level

```json
{
  "version": 2,
  "run_id": "20261106T153500Z-4f2a",
  "catalog": "avc-elumenapp-com-catalog-2026-27-welcome",
  "catalog_short": "avc",
  "ending": "published",
  "outcome": "Claude published Credit Value in v10.",
  "reason": null,
  "ruleset": {"started_on": 9, "based_on": 9, "published": [10], "latest": 10, "ext": "rs-0010",
              "compare": {"a": 9, "b": 10, "url": "#/c/avc/compare?a=9&b=10"}},
  "facts": [
    {"label": "Rules to improve", "text": "Credit Value"},
    {"label": "Also changed", "text": "Credit Unit Type"},
    {"label": "Checked", "text": "All 44 rules against 244 golden values. Nothing that was right got worse."},
    {"label": "Ruleset", "text": "v9 to v10"}
  ],
  "suite": {"rules": 44, "golden": 244, "now_right": 1, "inferred": 1, "got_worse": 0},
  "inferred": [ <InferredItem> ],
  "to_do": [ <ToDo> ],
  "rules": [ <RuleSection> ],
  "also_changed": [ <RuleSection> ],
  "together": [ <Together> ],
  "notes": "Free text from Claude, at most 5 lines." | null,
  "links": {"report": "#/c/avc/rules?run=20261106T153500Z-4f2a", "compare": "#/c/avc/compare?a=9&b=10"},
  "revert": {"version": 10, "text": "Revert v10? This publishes v11 with Credit Value and Credit Unit Type back to how they were in v9."} | null
}
```

- `ending`: `published` | `needs_you` | `failed`. `outcome` is the band's sentence ("1 decision before Claude can
  publish Subject Webpage.", "Claude couldn't finish: the install failed."). Use `endedIcon` from `ending`.
- `ruleset.based_on` differs from `started_on` after a rebase or a redo; the CLI then writes the Ruleset fact as
  "Based on v11; started on v9." `ext`: the extraction to pin `&ext=` to (the run's last published version, else the
  one it started from).
- `facts`: render one `dl.run-facts` row each, in order, after the Studio's own Started / Ran rows. Empty ones are left
  out by the CLI.
- `revert`: null unless the run published; then the footer's **Revert vN** with this confirm text (it calls §2.9).
- Started, Ran, who started it: from the run record (§1).

### 3.2 A row card (`Row`)

The Rules tab's row, as it was when the run ended. Verdict, byline and history get replaced by `…/rows` (§2.6),
matched on `(rule, course)`.

```json
{
  "rule": "course-credit-value",
  "rule_name": "Credit Value",
  "legend": "Credit Value",
  "kind": "property",
  "course": "ACCT199",
  "title": "ACCT 199 - Work Experience Education",
  "page_stem": "avc-elumenapp-com-catalog-2026-27-course-acct199",
  "url": "https://avc.elumenapp.com/catalog/2026-27/course/acct199",
  "key": "avc-elumenapp-com-catalog-2026-27-course-acct199@html > body",
  "occurrence_key": "avc-elumenapp-com-catalog-2026-27-course-acct199@html > body",
  "value": null,
  "status": "empty",
  "value_before": {"version": 9, "value": "1.0 - 8.0 Units"},
  "inferred": {"value": "", "annotation": "an-718755f023ce", "saves": "correct"},
  "left_out": [],
  "comment": "Empty is the value Jared's note asks for.",
  "verdict": {"annotation_id": "an-718755f023ce", "type": "verdict", "verdict": "wrong", "author": "Jared Diener",
              "author_role": "sme", "at": "2026-11-04T16:20:00Z", "note": "There should be no values for this property. ceterms:creditValue takes the sub-class Value Profile.",
              "expected": null, "rule_version_seen": 2, "value_seen": "1.0 - 8.0 Units",
              "run_id": null, "ruleset_version": null, "run_at": null},
  "state": "still-wrong",
  "history": [ <HistoryItem>, ... ],
  "links": {"rules": "#/c/avc/rules/course-credit-value?row=ACCT199&by=anyone&ext=rs-0010",
            "wrong": "#/c/avc/rules/course-credit-value?row=ACCT199&by=anyone&ext=rs-0010&mark=wrong"}
}
```

- `value`/`status`: the course's value in `ruleset.ext` (the version the run published, else started from).
  `status` is the extraction's (`found`, `empty`, `no_match`, `none`, or a claim: `absent`); `value: null` with a
  claim status renders "Not on the page (rule's claim)" (`empty claim`), as in the Rules tab.
- `legend`: the `.valbox-k` text (the property label, the web upper-cases it).
- `value_before`: present only when the value differs from the started-on version's; render the history item "In
  v9: 1.0 - 8.0 Units" first.
- `inferred`: present when Claude worked out this course's value (§3.3). `saves`: `correct` = the run published the
  value, so ✓ posts an ordinary ✓ verdict on the current value; `expected` = it didn't, so ✓ posts a ✕ with
  `expected.text = inferred.value` and `supersedes = inferred.annotation`. The ✓ tooltip: "Correct (1): this is the
  right value. Saves it as ACCT199's expected Credit Value".
- `left_out`: page passages the value leaves out (render as `.sel-piece` / `.sel-pol` "✕ not in answer" /
  `.sel-quote.out`): `[{"text": "Advisory: Eligibility for ENGL 101.", "before": "Prerequisite: None.", "after": "Lecture 3 hours."}]`.
- `comment`: Claude's sentence about this row, if it wrote one (also saved in the log and in `history`).
- `links.rules` / `links.wrong`: **Open in Rules →** and ✕ (both `target="_blank"`). Build **Open in Records →**
  as the Rules tab does, from `course`, `occurrence_key` and `legend`.
- `verdict`, `state`, `history`: as of the run's end. The web replaces them with `…/rows`.

### 3.3 `HistoryItem`

The items of the row's history line, oldest first, one per line in the report (`stacked`).

```json
{"kind": "verdict", "annotation_id": "an-718755f023ce", "verdict": "wrong", "author": "Jared Diener", "author_role": "sme",
 "at": "2026-11-04T16:20:00Z", "note": "There should be no values for this property. ceterms:creditValue takes the sub-class Value Profile.",
 "run_id": null, "ruleset_version": null, "run_at": null, "after_run": false}

{"kind": "comment", "annotation_id": "an-c1a0de4b7f20", "verdict": null, "author": "Claude", "author_role": "ai",
 "at": "2026-11-06T15:44:00Z", "note": "Empty is the value Jared's note asks for.",
 "run_id": "20261106T153500Z-4f2a", "ruleset_version": 10, "run_at": "2026-11-06T15:35:00Z", "after_run": false}
```

Render Claude's as: **Claude** (v10, [AI run Nov 6](#/c/avc/rules?run=20261106T153500Z-4f2a)): Empty is the value
Jared's note asks for. `ruleset_version` = the version the run published (or started from); `run_at` gives the date.

### 3.4 `InferredItem` ("A value Claude worked out")

```json
{"rule": "course-in-catalog", "rule_name": "In Catalog", "course": "ACCT199",
 "value": "https://avc.elumenapp.com/catalog/2026-27/course/acct199",
 "published": false,
 "evidence": [{"quote": "https://avc.elumenapp.com/catalog/2026-27/course/acct199",
               "source": {"kind": "note", "annotation_id": "an-441bd81433b2", "author": "Jared Diener", "at": "2026-11-04T16:31:00Z",
                          "rule": "course-in-catalog", "course": "ACCT199"}}],
 "row": <Row with inferred set>}
```

The section shows `row` (its value box holds the inferred value when `published` is false) with the evidence quotes
as history items. First open, the rest folded.

### 3.5 `ToDo` ("What you need to decide")

```json
{
  "ask": "Should Subject Webpage be empty for every course in the catalog?",
  "open": true,
  "rule": "course-subject-webpage",
  "rule_name": "Subject Webpage",
  "about": [<Row: ACCT199 in Subject Webpage>],
  "evidence": [
    {"kind": "quote",
     "quote": "When the resource is in a catalog, use the property ceterms:inCatalog instead of ceterms:subjectWebpage.",
     "source": {"kind": "note", "annotation_id": "an-39127172c8e8", "author": "Jared Diener", "at": "2026-11-04T16:28:00Z",
                "rule": "course-subject-webpage", "course": "ACCT199"}},
    {"kind": "set", "label": "marked correct", "rule": "course-subject-webpage", "count": 13,
     "rows": [<Row: GEOG222>],
     "courses": [{"course": "KINF244", "title": "KINF 244 - …", "value": "https://avc.elumenapp.com/catalog/2026-27/course/kinf244", "verdict": "correct"},
                 {"course": "NS922L", "title": "NS 922L - …", "value": "…", "verdict": "correct"}],
     "link": "#/c/avc/rules/course-subject-webpage?by=anyone&verdict=correct"}
  ],
  "options": [
    {"answer": "yes", "text": "If yes, mark the 13 courses \"Not on the page\" for Subject Webpage. The next run publishes Subject Webpage and In Catalog together.",
     "link": "#/c/avc/rules/course-subject-webpage?by=anyone&verdict=correct"},
    {"answer": "no", "text": "If no, mark ACCT199 correct for Subject Webpage. The next run publishes In Catalog.",
     "link": "#/c/avc/rules/course-subject-webpage?row=ACCT199&by=anyone"}
  ],
  "effect": [{"rule": "course-subject-webpage", "rule_name": "Subject Webpage", "text": "Subject Webpage becomes empty."},
             {"rule": "course-in-catalog", "rule_name": "In Catalog", "text": "In Catalog reads the page's address."}]
}
```

- At most 3 have `open: true` (the first; the CLI sets it); the rest are folded.
- A `set` evidence: `rows` holds the first course as a full row card; `courses` holds the others ("The other 12" as
  `linkish` codes; hover `Tip` shows title, value and verdict); `count` = all of them.
- `options[].text` is the sentence to show ("If yes, …"). `link` opens the filtered list or the row.

### 3.6 `RuleSection` (goal rules, then `also_changed`)

```json
{"rule": "course-credit-value", "name": "Credit Value", "goal": true,
 "outcome": "published", "now": "empty on every course", "why": null,
 "because": null,
 "values_changed": {"count": 1062, "of": 1062, "base": 9, "published": 10,
                    "compare_url": "#/c/avc/compare?a=9&b=10&rule=course-credit-value",
                    "text": "1,062 of 1,062 courses"},
 "rows": [<Row ACCT199 with comment>]}

{"rule": "course-credit-value-credit-unit-type", "name": "Credit Unit Type", "goal": false,
 "outcome": "published", "now": null,
 "why": "It took its unit word from Credit Value; it now reads the same line on the page.",
 "because": {"reads": "course-credit-value", "name": "Credit Value"},
 "values_changed": {"count": 0, "of": 1062, "base": 9, "published": 10,
                    "compare_url": "#/c/avc/compare?a=9&b=10&rule=course-credit-value-credit-unit-type", "text": "0 of 1,062 courses"},
 "rows": [<Row ACCT199 in Credit Unit Type: "Units", ✓ by Jared>]}
```

- `outcome`: `published` | `held` | `not changed` | `failed` (Claude's; checked against the published ruleset).
- `values_changed`: counted by the CLI (draft extraction against the base version). Null when the rule wasn't
  published and no try changed it. Show "Values changed: 1,062 of 1,062 courses. Compare v9 and v10" with the link.
  When not published, `published` is null and `compare_url` is null (the count is from the last try).
- `because`: also-changed only: `{"reads": id, "name"}` or `{"read_by": id, "name"}`; null otherwise.
- `rows`: the row cards Claude commented on in this rule; for an also-changed rule with none, the courses whose value
  changed (up to 3), or else one golden value that held.

### 3.7 `Together`

```json
{"rules": ["course-subject-webpage", "course-in-catalog"], "names": ["Subject Webpage", "In Catalog"],
 "quote": "When the resource is in a catalog, use the property ceterms:inCatalog instead of ceterms:subjectWebpage.",
 "source": {"kind": "note", "annotation_id": "an-39127172c8e8", "author": "Jared Diener", "at": "2026-11-04T16:28:00Z",
            "rule": "course-subject-webpage", "course": "ACCT199"}}
```

### 3.8 `source` of a quote

`{"kind": "note", annotation_id, author, at, rule, course}` (a verdict's note or a comment; `course` null for a
comment on a whole rule or the ruleset), or `{"kind": "page", "course", "title", "before", "after"}` (a passage of the
course's saved page, with one line of context before and after), or `{"kind": "value", "rule", "course"}`.

---

## 4. Files on the storage root (for reference)

| Path | What |
|---|---|
| `<catalog>/golden-dataset-studio/agent-runs/live.json` | `{"runs": [<run record>, ...]}`: the catalog's live runs (replaces `current.json`); written with ETags. A rule to improve is claimed by being in a live run's `scope.rules` here |
| `<catalog>/golden-dataset-studio/agent-runs/goals.json` | `{rule: <brief of its latest run>}`: `recent` and the picker's "since its last run" |
| `<catalog>/golden-dataset-studio/agent-runs/<run>/` | `run.json` (once ended), `prompt.md`, `log.jsonl`, `report.json`, `report.resolved.json`, `summary.md`, `inferred.json`, `last-try.json`, `published.json` |
| `golden-dataset-studio/agent-slots.json` | `{"cap": 2, "live": [{run, catalog, session, since}], "kill": [session ids to kill]}` |
| `golden-dataset-studio/agent-runs-recent.json` | `{"runs": [{run, catalog, sent_at, ended_at, minutes}]}`: the last 10 ended runs |
| `<catalog>/golden-dataset-studio/publish.json` | the publish lock: `{"holder": {run, by, since} | null, "expires_at"}` |

---

## Web requests

Fields the web needs that the contract above lacks. The web handles each one's absence. **All three are done**
(2026-11-05, see Changes).

1. **Keep `last` in `GET …/agent-runs/current`** (§2.3), or add `last_ended: <run record>`. The run bar shows the
   latest ended run's outcome (with Compare and Read the report) for 24 h, and needs its full record
   (`ruleset_before`/`ruleset_after`, `also_changed`, `rule_names`, `report_version`). `recent` holds briefs per rule,
   which aren't enough. The web reads `last` today; without it the ended-run bar doesn't show.
2. **`rule_name` in each `recent` entry** (§2.3): the run bar's live text adds "Subject Webpage needs 1 decision from
   you." for a rule whose last run ended `needs_you` (spec §1.3, mockup 1a). Without it the sentence is left out (the
   sidebar's amber "? 1" still shows, since the sidebar has the names).
3. **`rule_names` should cover `also_changed` ids** in the run record (§1), so the run bar can say "It also changed
   Credit Unit Type." Without it the id is shown.
