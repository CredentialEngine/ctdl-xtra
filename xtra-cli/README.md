# xtra-cli

Command-line ETL for public college catalog pages used by Credential Engine xTRA.

The same commands produce a working extract and a freeze-backed pack that can later be copied into a reviewed reference folder. That copy is a destination directory after human review, not a second pipeline or a second codebase.

This CLI does not invent CTIDs and does not publish to the Credential Registry.

## Requirements

- Python 3.9 or later
- Playwright Chrome (for crawl and download)
- Optional: `xtra_accuracy` on `PYTHONPATH` (for `course score`)
- Optional: Credential Registry API key (for exact `ceterms:subjectWebpage` lookup)

Run commands from the repository root that contains the `xtra-cli/` directory.

## Install

```bash
python3 -m pip install -r xtra-cli/lib/requirements.txt
python3 -m playwright install chrome
```

Optional Registry lookup:

```bash
export REGISTRY_API_KEY='...'
```

Without a key, registry status stays `not_checked`.

## Layout

```text
xtra-cli/
  xtra_cli.py                 entry point (Unix and Windows)
  bin/xtra-cli                bash wrapper (Unix)
  bin/xtra-cli.cmd            cmd wrapper (Windows)
  crawling/crawl.py           catalog crawl
  downloading/download.py     page download
  extraction/extract.py       course extract
  extraction/classify.py      page classify
  extraction/run.py           pipeline run
  transformation/transform.py course transform
  scoring/score.py            course score
  scoring/check.py            pack check
  scoring/promote.py          pack promote
  lib/                        shared engine, schema, templates
  tests/                      fixtures and command tests
```

Classification is not a separate top-level stage. CMS family detection runs during `catalog crawl`. Template detection runs during `course extract`. `page classify` is an extraction subcommand that stamps `template_id` on cached pages.

## Entry point

Canonical invocation:

```bash
python3 xtra-cli/xtra_cli.py <noun> <verb> [options]
```

Windows (cmd):

```bat
python xtra-cli\xtra_cli.py <noun> <verb> [options]
```

`bin/xtra-cli` is a bash wrapper. On Windows use `python xtra-cli\xtra_cli.py` or `xtra-cli\bin\xtra-cli.cmd`.

Stage scripts are also runnable directly. `--url` must be a live catalog home or course page (the host must resolve in DNS):

```bash
python3 xtra-cli/crawling/crawl.py --pack my_pack --url https://catalog.brookdalecc.edu --limit 5
```

Commands use noun-verb form (`<noun> [<noun>] <verb>`). Verb-only names remain as hidden aliases.

## Commands

| Command | Alias | Writes | Description |
|---|---|---|---|
| `catalog crawl` | `crawl` | `slots.json` | Discover course URLs. Does not download HTML. |
| `page download` | `download` | `cache/{yyyy-mm-dd}/*.html` | Freeze HTML. `--normalize` also writes `normalized/*.txt`. Dated copies are never overwritten. |
| `page classify` | `classify` | stamps `template_id` | Unknown layouts are dropped. No LLM fallback. |
| `course extract` | `extract` | `records/*.json` | Transcribe printed fields. Always `verification.status = candidate`. |
| `course transform` | `transform` | `jsonld/`, `courses/` | Map labels to CTDL JSON-LD and scoring JSON. No CTIDs. Does not publish. |
| `course score` | `score` | scorer stdout | Wraps `xtra-accuracy`. Pass the pack (or a class folder such as `courses/` inside it). `--golden` is a deprecated alias for `--reference`. |
| `pack check` | `check` | `CHECK.json` | Freeze and schema gates. Does not sign records. |
| `pack promote` | `promote` | copies `courses/*.json` | Copy scoring JSON into a folder you name. Still unsigned. |
| `pipeline run` | `run` | a new pack | One-shot crawl through transform. Refuses a nonempty destination directory. |
| `field union` | `union-fields` | label counts | Count inventory labels across catalogs or packs. |

`--pack` is a directory name under `XTRA_HOME` (default `xtra-cli/out/`) or an absolute path.

`pipeline run` creates a new pack. Re-running with `--out` pointing at an existing nonempty folder exits 2. Stage commands that take `--pack` do not have that gate.

## Examples

Staged extract:

```bash
python3 xtra-cli/xtra_cli.py catalog crawl --pack my_pack --url https://catalog.brookdalecc.edu --limit 5
python3 xtra-cli/xtra_cli.py page download --pack my_pack --normalize
python3 xtra-cli/xtra_cli.py course extract --pack my_pack
python3 xtra-cli/xtra_cli.py course transform --pack my_pack
python3 xtra-cli/xtra_cli.py pack check --pack my_pack
```

