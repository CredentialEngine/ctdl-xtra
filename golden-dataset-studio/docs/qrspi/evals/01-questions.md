# Q — Questions: the Evals tab

Phase 1 of QRSPI (questions, research, structure, plan, implement) for an **Evals tab** in the CTDL Golden Rules
Studio. It joins the Studio's loop, which makes the golden dataset, with xtra-cli's loop, which is the system under
test. From the tab you trigger an xtra extraction, score it against a version of the golden dataset, see the results
as charts, and drill into the segments of rows that don't agree with the golden set.

- Original prompts: [`prompt.md`](prompt.md)
- Folder: `docs/qrspi/evals/`, next to the Studio's own QRSPI docs
- Asked: 2026-10-27. **Answered 2026-10-27: Eric accepted every default** ("go with these defaults") and asked for a
  proof of concept on a new branch: [`poc.md`](poc.md).
- **The goal of QRSPI here is a spec and an order of work. The build doesn't start in this process.** Code is
  written or run only when it helps answer a question.
- Each question has a **default**: what research works from until you answer. The defaults come from the design
  discussed on 2026-10-27.

### What I already looked at (so the questions are grounded)

- **The scorer is on `origin/extraction_scoring_cli`, not main.** `xtra score extraction match --exactly |
  --partially` reads records from `--source-uri` and the golden set from `--baseline-uri`, at
  `{uri}/{catalog}/{run-id}/{stem}/{stem}.json`. Its reports are written **beside the records**, in the source
  crawl folder: `extraction-match-exact-report.json` and `extraction-match-partial-report.json`.
- **The two loops share one key: the crawl id.** Studio Publish writes `xtra-golden-sets/{catalog}/{crawl}/…`, and
  xtra's run id is the crawl id (`2026-10-12T20-59-13Z`). So `xtra score` already reads what the Studio publishes.
- **Neither side keeps versions where the scorer looks.**
  - xtra's `records/` is overwritten in place; it was last written on 2026-10-26.
  - The older `extractions/<ts>/` folders are v2 review-UI snapshots. They have no `expected` field, so the scorer
    gives every field `missing`.
  - Publish merges into the same golden files. Earlier versions survive only as Studio publications (`publication.json`
    plus `lineage.parquet`, pointing into immutable `rs-NNNN` extractions).
- **Extract takes separate `--source-uri` and `--target-uri`,** so it can read the shared crawl and write somewhere
  else. `--with-template` is deterministic: no LLM reads a page.
- **`xtra-golden-sets` holds only Language today.** GEOG222's file has one field, `ceterms:inLanguage`.
- **Every golden value says who approved it** (commit `fcacef5`). On each field, `approval` is `human` when a person
  confirmed that exact value, else `rule`; `approved_by` and `approved_at` go with it. A record's `approval` is
  `human`, `rule` or `mixed`. The lineage has the same columns.
- **Learning Type has no CTDL term** (`ctdl_property: null`). The scorer keys on `ctdl_property`, so it would count
  Learning Type as `missing` on every page.
- **The two sides pair courses differently.** The scorer pairs a page's entities with records by order
  (`{stem}--{entity}`); the Studio pairs them by `golden_record_id`.
- **The web app has no chart library** (React only), and `strata.py` / `facets.py` already cut rows into segments for
  the Sample drawer.
- **The existing match reports for AVC** (on 2026-10-12T20-59-13Z) scored 14 pages and 108 fields, with an exact
  match rate of 0.648. These came from the verified container, not the Studio's output.

---

## Part A — Questions for you

### A1. Purpose and readers

1. **Who reads the eval, and what decision does it drive?** For example: Eric and the xtra developers deciding what
   to fix in the extractor next, Jared deciding which rows to check by hand, or Credential Engine judging progress.
   *Default: Eric and the xtra developers, to direct extractor work; Jared uses it to pick rows to check.*

