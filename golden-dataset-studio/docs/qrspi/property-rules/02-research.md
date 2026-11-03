# R — Research: every CLI extraction label as a field rule

Phase 2 of QRSPI for growing the Studio's field rules to every CLI Extraction Label. Facts come from three
sources: the code, 22 sampled course records in each of the six catalogs, and Credential Engine's CTDL schema
repository. Each topic answers the matching items in [`01-questions.md`](01-questions.md): Part B, and the Part D
assumptions. This file is the summary. Evidence, commands and numbers are in the detail files:

| File | What's in it |
|---|---|
| [`research/pages.md`](research/pages.md) | B1: each of the 33 labels on the saved pages of all six catalogs (label × catalog table), how lists are split, nested parts, what today's rule types can't reach |
| [`research/code.md`](research/code.md) | B3, B4, R4, B7, B8 and stubs: every reader of the property list, what `multiple` needs, `>` paths through the Studio, the Rules tab and home table, cost for WVU |
| [`research/sheet-and-ctdl.md`](research/sheet-and-ctdl.md) | B9 and B2: reading the sheet without signing in, each label against CTDL, `prerequisite` vs `requires`, `learningOpportunityType` |

- Researched: 2026-11-02, on `golden-dataset-studio-local` (`5dbb778`).
- **Nothing in Azure was changed.** No source file was changed and nothing was committed. Pages were downloaded only
  into the local cache (`~/.cache/golden-datasets`). See "What research created" at the end.
- Test suites on the branch as it is: `uv run pytest -q` 122 passed (52 slow/Azure deselected); `npm test` 148 passed.
- *Inferred* marks things concluded rather than checked.

---

## 1. Headline findings

1. **Each catalog has a value on the page for 12–21 of the 33 labels. Four labels appear nowhere.**
   - **Everywhere:** name, description, code and credit (UARK has no code and no credit). Prerequisites are
     printed in all five college catalogs.
   - **Never, in any catalog:** `hasPart`, `deliveryTypeDescription`, minimum and maximum duration. `keyword` is
     nearly absent, and `inCatalog` is never printed as a URL.
   - **Delivery type, modality and duration:** printed by UARK only.

   Labels printed (P) in the 22-course samples:

   | | AVC | CCSF | Marshall | UALR | WVU | UARK |
   |---|---|---|---|---|---|---|
   | labels with a value on the page in ≥ 1 sampled course | 17 | 18 | 13 | 21 | 14 | 12 |

   *(Out of 33, counted from the table in `research/pages.md`. A label counts when it's printed (P), a copy of its
   parent's text, a title word or an "or". Values that are only implied (I), or that sit outside the record (O),
   don't count. Neither does "hours only".)*
2. **Labels that need decisions, because pages don't print them:**
   - `inCatalog`, CCSF's credit unit type and most `isNonCredit` values are implied, never printed. A3.12 says
     "extract only what's on the page", so these stay empty unless S decides otherwise.
   - `subject` is printed only as the page heading at CCSF and Marshall, outside the course record.
3. **The two condition-profile `>description` children always equal their parent.** On every catalog,
   `prerequisite>description` holds the same text as `prerequisite`, and the same goes for `recommends`. The parts
   that carry information are the target courses (1–15 codes per course), and "or" for `alternativeCondition`.
4. **Lists need three ways to split, not two (D5):**
   - **separate elements:** CCSF hour spans, Marshall's links, UARK's modality;
   - **one text split on a separator:** ",", ";" or line breaks;
   - **every match of a regex in a text:** course codes in AVC and CCSF prerequisites.

   WVU and UALR prerequisite links can't simply all be taken, because corequisite and description links look the
   same.
5. **Some labels need a rule to reach things today's rule types can't:**
   - text outside the record (the page heading, for `subject`);
   - attributes (`href`, popover text);
   - bare text between tags (UALR);
   - the page URL's `course=` slug, UARK's only identifier.
6. **Nothing needs a `group_index`, and `>` paths don't break the Studio (R4).** A `>` path flows through golden
   files, lineage, `golden.parquet`, scores and Evals without mis-keying. One web helper (`termUrl`) builds a broken
   CTDL link from it.
7. **`multiple` needs no Parquet change, but nine lookups ignore `value_index`.** Every table already has
   `value_index`. Every in-memory index keyed by (rule, occurrence) drops the second value.
   - **Tested today:** a second value on one course is silently missing from the Rules tab, the golden files and
     the Records tab.
   - Compare even counts it as "new" against the same version.
8. **A stub (a rule with no definition) can't exist today.**
   - `rule publish` refuses a rule with no `definition`.
   - A field rule with a `rule_type` but no selector extracts the **whole course block**.
   - A stub can be approved.
   - A stub needs its own `rule_type` and four small guards, and should **write no rows**. As empty rows, 28 stubs
     would add 617k match rows to WVU and triple the time to work out every rule's status.
9. **36 field rules cost little to extract and more to review.** For WVU (22k courses):
   - extraction stays about 1–2 s;
   - the server's in-memory snapshot grows from 120 MB to about 590 MB;
   - working out every rule's status (the rule list, and `golden.plan` after each verdict) goes from 0.7 s to
     about 3.5 s.
10. **The sheet syncs without signing in (B9).** It's shared by link. One anonymous `export?format=xlsx` gives every
    tab, including the Course tab's Required block, which parses to exactly A2.5's seven fields.
11. **Two labels don't match CTDL as written (B2):**
    - **`ceterms:prerequisite` points straight at a Course.** CTDL's ConditionProfile hangs off `requires` (and
      `recommends`), not `prerequisite`.
    - **`ceterms:learningOpportunityType` isn't a CTDL property.** In Credential Engine's publishing code it names
      the three classes (Learning Opportunity, Course, Learning Program): exactly what the Studio's **Learning Type**
      does.
    - `contentDescription` isn't in the schema repo either, but the publishing API accepts it.

