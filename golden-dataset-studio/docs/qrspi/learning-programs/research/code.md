# Research: adding ceterms:LearningProgram to Golden Dataset Studio (code findings)

Paths below are relative to the repo root (`/Users/eric/.paradev/worktrees/ctdl-xtra/all-right-looks-like-e2bc6cd3`). Abbreviations: `gds/` = `golden-dataset-studio/src/golden_datasets/`, `web/` = `golden-dataset-studio/web/src/`, `xc/` = `xtra-cli/`.

---

## 1. The scorer and what xtra emits for program pages

### Where the scorer comes from
- Studio imports xtra-cli in-process as a uv path dependency: `golden-dataset-studio/pyproject.toml` (`"xtra-cli"`, `[tool.uv.sources] xtra-cli = { path = "../xtra-cli", editable = true }`).
- `gds/scores.py:326-332` `run_scorer()` calls `implementations.score_extraction_match.match_extraction_run` twice (exact and partial). `PARTIAL_THRESHOLD` is used at `:401`, `extracted_claims` at `:591`, and `implementations.extract.IDENTIFIER, SUBJECT_WEBPAGE, TERMS` at `:616`. That last import decides which columns xtra "extracts", and so what goes into `not_scored`.
- The scorer lives in `xc/src/implementations/score_extraction_match.py` (962 lines). The CLI entry is `xtra score extraction match` (`xc/README.md:154-155`).
- `gds/scorecard.py` and `gds/suite.py` do **not** use the xtra scorer. They are Studio-internal comparisons (Compare tab, suite deltas) that join rows on `(course_key, page_stem)` (`scorecard.py:5,34-49,118-128`; `suite.py:28-35,52,72`).

### Is it class-aware? No. It is class-agnostic and pairs by position.
- No reference to `entity_type`, `LearningProgram` or `Course` in `score_extraction_match.py`. A grep for `entity_type` finds nothing there and nothing anywhere in `gds/`.
- What it reads:
  - **Baseline file**: `<catalog>/<crawl>/<stem>/<stem>.json`, a list of entities `[{fields:[{ctdl_property, value, source_url, location?, absent?}]}]` (`:533-553`, `_baseline_stems :823-833`).
  - **Records**: every `records/<stem>*.json`, grouped by the text before `--`, the page's own record first (`_record_keys_by_stem :836-858`).
- **Matching key** is page stem plus entity position. `match_page :556-572`: "The first baseline entity belongs to the page's own record and the rest to the extra-entity records, in record id order." The record's `entity_type` is never checked. Inside an entity, units pair per `ctdl_property`: exact pairs first, then greedy by similarity. Objects pair by `OBJECT_KEYS` (only `ceterms:estimatedDuration` → description, `:129`).
- **What it compares** is the record's flat `expected` {ceterms term: value} (`extracted_claims :157-184`). It has these hard-coded special cases:
  - `creditValue` is split into min/max (`CREDIT_PROFILE_KEYS :124-135`).
  - `subjectWebpage` is filled from `source_url` (`:180-181`).
  - `estimatedDuration` is the one object key (`:129`).
  - Any other term is compared generically by text similarity. So `ceterms:name`, `description` and `codedNotation` of a LearningProgram would score with no code change.