2. **Is there a headline number?** The scorer averages nothing, and its only ratio is the exact match rate, per
   property. Do you want a single overall figure per eval as well?
   *Default: no overall figure; exact match rate per property, always with its count.*

3. **Which catalogs?**
   *Default: AVC first (it has the most golden data), then the other four once it works.*

### A2. The golden side

4. **Which golden versions can an eval use?** Publications, the verified container (`xtra-golden-sets-verified`),
   and Studio extractions (`rs-NNNN`) that haven't been published.
   *Default: all three. An `rs-NNNN` golden is badged **unapproved**. It's the only way to evaluate properties
   other than Language until more are published.*

5. **"Hand-checked only" vs "Full":** is hand-checked exactly the fields with `approval: human`? Do the verified
   container's pages count as hand-checked too?
   *Default: yes to both.*

6. **When the verified container and a Studio value disagree, what happens?**
   *Default: the field is listed as a conflict and left out of the hand-checked golden until someone settles it in
   the Studio.*

7. **Learning Type:** leave it out of the eval?
   *Default: leave it out, and say so in the tab.*

8. **Properties outside the Studio's eight** (credits, prerequisites, `isNonCredit`) are in the verified container.
   Should they be scored when the golden is `verified`?
   *Default: yes. The scorer already scores them, and the tab marks them "verified container only".*

### A3. Triggering xtra runs

9. **Who can trigger a run?** The Studio is served over ngrok with basic auth.
   *Default: triggering is off unless the server starts with `serve --allow-runs`. With it on, anyone who can open
   the Studio can trigger runs.*

10. **Which xtra-cli code runs?** Any branch or commit, or a fixed list?
    *Default: any ref, resolved to a commit and recorded with the run. `extraction_scoring_cli` is the default
    until the scorer is merged to main.*

11. **Where does a Studio-triggered run write?**
    *Default: only into the Studio's own folder (`<crawl>/golden-dataset-studio/xtra-runs/x-NNNN/`). Never into the
    shared `records/` or reports.*

12. **Should the team's own `records/` be imported as runs?**
    *Default: yes. Each time it changes (by content hash), it becomes a new run, read-only.*

13. **Which stages can the tab trigger?** Only extract, reusing the newest discovery run? Or discover as well?
    Never crawl?
    *Default: extract only (`--with-template`), with a picker for the discovery run. No discover, no crawl.*

14. **Run scope:** golden sample only (quick), all pages, or both?
    *Default: both. Golden sample is the quick option.*

15. **Does a run score itself straight away?** That would mean extract → score against a default golden in one
    job.
    *Default: yes, optional and ticked by default. The default golden is the newest publication.*

### A4. Scoring

16. **Use xtra's scorer exactly as it is,** even where its choices differ from the Studio's? It pairs courses by
    order, not `golden_record_id`, and exact means byte-identical (`1.0` is not `1`).
    *Default: as it is, so the Studio's numbers equal `xtra score`'s. Pages where the pairing differs are flagged,
    not corrected.*

17. **Is the partial threshold fixed at the scorer's 0.8?**
    *Default: yes.*

18. **Triage in the first version?** Buttons on each disagreement: "golden is wrong" writes an annotation on the
    Studio row; "xtra is wrong" goes on an xtra failure list.
    *Default: the first version is read-only. Triage comes later, along with a `xtra disagrees` signal on the Rules
    tab.*

### A5. Charts and segments

19. **Are these the right charts?**
    - outcomes by property (stacked bars, one per golden);
    - similarity of the fields that aren't exact (histogram with the 0.8 line);
    - segment heatmap (segments × properties, share not exact, with counts);
    - "disagree most" (segments ranked by how far their rate sits above the overall rate);
    - history grid (xtra runs × golden versions) and a trend per property;
    - compare two evals (fixed, still wrong, newly wrong).
    *Default: all six; the first four in the first version.*

