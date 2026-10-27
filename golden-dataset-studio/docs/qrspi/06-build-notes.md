# Build notes: choices made where the spec is silent or ambiguous

Each entry: what the spec says (or doesn't), what was built, and why. Newest last.

1. **v2 lives in another branch.** `review-ui-v2/` isn't on the `golden-dataset-studio` branch (it's on
   `review-ui-v2-vscode-79248126`). So the Studio doesn't import it: `src/golden_datasets/v2engine.py` is a vendored,
   unmodified copy of `review-ui-v2/server/review_ui/engine.py` (plus `ROOT_ID` from `runs.py`). It is used only by
   the equivalence test that checks the Studio's engine against v2 on real pages. v2 itself is untouched.
2. **One lxml parse, no fragment re-parse.** v2 cut the content root out with lxml and re-parsed it with
   BeautifulSoup inside a `#xtra-root` wrapper. The Studio's engine (`engine.py`) runs the same rule primitives on
   the whole page parsed once by lxml, with selectors compiled by cssselect. To keep v2's selector semantics without
   the wrapper: selectors evaluated from the content root use `descendant-or-self::` (v2's wrapper could match the
   root itself), selectors evaluated from any other element use `descendant::` (soupsieve never matches the element
   itself). `tests/test_engine_equivalence.py` compares labels and values with the vendored v2 engine on ~45 pages
   of each of the five catalogs: identical.
3. **Offsets are DOM `textContent`, values keep v2's text.** Spec §4.2 asks for `textContent` offsets. A `<br>`
   reads as a newline in v2's text (and so in values, which stay identical to v2's), so the engine converts only
   the offsets (`to_text_content`). Because the whole page is parsed (not a re-parsed fragment), whitespace is the
   browser's too: GEOG222's description v2 starts at offset 78 (the prototype's v2-style offset was 70; spec
   feedback 9 is this mismatch).
4. **Implied `<tbody>`.** Browsers wrap a table's direct `<tr>` children in `<tbody>`; libxml2 doesn't. The engine
   does what the browser does, so css paths through tables resolve in the page pane (Marshall, WVU use tables).
5. **`import-v2` runs `extract` rs-0001 before importing annotations.** Spec §3.2 lists import-v2 before extract,
   but annotations must point at occurrences and matches of an extraction (`extraction_seen`), so import-v2 does
   rules → ruleset v1 → extract rs-0001 (if missing) → annotations. Running `extract` afterwards is then a no-op
   (it refuses to recreate rs-0001).
