# Research: the code (B3, B4, R4, B7, B8, stubs)

Research phase of the field-rules QRSPI. Facts only. Code facts cite `file:line` under `src/golden_datasets/` (Python)
and `web/src/` (TypeScript). Data facts come from the read-only disk cache of the Azure root
(`~/.cache/golden-datasets/8abf1653948e362f/`, filled by the running server) and from GETs to the server on :8000.
Nothing in Azure was written. No source file was changed. Anything **inferred** rather than checked is marked
*Inferred*.

Scratch scripts are in
`/private/tmp/claude-501/-Users-salt--superset-worktrees-ctdl-xtra-find-branch-latest-golden-d5579781/d8da7483-671f-4022-add7-adcfabd4f4cb/scratchpad/code/`
(`logcount2.py`, `size.py`, `enginetime.py`, `reviewtime.py`, `dup.py`, `sigtime.py`, `memtime.py`).

Test suites on the branch as it is: `uv run pytest -q` 122 passed, 52 deselected (the `slow` and `azure` markers,
`pyproject.toml` `addopts`); `cd web && npm test` 23 files, 148 tests passed.

## 0. Summary

- **Today most catalogs have 12 field rules, not 8.** Eight on `locator-course-page` (`course-*`) and four on
  `locator-program-requirement` (`stub-code`, `stub-external-id`, `stub-name`, `stub-learning-type`). WVU's ruleset v2
  dropped the four `stub-*` rules. The sheet's 33 labels + 2 column E fields + Learning Type make **36 field rules on
  course pages**, so 28 are new.
- **The property list has 14 readers in Python and 8 hard-coded rule ids or labels in the web app.** Every reader
  needs only label, CTDL path and order. The Rules tab needs `required` and `group` too. Three readers must **not**
  grow with the list: `import_v2.IN_SCOPE`, and the two "old publications published every property" fallbacks.
- **`multiple` touches nine places.** The Parquet schemas already have `value_index` everywhere, so they don't change.
  What breaks is every in-memory index keyed by `(rule_id, occurrence_key)` without `value_index`. Today a second
  value on one occurrence is silently dropped from the Rules tab, the golden files and the Records tab.
- **Nothing needs `group_index`** (R4). A `>` path flows through golden files, lineage, `golden.parquet`, scores and
  Evals without mis-keying. One web helper (`termUrl`) builds a broken link from it.
- **A stub can't be represented today.** A rule without `definition` fails `rule publish`. A field rule with no
  `selector` and a valid `rule_type` extracts the **whole course block** as its value. A stub needs its own
  `rule_type` and four small guards.
- **Stubs should write no `matches` rows.** As `empty` rows, 28 stubs add 617k match rows and 617k `empty` signals to
  WVU, and triple the time to compute every rule's status.
- **4× field rules is cheap to extract and costly to review.** Extraction compute for WVU stays about 1–2 s. The
  server's in-memory snapshot for WVU grows from 120 MB to about 590 MB, and computing every field rule's status
  (Rules tab list, `golden.plan` after each verdict) goes from 0.7 s to about 3.5 s.

---

## B3. Every reader of the property list and of hard-coded labels / rule ids

### B3.1 The list itself

`model.PROPERTIES` (model.py:26-35) is eight `(label, term)` pairs in display order. `PROPERTY_ORDER` (model.py:36)
maps label → position. `CTDL_TERM` (model.py:37) maps label → term. Labels are the join key everywhere: a rule's
`property_label` and a golden value's `property` are this label, and `publication.json` `properties` lists labels.

### B3.2 Python readers

