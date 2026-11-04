# R: what the live annotation log says (2026-11-04)

Read from the live annotation log and the latest extraction of each catalog, on 2026-11-04 around 18:45Z. Nothing was
written. Times are UTC. "Latest wins" means the newest live verdict per row (rule + course occurrence).

Log sizes: AVC 301 events, CCSF 590, Marshall 579, UALR 134, WVU 718. UARK has no log yet.

---

## 1. Q10.5: `estimatedDuration` and `creditValue` child rules

**Short answer:** nobody has ever annotated an `estimatedDuration` rule, in any catalog. The `creditValue` children
have exactly 3 annotations, all from Jared, all on AVC course ACCT199, all ✓, made today within 25 seconds. Plus one ✗
on the parent `course-credit-value` (same course).

### Annotations (every catalog, every rule version)

| Catalog | Rule | Annotation | Verdict | Annotator | Time | Value seen |
|---|---|---|---|---|---|---|
| AVC | `course-credit-value-min-value` | an-36cd4d162732 | ✓ | Jared Diener | 2026-11-04 15:33:52 | `1.0` |
| AVC | `course-credit-value-max-value` | an-0ea61300b70b | ✓ | Jared Diener | 2026-11-04 15:34:01 | `8.0` |
| AVC | `course-credit-value-credit-unit-type` | an-ec1403349d8b | ✓ | Jared Diener | 2026-11-04 15:34:17 | `Units` |
| AVC | `course-credit-value` (parent) | an-718755f023ce | ✗ | Jared Diener | 2026-11-04 16:40:19 | `1.0 - 8.0 Units` |

The ✗ on the parent has no expected value. Its note: "There should be no values for this property. ceterms:creditValue
takes the sub-class Value Profile. This information for Credit Value will be values for the properties associated with
the Value Profile."

No other catalog has any annotation on these rules. Zero annotations on any `course-estimated-duration*` rule.

### The rules and their rows (latest extraction)

"rows" = courses; "found" = rows with a value; "values" = list items (list rules have several per row). "no rule
yet" rules have a row per course and no values.

| Rule | AVC (rs-0008) | CCSF (rs-0006) | Marshall (rs-0006) | UALR (rs-0006) | WVU (rs-0006) |
|---|---|---|---|---|---|
| `course-estimated-duration` | 1,062 found, 4,248 values (list) | 1,927 found, 2,310 values (list) | no rule yet (6,692) | 623 / 3,130 found, 799 values (list) | 322 / 22,023 found, 421 values (list) |
| `…-description` | 1,062 found, 4,248 values (list) | 1,735 / 1,927 found, 2,118 values (list) | no rule yet | 623 / 3,130, 799 values (list) | 322 / 22,023, 421 values (list) |
| `…-time-required` | 1,062 found, 4,248 values (list) | 1,927 found, 2,310 values (list) | no rule yet | no rule yet | 322 / 22,023, 421 values (list) |
| `…-exact-duration` | no rule yet (1,062) | no rule yet (1,927) | no rule yet | no rule yet (3,130) | no rule yet (22,023) |
| `…-minimum-duration` | no rule yet | no rule yet | no rule yet | no rule yet | no rule yet |
| `…-maximum-duration` | no rule yet | no rule yet | no rule yet | no rule yet | no rule yet |
| `course-credit-value` | 1,062 / 1,062 | 1,927 / 1,927 | 6,692 / 6,692 | 3,044 / 3,130 | 22,023 / 22,023 |
| `…-credit-unit-type` | 1,062 / 1,062 | no rule yet (1,927) | 6,692 / 6,692 | 3,044 / 3,130 | 22,023 / 22,023 |
| `…-min-value` | 1,062 / 1,062 | 30 / 1,927 | 2,008 / 6,692 | 195 / 3,130 | 7,685 / 22,023 |
| `…-max-value` | 1,062 / 1,062 | 30 / 1,927 | 2,008 / 6,692 | 195 / 3,130 | 7,685 / 22,023 |

(`course-is-non-credit` exists too but is its own property, not a `creditValue` child.)

**Used how much:** effectively not at all. 3 ✓ on one course, against tens of thousands of rows. Replacing the child
rules loses no meaningful review work; the 3 ✓ and the parent ✗ can be shown as hints, as the Q10.5 default says.

---

## 2. Q1.4: ✗ with an expected value on a property row where the rule found nothing

**Short answer:** this has not happened yet. No annotation in any catalog has an expected value on a row where the
rule found nothing. All 7 annotations with an expected value are on rows that had a value (6 AVC `course-description`
fixes, by Jared on 2026-10-21 and Eric on 2026-10-29).

**The closest real case** (good for a screenshot): Jared marked a no-value row ✗ and typed the answer into the note
instead of selecting it on the page.

