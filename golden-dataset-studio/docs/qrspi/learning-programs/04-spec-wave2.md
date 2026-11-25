# S (draft, wave 2): LearningProgram in the Golden Dataset Studio

This is the second pass of the partial spec for adding the class `ceterms:LearningProgram` next to Course. It builds on
your reactions to wave 1 ([`answers-pass2.md`](answers-pass2.md)). Wave 1 is
[`03-spec-draft.md`](03-spec-draft.md).

What's in it:
- decisions so far;
- new research;
- the wave 2 screens, with each open question placed next to the picture it is about;
- the storage and CLI plan;
- asks for Jared and Jeanne, written so they can answer without other context.

Written 2026-11-24.

**How the pictures were made.**
- **Real app:** each picture is the real Studio, built from today's code and served locally on a read-only copy of the
  deployed data. A script edits the page with the app's own components and CSS, then takes a screenshot.
- **Labels:** a yellow MOCKUP tag marks proposals. Screens without the tag are today's app.
- **Real data:** WVU program names and codes come from the crawled pages. The Course ceterms:name scores are Seth's
  real figures.
- **Illustrative data:** everything else that is a LearningProgram number or a score, and each picture says so.
- **Scripts:** in [`mockups/`](mockups/): `shoot.py`, `shots.json` and `patches/w2-*.js`.

---

## 1. Decisions so far

| | Decision |
|---|---|
| 1 | Course was the first class and LearningProgram is the second. Three more follow, and possibly others after that. |
| 2 | The sheet's *Learning Program Properties* tab is the source of truth for this work. It's synced into a file, not read live. Issue #415 is ignored. |
| 3 | Three tiers for every class: Required (CTDL), then the rest of Phase 1, then Phase 2. Phase 2 works as it does for Course: a property with no rule is listed as not started. |
| 4 | Course gets the same three tiers. Coded Notation moves from Required into Phase 1. |
| 5 | Every class's record key is its External Identifier (issue #368). The field `course_key` becomes `record_external_identifier`. |
| 6 | The class is written `LearningProgram`, with no space. Its slug in paths, URLs and flags is `learningprogram`. |
| 7 | Rule ids carry the class: `learningprogram-name`, `course-name`. Merging rules across classes may come later. |
| 8 | Minors, concentrations, certificates and tracks each count as a program for now. |
| 9 | A golden dataset version is published per catalog and class. |
| 10 | Language is not read from `<html lang>`, because that is the website's language, not the program's. |
| 11 | One class menu in the top bar sets the class for every tab to its right and for the AI button. It can be set to **All classes**. |
| 12 | Home: classes are chosen from a multi-select menu, and the chosen classes' columns sit side by side. The table scrolls sideways. A catalog that has no programs says "Not a LearningProgram source". |
| 13 | AI runs use the top bar's class. With *All classes*, one run can cover several classes. |
| 14 | `--class` is only for commands that read or write one class's data. |
| 15 | A one-time migration rewrites today's files into the new layout and names. The old files are kept for reference. The app reads only the new format. Today's links that have no class stop working. |
| 16 | xtra-cli changes are out of scope. Evals and the daily scores are their own story, but planning continues here, because they decide where score files live. |

---

## 2. New research

The full notes are in [`research/programs.md`](research/programs.md) and [`research/storage.md`](research/storage.md).

### 2.1 Course lines on program pages: history, now gone

You asked why Course rules would ever read program pages.

**Where they came from.** On 2026-10-27 the import from the old review UI brought in three Course rules:
- `program-page`;
- `program-page-with-courses`;
- `locator-program-requirement`, which turned every row of a program's requirement list into a Course record.

**Examples:**

| Program page | Requirement row | Became a Course |
|---|---|---|
| AVC, Economics AA-T | "BUS201H - Business Law Honors" | BUS201H. It also has its own course page. |
| Marshall, Nursing M.S.N., nurse-midwifery emphasis | "NM 610 · Primary Care of Women" | NM610. Marshall has no crawled course page for NM. |
| UALR, Public History M.A. | "HIST 58133 - Seminar in Arkansas History" | HIST58133. It has no course page. |