| # | Where | What it does | What it needs from a file-based list |
|---|---|---|---|
| 1 | `import_v2.py:27` `IN_SCOPE`; used at `:183` (which v2 field rules are imported) and `:337` (which v2 decisions are imported) | Filters v2's rules and decisions by label | **Must stay the old eight.** v2's `canonical_label`s include "Credit Value" and similar (`docs/qrspi/research/data-model.md:242`). If `IN_SCOPE` grows, `import-v2` starts importing review-ui-v2's credit rules, which A5.18 rules out. `tests/test_engine_equivalence.py:16,43` imports it too. *Inferred:* freeze it as a literal set. |
| 2 | `golden.py:148` (`plan`) | Orders a record's fields in the golden file | label → order |
| 3 | `golden.py:185` (`property_rules`) | Orders the columns (approve, publish, home table) | label → order |
| 4 | `golden.py:208` (`published_properties`) | Old `pub-…` publications without `properties` "published every property" | **Must stay the old eight.** With a longer list, it claims old publications published 36 columns. |
| 5 | `golden.py:449` (`publish`) | Orders a version's `properties` | label → order |
| 6 | `golden.py:530` (`column_name`) | label → column name (term without `ceterms:`); None for Learning Type | label → path |
| 7 | `golden.py:536` (`columns_of`) | Labels → column names, in order | label → order, path |
| 8 | `golden.py:558` (`approval_publishes`) | Orders the "after" columns of the approve dialog | label → order |
| 9 | `golden.py:604` (`backfill`) | Orders the columns of rebuilt old publications | label → order |
| 10 | `check.py:370` (`golden_file_checks`) | Old publications without `properties`: every property | **Must stay the old eight**, same as #4 |
| 11 | `prompt.py:48` `IN_SCOPE`, used at `:319` (Improve prompt) and `:605` (first-rules prompt) | Tells Claude which properties are in scope; "Requisites, credit units … are out of scope" | Every label, and the sentence must change (requisites and credit units are now in scope) |
| 12 | `scores.py:620` `STUDIO_COLUMNS` | Home table columns, in order (`routes_evals.py:165`) | Every column with a path, in order; for A4.17 also `required` |
| 13 | `scores.py:623` `NOT_IN_STUDIO` = creditValue, creditUnitType, prerequisite | Greyed home-table columns "xtra extracts it, the Studio doesn't" | `creditValue` and `prerequisite` become Studio columns. `creditUnitType` becomes `creditValue>ceterms:creditUnitType` in the Studio, a different name. *Inferred:* the list becomes empty, or keeps only names no Studio path equals. |
| 14 | `routes_review.py:240` (`/rules`), `:492` (`/courses/{key}`) | Orders field rules in the Rules tab and fields in the Records tab | label → order (and for the Rules tab, group) |

Code that finds a rule by its label or term (not through the list):

| Where | What | Note |
|---|---|---|
| `model.py:161-170` `code_rule_for` | Course-key rule: `settings.course_key_rule`, else the field rule with `ctdl_property == "ceterms:codedNotation"` | Unchanged by the file |
| `rulesets.py:24-41` `first_settings` | Course-key rule of a first ruleset: `property_label == "Coded Notation"` | Needs the label to stay "Coded Notation" (column D says so) |
| `import_v2.py:224-226` | Same, at import | Same |
| `review.py:115-119` | Name rule (course line, golden ids): `ctdl_property == "ceterms:name"` | Unchanged |
| `signals.py:214` | Prose: "the Coded Notation rule found nothing" | Unchanged |
| `import_v2.py:36-100` `AVC_PROSE` | Prose keyed by rule id (`course-code`, `course-description`, …) | Import only |
| `prompt.py:606` | "Keep the template's rule ids (`course-code`, `course-name`, …)" | The file should fix rule ids (see B3.4) |
| `routes_review.py:26-35` | Titles of page rules and locators by rule id | Not field rules |
| `routes_review.py:211`, `:238`, `:483`; `golden.py:58` `FULL_LOCATOR` | `"locator-course-page"` means "course pages" | Unchanged |

### B3.3 Web (TypeScript) and bench readers

The web app never reads `PROPERTIES`. It gets `property_label` and `ctdl_property` on each rule summary
(`api/types.ts:42-48`) and the columns from `/catalogs-summary` (`api/types.ts:278`). Hard-coded names:

| Where | What | Effect of 36 rules |
|---|---|---|
| `rules/RulesTab.tsx:34-37` `defaultRule` | Opens `course-description`, else the first field rule | Still exists in all six catalogs. Fine. |
| `tour/model.ts:63-64` | Default rule; `locator-program-requirement` | Fine |
| `tour/steps.tsx:101-108` | "Three kinds of rules": `group(0..2)` by **index** of `.rule-group`, `fields: n(2)` | With three field groups, `n(2)` counts only the first field group ("Required"). Needs a selector by kind. |
| `tour/steps.tsx:119` | Prose "(Description, Coded Notation, Name …)" | Fine |
| `records/logic.ts:47-48` | Records heading from `ceterms:codedNotation` + `ceterms:name` | Fine |
| `rules/Discussion.tsx:54` | Placeholder mentions `ceterms:inLanguage` | Fine |
| `shell/router.ts:2-3` | Comment examples | Fine |
| `shell/ui.tsx:8` `termUrl` | `credreg.net/ctdl/terms/${t.split(":")[1]}` | **Broken for a path**: `ceterms:creditValue>schema:minValue` gives `…/terms/creditValue>schema`. Used by the rule head (`rules/RuleHead.tsx:50`) and Records cards (`records/RecordsTab.tsx:198`). |
| `bench/shots_review.py:118-379` | Screenshots open `course-description`, `course-code` | Fine; the rule list is longer in every shot |
| `bench/bench_review.py:40,111,127`, `bench/bench_loop.py:48`, `bench/bench_budgets.py:107` | Rule ids | Fine |

