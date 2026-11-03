# CTDL Golden Dataset Studio

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

## Properties: one rule per CLI Extraction Label ([`docs/qrspi/property-rules`](docs/qrspi/property-rules/03-spec.md))

Every property of the "xTRA: Learning Opportunity BU Template" sheet's Phase 1 Extraction tab (column F), plus
Learning Type, is a property rule in every catalog: 43 in all, listed in the checked-in
[`src/golden_datasets/properties.csv`](src/golden_datasets/properties.csv). Nested properties are flat paths
(`ceterms:creditValue>schema:minValue`), shown with arrows. The app never reads the sheet: sync it into the file,
review the diff like code, then add the new properties to each catalog with no rule yet (`rule_type: none`).

```sh
golden-datasets properties sync [--from bu.xlsx | phase1.csv]   # the sheet → properties.csv: added / kept / removed
golden-datasets properties list
golden-datasets properties apply --all     # one ruleset version per catalog that gets new properties
golden-datasets prompt --first-rules -c avc   # the Generate rules prompt: write the rules still missing
```

A property rule says what it reads (`input`: the record, the whole page, the URL or another rule's output, so a child
like Credit Unit Max Value reads Credit Value's text), can give a list (`multiple`: split elements, a separator or a
regex, and `keep`), and has `labelled`, `attribute` and `join` for text a selector can't reach alone. A list shows one
row per course with a ✓ / ✕ per item. Anyone can annotate any property, a rule or not.

## The loop with Claude Code (spec §3.1)

1. In the UI, Jared marks rows ✓ / ✗ (selecting the right text on the page) or asks a question for the institution.
2. **Improve all rules with Claude** (foot of the rule list) → the prompt → **Copy prompt**, or
   `golden-datasets prompt -c avc --rule course-description`.
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
5. Jared approves the rule or annotates again. **Approving a column's rule publishes its silver dataset** (after one
   confirmation: how many values go in, and that the golden dataset doesn't change): the column goes into its
   ruleset's **silver dataset**, also called the rule-matched dataset (the first approval creates `ruleset-vN` with
   every column approved so far; later ones write it again with the extra column), then xtra's latest extract output
   is scored against it. The **golden dataset** is only the values an expert reviewed, in any property: it grows with
   each expert verdict, not with approvals. Page rules and record locators approve as before; a column with no CTDL
   term (Learning Type) is approved but not written to the files. The **Datasets** tab is a read-only record: the
   golden dataset by property, and each silver version's columns, values and latest xtra score, and where it is
   written, each file a link to a sample. Engineers can still publish from the CLI:

```sh
golden-datasets golden publish -c avc --property Description   # into ruleset vN's silver dataset, written whole
golden-datasets golden backfill -c avc     # once: publications from before versions (pub-…) → ruleset-vN
golden-datasets golden backfill -c avc --again   # also write every version again in the current layout
```

A version's ID is its ruleset's (`ruleset-v3`). Each version is kept as two parallel trees,
`<golden root>/catalogs/<catalog>/versions/ruleset-vN/silver/<catalog>/<crawl>/` (every value: the silver dataset) and
`…/ruleset-vN/golden/<catalog>/<crawl>/` (only the `approval: human` values, only the pages that have one: the golden
dataset), and the latest version's silver tree replaces `<golden root>/<catalog>/<crawl>/` page by page, which is what
xtra's scorer reads by default. Versions written before the property list keep their folders, `rule-matched/` and
`human-reviewed/`. Version trees hold
`<stem>.json` only; `<stem>.html` (the page as crawled) is only at the latest location. Values with no CTDL term
(Learning Type) stay out of the files (`xtra score` rejects them) and in the Studio's lineage and `golden.parquet`. The
golden root defaults to `.data/golden` beside a local root (`$GOLDEN_DATASETS_GOLDEN_ROOT` overrides; an Azure root
publishes to `xtra-golden-sets`). An expert's verdict rewrites that page's file in all three places at once
(human-reviewed values, any column) and writes `scores/pending.json`.

```sh
golden-datasets sql -c avc "SELECT rule_id, count(*) FROM matches_latest WHERE status <> 'found' GROUP BY 1"
```

## Evals: score xtra's extract output against the golden dataset ([`docs/qrspi/evals`](docs/qrspi/evals/03-spec.md))

**The flow:** an expert's ✓ (or ✗ with the right text) makes a value **human-reviewed** at once, in any column; an
engineer's ✓ waits for an expert's **Confirm**. **Approving** a column's rule **publishes** it into `ruleset-vN`, then
the server **scores** xtra's latest extract output against it. Every score has two results: **Human-reviewed** (only
the values an expert checked: small, trusted) and **Rule-matched** (every value the rules found: large, as good as the
rules). The **Evals** tab charts them per extract output, with each value's diff; the home page's Catalogs table has
the latest score of every catalog.

The Studio doesn't run xtra: engineers run `xtra catalog extract`, and the Studio reads what it wrote
(`$GOLDEN_DATASETS_XTRA_SOURCE/<catalog>/<crawl>/records/`, else the shared `xtra-cli-output` container) and scores it
with xtra's own scorer, called in-process (xtra-cli is a path dependency on `../xtra-cli`). Each score is kept in
`<crawl>/golden-dataset-studio/scores/sc-NNNN/` (`score.json`, `values.parquet`) with two results: the version's
golden tree (human-reviewed) and its silver tree (rule-matched), each exactly what `xtra score extraction match --baseline-uri
<golden root>/catalogs/<catalog>/versions/ruleset-vN/<tree>` gives (`score.json` holds both commands). The first time the Studio sees an extract output it copies it into
`extract-outputs/<report last modified>/`, so it stays scorable after xtra overwrites it.
Only the columns the extract output emits under the same path are scored: a property xtra doesn't extract yet is
listed in `not_scored`, and each result's `xtra` keeps the scorer's own numbers over every column.

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
golden-datasets check -c avc   # keys, hashes, golden dataset files and each score's provenance
uv run --with playwright python bench/shots_review.py --base http://127.0.0.1:8000 --out docs/qrspi/screens   # spec screens
#   … --out docs/qrspi/evals/screens --only e   (the Evals spec's screens; run the server on a scratch copy of the roots)
uv run pytest -m azure tests/test_storage_contract.py   # the storage contract on Azurite + the Azure scratch prefix
```

Benchmarks for the performance budgets of spec §10 are in [`bench/`](bench/).
