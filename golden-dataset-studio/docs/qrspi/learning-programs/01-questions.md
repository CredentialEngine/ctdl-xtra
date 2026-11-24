# Q — Questions: Learning Program, the Studio's second class

Phase 1 of QRSPI (questions, research, structure, plan, implement) for **adding `ceterms:LearningProgram` to the
Golden Dataset Studio**. Until now every part of the Studio assumes one class, Course: the property list, the rule
ids, the golden record key, the Rules and Records tabs, the AI run reports, and the scorer. Learning Program is the
first of five classes, so the choices made here set the pattern for the other four.

- Original prompt and the resources it pointed to: [`prompt.md`](prompt.md)
- The sheet's Learning Program tab as read on 2026-11-23: [`learning-program-properties-2026-11-23.csv`](learning-program-properties-2026-11-23.csv).
  The Course tab, read on the same day: [`course-properties-2026-11-23.csv`](course-properties-2026-11-23.csv)
- Story: [#455](https://github.com/CredentialEngine/ctdl-xtra/issues/455) (sources and property list). Parent step:
  [#416](https://github.com/CredentialEngine/ctdl-xtra/issues/416) "Configure Studio to implement the class". Epic:
  [#401](https://github.com/CredentialEngine/ctdl-xtra/issues/401)
- Asked: 2026-11-23. Each question has a **Default**, which research works from until you answer. Notes from Claude
  are marked **Note**.

---

## What I already looked at

These facts shape the questions below. Each one is checked against the sheet, the issues, or the code.

1. **The five Learning Program sources are the same five catalogs Studio already has for courses.** Issue #455 lists
   Antelope Valley, City College of San Francisco, Marshall, UA Little Rock and West Virginia University. These are
   the five entries in `src/golden_datasets/catalogs.py`. So this work doesn't add new catalogs. **Each existing
   catalog gets a second class.**

2. **The sheet's tabs have been renamed, and Studio's property sync will break.** `golden-datasets properties sync`
   reads tabs named `Phase 1 Extraction` and `Course` (`properties.py`, `PHASE1_TAB, COURSE_TAB`). The sheet now has
   `Course Properties`, `Learning Program Properties`, `Prerequisite Mapping` and `PR with Alternative Conditions`.
   Neither old tab name exists any more.

3. **The sheet has no "required" column.** Column A is "xTRA Status", and its values are `Phase 1` or `Phase 2`. The
   Learning Program tab has 13 Phase 1 rows and 21 Phase 2 rows:

   | Phase 1 (13 rows) | Phase 2 (21 rows) |
   |---|---|
   | External Identifier, Name, Description, Subject Webpage, Life Cycle Status Type, Language, In Catalog, Is Non-Credit, Credit Value (with Value, Min Value, Max Value, Credit Unit Type) | Available At, Available Online At, Availability Listing, Audience Level Type, Date Effective, Approximate Date Effective, Delivery Type (+ Description), Learning Method Type (+ Description), Content Description, Subject, Entry Condition (+ Description, Target Learning Opportunity), Estimated Duration (+ Description, Exact, Minimum, Maximum, Time Required) |

   For courses, "Phase 1" is not the same as "required". The Course tab also marks In Catalog, Is Non-Credit and
   Credit Value as Phase 1. But Studio's Required group holds only seven properties: Learning Type, External
   Identifier, Name, Description, Subject Webpage, Life Cycle Status Type and Language. Coded Notation sits at the top
   of that group as the course key.

4. **The sheet and the issues list different properties.**
   - Issue #415 lists Coded Notation and Prerequisite as Learning Program properties. Neither is on the Learning
     Program tab.
   - Jared's comment on #359 describes the scope as "Required properties, In Catalog, Credit Value and properties
     associated with subclass Value Profile". That fits the Phase 1 rows.

5. **The Learning Program tab has columns the Course tab doesn't:** Value Type, Extraction Notes and CTDL
   Transformation Notes. Some rows differ from the Course version of the same property:
   - External Identifier is `Multiple` for programs and `Single` for courses.
   - The Sample column is copied from the course rows ("BIOL20003", "General Microbiology", "This course guides
     students…").
   - Available At (`ceterms:availableAt`) has no CLI Extraction Label. In its place is a question: *"The value is
     ceterms:Place. Should we attempt to extract properties for Place, or simply extract the verbatim text and handle
     Place during transformation?"*

6. **The course is wired in deep.** Every rule id starts with `course-`. The golden record key is `course_key` (the
   Coded Notation value) in `engine.py`, `golden.py`, `facets.py`, `check.py`, annotations and agent runs. Learning
   Type is a constant rule whose value is always `Course`. Storage keeps one rule history, one ruleset and one AI run
   lock per catalog, with no class in the path (`layout.py`). The heaviest "course" references in the code are in the
   report (`report.py`, `Report.tsx`), the prompt (`prompt.py`), review routes and the Records tab.

7. **xtra-cli already has a notion of a learning program, and it is narrower than "a program page".** Its README
   classifies a page as `LearningOpportunity → ceterms:LearningProgram` only when *"the page prints its own
   requirements and names no award (a minor, a pre-professional track, a non-credit program…)"*. A page that names an
   award, such as "B.S. in Biology", is a `Credential`. Most catalog program pages name a degree or certificate.

---

## Part A: the class and its first rules

**A1. Which Learning Program properties are "minimum", and get the Required treatment?**
For courses, the Required group sits at the top of the Rules tab, and those properties lead every Records row. The
sheet doesn't say which Learning Program properties are required (fact 3).
- **Default:** the same six CTDL properties as courses (External Identifier, Name, Description, Subject Webpage,
  Life Cycle Status Type, Language), plus Learning Type. The other Phase 1 rows (In Catalog, Is Non-Credit, Credit
  Value and its four children) come next. Phase 2 rows go below those.

**A2. Should the Rules tab show three tiers (Required, the rest of Phase 1, Phase 2) or two (Required, everything else)?**
Courses have two tiers today. The new sheet adds a Phase column to both tabs.
- **Default:** keep two tiers, so the Rules tab looks the same for both classes. Phase is shown only as a tooltip.

**A3. Do Phase 2 properties get rules now, or later?**
Your prompt says "put all the fields in there", the same as courses. Issue #401 says phase 1 benchmarking.
- **Default:** every row of the tab becomes a rule, the same as courses. Phase 2 rules start empty.

**A4. What identifies one learning program, the way Coded Notation identifies a course?**
Golden records for courses are keyed by Coded Notation, such as `BIOL 20003`. Programs often have no code, and the
Learning Program tab doesn't list Coded Notation (fact 4). Candidates are:
- a program code, where the catalog prints one
- the program's URL (`subjectWebpage`)
- the normalized name
- Name together with the award level
- **Default:** the subject webpage URL, because every program has its own page. A code is used when the catalog
  prints one.

**A5. Is Coded Notation a Learning Program property?** It is in issue #415 but not on the sheet (fact 4).
- **Default:** no, follow the sheet. Ask Jared whether to add it.

**A6. Is Prerequisite a Learning Program property?** Issue #415 lists it, and the sheet has two prerequisite tabs. The
Learning Program tab itself has Entry Condition instead.
- **Default:** no. Entry Condition stands in for it for programs. The two prerequisite tabs are about courses.

**A7. What does Learning Type hold for programs?** The constant Learning Type rule says `Course` today.
- **Default:** `Learning Program`. It becomes the column that tells the two classes apart in exports.

**A8. Available At (`ceterms:Place`): verbatim text, or structured Place fields?** The sheet asks this itself (fact 5).
- **Default:** verbatim text, one value per location. Turning it into a Place happens at transformation. This
  matches how Estimated Duration and the condition profiles were handled for courses.

**A9. Rule ids: `program-…` alongside `course-…`, or one id shared by both classes for the same CTDL path?**
For example, `ceterms:name` would be either `program-name` or a single `name` rule with a class.
- **Default:** a separate id per class (`program-name`). The same CTDL path means different things on a course page
  and on a program page, and each class gets its own rule history.

**A10. Can a course rule be used as the starting point for its program twin?** Name, Description, Credit Value and
the other shared properties already have course rules on all five catalogs.
- **Default:** no automatic copy. An AI run may read the course rule as a hint.

---

## Part B: what counts as a learning program page

**A page decides which class its record belongs to.** These questions settle which pages are learning programs.

**B1. A program page names a degree, such as "Biology, B.S.". Is that a Learning Program, a Credential, or both?**
xtra-cli calls it a Credential and does not make a Learning Program from it (fact 7). If Studio follows xtra-cli,
most program pages in these catalogs would produce no Learning Program at all.
- **Default:** treat it as a Learning Program for this work (the programme of study), and note that the Credential
  class will claim the same page later. Ask Jared and Jeanne to confirm.

**B2. Do minors, concentrations, emphases, certificates and tracks each count as a separate learning program?**
- **Default:** yes, one record per program the catalog lists on its own page or under its own heading.

**B3. Some catalogs print several programs on one page, such as a department page that holds a major, a minor and a
certificate. Is that one page with many records?** Courses already work this way: a course block is one record. Issue
[#116](https://github.com/CredentialEngine/ctdl-xtra/issues/116) reports the opposite problem, where one program is
split across several pages.
- **Default:** yes, a record locator picks out one program on a page, the same way course blocks are found. A program
  that spans pages (a requirements page and an overview page) is out of scope for now.

**B4. Do we have program pages crawled for the five catalogs, or do they need a new crawl?** The current crawls were
made for course pages. Issue #416 has a "crawl the sources" checkbox.
- **Default:** research checks each catalog's crawl for program pages (E2). Any catalog without them gets a new crawl
  from xtra-cli.

---

## Part C: one Studio, more than one class (UI)

The questions here apply to all five classes, not only Learning Program. Following the minimalism rule, each one asks
which existing element changes, not which new one gets added.

**C1. Where does someone choose the class?** Options:
1. a class switcher next to the catalog picker in the top bar, so that every tab shows one class at a time
2. a class filter on the Rules and Records tabs only
3. no switcher: both classes are mixed on each tab and grouped by class
- **Default:** option 1. The class sits next to the catalog in the top bar and the URL, such as
  `/catalog-wvu-edu/program/rules`. It is remembered per reviewer. Every tab then reads as it does today.

**C2. Catalogs list: one row per catalog or one row per catalog × class?** It shows status and counts per catalog
today.
- **Default:** one row per catalog, with a small count per class inside the row.

**C3. Records tab: a program record has no course code. What leads the row?** A course row today opens with the
course code and name.
- **Default:** the program name, with its URL as a tooltip.

**C4. Evals and scores: one score per catalog, or one per catalog × class?**
- **Default:** one per catalog × class. Course and program numbers are never added together.

**C5. AI runs: does a run work on one class at a time?** Today each catalog has one run lock, and the report is
written about courses ("12 courses changed").
- **Default:** yes, a run works on one class. Its report says "programs" and is checked for leftover "course"
  wording. Should a course run and a program run on the same catalog be able to run at the same time?
  **Default:** yes. The lock moves to catalog × class.

**C6. The Golden tab: a program golden dataset is published on its own, with its own version numbers.**
- **Default:** yes, one golden version per catalog × class.

**C7. Are there parts of the UI that should stay course-only for now?** For example, the course-code collision list
on the Golden tab (two course pages with the same code but different names) only makes sense for courses.
- **Default:** hide anything that is course-only when the class is Learning Program, instead of making a program
  version of it.

**C8. Which word is shown in the UI: "Learning Program", "Program" or "LearningProgram"?**
- **Default:** "Program" on buttons and labels, and "Learning Program" in headings and tooltips.

---

## Part D: the CLI and storage

**D1. Where does the class appear in storage paths?** Today the paths are `rules/<rule_id>/…`, `rulesets/vNNNN.json`,
`golden/ruleset-vN/`, `agent-runs/` and `scores/`, all per catalog (`layout.py`).
- **Default:** add a class folder under each catalog, such as `<catalog>/golden-dataset-studio/program/…`. Course
  data moves to `course/…` with a one-time migration. This keeps every per-catalog rule (ruleset version, run lock,
  score) as it is, but per catalog × class.

**D2. Does every CLI command take `--class`?** It would default to `course`, so scripts and the deploy keep working.
- **Default:** yes. `--class` sits beside `--catalog` and can also come from `GOLDEN_DATASETS_CLASS`, the same way
  `GOLDEN_DATASETS_CATALOG` works today.

**D3. One `properties.csv` with a class column, or one file per class?** Today one file holds all course rows, and it
is written by `properties sync` from the sheet.
- **Default:** one file per class (`properties/course.csv`, `properties/program.csv`), each synced from its own tab.
  The sync is fixed for the renamed tabs (fact 2).

**D4. Is the record key renamed from `course_key` to a neutral name, such as `record_key`, across the data?**
It appears in the parquet files, the annotations and `check.py`'s foreign keys.
- **Default:** yes. Migrate it once, while there is a single class, rather than carry both names.

**D5. Does the xtra scorer library (used by Evals and `xtra score`) score learning programs?**
- **Default:** research checks this (E6). If it doesn't, Studio scores programs with its own field-by-field
  comparison until the library does.

**D6. Is changing xtra-cli in scope?** It was out of scope for the course work.
- **Default:** no. Studio reads xtra-cli's crawls as they are. If the crawl or the classification of program pages
  (B1) needs to change, that becomes a separate xtra-cli story.

---

## Part E: facts to gather in research (no answer needed unless you know)

These check assumptions above. Research answers each one with evidence.

- **E1.** For each catalog, the number of program pages there are and the platform's program URL pattern:
  CourseLeaf `/programs/…` at Marshall, WVU and UALR, eLumen at AVC, CurricUNET at CCSF.
- **E2.** Whether the current crawls already hold program pages, and how many (B4).
- **E3.** What a program page looks like on each platform, and which Phase 1 properties it actually prints. Credit
  Value is likely "total hours 120"; Language and Life Cycle Status are almost never printed. Real page snippets,
  one per catalog.
- **E4.** Whether programs have codes in these catalogs, and whether those codes are unique (A4).
- **E5.** What the Credential Registry / Credential Finder already publishes for these five organizations as
  `LearningProgram`, since the Registry is the ground truth. Whether golden values can be checked against it.
- **E6.** Whether the xtra scorer library and `xtra score` accept `ceterms:LearningProgram` records, and which
  fields they compare.
- **E7.** What xtra-cli's extraction produces for a program page today (`LearningOpportunity` records, field
  names), so that Studio's rules match what the CLI will emit. What `FIELD_INVENTORY.csv` lists for programs.
- **E8.** A full count of every place `course` is assumed: rule-id prefixes, `course_key`, the Learning Type
  constant, report wording, prompt text, UI labels, tests and fixtures. Sorted into "rename", "generalize" and
  "course-only".
- **E9.** What `properties sync` does against the renamed sheet today, run without writing, and what it would add
  or drop.
- **E10.** How the deployed Studio's storage would migrate if D1 and D4 are accepted: the size of the data, and
  whether it can be done without downtime.
- **E11.** Who answers the property questions (A1, A4–A6, A8, B1): Jared, Jeanne, or both. Whether their sheet
  will gain a "Required" column so Studio doesn't have to infer it.
