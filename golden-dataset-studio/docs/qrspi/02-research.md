# R — Research

Phase 2 of QRSPI for **review-ui-v3**. Facts found by reading the code, running v2, and measuring against real
data, both in Azure and in a local copy. Each topic answers the matching items in [`01-questions.md`](01-questions.md)
(Part B, the **R-…** notes, and the Part D assumptions). This file is the summary. Evidence, commands and numbers are
in the detail files:

| File | What's in it |
|---|---|
| [`research/data-model.md`](research/data-model.md) | v2 extraction shape, provenance, rule kinds, course-code uniqueness, Jared's existing reviews, `feedback.md` |
| [`research/speed-storage.md`](research/speed-storage.md) | where load time goes, `extract` timing, DuckDB/Parquet benchmarks, storage options |
| [`research/rendering.md`](research/rendering.md) + `research/img/` | the CSS hypotheses tested on all five catalogs, JavaScript, assets, the v1 mockup's page browser |
| [`research/design-notes.md`](research/design-notes.md) | versioning pros/cons, uncertainty signals, the Claude loop's sequence diagram |
| [`02a-walkthrough-v2-loop.md`](02a-walkthrough-v2-loop.md) + `walkthrough/` | Eric's requested blog post: the full v2 loop with 17 screenshots |

- Researched: 2026-10-26
- Nothing in the real Azure data was changed. See "What research created" at the end.
- *Inferred* marks things concluded rather than checked.

---

## 1. Headline findings

1. **The slowness comes from storage reads made one at a time, not from JSON.** Each Azure request costs ~37 ms, and
   v2 makes them one after another:
   - **Opening WVU:** 1,039 record reads, 47.9 s (0.8 s from a local folder).
   - **Landing page:** walks the container, ~27 s.
   - **Every click after 5 s idle:** reruns that discovery, +10.8 s.
   - **First open after a new extract:** 199–291 s, because carry-over writes one decision at a time.

   A prototype fix took WVU from 48 s to 4 s. [speed §1–2]
2. **Parquet + DuckDB is a big step up for *exploring* the data. For *speed* it's only modestly better than one
   gzipped JSONL per extraction.** Most of the gain comes from writing one file per extraction instead of 11,242. "Every
   value of rule X" from Azure: 18 s today, 0.16–0.7 s from one Parquet file. A mutable `.duckdb` file in blob storage
   **doesn't work** (DuckDB opens it read-only). [speed §4–6]
3. **CSS: the cause differs by catalog, and Seth's hypothesis (only `<body>` is kept) is not it.**
   - **AVC:** its theme is a `<style>` *inside `<body>`*, which v2 drops. That's a fourth cause nobody predicted.
   - **UALR:** Claude's ancestor hypothesis. `content_root` is a `<td>`, and the browser throws it away inside the
     wrapper `div`. This also breaks UALR highlighting: 4 of 23 paths resolve.
   - **CCSF, Marshall, WVU:** the course content is styled correctly. Only the site chrome is missing.

   [rendering §1–3]
4. **The saved HTML already contains what JavaScript built**, because xtra-cli saves each page with Playwright after it
   loads. With scripts removed, the full saved page matched the live site on all five catalogs. Running scripts again
   made it **worse** (UALR widgets duplicated, WVU tabs hidden). [rendering §3.2]
5. **Provenance mostly exists already.** Every value has `rule_id`, raw text, `css_path` and character offsets. It's
   lost in `merge.py` (record position, "rule found nothing") and in Save golden dataset (3 keys). Paths are relative
   to the `#xtra-root` fragment, not the page. [data-model B1]
6. **The record locator is already a separate rule in practice.** All field rules in a ruleset carry the same
   `repeat` copy (checked in all five), so pulling it out doesn't change any output. [data-model B10]
