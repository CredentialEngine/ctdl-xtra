# Build notes: lists of objects, "not on the page", the reviewer's answer (sme-fixes §5, §6, §7)

Branch `sme-fixes-profiles` (from `b160a3a`). Scope: [`03-spec.md`](03-spec.md) §5 (Estimated Duration as a list of
objects), §6 (absent claim, "Why wrong?", row wording, golden absent fields), §7 (golden publishes the reviewer's
answer) and the rule-writing guidance for them in `prompt.py`. Paths are relative to `golden-dataset-studio/`.

## What changed

### Extraction (§5.1, §6)

| Where | What |
|---|---|
| `src/golden_datasets/profiles_rule.py` (new) | `profile: {fields: {<ctdl field>: <sub-definition>}, key}` on a `multiple` rule: `run` makes one object per split item, each field read from the item by its own sub-definition (a regex on the item's text, or a selector / `labelled` on the item's element). `values_of_text` (draft examples give objects). `row_item` / `row_value` (rows). `with_object_text` (an added object's `expected.text`). `fold_rules`: six Estimated Duration rules → one. |
| `src/golden_datasets/absent.py` (new) | `absent_if: {within, missing}`; `missing` is a selector, or a label's words (a string that isn't a valid selector, or `{"label": "…"}`); `{"selector": "…"}` also works. Applies only when the rule found no value. |
| `src/golden_datasets/engine.py:419` | `run_property` dispatches to `profiles_rule.run` and wraps the result in `absent.claim_or`. `:460` `values_of_text` for profile rules. |
| `src/golden_datasets/model.py:81` | `matches` gains a nullable `fields` column (JSON text). Old Parquet files read as null (`UNION ALL BY NAME`; `from_pylist` fills it). |
| `src/golden_datasets/check.py:111` | Match status may be `absent`. `:176` a lineage row with no `match_value_index` and an annotation is a reviewer's answer, not a broken FK. |
| `src/golden_datasets/properties.py:53` | `SKIP_PATHS` drops the five `ceterms:estimatedDuration>…` rows on `properties sync`. `:378` `apply` also folds (see "Migration"). |
| `src/golden_datasets/properties.csv` | The five duration children are `status=removed` (kept as rows, like any row gone from the sheet): 36 active properties instead of 41. |

### Review and annotations (§5.2, §6)

