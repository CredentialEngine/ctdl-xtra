# Repository Guidelines

## What CTDL xTRA Does
- Automates crawling of institution sites to capture courses, credentials, competencies, and learning programs.
- Uses LLM-assisted recipes to detect navigation patterns, fetch paginated content, and extract structured CTDL data for bulk upload to the Credential Registry.
- Provides a React UI for configuring runs and a Fastify/tRPC backend with BullMQ workers and Puppeteer-based scraping.

## Project Structure & Module Organization
- `client/`: React + TypeScript front-end (Vite, Tailwind, shadcn/ui) with routes and UI in `client/src`; static assets in `client/public`.
- `server/`: Fastify + tRPC API and BullMQ workers in `server/src`; integration/model-eval tests in `server/tests`; database migrations in `server/migrations`; worker entrypoint scripts alongside Docker assets.
  - `server/src/routers`: tRPC routers and route composition (`appRouter.ts`).
  - `server/src/workers`: BullMQ processors and worker orchestration (`worker.ts`).
  - `server/src/extraction` + `server/src/data`: crawling, parsing, and structured data helpers.
  - `server/src/emails`: React Email templates and `email.tsx` wiring.
  - `server/src/utils.ts`, `openai.ts`, `fastifySessionAuth.ts`, `fastifyAirbrakeNotifier.ts`: shared utilities, OpenAI helpers, session, and monitoring hooks.
- `common/`: Shared helpers/types consumed by both client and server.
- `doc/`: Reference notes on competencies, embeddings, worker queues, and related research.
- Root scripts include `scripts/dev.js` for orchestrating multi-service dev sessions.

## Client Pages (components/app)
- `/` (`welcome.tsx`): Landing card with a prompt to create a catalogue.
- `/login` (`login.tsx`) and `/logout` (`logout.tsx`): Auth flow and session teardown.
- Shell (`dashboard.tsx`): Sidebar/header layout; renders all routes and toasts.
- Catalogues (`catalogues/index.tsx`, `/new`, `/detail.tsx`, `/extract.tsx`): List/add catalogues, view catalogue detail, start an extraction for a recipe.
- Recipes (`recipes/create.tsx`, `edit.tsx`): Create or edit crawl recipes scoped to a catalogue; includes regex helper (`TestLinkRegex.tsx`).
- Extractions (`extractions/index.tsx`, `detail.tsx`, `step.tsx`, `page.tsx`): Monitor extraction runs, step statuses, and individual crawled pages/items.
- Datasets (`datasets/index.tsx`, `detail.tsx`, `items.tsx`): View generated datasets by catalogue and inspect exported items.
- Users (`users/index.tsx`, `create.tsx`, `reset-password.tsx`, `delete.tsx`): Administer user accounts.
- Profile/Settings (`profile/index.tsx`, `settings/index.tsx`, `settings/openapi.tsx`, `settings/proxy.tsx`, `settings/budget.tsx`): Update own profile; manage API keys, proxy settings, budget controls.
- Fallbacks (`unauthenticated.tsx`): Guarded view shown when auth is missing.

## Build, Test, and Development Commands
- Install deps: `pnpm install` run separately inside `client/` and `server/` (Node 20+).
- Full-stack dev (client + server + worker): `node scripts/dev.js` from repo root.
- Client: `pnpm run dev` (HMR at :5173), `pnpm run build`, `pnpm run preview`, `pnpm run lint`.
- Server/API: `pnpm run dev`, `pnpm run dev:worker` for BullMQ worker, `pnpm run dev:email` to preview transactional emails.
- Database ops: `pnpm run db:generate` then `pnpm run db:migrate` (PostgreSQL + Drizzle).
- Tests (server): `pnpm test` or `pnpm run test:html` (vitest). Tests may hit real OpenAI APIs; set env vars accordingly and avoid running in CI without mocks.

## Coding Style & Naming Conventions
- TypeScript everywhere; prefer explicit types on public functions and API surfaces.
- Formatting: Prettier defaults (2-space, semicolons=false per project configs); run `pnpm exec prettier --check .` before committing if you touch formatting-heavy files.
- Linting: ESLint with TS/React rules in `client`; keep hooks and dependency arrays clean. Follow existing naming: PascalCase for React components, camelCase for helpers, SCREAMING_SNAKE_CASE for env keys.
- Tests live in `server/tests` and end with `.test.ts`; fixtures under `server/tests/fixtures` or `server/tests/extractions`.

## Testing Guidelines
- Target vitest for API/workflow coverage; prioritize model-eval style assertions already present in `server/tests`.
- Add new tests alongside the code path touched; mock external services unless intentionally measuring real responses.
- For database changes, include migration plus a minimal test that exercises the new schema behavior.

## Commit & Pull Request Guidelines
- Commit messages follow a concise, present-tense style (e.g., `Add backend support for rerunning data extractions`, `Dynamic URL harvesting (#153)`). Keep the subject under ~72 chars and reference issues/PR numbers when applicable.
- PRs should state scope, rationale, and testing done; include screenshots or console snippets for UI or DX changes.
- Link related issues or tasks, call out breaking changes, and note any new env vars or migrations required for reviewers.

## Security & Configuration Tips
- Copy `.env.example` to `.env` in both `client/` and `server/`; never commit secrets. Generate `COOKIE_KEY` for secure sessions (`pnpm exec secure-session | xxd -p -c 0`).
- Keep API keys and database URLs out of logs; use local `.env` and pass secrets via deployment config.
- When adding new scraping logic, guard puppeteer usage with sensible timeouts and domain allowlists to avoid unintended crawl scope.
