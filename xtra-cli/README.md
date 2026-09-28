# xtra-cli

Command-line ETL for public college catalog pages used by Credential Engine xTRA.

The layout follows **ceops**: Click commands live at `src/xtra/<noun>/<verb>.py`, tests at `tests/xtra/<noun>/test_<verb>.py`, and reusable storage code lives in `src/common/`. There is no pack folder and no zip of a run. Each run is identified by an ISO8601 UTC timestamp `yyyy-MM-ddTHH:mm:ssZ`.

This CLI does not invent CTIDs and does not publish to the Credential Registry.

> **Architecture and ETL pipeline:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) —
> how the five stages (crawl → discover → extract → transform → score) fit together,
> with flow charts, the storage layout, the data contracts between stages, and what
> lives in `src/common/` versus `lib/`. Read that first if you are new to the repo;
> this README is the operator's reference for the flags.

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

`--with-crawl4ai` is a separate extra, kept out of the default install
because it pulls a large dependency tree:

```bash
python3 -m pip install -e ".[crawl4ai]"
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

`set` saves the active environment to `~/.xtra/config.json` (`XTRA_CONFIG_DIR` relocates it for CI and containers). Only the *name* of the secret variable is stored; the connection string itself never touches disk. Running `set` again for the environment that is already active keeps its saved `--data-uri` and `--connection-string-env` unless you pass new ones.

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
  --with-crawl4ai       -> src/implementations/crawl_crawl4ai.py
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

| Flag | Key needed | Install | Pick it when |
| --- | --- | --- | --- |
| `--with-playwright` | no | included | The default. A browser we drive ourselves, with nothing between us and the page. |
| `--with-crawl4ai` | no | optional extra | A site blocks the plain browser, or the pages need clicking through before the HTML is worth taking. |
| `--with-firecrawl` | yes | included | Neither of the above can run, or the site needs a residential exit. Costs money per page. |

`--with-ai-agent` and `--with-third-party` stay registered and fail closed
with a message naming the three that work.

**Start with `--with-playwright`.** It is the default because it has the
fewest moving parts and no dependency beyond the browser. Reach for another
only when it fails, and say so in the run notes when you do.

`crawl.json` records `strategy`, `pages_saved` and `total_bytes`, so two
small runs into two run ids settle any argument about which one is getting
more of a given catalog. It also records `strategy_version`, read from the
installed packages rather than written down anywhere, `strategy_settings`,
what the backend was handed, and `strategy_notes`, the places where a
backend honours one of those settings only approximately. Every saved page
carries its `strategy` in the sidecar, so one page can be traced back to the
backend that fetched it.

```bash
xtra catalog crawl --with-playwright --url "$CATALOG" --run-id "$A" --limit 5 --target-uri "$TARGET"
xtra catalog crawl --with-crawl4ai   --url "$CATALOG" --run-id "$B" --limit 5 --target-uri "$TARGET"
```

On the catalog tested here the two agreed to within half a percent of bytes,
which is the expected result when a site is not fighting back. The difference
only shows up when one is.

#### Crawl4AI

An open-source crawler, Apache 2.0, no key and no bill. It drives a browser
the way the playwright strategy does, but brings stealth handling and hooks
for running JavaScript on the page before the HTML is taken. That last part
is the reason it is here: a catalog that hides its course list behind a Next
button cannot be reached by fetching alone, and no amount of better rendering
changes that.

```bash
python -m pip install -e ".[crawl4ai]"
xtra catalog crawl --with-crawl4ai --url "$CATALOG" --target-uri "$TARGET" --limit 5
```

It is an optional extra on purpose. The package pulls about 75 dependencies,
among them LLM clients, scientific computing libraries, and a second
Playwright fork. None of that belongs in a default install of a deterministic
ETL tool, and nothing in this repository calls a model. Installing the extra
is a deliberate act; the import is deferred until a crawl actually asks for
the strategy, and a clear error names the install command if it is missing.

Its own cache is always bypassed. The crawl decides what it already has from
storage, and a cached hit would report a status and a latency that never
happened on this run.

#### Firecrawl

```bash
export FIRECRAWL_API_KEY="fc-..."
xtra catalog crawl --with-firecrawl --url "$CATALOG" --target-uri "$TARGET" --limit 5
```

The key comes from `--firecrawl-api-key` or `FIRECRAWL_API_KEY` and is sent
in one header. It is never logged and never written to `crawl.json`.
`--firecrawl-api-url` points at a self-hosted instance, which is the way to
use Firecrawl without a key at all.

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

The frontier starts from `--url`, then the same-host URLs in `/sitemap.xml`
and in any `Sitemap:` line of `robots.txt`, then every line of
`--seed-urls-file`, then the links found on the pages themselves in document
order. That order is recorded as `frontier_order` in `crawl.json`. The
sitemap is the site's own index of its content pages, so a limited run
reaches real content first and a full run ends up with the same pages either
way. A resume reorders what it reads back the same way, so sitemap URLs do
not wait behind a section the first pass queued.

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

Two warnings say out loud when a run is narrower than its name suggests. A
`FOLDER` line when the host that answers is not the host `--url` named: the
folder name is kept as typed, so the run id stays stable, and `crawl.json`
records `resolved_seed_url` and `catalog_folder_matches_resolved_host`. A
`SCOPE` line when `--url` has a path, because the crawl then covers that
section of the catalog and nothing above it.

Skips that are ordinary scope decisions (`out_of_scope`, `duplicate`,
`extension`, `include_rule`, `exclude_rule`, `scheme`) log at DEBUG, because
on a real catalog they outnumber the GET lines many times over. The
surprises (`robots`, `non_html`, `redirect_out_of_scope`) stay at INFO. Set
`LOG_LEVEL=DEBUG` to see every decision.

`crawl.json` is printed to stdout when the run ends.

#### Resume

Rerun with the same `--url` and the same `--run-id`. `state.json` carries
the frontier, the seen set, the failed URLs, and the strategy that fetched
them. `state.json`, `failed.jsonl` and `crawl.json` are written once at
startup before the first GET, again after the first saved page, then every
25 saved pages, on Ctrl+C, when the run gives up, and at the end. A run that
is killed outright still leaves a manifest saying what it was and that it
did not finish.

A resume may not change the backend: a rerun with a different
`--with-<strategy>` stops with an error naming both, because one run folder
must not mix rendered sources.

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
| `--stem` | none | Repeatable. Read only this saved page, by the stem the crawl wrote it under. |
| `--sample-label` | `Course` | Which label the golden sample is drawn from. |
| `--sample-size` | `30` | How many pages the sample should reach. |

`--stem` answers the one question the whole run cannot be read to answer
quickly: why is *this* page labelled that way. The same reports are written,
and `summary.json` carries `whole_run: false` and the stems asked for,
because every share, every rare marker and every special pattern in them is
then counted over those pages alone. A stem the run never saved is an error
rather than a report about nothing.

```bash
xtra catalog discover --catalog-id catalog-atlanticcape-edu   --run-id 2026-09-18T08:25:01Z --stem catalog-atlantic-edu-biology-21d07fde95
```

The stem is the `stem` field of the page's `.meta.json`, and `html_path`
there is the whole path to the page it describes.

Text is normalized in memory with the same normalizer the extractors use.
No normalized file is written; only its SHA-256 is kept, which is what
identifies two copies of one page.

Every regex, keyword list, threshold, and markup selector lives in one
module, `src/implementations/discover_rules.py`. When a page is labelled
wrong the fix is a rule there, plus a fixture in `tests/fixtures/html` that
proves it.

Two readings of each page use those rules. `discover_dom.py` parses the
markup as a tree with BeautifulSoup, over lxml where it is installed, and
reports what the publisher marked up: the page's own content with the
menus dropped, the elements that are course descriptions, the tables that
are requirement lists, and any machine-readable declaration of what the
page is. `discover_page.py` reads the flattened text for everything a
sentence says. Where the two overlap the markup is believed first, because
a page that marks its course descriptions up has said where they are; the
prose rules are what answer for the many catalogs that mark up nothing.

What only the tree can say:

| Signal | Where it comes from | What it settles |
| --- | --- | --- |
| Course description block | `courseblock`, `course-description`, `node--type-class`, and the like | This run of text describes one course, whether or not a credits value is printed anywhere near it |
| Requirement list | `sc_courselist`, `program-requirements`, `plangrid`, and any course table with an hours column | These course codes are references to courses described elsewhere, and the page printing them is a program |
| Course reference | `a.bubblelink.code`, `td.codecol` | A cross-listed course named inside a description is not a second course on the page |
| Declared type | JSON-LD `@type`, microdata `itemtype` | The publisher's own answer, in the one form on the page that was not written to be read as prose |
| CMS page type | `node--type-*`, `post-type-*` on the rendered node | Reported and used for grouping only. The taxonomy is the college's own, so `degree` on one site is a credential and on the next is the department that grants it |

#### What a page gets labelled

Four labels, one per entity `lib/mapping.py` can write CTDL for. They are
tried in this order, and the first three are exclusive: a page has one
subject, and only a competency list rides along with it.

| Label | CTDL class | Fires when |
| --- | --- | --- |
| `Course` | `ceterms:Course` | at least one course block, with the code in the title, the `h1`, or the heading lines of the page's own content; or one or more course descriptions the platform marked up, on a page that is not printing its own requirements; or two or more course blocks on such a page; or three or more course codes under a `/courses/` path |
| `Credential` | `ceterms:Credential` | the page's name names one award; or the page prints its own requirements and names the award beside its name, in a section heading, after "Degrees Conferred", or in its first paragraph; failing both, a program or award URL segment plus an award the page names, then the URL segment alone |
| `LearningOpportunity` | `ceterms:LearningProgram` | the page prints its own requirements and names no award (a minor, a pre-professional track, a non-credit program, a "Program (not a degree)"); or a program URL segment such as `/programs/…`, `/majors/…`, `/programs-by-program/…`, or `preview_program.php` and nothing else |
| `Competency` | `ceasn:Competency` | a lead-in that names or introduces learning outcomes ("Student Learning Outcomes", "Upon completion of this program students will be able to:") followed directly by two or more outcomes, in list items or as lines that open with an action verb or "An ability to" |

A course block is an element the platform marked up as a course
description, when the page marks any. Otherwise it is a course code with a
credits, units, or hours value within 400 characters of it: a code on its
own is a cross-reference; a code with a value is the course being
described. Codes inside a requirement list or a course-reference link are
never counted, however they are printed.

Before the tree reading, a whole catalog could be missed on the printed
form alone. A CourseLeaf graduate subject page numbers its courses with
five digits (`ASTR 50303`), which the course-code rule did not match, and
prints its credits inside the description rather than in a field; 104 of
the 303 course listings at the University of Arkansas held no course code
at all and none of them could be a `Course` page.

`Credential` and `LearningOpportunity` are the same page shape told apart by
one thing: whether the page names the award it leads to. The award is what
gets published, so a program page that names one is a credential page and a
program page that names none is a learning opportunity.

Both are read from the page's own content. Menus, sidebars, footers, the
site banner (`nav`, `aside`, `footer`, and their ARIA roles) and the
furniture a site names rather than marks up (breadcrumbs, skip links, nav
bars) are dropped first, and the text inside the page's main container is
used when it has one, because every page of a catalog links to "Degrees &
Certificates" and "Degree Requirements". The main container is `<main>` or
`role="main"`, or failing those the ids and classes the platforms use
instead (Coursedog's `id="main-content"`, Drupal's `region-content`).

The page's own name is its `h1` inside that container, or the first one
outside the menus, and never one from the menus: Coursedog prints the
college's name as the only `<h1>` on every page, inside the sidebar, which
named all 62 pages of one catalog after the college.

What is left has to show both of these:

- **It prints a program's requirements**: a requirement list the platform
  marked up, a credit total with its number (`Total Credits 60`), a
  requirements heading over a list of courses, a term-by-term plan, or a
  `Degrees Conferred:` line with an award after it. Prose that mentions
  "degree requirements" or "Fall semester" is not enough, and neither is
  any other table of course codes: a requirement list says what each of
  its courses is worth, and a transfer equivalency table is two columns of
  codes and nothing else.
- **Where it names the award**: its name (`Accounting (A.A.S.)`), the badge
  beside the name (Clean Catalog's `Associate in Science`), a section
  heading (CourseLeaf's `Requirements for B.S. in Chemical Engineering`),
  the `Degrees Conferred:` line, or its first paragraph (`This degree...`).
  A badge is a line that is nothing but an award; CourseLeaf prints its
  contacts in the same place, and `Ph.D. Program Director` or `504 J.B. Hunt
  Building` names no award of the program's.

A name that lists (`Degrees and Certificates`, `Graduate Certificates`),
states a rule (`Graduation Requirements`), or is only an award type
(`Associate in Applied Science`) names no credential, and neither does a
college's or school's own page unless it prints the requirements of one
named award, and only one — a school offering four degrees is nobody's
credential page.

A URL segment counts whole and with a page under it, or by its words when
it is a phrase and one of them is a section noun in the **plural**:
`programs-by-program` and `academic-programs` are sections holding many,
and `academic-english-language-program` is one programme's own folder with
its course pages underneath. `/honors-program` is not a program and
`/programs` is the list of them.

The first paragraph is the page's own prose, not the contact block a
bulletin opens with. A line naming a role *and* carrying a telephone
number or an email address is how to reach someone — "Dr. David Welky,
Chair, Department of History, Irby 105B, (501) 450-5624" — and reading it
as the first paragraph both described a minor with telephone numbers and
hid the sentence below it that said which award the page was about.

`Competency` rides along with any of the others: a program page that lists
what its students will be able to do is `Credential` and `Competency`, so
its `page_type` is `Multiple`. The outcomes are read from the page's own
lines, whatever element holds them, and they have to be about the learner:
a course titled "Psychotherapy Outcomes", a college's "Mission and
Objectives", a program's "objectives are to: provide...", admission
technical standards, and the ABET program educational objectives are not
competency lists.

`page_type` is the label when exactly one fired, `Multiple` when several did,
and `Unknown` when none did. `rules_fired` keeps the evidence for each.

#### Markers: the special cases a sample has to contain

`lecture_lab_credit_numbers`, `lab_clinical_field_study_hours`,
`printed_zero_hours`, `ceu`, `prerequisite`, `corequisite`,
`prerequisite_corequisite_combined`, `recommended`, `learning_outcomes`,
`program_markers`, `credential_award`, `course_requirement_list`,
`published_as`, `tabs_present`, `archived`, `catalog_year`,
`policy_or_definition_page`, `multi_course_page`, `empty_or_error_page`.

Each one is stored with a quote of up to 80 characters showing why it fired,
and `patterns.md` prints one line per marker on what it costs an extractor
that ignores it.

#### Named entities

Markers say what is *true* of a page. Entities say what it *names*. Six
kinds, written to `entities.csv` with a quote for each, and by value alone
into `pages.jsonl` and `labels.json`:

| kind | example | where it is read |
| --- | --- | --- |
| `AWARD` | `Associate in Applied Science` | the marked-up award field, a JSON-LD declaration, then the page's own content |
| `COURSE_CODE` | `ENGL 101` | course blocks first, then references in a requirement list, then the content |
| `CREDITS` | `3 credits` → `3`, `1-3 credits` → `1-3` | the marked-up credits field, then the content |
| `TERM` | `Fall 2026`, `First Semester`, `2026-2027` | term headings, seasons with a noun or a year, the catalog year |
| `ORG` | `Atlantic Cape Community College` | the site name, then names in the content |
| `OCCUPATION` | `Registered Nurse` | a career sentence, or a list under a career heading |

Nothing here is a model and nothing is downloaded. Every span is found by
the vocabulary in `discover_rules.py` that the labels already use, so an
entity a reviewer disagrees with is one line to find and one line to
change. A statistical recogniser would offer `ORG` and `DATE` and never
`AWARD` or `COURSE_CODE`, which are the two a credential catalog exists for.

Two rules keep the noise down. Entities are read from **the page's own
content**, because the menu says "Degrees & Certificates" on every page of a
catalog. And an occupation needs **two signals, never one**: a head noun
from the gazetteer *and* a sentence that introduces work ("prepares
students for careers as…") or a heading standing over a list of jobs. On
the head noun alone, "Nurse Education" is a nurse and every program
coordinator is an officer.

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
  entities.csv                 what each page names, by kind, with a quote
  patterns.json                every pattern as data
  patterns.md                  the demo document, special patterns first
  golden-sample-course.json    the sample, with a reason per page
```