7. **Course code as the key:**
   - **AVC, CCSF, UALR:** works perfectly.
   - **Marshall, WVU:** ~190 records where one code covers different entries, plus 21 entities with no code.
   - **WVU:** lists 88% of courses on 2+ course pages.

   [data-model D3]
8. **Jared's ~2,000 past field verdicts map exactly to (code, rule_id)**, 100% in every session. They can be imported
   so his past work counts in the version comparison. He records corrections as *reject + a separate "missing" with
   the right value*, not as an expected value. [data-model D6]
9. **Only 3 of the 7 required fields come from page content:** External Identifier, Name, Description. The other four
   are constants or the page URL. Coded Notation and External Identifier read **the same element**. The review work
   is smaller than it looks. [data-model D1]
10. **v2's loop works, but the important parts happen outside the UI.** The export is hidden. Claude gets too little
    page context. There's no ruleset history or diff. One fix changed 117 values, of which 1 was in the sample.
    Regressions are counts only. [walkthrough, Friction]

---

## 2. Findings by topic

### 2.1 Rules: kinds, versions, dependencies (B2, B10, B11, R-rule-kinds, R-versioning)

**Rule kinds, in plain language** (Eric asked, A1.1):

- **Page rules** decide *which pages contain courses*. Today these are the `label_rules`: a URL pattern plus "page
  has / doesn't have element X". `page_types` is only used for display and sampling. It decides nothing and can
  disagree with the label rules (CCSF: 123 vs 118).
- **Record locator rules** decide *where each course starts and ends on a page*. Today it's the `repeat` (+
  `repeat_filter`) copied into every field rule, for example "each `div.courseblock` is one course". With no
  `repeat`, the whole page is one course (AVC, UALR course pages).
- **Field rules** decide *where property X is inside one course*: a selector, an optional regex, transforms, `map`.
  Some are constants (`Active`, `English`) or the page URL.
- **Merging** is not a rule. `merge.py` groups every occurrence across the catalog by the course code.

**Dependencies.** A field rule needs its page rule (`applies_to`), its locator, and the code rule (to key the value to
a course). *Inferred:* rerunning one field rule means running page rule + locator + code rule + that rule. That's
cheap, but every page still has to be parsed (see 2.3).

**Versions.** v2's ruleset `version` doesn't identify content: AVC has two different `rules.json` files both labelled
v1. Rules are self-contained JSON objects, so a content hash per rule is easy. But a rule's *behaviour* also depends
on `content_root`, its page rule, its locator and the code rule. The chosen model is "version both" (A1.3), argued in
[`design-notes.md`](research/design-notes.md#r-versioning-versioning-single-rules-vs-whole-rulesets):
- immutable rule versions;
- immutable ruleset versions that list them;
- publishing always creates a ruleset version (D11);
- a page-rule or locator change reruns every field rule beneath it.

### 2.2 Records and keys (B3, D3, D9, D6)

- Two levels exist: an **occurrence** (one course block on one page) and a **record** (all occurrences with the same
  normalized code). v2 keys decisions by `record_id` (= normalized code) + field + page, with an occurrence suffix
  that is ambiguous when a code repeats on a page.
- **D3's assumption holds, with the numbers to back it.** Users see the code. Underneath, annotations attach to the
  *occurrence* (page + locator position) and also store the code, so they re-attach by code when locators change. On
  AVC, CCSF and UALR, code-only keying would also work. On Marshall and WVU it would wrongly merge ~190 records.
- **D9 ("is it better?" after a locator change):** compare by code. The cases that can't be matched (uncoded, or the
  same code twice on one page with different names) are few, can be counted, and get listed separately.
- **D6:** import Jared's verdicts. Accepted/rejected map 1:1 to (code, rule_id). "Missing" maps to the property's rule
  for that page's label. Reject + missing pairs join into one "wrong, expected value = …" annotation. Accepts on
  constants (Learning Type, Language, …) are a large share of the count but say little, so v3 can treat constant rules
  as approved by default. Most "missing" items are Credit Unit Type / Prerequisites, which v3 drops (D1).