### B3.4 Proposed file

**Where:** `src/golden_datasets/properties.csv`, inside the package. Hatch's wheel target is the package folder
(`pyproject.toml` `[tool.hatch.build.targets.wheel]`), so the CLI, the server and Claude's `uv run` all read the same
file. *Inferred:* a CSV diffs well in review, and `properties sync` can write it from the sheet's CSV export. `model`
loads it once at import, and `PROPERTIES` / `PROPERTY_ORDER` / `CTDL_TERM` become views of it.

**Columns** (one row per field rule on course pages, in sheet order):

| Column | Example | From | Used by |
|---|---|---|---|
| `path` | `ceterms:creditValue>schema:minValue` | Column F; column E where F is blank (rows 6, 7); empty for Learning Type | `ctdl_property` of the rule and golden values; `column()` |
| `label` | `Credit Unit Min Value` | Column D; where blank, "Parent: Child" (D9) | `property_label`, golden `property`, publication `properties`. **Must be unique** (see note). |
| `column_d` | `Credit Unit Min Value` or empty | Column D as written | Shows when the name was built, not read |
| `rule_id` | `course-credit-min` | Assigned once by `properties sync`, never renamed | The stub's rule id. **The same in every catalog**, so counts add up across catalogs (B7.4). The eight old rows keep `course-code`, `course-description`, … |
| `profile` | `ceterms:ValueProfile` | Column C | Detail pane only |
| `parent` | `ceterms:creditValue` | The part of `path` before `>` | Readable name, detail pane |
| `multiple` | `true` | Column K (`Multiple` / `Single`); D6 for blanks | Engine (B4) |
| `required` | `true` | Course tab's Required Properties block (D3) | Rules tab group, home table |
| `sheet_row` | `19` | Row in the tab | Tie-break order (D4) |
| `status` | `Include` / blank | Column A | `properties sync` warns on blank (D10) |
| `vocabulary` | `ceterms:CreditUnit` | Column J | Shown only; transformation is later (A3.12) |

Notes from the sheet as read (`phase1-extraction.csv`):

- Column D is blank on rows 23–25, 27–29 (the six ConditionProfile children), **30 (`hasPart`) and 36
  (`learningOpportunityType`)**. D9's "Parent: Child" covers the children only. The two flat rows need a name from the
  term ("Has Part", "Learning Opportunity Type"). *Inferred.*
- Four children are `…>ceterms:description`. With column D blank for the condition profiles, a label of
  "Description" would collide with the course's own Description. Every label lookup above (`property` in golden files,
  `publication.json` `properties`, `check.py:385` lineage keys) assumes one rule per label on course pages.
- Rows 31–34 (`LearningOpportunityProfile` under `hasPart`) and 35 (empty) have no column F and are left out (A1.1).

---

## B4. What `multiple: true` needs

### B4.1 How one value per rule is built in today

| Step | Where | Today |
|---|---|---|
| Find the element | `engine.py:237` | `select_one(el, selector)`: the first element only |
| Find the text | `engine.py:174-191` `extract_from_text` | One `re.search`, one group |
| Emit the match | `engine.py:297-299` | `"value_index": 0` is a literal |
| Index matches | `review.py:82-90` | `matches_by_occ[occ][rule_id] = m`: one per rule per occurrence; a second overwrites the first |
| Row key | `review.py:138-145` | `key = occurrence_key` |
| Verdict target key | `review.py:217-221` | `(rule_id, occurrence_key)`, no `value_index` |
| Re-attachment | `review.py:294-329` | By `(course_key, page_stem)` |
| Signals on a row | `review.py:106-109` | `signals_by_target[(rule_id, occurrence_key)]` |
| Rules tab rows | `routes_review.py:297` | `by_key = {r["key"]: …}` |
| Records tab | `routes_review.py:491` | Iterates `matches_by_occ[occ]` |
| New verdict | `routes_review.py:540-543` | Looks up `matches_by_occ[occ].get(rid)` and stores its `value_index` / `value_seen` |
| Compare / scorecard | `scorecard.py:30-56` `pair_rows` | Pairs rows by `key`, then `(course_key, page)`, then `course_key` |
| Golden publish | `golden.py:121-133`, `:147-168` | `human[(rid, occ)]`, `ann[(rid, occ)]`; iterates `matches_by_occ[occ]` |
| Web | `records/logic.ts:52` `valueKey` = `rule_id|occurrence_key`; `rules/logic.ts:153` `rowTarget` sends no `value_index` | React keys and targets per occurrence |