One-shot pack:

```bash
python3 xtra-cli/xtra_cli.py pipeline run --url https://catalog.brookdalecc.edu --out my_pack
```

Score extractor dumps against a pack (requires `xtra_accuracy` on `PYTHONPATH`):

```bash
python3 xtra-cli/xtra_cli.py course score --reference my_pack --candidate dumps
```

Windows (cmd):

```bat
python xtra-cli\xtra_cli.py page download --pack my_pack --normalize
xtra-cli\bin\xtra-cli.cmd pack check --pack my_pack
set PYTHONPATH=C:\path\to\xTRA-Scoring
python xtra-cli\xtra_cli.py course score --reference my_pack --candidate dumps
```

If both `PYTHONPATH` and this repository's `src/` contain `xtra_accuracy`, `PYTHONPATH` wins. The in-repo `src/` path is a fallback only.

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `XTRA_HOME` | `xtra-cli/out/` | Directory where relative pack names are created |
| `XTRA_PACK` | set by `--pack` / `--out` | Active pack directory |
| `XTRA_MODE` | `college` | Validation mode |
| `XTRA_SLOTS` | `dynamic` | Load course URLs from the pack `slots.json` |
| `XTRA_PILE` | pack folder name | Scoring pile label |
| `XTRA_CACHE_URL` | unset | Optional blob upload after a successful local freeze |
| `REGISTRY_API_KEY` | unset | Exact-URL Credential Registry lookup |

Deprecated `GOLDEN_SET_*` names (`GOLDEN_SET_HOME`, `GOLDEN_SET_PACK`, `GOLDEN_SET_MODE`, `GOLDEN_SET_SLOTS`, `GOLDEN_SET_PILE`, `GOLDEN_SET_CACHE_URL`) still work and print a stderr warning.

## Pack contents

A pack is a directory. Typical files after `pipeline run` or a full staged run:

| Path | Source | Contents |
|---|---|---|
| `slots.json` | crawl | Course URLs in this pack |
| `cache/<yyyy-mm-dd>/<stem>.html` | download | Frozen page HTML (immutable dated cache) |
| `cache/<yyyy-mm-dd>/<stem>.meta.json` | download | Retrieval time, HTTP status, SHA-256 |
| `normalized/<stem>.txt` | download `--normalize` | Visible text with scripts and styles stripped |
| `records/<id>.json` | extract | Candidate record, evidence, CTDL map |
| `courses/<id>.json` | transform | Scoring JSON (`id`, `catalogue_type`, `source_url`, `expected`) |
| `jsonld/` | transform | CTDL JSON-LD (no invented CTIDs) |
| `CHECK.json` | check / pipeline | `"ok": true` only if freeze and schema checks passed |
| `PACK.md` | pipeline | Pack notes and the scoring command |
| `MANIFEST.json` | transform | Pack index; status remains `candidate` |
| `record.schema.json` | copied into the pack | Record schema |
| `FIELD_INVENTORY.csv` | copied into the pack | Allowed field labels |

`CHECK.json.ok == true` means the pack is freeze-backed and schema-valid. Records remain candidates. The CLI never writes `human_signed`.

## Review and promotion

There is one extract pipeline. After independent dual review of freeze HTML and JSON side by side, copy scoring files into a reference folder:

```bash
python3 xtra-cli/xtra_cli.py pack promote --pack my_pack --to golden_sets/courses
```

`pack promote` copies files. It does not set `human_signed`. Quote official accuracy only with `--signed-only` against a signed pack.

Review checklist: `lib/HUMAN_REVIEW.md`. Classification rules: `lib/CLASSIFICATION.md`.

## Catalog families

Deterministic extractors, one module per supported CMS family:

- `lib/templates/clean_catalog.py`
- `lib/templates/coursedog.py`
- `lib/templates/acalog.py`

Unknown CMS families fail closed. College name is not a classification signal. There is no LLM fallback.

Supported field copies are only values printed on the frozen page (for example course id, name, description, credits or min/max, prerequisites, hours, department). The extractor does not invent credit type or fill missing fields.

## Tests

```bash
python3 -m pytest xtra-cli/tests -q
```

Fixtures live in `tests/fixtures/html/` (Clean Catalog course page and catalog home) and `tests/fixtures/pdf/sample-placeholder.pdf`. Command tests reuse cached HTML and do not hit the network.

## Non-goals

- Invent `expected` values, CTIDs, or `human_signed`
- Publish to the Credential Registry
- LLM classification or extraction
- Overwrite an existing nonempty pack with `pipeline run`
- Quote official accuracy without `--signed-only` on a signed pack
