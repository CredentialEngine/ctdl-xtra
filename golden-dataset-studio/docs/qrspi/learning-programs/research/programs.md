# Program pages: course lines, programs across pages, credits, language

Research for wave 2, 2026-11-24.

- **Measured vs estimated:** every number is measured unless it is marked (est.).
- **Source:** the Studio root copies of the five crawls.
- **"Program pages":** the pages matched by each catalog's `program-page` rule in ruleset v1. That is AVC 197,
  CCSF 333, Marshall 647, UALR 1,111 and WVU 727.

## 1. Course lines on program pages: history only

**Where the rules came from.** Three Course rules came in from the review-ui-v2 import (`label-course-on-program-page`)
in ruleset v1, on 2026-10-27:
- **`program-page`:** labelled the page "Program".
- **`program-page-with-courses`:** labelled the same page "Course".
- **`locator-program-requirement`:** made each course row in a program's requirements one Course occurrence. The row
  selectors were:
  - CourseLeaf: `table.sc_courselist tr`
  - Acalog: `li.acalog-course`
  - CCSF: `.course-entry`
  - AVC: `.new-rule`
- **`stub-*` rules:** four of them read the row's code and title. They read nothing else.

| Program page | Row | Golden Course |
|---|---|---|
| AVC `program/economics-aa-t-fall-2026` | "BUS201H - Business Law Honors" | BUS201H. It also has a course page. |
| Marshall `graduate/programs-az/health-professions/nursing-msn/nurse-midwifery-emphasis/` | "NM 610 · Primary Care of Women" | NM610. It has no course page. |
| UALR `preview_program.php?catoid=42&poid=10566` (Public History, M.A.) | "HIST 58133 - Seminar in Arkansas History" | HIST58133. It has no course page. |
| AVC `program/high-intermediate-esl-certificate-noncredit-fall-2023` | "ESL040 - ESL Vocabulary & Pronunciation 4" | ESL040. It has no course page. |

| Catalog | Row occurrences | Program pages | Distinct course keys | Keys with no course page |
|---|---|---|---|---|
| AVC | 2,751 | 197 | 920 | 13 |
| Marshall | 9,738 | 465 | 2,739 | 37 |
| UALR | 17,294 | 893 | 1,699 | 4 |
| WVU | 16,953 | 720 | 5,063 | 56 |
| CCSF | 6,071 | 334 | 1,591 | 47 |

**Why it happened.** The rule labelled every row it found; nothing was trying to fill gaps. Over 97% of these keys
are courses that also have their own page. The few without one are explained by:
- **Old program versions:** AVC renumbered its ESL courses since 2023.
- **Subjects with no course pages crawled:** Marshall has no `courses-az/nm` page.
- **The incomplete CCSF crawl** (est.).

**Status: removed.** Ruleset v2 (AVC v3), also published 2026-10-27, dropped all of these rules with the note "program
requirement lines aren't courses (out of scope)". The latest golden sets have no values from these rules. Two things
are left over:
1. All five latest rulesets still carry `settings.course_key_rule: {"locator-program-requirement": "stub-code"}`. This
   setting is stale.
2. WVU's `undergraduate/schoolofdentistry/` page is both a course page and a program page. 45 golden records come from
   it, and Jared marked 3 stub values on it "wrong".

## 2. One program on several pages, or several programs on one page

| Catalog | Pattern |
|---|---|
| AVC | One page per program. Department pages list program names only. |
| CCSF | One page per program, with no duplicate titles among 333 pages. |
| UALR | 319 programs saved as 1,111 copies. The copies differ only in a "Return to: …" line, so de-duplicate on (catoid, poid). 47 are concentration, track or emphasis variants, each with its own poid and restating the whole degree. |
| Marshall | 155 emphasis pages are split from their parent degree. `accountancy-ms/` holds the description and "Total Credit Hours 30", while `…/tax-compliance-planning-emphasis/` prints only "Select nine hours from the following courses: 9". Of the 155, 64 restate the degree total, 62 print a smaller total and 29 print none. |
| WVU | Department overview pages hold the Major Codes. The program's own page holds its requirements and prints no code. 18 overview pages have 36 tabs that say "please see the link to the right". 27 pages print two or more Major Codes. |

**Example (WVU).** `graduate/eberlycollegeofartsandsciences/english/` prints:

> M.A. Major Code: 1442 M.A. in Professional Writing and Editing Major Code: 1481 M.F.A. Major Code: 1486 Ph.D. Major
> Code: 1442

The English M.A.'s requirements and "Total Hours 30" are on `…/english/ma/`, which prints no code. The page also
gives **the same code, 1442, to the M.A. and the Ph.D.**

## 3. Credit Value

All five catalogs use semester-type credit:
- CCSF and AVC say "units".
- Marshall, UALR and WVU say "(credit) hours".

| Catalog | Verbatim | Proposed golden value |
|---|---|---|
| AVC | "Anthropology AA-T (Total 24 - 30)" (major only). The description says "Completion of 60 semester units". 48 of 197 print a range. | min 24, max 30 (the page's labelled program total), or 60, depending on the decision in §4 |
| AVC | Noncredit: "Required Courses (Total 180)" … "Total Hours 180.0" (25 pages) | Clock hours, not credit: no creditValue |
| CCSF | "Total : 30.0" (major only, per the page's note; 332 pages) | 30 units |
| CCSF | "Art History – AA-T … Total : 18.0- 19.0" (113 ranges). Noncredit: "Total : 700.0" hours (22 pages) | min 18, max 19. Noncredit is like AVC's. |
| Marshall | "Japanese, B.A. … Total Credit Hours 120" (430 pages) | 120 credit hours |
| Marshall | "Environmental Science, Minor … Total Credit Hours 17-19" (84 ranges). Nursing M.S.N.: "minimum of 42 credit hours and 780 clinical hours" | min 17, max 19. For the M.S.N., 42 (clinical hours are not credit). |
| UALR | Accounting, B.B.A.: "(120 total minimum hours …)", "Major (79 hours)". Only 2 of 319 print a "Total Hours" label. | 120 |
| UALR | "The minor consists of 18 credit hours" | 18 |
| WVU | "Total Hours 120" | 120 |
| WVU | The general education block "Total Hours 31-37" (on 225 pages). A Ph.D. page prints both "Total Hours 60" and "42". | The block is not the program total. For the Ph.D., min 42, max 60. |

## 4. Language of instruction

A regex for "language of instruction", "taught/offered/conducted in <language>" and "bilingual" over the visible
program-page text found:

| Catalog | Pages with a hit |
|---|---|
| AVC | 0 of 197 |
| Marshall | 10 of 647 |
| UALR | 2 of 1,111 |
| WVU | 5 of 727 |
| CCSF | 10 of 333 |

None of these hits states the program's own language. They are about a course (Marshall's French minor: "One course
must be taught in French"), an admission requirement, or the subject itself. The only language signal is
`<html lang="en">`.

**Scripts:** in the session scratchpad (`scripts/prog_lines.py`, `examples.py`, `multi.py`, `wvu_all.py`,
`credits.py`).