### 2.3 Speed (B4, B5)

| What the user does | Azure today | Local folder | Cause → fix |
|---|---|---|---|
| Landing page | ~27 s | 0.1 s | 139 sequential LISTs + summaries → read from an index, cache |
| Open WVU | 47.9 s | 0.8 s | 1,039 sequential record GETs → one file per extraction (or parallel reads: 4.2 s) |
| Click after 5 s idle | +10.8 s | 0 | discovery runs again on every request → long TTL / explicit refresh |
| Accept | 0.3 s | <10 ms | 1 append + 3 whole-file PUTs → append only, derive views in memory |
| First open after extract | 199–291 s | ~1 s | carry-over writes decisions one at a time → batch |
| `extract` WVU | 76–86 s | 37 s | half quadratic `css_path` (CPU) + 11,242 PUTs → memoize, one output file |

The JS bundle (55 KB gzipped) and FCP (the "Loading…" text, 32–76 ms) aren't factors. The real metric is time to the
first value card. **Rerunning one rule isn't much faster than rerunning the ruleset:** parsing pages dominates, not
evaluating rules. *Inferred:* after the fixes, a full WVU rerun should take ~10–15 s locally, so "rerun one rule" can
just be "rerun the ruleset, reuse unchanged rules' output". It's a correctness feature, not a speed one.

### 2.4 Storage options (B6, A7.2): pros and cons

