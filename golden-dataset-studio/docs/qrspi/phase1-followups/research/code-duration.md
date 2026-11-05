# Research: Estimated Duration review UI ("select correct values from the page")

Facts only, no design. Paths are relative to `golden-dataset-studio/` in the worktree. Line numbers are as of the
branch `golden-dataset-studio-value-reset-duration` (HEAD `a0e93fc`). Task source:
`docs/qrspi/phase1-followups/prompt.md:18` ("third task: Update UI for Estimated Duration to enable selecting correct
values from the page.").

---

## 1. Flat (scalar) property: how an expert picks the right value from the page

**Highlight → bar.**
- The page pane listens for `mouseup` in the page iframe and turns the selection into a `CapturedSelection`
  `{text, css_path, char_start, char_end, prefix, suffix, doc_start?, doc_end?}` (`web/src/pagepane/dom.ts:4-14`,
  `captureSelection` `:174-177`).
- If the caller passed `barActions`, the pane shows the `HighlightBar` above the selection instead of calling
  `onSelection` (`web/src/pagepane/PagePane.tsx:226-240`). With `captureFirst` it also hands the selection to
  `onSelection` first (`:235-238`). With no actions and `captureSelection` true, it calls `onSelection` directly
  (`:242-244`).
- `HighlightBar` itself is generic: it renders the `BarAction[]` it is given and runs `a.run(sel)` on click
  (`web/src/pagepane/HighlightBar.tsx:8-19, 48-56`). Its header comment already says "a list-of-objects rule has its
  field names (§5.3)" (`:3`).

**Which actions a flat property row gets** (`web/src/rules/RulesTab.tsx:286-301`):
- `comment` (bubble, `keepOpen`), `in` ("✓ In answer"), `out` ("✕ Not in answer").
- `barActions` is `null` when `listRule` is true (`:287`). So list rules (and Estimated Duration) never get these
  three actions.
- `in` / `out` call `onAnswer({...c, polarity})` (`:291`), which opens or extends a ✗ draft with the capture as a
  piece (`:275-284`; `addCapture` merges overlapping pieces, `web/src/rules/logic.ts:155-158`). After ✗ is open,
  `captureFirst` makes a drag count as a piece at once (`RulesTab.tsx:285, :288-290`).

**What gets saved.**
- Enter or Save calls `saveRow(i, {draft})` (`RulesTab.tsx:391-412`, key handling `:543`), which builds the event with
  `verdictEvent` (`logic.ts:201-217`).
- The event is `{type: "verdict", verdict: "wrong", target: {kind: "match", rule_id, occurrence_key, page_stem},
  expected, reasons?, supersedes}`. `rowTarget` builds the target (`logic.ts:194-198`).
- `expected` comes from `expectedOf` (`logic.ts:179-189`):
  - one piece: `{text, css_path, char_start, char_end, quote: {prefix, exact, suffix}, located_by: "highlight in the
    Studio"}` (`located`, `:160-161`);
  - several pieces, or only `out` pieces: `text` is the `in` texts joined by line breaks, and `segments[]` holds each
    piece with its `polarity`.
- A comment pinned with the bubble is saved as a second `comment` event with an `anchor` (`logic.ts:221-225`,
  `RulesTab.tsx:401-403`).
- Type: `Expected` in `web/src/api/types.ts:78-88`.

**API route.**
- `api.annotate` → `POST /api/catalogs/{catalog}/annotations` (`web/src/api/client.ts:59-62`).
- Server: `add_annotation` (`src/golden_datasets/server/routes_review.py:649-757`).
  - It fills the target from the current extraction: `value_seen`, `value_index`, `course_key`, `page_stem`
    (`:666-693`).
  - It stores `expected` through `profiles_rule.with_object_text` (`:706`), which is a no-op unless
    `expected.objects` is set.
  - It validates the event, then `log.append(full)` (`:729`).
  - For a verdict on a match, it rewrites the page's golden file with `golden.publish_page` (`:733-739`).

**Storage.**
- Append-only `<catalog>/golden-dataset-studio/annotations.jsonl` (`src/golden_datasets/log.py:1-7`, `append`
  `:107`).
- Golden page JSON: `[{golden_record_id, approval, fields: [{ctdl_property, property, value, source_url, location,
  approval, approved_by, approved_at}]}]` (`src/golden_datasets/golden.py:18-19`).
- The reviewer's ✕ answer is published in place of the rule's value, but **only for non-list rules**: `if v … ==
  "wrong" and not is_list` (`src/golden_datasets/golden_answers.py:88-94`). The text comes from `answer_text`
  (`:34-60`) and the location from `_location` (`:63-67`).

## 2. Estimated Duration (list of DurationProfile objects) today

### Backend shape of the rule
- `PROFILES = {"ceterms:estimatedDuration": {"fields": ["ceterms:description", "ceterms:timeRequired"], "key":
  "ceterms:description"}}` (`src/golden_datasets/profiles_rule.py:30-31`). **Only two sub-values are fields.**
- `FOLDED_CHILDREN` lists all five children (description, exact / minimum / maximum duration, timeRequired) as no
  longer rules (`:33-35`).
- `SKIP_PATHS` skips the five `ceterms:estimatedDuration>…` sheet rows (`src/golden_datasets/properties.py:51-55`).
- `properties.csv` marks the five rows `removed` (`src/golden_datasets/properties.csv:80-84`).
- Spec: "Exact / min / max are parsed at transformation, not in the Studio" (`docs/qrspi/sme-fixes/03-spec.md` §5.1;
  also in the fold draft's `why`, `profiles_rule.py:202-204`).
- `run` makes one match per split item. `value` is the canonical JSON object, and `fields` is the JSON of each
  field's `{text, css_path, char_start, char_end}` (`profiles_rule.py:78-100`).
- A review row's items carry `fields` with document-root paths (`src/golden_datasets/review.py:223-229`,
  `profiles_rule.item_fields` / `row_item` `:120-132`).

### Which component renders it
- `RulesTab` treats the rule as a list (`listRule = !!detail?.list`, `web/src/rules/RulesTab.tsx:199`) and a profile
  (`profileOf(detail.definition)`, `:200`; `web/src/rules/claims.ts:31-36`).
- Rows render through `ProfileItems` (`RulesTab.tsx:679-682`; component `web/src/rules/ProfileItems.tsx:12-72`).
  `noun` = the property label with "Estimated " removed, lower-cased → "duration" (`RulesTab.tsx:680`).
- Page pane highlights: each found object's fields are outlined where they are (`item-{i}-{field}`), labelled pieces
  of an object being added (`obj-{field}`, `obj-pending`), and added objects (`missing-item-{i}`)
  (`RulesTab.tsx:316-328`).
- Banner while adding: "Select a piece of the missing one … then label it" / "Which field is it? … pick its field
  under the row" (`RulesTab.tsx:587-589`).

### What the expert can do today
1. **✓ / ✕ per object** (not per field). `ProfileItems.tsx:34-39` (tooltips: "Correct: this duration is right, every
   field" / "Wrong: this duration shouldn't be here, or a field is wrong").
   - This saves `itemEvent` (`logic.ts:296-300`): `{verdict, target: {kind: "match", item: true, value_index},
     supersedes}`, with **no `expected`**.
   - The server sets `value_seen` to the object JSON (`routes_review.py:681-687`). Item state is keyed by normalized
     `value_seen` (`review.py:380-392`).
   - One ✕ makes the row wrong (`ProfileItems.tsx:18, 28`).
   - In the golden dataset a ✕'d object is **left out** (`golden_answers.py:111-116`).
2. **No ✓ / ✕ for the whole row.** For list rules the keyboard routes only H (select) and comment, so `1` / `2` do
   nothing (`RulesTab.tsx:559`).
3. **Add a missing object by labelling page text** ("+ Add a duration" or H → `startAddObject`, `RulesTab.tsx:477`,
   `:559`; button `ProfileItems.tsx:49`).
   - While `objAdd` is open on the row's page, the highlight bar shows **one button per field name** (`description`,
     `timeRequired`), built by `fieldBar` (`RulesTab.tsx:493-505`; passed as `barActions={barActions ?? fieldBar}`,
     `:746`).
   - Picking a field calls `labelField` (`claims.ts:56-58`). The object auto-saves once **every** field is labelled
     (`addComplete`, `claims.ts:61`; `RulesTab.tsx:501-502`). Save / Enter work once the **key** field is labelled
     (`addSavable`, `claims.ts:62`; `RulesTab.tsx:542`; `ProfileItems.tsx:65`).
   - The saved event is `objectEvent` (`claims.ts:67-74`): `{verdict: "missing", target: {kind: "match", item: true},
     expected: {text: "", css_path…: first labelled field, located_by: "labelled in the Studio", objects: [{fields:
     {<ctdl field>: {text, css_path, char_start, char_end}}}]}}`.
   - The server fills `expected.text` with the object's canonical JSON (`profiles_rule.with_object_text` `:141-148`;
     `routes_review.py:706`). Only `objects[0]` is used.
   - Added objects show dashed under the row, with the author's name and **no buttons** (`ProfileItems.tsx:42-48`).
   - Golden: added objects are published with `approval: human` (`golden_answers.py:128-137`).
   - There is also a fallback dark "label bar" under the row (`ProfileItems.tsx:57-63`). It shows only when
     `objAdd.pending` is set through `onAnswer` (`RulesTab.tsx:276`). *Inferred from code, not run:* in the browser
     the pane prefers `barActions` (`PagePane.tsx:231`), and `fieldBar` is non-null whenever `objAdd` is open on the
     row's page, so the in-row label bar would rarely appear. The unit test drives `onSelection` directly
     (`ProfileItems.test.tsx:138-143`).
   - Screenshot `04-label-a-new-duration.png` shows the dark highlight bar with `description · timeRequired`.

