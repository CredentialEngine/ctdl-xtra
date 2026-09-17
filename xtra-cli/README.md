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
  --with-playwright     -> src/implementations/crawl_browser.py
  --with-http           -> src/implementations/crawl_http.py
  --with-firecrawl      -> src/implementations/crawl_firecrawl.py
xtra catalog discover   -> src/xtra/catalog/discover.py
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

#### Which strategy to pick

Three backends fetch pages. Everything else about a crawl is identical
whichever one runs: the frontier, the scope rules, robots.txt, the retry
ladder, the pacing, the checkpoints, the log lines, and everything discovery
reads afterwards. A strategy only decides how one URL becomes one saved page.

| Flag | Renders JS | Cost | Pick it when |
| --- | --- | --- | --- |
| `--with-playwright` | yes | a browser per worker | You do not know yet. It works everywhere. |
| `--with-http` | no | none | The catalog is server-rendered. Far cheaper and it scales to real concurrency. |
| `--with-firecrawl` | yes | per page, to a third party | The site blocks the browser we drive, or we cannot run one. |

`--with-ai-agent` and `--with-third-party` stay registered and fail closed
with a message naming the three that work.

**Start with `--with-playwright`.** Then find out whether you need it: run
five pages each way into two run ids and compare.

```bash
xtra catalog crawl --with-playwright --url "$CATALOG" --run-id "$A" --limit 5 --target-uri "$TARGET"
xtra catalog crawl --with-http       --url "$CATALOG" --run-id "$B" --limit 5 --target-uri "$TARGET"
```

`crawl.json` records `strategy`, `pages_saved` and `total_bytes`, so the two
runs are directly comparable. If `total_bytes` is close, the browser is
buying nothing and `--with-http` is the better job. If the `--with-http` run
saved a fraction of the bytes, the catalog renders in the client and
Playwright is doing real work.

On the two catalogs tested here, `--with-http` captured the same content: the
same visible text to within a few characters and the same in-scope links,
with byte counts inside one percent. That will not hold for every catalog, so
measure rather than assume.

A browser is still the right default because the failure is silent. A page
that renders in the client returns HTTP 200 and a near-empty shell, so an
`--with-http` crawl of the wrong catalog looks like a success and produces
nothing to extract.

#### Firecrawl

```bash
export FIRECRAWL_API_KEY="fc-..."
xtra catalog crawl --with-firecrawl --url "$CATALOG" --target-uri "$TARGET" --limit 5
```

The key comes from `--firecrawl-api-key` or `FIRECRAWL_API_KEY` and is sent
in one header. It is never logged and never written to `crawl.json`.
`--firecrawl-api-url` points at a self-hosted instance.

Only the HTTP shape is implemented, with no SDK, so this adds no dependency.
Two things to know before reaching for it: every crawled URL goes to a third
party, and it renders the same page a browser would, so it does not reach
content that sits behind pagination or a button.

A rejected key is not retried. Six retries a page on a bad key would spend a
whole crawl's budget before anyone noticed, so only HTTP 429 and 5xx from the
service are waited out.

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

### Discover

```bash
xtra catalog discover \
  --catalog-id catalog-brookdalecc-edu \
  --run-id 2026-09-17T14:20:01Z \
  --source-uri "$TARGET" --target-uri "$TARGET" \
  --sample-size 30
```

Discovery reads **every** page the crawl saved, works out what each one is,
groups the pages that share a shape, names the shapes that are unusual, and
picks a sample that covers all of them. It fetches nothing and it samples
nothing while profiling: a special case that only appears on page 700 cannot
be found by looking at the first ten.

| Flag | Default | What it does |
| --- | --- | --- |
| `--catalog-id` | required | The catalog folder the crawl wrote. |
| `--run-id` | required | The crawl run to read. |
| `--sample-label` | `Course` | Which label the golden sample is drawn from. |
| `--sample-size` | `30` | How many pages the sample should reach. |

Text is normalized in memory with the same normalizer the extractors use.
No normalized file is written; only its SHA-256 is kept, which is what
identifies two copies of one page.

Every regex, keyword list, and threshold lives in one module,
`src/implementations/discover_rules.py`. When a page is labelled wrong the
fix is a rule there, plus a fixture in `tests/fixtures/html` that proves it.

#### What a page gets labelled

| Label | Fires when |
| --- | --- |
| `Course` | at least one course block, with the code in the title, the `h1`, or the first 300 visible characters; or two or more course blocks |
| `LearningOpportunity` | two or more different program terms, or a URL template containing `program`, `degree`, `certificate`, `major`, or `preview_program` |
| `Competency` | an outcomes, objectives, or competencies heading followed by two or more list items |

A course block is a course code with a credits, units, or hours value within
400 characters of it. A code on its own is a cross-reference; a code with a
value is the course being described.

`page_type` is the label when exactly one fired, `Multiple` when several did,
and `Unknown` when none did. `rules_fired` keeps the evidence for each.

