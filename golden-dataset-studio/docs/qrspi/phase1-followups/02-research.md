# R — Research: Credit Value's single value, Reset rule, and correcting a duration

The QRSPI R step. These are facts the spec rests on, gathered after the first pass of answers in
[`01-questions.md`](01-questions.md). There is no design here.

- **Sources:**
  - The code on `golden-dataset-studio-value-reset-duration` (`a0e93fc`).
  - The live Studio root `zz-scratch-review-ui-v3` on Azure, read 2026-11-05 with `golden-datasets sql`,
    `rule list` and `rule show`.
  - The Phase 1 tab as read 2026-11-05.
- **Longer code notes:** [`research/code-reset.md`](research/code-reset.md) and
  [`research/code-duration.md`](research/code-duration.md). This file keeps what the spec needs and checks the
  claims it uses.
- Paths are relative to `golden-dataset-studio/` unless they start with `xtra-cli/`. Anything inferred rather than
  read or run says **inferred**.

---

## A. `ceterms:creditValue>schema:value`

### A.1 What the sheet sync does

- **A dry run of `properties.from_sheet` plus `merge`** against the live xlsx, with nothing written:
  - **Adds** one row: `course-credit-value-value`, path `ceterms:creditValue>schema:value`, parent
    `ceterms:creditValue`, profile `ceterms:ValueProfile`, Single, sheet row 18, sample `3.0`. It is not required.
  - **Changes** one row: Credit Value's sample, from `3.0` to empty.
  - **Renumbers** every later row's `sheet_row` by one. Nothing is removed or renamed.
- **The name comes out as "Value".**
  - `from_sheet` takes column D as the name when no other row uses it (`properties.py`, the `label` branch in
    `from_sheet`).
  - Nothing in sync makes "Credit Unit Value" (E1). It needs either column D changed on the sheet, or a name
    override in sync.
  - A rename later goes through `merge`'s `accept_renames` (`properties.py`, `merge`).
- **Rule ids come from paths** (`rule_id_for`): `course-credit-value-value`.
- **`properties apply` publishes one ruleset version per catalog**, adding a `rule_type: none` draft for each property
  the catalog lacks, then extracts (`properties.apply`, `missing_rules`). No values change.
- **Tests that count the property list** move from 36 to 37:
  - `tests/test_properties.py:25`, `:61`
  - `tests/test_property_lists.py:35`, `:51`, `:106`, `:110`
  - `tests/test_scores.py:244`

### A.2 What the catalogs extract for Credit Value today (live, latest extraction)

| Catalog | Commonest Credit Value texts (count) | Min / Max rules read |
|---|---|---|
| Marshall | `3 Credit hours` (3,566), `1-4 Credit hours` (1,356), `1 Credit hour` (421), `1-18 Credit hours` (220) | the parent (`input: rule`) |
| AVC | `3.0 Units` (508), `1.0 Units` (150), `0.0 Units` (101); ACCT199 `1.0 - 8.0 Units` | the page |
| CCSF | `3.0` (993), `1.0` (306), `0.0` (195) | the parent |
| UALR | `Three credit hours` (2,074), `One credit hours` (199), `One, two, or three credit hours` (105), `Credits Hours: 3` (69) | the parent |
| WVU | `3 Hours.` (10,239), `1-6 Hours.` (3,449), `1-3 Hours.` (2,181), `1 Hour.` (1,631) | the parent |

- **Single values are the large majority everywhere.** Marshall's Min and Max Value rules fill only 2,008 of 6,692
  courses. WVU's fill 7,685 of 22,023. UALR's fill 195 of 3,130. The rest have no home until Value exists.
- **UALR writes numbers as words.** The Generate rules prompt says "no numbers from words (`Three`, not 3). That's
  transformation, later." (`prompt.py`, `REQUISITE_WORDS`). Under that rule, UALR's Value is `Three`.
- **Credit Value has no rule status of approved** in any catalog. It is `needs work` in AVC and Marshall (Jared's ✕s)
  and `in review` elsewhere (`rule list`).
- **When a parent finds nothing, a child reading it finds nothing too** (`engine.py:431-432`). So if Credit Value
  becomes `none`, the Min / Max Value rules of CCSF, Marshall, UALR and WVU go empty until they read the page
  themselves.

### A.3 Jared's reviews (live)

| Catalog | Property | Verdicts | What they say |
|---|---|---|---|
| AVC | Credit Value | ✕ ×1 (ACCT199) | "There should be no values for this property … values for the properties associated with the Value Profile" |
| AVC | Min / Max Value, Unit Type | ✓ ×1 each (ACCT199: `1.0`, `8.0`, `Units`) | a range: still right under row 18 |
| Marshall | Credit Value | ✕ ×4 (BMS600, 605, 607, 609) | "There should be no value for this property" |
| Marshall | Max Value | ✕ ×4, no answer, notes "The correct value is 7." / 5 / 3 / 6 | single credits: Value's under row 18 (A5: reset these) |
| Marshall | Unit Type | ✓ ×4 (`Credit hours`) | still right |

None of the ✕s carries an `expected` answer: the right values are in the notes.

### A.4 The Generate rules prompt and scoring

- **Two lines in the prompt teach the parent-as-input pattern on credits** (`prompt.py:542-553`):
  - the `regex` row: "Credit Value `1-4 Credit hours`, `-\s*(\d+)` → `4`";
  - the `input: rule` row: "Credit Unit Max Value reads Credit Value's `1-4 Credit hours`".
- **Evals score a column only if xtra's extract emits the property** (`scores.py:612-627`, `xtra_terms`,
  `only_emitted`). Nothing in the Studio needs to change for A4: Value is scored once xtra emits
  `ceterms:creditValue>schema:value`.
