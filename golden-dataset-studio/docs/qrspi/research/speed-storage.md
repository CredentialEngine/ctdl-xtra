# Research: speed and storage (B4, B5, B6, W2, A7)

Date: 2026-10-26. Facts and measurements, then an options comparison and a recommendation (sections 5 and 6).
The scripts, raw listings and the local data copy are in
`/private/tmp/claude-501/-Users-eric--superset-worktrees-ctdl-xtra-glowing-conchoraptor-79248126/9a24ca32-87da-41f1-8d05-111d893d1142/scratchpad/speed/`
(`scripts/instrument.py`, `measure_api.py`, `browser.py`, `real_discovery.py`, `real_ttl.py`, `measure_click.py`,
`extract_phases.py`, `page_profile.py`, `to_parquet.py`, `duck_bench.py`, `duck_more.py`, `onefile.py`, `fix_proto.py`).
v2 was run from a copy (`speed/v2/`, unchanged source), never from the repo folder.

## 1. Summary

**v2 is slow because of storage round trips made one at a time, not because of JSON, Python or the browser.** The same
server against a local folder shows the WVU review in 0.8 s; against Azure it takes 48 s. Each Azure request costs about
37 ms, and v2 makes them serially: 1,039 sequential record GETs to open WVU, 139 sequential LIST calls to discover
catalogs, and (by design) that discovery runs again on **any** request that comes more than 5 s after the last one.

| What the user does (Azure) | Time | Same thing, local folder | Main cause |
|---|---|---|---|
| Open the landing page, real `xtra-cli-output` | **~27 s** (11.6 s discovery + 15.3 s summaries, read-only measurement) | 0.1 s | 139 serial LISTs + 74 `crawl.json` GETs; per-card LIST of `pages/` and full replay of `events.jsonl` |
| Open WVU (first time since server start) | **47.9 s** to first card | 0.8 s | 1,039 serial `records/*.json` GETs |
| Open CCSF (first time) | **9.3 s** | 0.1 s | 126 serial record GETs + review-file reads |
| Any click or page change after 5 s idle, real root | **+10.7 to 10.9 s** | +0 s | `CatalogIndex` 5 s TTL: every `/api/c/...` call re-runs discovery |
| An Accept click (no idle) | 0.3 s | <10 ms | 1 append + 3 whole-file PUTs (`decisions.json` is 619 KB) + an ETag update of the index |
| First open after a new `extract` | **199 s** (CCSF), **291 s** (WVU) | ~1 s | carry-over replays 662 / 835 decisions through `apply()`, 5 writes each |
| `extract` WVU | 76 to 86 s | 37 s | half quadratic `css_path` (CPU), half 11,242 record PUTs |

FCP is not a useful number here: it is 32 to 76 ms everywhere, because the first paint is the word "Loading…". The real
"first contentful" moment is the first card, which is the LCP above. The JS bundle is 176 KB (55 KB gzipped) and loads
in 8 to 13 ms. It is not a factor.

**On DuckDB + Parquet (B6):** it works with our credentials (connection-string secret, `az://`), and the format shrinks
WVU's 187.5 MB of record JSON to a 4.3 MB Parquet file. Queries take 3 to 22 ms on a local file and 160 to 700 ms
straight from blob. But most of the speed gain comes from writing **one file per extraction instead of 11,242**, which
a single gzipped JSONL file does nearly as well (2.3 s vs 1.6 s to fetch and decode everything from Azure). So Parquet
is not needed for speed. It does make the rule-centric questions (every value of rule X, compare two
extractions) one line of SQL. Two traps showed up: **globbing `az://` lists every blob under the prefix** (23 to 25 s),
and **DuckDB cannot write a `.duckdb` file in blob storage** (attach is always read-only).

## 2. B4: where first-load time goes

### 2.1 Setup

- Azure: a scratch copy of CCSF (`2026-10-01T16-02-34Z`, 1,042 page blobs, 2 extractions of 1,960 blobs each) and WVU
  (`2026-10-20T13-19-46Z`, 1,800 page blobs, 1 extraction of 11,246 blobs) plus `review-ui-index/`, under
  `xtra-cli-output/zz-scratch-review-ui-v3/` (section 7). Root:
  `azure://https://ceteststorage.blob.core.windows.net/xtra-cli-output/zz-scratch-review-ui-v3`.
  `REVIEW_UI_GOLDEN_ROOT` unset; `REVIEW_UI_CACHE_DIR` in the scratch dir, cleared before "cold" runs.
