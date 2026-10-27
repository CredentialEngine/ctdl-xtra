# Golden Dataset Studio: build progress

Plan: [`docs/qrspi/04-plan.md`](docs/qrspi/04-plan.md). Choices where the spec was silent:
[`docs/qrspi/06-build-notes.md`](docs/qrspi/06-build-notes.md).

## Wave 0: scaffolding

- Built: one Python package (`pyproject.toml`, `src/golden_datasets/`) with the `golden-datasets` CLI (every command
  of spec §6 declared; implementations land wave by wave) and a FastAPI app (`server/app.py`); a React + Vite +
  TypeScript web app in `web/` (same stack as review-ui-v2/web, plus jsdom for component tests); `Makefile` with the
  gate checks.
- Checks: `golden-datasets --help` ✓ · `uv run pytest` ✓ · `ruff check` ✓ · `npm run typecheck` ✓ · `npm test` ✓ ·
  `npm run build` ✓
- Deviations: none.

## Wave 1: W0 storage layer

- Built: `storage.py` (one `Root` interface; `LocalRoot` and `AzureRoot` for `azure://https://…/container/prefix`
  and Azurite; conditional writes with ETag / if-none-match; append with 4 MiB append blocks; range reads; disk cache
  in `~/.cache/golden-datasets` for immutable files, ETag-revalidated for mutable ones; server-side copy between
  containers), `manifest.py` (read + update with optimistic concurrency and retry), `log.py` (append-only
  annotation log, incremental reads from a byte offset, event validation), `sync.py` (`golden-datasets sync`, both
  directions, `--pages copy|link|skip`, resumable, the log is appended never overwritten), `layout.py`,
  `catalogs.py`.
- Checks: `tests/test_storage_contract.py`, one contract on three backends: local folder 10/10 ✓, Azurite (podman)
  ✓, Azure scratch prefix (`zz-scratch-review-ui-v3/test-*`, deleted after) ✓ — 28 passed in total. ruff ✓.
- Performance: n/a yet (the layer is what makes §10 possible).
- Deviations: none. Note: local ETags are `mtime_ns-size`; writes to a local root take a `flock` on a sidecar
  `.name.lock` file (dotfiles are hidden from listings).

## Wave 2: W1 page pane ∥ W2 data model + engine → **M1 reached**

- Built (W2, lead): `model.py` (schemas, hashes, keys), `context.py`, `engine.py` (one lxml parse; document-root css
  paths, memoized; textContent offsets; implied tbody), `v2engine.py` (vendored, for the equivalence test),
  `extract.py` (`init`, `extract` with rerun scope by `input_hash` and row-identical copies from the parent),
  `rulesets.py` (versions assigned by `content_hash`; one ruleset version per publish), `import_v2.py` (generic for
  all five catalogs; rules → ruleset v1 → rs-0001 → annotations), `signals.py` (extract-time signals),
  `check.py` (`golden-datasets check`, and the check before every extraction write), `query.py`
  (`golden-datasets sql`: views through the manifest).
- Built (W1, subagent): `assets.py` (`assets fetch`), `render.py` (whole saved page: scripts and handlers removed,
  archived assets, `pane_css` in `<head>`, disk cache), `server/routes_pages.py` (render / source / meta / assets
  routes, CSP `script-src 'none'`, ETags), `web/src/pagepane/` (browser frame, tabs, Page | HTML, highlights by the
  CSS Custom Highlight API + an overlay outside `<body>` so no page element's css path changes, selection capture,
  block picking, prefetch), `bench/check_paths_browser.py`.
- **M1 on AVC from the local mirror**: `sync --pages link` → `init` (1,467 pages) → `assets fetch` (18,564 page→asset
  refs, 34 assets, 1.5 MB) → `import-v2` (17 rules: 3 page, 2 locators, 12 field; 153 annotations: 107 correct,
  5 wrong with expected text, 21 + 7 page-rule verdicts, 8 questions, 5 approvals — the prototype's tally exactly)
  → `extract` rs-0001 (4,401 page labels, 3,813 occurrences, 19,500 matches; `page_labels.parquet` and
  `occurrences.parquet` byte-identical to the prototype's) → `check`: **46 checks, 0 failed, 0.15 s**.
  `golden-datasets sql "SELECT … FROM matches WHERE rule_id = 'course-description'"` answers "every value of rule X".
- Checks: `uv run pytest` (35 passed) · `pytest -m slow tests/test_engine_equivalence.py` (5 catalogs × ~45 pages:
  labels and values identical to v2) · `pytest -m slow tests/test_avc_end_to_end.py` · ruff ✓ · web typecheck ✓,
  vitest 18 ✓, build ✓ · headless Chromium: **388 / 388** engine css paths resolve in the rendered pages, same
  textContent, same offsets.
- Performance (Eric's laptop, local root): init 1.9 s · assets fetch 3.3 s (re-run 2.5 s) · extract rs-0001 2.6 s
  (parse + rules 2.4 s, 10 workers; prototype 3.8 s) · incremental extract of one changed field rule over 1,062
  pages 1.8 s · check 0.15 s · page render cold 94 ms, warm 5 ms (Chromium median 41 ms cold, 1.7 ms warm).
- Deviations: build notes 2–10 and 14–17 (`docs/qrspi/06-build-notes.md`). The one visible difference from the
  prototype's data: description offsets are true DOM textContent offsets (GEOG222 v2 starts at 78, not 70).