### What is missing or blocked (from the code)
- **No way to correct a sub-value of an object the rule found.**
  - ✕ on an object records no expected value (`logic.ts:296-300`), and its tooltip lumps "shouldn't be here" with "a
    field is wrong" (`ProfileItems.tsx:38`).
  - The only correction path is ✕ the object, then "+ Add a duration" and re-label **every** piece of a whole new
    object.
  - The flat ✓ In / ✕ Not in bar is disabled for list rules (`RulesTab.tsx:287`).
- **No typing.** `ProfileItems` has no input elements. Values come only from page selections.
- **Highlighting works only while adding a new object.** Outside `objAdd`, `selectAnswer` is false for list rules
  unless an item or object is being added (`RulesTab.tsx:273`), and `fieldBar` is null (`:495`). So a selection on
  the page does nothing (`PagePane.tsx:229-247`).
- **Only `description` and `timeRequired` can be labelled.** `exactDuration`, `minimumDuration` and `maximumDuration`
  have no field and no button (`profiles_rule.py:30-35`). The 2026-11-05 sheet still lists all five DurationProfile
  children as `Include`, with samples "6 months" / "3 months" / "9 months" / "54.0"
  (`docs/qrspi/phase1-followups/phase1-extraction-2026-11-05.csv` rows 38-42).