- **xtra-cli's scorer already treats a `schema:value` as both min and max** (`xtra-cli/src/implementations/
  score_extraction_match.py:124-136`). xtra-cli is out of scope.

---

## B. Reset rule

### B.1 Where approval lives, and what a reset has to reach

- **One append-only log per catalog**: `<catalog>/golden-dataset-studio/annotations.jsonl` (`layout.py:29`).
  - Events: `verdict`, `comment`, `approve`, `reopen` (`log.py:18`). Readers read it from a byte offset
    (`log.py:85-97`).
  - Nothing is ever edited: an edit is a new event that `supersedes` the old one (`log.py:1-8`).
- **Rule approval:** the latest `approve` / `reopen` on the rule's current version (`review.py:550-558`).
- **Values:** every reader builds row states from `Review.live`, the events no later event superseded
  (`review.py:300-312`). These readers all go through `Review`:
  - the Rules tab,
  - the golden files (`golden.plan`, `golden_answers.fields`),
  - `rule publish`'s guard: `newly_wrong` in `scorecard.py:189`, read by `loop.py:566-570`.
- **One reader doesn't:** `human_reviewed_counts` (`review.py:853-888`) builds its own superseded set from the raw
  logs. It drives the home-page counts and the Rules tab's sort. A new event type has to be handled there too.
- **`append_many`** writes several events in one append (`log.py:112-117`). Today only the v2 import calls it.
- **`add_annotation`** (`routes_review.py:649-757`) takes one event per POST.
  - It republishes a page only after a `verdict` on a match (`:733-738`).
  - It publishes a column only after an `approve` (`:740-753`).
  - A `reopen` changes neither.

### B.2 The golden and silver datasets: "columns only grow"

- **Each version of a catalog's dataset is two trees**, kept side by side (`golden.py:1-40`, `trees` at `:308-311`):
  - **The silver dataset** (`rule-matched/`). Every value of every published column.
  - **The golden dataset** (`human-reviewed/`). Only the `approval: human` values, in any column, published or not.
  - The Approve dialog uses these two names (`web/src/rules/ApproveDialog.tsx:1-4`).
- **A reset reaches both.**
  - The ✓s leave the golden dataset once each page is rewritten.
  - The rule's values leave the silver dataset only if the column is withdrawn (below).

- **Approving a rule publishes its column** into the golden dataset of its ruleset (`golden.py:579-610`).
- **A published column stays published.** `publish` unions the chosen columns with the version's existing
  `properties` and with every earlier version's (`golden.py:484-485`, `inherited_columns` at `:335-345`). This was a
  decision: "Can a published column be withdrawn? Not for now. Columns only grow." (`docs/qrspi/evals/03-spec.md:13`).
- **In a published column, a value nobody reviewed goes in as `approval: rule`** (`golden_answers.py`, the
  `column` argument; `golden.py:160-170`).
  - Inferred: after a Reopen, `rule_ok` has no `approved_by`, but the values are still written.
- **So B6's answer ("left out of the golden dataset") needs the column withdrawn from the silver dataset (E4: yes).** Taking the ✓s away isn't
  enough. This reverses the Evals spec's "columns only grow" for this one case.
- **Live:** Subject Webpage is approved in CCSF, Marshall, UALR and WVU, so its column is in those catalogs'
  published golden datasets. That follows from the code path above; the publication files weren't opened.

### B.3 Marshall's Subject Webpage (live), the first real use

- **69 values human-reviewed**: ✓ by Seth (56, 23 Oct) and Jared (13, 22 Oct). The rule is approved.
- **6 ✕ from Jared on 5 Nov**, on five courses (BMS600, 605, 607, 609, 612), with no answer. For example: "There should be no value for this
  property. When a resource is in a clearly defined catalog, use the property ceterms:inCatalog for the page URL."
- **In Catalog:** 5 ✕ on 4 courses, each giving `https://catalog.marshall.edu/graduate/courses-az/bms/` in the note.
- **A Reset rule on Subject Webpage would reach:**
  - the 69 values `rule list` still counts as human-reviewed,
  - the rule's approval,
  - the six ✕s too, since they carry no answer. Inferred: B3 resets ✓ and ✕-with-answer, so ✕s with no answer stay.
