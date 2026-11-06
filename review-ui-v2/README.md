# review-ui-v2: verify CTDL Course extraction rules (CCSF, AVC, ...)

The multi-catalog version of `../review-ui`: one app, a landing page to pick the
ruleset, and rulesets for **CCSF** (CurricUNET) and **AVC** (eLumen). A local tool for checking
that a **declarative ruleset** (CSS selectors, regexes, constants; no executable
code) finds and extracts the right CTDL `Course` values from crawled catalog pages.
The product owner (Jared) reviews the results and writes notes; those notes go back
to Claude Code, which writes a better ruleset. Repeat until every sampled value is
accepted.

It is a separate copy, so both UIs run at the same time: **AVC on port 8000, CCSF
on port 8001**. Runs on a laptop and is shared with Jared over ngrok. **It is not
deployed anywhere, and v1 does not touch Azure.** All files are read and written
under one local storage root (default `../crawls`), laid out like the buckets. Both
apps share `review-ui-index/index.json` there; its entries are keyed by crawl run
and review id, so they do not collide.

What is new compared with `../review-ui`: **Flag for review** (below), plus the
CurricUNET rules. The generic engine gained `map` (rewrite an extracted value, e.g.
`Noncredit` to `TRUE`), a ruleset-level `page_title`, and a configurable content
root (`runs.MAIN_ID`, here `content-body`).

## Setup

```sh
cd ctdl-xtra/review-ui-v2
uv venv --python 3.13 .venv && uv pip install -e ".[dev]"
(cd web && npm install && npm run build)
```

## Storing everything in Azure Blob Storage

`--root` (or the `REVIEW_UI_ROOT` environment variable) is where the crawls, extractions,
reviews and `review-ui-index/` live: a folder (the default, `../crawls`) or an Azure
container:

```sh
uv pip install -e ".[dev,azure]"          # the Azure SDK is an optional extra
export REVIEW_UI_ROOT="azure://https://<account>.blob.core.windows.net/<container>[/<prefix>]"
.venv/bin/review-ui-v2 extract --run ccsf
.venv/bin/review-ui-v2 serve
```

* **Credentials.** `AZURE_STORAGE_CONNECTION_STRING` if set; otherwise
  `DefaultAzureCredential` (a managed identity in Azure, `az login` on a laptop). Nothing
  secret is stored by the app. The role needed is *Storage Blob Data Contributor* on the
  container.
* **The layout is the same as on disk**, so a folder and a container can be copied to
  each other file for file (`azcopy sync`).
* **How it stays safe.** Review events are written with Append Blob (each click is one
  atomic append); the other files are replaced whole, so a reader never sees half a file;
  the shared `review-ui-index/index.json` is updated with an ETag check and retried, so
  concurrent writers cannot lose each other's entries.
* **Local development: Azurite**, the Azure storage emulator:
  `npx azurite --blobPort 10000 --skipApiVersionCheck`, then use
  `azure://http://127.0.0.1:10000/devstoreaccount1/<container>` (create the container
  first). The Azure tests (`test_store_contract.py`, `test_azure_store.py`,
  `test_azure_end_to_end.py`) run against it and are **skipped when it is not running**;
  CI should start Azurite so they run.
* **Page cache.** Reading from Azure caches each crawled page (and its metadata) in
  `~/.cache/review-ui` the first time it is read, gzipped, so a re-extract or reopening a
  page does not download it again. Only `<run>/pages/*.html` and `*.meta.json` are cached,
  because a crawl is never rewritten; reviews, rulesets, extractions and the index always
  go to storage. The folder is capped (least recently used pages are deleted first).
  A local folder root is never cached.

  ```sh
  review-ui-v2 cache warm --run avc      # download a whole run once, 16 files at a time
  review-ui-v2 cache status              # what is cached, and how much space it uses
  review-ui-v2 cache clear --run avc     # forget one run (or `clear --all`)
  review-ui-v2 extract --run avc --no-cache   # bypass the cache for one command
  ```

  `REVIEW_UI_CACHE_DIR` moves the folder, `REVIEW_UI_CACHE_MAX_GB` sets the cap (default
  10), and `REVIEW_UI_CACHE=0` turns it off. The cache only speeds up *reading* pages;
  an extraction also writes one small file per record, which is the slower part against Azure.
* **Not done yet** (see the deployment plan): there is no sign-in; run a single server
  replica, since each review's state is held in memory.

## The loop

