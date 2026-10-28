# CTDL Golden Rules Studio

Build a golden dataset of CTDL Courses for one catalog by improving **rules**, not by editing records. Jared
reviews one rule at a time across the whole catalog; Claude Code turns his annotations into a new rule version; the
Studio reruns it over every saved page in seconds and shows what changed. When every rule is approved, the
extraction is the golden dataset.

The spec and its research are in [`docs/qrspi/`](docs/qrspi/) (start with [`03-spec.md`](docs/qrspi/03-spec.md)).
Build plan: [`04-plan.md`](docs/qrspi/04-plan.md); choices made where the spec was silent:
[`06-build-notes.md`](docs/qrspi/06-build-notes.md); progress: [`PROGRESS.md`](PROGRESS.md).

## Set up

```sh
uv sync                     # Python 3.12+ package: the golden-datasets CLI and the server
cd web && npm install && npm run build && cd ..   # the web UI (served by golden-datasets serve)
```

Every command takes `--root` or `GOLDEN_DATASETS_ROOT`: a folder, or an Azure prefix such as
`azure://https://ceteststorage.blob.core.windows.net/xtra-cli-output/zz-scratch-review-ui-v3`. For Azure:

```sh
export AZURE_STORAGE_CONNECTION_STRING="$(az storage account show-connection-string -n ceteststorage --query connectionString -o tsv)"
```

Files that never change (pages, Parquet, rule versions) are cached in `~/.cache/golden-datasets`
(`GOLDEN_DATASETS_CACHE`).

## A catalog, from a crawl to a reviewable extraction (spec §3.2)

```sh
export GOLDEN_DATASETS_ROOT=$PWD/.data/root
# a local root whose pages are symlinks into a local mirror of xtra-cli-output (never written to)
golden-datasets sync --from ~/review-ui-v3-data/xtra-cli-output --to $GOLDEN_DATASETS_ROOT -c avc --pages link
golden-datasets init -c avc                    # pages.parquet + manifest
golden-datasets assets fetch -c avc            # CSS, fonts, images, by hash (never runs JS)
golden-datasets import-v2 -c avc --v2-root ~/review-ui-v3-data/xtra-cli-output   # rules v1, rs-0001, Jared's verdicts
golden-datasets check -c avc                   # every key and hash
golden-datasets serve                          # http://127.0.0.1:8000
```

Catalogs: `avc`, `ccsf`, `marshall`, `ualr`, `wvu` (or the full folder names).

**Shared password.** `serve` asks for one password before the profile when the environment sets
`GOLDEN_DATASETS_PASSWORD_HASH` (from `golden-datasets hash-password`, which reads the password and prints a salted
scrypt hash) or `GOLDEN_DATASETS_PASSWORD` (hashed at startup). With neither, there is no password. Signing in lasts
30 days in that browser, across restarts, until the password changes.

## The loop with Claude Code (spec §3.1)

1. In the UI, Jared marks rows ✓ / ✗ (selecting the right text on the page) or asks a question for the institution.
2. **Improve this rule** → Prompt tab → **Copy prompt**, or `golden-datasets prompt -c avc --rule course-description`.
3. Claude Code works only through the CLI:

```sh
golden-datasets rule show course-description -c avc
golden-datasets rule annotations course-description -c avc --open
golden-datasets pages get <stem> -c avc            # the saved page, locally
golden-datasets rule draft course-description -c avc > draft.json   # edit definition + what / how / why
golden-datasets rule try draft.json -c avc         # scorecard over the whole crawl; writes nothing
golden-datasets rule publish draft.json -c avc     # refused if a value marked correct changes (unless --force)
```

4. The UI lists the new ruleset version; **Compare** shows v(n−1) → v(n), Jared's earlier verdicts first.
5. Jared approves the rule or annotates again. When every rule is approved, **Golden** publishes.

```sh
golden-datasets golden publish -c avc --property Description   # into ruleset vN's golden dataset, written whole
golden-datasets golden backfill -c avc     # once: publications from before versions (pub-…) → ruleset-vN
```

A golden dataset's ID is its ruleset's (`ruleset-v3`). Each version is kept at
`<golden root>/catalogs/<catalog>/versions/ruleset-vN/<catalog>/<crawl>/`, and the latest replaces
`<golden root>/<catalog>/<crawl>/` page by page. The golden root defaults to `.data/golden` beside a local root
(`$GOLDEN_DATASETS_GOLDEN_ROOT` overrides; an Azure root publishes to `xtra-golden-sets`). An expert's verdict rewrites
that page's file in both places at once (human-reviewed values, any column) and writes `scores/pending.json`.

```sh
golden-datasets sql -c avc "SELECT rule_id, count(*) FROM matches_latest WHERE status <> 'found' GROUP BY 1"
```

## Evals: score xtra's extract output against the golden dataset (docs/qrspi/evals)

The Studio doesn't run xtra: engineers run `xtra catalog extract`, and the Studio reads what it wrote
(`$GOLDEN_DATASETS_XTRA_SOURCE/<catalog>/<crawl>/records/`, else the shared `xtra-cli-output` container) and scores it
with xtra's own scorer, called in-process (xtra-cli is a path dependency on `../xtra-cli`). Each score is kept in
`<crawl>/golden-dataset-studio/scores/sc-NNNN/` (`score.json`, `values.parquet`) with two results: the human-reviewed
values only, and every rule-matched value. The first time the Studio sees an extract output it copies it into
`extract-outputs/<report last modified>/`, so it stays scorable after xtra overwrites it.

```sh
export GOLDEN_DATASETS_XTRA_SOURCE=~/review-ui-v3-data/xtra-cli-output   # where xtra writes extract outputs
golden-datasets score                       # the latest extract output vs the latest golden dataset
golden-datasets score --ruleset 2           # … vs golden dataset ruleset v2
golden-datasets score --human-reviewed      # … vs the human-reviewed values as they are now
golden-datasets score --draft rs-0004       # … vs an unpublished extraction
golden-datasets score --output <copy id or folder with records/>
```

The server scores on its own: a new extract output against the latest golden dataset, and the human-reviewed values
5 minutes after the last review (`scores/pending.json`, checked every 30 s).

## Develop

```sh
make check          # ruff + pytest + web typecheck / vitest / build
make slow           # end-to-end tests on the local mirror (all five catalogs)
uv run pytest -m azure tests/test_storage_contract.py   # the storage contract on Azurite + the Azure scratch prefix
```

Benchmarks for the performance budgets of spec §10 are in [`bench/`](bench/).
