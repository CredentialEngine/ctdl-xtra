# P — Plan: building CTDL Golden Dataset Studio

Phase 4 of QRSPI. It turns spec §11 into waves that can be built and checked one after another. The spec
([`03-spec.md`](03-spec.md)) is the source of truth. Choices made where it is silent are logged in
[`06-build-notes.md`](06-build-notes.md); progress, check results and measured performance are in
[`../../PROGRESS.md`](../../PROGRESS.md).

- Written: 2026-10-26, at the start of the build (Eric asked for the build to start without waiting for review).
- Branch: `golden-dataset-studio` (local commits only, one per wave).

## 0. Shape of the code

```text
golden-dataset-studio/
├── pyproject.toml              one Python package: CLI `golden-datasets` + FastAPI server
├── src/golden_datasets/
│   ├── cli.py                  argparse entry point (every command of spec §6)
│   ├── storage.py              W0  Root (local folder | azure://), disk cache, ETag writes, append, ranges
│   ├── manifest.py             W0  manifest.json read/update with optimistic concurrency
│   ├── log.py                  W0  annotations.jsonl: append, incremental read by byte offset
│   ├── sync.py                 W0  copy Studio files + pages between roots (link / server-side copy)
│   ├── layout.py               W2  every path of spec §4.5, in one place
│   ├── model.py                W2  Parquet schemas, hashes, rule / ruleset documents
│   ├── engine.py               W2  run rules on one page (lxml; document-root css paths; textContent offsets)
│   ├── v2engine.py             W2  vendored copy of review-ui-v2's engine, used only by the equivalence test
│   ├── extract.py              W2  init, extract (rerun scope by input_hash, copy from parent)
│   ├── import_v2.py            W2  v2 rules.json → rule versions + ruleset v1; v2 decisions → annotations
│   ├── check.py                W2  `golden-datasets check` (every PK / FK / hash of spec §4.1)
│   ├── query.py                W2  DuckDB views over the manifest's files (`sql`, server)
│   ├── signals.py              W3  extract-time signals; history signals at read time
│   ├── status.py               W3  rule status + review counts derived from the log
│   ├── assets.py               W1  `assets fetch`; page_assets / assets Parquet; files/<sha256>
│   ├── render.py               W1  whole-page renderer for the pane (scripts stripped, URLs → /assets/<sha>)
│   ├── scorecard.py            W5  comparison library shared by Compare and `rule try`
│   ├── loop.py                 W6  rule show / annotations / draft / try / publish; pages get / sample
│   ├── prompt.py               W6  deterministic prompt generator
│   ├── golden.py               W7  golden publication + lineage
│   └── server/                 FastAPI app; one router module per work stream
├── web/                        React + Vite + TypeScript (same stack as review-ui-v2/web)
│   └── src/{shell,catalogs,rules,records,pagepane,compare,prompt,golden,tour}/
├── tests/                      pytest (unit + contract + AVC end-to-end, marked `slow`)
├── bench/                      performance scripts for spec §10
└── docs/qrspi/                 this folder
```

Checks run at every gate: `uv run pytest`, `uv run ruff check`, `npm run typecheck`, `npm test`, `npm run build`,
plus `golden-datasets check` on every catalog that has data.

Data: a local root at `golden-dataset-studio/.data/root/` (git-ignored) whose `pages/` and `crawl.json` are symlinks
into the read-only mirror `~/review-ui-v3-data/xtra-cli-output/`, made by `golden-datasets sync --link`. v2 inputs
(`rules.json`, review sessions) are read from the mirror with `import-v2 --v2-root`. Azure tests write only under
`…/xtra-cli-output/zz-scratch-review-ui-v3/`.

## Wave 0 — scaffolding