| Option | Speed | Exploration | 2–3 annotators | Local ↔ Azure parity | Verdict |
|---|---|---|---|---|---|
| (a) Keep JSON, fix hot spots, one `values.jsonl.gz` per extraction | Good | Custom Python per question | Good (append blobs) | Same | Smallest change |
| **(b) One immutable `values.parquet` per extraction + append-only annotation JSONL + DuckDB in server and CLI** | Good (0.16–0.7 s on Azure, ms from cache) | **SQL for every rule-centric question, from the UI and from Claude** | Good (append blobs) | Same SQL on a path or `az://`. Find files through a manifest, not a glob (globbing Azure takes 23–25 s) | **Recommended** |
| (c) One mutable `.duckdb` file in blob storage | Each write uploads the whole file | SQL | Bad: one writer at a time | Different on Azure (download/upload) | Ruled out (DuckDB can't write to blob) |
| (d) SQLite file / DuckLake / Postgres | — | — | — | DuckLake and Postgres need a service | Not now (deployment is out of scope) |

On Eric's bar ("only if it dramatically increases performance and the ability to explore"):
- **Performance:** dramatic compared with today, but (a) gets nearly the same.
- **Exploration:** dramatic. Comparing versions is a join on (occurrence key, rule_id) across two Parquet files.
  Uncertainty signals are queries. Claude can run the same SQL from the CLI.

**Recommendation: (b).** The hot-spot fixes are needed either way.

### 2.5 Page rendering (B7–B9, A3.4, A6, D5, D7)

- **Render the whole saved page, not the fragment.** Remove scripts and inline handlers. Keep every stylesheet and
  `<style>` *wherever it is*. Show it in an iframe sandboxed with `allow-same-origin` only, served from our own URL
  (not `srcdoc`), with CSP `script-src 'none'`. Lay it out at desktop width and scale it to fit (as the v1 mockup
  does).
- **Highlighting:** map v2's `#xtra-root` path prefix onto `content_root` in the full page. CCSF, Marshall and UALR
  then resolve 100%. Better: v3 extraction records paths **from the document root**.
- **Highlight-to-annotate (D5) works:** the parent page reads the selection inside the same-origin iframe and stores
  `css_path` + character offsets + the quoted text with some context. Tested with page scripts blocked.
- **Assets (D7):** no crawl saved any CSS/JS/fonts/images, but every stylesheet still loads today. A v3 **`assets
  fetch`** step (no xtra-cli change):
  - reads the saved pages and follows `@import`/`url()`;
  - skips trackers;
  - stores each file once by content hash;
  - and the server then serves them itself (which also fixes the cross-origin font problem).

  Measured: 40–880 unique URLs per catalog, under 10 MB each, ~40 MB for CCSF (mostly fonts).
- **JavaScript (A6.3):** there's no reason to rerun scripts, since the saved HTML is already the rendered DOM. Fallback
  ladder for the rare JS-dependent content:
  1. per-catalog CSS that reveals hidden content (already done with `pane_css`);
  2. link to the crawled page that holds content loaded on click;
  3. a stored screenshot / HTML tree view / live link.

  "Fetch the JS as part of the crawl for the archive" can be part of `assets fetch` (store it, never run it).
- **For Eric/Jared:** some fonts (Font Awesome Pro, fonts.net) are licensed to the institution. Is storing copies OK?
  If not, fall back to loading those from the live site.

### 2.6 The v1 look (I2)

The mockup feels clean because the page sits in a **browser-like frame**:
- a tab per source document;
- a closable tab for a CTDL term definition;
- a Page | HTML switch;
- the site at its own desktop width, scaled;
- highlights as coloured text with numbered badges.

v2 shows a bare fragment with a margin. v3 should reuse the mockup's frame for the right-hand pane. Screenshots:
`research/img/mockup-*.png`, `v2-page-pane.png`.

### 2.7 The Claude loop today (B14, walkthrough)

- `feedback.md` has: header, notes, flags, problems grouped by rule (with the rule's properties and a ≤500-char HTML
  excerpt per item), and regressions. **None has ever been written in Azure.** It was only used locally.
- `ITERATE.md` covers pull → edit → check → extract → report. It doesn't mention publishing results, comparing
  versions, or running one rule.
- Walkthrough friction that v3 must address:
  1. the export is hidden (no copy-prompt button);
  2. Claude lacks surrounding page context and page paths, and had to write throwaway scripts;
  3. publishing overwrites the ruleset, so there's no history or diff;
  4. changed values outside the sample are invisible;
  5. the regression report gives counts without names;
  6. notes don't carry forward;
  7. `check-rules` doesn't test constant/filter rules.

### 2.8 Uncertainty signals (R-uncertainty)

Fleshed out in [`design-notes.md`](research/design-notes.md#r-uncertainty-uncertainty-signals-as-a-first-class-idea).

**Signal kinds.** An *uncertainty signal* is a named, deterministic check on each match. There are four kinds:
- **value:** empty, shape outlier, length outlier, label text included, markup leak, not in vocabulary;
- **comparison with other rows:** duplicate value/record, cross-field mismatch, block count ≠ record count;
- **page:** course-code pattern outside every record ("possible missed course"), a non-course page full of codes
  ("possible missed page", Eric's A2.5 caveat);
- **history:** changed since accepted, previously rejected, new/vanished in this version.

**Ordering.** The rule view orders rows by signals, then a random sample of rows with no signals.

**Comparison view.** The **version comparison is the same mechanism**, sorted by the history signals. That matches
Eric's A4.1: Jared's previous accepts/rejects first, then other signals, then a sample.

Data supports the value. One example: Marshall Description is absent on 1,201 course entities, but no record says
which rule found nothing.

### 2.9 Deployment and environment (B12, B13, I3)

- v2 isn't deployed anywhere: no workflow builds it, and it runs on a laptop + ngrok.
- The five catalogs and their latest runs: AVC `2026-10-12T20-59-13Z` (4.0 GB of pages), CCSF `2026-10-01T16-02-34Z`,
  Marshall `2026-10-20T13-18-30Z`, UALR `2026-10-18T21-05-00Z` (UALR's crawl is mostly program pages: 1,176 of 1,276
  records are stubs, so *inferred*: course pages were under-crawled), WVU `2026-10-20T13-19-46Z`.
- **I3 (local and Azure) is easy to support:**
  - v2's `Store` already abstracts folder vs `azure://`, prefixes included;
  - the scratch prefix and the local mirror below both work as roots;
  - pulling a whole catalog to local disk with `az` took 5–9 minutes per catalog (AVC is the slow one).
- **Path hygiene:** `index.json` has stale entries with a doubled `<catalog>/<catalog>/<run>` path from local runs,
  with frozen counts (AVC: 19 vs the real 145 accepted). v3 should key runs by `(catalog, run_id)`, not by
  filesystem path.

---

## 3. First draft of the data model (A7.2, for S to refine)

Eric asked for a data model that covers everything discussed. This is research's draft. S will fix the details.
Principles:
- crawls, rule versions and extractions are **immutable**;
- annotations are an **append-only** log;
- everything mutable is small and derived from that log.

**Definitions (small JSON, immutable once written)**

| Entity | Key | Fields |
|---|---|---|
| `rule_version` | `(catalog, rule_id, version)` | `kind` (page / locator / field), `content_hash`, `definition` (declarative JSON), `what`, `how`, `why` (empty for v1), `examples`, `depends_on` (page rule, locator), `ctdl_property`, `published_by`, `published_at` |
| `ruleset_version` | `(catalog, version)` | settings (`content_root`, page title, sample, `pane_css`, signal thresholds), list of `(rule_id, version)`, `parent_version`, `changed_rules`, `published_by`, note |
| `rule_status` | log events | `in review` → `approved` / `needs work`, per rule version (D8) |

**Extraction output (one immutable Parquet file per `(run, ruleset_version)`, plus a manifest entry)**

`matches.parquet`, one row per value a rule produced, or per "found nothing" (so empty is a fact, not an absence):

| Column | Notes |
|---|---|
| `catalog, run_id, ruleset_version` | |
| `rule_id, rule_version, rule_kind` | |
| `page_stem, page_url` | page-rule rows have only these |
| `occurrence_key` | `page_stem + locator css_path` (the stable key annotations attach to) |
| `locator_css_path, locator_index` | from the document root |
| `course_code` | normalized, from the code rule on the same occurrence (null if none) |
| `value, raw_text, element_css_path, char_start, char_end` | provenance (A7.3) |
| `status` | `found` / `empty` / `no_match` |

Unchanged rules' rows can be copied from the parent ruleset version's file rather than recomputed. Each row also
carries a `signals` list, or signals are computed when queried.

**Annotations (append-only JSONL, one log per catalog)**

| Field | Notes |
|---|---|
| `id, at, author` | |
| `target` | `{rule_id, rule_version_seen, occurrence_key, course_code, page_stem}`, or a page or a rule |
| `verdict` | `correct` / `wrong` / `missing` / `unsure` (expert flag) / `note` |
| `expected` | `{text, css_path, char_start, char_end, quote_context}` (highlight-to-annotate, D5) |
| `note` | free text |
| `supersedes` | id of an earlier annotation on the same target (edits never rewrite) |
| `imported_from` | v2 session + decision key, for the D6 import |

Joining annotations to two ruleset versions' `matches.parquet` on `(rule_id, occurrence_key)` (falling back to
`(rule_id, course_code)`) gives: fixed / still wrong / newly wrong / unchanged / new / vanished. That's the version
comparison and the history signals.

**Golden output (A7.4)**

- `golden/<catalog>/<publication_id>/courses.json`: domain-only content:
  - CTDL property + value per course;
  - `source_url` and the immutable page location (`css_path`, offsets);
  - no rule IDs.
- `golden-lineage.parquet` beside it: `(golden_record_id, ctdl_property) → (ruleset_version, rule_id, rule_version,
  occurrence_key, annotation ids)`. That's the "association table" Eric asked for, so every golden value traces back to
  its rule.
- This replaces Save golden dataset per page (that button can stay in the record tab, A2.7).

**Pages and assets**

- Pages stay where the crawl put them.
- `assets/<sha256>.<ext>` + `assets-manifest.json` (URL → hash) per run (D7).
- One `review-ui-v3-index/manifest.json` lists every run, ruleset version, extraction file and annotation log, so
  nothing is ever found by listing or globbing Azure.

**Layout.** It mirrors the crawl folders (A2.3: "co-locate the Parquet with the crawl"):
`<catalog>/<run>/review-ui-v3/extractions/<ruleset_version>/matches.parquet`,
`<catalog>/review-ui-v3/rules/…`, `<catalog>/review-ui-v3/annotations.jsonl`. Paths only appear in the manifest.
Queries go through it.

---

## 4. How the Part D assumptions stand

| | Assumption | Status after research |
|---|---|---|
| D1 | 7 required + Coded Notation | **Kept**, refined: Coded Notation and External Identifier read the same element, so they share one locator. 4 of the 7 are constants/URL and can start approved. Credit Value is dropped |
| D2 | page / locator / field rules | **Confirmed.** The locator can be pulled out with no change to output |
| D3 | show the code, key by occurrence + code | **Confirmed**, with numbers: code-only keys break on Marshall/WVU |
| D4 | missed pages as a signal | **Kept**. "Possible missed page" signal, plus a manual verdict |
| D5 | css_path + offsets + quote | **Feasible**, tested in a same-origin sandboxed iframe |
| D6 | record tab uses the same log; import v2 | **Changed to "import"**: ~2,000 verdicts map exactly |
| D7 | v3 `assets fetch`, no xtra-cli change | **Confirmed**. Small (≤40 MB/catalog). Font licensing is open |
| D8 | in review / approved / needs work | **Kept** |
| D9 | "same course" = same code | **Kept**. Cases that can't be matched are counted and listed |
| D10 | what / how / why + examples | **Kept** |
| D11 | always publish a ruleset version | **Kept**. Rerunning everything is cheap enough after the fixes |
| D12 | scratch prefix | **Created** (see below) |

## 5. Open questions to take into S

1. **Font licensing** (2.5): may we store copies of institution-licensed fonts?
2. **Where `matches.parquet` is computed for a publish:** on the laptop, uploaded by `rule publish` (simplest, and "the
   UI never runs anything"), or by a server endpoint? Research suggests the laptop.
3. **Code rule vs External Identifier:** keep two field rules reading the same element (as today), or have one code
   rule with a derived External Identifier? This affects how the review is shown, not the data.
4. **UALR's course pages look under-crawled.** That's a crawl question (out of scope), but it affects that catalog's
   golden set.
5. **Fix the v2 hot spots too?** They're cheap and would help Jared now. That's a scope call for Eric. v3 doesn't
   depend on it.

## 6. Work streams and order (after research)

Research removed two unknowns: rendering needs no crawler change, and storage is decided enough to design. Updated:

| # | Work stream | Depends on | Parallel? |
|---|---|---|---|
| W0 | **Storage layer + manifest**, local folder / Azure scratch switch (I3) | — | Start first |
| W1 | **Page pane**: whole-page render, `assets fetch`, highlight + selection capture, mockup-style browser frame | W0 (to read pages/assets) | **Independent of W3. Can run alongside from day one** |
| W3 | **Data model + v3 CLI core**: rule/ruleset versions, extraction → `matches.parquet` (paths from the document root, memoized `css_path`), annotation log, v2 import | W0 | The spine |
| W4 | **Uncertainty signals** (SQL over matches + annotations) | W3 | After W3's schema |
| W5 | **Rule-centric UI** (+ record tab) | W3 schema; uses W1's pane | Proof of concept can start on fixtures once the schema exists |
| W6 | **Version comparison** | W3, W4 (history signals) | — |
| W7 | **Claude loop**: prompt generator, `rule show/annotations/try/publish`, `pages get` | W3, W4 | — |
| W8 | **Golden publication + lineage** | W3 | Late, small |

Order: **W0 → W3 → W4 → (W5, W6, W7) → W8**, with **W1 alongside from the start**. The thin slice is still one rule
(Course Name or Coded Notation) on one catalog (CCSF, whose keys are clean and which has 655 of Jared's verdicts), end
to end.
*Optional, separate:* the v2 hot-spot fixes (Q5), if Jared needs v2 to be faster before v3 exists.

---

## What research created (delete these to undo)

- **Azure:** prefix **`zz-scratch-review-ui-v3/`** in `ceteststorage/xtra-cli-output`. It has 44,483 blobs:
  server-side copies of the CCSF and WVU runs, `review-ui-index/`, test extractions and reviews made by the speed
  measurements, and a `README.txt` saying what it is. Each blob is listed in `research/speed-storage.md` §7. The
  agent checked that the real CCSF, WVU and `review-ui-index` blobs did not change. Delete the prefix to undo.
- **Local:** `~/review-ui-v3-data/`, a read-only copy of the five catalogs' runs + `review-ui-index/`, same layout,
  with a README. When this was written, AVC (~4 GB) was still downloading; `download.log` gets a `DONE` line when it
  finishes. Delete the folder to undo.
- **Repo:** only this `qrspi/` folder. Nothing is committed.

---

## Eric's review of the research (2026-10-26)

Eric's words, tidied only for readability. Notes from Claude are marked **Note**.

- **Font licensing (open question 1):**
  > Yes, we are allowed to store copies, because we won't be using or redistributing the fonts.

- **v2 hot-spot fixes (open question 5):**
  > Sure, but that should be a completely separate work stream on a separate worktree. That's the kind of thing you
  > should use the Superset CLI for, to isolate it completely.

- **Finding 1, speed:**
  > Awesome. Maybe you could do something like only fetch the pages we're looking at as we click, and do some
  > prefetching. But if you've got a prototype, great. Take what I said as a suggestion, not a prescription, since
  > I'm not as familiar with the problem as you.

- **Finding 2, Parquet + DuckDB:**
  > I'm totally all right with Parquet files, because I get that the issue is a lot of small reads. Let's not do
  > DuckDB then. We can use DuckDB as an interface to explore it, but just use the Parquet files. The most important
  > thing was the data model, I think. As long as we have relational integrity between the data and the Parquet files,
  > that's pretty much what I cared about.
  >
  > **Note (Claude):** Read as: the *storage* is Parquet (plus JSON/JSONL), with no DuckDB database file. DuckDB is
  > allowed only as an in-process query library over those files, for the server, the CLI and exploration.
  > Relational integrity (primary and foreign keys across the files, checked by a validator) is a first-class
  > requirement of the spec.

- **Findings 3–9:**
  > CSS: I trust your reasoning there. The saved HTML already contains what JavaScript built: terrific, I love that
  > finding. Provenance mostly exists already: great. The record locator is already a separate rule in practice:
  > terrific. Course code as the key: terrific. Jared's 2,000 past verdicts can be imported: terrific.

- **Rule kinds (2.1):**
  > Page rules, record locator rules, field rules: awesome. Merging is not a rule: fine.

- **Name:**
  > Instead of "xtra review", I want it called something like Golden Dataset Studio. Call it **CTDL Golden Dataset
  > Studio**. It doesn't need to reference xtra.

- **Next step:**
  > Please create a spec from all this, as a markdown spec. I also want a Claude HTML artifact that combines the
  > flow diagram of the review (like the xtra page-routing page) with a diagram of concepts, a dependency budget and
  > zoom levels of abstraction (like the Fantasy Inn architecture map). Generate actual UI and take screenshots for
  > the spec. In the spec, show actual file and folder layouts and example data in them, to communicate boundaries,
  > inputs, outputs, vocabulary and workflow.