```sh
RUN=ccsf                     # any unique part of the crawl run's path

# 1. Pick the review sample once (about 30 pages, mixed by page type).
.venv/bin/review-ui-v2 sample --run $RUN

# 2. Claude edits a draft of the ruleset (see ITERATE.md), then you publish it
.venv/bin/review-ui-v2 rules pull ccsf-curricunet-com-catalog --out draft.json
.venv/bin/review-ui-v2 check-rules --rules draft.json
.venv/bin/review-ui-v2 rules publish draft.json

# 3. Run the rules over EVERY page of the run. Prints fill rates and checks
#    regressions; exits non-zero if a value Jared already accepted has changed.
.venv/bin/review-ui-v2 extract --run $RUN

# 4. Review. Seth drives, Jared talks. Share it with:
.venv/bin/review-ui-v2 serve                  # http://127.0.0.1:8001: choose a ruleset
.venv/bin/review-ui-v2 serve --run $RUN       # ...or go straight to one catalog
ngrok http 8001 --basic-auth "jared:<password>"

# 5. Turn the review into input for the next iteration
.venv/bin/review-ui-v2 export-feedback --run $RUN
```

Then give `feedback.md` and `ITERATE.md` to Claude Code and go back to step 2.
Restarting `serve` resumes the latest review of the latest extraction;
`--new-review` starts a fresh one. A new review **carries over** every accepted
value whose normalized text did not change, and every **open flag**.

## Where rulesets live

Rulesets and the field template are stored **in the storage root, under `review-ui-index/`**
(a folder or an Azure container; see above), not in this project:

```
<root>/<catalog>/<catalog>/<run>/pages | extractions | discovery | review-ui   # crawls and outputs
<root>/review-ui-index/index.json
<root>/review-ui-index/rulesets/<catalog_folder>/rules.json   # one ruleset per catalog
<root>/review-ui-index/templates/course.properties.json       # the field template (Property names)
```

The app reads them from there, so a ruleset reaches a running or deployed app by being
written to the root, with no redeploy; the landing page notices within a few seconds.
A local `crawls/` folder that is downloaded from the bucket therefore includes
`review-ui-index/rulesets/` and `review-ui-index/templates/` (sync `review-ui-index/` like any
other folder, e.g. `azcopy sync`).

```sh
.venv/bin/review-ui-v2 rules list                            # what is published
.venv/bin/review-ui-v2 rules pull ccsf-curricunet-com-catalog --out draft.json
.venv/bin/review-ui-v2 check-rules --rules draft.json        # validate + run its examples
.venv/bin/review-ui-v2 extract --run ccsf --rules draft.json # try a draft before publishing
.venv/bin/review-ui-v2 rules publish draft.json              # version must be higher than the published one
.venv/bin/review-ui-v2 extract --run ccsf                    # now uses the published ruleset
.venv/bin/review-ui-v2 template publish templates/course.properties.json
```

`rules publish` validates the file against the published template, runs the rules'
examples, and refuses a version that is not higher than the published one (`--force`
overrides). `sample` and `extract` use the ruleset published for the run's catalog
unless `--rules <file>` gives a draft. **Rulesets live only in the storage root**: this
project has no `rulesets/` folder (the tests keep their own copies under
`server/tests/fixtures/rulesets/`), so the published file is the one source of truth.
Keep drafts under version control wherever you like and publish them from there. The
`templates/` folder here holds the generated field template; publish it with
`template publish`. The same `--root` / `REVIEW_UI_ROOT` applies to every command.

## Choosing a ruleset (the landing page)

`review-ui-v2 serve` with no `--run` opens a landing page listing every **crawl run
that has a ruleset** published in the root, whose `catalog_folder` matches the
run's catalog (several crawls of one catalog are listed newest first). Each card shows
the crawl (seed URL, date, pages), the ruleset (id, version, rule count), the latest
extraction (and a **"rules changed since extract"** warning when the ruleset's version
is newer than the one the extraction used), and the progress of its latest review
(accepted of total, rejected, flagged).

* **Start review / Continue review** opens that catalog. Opening it resumes its latest
  review of the current extraction, or starts one.
* A catalog that is **not ready** (no extraction yet, or no sample) says which command
  to run (`review-ui-v2 sample --run ...`, `review-ui-v2 extract --run ...`).
  An invalid ruleset is listed last with its error.
