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