The discovery run id is the UTC start time. A discovery run is never
overwritten, so two runs sit side by side and a rule change can be compared
against what it replaced.

`summary.json` carries a `crawl` block read from the run's `crawl.json`: the
strategy, the seed URL and the URL it resolved to, the effective minimum
interval, the crawl status, and how many pages it saved. `patterns.md`
repeats it at the top, under **Where these pages came from**. When
`crawl.json` is missing the fields are null and both files say so, because a
report that cannot name its crawl should not look as if it can.

Discovery exits non-zero when the golden sample is empty, after writing every
report, and names the label it looked for and the page types it found
instead. When the population is smaller than `--sample-size` it warns with
both numbers and takes the whole population.

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

`--with-template` is the deterministic reading: the CMS extractors (Clean
Catalog, Coursedog, Acalog) and, for what they do not match, the page's own
markup. `--with-ctdl` maps printed labels to CTDL JSON-LD and never writes a
CTID. `--with-ai-agent` is reserved on both verbs. No LLM reads a page at
either stage.

Extract works from the list discovery produced rather than guessing what a
saved page is. It reads `labels.json` from the newest discovery run of the
crawl run, or from `--discovery-run-id` when you name one, and processes
every page discovery gave an entity to.

| Label | Record | CTDL class |
| --- | --- | --- |
| `Course` | one course, when the page holds exactly one course block | `ceterms:Course` |
| `Credential` | the award the page grants | `ceterms:Credential` |
| `LearningOpportunity` | the programme of instruction | `ceterms:LearningProgram` |
| `Competency` | one competency per outcome the page lists | `ceasn:Competency` |