* `serve --run <run>` skips the landing page and opens that catalog (the run is
  offered even if it has no ruleset published in the root). `--extraction`, `--review` and
  `--new-review` apply to that catalog.
* **⇄ Change ruleset** in the review's top bar returns to the landing page without
  restarting the server. The page URL is `#<catalog id>/<page>`, so a link opens a
  catalog directly.
* Each catalog is served under its own URL space (`/api/c/<catalog id>/...`), so two
  browsers can review two catalogs at the same time and a click cannot land in the
  wrong review.

To make a new catalog appear: crawl it into the root, publish a ruleset with its
`catalog_folder` (`rules publish`, see "Ruleset configuration" below), then run
`sample` and `extract`.

**AVC shares its crawl run with `../review-ui`.** `review-ui-v2 extract` on it writes a
new extraction next to the first app's, and the first app picks the *newest*
extraction when it restarts (pin the one it is using with `--extraction <id>`).
The sample (`<run>/review-ui/sample.json`) is shared, so both apps review the same
30 pages, and accepted values carry over into the first v2 review because decisions
are keyed the same way.

## Ruleset configuration (what differs per platform)

Besides `label_rules` and `field_rules`, a ruleset carries the platform settings, so the
engine itself has no catalog-specific code:

* `content_root`: CSS selector for the element holding a page's own content (the site
  menu and footer outside it are ignored). CCSF `#content-body`, AVC `#mainContent`.
  Rules see it inside a `#xtra-root` wrapper, so `#content-body ...` selectors still work.
* `page_types`: `[{"type", "url_regex"}]`, first match wins, anything else is `info`.
  Used for sampling and the page list.
* `page_title`: `[{"url_regex"?, "selector", "regex"?, "transforms"?}]`, the first that
  yields text titles the page in the list (the HTML `<title>` is often useless).
* `sample`: `quotas` per page type; `strata` per type (a quota spent on pages whose
  html matches a `pattern`, so odd cases such as a credit range or an empty description
  are included; a stratum with no pattern takes the rest); `size_pattern` + `small_page`
  to prefer small pages; `spread` (a URL regex with one group) to spread picks, e.g.
  across program areas. `review-ui-v2 sample --size N` rescales the quotas.
* `pane_css`: extra CSS for the page pane, for platform quirks (eLumen hides its
  accordions behind a click).

`check-rules` validates all of it. A new platform therefore needs only a ruleset, plus a
crawl whose pages actually contain the content (a catalog crawled behind a bot
challenge, such as `catalog-ualr-edu` as crawled on 2026-09-27, has none to extract).

## Flag for review

When Jared cannot tell what a label or value should be and needs a subject matter
expert, he flags it instead of guessing.

* **Flag page** (above the cards) flags the whole page. **⚑ Flag** on any label or
  value card (or `F` with the card focused) flags that property. A page can have a
  page flag and any number of flagged properties. Each flag takes an optional note
  ("what are you unsure about?").
* **Red flags mark them everywhere:** a red ⚑ and red edge on the page in the left
  list (with the number of flagged properties on it), a red flag chip and note on
  the card, and "⚑ flagged N pages, M items" in the footer. **Flagged only** above
  the list shows just the flagged pages.
* A flag is **independent of accept/reject.** A flagged item stays undecided (it
  still counts as pending) until Jared accepts or rejects it; **Accept remaining**
  and **Accept all remaining on this page** skip flagged items on purpose.