**Size.** About 53,000 rows across five catalogs. Over 97% of them repeat a course that has its own page.

**Status: dropped.** The same day, ruleset v2 removed them with the note "program requirement lines aren't courses
(out of scope)". No current golden value comes from them. Two leftovers remain:
- **A stale setting:** every catalog's latest ruleset still names `locator-program-requirement` in its
  `course_key_rule` setting. The migration removes it.
- **WVU's School of Dentistry page:** `undergraduate/schoolofdentistry/` is both a course page and a program page. It
  has 45 golden Course records, and Jared marked 3 stub values on it wrong. Both classes may read this page.

So there is nothing to decide here: Course rules don't read program pages.

### 2.2 One program, more than one page

This decides whether the Records tab needs to say where each value came from.

| Catalog | One page per program? |
|---|---|
| AVC, CCSF | Yes. |
| UALR | Yes, but each program was saved 3–4 times under different "Return to" links. The Studio de-duplicates them. 47 concentration and track pages each restate the whole degree. |
| Marshall | 155 emphasis pages are split off their degree. The degree page has the description and total. The emphasis page has only its own slice ("Select nine hours…: 9"). |
| WVU | **The Major Code is often on a different page.** Department overview pages print the codes. The program's own page has its requirements and total, and no code. |

**WVU example.** `graduate/…/english/`, the Department of English, prints:

> M.A. Major Code: 1442 M.A. in Professional Writing and Editing Major Code: 1481 M.F.A. Major Code: 1486
> Ph.D. Major Code: 1442

- **Two pages:** the English M.A.'s requirements and "Total Hours 30" are on `…/english/ma/`. So its External
  Identifier comes from one page and its other values from another.
- **A shared code:** the department page gives **1442 to both the M.A. and the Ph.D.**, so a printed code is not
  always unique. This is an ask for Jared.

### 2.3 Credit Value

**What the pages print.** All five catalogs use semester credit: "units" at AVC and CCSF, "credit hours" at the
others. Three things vary:
- **Which total:** many pages print a total for the major only, such as AVC's "Anthropology AA-T (Total 24 - 30)".
  The whole degree's total appears only in prose: "Completion of 60 semester units".
- **Ranges:**
  - AVC: 48 of 197 pages;
  - CCSF: 113 pages, such as "Total : 18.0- 19.0";
  - Marshall: 84 pages, such as "Total Credit Hours 17-19".
- **Hours that aren't credit:** noncredit certificates print clock hours ("Total Hours 180.0" at AVC, "Total : 700.0"
  at CCSF). The Nursing M.S.N. adds "780 clinical hours".

**Proposed rule.**
- The golden Credit Value is **the total the page gives for the whole program**.
- **Ranges** go to Min Value and Max Value.
- **The unit** is SemesterHour.
- **Clock hours** for noncredit programs are not a Credit Value.

Jared and Jeanne need to confirm this (§6).

### 2.4 Language

- **No page states it.** No program page in any catalog states its language of instruction. The regex hits are about
  a course ("One course must be taught in French"), an admission requirement or the subject itself.
- **Decision 10 applies.** The only signal is `<html lang>`, which we don't use.
- **So for now:** Language for programs stays **not started**, unless Jared and Jeanne want a default value (§6).

### 2.5 Where xtra-cli's outputs and scores should live

**Today, everything sits in xtra-cli's own container**, `xtra-cli-output/`, under a Studio prefix
(`zz-scratch-review-ui-v3`):
- **Crawls:** the Studio keeps copies of them there.
- **xtra's extract outputs:** the Studio copies them into a Studio folder (`extract-outputs/`).
- **Scores:** the Studio writes them under its own folder (`scores/sc-NNNN/`).

**xtra-cli itself writes one output folder per crawl.** Each extract run overwrites the last, so old outputs and
their scores are lost.

**No script makes the daily report.** Seth builds it by hand.

**Proposal.** Each owner gets its own place.

