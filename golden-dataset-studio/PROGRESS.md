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
