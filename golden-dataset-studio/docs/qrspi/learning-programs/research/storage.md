# Where xtra-cli and Studio data live, and a proposed split

Research for wave 2, 2026-11-24. Read-only: files and issues only.

**Caveat:** this worktree's `xtra-cli/` is behind `origin/main`. Main has two changes that matter here:
- per-property extraction (#376);
- `xtra score … --property` (#449), with the command at `src/xtra/score/` (here it is `src/xtra/scoring/`). It writes to
  `extraction_report/<prefix>/<prop>/`.

## 1. Today's layout

The Studio's root is a prefix inside xtra-cli's own container:
`azure://…/ceteststorage…/xtra-cli-output/zz-scratch-review-ui-v3` (`golden-dataset-studio/src/golden_datasets/cli.py:24`).
`layout.py:1-8` defines what goes under it:

- `<root>/golden-dataset-studio/manifest.json`
- `<root>/<catalog>/golden-dataset-studio/{rules/, rulesets/, annotations.jsonl, agent-runs/}`
- `<root>/<catalog>/<crawl>/{crawl.json, pages/}`. These are **copies** of the crawls, made by `golden-datasets sync`
  (`sync.py:1-12`).
- `<root>/<catalog>/<crawl>/golden-dataset-studio/`:
  - `pages.parquet`, `assets/`
  - `extractions/rs-NNNN/`: the Studio's own rule runs (`layout.py:78`)
  - `golden/ruleset-vN/` (`:87`)
  - `scores/{pending.json, sc-NNNN/{score.json, values.parquet}}` (`:91-102`)
  - `extract-outputs/<report-mtime>/{records/, extract-report.json}`: copies of xtra's outputs (`:105-107`)

Two settings point elsewhere:

- **`GOLDEN_DATASETS_XTRA_SOURCE`:** where xtra-cli writes extract outputs. The default is `azure://…/xtra-cli-output`
  (`scores.py:56,214-221`).
- **`GOLDEN_DATASETS_GOLDEN_ROOT`:** where golden versions are published. The default is
  `azure://…/xtra-golden-sets` (`golden.py:246-257`). Versions sit at
  `catalogs/<catalog>/versions/ruleset-vN/{silver,golden}/…`, plus a latest copy at `<catalog>/<crawl>/`.

## 2. Where xtra-cli reads and writes

- **URIs:** `--source-uri`, `--target-uri` and `--baseline-uri` come from the flag, then `--env`/`XTRA_ENV`, then the
  active environment (`xtra-cli/README.md:82-139`).
- **Output folder:** everything goes to `{target}/{catalog}/{crawl-run}/`, the same folder as `crawl.json`, `pages/` and
  `discovery/`. That includes `extract-report.json`, `records/`, `jsonld/`, `expected/` and the
  `extraction-match-{exact,partial}…-report.json` files (README `:992-1030`).
- **Runs overwrite each other.** There is one output folder per crawl, so old outputs and old scores are lost, and
  stale records stay behind. The Evals spec records this (`evals/03-spec.md:85-99`), and its follow-up is "write each
  run to its own folder" (`:447-448`).

## 3. Scoring today

- **Scorer:** `match_extraction_run` (`xtra-cli/src/implementations/score_extraction_match.py:762`).
- **xtra-cli command:** `xtra score extraction match --exactly|--partially` writes its report next to the records.
- **Studio:** `golden-datasets score` and the server call the scorer in-process.
  - The first time it sees an extract output, it copies the output into `extract-outputs/` (`scores.py:246-280`).
  - It writes `scores/sc-NNNN/` under the Studio folder (`scores.py:537,670`).
  - It scores twice: once against the golden (human-reviewed) tree and once against the silver (rule-matched) tree.
- **Daily "Extraction report":** no script in the repo produces it. Seth posts it by hand in the running notes.

## 4. Related issues

- **#447** (assigned to Rohit and Sneha) and **#386:** integrate xtra-cli's inputs and outputs into the xTRA UI.
- **#384 (Phase 2):** migrate the inputs and outputs from the xTRA CLI to the xTRA UI.
- **#379:** the Studio is temporary. Golden sets move to the xTRA UI in Phase 2.
- **#342:** the scoring report and evidence are saved in the project folder.
- **#394:** the 90% target.

None of these discusses where outputs should go.

## 5. Proposal

| What | Owner | Where |
|---|---|---|
| Crawls | xtra-cli | `xtra-cli-output/<catalog>/<crawl>/{crawl.json, pages/, discovery/}`. The Studio reads them in place, with no copies. |
| Extract runs | xtra-cli | `xtra-cli-output/<catalog>/<crawl>/extract/<extract-run-id>/{extract-report.json, records/}`. Each run gets its own folder (an xtra-cli change). |
| Scores | xtra-cli | `…/extract/<extract-run-id>/scores/<baseline>/<class>/<property>/{exact,partial}.json`, where `<baseline>` is e.g. `ruleset-v3-golden` or `ruleset-v3-silver`. |
| Score history | xtra-cli | `xtra-cli-output/scores/<class>/<property>/<catalog>.jsonl`: one appended line per score. The daily report and its trend lines read these small files. |
| Golden and silver versions | shared | `xtra-golden-sets/catalogs/<catalog>/versions/…`, as today. This is the baseline xtra-cli reads. |
| Studio data | Studio | Its own container, `golden-dataset-studio/`: `<catalog>/<class>/{rules, rulesets, annotations.jsonl, agent-runs}` and `<catalog>/<crawl>/{pages.parquet, assets/, <class>/rule-runs/rs-NNNN/}`. |

`extractions/` becomes `rule-runs/`, so it can't be confused with xtra's extract runs.

**The migration:**
1. Move each `extract-outputs/<id>/` into its extract run folder. This brings back the run history.
2. Move each `scores/sc-NNNN/` to the scores path, using the keys in its `score.json`.
3. Move everything else under `zz-scratch-review-ui-v3/**/golden-dataset-studio/` to the Studio container, into
   `course/`.
4. Check the crawl copies against the originals, then delete them.

**Do it once:** this should happen together with the move to class folders, so the data migrates once.

**Code to change:**
- Studio: `layout.py`, `scores.py:56,214-280`, `cli.py:24`, `sync.py`.
- xtra-cli: `common/keys.py` (`run_prefix`, `extract_report_key`, `extraction_match_report_key`).