| | |
|---|---|
| Catalog | AVC |
| Rule | `course-in-catalog` (In Catalog, `ceterms:inCatalog`, no rule yet) |
| Course | ACCT199 |
| Page | https://avc.elumenapp.com/catalog/2026-27/course/acct199 |
| Annotation | an-441bd81433b2, ✗, Jared Diener, 2026-11-04 15:25:55 |
| Expected | none |
| Note | `https://avc.elumenapp.com/catalog/2026-27/course/acct199` |

Studio URL:
https://golden-rules-studio.mlops-club.org/#/c/avc/rules/course-in-catalog?row=avc-elumenapp-com-catalog-2026-27-course-acct199-02f732419a%40html+%3E+body%3Anth-of-type%281%29+%3E+app-root%3Anth-of-type%281%29+%3E+app-public%3Anth-of-type%281%29+%3E+div%3Anth-of-type%282%29+%3E+div%3Anth-of-type%282%29+%3E+div%3Anth-of-type%282%29+%3E+main%3Anth-of-type%281%29+%3E+div%3Anth-of-type%284%29

A second one, same course: an-822d94938a8d, ✗ on `course-entry-condition` (no rule yet), Jared Diener,
2026-11-04 15:35:19, no expected value, no note.

Studio URL:
https://golden-rules-studio.mlops-club.org/#/c/avc/rules/course-entry-condition?row=avc-elumenapp-com-catalog-2026-27-course-acct199-02f732419a%40html+%3E+body%3Anth-of-type%281%29+%3E+app-root%3Anth-of-type%281%29+%3E+app-public%3Anth-of-type%281%29+%3E+div%3Anth-of-type%282%29+%3E+div%3Anth-of-type%282%29+%3E+div%3Anth-of-type%282%29+%3E+main%3Anth-of-type%281%29+%3E+div%3Anth-of-type%284%29

**Would an expected value reach the golden dataset? No** (`golden.py:142-171`):
- The loop walks the extraction's matches only, and skips any match whose status isn't `found` (line 156). A "no rule
  yet" rule has no matches at all.
- The value published is always `m["value"]`, the rule's value. `golden.py` never reads `expected`.
- A ✗ only makes a value human-reviewed after the rule changes to produce the expected text (state `fixed`,
  `review.py` `_carry`).
- Side note: the same holds on found rows. A row marked ✗ (with or without an expected value) still publishes the
  rule's value, approved by the rule.

---

## 3. Q1.2: AVC `course-entry-condition-description`, ACCT199

**History** (the only two events on this row):

| Annotation | Time | Verdict | Expected | Note | Supersedes |
|---|---|---|---|---|---|
| an-3b5283f5daeb | 2026-11-04 16:28:06 | ✓ correct | none | none | none |
| an-362cba1649b5 | 2026-11-04 16:30:03 | ✗ wrong | none | the extracted value, 378 characters, identical | an-3b5283f5daeb |

Both by Jared Diener (sme), on rule v2, extraction rs-0008.

**Extracted value (now, unchanged):** "LIMITATION ON ENROLLMENT: To participate in work experience education, students must
have a paid or unpaid job or internship and have approval of a work supervisor and the instructor supervising the work
experience in the specific subject area. Students must also attend a scheduled orientation or meet individually with
the supervising instructor for an individual orientation." (characters 9-387 of its element.)

**What the row shows now:** ✗ wrong (red), from an-362cba1649b5. The ✓ is superseded, so it is history only. The row
is not human-reviewed.

**Page:** https://avc.elumenapp.com/catalog/2026-27/course/acct199

**Studio URL:**
https://golden-rules-studio.mlops-club.org/#/c/avc/rules/course-entry-condition-description?row=avc-elumenapp-com-catalog-2026-27-course-acct199-02f732419a%40html+%3E+body%3Anth-of-type%281%29+%3E+app-root%3Anth-of-type%281%29+%3E+app-public%3Anth-of-type%281%29+%3E+div%3Anth-of-type%282%29+%3E+div%3Anth-of-type%282%29+%3E+div%3Anth-of-type%282%29+%3E+main%3Anth-of-type%281%29+%3E+div%3Anth-of-type%284%29

**Did this ✗ alone make the rule "needs work"? Yes.**
- The rule has 1,062 rows, 201 with a value. 4 rows are reviewed. ACCT199 is its only open ✗ (`open_wrong: 1`).
- How the set is chosen: `Review._rule_status` (`review.py:529-559`). A rule is "needs work" when it isn't approved
  for its current version and has at least one open row: a row in state `wrong`, `still-wrong` or `missing`, a list item
  marked wrong, or an open missing item / missing record. One open row is enough.
- The Claude prompt and the agent run take every rule with that status (`prompt.py:102`).
- The agent run 20261104T163408Z-f428 (started 16:34:08, 4 minutes after the ✗; it failed) had scope "needs work" with
  these 5 rules: `course-description`, `course-entry-condition`, `course-entry-condition-description`,
  `course-in-catalog`, `course-subject-webpage`.
