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