| | |
|---|---|
| Streams | scaffolding (one stream) |
| Files | `pyproject.toml`, `src/golden_datasets/{__init__,cli}.py`, `server/app.py`, `web/*` (Vite + React + TS + vitest), `tests/test_cli.py`, `Makefile`, `.gitignore`, `PROGRESS.md`, `docs/qrspi/06-build-notes.md` |
| Acceptance | `golden-datasets --help` lists every command group of §6; pytest, ruff, `tsc --noEmit`, vitest and `vite build` pass |
| Milestone | — |
| Parallel | nothing (it's small) |

## Wave 1 — W0 storage layer

| | |
|---|---|
| Streams | W0 |
| Files | `storage.py`, `manifest.py`, `log.py`, `sync.py`, `tests/test_storage_contract.py` |
| Acceptance | one contract test suite, run against a local folder and (when reachable) Azurite and the Azure scratch prefix: read/write/exists; conditional write with ETag (a stale ETag is refused); append + incremental read from a byte offset; disk cache hit on second read of an immutable file; `sync` local→local (copy and `--link`), local↔azure |
| Budgets | none yet (the store is what makes §10 possible: no listing at run time, immutable files cached) |
| Milestone | — |
| Parallel | nothing inside the wave |

## Wave 2 — W1 page pane ∥ W2 data model + engine → **M1**

| | |
|---|---|
| Streams | **W2** (lead): `layout`, `model`, `engine`, `v2engine`, `extract`, `import_v2`, `check`, `query`, CLI `init / import-v2 / extract / check / sql` · **W1** (subagent): `assets`, `render`, server route `/pages/...` + `/assets/<sha>`, `web/src/pagepane/` (browser frame, tabs, Page \| HTML, highlights with numbered badges, selection capture → `{text, css_path, char_start, char_end, prefix, suffix}`), CLI `assets fetch` |
| Shared contract | W1 needs only `storage.Root`, `layout` paths and `pages.parquet` (written first, by W2's `init`) |
| Acceptance | AVC end to end from the local mirror: `sync --link`, `init`, `assets fetch`, `import-v2`, `extract` (rs-0001), `check` passes. Row counts match the prototype: 1,467 pages; 4,401 page labels; 3,813 occurrences; 19,500 matches; 153 annotations. An equivalence test runs the vendored v2 engine on a page sample: 0 mismatches. `golden-datasets sql` answers "every value of rule X". Page pane: renders a saved AVC page without scripts, assets from the archive, a match highlighted by css_path, selection captured |
| Budgets | extract AVC ≤ ~5 s (prototype: 3.8 s) |
| Milestone | **M1** |
| Parallel | W1 ∥ W2 on disjoint files |

## Wave 3 — W3 signals

| | |
|---|---|
| Streams | W3 |
| Files | `signals.py`, `status.py`, tests |
| Acceptance | AVC signal counts on rs-0001 match the prototype (contains-label-text 547, duplicate-value 397, unclassified-page-with-codes 129, duplicate-occurrence 114, length-outlier 88, shape-outlier 33, uncovered-code 18; the prototype's names `page-not-classified` / `duplicate-record` become the spec's `unclassified-page-with-codes` / `duplicate-occurrence`). `block-count-mismatch` added. History signals (`previously-wrong`, `previously-correct`, `changed-since-correct`, `new-in-version`, `vanished-in-version`) computed at read time, never stored. Row ordering: severity, signal count, then a seeded sample of rows without signals |
| Milestone | — (prepares M2) |
| Parallel | none; W1 may still be finishing |

## Wave 4 — W4 UI ∥ W5 Compare ∥ W6 Claude loop → **M2**, **M3**

Before spawning, the lead writes the contract: the app shell (top bar, tabs, "Reviewing as", routing), the server
app with one router per stream, `scorecard.py` (shared by W5 and W6) and `web/src/api/types.ts`.

| | |
|---|---|
| Streams | **W4**: catalog picker, Rules tab (rule list with status icons + "N / M reviewed", rows ordered by signals, ✓ / ✗ / comment, highlight-to-annotate, question for the institution, keyboard), locator view (outlined blocks, marked `uncovered-code`, "Add a course this rule missed"), page-rule view ("Add a page this rule missed"), Records tab, Approve / Improve this rule. Server: `server/routes_review.py`. · **W5**: Compare tab (From/To, changed rules, summary line, Why this version, earlier verdicts with word diff, signals before → after with lost/gained, sample, "See on page →"). Server: `server/routes_compare.py`. · **W6**: CLI `rule list/show/annotations/draft/try/publish`, `pages get/sample`, `prompt`; Prompt tab (scope picker, size, Copy prompt, Download .md). Server: `server/routes_prompt.py` |
| Acceptance | **M2**: the Rules tab shows `course-description` on AVC with the full page pane; a verdict is appended to `annotations.jsonl` and survives a reload. **M3**: the real loop on AVC: prompt for `course-description` → a fresh Claude Code agent that sees only the prompt and the CLI → `rule try` prints the scorecard (5 fixed · 0 still wrong · 0 newly wrong; 278 changed) → `rule publish` (refuses if a `correct` value changes, unless `--force`) → ruleset v2 + rs-0002 (2 rules rerun, 15 copied) → Compare shows v1 → v2. `check` passes after publish |
| Budgets (bench/) | open catalog ≤ 300 ms warm / 2 s cold; switch rule ≤ 150 / 500 ms; next row ≤ 100 ms prefetched / 1 s; record verdict ≤ 300 ms; open Compare ≤ 300 ms / 2 s; `rule publish` upload ≤ 15 s |
| Parallel | W4 ∥ W5 ∥ W6 (disjoint directories; shared files owned by the lead) |

## Wave 5 — W7 golden publication ∥ tour; all five catalogs → **M4**

| | |
|---|---|
| Streams | **W7**: `golden.py`, CLI `golden publish`, Golden tab (status per rule, Publish disabled until all approved, what will be written, `golden_id` collisions) · **Tour** (subagent): `web/src/tour/`, reusing v1's `Tour.tsx` approach; 9 steps of §7.8, actions on real data, undo on leave, `Esc`, auto-open once per browser · **Catalogs** (lead): `sync`, `init`, `assets fetch`, `import-v2`, `extract`, `check` on CCSF, Marshall, UALR, WVU |
| Acceptance | **M4**: all five catalogs extracted and checked; a golden publication written to a local folder (and the scratch prefix), existing `xtra-golden-sets-verified` shape + `location` + `golden_id`, lineage complete, `check` passes (lineage FKs, domain-only). `golden_id` collisions listed for Marshall and WVU (~190). `rule try` on WVU ≤ 30 s |
| Parallel | W7 ∥ tour ∥ catalog runs |

## Dependencies

```
W0 ──► W2 ──► W3 ──► (W4 ∥ W5 ∥ W6) ──► W7
  └──► W1 ─────────────┘ (page pane used by W4)
```

The schema of spec §4–5 is the contract between streams. A subagent that needs to change it stops and reports
instead of changing it.