- Since then `course-credit-value` also needs work (Jared's ✗ at 16:40:19), so AVC has 6 such rules now.

---

## 4. Rows where the rule found nothing

A property row has no value when its status is `no_match` (the selector found nothing), `empty` (found an element,
no text), or `none` (no rule yet).

**Annotations on rows with no value when annotated**, every catalog:

| Catalog | Verdict | Count | Where from | Rules |
|---|---|---|---|---|
| AVC | ✗ | 2 | Studio, Jared Diener, 2026-11-04 | `course-in-catalog`, `course-entry-condition` (both no rule yet, ACCT199) |
| Marshall | ✓ | 14 | imported from review UI v2 (Seth, 2026-10-23) | `course-description` (13 `no_match`, 1 `empty`) |
| CCSF | ✓ | 1 | imported from review UI v2 (Jared, 2026-10-22) | `course-description`, STATC1000E (`empty`) |
| others | | 0 | | |

So 17 in total: 15 ✓ (all imported; "nothing here is correct") and 2 ✗ (Studio). No "missing" verdicts, no comments,
no ✗ with an expected value. None of these has a note saying the property isn't on the page; the one with a note is
the `course-in-catalog` ✗ above, whose note is the value Jared wanted.

Separately, WVU has 3 imported ✗ on rows that had a value then and have no row in the current extraction.

**Examples:**

1. Marshall, `course-description`, WS483, ✓ by Seth 2026-10-23 15:09:53 (an-29c9b01440af, imported). The rule finds
   nothing (`no_match`); Seth accepted "no description" as correct. Page:
   https://catalog.marshall.edu/undergraduate/courses-az/ws/. Studio URL:
   https://golden-rules-studio.mlops-club.org/#/c/marshall/rules/course-description?row=catalog-marshall-edu-undergraduate-courses-az-ws-d237b66e12%40html+%3E+body%3Anth-of-type%281%29+%3E+section%3Anth-of-type%281%29+%3E+div%3Anth-of-type%281%29+%3E+div%3Anth-of-type%282%29+%3E+main%3Anth-of-type%281%29+%3E+div%3Anth-of-type%281%29+%3E+div%3Anth-of-type%281%29+%3E+div%3Anth-of-type%281%29
2. AVC, `course-credit-value`, ACCT199, ✗ on a found value (`1.0 - 8.0 Units`), Jared Diener 2026-11-04 16:40:19:
   "There should be no values for this property. ceterms:creditValue takes the sub-class Value Profile…". The text is
   on the page, but the property should have no flat value. This is the only ✗ meaning "this property should be
   empty".
3. Marshall, page-rule questions by Seth, 2026-10-23: "No data was extracted from page. Unable to add description,
   admission requirements, etc." (an-3b69462d6741, 16:07:08) and "No values were extracted from page. Unable to add
   description, webpage, connected programs, etc." (an-3b683d230762, 16:08:21). These are program pages, not course
   rows, but show reviewers flagging "nothing extracted".

No note anywhere says "the property isn't on the page" about a found value.

**How the UI labels a no-value row today:**
- Rules tab row (`RulesTab.tsx:532`): "nothing found" (`no_match`), "no rule yet" (`none`), "empty" (`empty`), shown
  greyed (`val empty`).
- Rules tab page pane caption (`RulesTab.tsx:474`): "no rule yet." or "this rule found nothing on this page."
- Mark-wrong form (`parts.tsx:75`): "(the rule found nothing here; select the value the page shows)".
- Records tab (`RecordsTab.tsx:216`): "no rule yet" or "nothing found" (both `no_match` and `empty`).
- Value diff (`ValueDiff.tsx:62`): "no value". Evals tab: "no values" / "no values · no rule created yet".
- Source view (`SourceView.tsx:91`): "Not found: <css path>".
- There is no verdict meaning "correct: this property isn't on the page"; reviewers use ✓ on the empty row.

---

## 5. `GET /annotators` 500 (KeyError in `_Recent`)

It happened **once** in the server log available (2026-11-03 22:42Z to now): 1 of 131 `/annotators` requests.

```
2026-11-04T16:26:36Z "GET /api/catalogs/avc/annotators HTTP/1.1" 500 Internal Server Error
  routes_review.py:469 annotators → review.py:663 people → review.py:632 annotations → review.py:178 rows
  → review.py:75 __setitem__: del self[next(iter(self))]
KeyError: 'course-keyword'
```

The KeyError is raised by the eviction in `_Recent.__setitem__`, not by a lookup: the oldest key disappeared between
`next(iter(self))` and `del`. That points to two request threads evicting from the same snapshot's row cache at once
(sync endpoints run in a thread pool; `_Recent` has no lock). `rows()` also checks `in` and then reads, which can
fail the same way if another thread evicts in between.
