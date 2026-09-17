# xtra-cli

Command-line ETL for public college catalog pages used by Credential Engine xTRA.

The layout follows **ceops**: Click commands live at `src/xtra/<noun>/<verb>.py`, tests at `tests/xtra/<noun>/test_<verb>.py`, and reusable storage code lives in `src/common/`. There is no pack folder and no zip of a run. Each run is identified by an ISO8601 UTC timestamp `yyyy-MM-ddTHH:mm:ssZ`.

This CLI does not invent CTIDs and does not publish to the Credential Registry.

## Install

Python 3.10+. From this directory:

```bash
python3 -m pip install -e ".[dev]"
python3 -m playwright install chrome
```

Azure Blob (production or Azurite) needs the extra:

```bash
python3 -m pip install -e ".[dev,azure]"
```

Azurite (local Azure Blob emulator), same as ceops:

```bash
export AZURE_STORAGE_CONNECTION_STRING="UseDevelopmentStorage=true"
```

## Windows

PowerShell, from the repo root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".\xtra-cli[dev]"
python -m playwright install chromium

xtra --version
xtra environment set dev --data-uri .\xtra-cache
xtra catalog crawl --with-playwright --url https://catalog.brookdalecc.edu --limit 5 --min-interval-in-seconds 0
```

If activation is blocked, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`
first. In `cmd.exe` the activate line is `.\.venv\Scripts\activate.bat`.

Environment variables are set per shell:

```powershell
$env:AZURE_STORAGE_CONNECTION_STRING = "UseDevelopmentStorage=true"
$env:XTRA_ENV = "test"
$env:XTRA_CONFIG_DIR = "C:\ci\xtra-config"
$env:LOG_LEVEL = "DEBUG"
```

In `cmd.exe` use `set NAME=value`, and `setx NAME value` to persist across sessions.

One Windows difference to expect:

- **The config file is not permission protected.** `save_config` calls `chmod(0o600)`,
  which on Windows only toggles the read-only bit. `%USERPROFILE%\.xtra\config.json`
  holds no secret, only the name of the variable that does, but do not treat its
  permissions as equivalent to POSIX.

Local paths work in both forms: `.\xtra-cache`, `C:\xtra-cache`, or
`file:///C:/xtra-cache`.

## Environments

An xTRA environment names *where a run is written*: the storage container and the variable holding its secret. Same verbs as `ceops environment`:

```bash
xtra environment list
xtra environment set prod --data-uri azure://https://ACCOUNT.blob.core.windows.net/xtra
xtra environment show
```

`set` saves the active environment to `~/.xtra/config.json` (`XTRA_CONFIG_DIR` relocates it for CI and containers). Only the *name* of the secret variable is stored; the connection string itself never touches disk.

`dev` is the only environment with a built-in container (Azurite at `127.0.0.1:10000`). `test`, `sandbox`, and `prod` ship blank on purpose so nobody guesses a real account name; give each one a `--data-uri` once.

Once an environment is active, the ETL commands no longer need URIs:

```bash
export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=...;AccountKey=..."
xtra catalog crawl --with-playwright --url https://catalog.brookdalecc.edu --limit 5
```

To run one command elsewhere without changing the active environment, pass `--env` (or set `XTRA_ENV`):

```bash
xtra catalog crawl --with-playwright --env sandbox --url https://catalog.brookdalecc.edu --limit 5
XTRA_ENV=test xtra catalog extract --with-template --catalog-id brookdalecc --run-id 2026-09-14T18:12:00Z
```

Resolution order for every run, highest first:

| Source | Storage URI | Azure secret |
| --- | --- | --- |
| Command flag | `--target-uri` / `--source-uri` | `--azure-storage-connection-string` |
| `--env NAME` or `XTRA_ENV` | that environment's data URI | that environment's secret variable |
| Active environment | saved data URI | saved secret variable |

An explicit URI always wins, so `--target-uri ./xtra-cache` keeps working with no environment configured at all. When nothing resolves, the command fails with the exact `xtra environment set` line to run.

Per-environment secrets in one shell, without repeated exports:

```bash
xtra environment set prod \
  --data-uri azure://https://ACCOUNT.blob.core.windows.net/xtra \
  --connection-string-env CE_PROD_STORAGE
export CE_PROD_STORAGE="DefaultEndpointsProtocol=https;AccountName=...;AccountKey=..."
```

## Commands

Filesystem path matches invocation, the same way ceops does (`ceops elasticsearch graphs create` → `src/ceops/elasticsearch/graphs/create.py`):

```text
xtra environment set    -> src/xtra/environment.py
xtra catalog crawl      -> src/xtra/catalog/crawl.py
xtra catalog extract    -> src/xtra/catalog/extract.py
xtra catalog transform  -> src/xtra/catalog/transform.py
```

### Crawl