---

## 2. Findings by topic

### 2.1 The labels on real pages (B1)

| Group | Labels | What pages show |
|---|---|---|
| **Printed nearly everywhere** | identifier, name, description, codedNotation, creditValue, creditUnitType | UARK prints no code (its key is the URL's `course=` slug) and no credit. CCSF never prints a unit word |
| **Implied, not printed** | subjectWebpage (the page URL, as today), inCatalog | `inCatalog` is never printed as a URL. UALR prints the catalog's *name* |
| **Printed in some catalogs** | prerequisite (+ target, alternative), recommends (+ target, alternative), credit min / max | AVC labels "Minimum/Maximum Credit Units" on every course. Others print ranges in 1–6 of 22 courses. UALR writes them in words ("One, two, three, or four credit hours") |
| **Printed sometimes** | isNonCredit, learningMethodType, learningMethodDescription | CCSF prints a credit status on every course (192 of 1,927 "Noncredit"). AVC's and CCSF's hour labels read as learning methods (Lecture, Lab) |
| **UARK only** | deliveryType, estimatedDuration, exactDuration | "Online", "Self-Paced", which mixes delivery and method. "Access to Course: 6 Months", "Contact Hours: 120" |
| **Outside the record** | subject | CCSF and Marshall print it as the page heading |
| **Title words only** | learningOpportunityType | "Special Topics", "Seminar", "Lab" in 3–11 of 22 titles. UARK says "course" / "program" |
| **Absent everywhere** | hasPart, deliveryTypeDescription, minimumDuration, maximumDuration, keyword (nearly) | UARK's "fifth course of the … series" is the inverse of `hasPart` |
| **Questionable fit** | contentDescription, estimatedDuration>description | No separate field. Some descriptions hold a "Topics include …" sentence. AVC's and CCSF's contact hours aren't a span of time |

### 2.2 The property list in the code (B3)

- **The list has 14 readers in Python and 8 hard-coded rule ids or labels in the web app.** Every reader needs only
  label, CTDL path and order. The Rules tab needs `required` and a group as well.
- **Three readers must stay frozen at today's eight.** They are `import_v2.IN_SCOPE` (or import starts pulling in v2's
  credit rules, which are out of scope) and the two "old publications published every property" fallbacks
  (`golden.py:208`, `check.py:370`).