- Local: the same blobs downloaded into `speed/local/` (18,049 blobs in 39.7 s with 32 threads).
- Laptop to `ceteststorage`: **~37 ms per GET or HEAD** (median of 20 record GETs 39 ms, 10 HEADs 35 ms). LIST of
  `pages/` (1,800 blobs) 0.8 s; LIST of `records/` (11,242 blobs) 5.7 s.
- Storage calls were counted by wrapping `AzureBlobStore` / `LocalStore` methods (`instrument.py`). API latency was
  measured in-process with FastAPI's `TestClient` (`measure_api.py`), and the browser with headless Chromium through
  Python Playwright against a real `review-ui-v2 serve` (`browser.py`). Server CPU was profiled with cProfile.

### 2.2 Server startup and what `AppState` loads

- **Startup** (process start to `/healthz`): 2.1 s on Azure, 0.5 s local. `create_app` runs discovery once: 1.0 s on
  the 2-catalog scratch, **11.1 to 11.6 s on the real container** (measured read-only, `real_discovery.py`), because
  `AzureBlobStore.find_files("crawl.json", max_depth=4)` walks all ~60 catalog folders level by level: 139 LIST calls
  and 74 `crawl.json` GETs, all sequential.
- **`AppState` does not read every record.** It is built on the first `/api/c/<cid>/...` call. It reads `pages.jsonl`
  (the whole extraction's page index), replays the review's `events.jsonl`, and then `page_list()` calls
  `ExtractionView.page()` for every **sampled** page, which reads each record those pages reference **one at a time**
  (`views.py` `record()`). CCSF: 30 pages, 126 of 1,958 records. WVU: 21 pages, **1,039 of 11,242 records** (WVU's
  department pages list dozens of courses each). Without a sample it would read every record of the run.

### 2.3 Endpoint latency, payload and storage reads

Azure scratch, cold page cache. "n" is the number of storage calls.

| Call | CCSF | WVU | Local (CCSF / WVU) | Storage calls (Azure) |
|---|---|---|---|---|
| `GET /api/catalogs` (2 catalogs) | 4.3 to 5.6 s, 1 KB | same call | 39 ms / 42 ms | 2 LIST `pages/` (1.5 s), 6 GETs of review files (2.2 s, mostly `events.jsonl`), ~20 HEAD/GET/LIST. **Not cached**: every call repeats it. |
| same, real container (6 catalogs) | ~27 s (11.6 + 15.3) | | | 139 + 18 LISTs, 74 + 15 + 10 GETs, 12 + 12 HEADs |
| `GET /state` 1st (builds `AppState`) | **7.6 s**, 476 KB (32 KB gz) | **44.0 s**, 1.5 MB (69 KB gz) | 51 ms / 256 ms | CCSF 126 record GETs = 5.0 s; WVU **1,039 record GETs = 41.6 s**; plus `events.jsonl` 1.0 to 1.5 s |
| `GET /state` 2nd | 1.1 s | 1.15 s | 6 ms / 17 ms | Discovery refresh (TTL expired) + re-reads `report.json`, `rules.json`, lists review sessions with a HEAD each. Immutable files are never cached. |
| `GET /pages/<stem>` | 3 ms, 26 KB | 2 ms, 38 KB | 2 ms | none (records already in memory) |
| `GET /pages/<stem>/content` cold / warm | 293 / 78 ms, 17 KB | 128 / 79 ms, 13 KB | 16 / 5 ms | page HTML GET ~200 ms the first time (then disk cache); `rules.json` read **twice** per request (72 ms) |
| `POST /events` (one click) | | 312 ms | <10 ms | 1 APPEND + 3 PUTs (`decisions.json`, `notes.json`, `flags.json`) + 1 ETag read-modify-write of `review-ui-index/index.json` |
| same click after 6 s idle | | 1.08 to 1.17 s (scratch); ~11 s on the real root | | + full discovery |

Measured directly on the real root (`real_ttl.py`, read-only): `CatalogIndex.get()` after 6 s idle took **10.7 s and
10.9 s**. `S(cid)` in `api.py` calls it on every `/api/c/...` request, including `POST /events`. So on the real container,
a reviewer who pauses for more than 5 s waits about 11 s on the next click.

**`events.jsonl` is slow to read because it is an append blob.** WVU's 462 KB, 1,011-event log takes a median of
**1.77 s** to download. `decisions.json` (619 KB, a block blob) takes 0.23 s. The landing page reads it once per catalog,
and opening a review reads it again.

**Starting a review after a re-extract is the slowest path of all.** `ReviewSession.create` carries accepted decisions
forward by calling `apply()` once per decision. Each call appends, rewrites the three JSON views and updates the index.
Opening the catalog after my scratch re-extracts carried over 835 decisions on WVU (**291 s**) and 662 on CCSF (**199 s**).

### 2.4 Browser (headless Chromium, fresh server per row)

| | Azure scratch, cold server | Azure scratch, warm server | Local, cold server |
|---|---|---|---|
| Landing (first `.catalog-card`) | 4.9 s (real root: ~27 s, from 2.3) | 4.8 s | 0.11 s |
| CCSF (first `.card`) | **9.4 s** (`/state` 8.3 s) | 1.8 s | 0.10 s |
| WVU (first `.card`) | **47.9 s** (`/state` 46.4 s) | 0.8 s | 0.83 s |
| FCP (all rows) | 32 to 76 ms ("Loading…") | | |
| JS bundle | 55.6 KB transferred, 8 to 13 ms | | |

### 2.5 Server profile

cProfile of the WVU `/state` against the local folder: 0.35 s in total, of which 0.33 s is `views.page()` →
`views.record()` → opening 1,045 small files. JSON decoding is 50 ms, gzip 9 ms. **There is no CPU hot spot on the read
path.** Against Azure, the same call is 44 s of waiting on 1,039 sequential HTTPS round trips (the instrument counts above
account for 41.6 s of it).

### 2.6 How much the hot spots are worth (prototype, scratch copy only)

`fix_proto.py` monkeypatches two things: it prefetches the sampled pages' records with 64 threads, and it sets the
catalog TTL to 600 s.

| | Before | After |
|---|---|---|
| WVU `/state` 1st, Azure | 47.7 s | **4.2 s** |
| CCSF `/state` 1st, Azure | 7.9 s | **2.7 s** |
| `/state` after 6 s idle | 1.1 s (scratch), ~11 s (real root) | 0.5 s |

The remaining ~2 to 4 s are the append-blob `events.jsonl` read and immutable files read again on every call. Both
can be fixed without changing the format (section 5a).

## 3. B5: how long `extract` takes

`extract_phases.py` runs the real `review-ui-v2 extract` (8 worker processes, 18-core laptop) with timers around its
phases. Azure runs wrote new extractions into the scratch prefix.

| Run | Total | List pages + meta | Compute (read HTML, parse, rules) | Writes (records, pages.jsonl, labels) | Other |
|---|---|---|---|---|---|
| CCSF local | 2.5 s | 0.1 s | 1.7 s | 0.5 s | 0.2 s |
| CCSF Azure, cold page cache | 37.1 s | 2.2 s | 26.1 s (downloading 521 pages) | 7.1 s (1,956 PUTs) | 1.7 s |
| CCSF Azure, warm cache | 11.9 s | 0.8 s | 1.8 s | **7.6 s** | 1.7 s |
| WVU local | 37.3 s | 0.1 s | **32.2 s** | 3.9 s | 1.1 s |
| WVU Azure, cold cache | 86.3 s | 3.6 s | 37.2 s | **43.0 s** (11,242 PUTs) | 2.5 s |
| WVU Azure, warm cache | 76.3 s | 1.2 s | 31.9 s | **40.7 s** | 2.5 s |

**Compute is `css_path`, not HTML parsing.** One process over all 900 WVU pages: read 0.38 s, `split_page` (lxml)
0.89 s, BeautifulSoup parse 2.85 s, `run_page` in total 69.8 s. Under cProfile, `engine.css_path` accounts for
120 of 130 s (**~93%**). For every element on the way up to `#xtra-root`, it calls `parent.find_all(name,
recursive=False)` to find the element's position. That is quadratic on long sibling lists, and WVU's course list
has hundreds of `div`s in one parent. It runs for every entity root and every field (154,132 calls for a quarter of
the pages). Rule matching itself (soupsieve) is about 3 s.

**Would rerunning one rule help?** Not much for speed, once `css_path` is fixed. Every rule has to parse every page,
so parsing is the floor: about 4 s single-threaded for WVU, under 1 s on 8 processes. One rule's own evaluation is a
fraction of the 3 s of matching. What dominates on Azure is the **one-blob-per-record write**: 40 to 43 s for WVU. One
file per extraction (or per rule run) brings that to a single PUT (a 4.3 MB Parquet file uploads in about 1 s).
Rerunning one rule still matters for the data model and the UX (a rule version has its own output, which you compare
with the last one), just not for speed.

## 4. B6: DuckDB and Parquet

### 4.1 Conversion

`to_parquet.py` writes one row per extracted value: `catalog, run_id, extraction_id, ruleset_id, ruleset_version,
record_id, has_conflicts, canonical_label, ctdl_property, rule_id, rule_type, presence, value, raw_text, css_path,
char_start, char_end, source_url, page_stem, field_id` (zstd, at `<run>/extractions/<id>/values.parquet`, next to the crawl).

| Extraction | Record JSON | Rows | Parquet | Same rows as JSONL / JSONL.gz | As SQLite (indexed, not normalized) | As `.duckdb` |
|---|---|---|---|---|---|---|
| CCSF `2026-10-19T16-21-33Z` | 1,956 files, 42.5 MB | 47,451 | **1.03 MB** | | | |
| WVU `2026-10-21T14-25-24Z` | 11,242 files, 187.5 MB | 267,058 | **4.34 MB** | 228.6 MB / 5.95 MB | 164.3 MB | 17.3 MB |

Converting took 0.4 s (CCSF) and 2.5 s (WVU), almost all of it reading the JSON files. Writing Parquet took 0.03 to
0.17 s.

### 4.2 Queries (`duck_bench.py`, DuckDB 2.0.0, Python)

"First" uses a new connection (nothing cached); "repeat" is the median of 5 runs on the same connection.

| Query | Local file: first / repeat | `az://` scratch: first / repeat | Today's layout, for comparison |
|---|---|---|---|
| Q1: every value of rule `course-description` in WVU (21,813 rows, with `css_path`) | 22 / 13 ms | 713 / 159 ms | Azure: 11,242 GETs on 32 threads = **18.3 s**; local: ~2.4 s |
| Q2: one course (`ADV415`) across two WVU extractions (full join) | 9 / 3 ms | 703 / 288 ms | 2 GETs if you know the record id; impossible by course code without an index |
| Q3: every changed value between CCSF's two real extractions (full join on `field_id`) | 13 / 9 ms | 997 / 307 ms | read 2 × 1,956 files |
| Q4: glob `*/*/extractions/*/values.parquet`, fill rate per catalog, extraction and rule | 5 / 4 ms | **23.2 / 25.1 s** | not possible |
| Q4 with an explicit list of the 4 files (a manifest) | | **870 ms** | |
| Glob limited to one run, `catalog-wvu-edu/<run>/extractions/*/values.parquet` | | 13.8 s | |

Loading the `azure` extension and creating the secret takes about 1 s per connection. The secret is created from
`AZURE_STORAGE_CONNECTION_STRING` (`CREATE SECRET (TYPE azure, CONNECTION_STRING ...)`), so the same credential v2 uses
works.

The same rows as one file, fetched from Azure and decoded in Python (`onefile.py`): JSONL.gz takes 2.3 s, Parquet into
Python objects 1.6 s, Parquet into Arrow 1.2 s. Filtering all 267,058 rows by rule in memory takes 26 ms. **So "one file
per extraction" is what fixes reads. Parquet is about 30% faster on top of that, plus SQL.**

### 4.3 What does not work

- **Globbing over `az://` is slow and gets slower as the container grows.** Blob storage has no folders, so DuckDB
  lists every blob under the part of the path before the first `*`. Even inside one run, `extractions/*/` lists all the
  `records/` blobs. (The scratch prefix had 44,470 blobs at that point.) The real container is far bigger. The same glob
  takes 4 ms on a local folder. "Query across crawl folders by path" therefore works locally but needs a **manifest**
  (a list of files, e.g. in the index) on Azure, or the Parquet files kept under a prefix with nothing else in it.
- **DuckDB cannot write a database file in blob storage.** `ATTACH 'az://.../test.duckdb'` works for reading (2.6 s for
  the first query on a 17 MB file). It is **read-only even when attached without `READ_ONLY`**: the `INSERT` fails with
  "attached in read-only mode". `COPY ... TO 'az://...parquet'` does work (344 ms), so DuckDB can write new immutable
  files to blob but cannot change a database there.

### 4.4 DuckDB-WASM in the browser

It works, but it is not worth it for v3. `@duckdb/duckdb-wasm` 1.33 ships a 36 MB WebAssembly module (8.1 MB gzipped),
compared with today's whole 55 KB bundle. That adds seconds to the first load of every new browser session. Reading blob
directly from the browser would also need a SAS token in the page and CORS on the storage account (or the server
proxying range requests). The server-side DuckDB already answers in 3 to 25 ms from a local file, so the browser gains
nothing it needs. It might be worth revisiting later for free-form exploration.

## 5. Options

**(a) Keep JSON, fix the hot spots.** Ordered by payoff:

1. Stop rediscovering on every request: a long TTL or explicit refresh for `CatalogIndex`, and discovery from the index
   (a list of runs) instead of walking the container. Worth 11 s per idle click and ~11 s of startup on the real root.
2. Landing page: cache the summaries, take review counts from `review-ui-index/index.json` (already maintained), and
   stop listing `pages/` just to count it (`crawl.json` / `state.json` can say). ~27 s → well under 1 s.
3. Treat extraction outputs as immutable and keep them in memory/disk cache (they never change under one id): no re-reads
   of `report.json` / `rules.json` per call.
4. Replace the per-record files with one file per extraction (`values.jsonl.gz` or Parquet). Reading records in
   parallel gets WVU to 4.2 s; one 6 MB file gets it to ~2 s cold, then milliseconds.
5. Make carry-over a batch: one bulk append, then write the views once (currently 199 to 291 s).
6. Stop rewriting `decisions.json` / `notes.json` / `flags.json` on every click (derive in memory; snapshot occasionally).
   Read the append-blob log incrementally (remember the offset, fetch only new bytes) or compact it periodically.
7. Memoize `css_path` sibling positions (one pass per parent): extraction compute ~10× less on WVU.

Pros: smallest change. Every number in section 2 has a direct fix. Cons: the rule-centric questions (all values of a
rule, compare versions, across catalogs) still need custom Python per question. There is no query language for
Claude or Eric to explore with.

**(b) Immutable Parquet per extraction + append-only annotation log + DuckDB in the server.**
Each extraction (or rule run) writes one `values.parquet` once, next to its crawl. Annotations go to append-only JSONL
(append blobs: each event is one atomic append, so 2 to 3 annotators can write at once with no locking). The server
downloads each immutable Parquet file once into the existing disk cache (like pages) and queries it locally with
DuckDB. Annotations are read from the log and folded in memory, or read with `read_json`.

- Speed: same as (a) with step 4 for loading; queries take 3 to 25 ms locally, ~0.2 to 1 s straight from `az://`.
- Exploration: the rule-centric views are single SQL statements (Q1 to Q3), and Claude Code can run the same SQL from
  the CLI on the same files.
- Concurrency: good. Nothing is ever rewritten except the small index, which already uses ETags.
- Local vs Azure parity: the same SQL runs on a path or an `az://` URL. Globbing is the exception: it costs 4 ms
  locally and 14 to 25 s on Azure, so files are found through a manifest in the index, not a glob. With the cache, the
  server reads local disk in both modes.
- Cons: a new dependency (`duckdb` wheel, no service). Annotations stay JSONL, because Parquet cannot be appended to.
  Two formats.

**(c) One mutable DuckDB file in blob storage.** Measured: DuckDB cannot open a blob-hosted database for writing.
Every change would mean download, modify, upload the whole file (17 MB for one WVU extraction) under a lease or ETag,
so there is one writer at a time and every click costs a whole-file upload. Concurrent annotators would conflict or
queue. Local and Azure would behave differently (direct writes locally, download-upload on Azure). **Not recommended.**

**(d) Others.**
- **SQLite file:** the same blob problem as (c) (no in-place writes on blob), and 164 MB for WVU denormalized. Fine as a
  private local cache, not as shared storage.
- **DuckLake** (DuckDB's table format: Parquet in blob plus a catalog database): gives snapshots and multiple writers, but
  needs a catalog database (Postgres, or SQLite/DuckDB on a local disk). That is a service to run, which A8.4 keeps out
  of scope for now. Worth a look if v3 is deployed.
- **Azure Table Storage or Postgres for annotations:** credible later for concurrency at scale, but it is a deployment
  decision. 2 to 3 annotators do not need it, because append blobs already handle them.

## 6. Recommendation

1. **Do the hot-spot fixes regardless of format.** They are what makes the tool feel fast: discovery not on every
   request, landing-page counts from the index, immutable data cached, batched carry-over, no per-click view rewrites,
   memoized `css_path`. They take WVU's first open from 48 s to a few seconds, and an idle click from 11 s to under
   0.5 s.
2. **For v3's data model, choose (b): one immutable `values.parquet` per extraction or rule run (with the provenance
   columns of A7.3), an append-only JSONL annotation log, and DuckDB inside the server and CLI**, with a manifest in
   the index instead of globs on Azure. Measured against Eric's bar: on **performance** it is dramatic compared with
   today's layout (18 s → 0.16 s for "every value of rule X" over Azure, 40 s → 1 PUT for writes), but most of that comes
   from having one file, which a gzipped JSONL would also give. On **exploration** it is a real step up: comparing
   versions, slicing by rule and querying across catalogs become SQL that both the UI and Claude can run. If Eric wants
   the smallest possible change, (a) plus one `values.jsonl.gz` per extraction is the honest alternative. It has the
   same load speed and no SQL.
3. **Not (c)**, and not DuckDB-WASM.

## 7. What was created in Azure

Everything is under `xtra-cli-output/zz-scratch-review-ui-v3/`. Deleting that prefix undoes all of it. Nothing was
written anywhere else: a check after the work found 0 of the 18,049 real blobs under `review-ui-index/`,
`ccsf-curricunet-com-catalog/` and `catalog-wvu-edu/` modified today. `xtra-golden-sets-verified` was never touched.

- `zz-scratch-review-ui-v3/README.txt`: says it is a scratch area created by Claude Code on 2026-10-26 for
  review-ui-v3 research, and that deleting the prefix undoes everything.
- **Server-side copies (same relative layout), 18,049 blobs:** `review-ui-index/**` (9 blobs);
  `ccsf-curricunet-com-catalog/2026-10-01T16-02-34Z/**` (4,983); `catalog-wvu-edu/2026-10-20T13-19-46Z/**` (13,057).
- **Written by v2 while measuring (in the copies):**
  - new extractions: CCSF `extractions/2026-10-26T20-26-19Z/`, `extractions/2026-10-26T20-26-57Z/` (1,960 blobs each)
    and `discovery/` of the same ids; WVU `extractions/2026-10-26T20-27-09Z/`, `extractions/2026-10-26T20-28-35Z/`
    (11,246 blobs each) and `discovery/` of the same ids;
  - new review sessions (auto-created with carry-over when the new extractions were opened): CCSF
    `review-ui/2026-10-26T20-42-15Z/`, WVU `review-ui/2026-10-26T20-37-50Z/` (5 blobs each);
  - 3 test events (a general note `zz-speed-test` by `claude-speed-test`, set and then cleared) appended to the copied
    WVU review `review-ui/2026-10-22T16-05-24Z/`, and its views rewritten;
  - `review-ui-index/index.json` (the scratch copy) updated by those reviews.
- **Written by research scripts:** `values.parquet` in CCSF `extractions/2026-10-19T16-21-33Z/` and
  `extractions/2026-10-19T17-18-22Z/` and in WVU `extractions/2026-10-21T14-25-24Z/` and
  `extractions/2026-10-26T20-21-52Z/` (the last folder holds only that file; it comes from a local extract id);
  `values.jsonl.gz` in WVU `extractions/2026-10-21T14-25-24Z/`; `zz-duckdb-write-test/test.parquet` and
  `zz-duckdb-write-test/test.duckdb`.

At the end the prefix held 44,483 blobs. Local copies (not in Azure): `speed/local/` (a 708 MB copy of the same runs, plus
local extractions and Parquet files) and `speed/cache/` (the page cache). No servers are left running.
