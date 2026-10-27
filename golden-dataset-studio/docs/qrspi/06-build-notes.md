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