- **Other catalogs' Subject Webpage, human-reviewed (`rule list`):** CCSF 69, WVU 84, UALR 14, AVC 14. Every ✓ is
  from 20–23 Oct.

### B.4 The UI around Approve rule

- **The rule header**, `RuleHead.tsx:79-93`:
  - **Approve rule** when not approved;
  - "Approved by X · date · **Reopen**" when approved. Reopen is a link button, titled "Undo the approval (a reopen
    event)" (`:84`).
- **Approve asks first** through `ApproveDialog`: a preview of what the column adds, then confirm
  (`RulesTab.tsx:514-533`, `:633`). Reopen doesn't ask.
- **The tour:** the `approve` step describes these buttons (`web/src/tour/steps.tsx`, the `approve` step; see
  research/code-reset.md §5.7).
- **No test exercises `reopen`.** Approve's tests are in `tests/test_approve_publishes.py`, `test_golden.py` and
  `test_golden_versions.py`, and `web/src/rules/RulesTab.test.tsx:290-320`.

---

## C. Correcting a found duration

### C.1 What exists

- **Estimated Duration is one list-of-objects rule.**
  - Its sub-values are `ceterms:description` and `ceterms:timeRequired`, keyed on description
    (`profiles_rule.py:25-31`).
  - The values are page words (`{"ceterms:description": "Total Course In-Class (Contact) Hours",
    "ceterms:timeRequired": "54.0 - 432.0"}`), with a location per sub-value.
- **Per found duration, ✓ or ✕** (`ProfileItems.tsx:34-39`, `logic.ts:296-300`). The ✕ carries no answer, and the
  duration is left out of the golden dataset (`golden_answers.py:111-116`).
- **+ Add a duration** (or H):
  - While adding, a selection on the page offers one button per sub-value (`fieldBar`, `RulesTab.tsx:493-505`).
  - It saves as a `missing` item verdict whose `expected.objects[0].fields` holds each sub-value's text and location
    (`claims.ts:67-74`).
  - The golden dataset publishes it as `approval: human` (`golden_answers.py:128-137`).
- **The golden dataset already does what a correction needs:** a ✕'d found duration is dropped, and an added
  duration is published. **A correction is those two together**, so no new stored shape is needed for C2's default.
  - Today they take two events and two separate actions. `add_annotation` takes one event per POST (B.1).
- **Outside "add", a selection does nothing** for list rules: the flat bar is off (`RulesTab.tsx:287`) and `fieldBar`
  needs an open add (`:495`).
- **Added durations show with no buttons** (`ProfileItems.tsx:42-48`). Only `objects[0]` of a `missing` event is read
  (`profiles_rule.py:144-148`).
- **Keys 1 / 2 do nothing on list rules** (`RulesTab.tsx:559`).
- **The comment button isn't on the sub-value bar**, though sme-fixes §5.3 says it is.
- **Exact, minimum and maximum duration aren't sub-values** (`profiles_rule.py:30-35`).
  - The 2026-11-05 sheet lists them as Include (rows 39–41, samples `6 months`, `3 months`, `9 months`).
  - The prompt says they are "parsed from timeRequired at transformation" (`prompt.py`, `REQUISITE_WORDS`).
  - W14 says they are the overall span. This is E2.

### C.2 Live

- **AVC ACCT199, 2026-11-05 18:32Z:** Jared ✕'d Estimated Duration's whole value, with no note. The rule had found:
  - In-Class `54.0 - 432.0`
  - Out-of-Class `0.0 - 0.0`
  - Lecture `0.0`
  - Lab `432.0`
- **That ✕ is on the row, not on one duration.** Which duration he meant isn't recorded.
- **No catalog has a ✓ on any duration yet.**

| Catalog | Estimated Duration rule | Courses with durations |
|---|---|---|
| AVC | v3 | 1,062 / 1,062 |
| CCSF | v3 | 1,927 / 1,927 |
| UALR | v3 | 623 / 3,130 |
| WVU | v3 | 322 / 22,023 |
| Marshall | v1 | 0 |

### C.3 Tests

- **Web:**
  - `web/src/rules/ProfileItems.test.tsx` (`:100`, `:115`, `:131`);
  - `HighlightBar.test.tsx`;
  - the list and bar tests in `RulesTab.test.tsx`.
  - Nothing tests the sub-value bar.
- **Python:**
  - `tests/test_profiles_rule.py` (`:158`, `:205`, `:232`, `:350`): rule, review and golden behaviour of objects;
  - `tests/test_score_units.py`.

---

## Settled after research (01-questions.md, Part E)

- **E1:** the new property is named **Credit Unit Value**.
- **E2:** exact, minimum and maximum duration **stay out** for now.
- **E3:** one spec, built A, C, B.
- **E4:** a reset **withdraws the property's column** from that catalog's silver dataset, until the rule is approved
  again. Columns still only grow everywhere else.