| What | Owner | Where |
|---|---|---|
| Crawls | xtra-cli | `xtra-cli-output/<catalog>/<crawl>/` as today. The Studio reads them in place and stops copying them. |
| Extract runs | xtra-cli | `xtra-cli-output/<catalog>/<crawl>/extract/<run-id>/{extract-report.json, records/}`. One folder per run. |
| Scores | xtra-cli's scorer | `…/extract/<run-id>/scores/<baseline>/<class>/<property>/{exact,partial}.json`. `<baseline>` names the golden or silver version, such as `ruleset-v8-golden`. |
| Score history | xtra-cli's scorer | `xtra-cli-output/scores/<class>/<property>/<catalog>.jsonl`, one line per score. The daily report and its 7-day bars read these small files. |
| Golden and silver versions | shared | `xtra-golden-sets/`, as today. This is xtra-cli's baseline. |
| Studio data | Studio | Its own container, `golden-dataset-studio/`. Each catalog's `<class>/` holds rules, rulesets, annotations and AI runs. Each crawl holds `pages.parquet`, `assets/` and `<class>/rule-runs/`. |

**Two catches:**
- **Out of scope:** one folder per extract run is an xtra-cli change. Until xtra-cli makes it, the Studio would keep
  copying each output into the extract-run path the first time it sees it, the way it does today. It would write
  that copy under `xtra-cli-output/…/extract/<run-id>/` instead of under its own folder.
- **Scores move out of the Studio's folder:** they are written by xtra's scorer library (the Studio already calls
  it), to the xtra-cli paths above. xtra-cli's own `xtra score` command could write to the same place.

> **Question: do we take this layout to Rohit?**
>
> - **Today:** extract outputs and scores live under the Studio's folder, which Rohit and others object to.
> - **The proposal:** move them to xtra-cli's paths, give each extract run its own folder, and give the Studio its own
>   container.
> - **Cost:** one migration, done together with the move into class folders, so the data moves only once.
>
> **Working answer:** yes. Raise it with Rohit as the shape for the integration work in #447. Until xtra-cli adopts
> per-run folders, the Studio writes into these paths itself.

---

## 3. The class menu governs every tab

**The menu.** The top bar's class menu (approved in wave 1) lists each class and **All classes**. Whatever it says
applies to Rules, Records, Compare, Datasets, Evals and the AI button. With one class chosen, every tab shows only
that class. With All classes chosen:

| Tab | One class | All classes |
|---|---|---|
| Rules | that class's groups | a heading per class, with its groups folded under it |
| Records | that class's records | a folding heading per class in the list |
| Datasets | that class's golden and silver datasets | a section per class |
| Evals | that class's bars | one row of bars per class |
| AI button | that class's rules, with no switch | one list with a heading per class, and you tick across classes |

**The URL.** It carries the class (`#/c/wvu/learningprogram/rules`). All classes is `#/c/wvu/all/rules`.

The menu, opened:

![The class menu, opened](page/screens/m4-class-menu.png)

### 3.1 Rules, All classes

Each class has a heading with its counts, and its groups are folded under it. Search covers every class. The middle
and the page pane still show one rule.

![Rules with All classes](page/screens/m5-rules-all-classes.png)

### 3.2 The AI run, one class

The dialog's title names the class, and the list holds only that class's rules. The class switch from wave 1 is gone.

![Run dialog, LearningProgram only](page/screens/w2-run-one-class.png)

### 3.3 The AI run, All classes

- **One list:** a heading per class, each with what needs work first.
- **Ticking:** rules can be ticked across classes, and the button counts them ("Run on 3 rules in 2 classes").
- **Scrolling:** the list scrolls, so it still works with five classes.

![Run dialog, All classes](page/screens/w2-run-all-classes.png)

> **Question: what does a run across classes lock?**
>
> - **Today:** one AI run at a time per catalog.
> - **With classes:** a run that touches only LearningProgram rules doesn't need to block a Course run on the same
>   catalog.
> - **The two options:**
>   - Lock each class the run has a ticked rule in. Other classes stay free. This needs a lock per catalog and class.
>   - Lock the whole catalog whenever a run covers more than one class. This is simpler, but blocks more.
>
> **Working answer:** lock each class the run touches.

### 3.4 Records, one class