A page that is two of those is two records. Every program page at Atlantic
Cape prints both the credential and the list of what its students will be
able to do, and a single record has nowhere to put the second; the page's own
id belongs to what it is mainly about, and the other gets `{stem}--{entity}`.

#### Two readings, in order

A course page goes to the college templates in `lib/templates` first. They
are the verified path and they have fixtures behind them, so where one
matches it is the answer.

Everything else is read from the markup by
`src/implementations/extract_dom.py`, which is the same tree reading
discovery uses. Every catalog platform marks a field up, names its label and
names its value beside it — Drupal writes `field__label` and `field__item`,
Coursedog writes `field-label` and `field-value`, CourseLeaf prints a course
block whose title line carries the code, the name and the credits together,
and the rest of the web writes a definition list or a table row. Reading
those needs no rule per college, and it is the only way the three entities
beside `Course` are read at all: the templates are course templates, and a
credential page has no course block for them to find.

Each field records the element it came from, so a reviewer can go and look.
A page that prints too little to be a record — one field, which every page
has, because every page has a name — is skipped rather than written as an
empty record that looks extracted.

| Flag | What it does |
| --- | --- |
| `--discovery-run-id` | Read this discovery run instead of the newest. |
| `--only-golden-sample` | Extract only the pages in `golden-sample-course.json`, for review. |

