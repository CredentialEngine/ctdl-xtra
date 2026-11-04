# S — Spec: fixes from Jared's review session (sme-fixes)

Written 2026-11-04 from [`01-questions.md`](01-questions.md) and Eric's five passes of answers (`answers-pass*.md`).
Eric said "ready to build" with some questions still open; **every open question takes its default** (listed in §0).
Pictures: [`pass3.html`](pass3.html) / `img/mock-p3-*.png` (proposals) and `img/q*.png` (today, real).

The build lands on branch `golden-dataset-studio-sme-fixes`, PR into `golden-dataset-studio`. Never describe how or
where the Studio is deployed in code, docs, commits or the PR.

## 0. Decisions taken by default (open when Eric said "build")

Q1.1 highlight bar · Q1.4 golden uses the reviewer's answer · Q1.5 ask Jared (no code) · Q8.5 Esc goes up a level ·
Q8.6 fix locator naming in the first-pass prompt · Q10.5 six duration rules → one · Q10.8 per-element list review ·
Q10.9 labels "found"/"right" with recall/precision in tooltips · Q10.10 extra + "Where it's wrong" for every column ·
Q11.1 Watch becomes the report · Q9.1 lock · Q12.1–12.3 as drawn.

## 1. Highlighting on the page (item 1)

Today a highlight means only "this is the right answer", and a highlight equal to the found value is silently
dropped (`web/src/rules/RulesTab.tsx:250`). Replace both:

- After any text selection in the page pane (property rules), show a compact dark bar just above the selection with
  three buttons: **💬** (comment on this text), **✓ In answer**, **✕ Not in answer**. Each has an informative tooltip.
  No other new UI. Esc or clicking elsewhere dismisses it. Picture: `img/mock-p3-q1-1.png`.
- **✓ In answer** adds the selection as an `in` segment of the row's expected answer (today's behaviour, now explicit).
  **✕ Not in answer** adds it as an `out` segment and marks the row ✗. Segments are drawn on the page: `in` = green
  outline, `out` = red dashed outline with a light red fill. Several segments may be combined.
- **💬** opens the existing comment box, anchored to that text (`anchor {css_path, char_start, char_end, text}`); the
  comment shows a small numbered bubble at the text on the page.
- A selection equal to the found value is never dropped: the bar appears like for any other selection.
- Annotation schema: `expected.segments[]` gains `polarity: "in" | "out"` (missing = `in`, so old data reads the
  same); a comment annotation gains optional `anchor`. Update `query.py` `ANNOTATION_COLUMNS` and every reader.
- The browser `::selection` colour stops reusing the "saved answer" green (`render.py:53`): use a neutral blue.
- For a **list-of-objects** rule (§5) the bar shows the object's field names instead of In / Not in (§5.3).

## 2. Deep links (item 2)

- Selecting a row (click, Tab, keyboard) writes `?row=<occurrence key>` to the address bar with `history.replace`.
  Opening that URL selects and scrolls to the row (works already server-side, `routes_review.py:362,402`). Rows only:
  no comment ids. No Copy-link button.

## 3. Course blocks: several courses on one page (items 3 = 8)

- **Titles from the rule.** Replace the fixed "One course per course page" (`routes_review.py:33`, `RuleHead.tsx:13`)
  with a title derived from the locator definition: with `repeat` → "Course blocks: every `<repeat selector>` on the
  page"; without → "Whole page is one course". Same for the page rule's subtitle ("Which pages are a single course's
  own page" → derived: "Pages with courses" when the locator repeats). Show `repeat_filter.selector` in the
  definition view (`RuleHead.tsx:29`).