A program's values usually all come from its own page. So the cards drop the per-value "program page" line and the
heading drops "Found on 1 program page". The list keeps the identifier under each name, so you can search by either.

![Records, LearningProgram, one page](page/screens/w2-records-lp.png)

### 3.5 Records, a program whose values come from two pages

When a program's values come from more than one page (WVU's Major Codes, Marshall's emphases), and only then:
- the heading says "Values from 2 pages";
- each card names its page;
- the page pane has a tab per page.

Here the English M.A.'s code is on the Department of English page, and its other values are on its own page.

![Records, a program across two pages](page/screens/w2-records-multi.png)

### 3.6 Records, All classes

The list has a folding heading per class with its count. Search finds courses and programs.

![Records with All classes](page/screens/w2-records-all.png)

### 3.7 Datasets, one class

Today's Datasets tab, for Course at WVU:

![Today: Datasets](page/screens/t06-datasets.png)

With LearningProgram chosen, it shows that class's golden values. Its silver datasets start at **ruleset-v1**, because
each class numbers its own ruleset versions. The command hint at the bottom gains `--class learningprogram`. The counts
are illustrative.

![Datasets, LearningProgram](page/screens/w2-datasets-lp.png)

### 3.8 Datasets, All classes

A section per class, each with a heavy rule above it and the same two tables as today.

![Datasets with All classes](page/screens/w2-datasets-all.png)

### 3.9 Evals, one class and All classes

- **One class:** the history bars are those of LearningProgram, with matches at the bottom.
- **All classes:** one row of bars per class, on the same days. Clicking a bar opens that class's comparison.
- **Data:** the LearningProgram bars are illustrative, because xtra writes no LearningProgram records yet.

![Evals, LearningProgram](page/screens/w2-evals-lp.png)

![Evals with All classes](page/screens/w2-evals-all.png)

---

## 4. Home and Rules, revised

### 4.1 Home: a class menu, side by side, scrolling

- **The menu:** *Classes: Course, LearningProgram ▾* replaces the class switch, and each class has a tick box. One
  ticked class gives today's table. Several give their columns side by side, under a class heading. The button stays
  one button however many classes exist.
- **Scrolling:** the table **already** scrolls sideways inside its frame. The *Open*, logo and catalog name are pinned
  on the left, and Coverage is pinned on the right (`catalogs/ctab.css:61-67`). Nothing new is needed.
- **UARK:** its LearningProgram columns say "Not a LearningProgram source".

![Home, the class menu open](page/screens/w2-home-classes-menu.png)

Scrolled right, the catalog stays pinned and LearningProgram's columns come into view:

![Home, scrolled](page/screens/w2-home-scrolled.png)

### 4.2 Rules: where the identifier came from, on hover

- **Wave 1** put two tags under every row: *URL pattern* and *External Identifier*. The identifier repeated the left
  column, which is now a plain dotted-underlined key.
- **Hover:** hovering it opens a small card with the identifier, where it came from ("In-Person Major Code: 2166" on
  the page) and which page rule matched the page, with its URL pattern.
- **Generated identifiers:** they are grey, so you can tell at a glance which ones the page printed and which were
  made from the name.

![Rules, the identifier card](page/screens/w2-rules-id-card.png)

![Rules, a generated identifier](page/screens/w2-rules-id-generated.png)

---

## 5. Scores across many catalogs and classes (planning; its own story)

**Wave 1** showed one property at a time with a trend line that had no axis. That doesn't scale. With 20 catalogs and
5 classes, it is 100 rows for each of about 30 properties. Wave 2 has three views that nest.

### 5.1 Every property: the *xtra score* view mirrors the golden view (recommended default)

- **Same layout:** the same columns, class menu, tiers and sideways scroll as the golden view.
- **Cells:** each cell is that property's score (golden exact + partial) instead of its review progress. Red means
  below 90%, and a dash means no golden values to score against.
- **At target:** the right column counts the properties at target per class.
- **Scale:** it grows like the golden view does, one row per catalog and one column group per ticked class.
- **Drill-down:** a cell opens that property's report (5.2).
- **Data:** Course ceterms:name is Seth's real figure, and the rest is illustrative.