A page holding several courses, a page holding several credentials, and a
page nothing could read are skipped and recorded in
`{catalog-folder}/{run-id}/extract-report.json` with the reason. That file
sits **beside** `records/` and never inside it, because transform reads every
JSON file under `records/` and would treat a report as a course.

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

The container URL the Azure portal shows, `https://account.blob.core.windows.net/container/prefix`, is read as the `azure://https://` form above.

Pass `--azure-storage-connection-string` or set `AZURE_STORAGE_CONNECTION_STRING`. Production reads and writes Azure Blob containers. Tests use `file://` plus mocked Blob clients; set the connection string to `UseDevelopmentStorage=true` to exercise Azurite (`pytest -m integration`).



## Tests

```bash
cd xtra-cli
python3 -m pytest tests -q
```

Network is not required. Playwright harvest is monkeypatched. Azurite tests are marked `integration` and skip unless `AZURE_STORAGE_CONNECTION_STRING` is set.

CI runs these checks, and fails when coverage of `src/` drops under 80 percent:

```bash
python3 -m pip install -e ".[dev,azure]"
ruff check .
ruff format . --check
pytest -m "not integration" --cov=src --cov-report=term-missing --cov-report=html --cov-fail-under=80
```

The report lands in `htmlcov/index.html`. Without the `azure` extra the Blob tests skip. The workflows are described in [`CI-CD.md`](../CI-CD.md#xtra-cli).

## Docker

```bash
docker build -t xtra-cli .
docker run --rm xtra-cli --version
docker run --rm -e AZURE_STORAGE_CONNECTION_STRING xtra-cli catalog crawl \
  --with-playwright --url https://catalog.brookdalecc.edu --limit 5 \
  --target-uri azure://https://ACCOUNT.blob.core.windows.net/xtra
```

The entrypoint is `xtra`. The image carries Chrome, Playwright's chromium, and the `azure` extra, but not `crawl4ai`. It runs as uid 1001 in `/data`, so a relative `--target-uri ./xtra-cache` lands in a volume mounted there. An environment saved with `xtra environment set` lives only as long as the container unless `/home/xtra/.xtra` is mounted, so prefer `--target-uri`.

The CLI is installed editable from the source tree on purpose: `lib/` is not a package, so a wheel cannot import the extractors. On arm64 build with `--build-arg PLAYWRIGHT_BROWSERS=chromium`, because Google ships Chrome for amd64 only.

## Non-goals

- Invent `expected` values, CTIDs, or `human_signed`
- Publish to the Credential Registry
- LLM classification or extraction (the `--with-ai-agent` flags are stubs)
- Zip or pack a catalog run
- Normalize, classify, or template-match inside the crawler
- Decide what a page is with a model: discovery is rules in one file
