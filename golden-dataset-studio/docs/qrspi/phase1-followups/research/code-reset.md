# Research: bulk reset of approvals for a catalog (QRSPI R, facts only)

Feature under research: "a button to invalidate or reset all approved properties in bulk for a catalog — for when we
decide the value for a property should actually be different after we've approved a bunch of examples."

All paths are relative to `golden-dataset-studio/`. "Unverified" marks anything inferred rather than read or run.

---

## 1. Data model: what "approved" means

There are two separate kinds of approval, plus derived states. Each one comes from a single store: the append-only
annotation log.

### 1.1 The single source of truth: `annotations.jsonl`

- Path: `<root>/<catalog>/golden-dataset-studio/annotations.jsonl` (`src/golden_datasets/layout.py:4,29-30`). There is
  **one log per catalog**, shared by every crawl and every ruleset version of that catalog.
- Format: JSONL, one event per line, **append-only**. "People only ever append to it; nothing in it is edited. An edit
  is a new event whose `supersedes` names the old one." (`log.py:1-8`). Storage enforces this: the module docstring says
  "the annotation log is append-only and is read incrementally from a byte offset (`append`, `read_from`)"
  (`storage.py:11`). `Root.append` (`storage.py:129-131`) is the only write path for the log. The spec says the same:
  `annotations.jsonl … UI, import-v2 | append-only` (`docs/qrspi/03-spec.md:263`).
- Readers keep a byte offset and read only what was appended since (`log.py:85-97`, `AnnotationLog.refresh`). Truncating
  or rewriting the file would break that offset bookkeeping (unverified: inferred from the code, not tested). `sync`
  refuses logs that have diverged: "the two logs have diverged; merge them by hand (they are append-only JSONL)"
  (`sync.py:53-65`).
- Event types: `verdict`, `comment`, `approve`, `reopen` (`log.py:18`). Verdicts: `correct`, `wrong`, `missing`,
  `question` (`log.py:19`). Target kinds: `match`, `occurrence`, `page`, `rule`, `ruleset` (`log.py:20`). Optional
  fields: `author_role` (`sme`|`engineer`), `reasons` (`not_on_page`), `expected.segments[].polarity` (`in`|`out`),
  `anchor`, `compared_with`, `topic` (`log.py:21-28, 39-72`).
- `append_many` writes several events in one append (`log.py:112-117`). Its only caller is the v2 import
  (`import_v2.py:452-456`).
- The server fills each event's target from the current extraction: `rule_version_seen`, `extraction_seen`,
  `course_key`, `page_stem`, `value_index`, `value_seen` (`server/routes_review.py:659-701`). Ids are `ap-…` for
  approve/reopen and `an-…` for everything else (`routes_review.py:703`).

### 1.2 Kind A: rule approval ("Approve rule" / "Reopen")

- Stored as an `approve` or `reopen` event with `target.kind == "rule"`, `rule_id`, and `rule_version_seen`
  (`routes_review.py:667, 703`; the frontend sends it from `web/src/rules/RulesTab.tsx:514-532`).
- Status is derived (`review.py:538-575`, `Review.rule_status` / `_rule_status`):
  - `approved` when the latest live `approve`/`reopen` **for the rule's current version** is `approve`
    (`review.py:553-557, 565-566`);
  - otherwise `needs work` when there are open wrong or missing rows, wrong list items, or missing items
    (`review.py:560-563, 567-568`; `OPEN = {"wrong","still-wrong","missing"}` at `review.py:40`);
  - otherwise `in review` (`review.py:569-570`).
  - It also returns `reviewed`, `total`, `open_wrong`, `open_missing`, `questions`, `approved_by`, and `approved_at`
    (`review.py:572-575`).
- Spec: "`approved` when the latest `approve` / `reopen` for that rule version is `approve`", and "A new version starts
  at `in review`. Its old verdicts carry forward through the comparison." (`docs/qrspi/03-spec.md:332-337`).
