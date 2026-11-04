# Build notes: the xtra score (sme-fixes spec §8, scorer side of §5.4 and §6)

Branch `sme-fixes-score`, from `b160a3a`. Four commits: the scorer, xtra's extract output, the Studio's scores, the
Evals tab. Line numbers are at the branch's head.

## What changed

### xtra-cli

| File | What |
|---|---|
| `src/implementations/score_extraction_match.py:1-56` | Module docstring: units, outcomes, the two modes, found / right / entities_exact. |
| `:70` | `REPORT_SCHEMA = "xtra-extraction-match-report-2"`. |
| `:72-99` | Outcomes: `unsure` added to both modes' `outcomes`; `UNIT_OUTCOMES` = match, partial, wrong, missing, unsure, extra. |
| `:129-138` | `CREDIT_PROFILE_KEYS` also reads `schema:value` / `schema:minValue` / `schema:maxValue` (what `lib/mapping.py` and the Registry write). Trivially safe: an extra key lookup; nothing else reads them. |
| `:142` | `OBJECT_KEYS = {"ceterms:estimatedDuration": "ceterms:description"}`: list-of-objects properties and the field they pair by. |
| `:157` `extracted_claims` | The record as `(pool, absent)`: dict items of an object property are kept whole (before, dicts were reduced to `ceterms:name`); an explicit `null` is the claim "not on the page" (a null `creditValue` claims its min and max too). `extracted_values` (the old name) returns the pool. |
| `:227-243` | `is_absent` (`absent: true`); `is_implied` no longer treats an absent field as implied even when its `location` is null. |
| `:281` `compare_objects`, `:325` `compare` | One possible pair: a value's similarity is its pairing score; an object pairs by its key field's similarity, its similarity is its worst field's, and it is exact only when every field is. |
| `:377` `match_entity` | Per property: golden absent ↔ the null claim; exact pairs; then greedy by (pairing score, similarity), one to one. Unpaired golden → `missing` (`unsure` when golden is absent and the record has no key at all); unpaired extracted units of a covered property → `extras`. Each entity also returns `units` (every unit's outcome, whichever the mode). Field results carry `unit` and, for objects, `object_fields`. |
| `:586` `unit_numbers`, `:628` `summarize` | The report adds `units`, `found`, `right`, `unsure`, `entities`, `entities_exact`, `extras {count, outliers}`, and per property `{golden, extracted, match, partial, wrong, missing, extra, unsure, found, right, entities, entities_exact}` beside the mode's counts. `by_property` now lists every covered property (in partial mode an all-exact property used to be absent; it now shows `fields: 0`). |
| `:888` `format_table` | Prints found (recall) and right (precision) overall and as `match/golden`, `match/extracted` per property, plus the extras. |
| `src/xtra/scoring/extraction/match.py:13-24, 78` | Docstring; the stdout summary adds found, right, extras, unsure, entities_exact. |
| `lib/mapping.py:73-107` `duration_profile`, `:169` | One printed hours line → `{ceterms:description, ceterms:timeRequired}` in the page's words (the time is the number or range as printed, the description the rest of the line; the label words "Lecture Hours" / "Lab Hours" only when the reader kept none). `map_fields` puts every hours line in one `ceterms:estimatedDuration` list. |
| `lib/inventory.py:16-22`, `lib/FIELD_INVENTORY.csv:11-12` | Lecture / lab hours name `ceterms:estimatedDuration`. |
| `src/implementations/extract.py:65-66, 78, 205` | `TERMS` maps lecture / lab hours to `ceterms:estimatedDuration`; `_term_value` turns the draft into the object; `expected_values` keeps `estimatedDuration` a list even with one line (`LIST_TERMS`). |
| `src/implementations/extract_dom.py:287` `_hours_excerpt` | A field pair's or a heading's hours keep the label beside the number in the excerpt ("Total Course Lecture Hours 54.0"), so the description is the page's words. |
| `README.md` | Estimated Duration in the course table; units, unit outcomes and the new numbers in the scoring section. |
| Tests | `tests/implementations/test_score_extraction_units.py` (new: ACCT199 A/B/C, every outcome, absent, objects, report, table, backward compatibility); `test_score_extraction_match.py`, `tests/xtra/scoring/extraction/test_match.py` (`unsure: 0` in `outcomes`, by_property, a CLI test of found/right/extras/unsure); `test_extract.py`, `test_extract_dom.py`, `test_transform.py` (durations). |

### Golden Dataset Studio

| File | What |
|---|---|
| `src/golden_datasets/scores.py:26-32` | Docstring: units. |
| `:61-66` | `GOLDEN_OUTCOMES`, `OUTCOMES` (+ `extra`); `SCORE_VALUES` = `model.SCORE_VALUES` + `unit`, `field`, `reason` (kept here so `model.py` isn't touched). |
| `:139` `is_implied` | An absent field is scored. |
| `:343` `diff_kind`, `:368` `reason_for` | Word diff kind (cut short · extra text · different) and the `reason` column. |
| `:396` `value_rows` | One row per golden unit and per extra; `unit`, `field` (object fields that differ, prefix-free, worst first), `reason`. The rebuilt-count check still holds: golden rows = `fields_total`; match / missing / unsure from the exact report, partial / wrong from the partial report, extra = `extras.count`; any difference raises. |
| `:469` `counts`, `:486` `result` | `values` (golden units) and every outcome, `extracted`, `found`, `right`, `courses`, `courses_exact`, `list`; results add found / right / extracted / entities_exact. |
| `:588` `candidates`, `:612` `xtra_terms`, `:634` `finish` | A score keeps `candidates` (per column, the extract output's values; 0 = only a null claim) and `xtra_extracts` (the columns xtra's extract writes at all); `emitted` includes null claims. |
| `:823` `wrong_key`, `:845` `wrong_groups` | "Where it's wrong". |
| `:873` `scored_against`; `server/jobs.py:76-90` | The loop also scores the latest golden dataset against the latest extract output when no score of that pair exists (see §8.3 below). |
| `:884` `_line` | `golden-datasets score` prints found / right / unsure / extra. |
| `server/routes_evals.py:106` `_rows`, `:132` `where_wrong` | `GET /catalogs/{c}/scores/{id}/wrong?basis&column&key=auto|label|shape|diff|subject`; old values.parquet rows get `unit/field/reason = None`; briefs add `{basis}_found`, `{basis}_right`. |
| `web/src/api/types.ts`, `web/src/api/client.ts` | `ScoreOutcome` + unsure / extra; `OutcomeCounts` + found / right / courses; `WrongGroups`; `api.scoreWrong`. |
| `web/src/evals/EvalsTab.tsx:39-60` | `OUTCOMES`, `BAR_ORDER` (extras last), outcome rules in the tab's terms, `FOUND_TIP` / `RIGHT_TIP` / `COURSES_TIP` (formulas), the candidates / golden-values definitions. |
| `:99` `unscoredFacts`, `:553` `Unscored` | Coordinator's request: an unscored column says **Not scored** and two chips, *Candidates: …* and *Golden values: …* (*Rule-matched values* on that side), each with a tooltip defining the term and the full sentence; the old free-text `reasonFor` is gone. |
| `:411` `ScoreBody`, `:569` `ColRow`, `:661` `Bar` | Header row (Column · Units · Found · Right · Courses · Golden values) with formula tooltips; found / right per column, courses exact for list columns; found / right / extra / unsure under the headline; unsure and striped extra segments; the outcome filter has unsure and extra. |
| `:592` `WhereWrong` | The grouped list (`?wk=`), each group: count (click: filter the values), outcome · field · how it differs, grouped by, example (golden → candidate, objects shown as `description: … · timeRequired: …`) with a link, and its first 12 courses linked to `#/c/<cat>/rules/<rule>?row=<occurrence>&by=anyone`. |
| `:538` `rowText` | A row says what its candidate is, or why there's none. |
| `web/src/evals/evals.css` | `--o-unsure`, striped `--o-extra`, the new pieces. |
| `web/src/catalogs/CatalogPicker.tsx:17, 220` | The home table's bars use `BAR_ORDER` (a score without unsure / extra still draws). |
| Tests | `tests/test_score_units.py` (new: ACCT199 A/B/C through xtra's scorer, absent cases, the rebuilt-count check, diff kinds, groups); `tests/test_scores.py` (new outcomes, found/right/where-wrong route, the loop scoring a CLI-published golden dataset); `web/src/evals/EvalsTab.test.tsx` (every unscored-fact case, tooltips, found/right/courses, extra/unsure segments, Where it's wrong + Rules links + `wk`, row texts). |

## When the score runs (§8.3), from the code

1. **A golden dataset is published from the Studio**: approving a column's rule publishes it
   (`routes_review.py:704-711`, `golden.publish_approved`) and then calls `ScoreJobs.after_publish`
   (`routes_review.py:712` → `jobs.py:63`), which scores the latest extract output against the latest golden dataset
   (`ruleset-vN`).
2. **An expert's verdict** rewrites that page's golden file (`routes_review.py:697` → `golden.publish_page`) and writes
   `scores/pending.json` due 5 minutes later (`golden.py:599` `request_score`, `RESCORE_AFTER` `golden.py:64`; each
   verdict moves it on). The server loop runs it when due against `human-reviewed` (`jobs.py:89-94`).
3. **A new extract output**: the server loop (`jobs.py:111`, every 30 s, `EVERY` `jobs.py:20`, started in
   `server/app.py:78`) copies an output whose report ETag it hasn't seen and scores it against the latest golden
   dataset (`jobs.py:81-84`). Opening the Evals tab does the same (`GET extract-outputs`, `routes_evals.py:52-58`).
4. **New in this branch:** a golden dataset published **outside** the Studio's approve (`golden-datasets golden
   publish`, `golden.py:659`, which never scored) is now picked up by the loop: when the latest extract output has no
   score against the latest golden dataset, in any state (`scores.scored_against`), it is scored
   (`jobs.py:85-88`, reason "a new golden dataset, ruleset-vN"). Before, that pair was only scored when a new extract
   output appeared or someone pressed Score.
5. **From the Evals tab**: the Score button on a dashed bar (`POST /scores`, `routes_evals.py:75`).
6. **From the CLI**: `golden-datasets score [--ruleset N | --draft rs-NNNN | --human-reviewed] [--output …]`
   (`cli.py:269-282` → `scores.cmd_score`); `xtra score extraction match --exactly|--partially` (xtra-cli
   `src/xtra/scoring/extraction/match.py`), which writes `extraction-match-{mode}-report.json` beside the records.

A pair (golden content hash, extract output ETag) is scored once (`scores.existing`); one score runs per catalog at a
time (`jobs.py:30-60`). Only columns the output emits are scored (P10): a property the output neither has a value for
nor claims `null` for is "not scored", so its absent golden fields can't be `unsure` there.

## The math

Units, per entity (course) and property: a **value**, an **object** (one `estimatedDuration` golden field = one
object; several = the list), or **absent** (`{"value": null, "absent": true}`). In a record, `null` is the claim
"not on the page"; a missing key is no claim.

Pairing, per entity and property: golden absent ↔ the record's null; then exact pairs (`is_exact`: identical as
printed; objects: every field); then the rest greedily by pairing score, best first, one to one (values: similarity;
objects: the key field `ceterms:description`'s similarity, then the worst field's). Similarity is rapidfuzz `ratio`
on normalized text (and with punctuation and spaces removed, the higher), numbers by value.

| Golden ↓ · extracted → | a value | null ("not on the page") | no key |
|---|---|---|---|
| a value | match (exact) · partial (≥ 0.8) · wrong (< 0.8) | golden **missing** + the null claim **extra** | missing |
| absent | golden **missing** + the value **extra** | **match** | **unsure** |

An object is partial when every field is ≥ 0.8 and not all exact, wrong when any field is < 0.8. An entity with no
record at all is all missing (absent included). Extras count only for properties the golden entity covers
(`unscored_extras` lists the rest, as before); implied fields (`location: null`, not absent) are skipped as before.

Numbers, summed over every entity (micro-averaged), per property and overall:

    golden    = match + partial + wrong + missing + unsure
    extracted = match + partial + wrong + extra              (the Studio calls these candidates)
    found (recall)     = match ÷ golden
    right (precision)  = match ÷ extracted
    exact_match_rate   = match ÷ golden fields = found       (exact mode, as before)
    entities_exact     = entities whose every unit (extras included) matched ÷ entities with a unit
    courses exact (Studio, per column) = courses whose every unit in that column matched ÷ courses

Worked examples, ACCT199's "Units and Hours" (golden: In-Class `54.0 - 432.0`, Out-of-Class `0.0 - 0.0`, Lecture
`0.0`, Lab `432.0`), tested in `test_score_extraction_units.py` and `test_score_units.py`:

- **Rule B** (the four objects): 4 match → found 4/4 = 1.0, right 4/4 = 1.0, courses exact 1/1.
- **Rule A** (the four + `Minimum Credit Units 1.0`): 4 match, 1 extra → found 4/4 = 1.0, right 4/5 = 0.8,
  `exact_match_rate` 1.0 (unchanged by extras), courses exact 0/1. Where it's wrong: `extra` · description label
  "Minimum Credit Units".
- **Rule C** (In-Class and Out-of-Class times swapped): paired by description, so In-Class pairs with In-Class;
  `timeRequired` `54.0 - 432.0` vs `0.0 - 0.0` is 0.67 < 0.8 → 2 match, 2 wrong → found 2/4, right 2/4. Where it's
  wrong: `wrong` · `timeRequired` · value shape `9.9 - 9.9 → 9.9 - 9.9`, 2 units. Scored as loose values, all three
  would be 100%.

Backward compatibility: a golden file without objects or absent fields scores exactly as before (`fields_total`,
`outcomes` with `unsure: 0`, `exact_match_rate`, `outliers`, `pages`); the new numbers are `extras` / `right` (an
extracted list value with more items than the golden list now shows as extra) and `found` (= `exact_match_rate`).
In the Studio, old `score.json` files read as before (no unsure / extra / found / right: the tab computes found from the
counts and shows right as "–"), and old values.parquet rows get `unit / field / reason = None`.

## Left undone / notes

- **Screenshots** (§10) for this stream were not taken: no local server on the local mirror was run here.
- **Rules tab filtered to a group's courses**: the Rules URL has no course-list filter (`row`, `ext`, `by`, `v` only;
  `RulesTab.tsx` is another stream's file), so each course in a group links to its own row
  (`?row=<occurrence>&by=anyone`) and the example links to its row. A "these N courses" filter would need a Rules-tab
  parameter (the rows API already has `q`).
- Objects compare field by field as text; the research's parsing of times (`54.0` = `PT54H`, ranges as min/max) is not
  done: the spec keeps page words unparsed.
- `xtra-cli`: `uv run pytest` fails to resolve on Python 3.14 (crawl4ai's extra); the tests were run with a Python
  3.12 venv (`uv venv -p 3.12 && uv pip install -e ".[dev,azure]"`, then `pytest`), as the README's
  `python3 -m pytest tests -q`.
- `xtra catalog transform` on records extracted by `src/implementations/extract.py` still stops on
  `canonical_label` (known, README); `lib/mapping.py` maps durations for the lib pipeline it serves.

## Test results

- xtra-cli: 1,195 passed, 3 skipped; `ruff check` and `ruff format --check` clean.
- golden-dataset-studio `make check`: ruff clean; pytest 167 passed (52 slow deselected); web typecheck clean,
  vitest 181 passed (26 files); build OK.