- **No comment bubble on the field bar.** Spec §5.3 says "the highlight bar shows the rule's field names
  (`description`, `timeRequired`) and 💬" (`03-spec.md` §5.3). `fieldBar` has field names only
  (`RulesTab.tsx:496-504`).
- **Spec vs code on auto-save.** Spec: saved "when all key fields are labeled" (§5.3). Code: auto-saves when *all*
  fields are labelled, and allows manual save once the key field is.
- **Added objects can't be removed or ✕'d in the row.** No buttons on `added-object` (`ProfileItems.tsx:42-48`).
  *Inferred:* a later ✓ with the same `value_seen` would drop it from `missing` (`review.py:394-396`), but there is no
  button for that.
- **Only one object per `missing` event.** `with_object_text` reads `objs[0]` only (`profiles_rule.py:144-148`).
- **Statements in docs that it is deferred or not built:**
  - `docs/qrspi/sme-fixes/01-questions.md:428`: "(Maybe a container rule plus field rules; the UI isn't built for
    that yet.)"
  - `docs/qrspi/sme-fixes/build-notes-profiles.md:147-152`: "the bar isn't built here… When the highlight bar lands,
    for a profile rule it should show the field names and call RulesTab's `labelObject(field)` (starting `objAdd`
    with `startAddObject()` first if none is open)."
    - The field-name bar has since landed (`RulesTab.tsx:493-505`).
    - The "starting `objAdd` … if none is open" part was **not** done: `fieldBar` returns null without `objAdd`
      (`:495`).
  - `build-notes-score.md:137-138`: "the research's parsing of times (`54.0` = `PT54H`, ranges as min/max) is not
    done: the spec keeps page words unparsed."

