# Build notes: review UI (sme-fixes §1, §2, §3, §9)

Branch `sme-fixes-review-ui`, from `b160a3a`. Spec: [`03-spec.md`](03-spec.md). Paths are relative to
`golden-dataset-studio/`. `make check` passes (ruff; pytest 159 passed; vitest 192 passed; build). The `slow` tests
fail the same 9 tests on `b160a3a` as on this branch (they depend on the local mirror's data, not on this work).

## What changed

### §1 Highlight bar, in / out pieces, anchored comments

- **Reusable bar**: `web/src/pagepane/HighlightBar.tsx` (`BarAction {id, label, title, tone, run(sel)}`). The page pane
  takes `barActions` (`web/src/pagepane/PagePane.tsx:28`); with actions, a selection shows the bar instead of calling
  `onSelection` (`:224`); it closes on Esc (capture phase, so the tab's own Esc doesn't also fire), a click elsewhere,
  a scroll in the page, a new page, or when the actions go (`:248-265`). Position: `barAt` (`:391`), above the
  selection or below when there's no room. Styles: `web/src/pagepane/pagepane.css` (end, `.gpp-hbar`). The §5 stream
  can pass field-name actions (`{id: "ceterms:description", label: "description", …}`) the same way.
- **Rules tab actions** (property rules, not lists): `web/src/rules/RulesTab.tsx:277` (💬, ✓ In answer, ✕ Not in
  answer, each with a tooltip). The old drop of a selection equal to the found value is gone (was `RulesTab.tsx:250`).
- **Pieces**: `Piece = CapturedSelection & {polarity}` and `Draft.anchor` (`web/src/rules/logic.ts`);
  `expectedOf` (`logic.ts:170`) writes `segments[].polarity` whenever there is more than one piece or any `out` piece;
  `text` = the `in` pieces joined, or with only `out` pieces the value found without them (`withoutOut`, `:161`).
  A comment event carries `anchor {css_path, char_start, char_end, text}` (`logic.ts:201`).
- **Drawing**: paint kinds `excluded` (red dashed, light red fill) and `note` (a numbered blue bubble at the end of the
  text) in `web/src/pagepane/paint.ts:13, 150, 174`; reviewer pieces show over the yellow value (`:191`). The Rules tab
  draws draft and saved pieces by polarity and every anchored comment as bubble 1, 2, … (`RulesTab.tsx:305-320`); the
  row's history line numbers the same comments (`logic.ts:116`, `parts.tsx:97`). The ✗ expansion labels `out` pieces
  "✕ not in answer" (`parts.tsx:67`); the comment box quotes its anchor (`parts.tsx:47`).
- **Server**: `log.py:26` (`POLARITIES`) and `:60` validate polarity and anchor; `query.py:25` `ANNOTATION_COLUMNS`
  gains `segments[].polarity` and `anchor`; `routes_review.py:709` stores `anchor`, `:87` returns it in briefs.
  Readers: `prompt.py:119` and `loop.py:122-128, 249, 257` tell the fixer which pieces are NOT in the answer and what
  text a comment is about.
- **`::selection`** is a neutral blue (`render.py:54`); new styles `render.py:53, 66-68, 77-78`; `RENDER_VERSION` r4.

### §2 Deep links

- `replaceParam` (`web/src/shell/router.ts:49`): `history.replaceState`, no hashchange (the tab doesn't refetch).
  `selectRow` writes `?row=<row key>` on click, Tab / Shift+Tab, after ✓ / ✗ (`RulesTab.tsx:223`); on a page row of a
  course-blocks locator it writes the page stem (the server's `_find_row` already matches it).

### §3 Course blocks

- **Titles**: `locator_title` (`routes_review.py:38`): `repeat` → "Course blocks: every `<repeat>` on the page" /
  "Several courses on one page, one block each"; none → "Whole page is one course" / "Each page's content area is one
  course". `rule_title(rule, rules)` (`:46`): a page rule read by a repeating locator is subtitled "Pages with courses".
  The rule detail carries `locator_title` for property rules (`:372`, shown as "Looks inside" in `RuleHead.tsx:35`).
  `RuleHead.tsx:31` shows `repeat_filter.selector` (and `scope`). The fixed locator titles are gone from
  `RuleHead.tsx` and `routes_review.py`.
- **First-pass prompt**: `LOCATOR_NAMING` (`prompt.py:55`, used at `:711`).
- **Rows**: a repeating locator's rows come grouped by page, in page order, with `page_courses`
  (`routes_review.py:292-306, 424`). The web groups them (`pageGroups`, `logic.ts:213`) into one page row (subject from
  the course keys, page title, "N courses", ✓ that accepts all: `acceptPage`, `RulesTab.tsx:382`), with the current
  page's courses nested and "+ Add a course this rule missed" at the end (`RulesTab.tsx:637-670`). Locators without
  `repeat` keep one row per course.
- **Keys** (`moveIn`, `logic.ts:235`; `RulesTab.tsx:478-495`): page level: Tab / Shift+Tab next / previous page, Enter
  into the page's first course, 1 accepts the page; course level: Tab / Shift+Tab next / previous course (Tab after
  the last → next page row; Shift+Tab on the first → its page row), Esc up to the page row. Key strip:
  `PAGE_KEY_HINTS` (`RulesTab.tsx:57`).
- **Page boxes**: each found course keeps its border, transparent; only the current course is filled (none on a page
  row); green / red border once ✓ / ✗ (`RulesTab.tsx:322`, `render.py:66-67`).

### §9 Defaults

- Sample defaults to Autostratify (`RulesTab.tsx:80`); Compare keeps Shuffle; the drawer stays shut.
- "Annotated by" defaults to Anyone (`RulesTab.tsx:141`); `?by=` is written only when a person is picked (old links
  with `by=anyone` still read as Anyone). `defaultAnnotator` is no longer used by the tab.

## Tests

`tests/test_routes_review.py` (derived titles AVC vs CCSF, page rule subtitle, `by_page`, polarity / anchor validation,
`ANNOTATION_COLUMNS` reading old and new events), `tests/test_prompt.py`, `tests/test_property_lists.py`;
`web/src/rules/RulesTab.test.tsx` (bar actions, value-equal selection, in/out saved and drawn, out-only expected,
anchored comment, `?row=` via replaceState not pushState, Anyone default, Autostratify default, nested page rows with
Tab / Enter / Esc / Shift+Tab, page ✓ accepts all, box states, no-repeat locator), `web/src/rules/logic.test.ts`,
`web/src/shell/router.test.ts`, `web/src/pagepane/HighlightBar.test.tsx`.

## How to see each behaviour (for screenshots)

Checked on a local server over the local mirror (AVC; screenshots of the bar and the nested rows were taken and look
as specified). CCSF needs a root with its rulesets (the mirror has none): the same screens work there.

1. **Highlight bar**: AVC → Rules → Description → `?row=ACCT199`. Drag across "LIMITATION ON ENROLLMENT…" on the page:
   the dark bar sits just above it (💬 · ✓ In answer · ✕ Not in answer; hover for tooltips). The selection is blue.
2. **Not in answer**: click ✕ Not in answer: red dashed outline, the row's ✗ lit, "✕ not in answer" in the expansion.
   Then select "Work Experience Education is supervised…" → ✓ In answer: green outline. Enter saves; reopen the row:
   both pieces drawn by polarity.
3. **Value-equal selection**: select exactly the yellow value: the bar still appears.
4. **Anchored comment**: select a phrase → 💬 → type → Enter: a blue "1" bubble at the phrase; the row's history line
   shows the comment with the same "1".
5. **Deep link**: click or Tab between rows: the address bar's `?row=` follows; Back doesn't step through rows.
6. **Course blocks (titles)**: CCSF → Rules → record locator "Course blocks: every .course-summary-wrapper on the
   page"; "How this rule works" lists the definition; page rule "Course pages" subtitled "Pages with courses". AVC: the
   locator reads "Whole page is one course"; AVC's program-requirement locator (it repeats) also shows course blocks.
7. **One row per page**: CCSF locator (or AVC → "Course blocks: every #accordion-program-builder-rules .new-rule …"):
   page rows with "N courses", the first open. Enter → first course (its box filled); Tab → next course; Esc → back
   to the page row (no box filled); Tab → next page. ✓ on a course turns its box green; ✗ red. ✓ on the page row
   accepts every course on it. Key strip at the bottom says so. CCSF Interior Design:
   `#/c/ccsf/rules/locator-course-page?row=ccsf-curricunet-com-catalog-iq-courses-3-102-3ecab791c0`.
8. **Defaults**: open any rule: Sample shows Autostratify (drawer shut), Annotated by shows Anyone, no `by=` in the URL.

## Left undone / notes

- **Page row title on CCSF**: every CCSF page is titled "View - CurriQunet META", so a page row reads "INTD · View -
  CurriQunet META · 3 courses", not "INTD · Interior Design" as in the mock. The department heading isn't in the
  extraction; it would need a page-level heading rule or parsing the page's HTML on the server.
- **AVC program-requirement locator** is titled from its selector ("Course blocks: every #accordion-program-builder-rules
  .new-rule on the page"), long in the sidebar but true. Its page rule "Program pages that list courses" is now
  subtitled "Pages with courses".
- **Golden dataset** (§7, other stream) must read `segments[].polarity`; `golden.py` reads no segments today.
- The `slow` tests were run and fail identically on the base commit (mirror data drift), unrelated to this work.