The crawler downloads and saves. It renders a page, writes the HTML and a
metadata sidecar, follows links, and stops when nothing in scope is left or
`--limit` is reached. It does not detect a CMS family, name an institution,
pick a template, or normalize text. Those are jobs for discovery and
extraction, which read what the crawler saved.

```bash
xtra catalog crawl --with-playwright \
  --url https://catalog.brookdalecc.edu \
  --target-uri azure://https://ACCOUNT.blob.core.windows.net/xtra-golden-sets \
  --limit 40 \
  --concurrency-limit 1 \
  --min-interval-in-seconds 180 \
  --max-interval-in-seconds 3600
```

| Flag | Default | What it does |
| --- | --- | --- |
| `--url` | required | The catalog URL the crawl starts from. |
| `--run-id` | now | UTC run id, `yyyy-MM-ddTHH:mm:ssZ` or `yyyy-MM-ddTHH-mm-ssZ`. Reuse one to resume. |
| `--limit` | none | Stop after this many pages are saved in the run, across resumes. |
| `--concurrency-limit` | `1` | Pages downloaded in parallel. Each worker runs its own browser. |
| `--min-interval-in-seconds` | `180` | Smallest gap between one worker's GETs, and the first retry wait. |
| `--max-interval-in-seconds` | `3600` | Cap on the exponential backoff between retries. |
| `--max-retries` | `5` | Retries after the first attempt, for network errors, timeouts, HTTP 429, and HTTP 5xx. |
| `--scope-prefix` | directory of `--url` | Keep only URLs whose path starts with this URL's path. |
| `--include-regex` | none | Repeatable. A followed URL is kept only when it matches one of these. |
| `--exclude-regex` | none | Repeatable. A followed URL is dropped when it matches one of these. |
| `--seed-urls-file` | none | Extra start URLs, one per line, for pages no link reaches. |

A crawl is a rare, one-time job, so the defaults are slow on purpose: one
page every three minutes, one worker. Getting it wrong means doing it again.

`--with-ai-agent` and `--with-third-party` are reserved strategy flags. They
fail closed with a clear message until those backends exist.

#### What stays in scope

A URL is kept only when **all** of these hold:

- the scheme is `http` or `https`
- the host is the host of `--url`
- the path starts with the `--scope-prefix` path. Without that flag the
  prefix is the directory of `--url`, so
  `https://catalog.example.edu/courses/index.html` crawls
  `https://catalog.example.edu/courses/` and nothing above it
- it matches at least one `--include-regex`, when any are given
- it matches no `--exclude-regex`
- `robots.txt` allows it for user-agent `*`
- the extension is not one a browser would download rather than render:
  `pdf doc docx xls xlsx ppt pptx zip jpg jpeg png gif svg webp ico css js
  xml mp3 mp4`

`http` and `https` are the same site for both scope and duplicate detection.
Two URLs are the same page when the lowercased host, the path, and the query
match; the fragment is dropped. The URL a redirect actually lands on is
remembered too, so a redirect chain is not walked twice.

Links come from the `href` of `a`, `area`, and `link rel=next` in the
rendered HTML.

A response that is not `text/html` or `application/xhtml+xml`, and a
navigation that starts a download, are skipped with reason `non_html`. A
redirect that lands off the site is skipped with reason
`redirect_out_of_scope`.

The frontier starts from `--url`, every line of `--seed-urls-file`, and the
same-host URLs in `/sitemap.xml` and in any `Sitemap:` line of `robots.txt`.
Sitemap index files and `.gz` sitemaps are followed. `robots.txt` is fetched
with `urllib` and the shared browser user agent; a 4xx means the site
published no rules, and a 5xx or a network error means the same plus a
warning. `robots_status` is recorded in `crawl.json`. When `robots.txt` sets
`Crawl-delay` for `*`, the effective minimum interval is the larger of that
and `--min-interval-in-seconds`.

The two start URLs an operator types, `--url` and the lines of
`--seed-urls-file`, are exempt from `--include-regex` and `--exclude-regex`:
those flags narrow what the crawl *follows*, and a start URL that failed its
own filter would leave nothing to start from. They still have to be the same
host, inside the scope prefix, and allowed by `robots.txt`.

#### Catalogs that keep several years

Some hosts publish every catalog year on one site. That is an operator
decision, not something the crawler guesses, so narrow the run with a regex:

```bash
xtra catalog crawl --with-playwright \
  --url https://catalog.bergen.edu/content.php?catoid=13&navoid=664 \
  --include-regex "catoid=13" \
  --target-uri ./xtra-cache
```

#### What the log says

One INFO line per event:

```text
GET https://catalog.example.edu/english/engl101 -> 200 48213 bytes 1840 ms -> azure://https://ACCOUNT.blob.core.windows.net/xtra-golden-sets/catalog-example-edu/2026-09-17T14-20-01Z/pages/catalog-example-edu-english-engl101-300f5d79ef.html
RETRY https://catalog.example.edu/english/engl102 attempt 2 of 6 after HTTP 429, waiting 360 s
FAIL https://catalog.example.edu/english/engl103 after 6 attempts: HTTP 503
SKIP https://catalog.example.edu/private/x reason=robots
FROM-STORAGE https://catalog.example.edu/english/engl101 (already saved, no GET)
PROGRESS saved=120 failed=2 skipped=340 frontier=880 elapsed=06:01:10 eta=44:00:00
```