### B4.2 What already supports several values

- **Every Parquet schema has `value_index`.** `MATCHES` (model.py:54-58) and its sort and primary key
  (model.py:101, `check.py:82`); `SIGNALS` (model.py:59-63); `LINEAGE` `value_index` + `match_value_index`
  (model.py:72-78); `GOLDEN` (model.py:80-86). No schema change is needed.
- **Annotation targets already carry `value_index`** (`routes_review.py:543`, `query.py:28`), and `check.py:136-140`
  joins them to matches on it.
- **Golden files and lineage already number several values of one property.** `golden.plan` gives each lineage row
  `value_index = used[(gid, stem, property)]` (golden.py:171-174). `golden_rows` and the golden-file check count the
  same way per page (golden.py:326-336, `check.py:409-416`). Today this is used only when one course is listed twice
  on a page.
- **Scores pair several values in order.** `scores.studio_targets` sorts lineage by `value_index` and takes the
  scored values of one `(page, golden_record_id, ctdl_property)` in turn (scores.py:562-580). xtra's scorer matches a
  property's values as a list (`score_extraction_match.py:203`).
- `signals.compute` passes `value_index` through (signals.py:157-200).
- `expected.segments` (web `rules/logic.ts:139-149`) is **not** a list of values. It is one value selected in several
  pieces, joined by line breaks. It doesn't help "you missed Health".

### B4.3 What happens today when `value_index > 0` (the duplicate case)

Checked by adding a second value (`value_index` 1, text "SECOND …") to 50 WVU description matches in memory
(`dup.py`):

| Where | What happened |
|---|---|
| `Snapshot.rows` | 22,073 rows, 22,023 distinct keys: both values are rows, with the same key |
| `Review.row_states` | 22,023 states: both values share one state (one verdict covers both) |
| `Review.ordered` | 22,073 rows |
| Rules tab `/rows` | *Inferred:* 22,023, `by_key` keeps the second of each pair (`routes_review.py:297`) |
| `matches_by_occ` | Keeps the second value only |
| `golden.plan` | One Description per course; the 50 courses publish only the second value. The first is lost with no warning. |
| `scorecard.pair_rows(rows, rows)` | 22,023 pairs and **50 "new" rows** comparing a version with itself |
| A new verdict | Records the last value's `value_index` and `value_seen`, whichever item was clicked |
| `check` | Passes: the keys include `value_index` |

### B4.4 Smallest change

1. **Engine.** `run_field` returns a list when `definition.multiple`. Two ways to split, chosen in the definition
   (D5):
   - every element: `select(el, selector)` (engine.py:69) instead of `select_one`;
   - one text: a `split` regex applied to the selected text (after `regex`/`group`, before `transforms`). Each piece's
     offsets are the piece's span plus the group's start, then `to_text_content` as today (engine.py:112-115, 245-246).
   `run_page` numbers them `value_index` 0…n (engine.py:297-299). Nothing found stays one row at `value_index` 0 with
   status `empty` / `no_match`, so "every occurrence × every field rule, once" (`check.py:97-103`) still holds.
   `check_examples` (loop.py:355-372) compares a list output.
2. **Row key.** `occurrence_key` for single rules, `occurrence_key#value_index` for multiple ones. Index matches by
   `(occ, rule_id)` → list (review.py:83-90). `course_line` takes the first (review.py:122-127).
3. **Verdicts.** `_target_key` adds `value_index` for match targets (review.py:217-221). The client sends it
   (`rules/logic.ts:153`) and the server looks it up instead of `.get(rid)` (`routes_review.py:540-543`).
4. **Re-attachment of a list.** `value_index` shifts when one item is added before another. *Inferred:* for multiple
   rules, re-attach by `(course_key, page_stem, normalized value_seen)` first, then by index (review.py:294-329,
   `_carry` 355-367).