- **Proposed file: `src/golden_datasets/properties.csv`,** inside the package, so the CLI, server and Claude all read
  the same one. Its columns:
  - `path`: column F, or column E where F is blank;
  - `label` (unique), and `column_d` as written in the sheet;
  - **`rule_id`**: assigned once by `properties sync` and never renamed, so counts add up across catalogs;
  - `profile`, `parent`, `multiple`, `required`, `sheet_row`, `status` and `vocabulary`.

  Details are in `research/code.md` B3.4.
- **Most catalogs have 12 field rules today, not 8.** Eight read course pages. Four `stub-*` rules read program-page
  course lines (`locator-program-requirement`). UARK has 6, and WVU 8. The new list covers course pages only.

### 2.3 Lists: `multiple` (B4, D5)

- **The tables already hold several values.** `MATCHES`, `GOLDEN` and `LINEAGE` all have `value_index`.
- **The fix is the in-memory lookups.** Nine are keyed by (rule, occurrence) without `value_index`: the Rules tab's
  rows, verdict re-attachment, `golden.plan` / `tree_pages`, the Records tab and Compare. Today's behaviour when a
  second value exists is that it is silently dropped (tested).
- **Smallest change** (`research/code.md` B4.4): the engine's `run_field` gets a `multiple` mode that takes either
  every element, a split on a separator, or every regex match. It writes `value_index` 0…n. Each of the nine lookups
  adds `value_index` to its key.

### 2.4 Nested labels as flat paths (R4)

- **No `group_index` is needed anywhere.** A3.13 put grouping out of scope, and nothing in the code needs it.
- **A `>` path is just a longer `ctdl_property`.** `column()`, `value_rows`, `by_column`, golden files, lineage and
  the Evals tab key it correctly. Only `termUrl` in the web app needs to link to the leaf term.
- **xtra's scorer counts a property it never extracted as `missing`.** So once a new column is approved and
  published, the Evals score goes **down** rather than showing "—". That contradicts the note on A4.16.

### 2.5 Stubs (A5.19, D8)

- **What a stub needs:**
  - its own `rule_type` (for example `none`) that the engine skips;
  - no rows in `matches`;
  - an exception in `check`;
  - Approve blocked;
  - a "Not started" status.
- **How a stub gets its first version.**
  - A stub has no rows, so there is nothing to annotate on it. The first annotation has to be made from the
    Records tab or the page pane (select the text on the page as "missing").
  - The Improve prompt's rule "the new version must do BETTER" can't be met by a first version. The prompt needs a
    "first version" case: find this label on the sample pages, then aim for coverage.

### 2.6 Rules tab, home table, Evals (B7)

- **The three groups and search fit the existing list.** The server builds the groups (`routes_review.py:231`) and
  `RuleList.tsx` renders them, so Required / Other fields / Not started is a server change plus a search box over the
  list. The default selected rule (`course-description`) stays.
- **Live order across all catalogs is cheap.** Counting expert reviews from the annotation logs alone takes 12 ms
  for all six catalogs, within 2 of the server's exact per-catalog counts. It needs the fixed `rule_id` from the
  property file, because the same label must have the same id in every catalog.
- **The home table and the approve dialog read the column list from the server** (`/catalogs-summary`). Showing
  "Required, then reviewed, then Show all" is a server and table change.
- **The tour and the screenshot scripts** (`bench/shots_review.py`) name rules by id and need updating with each
  stream.

### 2.7 Cost (B8)