`bytes` is the size of the saved HTML in UTF-8. `latency_ms` runs from
navigation start to the HTML being in hand. The path is the full URI of the
saved object. `PROGRESS` is logged every 25 saved pages, and `eta` is
`frontier x effective minimum interval / --concurrency-limit`.

Skips that are ordinary scope decisions (`out_of_scope`, `duplicate`,
`extension`, `include_rule`, `exclude_rule`, `scheme`) log at DEBUG, because
on a real catalog they outnumber the GET lines many times over. The
surprises (`robots`, `non_html`, `redirect_out_of_scope`) stay at INFO. Set
`LOG_LEVEL=DEBUG` to see every decision.

`crawl.json` is printed to stdout when the run ends.

#### Resume

Rerun with the same `--url` and the same `--run-id`. `state.json` carries
the frontier, the seen set, and the failed URLs; `state.json`, `failed.jsonl`
and `crawl.json` are rewritten every 25 saved pages, on Ctrl+C, when the run
gives up, and at the end.

A frontier URL whose `.html` is already in storage is not fetched again: its
HTML is read back and its links are still followed, so a resume re-checks
coverage without touching the site. Failed URLs whose error was retryable are
queued once more. `--limit` counts pages saved across the whole run, so
rerunning with a higher limit continues where the last one stopped.

After 20 URLs fail in a row the run stops, checkpoints, and reports
`incomplete`, on the assumption that the site is blocking it.

#### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | `status` is `complete` or `limit_reached`, and no page failed |
| `1` | pages failed, or the run ended `incomplete`; one line on stderr says which |
| `130` | Ctrl+C. The checkpoint is written, so the same `--run-id` resumes |

### Extract and transform

Same `--with-<strategy>` pattern:

```bash
xtra catalog extract --with-template \
  --source-uri "$TARGET" --target-uri "$TARGET" \
  --catalog-id brookdalecc --run-id 2026-09-14T18:12:00Z

xtra catalog transform --with-ctdl \
  --source-uri "$TARGET" --target-uri "$TARGET" \
  --catalog-id brookdalecc --run-id 2026-09-14T18:12:00Z
```

`--with-template` is the current deterministic CMS extractors (Clean Catalog, Coursedog, Acalog). `--with-ctdl` maps printed labels to CTDL JSON-LD and never writes a CTID. `--with-ai-agent` is reserved on both verbs.

## Object layout (not packs)

`--target-uri` is a ceops storage URI. Runs are keys under the catalog folder and the UTC timestamp:

```text
{target-uri}/{catalog-folder}/{yyyy-MM-ddTHH-mm-ssZ}/
  crawl.json
  state.json
  failed.jsonl
  pages/{stem}.html
  pages/{stem}.meta.json
  records/{record-id}.json
  jsonld/{record-id}.json
  expected/{record-id}.json
```

The catalog folder is `--url` with every run of non-alphanumeric characters
turned into one hyphen, so a crawl is recognisable from the storage path
alone: `https://catalog.atlanticcape.edu/` becomes `catalog-atlanticcape-edu`.
Downstream commands take that folder name as `--catalog-id`.

The run folder is the run id with hyphens instead of colons, the same on
every operating system, so a Windows machine and a Linux machine write the
same keys. JSON keeps the colon form in `run_id`.

The page file name is the same hyphen conversion of the deduplicated URL, cut
to 80 characters, plus the first 10 hex characters of its SHA-256. That keeps
a Windows path under 260 characters and keeps two long URLs apart when the
readable part truncates to the same text.

URI schemes, copied from ceops:

```text
azure://https://account.blob.core.windows.net/container/prefix
azure://http://127.0.0.1:10000/devstoreaccount1/container/prefix   # Azurite
file:///absolute/path
./relative-path
```

Pass `--azure-storage-connection-string` or set `AZURE_STORAGE_CONNECTION_STRING`. Production reads and writes Azure Blob containers. Tests use `file://` plus mocked Blob clients; set the connection string to `UseDevelopmentStorage=true` to exercise Azurite (`pytest -m integration`).



## Tests

```bash
cd xtra-cli
python3 -m pytest tests -q
```

Network is not required. Playwright harvest is monkeypatched. Azurite tests are marked `integration` and skip unless `AZURE_STORAGE_CONNECTION_STRING` is set.

## Non-goals

- Invent `expected` values, CTIDs, or `human_signed`
- Publish to the Credential Registry
- LLM classification or extraction (the `--with-ai-agent` flags are stubs)
- Zip or pack a catalog run
- Normalize, classify, or template-match inside the crawler