6. **Which v2 inputs.** The latest review session that has `decisions.json`; its `session.json` names the v2
   extraction, whose saved `rules.json` is the ruleset imported (the rules Jared's verdicts were about). v2 inputs
   are read from `--v2-root` (default: the storage root; locally, the read-only mirror).
7. **Prose for non-AVC rules is generated.** AVC keeps the prototype's reviewed what/how. For the other four
   catalogs, `what` / `how` are generated from the definitions (and v2's rule descriptions), in page terms, until
   Claude rewrites them with the first new version.
8. **`pane_css`.** AVC gets the prototype's reviewed reveal sheet (spec feedback 12); the other catalogs start with
   an empty `pane_css` (v2's is kept as `pane_css_v2`), because v2's sheets were written for the bare fragment.
9. **Signals: the spec's names and severities.** `duplicate-occurrence` (was `duplicate-record`) and
   `unclassified-page-with-codes` (was `page-not-classified`) with the severities of spec §8. Kept from the
   prototype: `no-course-key` (high; an occurrence with no Coded Notation has no `course_key`, so it can't be
   grouped). Dropped for the first release, as spec §8 says: `markup-leak`. Counts on AVC rs-0001 equal the
   prototype's for every signal both have.
10. **`block-count-mismatch`** = on a page where a repeating record locator found courses, the number of blocks its
    `repeat` selector matches whose text contains a course code is larger than the number of occurrences kept
    (so `repeat_filter` dropped something that looks like a course). Fires once on AVC.
11. **Row order in the Rules tab.** Severity, then signal count, then a seeded random order for rows without
    signals; one such "boring" row is mixed in every 10 rows, so the reviewer always sees some. History signals
    that move a row up there: `previously-wrong` (incl. fixed rows), `changed-since-correct`, `new-in-version`.
    `previously-correct` doesn't (confirmed rows fade back instead); Compare uses every history signal.
12. **How old verdicts carry forward** (spec §4.3, "through the comparison"): on the same rule version, or when the
    value is unchanged, a verdict applies as given; a `wrong` whose value changed is **fixed** if the value now
    equals the expected text, else **still wrong**; a `correct` whose value changed is **changed since correct**.
    Rule status counts `wrong`, `still wrong` and open `missing` as "needs work"; `question` never does.
13. **Prose-only edits don't make a version.** `content_hash` covers only `definition` (spec §4.3), so a draft
    whose definition is unchanged reuses the existing rule version, even when its what/how/why changed.
14. **A changed code rule reruns its locator's occurrences** (their `course_key` comes from it); a changed page
    rule reruns everything (labels on every page); settings-only changes recompute signals only (page signals by
    re-parsing pages, rules copied).
15. **`course_key` lives only on occurrences** (spec feedback 3): `matches.parquet` has no `course_key`; the
    `matches` view of `golden-datasets sql` joins it in (`raw_matches` is the file as written).
16. **Signals PK has nullable parts** (`target_kind, rule_id, occurrence_key, value_index, page_stem, signal,
    css_path, char_start`), as spec §4.1 says. `golden-datasets check` groups NULLs as equal.
17. **Server reads the manifest at most every 3 s** (per catalog `Ctx`), and holds each extraction in memory once
    loaded (`review.Loader`); the annotation log is read incrementally from its byte offset.
18. **Assets over `--max-assets` still get an `assets` row** (status 0, no file), so `page_assets.url → assets.url`
    holds; the page pane loads them live (spec §9). `page_assets` stores the canonical URL an asset is archived
    under (numeric cache-buster queries removed, as `render.py` looks them up). CCSF references 847 distinct
    assets; 400 are archived by default.
19. **Golden output location.** Per-page files go to `<golden root>/<catalog>/<crawl>/<stem>/<stem>.{json,html}`,
    the layout `xtra-golden-sets-verified` already has. `lineage.parquet` and `publication.json` stay in the Studio
    (`<crawl>/golden-dataset-studio/golden/<pub>/`, spec §5.6 "lineage.parquet stays in the Studio"); the per-page
    JSON isn't duplicated there (the .html would double the crawl). The UI publishes to
    `$GOLDEN_DATASETS_GOLDEN_ROOT`, defaulting to `<storage root>/golden-dataset-studio/golden-out` so nothing
    outside the root is written unless asked for.
20. **What a publication contains.** Every course entry the locators found: course pages and program-page course
    lines (UALR's golden set is mostly the latter until it is recrawled, spec §12.3). A course listed twice on one
    page with identical values is written once; with different values, the second gets `value_index` 1, so
    lineage's key is `(publication, golden_id, page_stem, property, value_index)` (spec feedback 35). Entries with
    no `course_key` are left out and counted (`skipped_no_course_key`; UALR 222, WVU 16, Marshall 5).
21. **`golden_id` collisions, measured.** With spec §4.2's definition (one code, different names among its
    course-page entries) the current crawls give AVC 0, CCSF 0, Marshall 0, UALR 4, WVU 3, not the "~190" the
    research estimated for Marshall and WVU: Marshall's crawl has each code on one course page, and WVU's 9,805
    repeated codes repeat the same name. The Golden tab lists whatever collisions exist.
22. **`--allow-unapproved`** (CLI only) publishes for testing and records `approval_gate.all_rules_approved: false`
    in `publication.json` (spec feedback 27). The UI's button stays disabled until every rule is approved.
23. **Compare's earlier verdicts are ordered by history** (A4.1): newly wrong, still wrong, fixed, unchanged; wrong
    before correct within each. A `wrong` row whose value didn't change is "unchanged" (as in §5.8's query), so the
    summary's "still wrong" counts only values that changed but still aren't the expected text. Each signal's
    lost / gained list is capped at 100 rows in the API (full totals shown); `rule try` gets complete lists.
24. **Prompt details** (W6): it starts with the `export GOLDEN_DATASETS_ROOT=… GOLDEN_DATASETS_CATALOG=…` lines for
    the server's real root, so a fresh Claude Code can run commands immediately; it refers only to commands that
    exist; questions for the institution are listed separately and never as bugs; without a scope it covers all
    rules needing work. After M3, it also states the order a field rule applies (raw element text → regex → group
    → transforms → map), what `pages get` prints, and to update an example a fix makes wrong — the three things
    the M3 agent reported as unclear.
25. **Drafts.** A draft made from an older ruleset is merged into the latest one (with a warning); `"settings"` in
    a draft is merged shallowly; bad regexes and selectors are rejected before anything runs; examples must pass
    (`try` exits 1, `publish` exits 2).
26. **M3 was run by a fresh agent with only the copied prompt.** Its `course-description` v2 differs from the
    prototype's: it drops a leading "Prerequisite" line (colon optional, as THA218 needs) but keeps "Corequisite:"
    lines, which Jared never flagged, so 265 descriptions changed instead of the prototype's 278, and
    contains-label-text went 547 → 285 (prototype: 273). Same outcome on Jared's verdicts: 5 fixed · 0 still wrong ·
    0 newly wrong. It also reported ATH102 / ATH103 (now starting "Corequisite:") as a question for Jared, next to
    spec §12.2 Q2.
27. **Slow tests build their own AVC v1 root** from the mirror (`tests/conftest.py::avc_v1_root`), so they never
    depend on what has been published into `.data/root` (which now holds M3's v2).
28. **Page pane view tools** (Eric, after the build): a second row in the pane's browser bar with zoom out /
    zoom level (click = back to fit) / zoom in, and a "Page CSS" checkbox. Zoom works like browser zoom: the page
    is laid out narrower (1400 px ÷ zoom) and scaled up, so it reflows instead of scrolling sideways. "Page CSS"
    off disables the page's stylesheets and `style=""` attributes inside the iframe and adds a small plain-view
    sheet in `<head>`; the Studio's highlight styles stay. Neither changes the page's DOM structure, so css paths,
    highlights and selection capture keep working. Both settings are remembered in the browser.
29. **Renamed "Golden Rules Studio"** (Eric, after the build): the name people see — the top bar, the browser
    title, the prompt for Claude, the CLI help, the README. The `golden-datasets` CLI, the Python package and the
    `golden-dataset-studio/` folders of the storage layout keep their names, so existing roots keep working.