### What xtra-cli's extraction emits for program pages
- Discovery's label `LearningOpportunity` maps to the entity `LearningProgram` (`xc/src/implementations/discover_rules.py:1320-1325`; `extract_dom.py:107-113`). The README's classification table is at `xc/README.md:507-509, 744`. A program page that names an award is labelled `Credential` instead (`README.md:535-538`).
- One page can give several records. `xc/src/xtra/catalog/extract.py:160-182`: record id `stem` for the main entity, `stem--<type>` for the others (for example `stem--competency`, which Atlantic Cape's program pages produce).
- Record shape (`xc/src/implementations/extract.py:258-283`): `{id, record_id, catalogue_type: "COURSES" (hard-coded), entity_type, source_url, stem, template_id, verification, source_expected:{fields}, expected:{term: value}}`.
- Program fields: only three. `TERMS` (`extract.py:54-74`) maps:
  - `learning_program_id` → `ceterms:codedNotation`
  - `learning_program_name` → `ceterms:name`
  - `learning_program_description` → `ceterms:description`

  `ceterms:subjectWebpage` is added by the scorer from `source_url`. `ceterms:identifier` is derived **only for Course** (`record_fields` → `_course_derived`, `extract.py:186-211`). Course templates run only for `ENTITY_COURSE` (`:140-159`); programs are read by `extract_dom` (`NAME_FIELD/DESCRIPTION_FIELD/ID_FIELD`, `extract_dom.py:117-131`).
- The older pipeline in `xc/lib` agrees:
  - `FIELD_INVENTORY.csv` has exactly three `LearningProgram` rows (id/name/description) plus `course_program` (Course, no CTDL term) and `relationship_heading` (Link).
  - `lib/export_xtra.py:15,24,72-78` exports `learning_programs` / `LEARNING_PROGRAMS` with the same three fields.
  - `lib/union_fields.py:43` lists `learning_programs`.
  - `lib/record.schema.json:30,236,477` has the entity_type enum `Course, LearningProgram, Credential, CompetencyFramework, Competency, Link`.

### What would need to change
1. **Filter records by class before scoring.** Today, a golden LearningProgram tree for a stem would be paired with whatever record is first for that stem. That could be a `Credential` record (when discovery saw an award) or a Course record. The reverse problem already exists: Studio's Course golden includes **Course lines found on program pages** (`golden.py:43`, "course pages and program-page course lines alike"). xtra's own record for such a page is a LearningProgram or Credential, so those Course entities are paired with the wrong record type today. There are two places the fix could go:
   - **Cheapest:** in the Studio's `RecordsStore` (`gds/scores.py:85-116`), list only records whose `entity_type` matches the class being scored. This adds a read per key; records are cached in `_json`.
   - **Cleaner:** a `--entity-type` filter in `match_extraction_run`.

   Either way, positional pairing within a stem must count only records of that class.
2. Make the golden root and baseline paths per class (see §5). Otherwise a Course file and a LearningProgram file for the same program-page stem collide at `<catalog>/<crawl>/<stem>/<stem>.json`.
3. Decide whether to treat Credential-labelled program pages as LearningProgram. xtra splits them by whether an award is named; Studio's class would be LearningProgram for both.
4. `not_scored` / columns-xtra-extracts (`gds/scores.py:614-616`) reads `TERMS`, which is not per entity. For programs it should be limited to `codedNotation`, `name`, `description` and `subjectWebpage`. It must not claim `ceterms:identifier`, because programs don't derive it.
5. Optional: `catalogue_type: "COURSES"` is hard-coded in `extract.py:272`. Harmless to the scorer.

---

## 2. Course properties: which have rules, "Phase 1 vs 2", and ordering

### properties.csv
- 48 rows, 15 columns (`gds/properties.py:30-31`): `rule_id, path, sheet_path, path_note, label, parent, profile, multiple, required, course_key, sheet_row, status, vocabulary, definition_text, sample`.
- `status` holds the sheet's column A: `Include` (37 rows) or `removed` (11: the estimated-duration child paths, keyword, has-part and the `*-alternative-condition` paths). It does **not** mean "has a rule".
- `required=true` on 8 rows: learning-type, external-id, name, description, subject-webpage, lifecycle, language and code. The flag comes from the sheet's "Course" tab "Required Properties" block (`required_from_course_tab :167-180`), with a fallback list at `:45-46`. `codedNotation` is forced to required and is the `course_key` (`:271-272`).

### "Phase 1" vs "Phase 2"
- "Phase 1" exists only as the **sheet tab name** `"Phase 1 Extraction"` (`properties.py:1,29,186-198`) and in spec names (`phase1-followups`).
- There is **no Phase 2 notion anywhere in code**. A grep for `phase ?2` finds nothing in src or web.
- The sheet's `Course` tab is read only for the Required block (`COURSE_TAB`, `:29,198`). A LearningProgram class would need its own tab names, its own required block, its own `LEARNING_TYPE`-equivalent and its own `KEPT_IDS`.

### Which properties have rules today
"Has a rule" is a **per-catalog** question. It is answered by the catalog's ruleset: a property rule with `rule_type: "none"` means listed but with no rule yet. `properties apply` creates those drafts (`missing_rules :361-378`; `model.RULE_TYPES` includes `none`, `model.py:58-59`).

Deployed data, read from the local cache of the deployed root (`~/.cache/golden-datasets/8abf1653948e362f/<catalog>/golden-dataset-studio/{rulesets,rules}`, latest ruleset):

| catalog (latest ruleset) | property rules with a real rule (besides the 8 required) | `none` (listed, no rule) |
|---|---|---|
| AVC (v27) | 17: credit value/min/max/unit, description fields of the prerequisite family, content-description, estimated-duration, in-catalog, is-non-credit, learning-method-type, prereq/recommends target-LO | 20 |
| Marshall (v8) | 9 | 26 |
| UALR (v6) | 14 | 25 |
| WVU (v6) | 12 | 27 |
| CCSF (v8) | 12 | 23 |
| training-uark (v3) | 0 | 41 (code and external-id are `none` too) |

The 8 required properties have real rules in all 5 university catalogs. In older versions some are still legacy `kind: "field"` rules from import-v2 (for example `marshall/rules/course-name/v0001.json`).

### How the Rules tab orders and groups them
- Server side, `gds/server/routes_review.py`:
  - `PROPERTY_GROUPS` (`:324-326`): `required` "Required", `other` "Other properties", `not-started` "Not started" (collapsed), `program` "Program page lines" (collapsed).
  - `property_group()` (`:328-334`): a rule whose locator isn't `locator-course-page` goes in `program`; a CSV-required one goes in `required`; `rule_type none` goes in `not-started`; anything else goes in `other`.
  - Sorting (`:337-375`): Required by `model.PROPERTY_ORDER`; Other by human-reviewed count across all catalogs, then sheet row; Not started by sheet row; Program by locator.
  - Page rules and record locators come first. `PAGE_RULE_TITLES`/`KNOWN_LOCATORS` hard-code `course-page`, `program-page`, `program-page-with-courses`, `locator-course-page` and `locator-program-requirement` (`:26-31`).
- `gds/model.py:41-55` `_ordered_properties()`: required rows first in `properties.REQUIRED_ORDER` (`properties.py:47-49`: codedNotation, identifier, "" (Learning Type), name, description, subjectWebpage, lifeCycleStatusType, inLanguage), then sheet order. The result is module-level constants `PROPERTY_ROWS/PROPERTIES/PROPERTY_ORDER/CTDL_TERM` (`:57-61`), loaded once at import, so not per class. `FIRST_EIGHT` is at `model.py:~22-39`.
- Client side, `web/rules/RuleList.tsx:25-27`: `COUNTED = {"not-started": "properties", program: "rules"}`. The client renders the server's groups as given.
- ⚠ **Name clash.** The existing **Course** group id `program` ("Program page lines") and the Course page rules `program-page` and `program-page-with-courses` use a `program` prefix. They are in every university catalog's rule history: 5 catalogs each have `program-page`, `program-page-with-courses` and `locator-program-requirement` under `rules/`, although the latest rulesets no longer include them. They are also in `import_v2.py:30-31`. The new `program-…` rule-id prefix for LearningProgram would clash with them. Rename them, or choose a different prefix.

---

## 3. Inventory of Course hardcoding

### Rough counts (case-insensitive "course"; `course_key|courseKey`; `course-…` id literals)

| area | "course" mentions | course_key | `course-*` literals | `locator-course-page`/COURSE_LOCATOR/FULL_LOCATOR |
|---|---|---|---|---|
| gds/ (src) | 670 | 145 | 102 | 18 (routes_review 9, import_v2 6, properties 4, golden 3, prompt 2) |
| web/ | 1023 (includes CSS classes) | 54 | ~416 (mostly tests and CSS) | 24 |
| tests/ | 695 | 44 | ~444 | 38 |
| bench/ | 49 | 0 | 42 | 3 |

### Per file (top of the list; columns are any / course_key / `course-` literals)

| file | any | ck | id |
|---|---|---|---|
| gds/report.py | 153 | 11 | 0 |
| gds/prompt.py | 87 | 5 | 10 |
| web/agent/Report.tsx | 76 | 1 | 1 |
| gds/server/routes_review.py | 66 | 25 | 2 |
| gds/review.py | 54 | 25 | 0 |
| gds/import_v2.py | 53 | 5 | 12 |
| web/rules/RulesTab.tsx | 49 | 15 | 1 |
| gds/properties.csv | 49 (rule ids and the `course_key` column) | 1 | – |
| web/records/RecordsTab.tsx | 37 | 10 | 2 |
| gds/properties.py | 29 | 6 | 7 (+LEARNING_TYPE) |
| gds/golden.py | 22 | 9 | 0 |
| gds/loop.py | 21 | 11 | 1 |
| web/tour/steps.tsx | 20 | 0 | 0 |
| web/api/types.ts | 19 | 7 | 0 |
| gds/scores.py | 19 | 0 | 0 |
| web/rules/logic.ts | 18 | 0 | 0 |
| gds/signals.py | 17 | 5 | 0 |
| gds/suite.py | 16 | 5 | 0 |
| gds/scorecard.py | 15 | 14 | 0 |
| web/agent/api.ts | 14 | 0 | 0 |
| gds/strata.py, web/evals/EvalsTab.tsx | 11 each | 1 / 0 | 0 |
| gds/facets.py, model.py, agent_runs.py, query.py, engine.py, check.py, rulesets.py | 3–8 each | 2–5 | 0 |

### Classification

**Rename only** (`course_key` → `record_external_identifier`; wording):
- Persisted and schema-level:
  - `model.OCCURRENCES.course_key` (`model.py:74`)
  - `model.course_key()` (`:178`)
  - `settings.course_key_rule` (`rulesets.py:41`, `model.py:195`, `loop.py:299-302`, `properties.py:357`)
  - annotation `target.course_key` (checked at `check.py:141-144`; re-attach at `review.py:16,443-578,1035`)
  - properties.csv column `course_key` (`properties.py:31,32,272`)
  - golden `publication.json` `skipped_no_course_key` (`golden.py:200,406`)
  - DuckDB views (`query.py:28,117,132`)
- API and TS field names: `web/api/types.ts:50,129,153,159,173,206,445`.
- Report contract: `report.json` uses keys `course` / `courses` (`prompt.py:275-324` documents them for Claude; `report.py:124-268` resolves them; `web/agent/Report.tsx` renders them). Stored reports under `agent-runs/<id>/` already use these keys, so they need a read-compat alias.
- Pure wording: "course", "courses exact", "Missed course" and similar in `report.py`, `prompt.py`, `tour/steps.tsx:85-94`, `EvalsTab.tsx:12,57,453,577,586,620,641`, `RulesTab.tsx` toasts (`:433-483`), `scores.py:471-482` (`courses`, `courses_exact` count keys, also in `types.ts:337-338,432`).

**Generalize** (needs a class parameter):
- `properties.py`:
  - `FILE` (one CSV), `PHASE1_TAB/COURSE_TAB` (`:29`)
  - `LEARNING_TYPE` (`:35-38`, `sample: "Course"`)
  - `KEPT_IDS` (`:40-43`)
  - `REQUIRED_FALLBACK/REQUIRED_ORDER` (`:45-49`)
  - `rule_id_for` → `"course-" + …` (`:116-121`)
  - `COURSE_LOCATOR`/`course_locator` (`:351-358`)
  - `apply()` and `cmd_apply`, which load per catalog
- `model.py:41-61`: `PROPERTY_ROWS/PROPERTY_ORDER/CTDL_TERM/FIRST_EIGHT` are module globals. They need to be per class.
- `routes_review.py`: `PROPERTY_ROW` global (`:34`), `PAGE_RULE_TITLES/PLAIN_SUBTITLES/KNOWN_LOCATORS` (`:26-31`), `locator_title` ("Whole page is one course", `:37-42`), `rule_title` (`:55-58`), `PROPERTY_GROUPS/property_group` (`:324-334`).
- `golden.py:63` `FULL_LOCATOR = "locator-course-page"`, used for golden_record_id collisions (`:85-106`) and the properties listing (`:205-210`).
- `layout.py`: every Studio path (see §5). `context.py:119` builds a rules prefix by hand.
- Server: about 45 catalog-scoped routes (`/api/catalogs/{catalog}/…`) need a class segment or query parameter.
  - Explicitly course-named: `GET /catalogs/{catalog}/courses` and `/courses/{course_key}` (Records tab; `web/api/client.ts:56-58`, `web/records/RecordsTab.tsx:44-69`).
  - Class-independent: `pages/*`, `assets`, `crawls`, `profiles`, `login`.
- CLI: 40 `add_parser` calls (`cli.py:87-342`), about 31 leaf commands.
  - Clearly class-independent: `init`, `assets fetch`, `crawls list/add`, `pages get/sample`, `sync`, `serve`, `hash-password`, `properties sync` (arguably), `sql`.
  - A blanket required `--class` would be awkward on these.
- `prompt.py:39-62`: the first-pass prompt hard-codes `course-page`/`locator-course-page` and "one course per page".
- `agent_runs.py:484,927-928`: row payloads and history text.
- `scores.py:161,471-482,753-868`: "courses" counting, `subject()` grouping by course-code letters.
- `catalogs.py:9-26`: a per-catalog `course_code_pattern`.
- `strata.py:44` and `facets.py:154`: course-code subject strata.

**Course-only** (hide for other classes, or keep as Course features):
- Program-page course lines: `locator-program-requirement` and the `program` group (`routes_review.py:58,325-329`), and import_v2's program rules (`import_v2.py:30-31,59-100`).
- Repeating course blocks (`locator.repeat`, `RulesTab.tsx:66-69,237-269,386,450-466`, `MissedCourse`), and duplicate-code collisions `course_key~n` (`golden.py:43-45,85-106`).
- `creditValue`/`estimatedDuration`/prerequisite-family list-of-objects rules (`profiles_rule.py`; `SKIP_PATHS` in `properties.py:52-56`). The scorer's credit split also applies only where those terms exist.
- `signals.py:156-219` ("<code> occurs N× on this page").
- `golden.py` docstring rule: "every course found on a page is published".

### Top ~15 hotspots
1. `gds/properties.py`: LEARNING_TYPE, KEPT_IDS, REQUIRED_ORDER, rule_id_for, COURSE_LOCATOR, single CSV.
2. `gds/model.py:41-74,178-204`: global property order, OCCURRENCES.course_key, code_rule_for.
3. `gds/server/routes_review.py`: 25 course_key; titles, groups, `/courses` routes.
4. `gds/review.py`: 25 course_key; annotation re-attachment by (course_key, page).
5. `gds/report.py`: 153 mentions; `course`/`courses` reference grammar.
6. `gds/prompt.py`: report schema plus first-pass prompt with course rule ids.
7. `web/agent/Report.tsx`: 76 mentions; `ReportCourse`, `course_key: r.course`.
8. `web/rules/RulesTab.tsx`: 49; default rule `course-description` (`:49`), per-course navigation.
9. `web/records/RecordsTab.tsx` and `records/logic.ts`: the whole tab is "find a course".
10. `gds/golden.py`: FULL_LOCATOR, course_key collisions, golden root paths.
11. `gds/scorecard.py` and `gds/suite.py`: joins on (course_key, page_stem).
12. `gds/loop.py`: 11 course_key; `course_key_rule` settings.
13. `gds/layout.py` and the hand-built paths in `golden.py:265,284`, `scores.py:250,296`, `publishing.py:35`, `agent_runs.py:63-64`.
14. `gds/import_v2.py`: v2 import is Course-only. Leave it Course-only.
15. `web/api/types.ts` and `client.ts`: field names, `courses()`/`course()` endpoints.

---

## 4. Tests: what is outside-in and what is tied to Course

Runners: `make check` runs ruff, pytest (default `-m 'not slow and not azure'`), web tsc and vitest, and build. `make slow` runs `pytest -m slow`, which needs `~/review-ui-v3-data` (Makefile; pyproject markers).

| test | kind | what it covers | catches refactor regressions? |
|---|---|---|---|
| tests/test_golden_versions.py (`studio` fixture `:29-43`) | **HTTP + CLI end to end** on a synthetic 3-page catalog: real `crawls add`, `rule publish`, TestClient | verdicts → golden trees, versions, human-reviewed | **Yes**, the best fast harness. Imported by test_scores, test_reset, test_property_lists, test_approve_publishes and test_speed. Its RULES use `course-*` ids (41 literals). |
| tests/test_scores.py | CLI + **real xtra scorer** in-process | score.json, values.parquet, not_scored | **Yes.** It is the one test of the scorer integration. |
| tests/test_one_rule_runs.py + tests/minicat.py | CLI-built 6-course catalog + HTTP, fake K2 | AI runs, report checking | **Yes** for runs and reports. Heavily Course-shaped (cuesta codes, `course-*` rules). |
| tests/test_agent_runs.py | unit + HTTP (FakeK2) | live.json/goals locks, queue | Partly. 29 `course-*` ids. |
| tests/test_reset.py, test_approve_publishes.py, test_property_lists.py, test_profiles_rule.py, test_speed.py | CLI/HTTP behavioural on synthetic catalogs | reset, approve → publish → score, `properties apply`, list-of-objects, per-verdict cost | Yes |
| tests/test_crawls.py | CLI + HTTP | add catalog / crawl | Yes (class-independent) |
| tests/test_routes_review.py | HTTP; fast pure tests + 7 slow on `.data/root-demo` (skips if missing, `:92`) | Rules/Records API | Partly. Slow half skips here: no `.data/` in this worktree. |
| tests/test_compare.py, test_golden.py | slow, need `.data/root-demo` | Compare API, golden publication | Skip without the demo root |
| tests/test_avc_end_to_end.py, test_engine_equivalence.py, test_prompt.py (6 slow), test_loop.py (2 slow), test_files.py (slow) | `make slow` on the AVC mirror (`conftest.avc_v1_root`: sync, init, import-v2, extract) | full M1 path, engine parity, prompt, loop | Yes, but slow and AVC/Course-only |
| tests/test_storage_contract.py, test_storage_sas.py | storage backend contract (azure marker) | Root API | Unaffected (paths are opaque) |
| tests/test_properties.py, test_property_rules.py, test_engine.py, test_strata.py, test_facets.py, test_scorecard.py, test_score_units.py, test_report*.py, test_loader_cache.py, test_recent_lock.py | unit tests on internals | sheet parsing, engine, strata, report helpers | Tied to Course constants (`LEARNING_TYPE`, `course-*`, course_key fixtures). These will churn and not protect. |
| web vitest: 31 files (`RulesTab.test.tsx` 44 its, `report.test.tsx` 23, `agent.test.tsx` 15, `picker.test.tsx` 14, `report.pass7.test.tsx` 14, `EvalsTab.test.tsx` 12, `CompareTab.test.tsx` 10, `RuleList`, `ProfileItems`, `NotHere`, `GoldenTab`…) | component tests with `vi.stubGlobal("fetch", …)` and hand-written JSON fixtures | rendering and interaction | They catch UI regressions, **not** API-contract drift. Fixtures carry `course-*` ids and `course_key`, so a rename means fixture edits. |
| bench/shots_review.py, shots_sme_fixes.py, shots_tour.py (Playwright screenshots), check_paths_browser.py | manual, against a running server on AVC (`CAT = "avc"`) | visual review | No assertions. Useful for a before/after visual diff only. |

**Verdict.** The fast behavioural layer (the test_golden_versions `studio` fixture → scores/reset/approve/property_lists, plus minicat → one_rule_runs) is the regression net for the refactor. It drives the real CLI and HTTP. It is fully Course-shaped, so it should be parametrized or cloned for a LearningProgram catalog. The slow e2e and demo-root API tests mostly skip without `.data/root-demo`. Web tests mock fetch and need fixture updates for the renames.

---

## 5. Storage migration

### Per-catalog paths (`gds/layout.py`, `manifest.py`, plus hand-built paths)

| path today | moves under a class folder? |
|---|---|
| `<cat>/golden-dataset-studio/rules/<rule_id>/vNNNN.json` (`layout.py:21-22`, `context.py:119`) | **yes** |
| `<cat>/golden-dataset-studio/rulesets/vNNNN.json` (`:25-26`) | **yes** |
| `<cat>/golden-dataset-studio/annotations.jsonl` (`:29-30`) | **yes** |
| `<cat>/golden-dataset-studio/agent-runs/{live.json, goals.json, last.json, <run_id>/…}` (`:33-39`; `agent_runs.py:8-17`) | **yes** |
| `<cat>/golden-dataset-studio/publish.json` publish lock (`publishing.py:35`, built by hand) | **yes** |
| `<cat>/<crawl>/golden-dataset-studio/extractions/<rs-NNNN>/{extraction.json, page_labels, occurrences, matches, signals .parquet}` (`:79-85,110`) | **yes** |
| `<cat>/<crawl>/golden-dataset-studio/golden/ruleset-vN/{publication.json, lineage.parquet, golden.parquet}` (`:88-89`) | **yes** |
| `<cat>/<crawl>/golden-dataset-studio/scores/{pending.json, sc-NNNN/{score.json, values.parquet}}` (`:92-103`) | **yes** |
| `<cat>/<crawl>/golden-dataset-studio/extract-outputs/<id>/` (`:106-108`) | Optional: this is xtra's whole output and is class-independent. It could stay shared, with the class filter applied when scoring. |
| `<cat>/<crawl>/golden-dataset-studio/pages.parquet`, `assets/` (`:64-76`) | no (class-independent) |
| `<cat>/<crawl>/{crawl.json, pages/}` | no (xtra-cli, read-only) |
| root `golden-dataset-studio/{manifest.json, profiles.json, agent-slots.json, agent-runs-recent.json}` | No move, but the **manifest schema** needs a class level: `catalogs[].rulesets`, `rule_versions`, `annotations`, `crawls[].extractions`, `golden`, `extract_outputs` (`manifest.py:7-14`; `scores.py:~276`). |
| Golden root (`xtra-golden-sets` container, built by hand in `golden.py:12-15,265,284`, `scores.py:~205`): `<cat>/<crawl>/<stem>/<stem>.{json,html}` (latest) and `catalogs/<cat>/versions/ruleset-vN/{rule-matched,human-reviewed}/<cat>/<crawl>/<stem>/<stem>.json` | **yes.** Otherwise Course and Program files for the same program-page stem collide. xtra's `--baseline-uri` must point at a per-class tree. |

Also route through layout: `routes_files.py:29,39,113-138` (storage-files view regexes), `sync.py:7,72-87` (sync prefixes) and `cli.py:319` (`--studio-only`).

### Data keyed by course_key (needs a migration rewrite, or read-compat)
- `extractions/*/occurrences.parquet`: column `course_key` (`model.py:71-75`). This also flows into `matches` through a join view (`query.py:117`).
- `annotations.jsonl`: `target.course_key` on verdicts and comments. This is the re-attach key when occurrence keys change (`review.py:16,485-578`; check FK at `check.py:141-144`). The log is append-only, so read both names, or rewrite it once during migration.
- `rulesets/vNNNN.json`: `settings.course_key_rule` (`rulesets.py:41`).
- `golden/ruleset-vN/publication.json`: `skipped_no_course_key`, `golden_record_id_collisions[].course_key`.
- `golden_record_id` values are course_key strings, sometimes `~n`. They are in lineage.parquet, golden.parquet, values.parquet and the golden JSON files. Values only, so no rename is needed.
- `agent-runs/<id>/report.json` and rows: `course` / `course_key` keys (`report.py`, `agent_runs.py:484`).
- `extractions/*/occurrences.parquet` and others are immutable and cached client-side by content (`~/.cache/golden-datasets`). Rewriting them changes their bytes, so the cache would need invalidating.

### Deployed root and size
- README (`golden-dataset-studio/README.md:19-23`): roots are a folder or `azure://https://ceteststorage.blob.core.windows.net/xtra-cli-output/<prefix>`; the golden root on Azure is `xtra-golden-sets` (`README.md:110`). So the deployed root is Azure (`ceteststorage`).
- `~/review-ui-v3-data` (5.2 GB) is a mirror of **xtra-cli crawls only**. It has no `golden-dataset-studio/` folders: AVC 3.8 GB, CCSF 438 MB, Marshall 408 MB, UALR 309 MB, WVU 270 MB.
- The best local proxy is the Studio's immutable-file cache of the deployed root: `~/.cache/golden-datasets/8abf1653948e362f/`. Its Studio files (rules, rulesets, extraction parquet, golden, scores) are about **70 MB across 6 catalogs**: AVC 9, Marshall 13, UALR 12, WVU 26, CCSF 7, training-uark 3. Mutable files such as annotations.jsonl and manifest are not cached and are small. Studio data to migrate is therefore in the **tens to low hundreds of MB, about 70 MB as cached**, plus the golden-root trees (`<stem>.html` copies of ~3 MB each at the latest location are the bulk there). Pages and assets don't move. I did not query Azure directly.
