# Research: CCSF course blocks (items 3 and 8)

Done on 2026-11-04. Code was read, and the CCSF extraction `rs-0006` (ruleset 6, made 2026-11-03) was read from the
live data. The signal code was also re-run on all 118 CCSF course pages. Nothing was changed. Paths are relative to
`golden-dataset-studio/`.

## Short answers

- **Q8.4:** The duplicate and uncovered-code signals do **not** fire falsely on CCSF. They do not fire at all: 0
  `duplicate-occurrence`, 0 `uncovered-code`, 0 `block-count-mismatch` on 1,927 courses over 118 pages. Re-running
  the page checks on every page gives the same 0. Nothing needs fixing for false alarms. There are blind spots
  (below), but they hide problems; they don't invent them.
- **Q8.3:** Today the CCSF locator table has **one row per course block** (1,927 rows), not one per page (118 pages).
- **Locator definition:** `repeat: ".course-summary-wrapper"`, no `scope`, no `repeat_filter`, used on page rule
  `course-page`. Its stored `what` already says it well: "On course pages, each `.course-summary-wrapper` block is one
  course."

## CCSF's rules, as stored (ruleset 6)

| Rule | Definition |
|---|---|
| `course-page` (page rule) | `url_regex: /catalog/iq/courses/\d+/[^/]+$`, `requires_selector: #content-body .course-summary-wrapper` |
| `locator-course-page` | `page_rules: [course-page]`, `scope: null`, `repeat: .course-summary-wrapper`, `repeat_filter: null` |
| `course-code` | `css+regex` on `.course-title-units-row`, regex `^\s*(.+?)\s+-\s` (group 1), `collapse_ws` |
| content root | `#content-body` |
| signal pattern (CCSF override) | `\b[A-Z]{2,5} \d{1,3}[A-Z]{0,2}\b` |

For comparison, AVC's `locator-course-page` has `repeat: null` (the whole content area is one course).

Each CCSF "course page" is really a **department page**: `/catalog/iq/courses/3/155` is Spanish, with 28 courses. Pages
hold 1 to 110 courses. Only 4 of 118 pages hold a single course.

| Courses on the page | 1 | 2-5 | 6-10 | 11-20 | 21-40 | 41-110 |
|---|---|---|---|---|---|---|
| Pages | 4 | 32 | 21 | 26 | 20 | 15 |

So the fixed titles are wrong for CCSF:

- `LOCATOR_TITLES` gives "One course per course page" (`src/golden_datasets/server/routes_review.py:33`), and the
  same string is hard-coded in the web app (`web/src/rules/RuleHead.tsx:13`).
- `PLAIN_SUBTITLES["course-page"]` says "Which pages are a single course's own page" (`routes_review.py:28`). That is
  also false for CCSF.
- A title made from the definition is easy: `repeat` set → "Course blocks: every `.course-summary-wrapper` on the
  page"; `repeat` null → "Whole page is one course". Add "inside `<scope>`" when `scope` is set, and "kept only if
  `<selector>` matches `<regex>`" when `repeat_filter` is set. Today the head shows only the filter's regex and drops
  its `selector` (`RuleHead.tsx:29-30`).

## Q8.4: what the two signals check

Both are computed when an extraction is made and stored in `signals.parquet` (`src/golden_datasets/signals.py:150`).

| Signal | What it checks | Where |
|---|---|---|
| `duplicate-occurrence` | Counts courses by (page, `course_key`, locator). `course_key` is the code with spaces removed, upper case (`model.py:176-178`). Fires on each block when the same code is found in 2+ blocks **of the same page**. | `signals.py:210-219` |
| `uncovered-code` | Finds the nearest element that holds every found block (the "area"). Scans each text node inside the area but outside every block for the course-code pattern. Each hit fires once per page: "possible missed course". | `signals.py:94-131` (facts), `243-246` (signal) |
| `block-count-mismatch` (related) | Counts `repeat` elements whose text matches the code pattern. Fires only when that count is **greater** than the courses found. | `signals.py:84-89`, `238-242` |

Why they stay quiet on CCSF department pages:

- **Duplicate:** each course appears once on its department page. 18 courses appear on 2 or 3 pages (cross-listed,
  e.g. `IDST37` on 3 pages, `PSYC23` on 2). The check is per page, so that is correctly not flagged.
- **Uncovered:** the area is the plain `div` that holds the `.course-summary-wrapper` wrappers, and it holds nothing
  else. The department heading ("INTD - Interior Design") sits outside the area, and it has no number anyway. Codes
  in prerequisites ("ESL 188A") sit inside a block. So nothing is outside the blocks.
- **Block count:** there is no `repeat_filter`, so the candidate blocks are the found blocks. The count can never be
  larger, so this signal can never fire on CCSF.

## Two real examples

**Example 1: Interior Design, 3 courses.** https://ccsf.curricunet.com/catalog/iq/courses/3/102

| # | Course | Occurrence key (page stem `ccsf-curricunet-com-catalog-iq-courses-3-102-3ecab791c0` + `@` + path) |
|---|---|---|
| 1 | INTD 100 | `…@html > body:nth-of-type(1) > div:nth-of-type(3) > div:nth-of-type(1) > div:nth-of-type(3) > article:nth-of-type(1) > ol:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type(1)` |
| 2 | INTD 102 | same, with `div:nth-of-type(2)` as the 9th step |
| 3 | INTD 138 | same, with `div:nth-of-type(3)` as the 9th step |

Signals: none. Three different codes, so no duplicate. No text sits between the blocks, so nothing is uncovered.
The page's only free-standing code match is "ESL 188A", inside a prerequisite of a block. Not a false alarm.