| Where | What |
|---|---|
| `src/golden_datasets/review.py:208-210` | A list row's item carries `fields` for an object; the row's `value` reads `description · timeRequired`, one per line. Item verdicts are the list-item mechanism unchanged (`target.item`, `value_index`, keyed by `value_seen` = the object's JSON). |
| `src/golden_datasets/log.py:24, :55` | `REASONS = {"not_on_page"}`; `reasons` only on a `wrong` verdict. |
| `src/golden_datasets/server/routes_review.py:79` | Event briefs carry `reasons`. `:674` an added object's `expected.text` is set server-side. `:684` `reasons` stored. `:598, :603` the course endpoint (Records tab) gets `fields` and readable list values. |
| `src/golden_datasets/query.py:33-36` | `ANNOTATION_COLUMNS`: `expected.objects JSON`, `reasons VARCHAR[]`. |

### Golden dataset (§5.4, §6, §7)

| Where | What |
|---|---|
| `src/golden_datasets/golden_answers.py` (new) | `fields(...)`: what one rule publishes on one course, in this order: the reviewer's answer; an absent field; the rule's values (objects one field each, ✕'d objects left out, added objects in). `answer_text`: the `in` segments joined in page order, minus `out` segments (reads `polarity`; missing = `in`). |
| `src/golden_datasets/golden.py:141-180` | `plan` asks `golden_answers.fields` per (rule, course), including rules with no found value when a reviewer answered there. `:361` `golden.parquet`: an object is canonical JSON text, its `location` the key field's. |

### Prompt (rule-writing guidance)

`src/golden_datasets/prompt.py:549` `profile` and `:555` `absent_if` rows in "Every rule type and input" (claim absence
only after seeing pages where the property is truly missing). `:574` Prerequisite: Description keeps the full sentence
(ATH103L), conditions stay flat text. `:583` Estimated Duration is one list-of-objects rule. `:588` keep whole text
blocks. Only the `RULE_TYPES` / `REQUISITE_WORDS` constants changed (nothing in `build_prompt`).

### Web

| Where | What |
|---|---|
| `web/src/rules/claims.ts` (new) | `statusWords` / `statusHint` (the three outcomes' wording), `REASONS`, profile helpers (`profileOf`, `objectOf`, `ObjectAdd`, `labelField`, `objectEvent`). |
| `web/src/rules/ProfileItems.tsx` (new) | The list-of-objects row: sub-rows with fields side by side (names small), ✓ ✕ each, "N ✕ → row wrong", added objects (dashed green), "+ Add a duration" with a dark label bar (field names) under the row. |
| `web/src/rules/WhyWrong.tsx` (new), `claims.css` (new) | The "Why wrong?" flag set; styles for all of the above. |
| `web/src/rules/RulesTab.tsx` | `:110` `objAdd` state; `:194` `profile`; `:275-293` per-field highlights, labelled pieces, `looked` box for an absent row; `:397-414` start / label / save an object; `:514`, `:572` wording; `:581` `ProfileItems` branch; keys: H starts adding an object, Enter saves (once the key field is labelled), Esc cancels. |
| `web/src/rules/parts.tsx:77` | `Expansion` (✕) shows `WhyWrong` on property rules. |
| `web/src/rules/logic.ts:129, :186, :108` | `Draft.reasons`; `verdictEvent` sends them; the history line says "Why wrong: Not on the page". |
| `web/src/pagepane/paint.ts:12, :43, :51` | Highlight kind `looked`: the whole element, dashed purple (style in the overlay CSS, so no `render.py` change). |
| `web/src/records/RecordsTab.tsx:217` | Same wording for a property with no value. |
| `web/src/api/types.ts` | `ObjectField`, `RowItem.fields`, `Expected.objects`, `EventBrief.reasons`, `NewEvent.reasons`, `Row.status` `absent`. |

## Data formats as built

**Rule definition** (AVC after the fold, `course-estimated-duration` v3):

```json
{"locator": "locator-course-page", "rule_type": "css+regex", "selector": ".infocard",
 "multiple": {"split": "regex", "regex": "(Total Course [^\\n]*?Hours\\s+\\d[\\d.]*(?:\\s*-\\s*\\d[\\d.]*)?)"},
 "transforms": ["strip", "collapse_ws"],
 "profile": {"key": "ceterms:description", "fields": {
   "ceterms:description":  {"rule_type": "regex", "regex": "\\A\\s*(Total Course [\\s\\S]*?Hours)", "transforms": ["strip", "collapse_ws"]},
   "ceterms:timeRequired": {"rule_type": "regex", "regex": "Hours\\s+(\\d[\\d.]*(?:\\s*-\\s*\\d[\\d.]*)?)\\s*\\Z", "transforms": ["strip", "collapse_ws"]}}}}
```

**Absent check:** `"absent_if": {"within": ".introtext", "missing": "LIMITATION ON ENROLLMENT"}`.

**Match row** (one per object): `value` = `{"ceterms:description":"Total Course In-Class (Contact) Hours","ceterms:timeRequired":"54.0 - 432.0"}`
(`model.canon`: keys sorted, compact); `raw_text`, `css_path`, offsets = the item's; `fields` =
`{"ceterms:description": {"text", "css_path", "char_start", "char_end"}, …}` (paths relative to the occurrence).
An absent claim: `status: "absent"`, `value: null`, `css_path` = the `within` container.

**Annotations:** an object verdict is a list-item verdict (`target.item: true`, `value_index`, `value_seen` = the
object JSON). An added object: `verdict: "missing"`, `target.item: true`,
`expected: {text: <object JSON, set by the server>, css_path…: the first labelled field, located_by: "labelled in the Studio", objects: [{fields: {<ctdl field>: {text, css_path, char_start, char_end}}}]}`.
A reason: `reasons: ["not_on_page"]` on a `wrong` verdict.

**Golden page file field** (what the scorer reads):

```json
{"ctdl_property": "ceterms:estimatedDuration", "property": "Estimated Duration",
 "value": {"ceterms:description": "Total Course In-Class (Contact) Hours", "ceterms:timeRequired": "54.0 - 432.0"},
 "source_url": "…", "location": {"ceterms:description": {"css_path", "char_start", "char_end"},
                                 "ceterms:timeRequired": {"css_path", "char_start", "char_end"}},
 "approval": "rule", "approved_by": null, "approved_at": null}
{"ctdl_property": "ceterms:entryCondition>ceterms:description", "property": "Entry Condition: Description",
 "value": null, "absent": true, "source_url": "…", "location": {css_path, …} | null, "approval": …}
```

`absent` appears only on absent fields. Lineage rows of reviewer answers have `match_value_index: null` and the
row's annotation ids.

**Approval of reviewer answers:** a ✕ with an expected value, a ✕ with `not_on_page`, a ✓ on a "Nothing found" row
and an added object are all `approval: human`, `approved_by` the reviewer, whatever their role (spec §7). A rule's
absent claim is approved like any value (an expert's ✓ → human, else the rule's approval).

## Migration (six Estimated Duration rules → one)

`golden-datasets properties apply -c <catalog>` (or `--all`) now also runs `profiles_rule.fold_rules` on the latest
ruleset and publishes one ruleset version (note "Estimated Duration is one list of objects (5 child rules folded
in)") with its extraction:
- the parent gets `profile.fields` from its children that read it (`input.rule` = the parent) and have a rule
  (description, time required); a child's one-match `multiple.split: regex` becomes a plain `regex`;
- the five children leave the ruleset (a catalog whose parent has no rule just loses them);
- nothing migrates in the annotation log (nobody annotated these rules, `research/annotations.md` §1).

Checked on a local AVC root built from the mirror plus AVC's six duration rules as the Studio has them (rules v2 from
the local cache): `properties apply` → `course-estimated-duration` v3, 4,248 objects on 1,062 courses, ACCT199's four
objects `In-Class 54.0 - 432.0`, `Out-of-Class 0.0 - 0.0`, `Lecture 0.0`, `Lab 432.0`; `check` 0 failed. The Studio's
own catalogs are **not** migrated by this branch: run `golden-datasets properties apply --all` against the Studio root
after merging.

## Seeing each behaviour in the UI (for screenshots)

A local root on the mirror, with AVC's six duration rules folded and an `absent_if` example:

```sh
export GOLDEN_DATASETS_ROOT=$PWD/.data/root-profiles GOLDEN_DATASETS_GOLDEN_ROOT=$PWD/.data/golden-profiles
golden-datasets sync --from ~/review-ui-v3-data/xtra-cli-output --to $GOLDEN_DATASETS_ROOT -c avc --pages link
golden-datasets init -c avc && golden-datasets import-v2 -c avc --v2-root ~/review-ui-v3-data/xtra-cli-output
golden-datasets rule publish -c avc durations.json   # AVC's six rules: course-estimated-duration{,-description,-time-required,-exact-,-minimum-,-maximum-duration}
golden-datasets properties apply -c avc              # folds them: one list-of-objects rule
golden-datasets rule publish -c avc absent.json      # Entry Condition: Description with absent_if (below)
golden-datasets serve
```

`absent.json`: `course-entry-condition-description`, `css+regex` on `.introtext`, regex
`LIMITATION ON ENROLLMENT:\s*([\s\S]+?)\s*$`, `absent_if: {"within": ".introtext", "missing": "LIMITATION ON
ENROLLMENT"}` → 26 courses found (ACCT199, ABDY199, …), 1,036 "Not on the page (rule's claim)".

| Behaviour | Where |
|---|---|
| Objects, per-object ✓ ✕, "1 ✕ → row wrong" | AVC · Rules · Estimated Duration · ACCT199 (`?row=` its occurrence key; or search ACCT199). ✕ the 4th object. |
| Each field outlined on the page | same row, page pane |
| Adding an object by labels | same row, "+ Add a duration" (or H), drag "Total Course Lab Hours", pick `description`, drag "432.0", pick `timeRequired`: saved, shown dashed green under the objects |
| "Not on the page (rule's claim)", dashed purple box on the page | AVC · Rules · Entry Condition: Description · ABDY112 |
| "Nothing found · the rule made no claim; check the page" | any property whose rule found nothing, e.g. Description on a course with no `.introtext`; or Entry Condition: Description before `absent.json` |
| ✕ → "Why wrong? ☐ Not on the page" (tooltip) and the history line "Why wrong: Not on the page" | Entry Condition: Description · ACCT199 (a found value), ✕ |
| Records tab wording | Records · ABDY112 · Entry Condition: Description |
| Golden: objects, absent fields, reviewer answer | approve a rule (publishes), then read `.data/golden-profiles/avc-…/…/<stem>/<stem>.json`; DA107A-like case: ✕ Description on a course, select the full text, then look at that page's file (`approval: human`) |

## Left undone / for the merge

- **The highlight bar (§1, other stream) and §5.3:** the bar isn't built here. Labelling happens in a dark label bar
  under the row (`ProfileItems`, `.label-bar`) after a selection on the page. When the highlight bar lands, for a
  profile rule it should show the field names and call RulesTab's `labelObject(field)` (starting `objAdd` with
  `startAddObject()` first if none is open); `onAnswer` already routes a selection to `objAdd.pending`.
- **`polarity`** on `expected.segments[]` is the other stream's; `golden_answers.answer_text` already reads it
  (missing = `in`). `ANNOTATION_COLUMNS` (query.py) was edited by both streams: merge both additions.
- **Flat lists** (not objects): a ✕'d item is still published with the rule's approval, as before; only objects
  of a profile rule are left out when ✕'d.
- A ✓ on a **"no rule yet"** row doesn't publish an absent field (spec: "Nothing found" rows only).
- `golden.parquet` has no `absent` column: an absent field is a row with `value` null (page files have
  `absent: true`). An object's `location` there is its key field's.
- The Studio's catalogs aren't migrated (run `properties apply --all` after merging). No screenshots taken.
- `make slow` has 9 failures that are the same at `b160a3a` (AVC end-to-end counts, loop, prompt); not touched.
