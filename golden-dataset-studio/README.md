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
golden-datasets golden publish -c avc --to <golden root>   # existing xtra-golden-sets-verified shape + location + golden_id
golden-datasets sql -c avc "SELECT rule_id, count(*) FROM matches_latest WHERE status <> 'found' GROUP BY 1"
```

## Evals: score xtra-cli against the golden set (docs/qrspi/evals)

The Studio runs xtra-cli (at a pinned commit) into its own folder and scores the run with xtra's own scorer, against
the hand-checked values and against the whole golden version. The team's `records/` and reports aren't touched.

```sh
export GOLDEN_DATASETS_XTRA_SOURCE=~/review-ui-v3-data/xtra-cli-output   # where xtra reads the crawl and discovery
golden-datasets xtra run --import                      # the team's records/ as run x-NNNN
golden-datasets xtra run --sample --ref <branch> --then-eval rs-0003
golden-datasets eval run --xtra-run x-0001 --golden published|verified|rs-NNNN
golden-datasets eval show
golden-datasets serve --allow-runs                     # the Evals tab may start runs and evals
```

## Develop

```sh
make check          # ruff + pytest + web typecheck / vitest / build
make slow           # end-to-end tests on the local mirror (all five catalogs)
uv run pytest -m azure tests/test_storage_contract.py   # the storage contract on Azurite + the Azure scratch prefix
```

Benchmarks for the performance budgets of spec §10 are in [`bench/`](bench/).