5. **Signals.** Key `signals_by_target` with `value_index` (review.py:106-109).
6. **Compare.** `pair_rows` pairs by the new key, then by `(course_key, page, value)` (scorecard.py:30-56).
7. **Golden.** `plan` loops over the list and keys `human` / `ann` by `(rid, occ, value_index)` (golden.py:121-168).
   The lineage and file numbering already work (B4.2).
8. **Records tab.** `course()` lists every value (`routes_review.py:491-505`); `valueKey` adds `value_index`
   (`records/logic.ts:52`).
9. **Adding a missing item.** `missing` is allowed only on occurrences and pages (`log.py:47-48`). A missing list item
   has no row to mark. Options: a `missing` verdict on a match target with the next `value_index` and `expected`, or
   a ✗ on the row of the item before. **Open for the spec.**

Effort is mostly in (2)–(4). *Inferred:* a single rule (`multiple` false) behaves exactly as today if its key stays
the bare occurrence key, so existing annotations keep their rows.

---

## R4. No `group_index`; `>` paths through the Studio

**Nothing needs a `group_index`.** No code reads one (`grep group_index` finds only docs). Several values of one path
are numbered by `value_index` in matches, lineage and `golden.parquet` (B4.2). Pairing a child with its profile is
transformation (A3.13).

How `ctdl_property = "ceterms:creditValue>schema:minValue"` flows:

| Where | What happens | OK? |
|---|---|---|
| Rule doc, `rulesets.publish` | Stored as a string (rulesets.py:16, 148-152) | Yes |
| `MATCHES` | Has no `ctdl_property` | Yes |
| Golden files (`golden.py:158-159`) | `fields[].ctdl_property` is the path; `tree_pages` keeps any truthy path (golden.py:262-264) | Yes (A4.15: flat fields) |
| `LINEAGE`, `GOLDEN` | String columns (model.py:72-86); PKs use `property` (the label), not the path (`check.py:157`) | Yes, if labels are unique (B3.4) |
| `scores.column()` (scores.py:59-61) | `split(":", 1)[-1]` → `creditValue>schema:minValue`; `ceterms:prerequisite>ceterms:description` → `prerequisite>ceterms:description` | Unique, so no mis-keying. Only the first `ceterms:` is cut (cosmetic). |
| `golden.column_name` (golden.py:528-531) | Same rule, through `CTDL_TERM` | Yes |
| `uses_slot_names` (scores.py:285-291) | Reads xtra's records, not golden files | Not affected |
| `value_rows` (scores.py:320-361) | Keys outliers by `(stem, entity, ctdl_property, value)` from the scorer | Yes |
| `result` / `by_column` (scores.py:364-378) | Per `column()` | Yes |
| `_column_counts`, `column_statuses` (scores.py:626-680) | Keyed by `ctdl_property`, reported by `column()` | Yes |
| `/scores/{id}/values` row key | `page|entity|column|n` (`routes_evals.py:116-118`) | Yes: no `|` in a path |
| Evals tab | `col` in the hash query via `URLSearchParams` (`evals/EvalsTab.tsx:73`, `shell/router.ts:20,35`) | Yes |
| `termUrl` (`shell/ui.tsx:8`) | `split(":")[1]` → `creditValue>schema` | **Broken link** |
| `check.py:384-386` | Builds `property IN ('…')` from labels by string interpolation | Labels with `'` would break the SQL; none in the sheet |