#### Markers: the special cases a sample has to contain

`lecture_lab_credit_numbers`, `lab_clinical_field_study_hours`,
`printed_zero_hours`, `ceu`, `prerequisite`, `corequisite`,
`prerequisite_corequisite_combined`, `recommended`, `learning_outcomes`,
`program_markers`, `tabs_present`, `archived`, `catalog_year`,
`policy_or_definition_page`, `multi_course_page`, `empty_or_error_page`.

Each one is stored with a quote of up to 80 characters showing why it fired,
and `patterns.md` prints one line per marker on what it costs an extractor
that ignores it.

#### Patterns

A field label on more than 90 percent of pages is site chrome, and a label on
exactly one page cannot group anything. Both stay in `field-labels.csv` for
review and leave the signature.

```text
signature  = page_type + sorted remaining field labels + sorted marker names
pattern_id = first 8 hex characters of sha256(signature)
```

Headings never take part. A course title is written as a heading on most
catalogs, so including them would give every course its own pattern.

A pattern is **special** when any of these hold: it is under 5 percent of its
page type; it carries a field label found on under 5 percent of its page
type; it carries a marker found on under 20 percent of its page type; it is
empty or archived; or its catalog year differs from the run's most common
one. `patterns.md` lists the special ones first.

#### The golden sample

Coverage first, representation second.

1. **Coverage.** Until every feature is covered, take the page that covers the
   most uncovered features, each weighted by how rare it is in the
   population. A case that never appears in the sample is a case nobody
   checks.
2. **Representation.** Fill to `--sample-size` by pattern share, using the
   largest remainder method, so the sample still looks like the catalog.

The population is the pages carrying `--sample-label`, minus duplicates and
empty or error pages. Every tie is broken by the SHA-256 of the URL, so the
same pages and the same code always give the same sample. If coverage alone
needs more than `--sample-size` pages they are all kept, and the features that
forced the extra pages are listed. If the population is smaller than
`--sample-size` the whole of it is taken and the report says so.

#### What it writes

```text
{catalog-folder}/{run-id}/discovery/{discovery-run-id}/
  summary.json                 counts, unknown share, git commit, version
  pages.jsonl                  one profile per page
  labels.json                  the preprocessed list extraction reads
  field-labels.csv             vocabulary, rarest first, then headings
  patterns.json                every pattern as data
  patterns.md                  the demo document, special patterns first
  golden-sample-course.json    the sample, with a reason per page
```

The discovery run id is the UTC start time. A discovery run is never
overwritten, so two runs sit side by side and a rule change can be compared
against what it replaced.

### Extract and transform

Same `--with-<strategy>` pattern:

```bash
xtra catalog extract --with-template \
  --source-uri "$TARGET" --target-uri "$TARGET" \
  --catalog-id catalog-brookdalecc-edu --run-id 2026-09-17T14:20:01Z

xtra catalog transform --with-ctdl \
  --source-uri "$TARGET" --target-uri "$TARGET" \
  --catalog-id catalog-brookdalecc-edu --run-id 2026-09-17T14:20:01Z
```

`--with-template` is the current deterministic CMS extractors (Clean Catalog,
Coursedog, Acalog). `--with-ctdl` maps printed labels to CTDL JSON-LD and
never writes a CTID. `--with-ai-agent` is reserved on both verbs.

Extract works from the list discovery produced rather than guessing which
saved pages are courses. It reads `labels.json` from the newest discovery run
of the crawl run, or from `--discovery-run-id` when you name one, and
processes the pages labelled `Course` that hold exactly one course block.

| Flag | What it does |
| --- | --- |
| `--discovery-run-id` | Read this discovery run instead of the newest. |
| `--only-golden-sample` | Extract only the pages in `golden-sample-course.json`, for review. |

A page that matches no known template, and a page holding several courses,
are skipped and recorded in `{catalog-folder}/{run-id}/extract-report.json`
with the reason. That file sits **beside** `records/` and never inside it,
because transform reads every JSON file under `records/` and would treat a
report as a course.

Pages are read by the stem discovery lists, which is the stem the crawler
saved them under. The `Slot.stem` property in `lib/` still slugs the URL the
old way, so it is never used for a storage key, and the record carries the
crawl stem instead.

## Object layout (not packs)

`--target-uri` is a ceops storage URI. Runs are keys under the catalog folder and the UTC timestamp:

```text
{target-uri}/{catalog-folder}/{yyyy-MM-ddTHH-mm-ssZ}/
  crawl.json
  state.json
  failed.jsonl
  pages/{stem}.html
  pages/{stem}.meta.json
  discovery/{discovery-run-id}/summary.json
  discovery/{discovery-run-id}/labels.json
  discovery/{discovery-run-id}/patterns.md
  discovery/{discovery-run-id}/golden-sample-course.json
  extract-report.json
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
- Decide what a page is with a model: discovery is rules in one file