- The server refuses `approve` with 409 while there are open wrong or missing rows (`routes_review.py:720-723`).
- `approved_count` (`routes_review.py:106-114`) counts approved rules for the home-page catalog list
  (`routes_review.py:143-144`).

### 1.3 Kind B: per-value verdicts (✓ / ✕ / missing / question) and "human-reviewed"

- Stored as `verdict` events on `match` (property rule), `occurrence` (record locator) or `page` (page rule) targets.
  List items carry `target.item` plus `value_index` and `value_seen` (`routes_review.py:670-696`).
- A row's state is computed when the log is read, never stored (`review.py:1-24`, `RowState` at `review.py:271-288`).
  States: `correct | wrong | fixed | still-wrong | changed-since-correct | question | missing` (`review.py:273`).
- **Human-reviewed** means an SME's verdict that is `correct` (and the value is unchanged since), or `wrong` with
  expected text that the value now equals (`fixed`): `HUMAN_STATES = ("correct","fixed")` (`review.py:41-43`), set at
  `review.py:476-479`.
- **Engineer-checked** means an engineer's ✓ waiting for an expert (`review.py:285-288`). An engineer's later verdict
  never supersedes an expert's (`review.py:308-311`; docstring `review.py:20-23`).
- List items have their own `ItemState` with `human` (`review.py:291-296, 376-397`).
- The **reviewer's answer** is a ✕ with expected segments, a ✕ with reason `not_on_page`, or a ✓ on "nothing found".
  Each is published as `approval: human` in place of the rule's value (`golden_answers.py:1-17, 79-137, 147-155`).
  Spec: `docs/qrspi/sme-fixes/03-spec.md` §6 (line 112ff) and §7 (line 130ff).

### 1.4 Values in the published files

- Each golden field carries `approval` (`human` or `rule`), `approved_by`, and `approved_at` (`golden.py:27-30`). A
  record's approval is `human`, `rule`, or `mixed` (`golden.py:69-72`). `human` comes from an expert verdict;
  otherwise the rule's approval supplies it (`golden_answers.py:70-71, 119`; `golden.py:170`).
- The same three columns are in `lineage.parquet` and `golden.parquet` (`model.py` schemas `LINEAGE` / `GOLDEN`,
  around `model.py:96-110`).

### 1.5 "In review" and the other statuses on the home page

- The home table's column status comes from `scores.column_statuses` (`scores.py:940-984`). It is `published` when
  the property is in the latest golden publication's `properties`, else `needs work`, else `in review`
  (`scores.py:975-979`).
- Counts are `human` and `rule` (values in the latest golden dataset as `golden.plan` writes them now) and `found` (the
  values its rule found) (`scores.py:992-1006`). The fraction "H / N" is "values an expert reviewed, of values the rule
  found" (`web/src/catalogs/CatalogPicker.tsx:5-6, 43-51`).

### 1.6 Rule and ruleset versions (what an approval points at)

- Rule versions are at `<catalog>/golden-dataset-studio/rules/<rule_id>/vNNNN.json`, ruleset versions at
  `rulesets/vNNNN.json` (`layout.py:21-26`). A rule's version changes only when the hash of its `definition` changes.
  Edits to the prose alone reuse the version (`rulesets.py:44-76`). Spec: "`content_hash` … decides the version number
  and what an approval refers to … Hashing the dependencies too … re-versioned rules nobody touched and lost their
  approvals" (`docs/qrspi/03-spec.md:297-300`).

---

## 2. Scope, carry-forward, and existing undo paths

### 2.1 Keys