**One thing contradicts A4.16's note.** The note says a new column "scores as '—' until xtra writes the same names".
xtra's scorer says "A property the extractor never emitted counts as missing" (`xtra-cli/src/implementations/
score_extraction_match.py:24`). So once a `>` column is published, every value of it counts as **missing** in both
bases, and the overall exact-match rate drops. *Inferred:* the Studio would have to leave those columns out of what it
hands the scorer (in `golden.tree_pages` or `scores`), or show the overall rate over the scored columns only. How
xtra names them stays out of scope.

---

## B7. Rules tab, home table and Evals with about 36 field rules

### B7.1 What the screens do now

| Piece | Where | Today | With 36 + 4 stub-locator field rules |
|---|---|---|---|
| Rule groups | `routes_review.py:231-246` | Three groups by kind: Page rules, Record locators, Field rules. Field rules sort by course pages first, then locator, then `PROPERTY_ORDER` (99 if absent), then id. | One group of ~40 |
| Rule summary | `routes_review.py:172-186` | Calls `rule_status` per rule (all row states) | ×4 cost (B8) |
| Rule list | `rules/RuleList.tsx:25-74` | Renders `rules.groups`, `key={g.kind}`; header "N of M approved" | Three field groups would share `key="field"`: needs a group id |
| Search | none | | Fits in `top` (`RuleList.tsx:24`), today the ruleset picker (`RulesTab.tsx:441`); filter by title, label, path, client-side |
| Default rule | `rules/RulesTab.tsx:34-37` | `course-description` | Unchanged |
| Approve block | `rules/logic.ts:38` `approveBlocked` (used by `RuleHead.tsx:58`); server `routes_review.py:560-563` | Blocked only by open wrong / missing | **A stub has no rows, so it can be approved**, and approving publishes an empty column (`golden.py:539-563`). Needs a guard. |
| Approve dialog | `rules/ApproveDialog.tsx:19-35`; `routes_golden.py:122-150` | "Now" / "After" list every column name joined by ", " | Up to 36 names in one cell. *Inferred:* say "+ creditValue (12 columns)" instead. |
| Fix bar | `agent/FixBar.tsx:9-18` | Counts "needs work" rules | Stubs have status "in review" (no open rows) |
| Picker cards | `routes_review.py:130-132` | `rules_total = len(rs["rules"])` | 17 → 45 rules; "approved" share drops |
| Tour | `tour/steps.tsx:101-108`, `tour/model.ts:48-78` | Groups by index; first rule item is the status anchor | See B3.3 |
| Screenshots | `bench/shots_review.py`, `bench/shots_tour.py` | Fixed rule ids | Longer list in every shot; no code change needed |

### B7.2 Where the three groups and search go

- **Server, `/rules`** (`routes_review.py:235-245`): split the field kind into `required`, `other` and `not-started`,
  each with its own label and an `id`. Order Required by the file's order, Other by cross-catalog human count then
  sheet row, Not started by sheet row. Add `required`, `group` and `human_all` to each summary (`_rule_summary`,
  `:172-186`; `RuleSummary` in `api/types.ts:42-48`; `RuleGroup` in `:50` gains `id`).
- **Program-page field rules** (`stub-code`, `stub-name`, …): today they sort after course rules in the one field
  group. Which of the three groups they join is **open for the spec**. *Inferred:* with their property (Required).
- **Client**: `RuleList` keys groups by `id`; the search box sits above the groups and filters all of them;
  `replaceSummary` (`RulesTab.tsx:40-46`) and `fixCounts` already work across groups. The tour picks the field
  groups by kind, not index.

### B7.3 Home table (`/catalogs-summary`)

- `routes_evals.py:146-165` returns `columns = STUDIO_COLUMNS` and `not_in_studio`, and per catalog
  `scores.column_statuses` (`{status, ruleset, human, rule, found}` per column, scores.py:626-655).
- The web table draws one rotated header per column (`catalogs/CatalogPicker.tsx:118-119`) and one KaTeX fraction per
  cell (`:170-184`). 36 + 3 columns do not fit 1440 px. *Inferred.*
- For A4.17 ("Required, then any column with a human review, rest behind Show all"), the response needs per column:
  `required`, the label, and the cross-catalog human count. Per-catalog `human` is already there; the sum across
  catalogs can be done in the client from the same response.
- `column_statuses` lists every rule from `golden.property_rules` (golden.py:181-192). A stub would show as "in review"
  with `found` 0. It needs a "not started" status.

### B7.4 Counting human-reviewed values across all catalogs

| Way | Cost | Exact? |
|---|---|---|
| **A. Per catalog `Review`**: sum `RowState.human` per rule (review.py:330-336), as `scores._column_counts` does through `golden.plan` | Needs every catalog's snapshot and row states. WVU today: 0.18 s snapshot + 0.7 s states, 3–4 s at 4× (B8). `/catalogs-summary` already pays this for the home page and caches it per log offset (scores.py:658-680). | Yes |
| **B. Annotation logs only**: per `(rule_id, course_key, page)`, the latest live expert verdict that is `correct`, or `wrong` with `expected.text` | 12 ms for all six logs on local disk (`logcount2.py`). The server already keeps each log open and reads only appended bytes (`log.py:62-76`, `review.py:589-593`) | Close. It skips carry-forward (`fixed`, `changed-since-correct`). AVC: 14 per rule from A vs 12–14 from B; CCSF: 63–65 vs 63–65; WVU 83–84 vs 83–84. |

- Measured live, per catalog and column (`/catalogs-summary?basis=human`): AVC 14, CCSF 63–65, Marshall 13, UALR 10,
  UARK training 0, WVU 83–84. Way B reproduces these within 2.
- Most events have no `author_role`. The role comes from `profiles.json` (`profiles.py`, `review.py:204`): Jared and
  Cadence are `sme`.
- **Keying across catalogs:** a target carries `rule_id`, not the path. Rule ids match across catalogs today
  (`course-code` … in all six). With the file's fixed `rule_id` (B3.4) they keep matching. Otherwise map through each
  catalog's latest ruleset (small JSON, cached).
- *Inferred:* B, cached per `(catalog, log offset)`, is cheap enough for every `/rules` call. On Azure, the first read
  of six logs is the cost (the v2 research measured 1.77 s for a 462 KB append blob,
  `docs/qrspi/research/speed-storage.md` §2.3). Reading them in parallel once per server start, then by offset, keeps it
  to six small range GETs per call.

### B7.5 Evals tab

`/scores/{id}/values` builds its column list from the scored rows (`routes_evals.py:126-142`), and `EvalsTab.tsx:343-345`
draws one `ColRow` per column. It shows only columns that were scored. More Studio columns only add rows there. The
"missing" effect in R4 applies.

---

## B8. Cost of 4× field rules (WVU, 22,023 courses)

WVU's latest extraction `rs-0002` (local cache): 900 pages, 22,023 occurrences, 8 field rules, **176,184 matches,
2.7 MB** `matches.parquet`, 18,720 signals. Its first extraction `rs-0001` (12 field rules, 38,976 occurrences, 243,996
matches) took **1.37 s** to parse and run rules on 900 pages, with workers, and 1.18 s for signals and assembly
(`extraction.json` `timings_s`).

| Measure | Today (8 rules) | + 28 stubs as `empty` rows | + 28 rules like description / name | Script |
|---|---|---|---|---|
| `matches` rows | 176,184 | 792,828 | 792,828 | `size.py` |
| `matches.parquet` (zstd) | 2.7 MB | 4.0 MB | 38 MB (upper bound: 14 copies each of description and name text) | `size.py` |
| `signals` rows | 18,720 | 635,364 (+616k `empty`) | | `sigtime.py` |
| `signals.compute` | 0.91 s | 1.38 s | | `sigtime.py` |
| Engine, field rules only | ~5 µs per field per course (AVC: 22 pages, 8 vs 40 rules, 0.277 s vs 0.281 s; parsing is 0.24 s of it) | | *Inferred:* 22,023 × 28 × 5 µs ≈ 3 s CPU, ~0.3 s on 10 workers | `enginetime.py` |
| `Snapshot` build | 0.18 s | 0.57 s | 0.72 s | `reviewtime.py` |
| `Snapshot` memory | 120 MB | | 588 MB | `memtime.py` |
| Every field rule's status (Rules tab list) | 0.70 s | 3.24 s | 3.71 s | `reviewtime.py` |
| `golden.plan` (home table, approve, **every expert verdict** via `publish_page`) | 1.41 s | 1.72 s | 3.07 s | `reviewtime.py` |

Findings:

- **Extraction stays cheap.** Parsing dominates the engine. Adding the stub version reruns only the 28 new rules
  (their `input_hash` is new, extract.py:113-128), which still parses all 900 pages: about the 1.4 s of `rs-0001`.
- **The review side grows linearly with rows.** A new `Review` is built after every annotation (the cache key
  includes the log offset, review.py:595-611), so the first `/rules` after a verdict recomputes every rule's status.
  `publish_page` after each verdict runs `golden.plan` over every field rule (golden.py:126-133, 514).
  *Inferred:* WVU at 4× with real rules adds 2–3 s to those calls and about 0.5 GB per loaded WVU snapshot (the
  loader also keeps the parent extraction's snapshot, review.py:595-603).
- **Stubs as `empty` rows cost almost as much as real rules on the review side** (3.24 s vs 3.71 s), for nothing.
  Stubs that write no rows cost nothing until they get a definition.

---

## Stubs: rules with no definition

### What happens today

| Path | Where | A rule with no `definition` | `definition = {"locator": …, "rule_type": "css"}`, no selector |
|---|---|---|---|
| `rule try` / `publish` draft | loop.py:389-390 | Refused: "each rule in a draft needs rule_id and definition" | Accepted |
| `_validate_definition` | loop.py:328-352 | Needs an object | OK |
| `validate_ruleset` | rulesets.py:79-91 | `KeyError` on `definition` | OK. A `rule_type` outside `css`, `css+regex`, `regex`, `constant`, `source_url` is refused. A missing `locator` is a bare `KeyError`, not a `UserError`. |
| `model.dependencies` / `content_hash` | model.py:114-143 | `KeyError` | OK. Every stub has the same `content_hash`; versions are per rule, so that's fine. |
| `engine.run_field` | engine.py:237-247 | — | **No selector means the whole occurrence element is the target.** With no regex, the value is the whole course block's text, status `found`. |
| `extract.compute` | extract.py:146-153 | `KeyError` (`["definition"]["locator"]`) | OK |
| `signals.compute` | signals.py:168 | `KeyError` (`["definition"]["rule_type"]`) | OK |
| `Snapshot` name rule | review.py:117-119 | `KeyError` | OK |
| `/rules` sort | `routes_review.py:238` | `KeyError` | OK |
| `check` CHK | `check.py:97-103` | | An occurrence without a match row for a field rule of its locator fails "every occurrence × every field rule, once" |
| `rule_status` | review.py:392-420 | | 0 rows → "in review", never "needs work"; **Approve is allowed** (B7.1) |
| `rule draft` | loop.py:281-300 | | Works once the stub is in the ruleset; before, "a new rule: write it into the draft by hand" |

### What a stub needs (smallest)

- `definition = {"locator": "locator-course-page", "rule_type": "stub"}`, plus `ctdl_property` and `property_label`
  from the file. *Inferred:* a dedicated `rule_type` is safer than a `css` rule with no selector, which extracts
  whole blocks.
- `validate_ruleset` accepts `stub` (rulesets.py:88).
- `run_page` skips stubs: no `matches` rows (engine.py:286-299). Signals then skip them too (signals.py:166-170).
- `check.py:97-103` excludes `rule_type = 'stub'` (the `rule_versions` view has `rule_type`, `query.py:46-47`).
- `rule_status` says `not started` for a stub, and Approve is refused for it (server `routes_review.py:560-563`, web
  `logic.ts:38` `approveBlocked`). `column_statuses` and `property_rules` report "not started".
- `check_examples` skips stubs, as it skips derived rules (loop.py:362).

### The Improve prompt and `rule try` for a stub

- `prompt --rule <stub>` works (`scope_rules`, prompt.py:94-98) and prints the stub definition. But:
  - "Only the in-scope Course properties count: … Requisites, credit units … are out of scope: don't add rules for
    them" (prompt.py:319-320) now says the opposite of the task.
  - "Publish only when … `rule try` must say BETTER (fixed > 0, newly wrong = 0)" (prompt.py:322-323). A stub's first
    definition has no annotations, so the scorecard can only say "UNKNOWN (no annotated row changed)"
    (scorecard.py:170-180). The prompt needs a "first version" branch, like `build_first_rules_prompt` (prompt.py:547).
  - "Open annotations (0) · None: every wrong / missing verdict on this rule is fixed" reads wrong for a stub.
- `rule publish` refuses only when `newly_wrong > 0` (loop.py:551-554), so a first definition can be published.
- The "Improve all rules" run (`needs_work`, prompt.py:277-278) picks only "needs work" rules, so stubs are never in
  it.
- A stub has no rows, so the usual loop (annotate rows → Improve) has nothing to annotate until Claude writes a first
  version. *Inferred:* A5.19's answer ("the usual loop") needs the first version written from saved pages, with
  `pages sample` / `pages get`, before anyone annotates.

---

## What contradicts the decisions or assumptions

1. **A4.16 note: "a new column scores as '—'".** xtra's scorer counts an unemitted property as missing (R4). Once
   approved and published, a `>` column lowers the exact-match rate.
2. **"Eight field rules" (Part C, A6.21).** There are 12 per catalog today (6 for UARK training, which has no code or identifier rule; 8 for WVU, whose v2 dropped the program-page rules): 8 on course
   pages, 4 on program-page lines. The new list covers course pages. Program-page rules need a place in the three
   groups.
3. **D9's "Parent: Child" naming** doesn't cover `hasPart` (row 30) and `learningOpportunityType` (row 36): both
   flat, both with a blank column D.
4. **A5.19 "the usual loop"** has nothing to annotate on a stub, and the prompt's BETTER rule can't be met by a first
   version.
5. **Labels must be unique** (golden `property`, `publication.json`), so a ConditionProfile `description` can't be
   labelled "Description".
6. **D8 (stubs in the ruleset)** is fine if stubs write no rows. As `empty` rows, the cost in B8 applies.
