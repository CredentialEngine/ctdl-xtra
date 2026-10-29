Task ID: golden-dataset-studio-build

You are building **CTDL Golden Dataset Studio** from an approved spec, in waves. This is the P (plan) and I
(implement) steps of a QRSPI process. Q, R and S are done.

## Read first (absolute paths, in another worktree, read-only for you)

QRSPI folder: `/Users/eric/.superset/worktrees/ctdl-xtra/glowing-conchoraptor-79248126/review-ui-v2/qrspi/`

- `03-spec.md`: **the spec, and the source of truth.** Read all of it. Context (§0), scope (§1), vocabulary (§2),
  workflow (§3), data model (§4), real example files (§5), CLI (§6), UI with screenshots (§7, including the tour in
  §7.8), signals (§8), page rendering (§9), performance budget (§10), sequence of work (§11), decisions (§12).
- `02-research.md` and `research/*.md`: the measured facts behind the spec (speed, rendering, data model).
- `01-questions.md`: Eric's own answers, to understand intent.
- `prototype/example-data.md`: real example data in the spec's layout, plus **"Spec feedback"** (items 1–35). Each item
  is a lesson from building the prototype; follow them where the spec is silent.
- `prototype/make_example.py`, `prototype/check_integrity.py`, `prototype/ui/`: a throwaway prototype that already
  builds the AVC data in the spec's layout, checks its integrity, and renders every screen. **Reuse its logic freely**;
  it isn't production code, so restructure it as needed.
- `screens/*.png`: the agreed look of every screen. Match their layout and wording.
- A visual companion of the whole spec: https://claude.ai/artifact/Nco7wuYZyHK9kMDyyzfor8 (it may need sign-in; the
  markdown has everything).

Also relevant:
- `review-ui-v2/` in **your** worktree: the previous tool. Its engine (`server/review_ui/engine.py`, `runs.py`) runs
  the declarative rules; import its v2 rules and review data with `golden-datasets import-v2`. **Don't modify v2.**
- `~/repos/xtra-mockup/viewer/src/Tour.tsx`: the v1 tour to reuse for §7.8.

## Step 1: set up and plan (P)

1. Create the top-level folder `golden-dataset-studio/` in your worktree (spec §12.1). Copy the whole QRSPI folder
   above into `golden-dataset-studio/docs/qrspi/`, so the spec travels with the code.
2. Write `golden-dataset-studio/docs/qrspi/04-plan.md`. Base it on spec §11:
   - the waves below, refined;
   - for each wave, the work streams in it, the files it creates, its acceptance checks (tests, the performance
     budgets of §10 that apply, and the milestone M1–M4 it reaches);
   - and what can run in parallel inside it.
   Don't wait for approval: Eric asked for the build to start. Then build.

## Step 2: build in waves (I)

| Wave | Work streams (spec §11.1) | Gate |
|---|---|---|
| 0 | Scaffolding: one Python package with the `golden-datasets` CLI and a FastAPI server, plus a React + Vite + TypeScript web app (same stack as `review-ui-v2/web`); test, lint and typecheck commands | `golden-datasets --help` runs; CI-style checks pass |
| 1 | **W0** storage layer: local folder or `azure://` root, disk cache, manifest with ETag, append-only log, `golden-datasets sync` | Contract tests pass against a local folder (and Azurite if available) |
| 2 | **W1** page pane + `assets fetch` ∥ **W2** data model + engine: `init`, `import-v2`, `extract` → Parquet, `check`, `sql` | **M1**: AVC end to end from the local mirror; `golden-datasets check` passes |
| 3 | **W3** signals (value, cross-row, page incl. `uncovered-code`; history at read time) | Signal counts on AVC match the prototype's |
| 4 | **W4** UI (catalog picker, Rules tab, Records tab, annotation, "Reviewing as") ∥ **W5** Compare ∥ **W6** Claude loop (`rule show/annotations/draft/try/publish`, `pages get/sample`, prompt generator + Prompt tab) | **M2** then **M3**: the real AVC "prerequisite in Description" fix goes round the whole loop |
| 5 | **W7** golden publication + lineage (existing `xtra-golden-sets-verified` shape + `location` + `golden_id`); the **tour** (§7.8); run all five catalogs | **M4** |

- Inside a wave, run the parallel work streams with subagents on **disjoint files**. Integrate and test before
  moving on.
- **At the end of each wave:**
  1. run every check;
  2. update `golden-dataset-studio/PROGRESS.md` with what was built, the check results, the measured performance
     against §10, and any deviations from the spec;
  3. commit on this workspace's branch with a clear message.
- Keep going to the next wave unless you're blocked.

## Rules

- **The spec wins.** If it's ambiguous, pick the option that best fits its intent (and Eric's answers in
  `01-questions.md`). Log the choice in `golden-dataset-studio/docs/qrspi/06-build-notes.md` and keep going. Only stop
  for a real blocker.
- **Data:**
  - A local read-only mirror of the five catalogs is at `~/review-ui-v3-data/xtra-cli-output/`. Read from it or copy
    from it, but never write into it.
  - Use a local root under your worktree, or the Azure scratch prefix, for everything you write.
- **Azure:**
  - Credentials: `export AZURE_STORAGE_CONNECTION_STRING="$(az storage account show-connection-string -n ceteststorage --query connectionString -o tsv)"`. Never print or save it.
  - You may write **only** under `azure://https://ceteststorage.blob.core.windows.net/xtra-cli-output/zz-scratch-review-ui-v3/`. It's a deletable scratch mirror.
  - Never write elsewhere in `xtra-cli-output`, and never write to the `xtra-golden-sets-verified` container. For
    testing, golden publications go to a local folder or a path inside the scratch prefix.
- **Don't modify** `review-ui-v2/` or `xtra-cli/`.
- **Out of scope** (spec §1.2): login/auth (a "Reviewing as" dropdown only), deploying to Azure, running Claude from
  the UI, fields beyond the minimum required Course fields + Coded Notation.
- **Git:** commit locally on your branch. Don't push and don't open a PR.
- Stop any servers you start.

## Finish

When wave 5 is done, or if you're blocked, end your final response with exactly one of:

```
SUPERSET_WORKER_DONE
task: golden-dataset-studio-build
summary: <one-line outcome>
files: <main paths>
checks: <commands and outcomes, milestones reached>
handoff: <what's left, open questions for Eric>
```

```
SUPERSET_WORKER_BLOCKED
task: golden-dataset-studio-build
reason: <blocker>
needs: <decision, access or dependency>
```