| WVU, 22,023 courses | Today (8 field rules) | 36 field rules, stubs write nothing | 36, stubs as empty rows |
|---|---|---|---|
| Extraction compute | ~1 s | ~1–2 s | ~2 s |
| Server snapshot in memory | 120 MB | ~590 MB *(Inferred: scales with rules that find values)* | more |
| Every rule's status | 0.7 s | ~3.5 s | ~10 s |

- *Inferred:* 3.5 s after each verdict is noticeable. S should decide whether rule status is computed per rule on
  demand or cached per ruleset version.

### 2.8 The sheet and CTDL (B2, B9)

See `research/sheet-and-ctdl.md`.
- **Sync:** use one anonymous xlsx download. A `--from bu.xlsx` fallback covers the case where the sheet's sharing
  is ever narrowed.
- **Headers:** don't use `gviz`, because it merges the header rows.
- **Column F against CTDL:** every label maps to a real CTDL term on Course or its profile, except
  `learningOpportunityType` and `contentDescription` (§1, item 11).
- **Status:** `isNonCredit`, `inCatalog` and `lifeCycleStatusType` are marked *unstable* in CTDL.

---

## 3. How the Part D assumptions stand

| | Assumption | After research |
|---|---|---|
| D1 | Coded Notation first in Required, marked "course key" | **Holds.** Every catalog's records are keyed by it, except UARK, which has no code rule and is keyed by the URL slug |
| D2 | File = column F + column E for lifeCycleStatusType / inLanguage + Learning Type | **Holds**, with a fixed `rule_id` column added (§2.2). The four program-page `stub-*` rules aren't in the file and need a home (§4.3) |
| D3 | `required` column from the Course tab's block | **Holds.** The block parses to A2.5's seven fields |
| D4 | New labels ordered by sheet row while tied | **Holds.** Live counts across catalogs are cheap (§2.6) |
| D5 | A `multiple` rule returns a list; two ways to split | **Changed:** three ways, adding "every regex match" (§1, item 4) |
| D6 | prerequisite / recommends / hasPart Multiple | **Changed:** each course had one prerequisite block and one recommends block. The children `targetLearningOpportunity` are the lists. `hasPart` is absent everywhere |
| D7 | Learning Type and `learningOpportunityType` are different things | **Probably wrong.** `learningOpportunityType` isn't a CTDL property, and Credential Engine uses the name for the three classes, which is what Learning Type does (§1, item 11). Pages only print type words in titles |
| D8 | One ruleset version adds all stubs; one per later sync | **Holds,** if stubs write no rows (§2.5) |
| D9 | Name = column D, or "Parent: Child" | **Needs more.** `hasPart` and `learningOpportunityType` are flat with a blank column D. Labels must be unique, so a condition profile's `description` can't be "Description" |
| D10 | Row 24 means `prerequisite>targetLearningOpportunity`; any row with a label is a rule | **Holds.** Note that CTDL would put this under `requires`, not `prerequisite` (§1, item 11) |

---

## 4. Open questions to take into S

1. **Values a page implies but doesn't print.** `inCatalog` (the catalog URL), CCSF's credit unit type and most
   `isNonCredit` values. Leave them empty (A3.12 as answered)? Or allow a per-catalog constant, as
   `lifeCycleStatusType` and `inLanguage` already work today?
2. **Learning Type and `learningOpportunityType`** (D7). Is `learningOpportunityType` the same thing as Learning Type?
   If so, should Learning Type's rule be named by it, so there aren't two rules for one thing?
3. **The program-page rules.** Four `stub-*` rules read program-page course lines today. Which group do they go in?
   Required, because they are code / id / name / type?
4. **Approved new columns lower the Evals score,** because xtra doesn't emit them (§2.4). Should Evals score only
   columns xtra emits, while still publishing the rest to the golden dataset? Or is a lower score the honest number?
5. **Duplicate condition children.** `prerequisite>description` and `recommends>description` always equal their
   parent. Keep them as copies, so the sheet's list is complete? Or leave them as rules that stay **Not started**?