## 3. Other list-of-objects / profile properties

- **Only Estimated Duration is a list of objects.**
  - `PROFILES` has one entry (`profiles_rule.py:17, 30-31`).
  - Decided in `01-questions.md:419-427` (Q10.2b, "Pass 3 (Eric): yes: a list of objects for Estimated Duration
    only. **Decided.**") and `03-spec.md` §5.1.
- **Credit Value (`ceterms:ValueProfile`)** "stays as today (one value; its children stay)" (`03-spec.md` §5.1). Its
  children are separate flat rules, all `Include`, `multiple=false`: `course-credit-value-min-value`, `-max-value`,
  `-credit-unit-type` (`properties.csv:46-49`). They are reviewed with the flat bar.
- **ConditionProfiles** (prerequisite, corequisite, coPrerequisite, recommends, entryCondition): "stay flat text"
  (`03-spec.md` §5.1). Their `>description` / `>targetLearningOpportunity` / `>alternativeCondition` children are
  separate rules (`properties.csv:64-78, 86-89`).
- **The pattern is generic in code.**
  - The engine reads any rule whose definition has `profile` (`is_profile`, `profiles_rule.py:38-39`).
  - The UI keys off `definition.profile` (`claims.ts:31-36`) and `detail.list`.
  - `ProfileItems` takes `fields` / `keyField` / `noun` as props.
  - `golden_answers` checks `is_profile` (`:108`).
- So a UI change in `ProfileItems` / `RulesTab`'s profile branch would apply to any future profile rule. *Inferred:*
  only `fold_rules` / `PROFILES` / `FOLDED_CHILDREN` are duration-specific, and the "Estimated " strip in `noun`
  (`RulesTab.tsx:680`).
- **Flat lists** (non-object, e.g. learning method types) use the sibling `ListItems` with the same item / missing
  mechanism (`RulesTab.tsx:683-685`, `startAddItem` / `saveAddItem` `:465-474`, `missingItemEvent`
  `logic.ts:303-307`).

## 4. Backend data shape of a duration value

- **Rule definition** (AVC after the fold): `docs/qrspi/sme-fixes/build-notes-profiles.md:60-69`.
  - The item split regex is `(Total Course [^\n]*?Hours\s+\d[\d.]*(?:\s*-\s*\d[\d.]*)?)`.
  - The `profile.fields` regexes read `ceterms:description` and `ceterms:timeRequired`.
- **Match row** (`build-notes-profiles.md:73-76`):
  - `value` = `{"ceterms:description":"Total Course In-Class (Contact) Hours","ceterms:timeRequired":"54.0 - 432.0"}`
    (canonical JSON, keys sorted, compact; `model.canon`).
  - `fields` = per-field `{text, css_path, char_start, char_end}` (css paths relative to the occurrence).
- **Annotation of an added object**: `build-notes-profiles.md:78-80`, test
  `tests/test_profiles_rule.py:248-253`.
- **Golden page file field** (`build-notes-profiles.md:85-90`; produced by `golden_answers.py:120-125`):
  ```json
  {"ctdl_property": "ceterms:estimatedDuration", "property": "Estimated Duration",
   "value": {"ceterms:description": "Total Course In-Class (Contact) Hours", "ceterms:timeRequired": "54.0 - 432.0"},
   "source_url": "…", "location": {"ceterms:description": {"css_path", "char_start", "char_end"},
                                   "ceterms:timeRequired": {"css_path", "char_start", "char_end"}},
   "approval": "rule", "approved_by": null, "approved_at": null}
  ```
  - One golden field per object (`03-spec.md` §5.4).
  - In `golden.parquet` an object is canonical JSON text, and its `location` is the first (key) field's
    (`golden.py:361-369`).
- **Raw, not normalised.** Values are "page words, unparsed ('54.0 - 432.0')" (`profiles_rule.py:9-10`; `03-spec.md`
  §5.1; Eric's answer to Q10.3, `01-questions.md:438-447`: "Don't parse '54.0 - 432.0' into min and max now.
  Downstream will do that"). The only change is the rule's `transforms` (`strip`, `collapse_ws`).
- **No ISO 8601 (`P6M`, `PT54H`) anywhere in the Studio code.** A grep for `P6M|PT54H|ISO 8601|exactDuration` in
  `src/` hits only `properties.py`, `profiles_rule.py` and `properties.csv` (names, not values).
  - ISO 8601 shows up only in research: `research/profiles.md:25`
    (`schema:Duration` (ISO 8601, `PT54H`)); `:38` the Registry's ART-16 `estimatedDuration: [{minimumDuration:
    PT72H, maximumDuration: PT81H}]`; `01-questions.md:356-359`.
  - "6 months" etc. appear only as sheet samples (`properties.csv:81-83`; phase1 CSV rows 39-41).
  - The scorer compares object fields as text (`build-notes-score.md:137-138`).

## 5. Real page evidence

- **No real course pages are stored in this repo.** No crawled `.html` / page JSON found outside docs mockups.
  Real data lives in an external root (`~/review-ui-v3-data/xtra-cli-output`, per `build-notes-profiles.md:124-125`;
  not checked).
- **Test fixtures are synthetic HTML modelled on AVC**: `tests/test_profiles_rule.py:21-25` (`DURATIONS`: e.g.
  `("Total Course In-Class (Contact) Hours", "54.0 - 432.0")`, `("Total Course Lab Hours", "432.0")`), built by
  `_html` `:33-42` into `<div class="infocard"><div class="col"><h5>{label}</h5><div class="text"><p>{hours}</p>…`.
- **Real snippets quoted in research docs** (from real crawls, not re-verified here):
  - AVC ACCT199: In-Class `54.0 - 432.0`, Out-of-Class `0.0 - 0.0`, Lecture `0.0`, Lab `432.0`
    (`build-notes-profiles.md:113-114`, `build-notes-score.md:112-113`). Visible in `screens/03-duration-objects.png`.
  - AVC: `Total Course Lecture Hours 54.0`, `Total Course Lab Hours 0.0`
    (`docs/qrspi/property-rules/research/pages.md:132`).
  - CCSF: `Hours: Lecture - 52.5` (`pages.md:105-106`); `.lec-hours` `Lecture - 52.5`, `Lab - 17.5` (`pages.md:148`).
  - UARK: `Contact Hours:  120`, `Access to Course:  6 Months` (22 of 22) (`pages.md:235-236`); prose "Approximately 16
    hours to complete the course. Registrants will have 4 weeks to complete the course." (`pages.md:237`). Note 14:
    "Access to Course: 6 Months is how long you can access the course, which may not be how long it takes"
    (`pages.md:107`).
  - UALR: "Three hours lecture. Three hours laboratory per week." (`pages.md:191`).
  - Summary: "No catalog prints a min–max time range" in months / weeks. AVC's ranges are hours (`pages.md:283`).
  - Counts: several durations on every AVC course (1,062), 383 at CCSF (`01-questions.md:419-420`).

## 6. Tests covering this UI

**Web (Vitest):**
- `web/src/rules/ProfileItems.test.tsx`:
  - "reads a profile rule and builds the object a reviewer labels" (`:100`);
  - "shows one sub-row per object, fields side by side, a ✓ ✕ each; one ✕ makes the row wrong" (`:115`);
  - "+ Add a duration: select a piece, label it with a field name; saved once every field is labelled" (`:131`;
    drives `onSelection` and the in-row `.label-bar`, **not** the `fieldBar` highlight-bar actions).
- `web/src/pagepane/HighlightBar.test.tsx` (`:12, :34, :54, :59`): generic bar behaviour.
- `web/src/rules/RulesTab.test.tsx`:
  - flat bar: `:261` "marks the right value by selecting it on the page…", `:514` "a selection shows the highlight
    bar…", `:541`, `:555`, `:566`, `:574`, `:593`;
  - flat lists: `:473` "a list row shows one line per item…", `:491` "＋ Select a missing item…", `:724` "the page
    pane outlines every item of the list on its page".
- Also mention duration: `web/src/rules/RuleList.test.tsx:24, :81` (the "list" tag), `web/src/records/RecordsTab.test.tsx:26`,
  `web/src/evals/EvalsTab.test.tsx:34-180`.
- **Gap (verified by grep):** no test asserts `fieldBar` (field-name `barActions` for a profile rule).

**Python (pytest):**
- `tests/test_profiles_rule.py`:
  - `test_a_profile_rule_gives_acct199_four_objects_with_each_fields_place` (`:158`);
  - `test_properties_apply_folds_the_six_duration_rules_into_one_profile_rule` (`:205`);
  - `test_each_object_has_its_own_verdict_and_an_added_object_is_labelled_field_by_field` (`:232`);
  - `test_golden_parquet_and_page_files_hold_objects_and_absent_fields` (`:350`).
- `tests/test_score_units.py` (`:49, :58, :75, :87`: object scoring, rules A/B/C).
- Outside this package: `xtra-cli/tests/implementations/test_score_extraction_units.py`.

## 7. Screenshots

- `docs/qrspi/sme-fixes/screens/03-duration-objects.png`: AVC · Estimated Duration · ACCT199.
  - Shows "4 found", four object sub-rows (description and timeRequired side by side, field names small, ✓ ✕ each)
    and "+ Add a duration".
  - Banner: "each item found is highlighted. Wrong item? Use its ✕. Missing one? Add it below." The infocard fields
    are outlined on the page.
- `docs/qrspi/sme-fixes/screens/04-label-a-new-duration.png`: same row after "Add a duration" and a selection.
  - The in-row "Adding a duration: select each piece on the page, then say which field it is." with empty
    `description —` / `timeRequired —` slots and a disabled "Save duration".
  - The dark highlight bar on the page shows `description · timeRequired`, with no comment bubble.
- Generator: `bench/shots_sme_fixes.py:61-72`.
- Mockups and proposals in `docs/qrspi/sme-fixes/img/`: `mock-p3-q10-list.png` (the list review design referenced by
  spec §5.2), `mock-q10-shape.png`, `mock-q10-4.png`, `mock-p3-q10-5.png`, `mock-p3-q10-agg.png`,
  `q10-4-evals-today.png`, `q10-creditvalue-jared.png`, `q10-7-ath103l-prereq.png` (not opened, apart from the two
  screens above).

## Unverified / flags
- I did not run the app. The claim that the in-row label bar rarely shows in the browser is inferred from
  `PagePane.tsx:231` plus `RulesTab.tsx:495, :746`.
- I did not open any real page data. All real snippets above are quotes from research docs.
- I don't know whether the Studio's live catalogs were migrated with `properties apply --all`. Build notes say not on
  that branch (`build-notes-profiles.md:115-116`). The screenshots show "v4 (latest)" with the folded rule.
