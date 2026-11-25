# S (draft, wave 1): LearningProgram in the Golden Dataset Studio

A partial spec for adding the class `ceterms:LearningProgram` to the Studio, next to Course. It holds:

1. the decisions made so far;
2. what research found, with evidence;
3. the first wave of mockups, each next to today's screen;
4. follow-up questions for Eric, for Jared and Jeanne, and about Evals.

It is not the full spec. Questions answered here go into the next pass.

- Questions: [`01-questions.md`](01-questions.md). Answers, pass 1: [`answers-pass1.md`](answers-pass1.md). Prompt: [`prompt.md`](prompt.md)
- Research notes in full: [`research/crawls.md`](research/crawls.md) (what the five crawls hold) and
  [`research/code.md`](research/code.md) (the scorer, Course hardcoding, tests, storage)
- Written 2026-11-23.

### How the mockups were made

Every mockup is a screenshot of the real Studio, built from the current `golden-dataset-studio` code and served
locally on a read-only copy of the deployed data. A small script edits the page using the app's own components and
CSS, then takes the screenshot. Nothing is redrawn by hand, so a mockup looks the way the built screen would.

- **Labels:** each proposal carries a yellow **MOCKUP** tag in its corner. Screens named `t…` are today's app, unedited.
- **Real data:** the WVU program names and Major Codes come from WVU's crawled pages. The ceterms:name scores are
  Seth's figures from the running notes.
- **Illustrative data:** LearningProgram labeling progress and the 7-day score lines are made up, and each mockup
  says so.
- **To re-run:** the script and its patches are in [`mockups/`](mockups/) (`shoot.py`, `shots.json`, `patches/`).

---

## 1. Decisions so far

| # | Decision | From |
|---|---|---|
| D1 | Course was the first class. LearningProgram is another class, and three more will follow. | Framing |
| D2 | The sheet ("xTRA: Learning Opportunity BU Template", tab *Learning Program Properties*) is the source of truth. Issue #415's list is ignored. | A5, A6 |
| D3 | Every Phase 1 row is a **minimum** property. Required (CTDL) comes first, then **the rest of Phase 1 right after it**, then Phase 2: three tiers. | A1, A2 |
| D4 | Phase 2 properties are handled the way Course handles them. Rules can be added later without new code. | A3 |
| D5 | A program is identified by its **External Identifier**, following the team's protocol (issue #368, §2.2). | A4 |
| D6 | Learning Type for programs is `LearningProgram`. The UI writes the class as `LearningProgram`, with no space. | A7, C8 |
| D7 | Available At (`ceterms:Place`) is extracted as verbatim text, one value per location. | A8 |
| D8 | Each class has its own rule ids. Merging rules across classes may come later. | A9 |
| D9 | Course rules may be used as inspiration for program rules. | A10 |
| D10 | Minors, concentrations, certificates and tracks each count as a program for now. A page that lists several programs is one page with several records. | B2, B3 |
| D11 | A golden dataset version is published per catalog × class. Course-only UI is hidden when the class is LearningProgram. | C6, C7 |
| D12 | Storage gets a class folder under each catalog, and existing data is migrated into it. `--class` is explicit, with no default. There is one properties file per class. `course_key` becomes `record_external_identifier`. | D1–D4 |
| D13 | xtra-cli changes are out of scope. The scorer must score every class (§2.6). | D5, D6 |

---

## 2. What research found

### 2.1 Program pages are already crawled, about 2,000 of them

No new crawl is needed. crawl.json and meta.json don't record a page type, so program pages were found by URL
pattern and by the Studio's existing `program` page type.

| Catalog | Program URL pattern | Program pages | Notes |
|---|---|---|---|
| AVC | `/catalog/2026-27/program/<slug>-fall-2026` | 197 distinct | 24 of them are noncredit |
| CCSF | `/catalog/iq/programs/<area>/<id1>/<id2>` | 335 | The crawl stopped with 437 URLs still queued, so some programs may be missing. |
| Marshall | `/{undergraduate,graduate}/programs-az/<college>/<program>/[<emphasis>/]` | 647 pages, about 550 programs | About 150 are emphasis subpages |
| UALR | `preview_program.php?catoid=&poid=` | 1,111 pages, 319 programs | Each program was saved 3–4 times through `returnto=` |
| WVU | no fixed URL segment; a page with `table.sc_courselist` | 617 distinct URLs | 357 degrees, 184 minors, 46 certificates, 30 other |