| What | Keyed by | Where |
|---|---|---|
| Log | catalog (one file for all crawls and versions) | `layout.py:29-30` |
| Rule approval | `(rule_id, rule_version_seen)` | `review.py:555-556`; `routes_review.py:112-114` |
| Value verdict | `(rule_id, occurrence_key)` for match/occurrence, `(rule_id, page_stem)` for page; re-attached by `(course_key, page_stem)` when the occurrence key changed | `review.py:322-326, 434-439, 462-465` |
| List item verdict | `(rule_id, course_key or occurrence_key, page_stem)` plus normalized `value_seen` | `review.py:367-374, 381-382` |
| Human-reviewed counts (home sort) | `(catalog, rule_id, course/occurrence, page, item)`, across every catalog | `review.py:853-888` |

Verdicts are not filtered by crawl or ruleset version: `verdicts_for` filters by `rule_id` only (`review.py:342-365`).
Every event carries `crawl` and `extraction_seen` (`routes_review.py:668, 705`). The "Annotated in" facet groups them
by the ruleset version they were made in (`review.py:641-646`).

### 2.2 What happens to existing approvals when a rule changes

- **Rule approval:** it is tied to the version. When the definition changes, the rule gets a new version, so the old
  `approve` no longer matches and the rule shows `in review` (or `needs work`) (`review.py:555-556`;
  `docs/qrspi/03-spec.md:337`). The approval is not carried forward. It stays in the log under the old version.
- **Value verdicts carry forward** (`review.py:501-515`, `_carry`; docstring `review.py:12-16`):
  - The verdict applies as given when it was seen on this rule version, or when the value is unchanged.
  - When the value changed, `wrong` becomes `fixed` if the value now equals the expected text, else `still-wrong`.
  - When the value changed, `correct` becomes `changed-since-correct`. That state is not in `HUMAN_STATES`, so the value
    stops being human-reviewed (`review.py:478`), and it is not open, so it doesn't block approval.
  - With a parent extraction, rows get history signals: `previously-wrong`, `previously-correct`,
    `changed-since-correct`, and `new-in-version` (`review.py:489-497`). The Rules tab moves `previously-wrong`,
    `changed-since-correct`, and `new-in-version` up the list (`review.py:580`).
- **If the rule doesn't change but the expected answer does** (the scenario in this feature), nothing in the code
  invalidates existing ✓s. They stay `correct` and human-reviewed as long as the extracted value stays the same.
- **Publishing a changed rule is guarded by the existing ✓s.** `rule publish` refuses when any value marked correct
  would change, unless `--force` is passed (`loop.py:566-570`). A forced publish records `{"forced": true,
  "newly_wrong": n}` on the ruleset (`loop.py:575-576`). The prompt for Claude says "Publish only when nothing marked
  correct changes … Never use `--force`." (`prompt.py:341-342`). Inference (unverified): after a policy change, the
  old ✓s stop Claude's "Improve all rules" run from publishing the new behaviour.

### 2.3 Existing undo, reopen, and clear paths (searched widely)

Search over `src/` and `web/src/` for `reopen|unapprove|undo|retract|invalidat|reset|withdraw|revoke`:

- **`reopen` event:** this is the only "unapprove". It covers one rule at a time.
  - In the UI, the Rules tab header shows "Approved by X · date · **Reopen**", a link button titled "Undo the approval (a
    reopen event)" (`web/src/rules/RuleHead.tsx:80-85`). It calls `approve("reopen")`, which posts `{type:"reopen",
    target:{kind:"rule",rule_id}, note:"Reopened in the Studio"}` and shows a toast "Reopened: …"
    (`web/src/rules/RulesTab.tsx:514-525, 632`). There is no confirmation for reopen; only `approve` asks first
    (`RulesTab.tsx:516-519`).
  - On the server, `add_annotation` appends the event. It doesn't republish anything for `reopen`: only `verdict` on a
    match (`routes_review.py:733-738`) and `approve` (`routes_review.py:740-753`) touch golden files.
  - It only affects `rule_status` (`review.py:555`) and `approved_count` (`routes_review.py:112`).
  - It never clears per-value verdicts.
- **Superseding a verdict:** a new verdict on the same row supersedes the previous one (`web/src/rules/logic.ts:200-217`,
  `verdictEvent`; `supersedes` is set only when the previous event was a verdict). Superseded events drop out of
  `Review.live` (`review.py:308-312`), except when an engineer's event tries to supersede an expert's verdict. There is
  **no event or UI that returns a row to "no verdict"**: a verdict can only be replaced by another verdict.
- **Inconsistency:** `human_reviewed_counts` builds its own superseded set **without** the role rule
  (`review.py:873`), but `Review.__init__` applies the rule (`review.py:308-311`). Unverified whether this ever matters
  in practice.
- **Spec claim with no code behind it:** the Evals spec says "Undoing a verdict takes the value out the same way"
  (`docs/qrspi/evals/03-spec.md:236`). I found no "undo a verdict" path. Changing a ✓ to ✕ republishes the page
  (`routes_review.py:733-738`), which is the only way a value leaves the golden files today.
- **Withdrawing a published column:** decided "Not for now. Columns only grow." (`docs/qrspi/evals/03-spec.md:13`).
  Code: `publish` unions the chosen columns with the existing `properties` and `inherited_columns` of earlier versions
  (`golden.py:484-485, 335-345`). Reopening a rule therefore does not remove its column from the silver dataset.
  - Unverified inference: the next rewrite of a page (`publish_page`) still writes that column's values as
    `approval: rule`, with `approved_by`/`approved_at` set to `None`, because `rule_ok` comes from a status that is no
    longer approved (`golden.py:169-170`, `golden_answers.py:117-119`).
- **Other hits are unrelated:** `ctx.invalidate()` drops manifest caches (`context.py:45`; called in `golden.py:529`,
  `scores.py:279,568,584`, `server/jobs.py:80,104`). The tour's "undo" restores the UI after a tour step
  (`web/src/tour/model.ts:81-140`). "Reset zoom" is in the page pane (`web/src/pagepane/PagePane.tsx:365`).
- **Specs:** neither `docs/qrspi/03-spec.md` nor `docs/qrspi/sme-fixes/03-spec.md` mentions a bulk reset, a reopen of
  value verdicts, or invalidating approvals. `docs/qrspi/03-spec.md` defines `reopen` as "undoes an approve" (line 312)
  and "An edit is a new event that `supersedes` the old one" (line 331). The sme-fixes spec only covers how reviewer
  answers become golden values (§6, §7).

---

## 3. Derived data that depends on approvals, and how it refreshes

| Derived data | Built from | Cache key / refresh | Where |
|---|---|---|---|
| `Review` (row states, statuses, facets, annotations) | snapshot + `log.events()` | rebuilt when `log.offset` moves; per-rule LRU `_Recent` (8 rules) | `review.py:819-837, 60-93, 313-316` |
| `STATUS_CACHE` (rule status) | per (root, catalog, ext, parent, rule, **ids of that rule's live events**) | a new event on the rule changes the key; capped at 20k; cleared by `forget_reviews` | `review.py:52-53, 538-548, 839-844` |
| `_HUMAN_COUNTS` (Rules-tab "Other properties" sort, home column order) | every catalog's log | key = each log's offset | `review.py:850-888`; used `routes_review.py:338-352`, `routes_evals.py:196-197`, `scores.py:932-937` |
| Extraction / snapshot cache | extraction parquet only (no approvals) | LRU of 4 / row budget | `review.py:737-805` |
| Home column statuses and H/N | `golden.plan` on latest publication + log | key includes `log.offset` and `LOADER.generation` | `scores.py:940-984, 992-1006` |
| Golden tab "golden dataset now" | `row_states(...).human` | key includes `log.offset` | `server/routes_golden.py:119-134` |
| Golden tab per-version counts (latest) | `golden.plan` | key includes `log.offset` | `routes_golden.py:37-47` |
| Approve-dialog preview counts | `golden.plan` | key includes `log.offset` | `routes_golden.py:137-163` |
| Compare cache | scorecards with `rv` | keyed with log offset | `server/routes_compare.py:89-94, 131-154` |
| **Golden / silver files on storage** | `golden.plan` | **not** refreshed by reading the log: rewritten only by `publish` (whole version) or `publish_page` (one page) | `golden.py:468-530, 533-564` |
| `lineage.parquet`, `golden.parquet`, `publication.json` | written by `publish` only | `publish_page` does not rewrite them | `golden.py:506-518` |
| Scores | the golden trees + extract output | pair key = golden content sha + output etag; `scores/pending.json` (due +5 min) is run by the server loop against `human-reviewed` | `scores.py:548-563`, `golden.py:614-618`, `server/jobs.py:76-98` |
| Claude's prompt / `rule annotations` | live annotations | read each run | `loop.py:61-112`, `prompt.py:26-30, 147-160` |
| Scorecard "newly wrong" / publish guard | `correct` verdicts | read each `rule try` / `publish` | `loop.py:444-466, 566-570`, `scorecard.py` (outcome `newly wrong`) |

How to refresh after a bulk change (facts about the existing mechanisms):

- Appending events moves `log.offset`. That alone refreshes every in-memory view: `Review`, statuses, home counts,
  Golden tab, approve preview, and Compare (rows above).
- On-disk golden files are rewritten per page by `publish_page` (`golden.py:533-564`), which `add_annotation` calls only
  for a verdict on a `match` (`routes_review.py:733-738`). `golden.publish(ctx, default_target(ctx), by,
  properties=…)` rewrites the whole latest version: both trees, the latest location, `lineage.parquet`,
  `golden.parquet`, and `publication.json` (`golden.py:468-530`). `publish_page` also writes `scores/pending.json`
  (`golden.py:564, 614-618`). The score loop then rescores the human-reviewed tree when it is due
  (`server/jobs.py:89-92`). `after_publish` starts a score immediately (`server/jobs.py:63-66`).
- `LOADER.forget_reviews()` is the only whole-cache reset. It is used when a profile's role changes (`review.py:839-844`).

---

## 4. History and audit

- The audit trail **is** the annotation log. Every approve, reopen, verdict, and comment is an event with `author`,
  `author_role`, `at`, and `note`. Superseded events stay in the file (`log.py:1-8`).
- `GET /api/catalogs/{c}/annotations[?rule=]` returns the live events (`routes_review.py:775-778`). The CLI
  `rule annotations` lists them (`loop.py:263-274`).
- Machine authors are allowed (`docs/qrspi/03-spec.md:319`). Events by authors starting with `golden-datasets` are
  excluded from "Annotated by" and the authors list (`review.py:644, 662`; `routes_review.py:178, 577`).
- Golden versions: `publication.json` keeps `created_at` and `published_at` and is overwritten on each publish
  (`golden.py:510-518`). Old ruleset versions' folders are kept (`golden.py:621-625`). There is no git-like history of
  page files: `publish_page` overwrites them in place (`golden.py:550-561`).
- Rulesets record `forced` / `newly_wrong` when a publish overrode ✓s (`loop.py:575-576`). That is the only existing
  record of approvals invalidated in bulk.
- There is no undo for an approve or a verdict beyond appending a new event.

---

## 5. UI: candidate places and existing patterns

### 5.1 Rules tab, property header (`web/src/rules/RuleHead.tsx`)

- `.rh-actions` (`RuleHead.tsx:79-93`) holds the only per-rule action. When the rule is approved, it shows "✓ Approved",
  "by X · date ·", and the **Reopen** link (`linkish`, title "Undo the approval (a reopen event)"). Otherwise it shows
  the **Approve rule** button, which is disabled with a tooltip reason while blocked (`approveBlocked`). Both carry
  `data-tour="approve"`.
- "How this rule works" `<details>` (`RuleHead.tsx:97-118`).
- Mounted at `RulesTab.tsx:632`. The approve flow is at `RulesTab.tsx:513-532`.

### 5.2 Rules tab, left column (`web/src/rules/RuleList.tsx`, `RulesTab.tsx:624-630`)

- Group headers show "N of M approved" (`RuleList.tsx:25-27, 86`). Each rule has a talk button (`RuleList.tsx:120`).
- At the top is `RulesetPicker`. At the bottom are `WaitingNote` (SME only, filters to engineer-checked values) and
  `FixBar` ("Improve all rules", the agent run) (`RulesTab.tsx:626-630`).

### 5.3 Home / catalog picker (`web/src/catalogs/CatalogPicker.tsx`)

- Header: view switch (Golden dataset / xtra score), "+ Add a catalog" (`CatalogPicker.tsx:92-96`), and the basis
  switch (`:115-116`).
- Each row: "Open →", or "Dismiss" / "✦ Generate rules" (`:138-141`). Per-property fraction cells with tooltips
  (`:181-182`). "How the Studio works" (`:161`).
- No per-catalog menu exists.

### 5.4 Datasets ("Golden") tab (`web/src/golden/GoldenTab.tsx`)

- Read-only by design: "Approving a rule publishes its silver dataset (Rules tab), so there's no Publish button here"
  (`GoldenTab.tsx:1-5`). The header reads "Approving a rule publishes its silver dataset. The golden dataset changes only
  when an expert gives a verdict." (`GoldenTab.tsx` ~line 114). The backend docstring says "nothing here writes"
  (`server/routes_golden.py:1-2`).
- It has a "Golden dataset" section by property (`GoldenTab.tsx:75`), a "Silver datasets" table, and a "Where these
  files are" modal (`GoldenTab.tsx:140`).

### 5.5 Top bar (`web/src/shell/TopBar.tsx:1-42`)

- Catalog, crawl, ruleset, the tabs, and "Show the tour". No catalog actions.

### 5.6 Confirm-dialog patterns

- **`ApproveDialog`** (`web/src/rules/ApproveDialog.tsx:11-49`) is the closest match. It is a modal (`apx-back` / `.apx`,
  `role="dialog" aria-modal="true" aria-labelledby`) that closes on Esc or a backdrop click. It shows a before/after
  table, counts, Cancel, and a primary button with a busy label. The data comes from a preview endpoint
  (`GET /catalogs/{c}/golden/approve/{rule}`, `routes_golden.py:137-163`; `api.approvePreview`, `web/src/api/client.ts:79`).
- Other modals follow the same `role="dialog" aria-modal` shape: `AddCatalogModal.tsx:93`, `GenerateRulesModal.tsx:28`,
  `LoopModal.tsx:125`, `agent/RunButton.tsx:77` (a run "ask" dialog), and `PromptModal.tsx:79`.
- Simplest pattern: `window.confirm("Cancel this run? …")` (`web/src/agent/RunBar.tsx:79`).
- Feedback after an action is a toast (`RulesTab.tsx:525-531`).

### 5.7 Tour text (`web/src/tour/steps.tsx`)

- Step `rules` (`:71-95`) explains Approved / Needs work / In review and counts approved rules.
- Step `annotated-by` (`:160-176`) says an SME ✓ "goes into the golden dataset at once"; an engineer's ✓ waits for
  Confirm.
- Step `approve` (`:340-374`):
  - It reads `.ab-who` and strips "· Reopen" (`:363`).
  - It explains that Approve is blocked until no row is wrong or missing.
  - It says "Approving a rule publishes its silver dataset … The golden dataset … doesn't change" (`:366-370`).
- Any new reset control near `[data-tour=approve]` would need this step's text, and probably `rules`, updated. The tour
  tests read these steps (`web/src/tour/tour.test.tsx`).

---

## 6. Tests that cover approvals

Python (`tests/`):

- `test_approve_publishes.py`: `test_approving_a_column_publishes_it_then_scores_it` (:24),
  `test_a_column_with_no_ctdl_term_is_approved_but_not_written` (:70).
- `test_golden.py`: `test_a_property_is_published_once_its_rule_is_approved` (:33),
  `test_properties_published_one_at_a_time_add_up` (:43), `test_publication_shape_and_lineage` (:63).
- `test_golden_versions.py`: `test_an_engineers_check_waits_for_an_expert_whose_check_is_published_at_once` (:64),
  `test_an_engineers_check_after_an_experts_leaves_it_human_reviewed` (:101),
  `test_annotated_by_filters_rows_courses_and_the_rule_list` (:122),
  `test_an_engineers_cross_still_marks_the_rule_needs_work` (:158),
  `test_events_without_a_role_take_the_authors_role_today` (:164),
  `test_publishing_writes_the_whole_version_and_replaces_the_latest` (:191).
- `test_routes_review.py`: `test_verdict_with_supersedes_and_missing_are_appended` (:169).
- `test_avc_end_to_end.py`: `test_api_rules_rows_compare_and_verdict` (:101; approve refused with 409 at :126-128),
  `test_m1_counts_match_the_prototype` (:40).
- `test_compare.py` (:73-79, changed-since-correct / newly wrong ordering), `test_loop.py`
  `test_try_refuse_publish_check` (:119; the publish refusal on newly wrong, :134), and `test_scorecard.py` (:7).
- `test_scores.py`: `test_human_reviewed_values_are_read_live_from_the_page_files` (:76),
  `test_the_pending_score_runs_when_due` (:218),
  `test_the_catalogs_summary_has_each_columns_status_and_the_latest_score` (:236).
- `test_profiles_rule.py` uses approve events (list-of-objects items; not inspected in detail).
- **No test exercises `reopen`.** A grep for `reopen` in `tests/` and `web/src/**/*.test.*` finds only tour-related
  lines.

Web:

- `web/src/rules/RulesTab.test.tsx`: "…enables Approve when nothing is wrong" (:295), and "asks before approving a
  property's rule: the silver dataset's columns now and after, then approves and publishes it" (:307). Group header "N
  of M approved" (:290).
- `web/src/rules/RuleList.test.tsx`, `web/src/rules/logic.test.ts` (verdict / supersedes logic),
  `web/src/golden/GoldenTab.test.tsx`, `web/src/catalogs/CatalogPicker.test.tsx`, `web/src/tour/tour.test.tsx`.

---

## 7. Open facts and uncertainties (to settle in the Questions or Spec step)

1. **What "approved properties" means for the user** is ambiguous in code terms. It could be (a) rule approvals
   (`approve` events, one per rule version), (b) SME ✓s / answers on values (human-reviewed), or (c) both. Only (a) has
   an existing per-rule undo (`reopen`). (b) has no way back to "no verdict".
2. **Append-only constraint:** any reset must be new events. Deleting or rewriting lines would break readers that track
   offsets and `sync` (`log.py:85-97`, `sync.py:53-65`). Superseding an SME verdict with an engineer-authored event is
   ignored by `Review` (`review.py:308-311`), but `human_reviewed_counts` doesn't apply that rule (`review.py:873`).
3. **Golden files don't follow the log on their own.** After a bulk change, the human-reviewed tree, the latest location,
   and `golden.parquet`/`lineage.parquet` stay stale until `publish` or per-page `publish_page` runs
   (`golden.py:468-564`).
4. **Columns only grow** (`docs/qrspi/evals/03-spec.md:13`, `golden.py:484-485`). Resetting rule approvals would not
   remove a column from the silver dataset. The home status would still show `published` (`scores.py:975-976`).
5. Scope per catalog is natural: the log and `reopen` are per catalog. But `_HUMAN_COUNTS` and the home column order
   sum over all catalogs (`review.py:853-888`, `scores.py:932-937`).
6. Unverified: whether "the value should be different" is better served by targeting `correct` verdicts per property,
   so that `rule publish` stops refusing (`loop.py:566-570`, `prompt.py:341-342`), than by targeting rule approvals.