![Score, every property](page/screens/w2-score-all-properties.png)

### 5.2 One property: the running notes' table, stacked by class

- **What it is:** Seth's report for one property. There is one table per class, stacked. Each row has golden exact,
  golden + partial, silver exact and silver + partial.
- **The bars:** the last 7 scores as thin bars on a real chart. The y-axis is 0–100 with a dashed red 90 line, and the
  x-axis runs from the first day to the last. Green bars meet the target and amber bars don't.
- **Copy:** *Copy as a table for the running notes* gives the same table as text.

![Score, one property](page/screens/w2-score-one-property.png)

### 5.3 The overview, for when the grid gets too wide

- **What it is:** one cell per catalog and class. It shows how many of the class's minimum properties meet the target,
  with a bar and the lowest property. A cell opens that catalog's every-property view.
- **Scale:** five classes are five columns. A search box filters catalogs by name or state.
- **Data:** illustrative.

![Score, the overview](page/screens/w2-score-overview.png)

> **Question: which score view opens first?**
>
> - **Every property (5.1):** the same table as the golden view, with percentages.
> - **The overview (5.3):** one cell per catalog and class.
> - In both, clicking a cell goes one level down. One property (5.2) is always the bottom level.
>
> **Working answer:** the every-property view first. Add the overview as a first level once there are more than about
> three classes or fifteen catalogs, when the grid needs a lot of sideways scrolling.

> **Question: which number is held to 90%?**
>
> - **The four numbers:** Seth's report gives golden exact, golden exact + partial, silver exact and silver exact +
>   partial. "+ partial" also counts a candidate at least 80% similar to the golden value.
> - **Issue #394:** says "90%", but not which of the four.
> - **Where it shows:** the dashed line and the red cells in all three views use one of them.
>
> **Working answer:** golden exact + partial.

> **Question: Golden and Silver, or the Studio's words?**
>
> - **The team's report** says *Golden* and *Silver*.
> - **The Studio** says *Human-reviewed* and *Rule-matched* for the same two baselines.
> - **The one-property table** above uses both: *Golden: human-reviewed* and *Silver: rule-matched*.
>
> **Working answer:** keep both, team word first, as drawn.

> **Question: what is one bar in the 7-day chart?**
>
> - **The Studio** scores each new extract output, which can be several a day or none.
> - **The report** is daily.
>
> **Working answer:** one bar per day, the day's latest score. A day with no new output has no bar.

**Not asked, kept as is:** Seth's "Why values are missing" notes stay in the running notes doc for now.

---

## 6. Asks for Jared and Jeanne

Each ask stands alone. The Studio goes ahead with the working answer until they reply.

**1. A program page prints more than one code. Which is the program's identifier?**
- **The example:** WVU's Accountancy page prints "In-Person Major Code: 2166". Other WVU pages print both
  "In-Person Major Code: 5542" and "Online Major Code: 5545" for the same degree.
- **Option 1:** one program, identified by the first code printed.
- **Option 2:** one program per code, one in-person and one online, with the same name and requirements.
- **Option 3:** one program carrying both codes as two identifiers.
- **Working answer:** option 1.

**2. Two programs share one code.**
- **The example:** WVU's Department of English page prints "M.A. Major Code: 1442 … Ph.D. Major Code: 1442".
- **The problem:** if the code is the identifier, the English M.A. and the English Ph.D. become one record.
- **Option 1:** use the code anyway, and let the two merge.
- **Option 2:** when a code is shared, give each program the generated identifier instead, such as
  `program-english-m.a.`.
- **Working answer:** option 2.