* **Remove flag** (or flagging again with the form's button) clears it. Flags that
  are still open **carry into a new review**, so a question waiting on an expert is
  not lost when the rules change.
* **Download → ⚑ Flagged for review (.md)** is a short document of just the flags
  (page, property, record, what was extracted, the note) to forward to the experts.
  `feedback.md` has the same list in its own section, marked as not-a-rule-bug; the
  golden and labels downloads add `flagged` / `flag_note` to the affected items
  (`verification.page_flagged` for a page) without changing their review status.

Flags are saved like every other action (`events.jsonl`, then `flags.json`).

### The golden sample download

One record per course, in the extracted-value format. Each field has its `canonical_label`,
its **`ctdl_property`** (the rule's, else the "Term" for that property in the field
template, e.g. `ceterms:codedNotation`; a few properties, such as Learning Type, have
no term), `value`, `presence`, `rule_id`, `source_url` and a `review_status`:
`accepted`, `corrected` (Jared's value replaced the extracted one), `pending`, or
`added` (Jared supplied a value no rule found: `rule_id` is `null`, and the term comes
from the template). The mapping is applied when the file is downloaded, so values added
earlier get it too; download again to pick it up.

### Saving a golden dataset to storage

The **Save golden dataset** button (above the cards) saves the current page's verified values
and its source HTML into the **verified golden sets** storage, a container of its own (not the
crawl's folder). Point the app at it with `--golden-root` or `REVIEW_UI_GOLDEN_ROOT`:

```sh
export REVIEW_UI_GOLDEN_ROOT=azure://https://ceteststorage.blob.core.windows.net/xtra-golden-sets-verified
```

(Without it, golden sets are written into the crawl's own root.) Each page gets a folder named
like its source HTML file:

```
<golden root>/<catalog>/<crawl folder>/<page>/<page>.json    the verified values
<golden root>/<catalog>/<crawl folder>/<page>/<page>.html    the page's source HTML, as crawled
```

The container must already exist and your key or sign-in needs write access to it. There is
no index file: list the container to see what has been saved.

* **Only verified values are saved**: accepted ones, ones Jared corrected, and ones he
  added. Values still waiting for a decision (including those flagged for an expert),
  rejections with no correction, values accepted as absent, and values whose property has
  no CTDL term are left out. The message under the button says how many and why, so a page
  can be saved partway and saved again later; saving again replaces that page's folder
  contents.
* **Only three keys per value**: `ctdl_property`, `value`, `source_url`. A department page
  lists many courses, so values are grouped by record:
  `[{"fields": [{"ctdl_property": "ceterms:name", "value": "...", "source_url": "..."}, ...]}, ...]`.
* This is separate from the **Download** menu, which gives the fuller golden format
  (every field with its `review_status`, flags, and labels) as a file on your computer.

## In the UI

| Action | Key |
|---|---|
| next / previous value | `Tab` / `Shift-Tab` |
| accept the focused value | `A` |
| reject (reason chips, expected value, note) | `R` (or `E` to edit) |
| note | `C`: on this value, on the rule (all pages), or on the property (all pages) |
| flag for review | `F` |
| next page | `Enter` (`[` `]` also work) |

* **Recording as** Seth / Jared tags every decision, note and flag with its author.
* **Add missing property / label** is for something on the page that no rule found.
* **Notes** (top bar) holds general notes and lists every scoped note and flag.
* The header shows **Saved to disk** after every action. If it shows
  **NOT SAVED**, keep the window open and retry.

Pass bar: a value is correct if it matches after ignoring case and whitespace.

## What gets written (next to the crawl's `pages/`)

```
<run>/extractions/<ts>/rules.json | sample.json | pages.jsonl | report.json | records/<CODE>.json
<run>/discovery/<ts>/labels.json
<run>/review-ui/sample.json                          # the fixed sample
<run>/review-ui/<ts>/session.json | events.jsonl | decisions.json | notes.json | flags.json | feedback.md
<root>/review-ui-index/index.json                    # every review, with accepted/rejected/pending/flagged counts
```

`events.jsonl` is append-only and is the source of truth; the other files are
rewritten from it after every action.

## The AVC ruleset

`<root>/review-ui-index/rulesets/avc-elumenapp-com-catalog-2026-27-welcome/rules.json` (ported from the first
app, same 17 rules). eLumen: one course per page in `#mainContent` (`header.header h2`
title, `h3` code, `p.header-x-meta` units such as `3.0 Units`, `1.0 - 8.0 Units`,
`0.0 Units`), and program pages whose `.new-rule` rows become stub courses. Its
extraction of 118 real pages matches the first app's value for value.

## The CCSF ruleset

`<root>/review-ui-index/rulesets/ccsf-curricunet-com-catalog/rules.json`. CurricUNET specifics:

* A **course page is a department page** listing every course of one subject (up to
  about 30). Each course is a `div.course-summary-wrapper`, so field rules use
  `repeat: ".course-summary-wrapper"` and give one record per course.
* **Program pages** list requirement rows (`div.course-entry`); each becomes a stub
  course record, merged by course code with the full record from its department page.
* The code is everything before the ` - ` delimiter in the title row (subjects can
  contain a space: `P SC 11`, `PE A 60`). Credits come from `(3.0)` / `(1.0-3.0)`.
  **Is Non-Credit** is `TRUE` for `Noncredit` courses and absent otherwise, as the
  template asks.
* Content lives in `div#content-body`. Page titles come from the ruleset's
  `page_title` (department header / program `h2`); the HTML `<title>` is useless.
* The crawl is incomplete (`status: incomplete`): a few department pages are empty
  and produce nothing until they are recrawled.

Fields: Name, Coded Notation, External Identifier, Description, Credit Value /
Min / Max, Is Non-Credit, Subject Webpage (the department page), Learning Type,
Life Cycle Status Type, Language. The rule and record formats are otherwise those of
`../review-ui` (see its README).

## Running in a container (Podman or Docker)

The `Dockerfile` builds the web app and the server into one ~210 MB image that runs
`review-ui-v2 serve` as an unprivileged user on port 8001. Nothing is baked in: the storage
root, credentials and cache are all supplied when it runs, so the same image works locally
and on Azure (Container Apps, App Service for Containers, ...).

```sh
podman machine start                       # Podman Desktop's VM, if it is stopped
podman build --format docker -t review-ui-v2 .
```

If the build fails with `gcloud.auth.docker-helper ... reauthentication`, your
`~/.docker/config.json` has a `credHelpers` entry whose login expired. Either run
`gcloud auth login`, or build with an empty config just for that command:
`mkdir -p /tmp/emptycfg && echo '{}' > /tmp/emptycfg/config.json && DOCKER_CONFIG=/tmp/emptycfg REGISTRY_AUTH_FILE=/tmp/emptycfg/config.json podman build ...`.

**Against your Azure bucket** (the secret is passed through from your shell, not written down):

```sh
export AZURE_STORAGE_CONNECTION_STRING='...'      # as for the CLI; never commit it
podman run --rm -p 8001:8001 \
  -e AZURE_STORAGE_CONNECTION_STRING \
  -e REVIEW_UI_ROOT=azure://https://ceteststorage.blob.core.windows.net/xtra-cli-output \
  -v review-ui-cache:/cache \
  review-ui-v2
```

**Against a local folder** (e.g. your downloaded `crawls/`). The container user is uid 10001;
`keep-id` makes the files it writes belong to you:

```sh
podman run --rm -p 8001:8001 --userns=keep-id:uid=10001,gid=10001 \
  -v "$PWD/../crawls:/data" review-ui-v2
```

**With a local Azure emulator**: `podman compose up --build` starts Azurite and the app
(`compose.yaml`). The emulator must run with `--blobHost 0.0.0.0 --disableProductStyleUrl`
(already set there); the storage container is created automatically for emulator addresses.
From a container, the host's emulator is `azure://http://host.containers.internal:10000/devstoreaccount1/<container>`.
Seed it with `podman compose run --rm app template publish /app/templates/course.properties.json`
and `rules publish`, then `extract`.

Any CLI command works the same way: `podman run --rm -e ... review-ui-v2 extract --run <run>`.

| Setting (environment) | Default in the image |
|---|---|
| `REVIEW_UI_ROOT` | `/data` (a folder or an `azure://` root) |
| `REVIEW_UI_GOLDEN_ROOT` | unset (golden sets go to the crawl root) |
| `REVIEW_UI_HOST` / `REVIEW_UI_PORT` (or `PORT`) | `0.0.0.0` / `8001` |
| `REVIEW_UI_CACHE_DIR` | `/cache` (mount a volume to keep it between runs) |
| `REVIEW_UI_CACHE_MAX_GB`, `REVIEW_UI_CACHE=0` | 10 GB, on |

`/healthz` answers `{"status":"ok"}` without touching storage, and the image has a
`HEALTHCHECK` using it. The app has no login of its own: put it behind your platform's
authentication (or ngrok basic auth) before exposing it, and give it a managed identity with
the *Storage Blob Data Contributor* role instead of a connection string when it runs in Azure.

## Not yet done (deliberately)

* **Prerequisite, Corequisite and Co-Prerequisite** (`ceterms:prerequisite` etc., a ConditionProfile in CTDL) are in the field template but are left out of the rulesets for
  now and will be addressed in a later iteration. Requisites are a separate element
  on CCSF pages, so they are simply not extracted.
* Hours, grading, transfer and repeatability are not template properties and are skipped.

## Development

```sh
.venv/bin/pytest --cov=review_ui     # Python
.venv/bin/ruff check server
(cd web && npm test && npm run typecheck)
```

`npm run dev` in `web/` serves the UI with hot reload and proxies `/api` to a
running `review-ui-v2 serve` (port 8001).