### 2.2 External Identifier: the team settled the protocol today

Issue [#368](https://github.com/CredentialEngine/ctdl-xtra/issues/368) was agreed on 2026-11-23 by Jared and Rohit:

> 1. If the resource carries a clearly identifiable and unique identifier such as a course code, use it. Example: `CHEM212A`
> 2. If the resource does not carry a clearly identifiable and unique identifier, generate one using the combination
>    `{resource-type}-{normalized-resource-name}`. Do not exceed 100 characters.

Jared's example for a UALR program is `program-anthropology-b.a.`. In the crawls:

- Only WVU prints program codes, such as "Major Code: 5542" and "Minor Code - U003". About a third of WVU program
  pages have one.
- One WVU page can print 2–4 codes, split by delivery ("In-Person Major Code: 5542 Online Major Code: 5545") or by
  degree. Thirteen Major Codes appear on two different pages.
- The other four catalogs print no code. Their programs get the generated id.

So `record_external_identifier` holds this External Identifier value. It replaces Coded Notation as the record key
for programs, and for courses too if F5 below is accepted.

### 2.3 What a program page prints for the Phase 1 properties

| Property | What the pages show |
|---|---|
| Name, Description | On nearly every page. Some UALR degree pages go straight to requirements, with no description. |
| Subject Webpage | The page's own URL. |
| Language | Only `lang="en"` in the HTML. |
| Life Cycle Status | Never printed for a program. |
| In Catalog | The catalog year in the header or footer ("2026-27 Catalog"), except at WVU. |
| Is Non-Credit | Explicit only at AVC ("(Noncredit)" in the name). At CCSF it can be inferred from "Certificate of Competency" pages with an HOURS column. |
| Credit Value | Inconsistent. AVC prints "(Total 18)" with no unit, and its noncredit "Total 180" is hours. The printed total often covers only the major, while the degree total appears only in prose ("Minimum of 120 hours"). Labelled totals exist: Marshall "Total Credit Hours 30", WVU "Total Hours 120". Ranges occur ("31-37"). |

### 2.4 Course today: tiers, Phase 2 rules and an id clash

- **No Phase 1 or Phase 2 in the Studio.** The Rules tab groups are Required (8: the seven CTDL-required properties
  plus Coded Notation as the course key), Other properties, Not started, and Program page lines. The new Course tab
  in the sheet now has a Phase column. It marks Coded Notation, In Catalog, Is Non-Credit and Credit Value as
  Phase 1. Issue #317 calls the same four "Additional properties".
- **Course already has rules for some Phase 2 properties.** Beyond the required eight, AVC has 17 real rules and WVU
  has 12. A property with no rule is listed as "not started". Per D4, LearningProgram lists all 30 properties the
  same way, with its 16 Phase 2 properties not started.
- **The `program-` prefix is taken.** Course rules named `program-page`, `program-page-with-courses` and
  `locator-program-requirement` exist in every university catalog's history. These read course lines from program
  pages. LearningProgram rule ids therefore need a different prefix (F4).

### 2.5 The sheet changed under the Studio

`golden-datasets properties sync` reads tabs called `Phase 1 Extraction` and `Course`. The sheet now has
`Course Properties`, `Learning Program Properties`, `Prerequisite Mapping` and `PR with Alternative Conditions`, so
sync can't run until it reads the new names. The Learning Program tab also has a Value Type column and Extraction
Notes and Transformation Notes columns that the Course tab doesn't have.

### 2.6 The scorer ignores class, and that is already a bug for Course

- **How Studio scores:** Evals and `golden-datasets score` call xtra's `match_extraction_run`. It pairs records with
  golden entities by **page stem, then by position on the page**, and never reads `entity_type`.
- **What xtra emits for a program page:** an `entity_type: "LearningProgram"` record with three fields:
  `codedNotation`, `name` and `description`. A program page that names an award becomes a `Credential` record
  instead.
- **No program records yet.** No crawl has any LearningProgram records. Only AVC has a `records/` folder: 1,062
  Course and 3 Competency.
- **Existing bug:** Course golden data already holds course lines read from program pages. On those pages xtra's
  first record is a LearningProgram or Credential, so those courses are scored against the wrong record type today.
  Filtering records by class before scoring fixes this for Course and is needed for LearningProgram anyway.

### 2.7 How much assumes Course, and what protects the refactor

- **Mentions of "course":** about 670 in the Python code, 1,023 in the web UI and 695 in tests. `course_key`
  appears 145, 54 and 44 times respectively. The hotspots are `properties.py`, `model.py`, the review routes, the AI
  report (`report.py`, `prompt.py`, `Report.tsx`), `RulesTab.tsx` and `RecordsTab.tsx`.
- **Outside-in tests that would catch a regression:**
  - the fixture in `test_golden_versions.py`, which drives the real CLI and HTTP API and is reused by `test_scores`
    (the only test that runs the real scorer), `test_reset`, `test_approve_publishes`, `test_property_lists` and
    `test_speed`;
  - `minicat.py`, which feeds `test_one_rule_runs`.

  All of them are built around Course. Running them for a program catalog as well would make them the safety net
  you asked for.
- **Tests that won't help:**
  - The slow API tests skip, because their demo root isn't present.
  - The 31 web test files stub `fetch` with hand-written JSON, so they won't notice API changes.
  - The Playwright scripts in `bench/` take screenshots but don't check anything.

### 2.8 What moves in storage

- **Moves under a class folder:**
  - at the catalog level: `rules/`, `rulesets/`, `annotations.jsonl`, `agent-runs/`, `publish.json`;
  - at the crawl level: `extractions/`, `golden/`, `scores/`;
  - the golden root's version trees.
- **Stays where it is:** `pages.parquet`, `assets/`, the crawls themselves, and `extract-outputs/`.
- **Keyed by `course_key`:**
  - the `occurrences.parquet` column;
  - `annotations.jsonl` (append-only, so it needs a one-time rewrite or a read alias, F7);
  - ruleset settings, `publication.json`, and stored AI reports.
- **Size:** about 70 MB of Studio files across six catalogs, plus the golden root.

### 2.9 The daily scores live in a Google Doc tab, not a sheet

Seth posts them in the **"Extraction report"** tab of *CTDL xTRA Engineering Running Notes (Shared)*.

- **What a table holds:** one per property (`ceterms:name`, `description`, `identifier`), with one row per catalog
  (six, including UARK) and an **All** row. The four columns are Golden exact, Golden exact + partial, Silver exact,
  and Silver exact + partial, each as "n/d (pct)".
- **Under each table:** a "Why values are missing" table of reasons (M1–M4, with counts per catalog), then the
  mismatches one by one.
- **Target:** issue [#394](https://github.com/CredentialEngine/ctdl-xtra/issues/394) sets 90% for phase 1 and asks
  for the reports to be posted to the GitHub issue.
- **Matches the Studio's terms:** Golden is the Studio's *Human-reviewed* side and Silver its *Rule-matched* side.
  The Studio already computes both, as the two "scored against" bases.

### 2.10 Why the green bar is at the top

`.evx-stack` is a `flex-direction: column` with matches drawn first, so green sits on top
(`web/src/evals/evals.css:67`, `BAR_ORDER` in `EvalsTab.tsx:42`). `column-reverse` puts it at the bottom. M8 shows
the result.

---

## 3. Mockups, wave 1

### Choosing a class: where it lives

| Need (C1) | Where | Mockups |
|---|---|---|
| One class, all its properties, all catalogs side by side | Home table, with the class filter on that class | M1 or M2 |
| One catalog, all classes and all their properties | The class chip in the top bar, set to **All classes** | M4, M5 |
| All classes, all properties, all catalogs | Home table, with the class filter on **All classes** | M1 or M2 |
| Work inside one catalog and one class (labeling, records, runs) | The class chip in the top bar | M3, M6, M7 |

**Recommendation:**
- **Home table: M2.** It keeps the existing table and adds a row per class. Columns are CTDL properties, so `name`
  for Course sits right above `name` for LearningProgram. It also fits at 1640 px, where M1 needs about 1920.
- **Inside a catalog: the class chip (M3, M4).** It adds one chip to the top bar and changes nothing else on the
  page.

### M1. Home: one row per catalog, columns grouped by class

Today the home table has one row per catalog and one column per Course property (37 of them, with Required in bold):

![Today: the home page](page/screens/t01-home.png)

**Proposed:**
- **Class filter:** a second switch, *All classes | Course | LearningProgram*, sits beside *Golden dataset | xtra
  score*.
- **Columns:** grouped under a class heading, then by tier. Required is bold, as today. The rest of Phase 1 is in
  regular weight. Phase 2 folds into one "+ n Phase 2" column that opens to show its columns.
- **Coverage:** one line per class.
- **UARK:** it isn't a LearningProgram source, so its row says so instead of showing empty cells.

![M1](page/screens/m1-home-columns-by-class.png)

### M2. Home: one row per catalog × class (recommended)

**Proposed:**
- **Rows:** each catalog gets one row per class, with its own *Open →* that goes to that class's tabs. The logo, name
  and crawl date span the catalog's rows.
- **Columns:** the CTDL properties the classes share, in the three tiers.
  - Coded Notation is a Course property, so the LearningProgram row shows *n/a*.
  - Under the new Course tab it moves from Required into Phase 1 (F5).
- **xtra score:** the same layout works there, with one score per catalog × class (C4).

![M2](page/screens/m2-home-rows-by-class.png)

### M3. Rules tab for LearningProgram

Today's Rules tab (WVU, Course):

![Today: Rules](page/screens/t03-rules.png)

**Proposed:**
- **Top bar:** the class chip sits after the catalog chip, as `WVU / LearningProgram ▾`.
- **Rule list:**
  - **Page rules:** *Program pages*.
  - **Record locators:** *Programs: one per page, or one per tab*. WVU department pages show several programs as
    tabs.
  - **Required (7):** External Identifier is tagged **record key**, replacing *course key*.
  - **Phase 1 (7):** In Catalog, Is Non-Credit and Credit Value with its four parts.
  - **Phase 2:** folded, 16 not started.
- **Rows:** the left column shows each program's External Identifier. It is the code the page prints, such as `2166`
  for Accountancy, M.Acc. A program with no code gets the generated id, such as `program-geography-minor`. A tag on
  each row says where the identifier came from.
- **Page pane:** shows the real Accountancy, M.Acc. page with its name highlighted.

![M3](page/screens/m3-rules-learningprogram.png)

### M4. The class chip, opened

The chip uses the app's existing menu component. It lists:
- each class, with its size and progress;
- **All classes** (M5).

The chip and the class in the URL (`#/c/wvu/learningprogram/rules`) are the same setting.

![M4](page/screens/m4-class-menu.png)

### M5. One catalog, all classes, in the Rules tab

With **All classes** chosen, the rule list has a heading per class with that class's groups under it. Folded groups
show their approved counts. Search covers both classes. The middle and the pane still show one rule, from whichever
class it belongs to.

![M5](page/screens/m5-rules-all-classes.png)

### M6. AI runs work on one class

Today's "Run with Claude?" dialog (WVU, Course):

![Today: Run with Claude?](page/screens/t07-run-dialog.png)

**Proposed:**
- **Class switch:** at the top, *Course | LearningProgram*. It starts on the chip's class.
- **Scope:** the list, the checks Claude runs, and the run itself stay inside that class, and the text says Course
  rules are left alone.
- **Rule picking:** the same as today: one rule, several, or all of the class.
- **Locks:** runs are locked per catalog × class, so a Course run and a LearningProgram run on the same catalog can
  happen at the same time.

![M6](page/screens/m6-run-dialog-class.png)

### M7. Records tab for LearningProgram

Today's Records tab (WVU, Course):

![Today: Records](page/screens/t04-records.png)

**Proposed:**
- **List:** each row leads with the **program name** and shows the External Identifier under it. Hovering shows the
  program's URL. Search matches either.
- **Heading:** the program name, with where it was found and where its identifier came from.
- **Cards:** the program's properties, each tagged *program page*.

![M7](page/screens/m7-records-learningprogram.png)

### M8. Evals: green at the bottom

Today (AVC):

![Today: Evals](page/screens/t05-evals.png)

**Proposed:** matches sit at the bottom of each bar, so the green rises from day to day. Here five illustrative
daily outputs climb from 54% to 88%.

![M8](page/screens/m8-evals-green-bottom.png)

### M9. The daily scores report, in the Studio

Today the home page's *xtra score* view (empty in the local copy, because its scores live in the golden root):

![Today: xtra score](page/screens/t02-home-score.png)

**Proposed:** on the *xtra score* view, picking a **Property** turns the table into the running notes' report.
- **Rows:** grouped by class, one per catalog, plus **All**.
- **Columns:** Golden (human-reviewed) exact and + partial, and Silver (rule-matched) exact and + partial.
- **Target:** cells below 90% (issue #394) are red.
- **Trend:** a last-7-days line runs against the dashed 90% line.
- **Copy:** *Copy as a table for the running notes* keeps the doc in sync while people still use it.

The ceterms:name figures are Seth's real ones. LearningProgram says why it has no score yet.

![M9](page/screens/m9-score-report.png)

---

## 4. CLI and storage (proposal, no mockups)

- **`--class`:** required on every command that depends on the class, with `GOLDEN_DATASETS_CLASS` as the
  environment form. It has no default, so every call site gets updated: the deploy, the Studio's own prompts, docs
  and tests. Which commands count is in F6.
- **Class slugs:** `course` and `learningprogram` in paths, URLs and flags. The UI shows `Course` and `LearningProgram`.
- **Properties:**
  - **Files:** `properties/course.csv` and `properties/learningprogram.csv`.
  - **Sync:** `properties sync --class X` reads the `<Class> Properties` tab, so a later class means a new tab, not
    new code.
  - **Tiers:** `required` stays a column. Phase comes from the sheet's xTRA Status column.
- **Storage:**
  - **Layout:** `<catalog>/golden-dataset-studio/<class>/{rules,rulesets,annotations.jsonl,agent-runs,publish.json}`
    and `<catalog>/<crawl>/golden-dataset-studio/<class>/{extractions,golden,scores}`.
  - **Shared:** pages, assets and extract outputs stay at today's paths.
  - **Migration:** a one-time `golden-datasets migrate --to-classes` moves today's data under `course/`.
- **Record key:** `course_key` becomes `record_external_identifier` in every file and API. Its value is the External
  Identifier from §2.2.
- **Scoring:** records are filtered by `entity_type` to the class before they're paired. That also fixes the Course
  bug in §2.6.

---

## 5. Follow-up questions for Eric

Each has a default that the next pass works from.

- **F1. Home table: M1 or M2?** **Default: M2.**
- **F2. Old links.** Today's links, such as `#/c/wvu/rules/course-name`, have no class. Should they keep working and
  open Course? **Default: yes.**
- **F3. Where "All classes" works.** It could be in the Rules tab only (M5), or also in Records, Datasets and Evals.
  **Default: Rules only.** Records, Datasets and Evals show one class at a time, and the chip offers only the
  classes there.
- **F4. Rule id prefix.** `program-` is already used by Course rules (`program-page`…), so LearningProgram rules
  would be `learningprogram-name`, `learningprogram-description`, and so on. **Default: `learningprogram-`.**
- **F5. Course gets the three tiers too.** By the new Course tab, Coded Notation moves from Required into Phase 1.
  The Course record key becomes External Identifier, which is a course's code under the protocol: `BIOL20003` rather
  than `BIOL 20003`. **Default: yes, both classes are keyed by External Identifier.** The values change, so
  research checks how many course records would merge or split.
- **F6. Which commands need `--class`?**
  - **Don't depend on the class:** about 10 of the CLI's 31 commands, such as `init`, `assets`, `crawls`, `pages`,
    `sync`, `serve`, `sql` and `hash-password`.
  - **Default:** require `--class` on the class-dependent commands only, and reject it on the others.
- **F7. `annotations.jsonl`.** The file is append-only and every line says `course_key`. **Default:** rewrite it
  once during the migration, keeping the old file beside it, rather than read both names forever.
- **F8. Course lines on program pages.** The Course rules that read course lines from program pages
  (`program-page…`) stay Course rules. **Default: yes.**
- **F9. Datasets tab.** It has no mockup yet. Is publishing per catalog × class (D11) enough to go on, or do you
  want to see it? **Default: show it in wave 2.**
- **F10. UARK.** In M1 its LearningProgram cells say "Not a LearningProgram source". In M2 it has only a Course row.
  **Default: the M2 behaviour.**

## 6. Asks for Jared and Jeanne

The Studio goes ahead with the answer in brackets until they reply.

- **J1. External Identifier for programs.** Some WVU pages print two to four codes (In-Person and Online Major
  Codes), and 13 codes appear on two pages. Which code is the program's identifier? And is the generated prefix
  `program-` (Jared's example) or `learningprogram-`? *(first code printed; `program-`)*
- **J2. Coded Notation.** WVU's Major Code looks like a Coded Notation, but the Learning Program tab has no Coded
  Notation row. Should it? *(no, per the sheet)*
- **J3. Prerequisite.** Is Entry Condition the program's version of prerequisites, or should Prerequisite be on the
  tab? *(Entry Condition only, per the sheet)*
- **J4. Learning Type.** Is the value `LearningProgram`? *(yes)*
- **J5. Available At.** Verbatim text now, and a Place at transformation? *(yes)*
- **J6. Degree pages.** A page for "Accountancy, M.Acc." names a degree. xtra-cli calls that a **Credential**, not
  a LearningProgram. Should the Studio label it as a LearningProgram, as a Credential later, or as both?
  *(LearningProgram now; Credential when that class comes)*
- **J7. Minors, concentrations, emphases and tracks.** Marshall has about 150 emphasis subpages that print only
  their slice of the requirements. UALR gives each concentration its own page that repeats the whole degree. Is
  each one a separate program? *(yes)*
- **J8. Required.** The sheet has no Required column. Are the Learning Program required properties the same six
  as Course? Could the sheet get a Required column? *(the same six)*
- **J9. Credit Value.** Should it hold the major's printed total ("Total 18"), the degree total from prose
  ("Minimum of 120 hours"), or both? *(the total the page labels as the program's)*
- **J10. Defaults.** Life Cycle Status and Language are never printed. Is the golden value the default from the
  Extraction Notes ("Active", English), or empty? *(the default)*
- **J11. In Catalog.** Is it the catalog's URL, as the sheet says, or can it come from the "2026-27 Catalog" text?
  *(the URL)*
- **J12. Sample column.** The tab's Sample column was copied from Course ("General Microbiology"). Can it be
  replaced with program examples?

## 7. Evals and daily scores: questions (scope undecided)

- **E1. Scope.** Is this part of the LearningProgram work, or its own small story? **Default: its own story.** The
  green-bar fix (M8) goes in either way, because it's one line.
- **E2. Words.** The report says Golden and Silver, and the Studio says Human-reviewed and Rule-matched. **Default:**
  in M9, use the team's words with the Studio's in small type, as shown.
- **E3. Which number is the target?** Golden exact, or golden exact + partial? Issue #394 says 90% without saying
  which. **Default: golden exact + partial.**
- **E4. "Daily."** The Studio scores each new extract output, not each day. **Default:** the 7-day line shows the
  latest score per day.
- **E5. "Why values are missing."** These are Seth's hand-written reasons (M1–M4). Should the Studio hold them, for
  example as a note per catalog × property shown under the report? Or do they stay in the doc?
  **Default: they stay in the doc for now.**
- **E6. The running notes.** Should the doc link to the Studio, or should the Studio offer *Copy as a table* (M9)?
  **Default: both while people move over.**
- **E7. Other bars.** The home page's horizontal bars already start with green on the left. Should the Evals legend
  be reordered to match the new bottom-up bars? **Default: yes, match first.**
- **E8. Evals per class.** The Evals tab follows the class chip, so it scores one catalog × class at a time.
  **Default: yes.**
