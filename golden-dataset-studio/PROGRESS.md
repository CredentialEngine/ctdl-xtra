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

## Wave 3: W3 signals

- Built: extract-time signals (`signals.py`, landed with wave 2 because `extract` writes them) and the read model
  `review.py`: verdicts carried forward to the current rule version (fixed / still wrong / changed since correct),
  re-attachment by course key + page when an occurrence key changes (D3), history signals at read time
  (`previously-wrong`, `previously-correct`, `changed-since-correct`, `new-in-version`; `vanished-in-version` in
  Compare), rule status (approved / needs work / in review) and the Rules tab's row order.
- **Signal counts on AVC rs-0001 match the prototype** for every signal both have: contains-label-text 547,
  duplicate-value 397, unclassified-page-with-codes 129, duplicate-occurrence 114, length-outlier 88,
  shape-outlier 33, uncovered-code 18 (new: block-count-mismatch 1). After the description fix (rs-0002):
  contains-label-text 273, as in the prototype.
- Statuses on AVC v1 match the prototype's table: 5 of 17 approved (the constant / URL rules); needs work:
  `course-description` (5 wrong) and `program-page-with-courses` (Jared's 7 rejections, spec §12.2 Q1). With v2,
  `course-description` goes back to in review (its 5 wrong rows are fixed).
- Checks: `pytest -m slow tests/test_avc_end_to_end.py` (4 passed: counts, incremental rs-0002 with 278 changed
  descriptions, check, API statuses / rows / verdict / approve refused while wrong).
- Performance (local): load an extraction into memory 60 ms; all 17 rule statuses 30 ms; order 1,062 rows 2 ms.
- Deviations: build notes 11–12.

## Wave 4: W4 UI ∥ W5 Compare ∥ W6 Claude loop → **M2 and M3 reached**

- Built (lead, before spawning): the contract — `server/routes_review.py` (catalogs, rules, rows, overlays,
  courses, annotations), `scorecard.py`, `server/routes_compare.py`, `web/src/api/{types,client}.ts`, the app shell
  (`web/src/shell/`: routing, top bar, "Reviewing as", key hints, icons), the catalog picker; gzip on the API.
- Built (W4, subagent): Rules tab (`web/src/rules/`: rule list by kind with status icons and "N / M reviewed",
  rule head with Improve this rule / Approve (greyed with the reason while anything is wrong or missing) / reopen,
  "How this rule works ▸", rows ordered by signals that fade once judged, ✓ / ✗ with select-the-right-text,
  comment + "question for the institution", keyboard Tab/A/W/C/H/Enter/Esc, record-locator view with outlined
  blocks, marked uncovered codes and "Add a course this rule missed", page-rule view with "Add a page this rule
  missed", the page pane with prefetch), Records tab (`web/src/records/`), `bench/bench_review.py`,
  `bench/shots_review.py`, API extensions (`focus=` for "See on page", `page-search`).
- Built (W5, subagent): Compare tab (`web/src/compare/`), scorecard ordering by history (A4.1), signal lost/gained
  lists, `bench/bench_compare.py`.
- Built (W6, subagent): `loop.py` (`rule list / show / annotations / draft / try / publish`, `pages get / sample`),
  `prompt.py` + `server/routes_prompt.py` + Prompt tab, `bench/bench_loop.py`.
- **M2**: on AVC the Rules tab shows `course-description` with the full page pane; a verdict made in headless
  Chromium (wrong + selected text + note) is appended to `annotations.jsonl` and shows after a reload.
- **M3, the loop closes on the real problem**: the Prompt for `course-description` (11,689 chars ≈ 2,922 tokens,
  5 page references, no raw HTML) was handed to a **fresh Claude agent with nothing else**. Using only the CLI it
  ran `rule show / annotations / pages get / sql / rule draft`, six `rule try` iterations, then `rule publish`:
  ruleset v2 + rs-0002 (course-description rerun on 1,062 pages, 16 rules copied). Scorecard: **5 fixed · 0 still
  wrong · 0 newly wrong · 9 unchanged**, 265 values changed, contains-label-text 547 → 285. Compare (UI API) shows
  v1 → v2 with the same numbers; `check` passes, with 18,438 copied rows identical to rs-0001. The rule went from
  needs work to in review. (The prototype's own v2, in `.data/root-demo`: 278 changed, 547 → 273.)
- Checks: `pytest` 49 fast + 25 slow ✓ (incl. `test_loop.py`: a draft that also drops "Advisory:" lines is
  refused because ACCT199, AERO199, CFE114, NS922L would change) · ruff ✓ · web typecheck ✓, vitest 60 ✓, build ✓
  · `check` on all five catalogs ✓.
- **Performance vs §10** (`bench/bench_budgets.py`: a fresh `serve` process, empty disk cache, then warm):

  | Action | Azure scratch cold | warm | Local cold | warm | Budget cold / warm |
  |---|---|---|---|---|---|
  | Open catalog, rule list shown | 1.33–1.52 s | 89 ms | 183 ms | 15 ms | 2 s / 300 ms |
  | Switch rule, rows shown | 50 ms | 47 ms | 13 ms | 10 ms | 500 / 150 ms |
  | Next row, page pane updated | 0.88–0.98 s (not prefetched) | 1.6 ms (prefetched) | 50 ms | 1.4 ms | 1 s / 100 ms |
  | Record a verdict | 154–160 ms | 135–165 ms | 3 ms | 2 ms | 300 / 300 ms |
  | Open Compare | 106–109 ms | 39–41 ms | 66 ms | 3.7 ms | 2 s / 300 ms |
  | `rule try` on WVU (largest) | | | 3.4 s | | 30 s |
  | `rule publish` upload | | | AVC 0.03 s, WVU 0.23 s | | 15 s |

  In Chromium end to end (W4): next row 96 ms, switch rule 137 ms (warm, local). The first Azure cold run of
  "open catalog" was 2.1 s; fetching the 17 rule files and 5 Parquet files in parallel brought it to 1.3–1.5 s.
- Deviations: build notes 23–27; W4's (a "fixed" or "changed since correct" row doesn't fade, it needs a fresh
  look; the program-page bubble count includes the page-level questions).
