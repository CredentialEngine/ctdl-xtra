# P: LearningProgram, and the Studio for any number of classes

This is the plan for building what [`05-approved.md`](05-approved.md) and [`07-spec-wave4.md`](07-spec-wave4.md)
describe. Every screen it builds is drawn in `screens/`, which holds the mockups, today's screens and the doc crops (in
`screens/doc/`). Open [`surface.html`](surface.html) in a browser to see each screen, latest version only, grouped
by area and marked approved or proposed. All of them are approved now.

Written 2026-11-24.

**Out of scope:**
- triggering a score from the UI (the *Score now* button);
- changes to xtra-cli itself;
- deploying. Everything is built and checked locally.

## How to work

- **One phase, one commit.** The tests pass at every commit. Each phase ends with its checks run and a short note in
  the [Progress](#progress) section at the bottom.
- **Tests are outside-in.**
  - The `test_golden_versions` fixture and `minicat` drive the real CLI and HTTP API. Run them for a **program
    catalog** as well as the course catalog. Phase 1 adds a small LearningProgram fixture (two WVU program pages,
    one AVC).
  - Web tests stub `fetch`. Update their fixtures with each API change.
- **Local app.** Data is a read-only copy of the deployed root, at `~/studio-local/learning-programs/root`. Never
  write to Azure.

  ```bash
  cd golden-dataset-studio
  L=~/studio-local/learning-programs
  env -u AZURE_STORAGE_CONNECTION_STRING GOLDEN_DATASETS_ROOT=$L/root GOLDEN_DATASETS_GOLDEN_ROOT=$L/golden \
    GOLDEN_DATASETS_XTRA_SOURCE=$HOME/review-ui-v3-data/xtra-cli-output GOLDEN_DATASETS_CACHE=$L/cache \
    uv run golden-datasets serve --port 8031 --host 127.0.0.1
  ```

  The web UI is built with `make` / `npm run build` in `web/` (see the Makefile). Copy the root again before running
  the migration against it, so a bad migration can be redone.
- **Screenshots.** Take them with Playwright against the local app, as in `mockups/shoot.py`. Every phase that changes
  a screen saves one to `screens/impl/`, named like its mockup, for the PR.
- **Keep images out of git.** `screens/`, `surface.html` and `mockups/` are local reference material and are listed
  in `.git/info/exclude`. Commit only the markdown docs. Phase 8 hosts the PR's images and video on an orphan
  branch, `pr-assets/studio-learning-program`, and links to them by raw URL.
- **Rules from earlier work:**
  - keep the UI minimal: borders, not fills; tooltips for detail; no `·` middle-dot separators in new UI;
  - never mention where or how the Studio is deployed;
  - follow the existing code style in each file.

## Phase 0: catch up with main

- **Branch:** this branch, `studio-learning-program`, is cut from `origin/golden-dataset-studio` at a78be91. That is
  the branch where the Studio lives; `main` holds only xtra-cli. The PR targets `golden-dataset-studio`.
- **Merge `origin/main`.** Its 18 newer xtra-cli commits go into this branch, because the Studio must score what
  today's xtra-cli writes. If the merge conflicts outside `xtra-cli/`, stop and report.
- **Read what changed in xtra-cli** since a78be91: one extraction script per property (#376), `xtra score … --property`
  (#449), discovery tuning, and the `extraction_report/ceterms/<prop>/…` layout.
- **Find what in the Studio's `scores.py` breaks.** It reads `records/` and calls `match_extraction_run`, and the
  scorer module may have moved (`src/xtra/score/`).
- **Fix it**, and add a test that scores a new-layout extract output.
- **Check:** `make test` (or `uv run pytest`) and `npm test` pass. Scoring an AVC output locally works.

## Phase 1: classes, properties, tiers, record key

- **Class registry:** `course` and `learningprogram`, each with its display name (`Course`, `LearningProgram`), its
  rule id prefix (`course-`, `learningprogram-`), its sheet tab (`Course Properties`, `Learning Program Properties`)
  and its xtra `entity_type`.
- **Properties:**
  - one file per class: `properties/course.csv` and `properties/learningprogram.csv`;
  - `properties sync --class X` reads the `<X> Properties` tab;
  - Phase comes from the sheet's xTRA Status column;
  - tiers are Required, then Phase 1, then Phase 2.
  - Course: Coded Notation moves to Phase 1. LearningProgram's Required is Course's without Coded Notation, until
    Jared answers ask 9 in [`asks-jared-jeanne.md`](asks-jared-jeanne.md).
- **Record key:** `course_key` → `record_external_identifier` in the code, the API, the web types and the stored
  files. The migration (Phase 2) rewrites the stored files.
- **`--class`:** on the class commands listed in item 19 of `05-approved.md`, and refused on the others.
  `GOLDEN_DATASETS_CLASS` is the environment form.
- **Fixture:** a small LearningProgram fixture for the outside-in tests.
- **Check:** all tests pass for both classes, and `properties sync --class learningprogram` reproduces the tab
  snapshot in `learning-program-properties-2026-11-23.csv`.

## Phase 2: storage layout and the migration

- **Studio data** moves under class folders (item 20 of `05-approved.md`), and `extractions/` becomes `rule-runs/`.
- **xtra-cli's data is read where xtra-cli writes it** (item 21): crawls, extract outputs and scores. The Studio stops
  copying it. Keep a path setting for the Studio's own container, separate from xtra-cli's.
- **`golden-datasets migrate --to-classes`:** one-time and idempotent. It:
  - moves today's data into `course/`;
  - rewrites `course_key` everywhere, including `annotations.jsonl`, keeping `*.legacy` copies;
  - removes the stale `course_key_rule` setting;
  - moves extract-output copies and scores to the xtra-cli paths;
  - supports `--dry-run`, which prints every move.
- **Check:**
  - the migration runs on the local root copy, and a second run changes nothing;
  - the app serves every catalog as before, as Course;
  - the outside-in tests pass on a migrated fixture.

## Phase 3: scoring by class

- **Pairing:** filter records by `entity_type` to the class before pairing (§2.6 of `03-spec-draft.md`).
- **Where scores go:**
  - each score is written under its extract run, at `…/scores/<baseline>/<class>/<property>/`;
  - each score appends one line to `xtra-cli-output/scores/<class>/<property>/<catalog>.jsonl`.
- **What each line holds:** the time, the extract run, the golden version, the trigger (`golden-published` or
  `new-output`), the outcome counts, and the xtra-cli version and commit (`scores.py` already records the commit).
  Also "extracted with", when the extract report records it.
- **Triggers:** a golden publish scores the changed properties of the latest output. A new output scores every
  property. Both go through the existing score scheduler.
- **The 90% target is golden exact.** Partial is never added to it.
- **Check:** tests for the class filter (a page with both a program and a course), the history line, and both
  triggers.

## Phase 4: the class menu and the per-catalog tabs

Mockups: `w4-class-menu`, `w4-rules-all-classes`, `w2-rules-id-card`, `w2-rules-id-generated`, `w2-run-one-class`,
`w2-run-all-classes`, `w2-records-*`, `w2-datasets-*` and `w2-evals-*`.

- **URL:** `#/c/<catalog>/<class>/<tab>`, with `all` for All classes. Today's links without a class are not kept.
- **Class menu:** in the top bar, after the catalog chip.
- **Rules:**
  - groups by tier;
  - the record key column has a dotted underline and a hover card. The card shows the identifier, its source as
    inline code, and the page rule with its URL pattern. Generated identifiers are grey;
  - All classes shows a heading per class with its groups folded.
- **AI run dialog:**
  - one class: the title names it, and there is no switch;
  - All classes: one list with a heading per class;
  - locks are per catalog and class, so a run locks the classes it has a ticked rule in.
- **Records:**
  - list rows show the name with the identifier under it;
  - a value shows its source page only when the program's values come from more than one page;
  - All classes: a folding heading per class.
- **Datasets:** per class, with silver versions numbered per class. All classes: a section per class.
- **Evals:**
  - per class, using that class's scores;
  - bars use `column-reverse`, so matches sit at the bottom;
  - All classes: one row of bars per class.
- **Check:** web tests for each tab under one class and under All classes, plus screenshots in `screens/impl/`.

## Phase 5: the home page

Mockups: `w2-home-classes-menu`, `w2-home-scrolled` and `w4-scores-*`.

- **Golden dataset view:**
  - a multi-select *Classes* menu, with the ticked classes' columns side by side under class headings, in the
    three tiers;
  - Phase 2 is folded;
  - a catalog with no programs says "Not a LearningProgram source".
- **xtra score view:**
  - **Menus:** Catalogs, Classes, Properties. Properties are listed under their class, and ticking a class ticks all
    its properties.
  - **The four scopes:**
    - all catalogs and all properties, with a *Rows: Catalogs | Properties* switch;
    - one catalog, all properties;
    - all catalogs, one property;
    - one catalog and one property, over time.
  - **Every row:** a Golden line and a Silver line, a stacked outcome bar in the Evals colours with a dotted 90% line,
    exact and partial shown separately, and a *Bars | Numbers* switch.
  - **History:** the last 7 scores as stacked bars with axes, each marked *golden* or *output*.
  - **Scored with:** the golden version and the xtra-cli version.
  - **Navigation:** rows open the next scope down. The one-catalog views link into that catalog's Evals tab at the
    property.
  - **No Score now button.**
- **Check:** web tests per scope, plus screenshots.

## Phase 6: findings, property status, discussion

Mockups: `w4-evals-findings`, `w4-evals-finding-panel`, `w4-property-review` and `w4-scores-by-property-status`.

- **Storage** (Studio data, per catalog-independent class and property):
  - `findings.jsonl` (append-only);
  - `status.json` (*Needs review* / *Done*, with who and when);
  - threads in the same comment store the Rules tab uses.
- **Who can do what:**
  - anyone can set *Needs review*; only the SME role sets *Done*;
  - a finding with no units left shows *0 units*, and a person marks it fixed.
- **Evals:**
  - *Where it's wrong* gets a Finding column, with the finding or *+ Add finding*, and *Discuss* with a count;
  - the finding editor has code, title, whose error, cause, fix, assessment, the units it covers per catalog
    (live), and a thread.
- **Review page:** the one-property scope gets the status control and the findings table: code, kind, partial /
  wrong / missing as golden / silver, catalogs, whose error, state and comments.
- **Rows by property** show each property's status.
- **Seed data:** import Seth's Course description codes (D1–D9, M1–M4) from the running notes as findings, so the page
  isn't empty. Keep the text verbatim.
- **Check:** API tests for findings, status and threads, including the role rules, plus web tests and screenshots.

## Phase 7: the first LearningProgram rules

Using the Studio's own rule tools (`rule draft` / `try` / `publish`, or an AI run):
- **Rules:** a page rule (Program pages), a record locator (one per page, or one per tab), and External Identifier,
  Name and Description for **WVU** and **AVC**.
- **Identifiers:** follow `05-approved.md` item 5, and the working answers to asks 1–3 in `asks-jared-jeanne.md`.
- **Check:** the Rules tab shows real LearningProgram rows for WVU and AVC, labelled from real pages.

## Phase 8: the pull request

- **Screenshots:** each mockup beside the screenshot of what was built, from `screens/impl/`.
- **Markup:** where a difference or a decision needs a note, mark up the screenshot with VectorCraft (arrows,
  callouts). Mark nothing that doesn't need it.
- **Walkthrough video:** a screen recording with a voiceover. Record with Playwright, voice with TTS, and mux with
  ffmpeg. It covers:
  1. choosing a class;
  2. LearningProgram Rules and the identifier card;
  3. an AI run across classes;
  4. Records with two pages;
  5. the home page side by side;
  6. scores from overview to one property to Evals;
  7. adding a finding and setting a status.

  Keep it under 4 minutes.
- **PR body:** the problem, what changed by area, the migration and how to run it, what's out of scope, and the open
  asks for Jared and Jeanne. It ends with the attribution lines.
- **Open it as a draft** against `golden-dataset-studio`. Don't merge.

## Progress

Add one line per phase as it lands: the phase, the commit, the checks run, and anything left over.

- **Phase 0** (merge of `origin/main` at 4f1b689, 19 xtra-cli commits). Conflicts were only in `xtra-cli/`.
  Extraction, discovery and crawl files take main's version, which is today's xtra-cli. That drops this branch's
  older copies of #316, the prerequisite and creditUnitType extraction work, and the semgrep fixes; main has its own
  versions. The scorer (`score_extraction_match.py`, `xtra score extraction match`) keeps the Studio's #355 additions
  (found/right, extras, unsure) together with main's `--property` (#449) and `pages_not_extracted` (#392). Main's
  new scorer tests now expect the `unsure` outcome. The Studio reads today's layout,
  `extraction_report/<prefix>/<prop>/<resource>.json` plus `extraction-<prop>-report.json`, through xtra's own
  `extraction_records`; it copies the built records and the property reports, and keeps reading older `records/`
  outputs. `xtra_terms` comes from xtra's extractor registry. New test: `tests/test_score_extract_layout.py`.
  Checks: xtra-cli `uv run --extra dev --extra azure pytest` 2365 passed; ruff check and format clean. Studio
  `uv run pytest` 229 passed; `ruff check` clean; web typecheck clean, `npm test` 279 passed, `npm run build` OK.
  Locally, today's xtra-cli extracted all six properties for AVC into a scratch copy, and `golden-datasets score
  --catalog avc --draft rs-0029` scored it (sc-0045: 1,062 records, rule-matched 94.6% exact). Left over: `check`
  can't run fully offline, because it reads the golden versions from the shared container; that predates this
  phase. The scorer modules now live in `src/xtra/score/` (was `scoring/`), and the Studio didn't import them.
- **Phase 1** (classes, properties, tiers, record key).
  - **Classes:** `classes.py` lists `course` and `learningprogram`: name, rule prefix, sheet tab, xtra `entity_type`
    and CTDL type, required list, and generated-id prefix (`program`, ask 3).
  - **Properties:** `properties/course.csv` and `properties/learningprogram.csv`. Sync reads the class's tab by its
    headers; the path is the CLI Extraction Label, else the CTDL Shorthand URI (LearningProgram's Available At).
    New columns: `phase` (xTRA Status), and `record_key` in place of `course_key`. Tiers are Required, Phase 1 and
    Phase 2. Course's Coded Notation is now Phase 1. LearningProgram's Required is Course's without Coded Notation
    (ask 9).
  - **Rule ids:** LearningProgram rule ids mirror Course's for the same property (`learningprogram-external-id`,
    `-lifecycle`, `-language`), so the classes line up.
  - **Sheet check:** a live-sheet sync of both tabs matches the checked-in files exactly. Against the 2026-11-23
    CSV snapshots, every row, path, label, phase, tier and Single/Multiple matches; only Sample cells differ,
    because that export wrote numbers as floats (`3.0`). The xlsx reader now gives booleans and dates as the sheet
    shows them.
  - **Record key:** `course_key` is renamed `record_external_identifier` in code, API and web types. Its value comes
    from the locator's External Identifier rule, else its Coded Notation rule (normalized as before); the
    `course_key_rule` setting is no longer read or written. In all five local catalogs, every current `course_key`
    equals the External Identifier value, so Course keys don't change. A `generated_id:<type>` transform gives
    `program-<normalized name>`.
  - **`--class`:** required on the item-19 commands (or `GOLDEN_DATASETS_CLASS`), and refused by argparse on the
    others. AI-run env files name the class. `import-v2` is gone from the CLI and the package; its importer lives on
    in `tests/v2_import.py`, only to build the slow tests' AVC fixture.
  - **Fixture:** `tests/programs.py` (two WVU program pages with major codes, one AVC page with a generated id),
    driven by `tests/test_learning_programs.py` through the CLI and the HTTP API.
  - **Checks:** `uv run pytest` 240 passed; `ruff check` clean; web `typecheck` clean, `npm test` 279 passed, build OK.
    `make slow` has the same 9 failures as before this phase (checked on a clean copy of e77f38c); they're stale
    against the local mirror.
  - **Left over:** the server's API is still Course-only (the class in the URL is Phase 4), and `sql`'s `class`
    column comes with the class folders (Phase 2). The app can't serve the local data until Phase 2's migration
    renames `course_key` in the stored files.
- **Phase 2** (storage layout and the migration).
  - **Studio root, per class (`layout.py`):** `manifest.json` (schema 2: per-class `classes` sections at the catalog
    and crawl levels), `<catalog>/<class>/{rules, rulesets, annotations.jsonl, agent-runs, publish.json}`,
    `<catalog>/<crawl>/{pages.parquet, assets/}` and `<catalog>/<crawl>/<class>/{rule-runs/, golden/,
    scores-pending.json}`. The root's `profiles.json` and agent-run files move up to the root.
  - **xtra-cli's container (`xtra_paths.py`; `GOLDEN_DATASETS_XTRA_SOURCE`, the older `GOLDEN_DATASETS_CRAWLS_ROOT`
    still read):**
    - crawls are read in place from each catalog's `crawls_root`; `crawls add` no longer copies;
    - extract outputs are registered and read in place (no copy); an output xtra has overwritten can't be scored
      again;
    - scores go under the output they scored: `…/extract/<output>/scores/<golden>/<class>/sc-NNNN/`.
  - **Per class:** the publish lock, the agent-run folders and the loader's cache keys are per catalog and class.
    `sync` copies only Studio files plus the manifest entry with its `crawls_root` (`--pages` and `--studio-only`
    are gone). `sql` views carry a `class` column, cover every class the catalog has, and `check` uses its own
    class. The API takes `?class=` (Course by default), which Phase 4's URL builds on.
  - **Golden root:** Course keeps today's paths, which xtra-cli reads; every other class sits under `<class>/`.
  - **`golden-datasets migrate --to-classes [--dry-run] [--xtra-root] [--crawls-root]`:**
    - moves everything under `course/`;
    - renames `course_key` → `record_external_identifier` in JSON, JSONL and Parquet, keeping `*.legacy` copies and
      re-hashing each rule run's tables;
    - drops `course_key_rule`;
    - moves copied extract outputs and scores into xtra-cli's container;
    - removes crawl copies only when the same files are found in a crawl root (a symlinked `pages/` is unlinked,
      never followed);
    - writes the schema-2 manifest and keeps the old one as `golden-dataset-studio/manifest.json.legacy`.
  - **Tests:** `tests/test_migrate.py` writes a scored Course catalog back into the legacy layout, migrates it, and
    checks: the manifest is equal, the API serves the same answers, `check` passes, the dry run changes nothing, a
    second run does nothing, a crawl found nowhere else stays, and a symlinked `pages/` keeps its target.
  - **Local run:** `cp -R ~/studio-local/learning-programs/root root-migrated` (`root` stays the before-state),
    xtra-cli's container stood in by `~/studio-local/learning-programs/xtra`, crawls verified against the mirror.
    - Dry run: 4,826 moves listed, nothing changed.
    - Run: 4,826 moved, 227 rewritten, 10 crawl copies removed.
    - Second run: no file changed.
    - training-uark's crawl isn't in the local mirror, so its `crawl.json` copy stays and is read where it is.
  - **Serving:** the before code (e77f38c on a copy of the original root) and this branch (on `root-migrated`) serve
    the same thing for all six catalogs:
    - cards, rule ids, every `course-name` and `course-description` row, records, scores, discussion;
    - AVC sc-0044's values (same hash) and the golden versions.
    - The one difference is approved item 4: `course-code` moved from Required to Phase 1 (Phase 1's change).
    - Screens are in `screens/impl/p2-*.png`. training-uark's pages give 500 before and after, because its HTML was
      never in the local data.
  - **Checks:** `uv run pytest` 243 passed; `ruff` clean; web typecheck clean, 279 passed, build OK. `-m slow` has
    the same 9 failures as the baseline.
- **Phase 3** (scoring by class).
  - **Class filter:** `RecordsStore(…, cls)` hands xtra's scorer only the class's records: an older record by
    `entity_type`, today's `extraction_report/` files by `type`, before `extraction_records` orders and pairs them.
    The columns "xtra extracts" are per class too, from each extractor's declared classes.
  - **Per-property results:** each done score writes, per property it is for and per tree,
    `…/extract/<output>/scores/<golden>-golden|silver/<class>/<property key>/score.json`. It also appends one line
    to `scores/<class>/<property key>/<catalog>.jsonl` in xtra-cli's container. The line holds: the time, catalog,
    crawl and class; the extract run and the golden version; the trigger; the score id; golden and silver counts
    with `exact` and `partial_share` apart and golden's `meets_target` (exact ≥ 0.9, partial never added); the
    xtra-cli version and commit; and `extracted_with` from the output's report when it has one. `scores.history()`
    reads it. The Studio's whole score stays at `…/scores/<golden>/<class>/sc-NNNN/`.
  - **Triggers:** every score carries `trigger` and `properties`.
    - An approval or reset scores that column (`golden-published`).
    - Verdicts gather their columns into `scores-pending.json`, and the pending score covers those.
    - The scheduler goes over each catalog and class. An output the class hasn't scored is `new-output` (every
      property); a newer golden version published from the CLI is `golden-published` (the columns it added, else
      all).
    - CLI and Evals scores are `manual`.
    - The "already scored" checks read the manifest's score paths, not every `score.json`.
  - **Tests:** `tests/test_score_classes.py` covers:
    - a WVU School of Dentistry-style page holding a program and two courses, in both layouts: unfiltered, the
      program takes the first course's place; filtered, each class meets its own;
    - the history line and the per-tree files;
    - a score for some properties records only those;
    - verdicts gather their columns.

    `test_scores` covers both scheduler triggers end to end; `test_approve_publishes` checks an approval scores only
    its column.
  - **Real data:** on `root-migrated`, `golden-datasets score --class course -c avc --draft rs-0029`:
    - against the kept older output (1,062 Course + 3 Competency records, the Competency ones filtered out): 61.5%
      rule-matched exact;
    - against Phase 0's new-layout output: 94.6% exact, `extracted_with: 0.2.0`.

    Both wrote history lines (`scores/course/ceterms_name/avc-….jsonl`).
  - **Checks:** `uv run pytest` 247 passed; `ruff` clean; web unchanged.
  - **Left over:** published golden versions are in the shared container, so scoring against them can't run
    offline here; drafts can.
- **Phase 4** (the UI by class).
  - **The API's class:** every catalog request takes `?class=` (Course when it names none, so Course calls are
    unchanged). A middleware sets it for `studio().ctx()`, and `class=program` is a 422. The catalog answer lists
    the classes with their properties, rules, approved rules and records. A class with no ruleset answers an empty
    catalog, not an error.
  - **The address:** `#/c/<catalog>/<class>/<tab>/<id>`, with `all` for All classes. With All classes, a record
    says its class with `?in=` and a rule with its id. `shell/klass.ts` (`apiClass`, `inClass`, `withClass`) adds
    the class to every catalog call.
  - **Class menu** (w4-class-menu): after the catalog chip. Each class with "45 rules, 22,023 courses, 9
    approved" (or "30 properties, no rules yet"), then All classes. Tabs keep the class; a class with no rules
    shows an empty state.
  - **Rules:**
    - Groups are Required, Phase 1 and Phase 2 (Phase 2 folded), plus "Other record locators" for programs. Each
      group with properties not started says how many.
    - All classes (w4-rules-all-classes): a heading per class ("7 required, 37 properties, 9 of 45 rules
      approved"), and "Search 73 properties in 2 classes".
    - The record key (w2-rules-id-card, w2-rules-id-generated) is `.code.k`, a generated one greyed. A hover card
      (`GET /catalogs/{c}/key-source?occ=`) quotes the page text it was read from, or how it was generated, and
      the page rule with its URL pattern. The strata tags on rows are gone.
    - Wording names the class's records ("the program record", "program pages").
  - **Run with Claude** (w2-run-one-class, w2-run-all-classes):
    - One class: "Run with Claude on LearningProgram rules?", and the other classes stay as they are.
    - All classes: one list with a heading per class ("45 rules, 1 needs work"). A class lists its rules that need
      work or have reviews; the rest wait behind "N more rules with nothing reviewed". It starts one run per class
      with a ticked rule ("Run on 2 rules in 2 classes").
  - **Records** (w2-records-lp, w2-records-all):
    - Items show the name over the identifier, a generated one greyed. A class other than Course sorts by name;
      annotated records stay first.
    - All classes: a folding heading per class, the record's class open.
    - "Values from N pages" and each card's page line show only when the record has several pages.
  - **Datasets** (w2-datasets-lp, w2-datasets-all): All classes has a section per class ("37 properties, published
    as ruleset-v8", "nothing published yet" or "no rules yet"). The empty silver row names the class, and the
    footer's command has `--class`.
  - **Evals** (w2-evals-lp, w2-evals-all, m8-evals-green-bottom): All classes has one History row per class under
    its heading, with one legend; a bar opens that class. Bars stack match at the bottom (m8). Compare with All
    classes says to compare one class at a time.
  - **Engine:** a property definition can have a `fallback` (another read, used when the first finds nothing),
    which is how a page with no printed code gets `program-<name>`. `css+regex` with `join` reads every matched
    element.
  - **Tests:**
    - `tests/test_learning_programs.py`: class summaries, key-source (printed and generated), programs by name.
    - `test_engine`: the fallback.
    - Web:
      - `shell/classes.test.tsx`: the menu, the API's class, Records with one class and with All classes;
      - All-classes cases in `RuleList`, `picker` (one run per class), `GoldenTab` and `EvalsTab`.
  - **Screens** (`screens/impl/`, each named after its mockup, compared with it):
    - They come from a scratch copy of `root-migrated` with a demo LearningProgram ruleset for WVU (105 programs:
      7 printed codes, 98 generated) and one demo "wrong" verdict, served locally. Nothing here is real program
      review.
    - `w2-run-all-classes-scrolled` shows the program part of the list; WVU's Course has a dozen reviewed rules,
      so it starts below the fold.
    - Not shown: `w2-records-multi` (no demo program spans several pages; the rule is in the code and the tests).
    - `w2-evals-lp` is the empty state, because WVU has no local extract output. `w2-evals-all` uses AVC, whose
      local mirror makes 26 Oct the latest output and 28 Oct a scored earlier one.
    - Records opens a record on its Description card, as Course always has, not on Name as the mockup does.
  - **Checks:** `uv run pytest` 251 passed; `ruff` clean; web typecheck clean, 289 passed, build OK.
  - **Left over:** the run bar and the AI runs panel (`AgentProvider`) follow one class. With All classes they
    show Course's runs.
- **Phase 5** (the home page), with three fixes to Phase 4.
  - **Golden dataset view** (w2-home-classes-menu, w2-home-scrolled):
    - A *Classes* menu (each class with its properties and catalogs) ticks the classes whose columns show. They sit
      side by side under a heading per class ("Course 8 required, 7 more in Phase 1, 22 in Phase 2").
    - The columns come in three tiers: Required in bold, then Phase 1, then Phase 2 folded into one column ("6 of 22")
      that opens on a click.
    - Coverage has a line per class. A catalog without a class's rules says "No LearningProgram rules yet" across
      that class's columns, or "Not a LearningProgram source" when the catalog lists the class in `not_sources` (the
      manifest entry, else `catalogs.py`; no catalog does yet).
    - The table waits for every ticked class's summary, so columns don't move. The catalog columns stay fixed when
      it scrolls.
  - **xtra score view** (w4-scores-all, w4-scores-all-numbers, w4-scores-props-menu, w4-scores-one-catalog,
    w3-scores-one-property, w4-scores-one-catalog-one-property):
    - **Menus:** Catalogs (all, or one), Classes, and Properties (under their class, with a search; a class ticks all
      of its own).
    - **Scopes:** the menus pick one of the four. All catalogs and all properties has *Rows: Catalogs | Properties*.
    - **Tables:** each class is its own table. Every row has Golden and Silver lines: a stacked outcome bar with the
      90% target dotted, exact and partial apart (or *Numbers*: a column per outcome), and the last 7 scores as
      stacked bars with an axis, the 90 line and the first and last day.
    - **Navigation:** a row opens the next scope down. One catalog links each property's *Evals →*. One catalog and
      one property shows two large charts (each bar marked golden or output), then each score with its trigger, the
      golden version and the xtra-cli version and commit, and a link into that catalog's Evals tab at the property.
    - **Unscored rows:** rows with no score aren't listed; a line counts them. There is no Score now button.
    - **Sums:** a row's counts are the sum of its pairs' latest scores, so exact is match ÷ values over everything
      the row covers. Its history sums every pair's latest score at each point. Across catalogs, one day is one
      point.
  - **API:**
    - `GET /api/catalogs-summary` takes `?class=` and adds `cls` and `tiers`. Columns are ordered Required, Phase 1,
      Phase 2.
    - `GET /api/score-history?class=` returns the class's properties (column, label, term, tier), its catalogs, and
      per catalog each property's last 7 history lines from xtra-cli's container (one listing, one read per file).
    - `/catalogs` cards add `not_sources`.
  - **Fixes to Phase 4:**
    - The identifier card shows a page rule's URL pattern as a short path (`/graduate/collegeofbusinessandeconomics/…,
      and 1 more`), with the full regex as its tooltip.
    - The page pane's note reads "Name on program-business-administration", with no middle dot.
    - With All classes, the run bar and the AI runs panel poll every class with rules. Each run says its class
      ("LearningProgram: Claude is working on Name"), and a run's actions (report, Cancel) go to its class.
    - Found while doing this: the shared queue only looked at Course runs, so a LearningProgram run neither took a
      place nor showed in *See the queue*. The queue now walks every catalog and class. Runs record their `class`,
      and queue entries show it ("WVU LearningProgram: Name").
  - **Tests:**
    - `test_score_classes`: score history and the class summary with tiers.
    - `test_learning_programs`: a program run takes its place in the shared queue.
    - Web:
      - `ScoreViews.test.tsx`: sums and history, each scope, Numbers, the Properties menu;
      - `CatalogPicker.test.tsx`: tiers, Phase 2 folded and opened, classes side by side, no rules or not a source;
      - `KeyCode.test.ts`: the short pattern;
      - `picker.test.tsx`: runs with All classes.
  - **Screens** (`screens/impl/`):
    - The golden view is real: the scratch root with the demo WVU LearningProgram ruleset.
    - The score views' history is illustrative. Locally only AVC Course has an extract output, so Playwright serves
      generated scores for the real classes, catalogs and properties.
    - `w4-scores-one-catalog-one-property-real` and `w4-scores-all-real` use real AVC scores. These are drafts scored
      on a scratch copy of xtra-cli's container (`score --draft rs-0026|rs-0029 --output <id>`).
    - `w4-scores-by-property-status` (property status) is Phase 6. The mockup's *Score now* is out of scope.
  - **Checks:** `uv run pytest` 254 passed; `ruff` clean; web typecheck clean, 301 passed, build OK.
  - **Left over:** which catalogs are "Not a LearningProgram source" isn't known yet. Set `not_sources:
    ["learningprogram"]` on those catalogs' manifest entries.
- **Phase 6** (findings, property status, discussion), with four fixes to Phase 5.
  - **Storage:** Studio data, per class and property, across catalogs (`findings.py`):
    - `properties/<class>/<property>/findings.jsonl`: append-only, each save is the whole finding, latest wins, and
      the first save says who opened it;
    - `status.json`: Needs review or Done, who set it and when, with the earlier ones kept;
    - `threads.jsonl`: comments on a finding or on a Where-it's-wrong group, in the annotations' comment event
      shape. A comment on one unit stays in the catalog's annotations, as Evals already did.
  - **Who can do what:** anyone sets Needs review; only the SME role sets Done (403 otherwise). A finding never
    closes by itself: at 0 units it says so, and a person sets it fixed.
  - **Live units:** a finding links Where-it's-wrong groups (catalog, outcome, field, grouping and key). Their
    units are counted, golden and silver, in each catalog's latest score: the latest output's, else the newest
    finished score on that basis.
  - **API:**
    - `GET /api/properties/{class}/{property}/review`;
    - `POST …/status`;
    - `POST …/findings`, `PUT …/findings/{id}`;
    - `GET|POST …/threads`;
    - `GET /api/property-status?class=`.
  - **CLI:** `golden-datasets findings list|seed --class`.
  - **Seed:** `seed` imports Seth's Course description codes from the running notes' Extraction Report
    (2026-11-18): D1–D9 (with D1b, which the table lists) and M1–M4. The text is verbatim, with the notes' counts,
    catalogs and whose error (`data/running_notes_description.json`). A second run adds nothing.
  - **Evals** (w4-evals-findings, w4-evals-finding-panel):
    - With a property picked, *Where it's wrong* has a Finding column: the group's finding, or *+ Add finding* (a
      new one, or add the group to an existing finding), and *Discuss* with its comment count.
    - The finding editor is a drawer on the right: code and title, whose error, the units it covers per catalog
      (live), cause, fix and assessment (shown as written, click to edit), state, and its thread.
  - **Review page** (w4-property-review): the one-property scope has the status control at the top (Done only for
    the SME role), and below the scores the findings table: code, kind, partial, wrong and missing as golden /
    silver, catalogs, whose error, state and comments. Each row opens the editor. Choosing one property narrows
    Classes to its class.
  - **Rows by property** (w4-scores-by-property-status): each property shows *Needs review* or *✓ Done*.
  - **Fixes to Phase 5:**
    - The All row's exact is red below 90%.
    - A class with one catalog reads "1 catalog, over its scored properties".
    - UARK is known by its short name: `catalogs.KNOWN` gives `uark`/"UARK" and `not_sources: ["learningprogram"]`,
      so the golden view says "Not a LearningProgram source" with no hand edits. The address takes `uark` too.
  - **Tests:**
    - `tests/test_findings.py`: role rules, findings saved whole and marked fixed, live units from the score,
      threads, the verbatim seed, UARK.
    - Web:
      - Evals: the Finding column, the editor, adding a group to a finding;
      - score views: status tags, the status bar and its role rule, the findings table, a new finding.
  - **Screens:**
    - Taken on the scratch root, with the seed imported and statuses set as in the running notes (description, name
      and identifier: Needs review; codedNotation: Done).
    - D8 and D3 are linked to real AVC groups, and the four comments are demo text. These links and comments are
      illustrative; Seth's text is not.
    - The score tables in w4-property-review and w4-scores-by-property-status use Phase 5's illustrative history.
  - **Checks:** `uv run pytest` 260 passed; `ruff` clean; web typecheck clean, 303 passed, build OK.
- **Phase 7** (the first LearningProgram rules, WVU and AVC), on `root-migrated` with the Studio's own tools:
  `rule try` for each draft, then `rule publish --class learningprogram`, then `properties apply` (27 properties with
  no rule yet). WVU is at ruleset v3 (rs-0003) and AVC at v2 (rs-0002). The published definitions are in
  `rules-phase7/{wvu,avc}.json`, exported with `rule draft`.
  - **Rules:**
    - **Program pages:** WVU pages with a `table.sc_courselist` (degrees, minors, certificates), except five unit
      landing pages, named in the rule. AVC pages at `/program/<name>` with Program Requirements.
    - **Locator:** one program per page.
    - **Name:** the `h1`. On WVU it is above the content root, so the rule reads the whole page.
    - **Description:** WVU takes the paragraph under "Nature of the Program", else the Overview's first paragraph.
      AVC takes the whole `div.introtext`.
  - **External Identifier:**
    - **Printed codes:** the first Major, Minor or Certificate Code the page prints (ask 1).
    - **Shared codes:** five codes are printed by two different programs: 1160, 3075, 3076, 3712 and 8948. The rule
      skips them, so those programs get `program-<name>` (ask 2). The list lives in WVU's rule, not in the engine.
    - **Prefix and fallback:** otherwise `program-<normalized name>` (ask 3).
    - **AVC** prints no codes.
  - **Fill rates:**

    | Catalog | Program pages | Records | External Identifier | Name | Description |
    |---|---|---|---|---|---|
    | WVU | 722 | 593 | 100% (508 printed, 214 generated) | 100% | 73.7% (532) |
    | AVC | 197 | 197 | 100% (all generated, none repeated) | 100% | 100% |

  - **WVU records with two pages:** 129.
    - 110 are pages crawled twice (the same address, or `…/index.html`).
    - The rest are the same degree on two campuses with no printed code (for example Mechanical Engineering,
      B.S.M.E. at Morgantown and WVU Tech). These merge, as Nursing's printed code 8649 already does.
  - **WVU pages with no description (190):** mostly minors and certificates that print only a code and a course
    list.
  - **Code changes:**
    - `engine`: a `fallback` that reads the page (`input: page`) reads it from the document.
    - `check`: such a fallback may give a document-root `css_path`.
    - The identifier card quotes the smallest element that prints the code ("Minor Code - U120"), not the whole tab.
    - Tests are in `test_engine` and `test_learning_programs`.
  - **Screens** (`screens/impl`, against `m3-rules-learningprogram`, `w2-rules-id-card` and `w2-rules-id-generated`):
    - `m3-rules-learningprogram-wvu`, `-wvu-identifier` and `-avc`;
    - `w2-rules-id-card-wvu` and `w2-rules-id-generated-avc`.
  - **Checks:** `uv run pytest` 261 passed; `ruff` clean; `golden-datasets check --class learningprogram` reports
    0 failed for WVU and AVC.
  - **Left over:**
    - A few WVU pages hold two degrees ("Computer Science, M.S.C.S., Ph.D."), or a department heading names a degree
      page ("Department of Mining Engineering"). One record per tab could split the first kind later.
    - No golden values have been labelled yet.