**3. The prefix of a generated identifier.**
- **Today:** programs with no printed code get `{type}-{normalized name}` (issue #368). Jared's example was
  `program-anthropology-b.a.`.
- **The question:** should the type be `program` or the CTDL class name, `learningprogram`? Later classes such as
  Credential would follow the same pattern.
- **Working answer:** `program`, as in Jared's example.

**4. A degree page: LearningProgram, Credential, or both?**
- **The example:** WVU's "Accountancy, M.Acc." page describes a program that leads to a degree.
- **xtra-cli today:** it writes such a page as a **Credential** record, not a LearningProgram. The Studio scores
  records by class, so a program labelled here would find no LearningProgram record to match.
- **Working answer:** label it as a LearningProgram now. Label its Credential when that class comes.

**5. An emphasis page that prints only its slice.**
- **The example:** Marshall splits 155 emphases off their degree. The degree page `accountancy-ms/` says "Total Credit
  Hours 30". The emphasis page `…/tax-compliance-planning-emphasis/` says only "Select nine hours from the following
  courses: 9".
- **Agreed already:** each emphasis is its own program.
- **The question:** is its Credit Value the slice it prints (9), or the degree's total (30) from the other page?
- **Working answer:** the degree's total, 30. The emphasis is a whole path through the degree.

**6. Which credit total.**
- **The example:** AVC prints "Anthropology AA-T (Total 24 - 30)", which covers the major's courses. The description
  says "Completion of 60 semester units", which is the whole degree.
- **Option 1:** the whole program's total, 60, even when it is only in prose.
- **Option 2:** the labelled total the page prints, min 24 and max 30.
- **Working answer:** option 1, the whole program. A range goes to Min Value and Max Value. The unit is SemesterHour.

**7. Noncredit hours.**
- **The example:** AVC's noncredit certificates print "Total Hours 180.0", and CCSF's print "Total : 700.0". These are
  clock hours.
- **Option 1:** no Credit Value. Is Non-Credit is true.
- **Option 2:** a Credit Value of 180 in clock hours.
- **Working answer:** option 1.

**8. Properties no page prints.**
- **What we found:** Life Cycle Status and Language never appear on a program page.
- **Language:** only the website's `<html lang="en">` hints at it, and we don't use that, because it is the site's
  language, not the program's.
- **The Extraction Notes:** they suggest defaults, "Active" and English.
- **Option 1:** the golden value is the default.
- **Option 2:** leave them unlabelled until a page states them.
- **Working answer:** option 2, unlabelled.

**9. Required properties.**
- **The sheet:** the Learning Program tab has Phase 1 and Phase 2 columns, but no Required column.
- **The Studio:** it puts Required first.
- **The question:** are a program's required properties the same as Course's, without Coded Notation? That is
  External Identifier, Learning Type, Name, Description, Subject Webpage, Life Cycle Status and Language.
- **Also:** could the sheet get a Required column, so the Studio reads it rather than assuming?
- **Working answer:** the same, and yes to a column.

---

## 7. CLI and storage

**`--class`** is required on commands that read or write one class's data, and refused on the others. There is no
default. The environment variable form is `GOLDEN_DATASETS_CLASS`.

| Takes `--class` | Doesn't |
|---|---|
| `properties sync / list / apply`, `extract`, `check`, `rule …` (list, show, annotations, draft, try, publish, downstream), `ruleset revert`, `pages sample`, `run …`, `prompt`, `golden publish / backfill`, `score` | `init`, `assets fetch`, `crawls list / add`, `pages get`, `sync`, `serve`, `hash-password`, `sql` (it gets a `class` column instead) |

`import-v2` is Course-only history and is removed.

**Properties:**
- **Files:** one file per class: `properties/course.csv`, `properties/learningprogram.csv`.
- **Sync:** `properties sync --class learningprogram` reads the *Learning Program Properties* tab, so a later class
  needs a new tab, not new code.
- **Phase:** it comes from the sheet's xTRA Status column.

**The migration** is a one-time command, run once per root. It:
1. moves today's Studio data into `course/` folders;
2. rewrites every file that says `course_key`, including `annotations.jsonl`, to say `record_external_identifier`. The
   old files are kept beside the new ones, renamed `*.legacy`;
3. removes the stale `course_key_rule` setting (§2.1);
4. moves extract outputs and scores to their xtra-cli paths (§2.5), if Rohit agrees.

**Scoring:** records are filtered by class before they are paired. This also covers pages that hold both classes, such
as WVU's School of Dentistry page. Today, xtra's first record on such a page can be a program, and Course values would
be paired with it.
