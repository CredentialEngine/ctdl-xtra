# S — Spec: Evals

How the CTDL Golden Rules Studio shows how closely xtra's extract output matches the golden dataset. Written
2026-10-28 from [`principles.md`](principles.md) and Eric's answers of the same day (recorded in §1). It replaces the
POC's design ([`poc.md`](poc.md)). **Mockups (§6) come first: review them before anything is built.**

## 1. Decisions (Eric, 2026-10-28)

| # | Question | Decision |
|---|---|---|
| 1 | What is a golden dataset version? | **A publication.** There are many more ruleset versions than golden datasets. Each golden dataset comes from exactly one ruleset version. A rule found wrong after publishing is fixed and the column republished, which makes a new version. Each column has exactly one rule (some rules aren't for columns). |
| 2 | Can unpublished rulesets be scored? | **Yes, as clearly marked drafts, and tucked away:** never the first way to do something. |
| 3 | Can a published column be withdrawn? | **Not for now.** Columns only grow. |
| 4 | Where are the extract outputs? | **Wherever xtra-cli already writes them in Azure** (§3.1). The UI says where, in an info popover. Ignore the v2 review UI's folders. |
| 5 | Old extractions score 0 (slot names) | **Checked: Nicolas's branch fixes it** (§3.2), and it's merged here (row 19), so no adapter is needed. |
| 6 | How do scores run? | **xtra's scorer, called as a Python library**, with a subprocess only if its logic ends up gated behind the CLI. A durable async job, shown in the UI at the right moments (§4). |
| 7 | Keep score results? | **Yes**, with provenance: what was scored, against what, by which xtra-cli version, and the equivalent command. |
| 8 | After a publish | **Score automatically** against the latest extract output for that catalog. |
| 9 | All catalogs | **The home page's catalog list becomes a compact table**, with expandable rows that show a short summary. One view shows golden dataset progress and one shows the xtra score (§6.1, §6.2). |
| 10 | Baselines | **Dropped.** There is one golden dataset. "Approved by a person / by its rule" becomes a filter. |
| 11 | The old verified container | **Out of scope.** It isn't imported and isn't mentioned. |
| 12 | Counts | **Values, counted per column.** This view is field-centric, not record-centric. No "N records · M fields" lines. |
| 13 | `ceterms:` names | **In Evals and Publish.** Rules and Records stay as they are. When the prefix makes a label too long, drop `ceterms:` and keep the rest (`description`). |
| 14 | Running extractions from the UI | **Removed**, code and CLI included. Engineers run `xtra extract`, and the Studio only reads its output. |
| 15 | Where to build | In the Superset workspace **evals** (branch `golden-dataset-studio-evals`). |
| 16 | Publishing | **Never merge in place: every publication writes the full golden dataset** (all columns published so far), and each version is kept (§4.1). |
| 17 | Version numbers | **The ruleset number**: golden dataset *v3* comes from ruleset v3. One less lookup. If one ruleset is published more than once, the later ones are *v3.2*, *v3.3*. |
| 18 | xtra-cli in the Studio | **A dependency of the Studio**, from the same repo (`../xtra-cli`). |
| 19 | Nicolas's branch | **Merged into this branch now** (2026-10-28, `6513231`), since it will become the latest xtra-cli. |
| 20 | Home table columns | **The seven Course columns, plus the columns the extract output has that the Studio doesn't cover yet** (credits, prerequisites), shown as "—". |
| 21 | Icons | **The Rules tab's icons** (approved, needs work, in review), reused as they are. |

**Design rule:** simplify and focus. Show one thing well instead of every piece of information.

## 2. Vocabulary

| Term | Meaning |
|---|---|
| **Extract output** | The records `xtra catalog extract` wrote for one crawl of one catalog. Engineers produce it; the Studio reads it. |
| **Golden dataset (version)** | One publication: the full set of values the Studio published for one catalog, from one ruleset version. Named after the ruleset: *v3* (a second publication from the same ruleset is *v3.2*). |
| **Draft** | An unpublished ruleset version's extraction (`rs-NNNN`), scored as if it were a golden dataset. Clearly marked. |
| **Score** | One extract output compared with one golden dataset by `xtra score extraction match`, exact and partial. Kept. |
| **Column** | A `ceterms:` property of the golden dataset (`ceterms:description`). |
| **Value** | One column of one course. |
| **Outcome** | Per value: **missing** (nothing extracted), **wrong** (similarity < 0.8), **partial** (≥ 0.8), **match** (identical). |
| **Not scored** | A column whose values aren't read from the page (`location: null`: `inLanguage`, `lifeCycleStatusType`, `subjectWebpage`). xtra's scorer skips these as *implied* (xtra-cli #343). |

## 3. Facts the design rests on (checked 2026-10-28)

### 3.1 Where extract outputs are

- **The standard place** is `xtra-cli-output/<catalog folder>/<crawl>/records/*.json`, with `extract-report.json`
  beside it. It's the same layout as `crawl.json` and `pages/`.
- **72 crawls** in `xtra-cli-output`; **4 have extract output**: AVC (rewritten 28 Oct 11:49 MDT), Cabrillo (9 Oct),
  Arkansas Tech (8 Oct), Bergen (20 Oct). Of the Studio's five catalogs, **only AVC has one**.
- **One output per crawl, overwritten in place.** Earlier outputs are gone from the bucket.
- **`extract-report.json` doesn't say which xtra-cli version produced it.** It has `schema`, `run_id`,
  `discovery_run_id`, `only_golden_sample`, `pages_considered`, `records_written` and `skipped`. So the Studio can
  only identify an output by its report's last-modified time, its ETag and its counts. Asking engineers to record the
  CLI version in the report is a follow-up, not a blocker.
- **Consequence:** the Studio can't list past outputs from the bucket. Its "extract output" history is the outputs it
  has scored. Each score keeps both values of every row, so a past score stays viewable after the output is
  overwritten.

### 3.2 Will new extractions score?

- `xtra score` reads each record's `expected`, keyed by `ceterms:` terms. Main's extractor writes slot names
  (`course_description`), so its output scores as all missing.
- **Nicolas's branch** (`fix/xtra-cli-extraction-pages-fix`) maps slot names to `ceterms:` terms. It's now merged into
  this branch (`6513231`). Run on AVC's review sample, it wrote `ceterms:codedNotation`, `identifier`, `name`,
  `description`, `subjectWebpage`, `creditValue` and `creditUnitType` for all 11 records.
- AVC's output in the bucket (28 Oct) already has `ceterms:` keys.
- **So there's no adapter.** If an extract output has no `ceterms:` keys (Cabrillo, Arkansas Tech and Bergen still
  don't), its score says so: "this output uses slot names; re-extract with the current xtra-cli".

### 3.3 The scorer as a library

- `implementations.score_extraction_match.match_extraction_run(records_store, baseline_store, catalog, run_id, mode)`
  returns the report as a dict.
- It needs two store objects with `list_keys(prefix)`, `get_json(key)` and `describe_location()`.
- **So the Studio can call it in-process:**
  - records read in place from `xtra-cli-output` (read-only, nothing copied, no report written there);
  - the baseline served from the golden dataset version;
  - the report written into the Studio's own score folder.
- The scorer's `fields` and `outliers` give everything a row needs. With the library there's no need to rebuild rows
  from two report files: `match_entity` returns every field.

## 4. Scores

**Where they're kept:** `<crawl>/golden-dataset-studio/scores/sc-NNNN/`, immutable once done.

| File | Holds |
|---|---|
| `score.json` | status, golden dataset version (or draft `rs-NNNN`), extract output identity (path, report ETag, last modified, `discovery_run_id`, records), scorer (xtra-cli commit), whether the output used slot names (so nothing could match), the equivalent `xtra score` commands, who, when |
| `values.parquet` | one row per scored value: column, course, page, outcome, similarity, golden value, extracted value, golden location, approved by (person / rule) |

- **When a score runs:**
  - **automatically after every publish**, against the catalog's latest extract output (§6.4);
  - when someone presses **Score**, which appears when the chosen pair has no score yet;
  - when someone presses **Score again**, after the extract output has changed since the last score.
- **As a durable job:**
  - `POST /api/catalogs/{c}/scores` writes `score.json` with status `running` and runs the score in a worker
    thread; it's a few seconds for AVC;
  - the UI polls `GET …/scores/{id}`;
  - on server start, a `running` score left by a restart becomes `interrupted`, with a **Score again** button;
  - only one score runs per catalog at a time.
- **The scorer version:** xtra-cli is a dependency of the Studio, from the same repo (uv path dependency on
  `../xtra-cli`; resolution checked on 2026-10-28). The scorer is whatever xtra-cli the branch holds, Nicolas's work
  included, and every score records that commit.
### 4.1 Golden dataset versions

- **Every publication writes the full golden dataset, and every version is kept.** Today a publication merges its
  columns into the files in `xtra-golden-sets`, so v2 is gone from disk once v3 is published. That changes:
  - **Each version is written whole** to its own folder in the shared container, in the layout `xtra score` already
    reads:

    ```
    xtra-golden-sets/catalogs/<catalog>/versions/v3/<catalog>/<crawl>/<stem>/<stem>.json
    ```

    The catalog is the outer level and versions sit inside it (Eric, 2026-10-28). `xtra score` always reads
    `{baseline-uri}/{catalog}/{crawl}/{stem}/{stem}.json`, which is why the catalog appears again inside the version.
    So an engineer can score against any version with the standard command (`--baseline-uri
    …/xtra-golden-sets/catalogs/<catalog>/versions/v3`).
  - **`xtra-golden-sets/<catalog>/<crawl>/`** keeps holding the latest version, replaced whole, never merged. Readers
    of the current location keep working.
  - **The Studio also keeps a Parquet copy,** `golden/<pub>/golden.parquet` (one row per value, about 1 MB for AVC), so
    Evals can load a version quickly.
- **The two existing AVC publications** are rebuilt once from their lineage and the immutable extractions, and
  written as versions v2 and v3.

## 5. What goes away

- Running extractions from the Studio: "+ New extraction", `golden-datasets xtra run`, `serve --allow-runs`, the
  extraction job runner, and the `xtra-runs/` copies.
- The left nav and the baselines (full catalog / hand-checked / verified container).
- Every mention of `xtra-golden-sets-verified`.
- "Records" and "fields" counts in the Evals tab.

## 6. Mockups

Static mockups in [`mockups/mockups.html`](mockups/mockups.html). The numbers are AVC's from the POC, and the other
catalogs' are illustrative. **M2 and M3 are illustrative too:** they show AVC as if `identifier`, `name` and
`description` were published (today only `inLanguage` is, and it isn't scored).

### 6.1 Home: Catalogs, golden dataset progress

![Home, golden dataset](mockups/m1.png)

- **A compact table instead of cards:** one row per catalog, and one column per `ceterms:` property (prefix dropped to
  fit).
- **Each cell is that column's rule status,** with the Rules tab's own icons: approved, in review, needs work. A
  published column also shows the golden dataset version it's in (**v3**) under its icon.
- **Italic columns** (`creditValue`, `creditUnitType`, `prerequisite`) are in xtra's extract output but not in the Studio
  yet. They show "—".
- **Expanding a row** shows three lines: the golden dataset (version, columns, courses), the rules, and what to do
  next.

### 6.2 Home: Catalogs, xtra score (the all-catalog Evals view)

![Home, xtra score](mockups/m2.png)

- **The same table, switched to "xtra score":** match rate and outcome bar per catalog, and match % per column (with
  a thin outcome bar) for the latest golden dataset against the latest extract output.
- **"—"** means the column isn't published yet (or isn't in the Studio). **"not scored"** marks columns that aren't read
  from the page.
- **Expanding a row** shows which golden dataset and which extract output were compared, when, and a link to the
  catalog's Evals tab. That tab is this view filtered to one catalog.

### 6.3 A catalog's Evals tab

![Evals tab](mockups/m3.png)

- **No sidebar.** The header has two searchable dropdowns, **Golden dataset** (default: latest) vs **Extract output**
  (default: latest), plus an ⓘ, the score's time and **Score again**.
- **Below the header:**
  - the match rate;
  - one bar per column (`ceterms:` terms, ascending missing → wrong → partial → match);
  - the outcome filter and **Group by** (subject, course level, value length, xtra extractor, approved by a person or
    a rule);
  - the rows; selecting a row opens its saved page with both values highlighted, as in the POC.
- Columns that aren't scored are named in one muted line under the legend.

![Dropdown and info](mockups/m3b.png)

- **The golden dataset dropdown** lists published versions, newest first. **"Compare with an unpublished ruleset
  (draft)…"** sits at the bottom. A draft score is marked *draft* wherever it shows.
- **The ⓘ popover** says where everything comes from: the extract output path and that it's overwritten each run, the
  golden dataset path, the scorer and its commit, and a **Show the command** link to the equivalent shell command
  (multi-line, Copy in the code block's corner).

### 6.4 Publish, then score

![Publish](mockups/m4.png)

- **Columns are listed by `ceterms:` term.**
- **After Publish,** one line reports the new version and that the latest extract output is being scored against it,
  with **Open in Evals →**.

## 7. Order of work

1. **Golden dataset versions** (§4.1):
   - Publish writes the full dataset, versioned, plus the Parquet copy;
   - backfill v2 and v3;
   - draft versions from `rs-NNNN`.
2. **Scores:**
   - xtra-cli as a path dependency, called as a library;
   - a store adapter over the Studio's roots;
   - `scores/` with its durable job;
   - the CLI `golden-datasets score --golden vN|rs-NNNN`.

   Remove the extraction-running code.
3. **The Evals tab** (§6.3).
4. **The home table** (§6.1, §6.2).
5. **Publish:** `ceterms:` names and auto-score (§6.4).
6. **Tests and checks:** `check` rules (score → golden version and extract identity; values → pages); tour, spec and
   screenshots.

## 8. Open questions

None. Every question was resolved on 2026-10-28 (§1, rows 16–21, and the versioned path in §4.1).