6. **New rule abilities.** Which of these does the first version add?
   - every regex match;
   - reading outside the record (page heading);
   - attributes (`href`);
   - bare text;
   - the URL slug.

   Without them, `subject`, UARK's identifier and some prerequisite targets stay empty.
7. **Names for rows with a blank column D,** and unique names for the four `>description` children. For example
   "Prerequisite: Description", "Duration: Description", "Has Part", "Learning Opportunity Type".
8. **Rule status after each verdict on WVU** (~3.5 s). Should it be cached per ruleset version and updated per rule?
9. **Contact hours as `estimatedDuration`?** AVC's and CCSF's contact hours aren't a span of time. Leave
   `estimatedDuration` empty there, or extract the hours as the parent's text for transformation to decide?
10. **Telling the sheet's owner:** row 24's lost prefix, Content Description's blank status, and
    `prerequisite` → `requires` in CTDL.

---

## 5. Work streams and order (after research)

| # | Work stream | Changes since Q |
|---|---|---|
| F1 | **Property list from the sheet:** `properties.csv` with a fixed `rule_id`, and `properties sync` (anonymous xlsx, `--from`). Freeze `IN_SCOPE` and the two fallbacks | adds `rule_id` and the three frozen readers |
| F2 | **Rules tab:** Required / Other fields / Not started, search, live counts across catalogs | program-page rules need a group (§4.3) |
| F3 | **Stubs:** a `rule_type` that's skipped and writes no rows; guards in `check` and Approve; the Improve prompt's first-version case | the "no rows" rule and the prompt change are new |
| F4 | **Engine: `multiple`** (elements, separator, every regex match), and `value_index` in the nine lookups | three ways to split; nine named lookups |
| F5 | **Golden files for `>` paths:** `termUrl`, the home table's columns, and what Evals scores | Evals question (§4.4) |
| F6 | **Spec, tour, screens, `check` rules** | with each stream |
| F7 | **New rule abilities** chosen in §4.6 | new, optional |

Order: **(F1, F4) → F2, F3 → F5 → F7**, with F6 alongside. F7 can be left out of the first version.

---

## What research created (delete these to undo)