**Example 2: Spanish, 28 courses.** https://ccsf.curricunet.com/catalog/iq/courses/3/155

Courses: SPAN 1, 1A, 1B, 2, 2A, 2B, 3, 3A, 3B, 5, 5S, 6A, 6B, 7, 10A, 10B, 10C, 10D, 22A, 22B, 22C, 31, 31A, 31B, 32,
32A, 32B, 42. Keys follow the same pattern, `div:nth-of-type(1)` to `div:nth-of-type(28)` as the 9th step.

Signals: none. This page names many SPAN codes in prerequisites ("SPAN 1A" three times), but they are all inside
blocks. `duplicate-occurrence` counts found courses, not mentions, so the repeats don't count.

### Studio links

The locator's route id is `locator-course-page` (the Rules tab reads the rule id from the path,
`web/src/rules/RulesTab.tsx:126`, and the row from `?row=`, `:127`; `web/src/shell/router.ts:16-29`). The link
`#/c/ccsf/rules/course-page` opens the **page rule**, whose rows are pages (`?row=<page stem>`).

- Locator, INTD 100 (block 1 of 3):
  https://golden-rules-studio.mlops-club.org/#/c/ccsf/rules/locator-course-page?row=ccsf-curricunet-com-catalog-iq-courses-3-102-3ecab791c0%40html+%3E+body%3Anth-of-type%281%29+%3E+div%3Anth-of-type%283%29+%3E+div%3Anth-of-type%281%29+%3E+div%3Anth-of-type%283%29+%3E+article%3Anth-of-type%281%29+%3E+ol%3Anth-of-type%281%29+%3E+div%3Anth-of-type%281%29+%3E+div%3Anth-of-type%281%29+%3E+div%3Anth-of-type%281%29+%3E+div%3Anth-of-type%281%29+%3E+div%3Anth-of-type%281%29
- Locator, INTD 102 (block 2 of 3):
  https://golden-rules-studio.mlops-club.org/#/c/ccsf/rules/locator-course-page?row=ccsf-curricunet-com-catalog-iq-courses-3-102-3ecab791c0%40html+%3E+body%3Anth-of-type%281%29+%3E+div%3Anth-of-type%283%29+%3E+div%3Anth-of-type%281%29+%3E+div%3Anth-of-type%283%29+%3E+article%3Anth-of-type%281%29+%3E+ol%3Anth-of-type%281%29+%3E+div%3Anth-of-type%281%29+%3E+div%3Anth-of-type%281%29+%3E+div%3Anth-of-type%282%29+%3E+div%3Anth-of-type%281%29+%3E+div%3Anth-of-type%281%29
- Locator, SPAN 1 (block 1 of 28):
  https://golden-rules-studio.mlops-club.org/#/c/ccsf/rules/locator-course-page?row=ccsf-curricunet-com-catalog-iq-courses-3-155-b4b7757633%40html+%3E+body%3Anth-of-type%281%29+%3E+div%3Anth-of-type%283%29+%3E+div%3Anth-of-type%281%29+%3E+div%3Anth-of-type%283%29+%3E+article%3Anth-of-type%281%29+%3E+ol%3Anth-of-type%281%29+%3E+div%3Anth-of-type%281%29+%3E+div%3Anth-of-type%281%29+%3E+div%3Anth-of-type%281%29+%3E+div%3Anth-of-type%281%29+%3E+div%3Anth-of-type%281%29
- Page rule, Interior Design page: https://golden-rules-studio.mlops-club.org/#/c/ccsf/rules/course-page?row=ccsf-curricunet-com-catalog-iq-courses-3-102-3ecab791c0
- Page rule, Spanish page: https://golden-rules-studio.mlops-club.org/#/c/ccsf/rules/course-page?row=ccsf-curricunet-com-catalog-iq-courses-3-155-b4b7757633

## Q8.3: rows today

- Locator rows are one per occurrence, keyed by `occurrence_key` (`src/golden_datasets/review.py:9, 211-220`).
- `occurrence_key` = `<page stem>@<css path of the block>` (`src/golden_datasets/engine.py:518-519`).
- So the Interior Design page gives 3 rows and the Spanish page gives 28. Each row's context column is the page title,
  which is "View - CurriQunet META" on every CCSF page (`review.py:220`). The rows don't name the department.
- The page preview outlines every block on the page and numbers them (`routes_review.py:476-493`); only the selected
  row's block is filled (`render.py:63-64`).
- Page signals are attached to **every** locator row of that page (`review.py:213-214`). If an uncovered-code or
  block-count signal ever fires on a 110-course page, it shows on all 110 rows.

## Blind spots (not false alarms)

These make the signals miss things on CCSF. They never make them fire wrongly.

| Blind spot | Effect | Where |
|---|---|---|
| The page text joins blocks with no space: "Interior DesignINTD 100", "Fall 2022INTD 102". `\b` fails before the code. | The page-level code list sees almost none of the courses: on the Interior Design page it finds only "ESL 188A". This list only feeds `unclassified-page-with-codes`, which needs 5+ codes. | `engine.py:80-110`, `signals.py:79-80` |
| CCSF's pattern allows 1-3 digits. 192 of 1,927 codes are noncredit 4-digit codes (TICU 5000, BOSS 4510). Only 1,555 of 1,927 found codes fully match the pattern. | A missed 4-digit course between blocks would not raise `uncovered-code`. | `rs.settings.signals.course_code_pattern` |
| `uncovered-code` scans only inside the blocks' shared container. | A course block outside that container, e.g. a second list lower on the page, would be missed silently. | `signals.py:99-103` |