- **First-pass prompt** (the prompt that writes a catalog's first rules, `prompt.py`): name and describe locators
  from what they do (one per page vs many per page) instead of the AVC wording.
- **One row per page** for a locator that repeats: the row is the page (subject code + page title + "N courses");
  its course blocks are nested inside, each with its own ✓ ✕; "Add a course this rule missed" stays at the end.
  The page row has a ✓ that accepts all its courses at once. Locators without `repeat` keep one row per course.
- **Keys:** Tab / Shift+Tab move between courses inside the page; **Esc** goes back up to the page row; Tab at page
  level moves to the next page. Tooltips / the key strip say so.
- **On the page:** every found course is a box with a **border and a transparent fill**; only the current course is
  filled. A box's border turns green / red once its course is ✓ / ✗. No chips. Picture: `img/mock-p3-q8.png`.
- Signals: no change (they never fire falsely; `research/ccsf-courses.md`).

## 4. AI runs (items 4, 11, bonus)

- **Not responding:** if a run is `running` and no `note` from the agent has arrived **5 minutes after `sent_at`**,
  the bar reads "Claude isn't responding. No update in 5 minutes; it may have stopped." with a **Mark as ended**
  button (existing end action). Never mention K2 in the UI. Client-side only, from data the poll already returns
  (`research/k2-status.md`).
- **Prompt rule:** the agent's first action in a run is `golden-datasets run note` (`prompt.py`).
- **Watch → report (Q11.1):** when a watched run ends, the Watch panel shows the run's report (`summary` Markdown) on
  top with a **Compare vN → vN+1** button (when a ruleset was published), and the progress notes folded below.
  When you weren't watching, the bar says "Claude finished · **Read the report**" (replacing *Details*), opening the
  same view. Picture: `img/mock-q11-1.png`.
- **Lock (Q9.1):** `_Recent` (`review.py:59-75`) gets a `threading.Lock` around get/set/evict. Test with threads.

## 5. Estimated Duration as a list of objects (item 10)

### 5.1 Rule and extraction

- New property rule shape: a rule may declare `"profile": {"fields": {"<ctdl field>": <sub-definition>, …},
  "key": "<ctdl field>"}` on top of a `multiple` split: each split item (e.g. each duration line) becomes one object;
  each field is extracted from the item with its own sub-definition (selector / regex / labelled, like any rule).
  Matches carry the object: `value` is a JSON object `{"ceterms:description": "...", "ceterms:timeRequired": "..."}`
  (stored as JSON text in `matches.value`, with per-field offsets in a new `fields` column or JSON).
- Values are **page words, unparsed** ("54.0 - 432.0"). **Keep whole text blocks** (no splitting at extraction).
- **Only `ceterms:estimatedDuration`** uses it now. The six rules (`course-estimated-duration` + its five children:
  description, exact/minimum/maximum duration, time required) become **one** rule `course-estimated-duration` with
  `profile.fields = {ceterms:description, ceterms:timeRequired}`, key `ceterms:description`. Exact / min / max are
  parsed at transformation, not in the Studio. `properties.csv` drops the five children for durations; nobody
  annotated them (verified), so nothing migrates. Credit Value stays as today (one value; its children stay).
- Conditions (prerequisite, corequisite, …) stay flat text. `prerequisite>description` keeps the **full** sentence
  ("Completion of ATH 100 and completion of or concurrent enrollment in ATH 103.") even when it repeats
  co-prerequisite text: put this in the rule-writing prompt guidance.

### 5.2 Review (per element)

- A list-of-objects row shows one sub-row per object (field values side by side, field names small) with ✓ ✕ each.
  One ✕ makes the row wrong. "+ Add a duration" adds an object by labeling text on the page (§5.3). Picture:
  `img/mock-p3-q10-list.png`.
- Annotations: per-element verdicts reuse the list-item mechanism (`target.item`, `value_index`); an added object is
  an `expected.objects[]` entry `{fields: {<ctdl field>: {text, css_path, char_start, char_end}}}`.

### 5.3 Labeling

- For a list-of-objects rule the highlight bar shows the rule's field names (`description`, `timeRequired`) and 💬.
  Picking a field labels the selection as that field of the object being added; when all key fields are labeled the
  object is saved.

### 5.4 Golden dataset format

- One golden field per object: `{"ctdl_property": "ceterms:estimatedDuration", "value": {"ceterms:description":
  "Total Course In-Class (Contact) Hours", "ceterms:timeRequired": "54.0 - 432.0"}, "location": {...per field...},
  approval...}`. Several fields with the same property form the list (the existing multi-value convention).

## 6. "Not on the page" (item 12)

- **Three rule outcomes per course**, shown in the row's value text:
  - a value;
  - **"Not on the page (rule's claim)"**: new match status `absent`. A rule claims absence only through an explicit
    check in its definition, `absent_if: {within: <selector, relative to the record>, missing: <selector or label>}`:
    the container was found and the property's element/label is not in it. Draw the checked container dashed
    purple on the page ("rule looked here").
  - **"Nothing found · the rule made no claim; check the page"**: today's `no_match` / `empty` (wording change).
- Review: only ✓ ✕. ✓ on an `absent` row agrees with the claim. **✕ reveals a small "Why wrong?" flag set**; for now
  one flag, **Not on the page** (tooltip: "This course's page doesn't state this property anywhere."). Saved as
  `reasons: ["not_on_page"]` on the verdict annotation. ✓ on a "Nothing found" row means the reviewer checked: not on
  the page. Picture: `img/mock-p3-q12.png`.
- Golden dataset: an absent property is an explicit field `{"ctdl_property": ..., "value": null, "absent": true}`.
  It is written when: the rule claims absent and is ✓/approved, or a reviewer ✓'d a "Nothing found" row, or a
  reviewer ✗'d with reason `not_on_page`.
- The rule-writing prompt teaches `absent_if` (claim only after seeing pages where the property is truly missing).

## 7. Golden dataset uses the reviewer's answer (Q1.4)

- `golden.py` publishes, per row: the reviewer's expected answer when the row's latest verdict is ✗ with an expected
  value (approval `human`, `approved_by` the reviewer); else the rule's value (as today). The expected text is the
  `in` segments joined in page order, minus `out` segments. Applies to found rows and to no-value rows (today those
  are skipped, `golden.py:156`). Example: AVC Description DA107A (`img/mock-p3-q1-4.png`).

## 8. The xtra score

### 8.1 What it is (put this in the PR description, with the examples)

`xtra score extraction match` compares an xtra extract output (records) with a golden dataset, page by page and
entity by entity. Units:
- a **flat value** (a string or number) for ordinary properties;
- a **pair** (one object) for list-of-objects properties (`estimatedDuration`);
- an **absent** marker when the golden dataset says the property isn't on the page.

Matching, per entity and property: exact matches first (normalized text, numbers by value), then the rest greedily
by similarity (rapidfuzz ratio, best first), one to one. For objects, pairing uses the **key field**
(`ceterms:description`) and an object is **exact** only if every field is exactly equal.

Outcomes per unit: **match** (exact); **partial** (paired, similarity ≥ 0.8, not exact; for an object: all fields
≥ 0.8); **wrong** (paired below 0.8, or an object with a field below 0.8); **missing** (golden unit, no partner);
**extra** (extracted unit with no partner, for a property the golden entity covers, including an absent one);
**unsure** (golden says absent and the record has no key for the property at all: the extractor made no claim).
An extracted `null` for a property is the extractor's claim "not on the page": against golden absent it's a match;
against a golden value it's missing.

Numbers: `found` (recall) = match ÷ golden units; `right` (precision) = match ÷ extracted units for covered
properties; `exact_match_rate` stays = match ÷ golden units (= found) for continuity; per property and overall,
micro-averaged (summed over all entities). Also `entities_exact` = entities whose every covered unit matched ÷
entities. Worked examples (ACCT199, `img/mock-p3-q10-4.png`, `img/mock-p3-q10-agg.png`): rule B 4/4 found, 4/4 right;
rule A (extra "Minimum Credit Units 1.0") found 4/4, right 4/5; rule C (two times swapped) found 2/4, right 2/4.

### 8.2 CLI changes

- The report (schema bumped to `xtra-extraction-match-report-2`) adds `extras` (count + outliers), `unsure`,
  `found`, `right`, `entities_exact`, and per property `{golden, extracted, match, partial, wrong, missing, extra,
  unsure, found, right}`. The terminal output prints found / right per property.
- `extracted_values` keeps dict items for list-of-objects properties (today dicts are reduced to `ceterms:name`,
  `score_extraction_match.py:116-129`), and reads `null` as the absent claim.
- Fix the ValueProfile keys it reads (`ceterms:value`/`ceterms:minValue` → also `schema:value`, `schema:minValue`,
  `schema:maxValue`) only if trivially safe; otherwise leave a note.
- xtra-cli's extract output writes `ceterms:estimatedDuration` as a list of `{ceterms:description,
  ceterms:timeRequired}` objects (page words), where it extracts lecture/lab hours today (`lib/inventory.py`,
  `lib/mapping.py`).
- Tests for every outcome, the examples above, and backward compatibility (old golden files without objects/absent
  score exactly as before except the new extra/right numbers).

### 8.3 When it runs (verify in code and say so in the PR)

Automatically after a golden dataset is published and when a new extract output appears (Evals spec), from the
Evals tab, and from the CLI (`golden-datasets score`, `xtra score extraction match`).

### 8.4 Evals tab

- Each column's bar gains an **extra** segment (striped) and an **unsure** segment; the row shows **found** and
  **right** (tooltips: recall / precision, with the formula) and, for list properties, **courses exact**.
- **Where it's wrong:** under a column (and for all columns), every non-match unit grouped by reason, biggest group
  first: outcome × field (for objects) × a grouping key (the description label for durations; value shape
  `strata.shape`; word-diff kind: cut short / extra text / different; course subject). Each group shows count, one
  example (golden → extracted), and links to the Rules tab filtered to those courses. Picture:
  `img/mock-p3-q10-agg.png`.
- The values table (`values.parquet`) gains `unit` (value | object | absent), `field` (for object fields that
  differ), `reason` columns.

## 9. Defaults (items 5, 6)

- Rules tab sample defaults to **Autostratify** (`RulesTab.tsx:73`); Compare keeps Shuffle; the Sample drawer does not
  open by itself.
- "Annotated by" defaults to **Anyone** (`logic.ts:266-269`); `?by=` is written only when a person is picked.

## 10. Done means

- `make check` passes (ruff, pytest, web typecheck/tests/build) and xtra-cli's tests pass.
- New tests for: highlight bar segments (in/out), deep-link URL writing, nested locator rows + keys, not-responding
  timer, Watch report, `_Recent` lock under threads, profile rule extraction, per-element review, golden objects +
  absent + reviewer answer, every scorer outcome, the CLI report, Evals extra/unsure/where-wrong.
- Screenshots of every new or changed behaviour, from a local server on the local mirror, in `screens/`.

## 11. Evals row statuses (Eric, 2026-11-04 13:24, `answers-pass6.md`)

Replace the free-text reasons on unscored Evals rows (`EvalsTab.tsx` `reasonFor`) with two explicit facts per row:
- **Candidates** (values in xtra's extract output): "N candidates" · "No candidates: xtra doesn't extract this
  property" · "No candidates in this output".
- **Golden values** (Human-reviewed side; "rule-matched values" on the Rule-matched side): "N golden values" · "No
  golden values: no Studio rule yet" · "…: the Studio rule needs work" · "…: the Studio rule is in review" · "Not read
  from the page" · "Studio only: no CTDL property".
A row is scored only when it has both; otherwise "Not scored" plus the two facts as compact labelled chips with
tooltips defining each term. The same terms are used in tooltips and "Where it's wrong".