20. **Which segments would Jared and you want that the data doesn't obviously give?** Course level (100 / 200 /
    900), credit vs noncredit, catalog section or department, page type (course page vs program-page course line)?
    *Default: everything `strata.py` already has, plus property, outcome, similarity bucket, extractor
    (`template_id`), page status, approval (field and record), approved by, and approval date. Course level from the
    coded notation, if it's easy.*

21. **Sharing and export:** should a filtered view be a link you can send? A CSV of the rows?
    *Default: the URL holds the eval, golden toggle and filters; a CSV download of the current rows.*

### A6. Scope and process

22. **The spec's boundary changes.** §1.2/§1.3 say the Studio only *imports* from xtra-cli. With this plan it also
    *runs* xtra-cli, writing only into its own folder. Is that OK? Does the xtra team need to hear about it first?
    *Default: OK. Spec updated, and the xtra team is told once a first version works.*

23. **Where does the work happen?** On `golden-dataset-studio`, or in its own Superset workspace and branch?
    *Default: its own workspace, branch `golden-dataset-studio-evals` off `golden-dataset-studio`.*

24. **How far does this QRSPI go?** As before: questions, research, spec, plan, then a build prompt?
    *Default: yes. No building in this process.*

---

## Part B — Facts I'll find out myself (research phase)

- B1. **The match reports' shape:** do they hold a row for every field, exact matches included? Can
  `fields.parquet` be built from the two reports alone, without the scorer as a library?
- B2. **Source ≠ target:** does extract read pages and discovery only from `--source-uri`, and write only to
  `--target-uri`? Does score write its reports only beside the records it read?
- B3. **How long extract takes** for AVC, golden sample and all pages, against Azure and against a local copy.
- B4. **How the scorer handles the Studio's files:** extra keys (`approval`, `location`), `golden_record_id`,
  `ctdl_property: null`, and pages with several courses (AVC, Marshall).
- B5. **Running xtra-cli from a pinned ref** with `uvx --from git+…@<sha>`: install time, caching, and whether
  extract needs Playwright.
- B6. **Jobs in the FastAPI server:** a subprocess per job, its log and progress, cancelling it, one job per catalog,
  and keeping the manifest consistent while a job writes.
- B7. **Joining xtra records to Studio rows** (stem + entity index ↔ `occurrence_key`). The join is needed for
  segment columns and for highlighting values in the page pane.
- B8. **The hand-checked golden today:** how many `human` values exist per catalog and property, and how many fields
  the verified container has.
- B9. **The verified container vs Studio files:** format differences, and how many values conflict.
- B10. **Size and speed** of an eval and its queries for all five catalogs.
- B11. **Charts without a library:** what the hand-built SVG components need, following the dataviz guidance, in
  light and dark themes.

---

## Part C — Work streams and order (first guess)

| # | Work stream | Depends on | Can start now? |
|---|---|---|---|
| E1 | **Eval engine + CLI:** import `records/` as a run, write a golden version as a baseline (hand / full), run the scorer, build `fields.parquet`; `golden-datasets eval run` | B1, B2, B4 | **Yes** |
| E2 | **Job runner + `xtra run`:** `uvx` at a pinned ref, logs, lock, cancel, `--allow-runs` | B2, B5, B6 | **Yes**, alongside E1 |
| E3 | **Tab, part one:** run panel, jobs strip, eval picker, Hand-checked / Full toggle, outcome bars, similarity histogram | E1 (E2 for the run buttons) | Mock-ups yes |
| E4 | **Segments:** dimensions, heatmap, "disagree most", filter bar, rows list with the page pane | E1, B7 | After E1 |
| E5 | **History:** grid, trends, compare two evals | E1 with several evals | After E3 |
| E6 | **Back into the rule loop:** `xtra disagrees` signal, triage → annotations | E4 | Later |

Order: **(E1, E2) → E3 → E4 → E5 → E6**. Spec, tour, screenshots and `check` rules land with each stream.