| What | Where |
|---|---|
| This file and the three detail files | `docs/qrspi/property-rules/02-research.md`, `docs/qrspi/property-rules/research/` |
| Pages downloaded for the sample | `~/.cache/golden-datasets` (the Studio's normal page cache) |
| Scripts, the sheet's xlsx and CSV exports, CTDL term files | the session scratchpad (`…/scratchpad/b1/`, `code/`, `ctdl/`, `anon/`) |

---

## Seth's and Eric's review of the research (2026-11-02)

Both read the research aloud and reacted as they went. Their reactions are tidied for readability and grouped by the
section they answer. Transcription noise is left out. What each one changes is in the spec,
[`03-spec.md`](03-spec.md) §1.2.

**Properties that pages don't print** (§1, items 1–2; §4.1)

> **Seth:** That's fine, as long as a human reviewer can annotate `hasPart` and `deliveryTypeDescription` by hand,
> in case you were wrong. For `inCatalog`, CCSF's credit unit type and `isNonCredit`, empty is fine, so long as a
> human can overwrite it. For the implied ones, we'd just want to show that the value didn't appear on the page.
>
> **Eric:** I'm okay if we can't find some of these on every catalog. But I want the UI to show that these
> properties exist. On the catalogs page and the Evals page I still want a column for each one, even if it's blank.
> That shows a reviewer how much of the available properties our whole process covers. It's also okay to imply
> things, as long as the rule makes it explicit: "this is not present, but assume it's this, based on that".
> Capture what the inference is based on.

**Names** (whole document)

> **Eric:** Purge every reference to the term "field" from this project, and use "property". That's what CTDL calls
> it internally. Using the same word lowers the learning curve and gives the engineers and product people a common
> language.

**The coverage counts** (§1, item 1)

> **Eric:** I don't really understand it, so just build it into the first set of rules you generate for each
> catalog, and we'll iterate on them.

**Condition profile descriptions equal their parent** (§1, item 3)

> **Seth:** That's fine. A human will decide whether they're actually different.
>
> **Eric:** Write it as a note on the rules you generate, so the subject-matter experts can comment on it later.

**Lists and new rule types** (§1, items 4–5)

> **Seth:** WVU's and UALR's prerequisite links can't simply all be taken, because corequisite and description
> links look the same. Grill me on that one.
>
> **Eric:** I'll trust your judgment, but the spec needs concrete examples: real content from real pages, the real
> gaps in our rules, and why the new rule types would catch these. I love that you found blind spots, both in our
> existing rules and in the types of rules. Call out in the spec which new rule types and which new rules we need.

**How rules are declared** (§1, item 5)

> **Eric:** I'd like rules to work almost like a pub/sub model, or just "sub". A rule should be able to declare a
> dependency on another rule's output, and say what kind of input it needs: content on the page, the output of a
> rule, or what's in the URL. Think of the declarative rules as a dependency graph, where the pipeline flows from
> parents down through their children.

**The `>` in paths** (§1, item 6)

> **Eric:** Instead of the greater-than sign, use something like a little arrow. Make it prettier for the humans
> reading the UI.

**Lists and stubs** (§1, items 7–8)

> **Eric:** Include the silently dropped second value in the spec. A rule with no definition: you'll need to support
> that.

**Cost** (§1, item 9)

> **Seth:** That's fine.
>
> **Eric:** In the spec, call out the sort: required properties first, then by how many values a human has
> annotated, in descending order.

**The sheet sync** (§1, item 10)

> **Seth:** Yes, the download fallback is good.

**CTDL mismatches** (§1, item 11; §2.8)

> **Seth:** `learningOpportunityType` is not a valid CTDL term. Don't confuse it with `targetLearningOpportunity`.
> I'm also curious about the "unstable" status. I don't know that that's right.
>
> **Eric:** Where they don't match, do whatever is most true to CTDL. Where there's real ambiguity, put it in a
> section of call-outs for the subject-matter experts to sign off on. Make it very clear what's in scope and what's
> out. The spec should come in two forms: a markdown file with referenced images, and … *(the sentence was cut off)*.

**The property list in the code** (§2.2)

> **Seth:** I'm curious why we're importing from v2 at all, with `IN_SCOPE`.

**A new catalog's first rules** (new scope)

> **Eric:** Add to the scope a structured, exhaustive prompt with every rule type we want to generate for a brand
> new catalog. When we add a catalog, we run Claude against it as part of the import, to generate its first rules.
> The UI already has a place for that prompt, so the scope includes editing it to cover every rule we care about for
> a course.

**Open questions** (§4)

> **Seth:** It all stands. The work streams are fine.
>
> **Eric:** These are deeper into implementation than I care about. Make a proposal for each one.

> **Note (Claude):**
> - **"Unstable" is in the schema itself.** Each property file in `CredentialEngine/Schema-Development` carries
>   `"vs:term_status": "vs:unstable"`. Examples: `ceterms_isNonCredit.jsonld`, `ceterms_inCatalog.jsonld` and
>   `ceterms_lifeCycleStatusType.jsonld`, against `vs:stable` for `ceterms_name.jsonld`. `vs:` is the W3C
>   Vocabulary Status vocabulary, where "unstable" means the term may still change. It says nothing about whether
>   to use the term. The spec mentions it once, as a call-out.
> - **Why `IN_SCOPE` is frozen.** `import-v2` is how the five original catalogs got their first rules and Jared's
>   verdicts. It only runs again when a catalog is re-imported. If `IN_SCOPE` grew with the property list, a
>   re-import would bring in review-ui-v2's credit and requisite rules, which decision #18 keeps out. Freezing it at
>   today's eight keeps import behaving exactly as it does now.
