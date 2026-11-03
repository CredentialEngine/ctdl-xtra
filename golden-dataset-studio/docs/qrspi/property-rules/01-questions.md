# Q — Questions: every CLI extraction label as a field rule

Phase 1 of QRSPI (questions, research, structure, plan, implement) for **growing the Studio's field rules from eight
to every CLI Extraction Label** in column F of the Phase 1 Extraction tab of "xTRA: Learning Opportunity BU
Template". Each label becomes its own field rule on the Rules tab. Required fields come first. The rest follow,
with labels that people have annotated before ahead of those nobody has touched. Nested labels such as
`ceterms:creditValue>schema:minValue` are values that sit inside a CTDL profile, not on the course itself. They need
a representation that the rules and the golden dataset files both understand.

- Original prompt: [`prompt.md`](prompt.md). The tab as read on 2026-11-02: [`phase1-extraction-2026-11-02.csv`](phase1-extraction-2026-11-02.csv) (re-read 2026-11-03: [`phase1-extraction.csv`](phase1-extraction.csv))
- Folder: `docs/qrspi/property-rules/`, next to the Studio's own QRSPI docs and `evals/`
- Asked: 2026-11-02. **Answered 2026-11-02, in two passes by voice:** first the grounding facts and A1.1–A1.3,
  then the rest of Parts A–C. The answers are tidied only for readability; transcription noise is left out.
- **This QRSPI goes as far as S** (questions, research, spec), not plan or build prompt (A6.24). The build doesn't
  start in this process. Code is written or run only when it helps answer a question.
- **Out of scope as well: transformation.** Mapping extracted text to CTDL vocabularies, and grouping the parts of
  one profile together, happen in a later transformation step (A3.11–A3.13).
- Each question has a **default**: what research works from until you answer. Notes from Claude are marked
  **Note** and kept separate from the answers.
- **Out of scope, from Seth's answers:**
  - Changes to xtra-cli, including how it names or scores credits.
  - Anything from review-ui-v2's rules.
  - The work is the Golden Dataset Studio only.
- Part D holds the second pass of questions, on the points Seth asked to be grilled on.

### What I already looked at (so the questions are grounded)

- **Column F has 33 labels: 20 flat and 13 nested.** The rows for Life Cycle Status Type and Language have no
  label, and neither do the four `LearningOpportunityProfile` rows under `hasPart` (rows 31–34).
  - **Flat (20):**
    - identifier, name, description, subjectWebpage, codedNotation
    - isNonCredit, deliveryType, deliveryTypeDescription, inCatalog, contentDescription
    - learningMethodType, learningMethodDescription, keyword, subject
    - creditValue, prerequisite, recommends, hasPart, learningOpportunityType, estimatedDuration
  - **Nested (13), in four profiles:**

    | Profile | Parent label | Child labels |
    |---|---|---|
    | `ValueProfile` | `creditValue` | `schema:minValue`, `schema:maxValue`, `ceterms:creditUnitType` |
    | `ConditionProfile` | `prerequisite` | `description`, `targetLearningOpportunity`, `alternativeCondition` |
    | `ConditionProfile` | `recommends` | `description`, `targetLearningOpportunity`, `alternativeCondition` |
    | `DurationProfile` | `estimatedDuration` | `exactDuration`, `minimumDuration`, `maximumDuration`, `description` |

  > **Answer:** The flat list looks right, and so do the nested profiles.

- **The sheet has a few oddities.**
  - Content Description has a label but its xTRA Status is blank, not "Include".
  - `targetLearningOpporunity` is misspelled on both rows. The CTDL term is `ceterms:targetLearningOpportunity`.
  - Row 35 is empty, and Delivery Type Description, `hasPart` and the ConditionProfile rows have no Single / Multiple.

  > **Answer:** I'm not really sure what xTRA Status means. Let's assume "Include" was accidentally left off Content
  > Description. Use the correct spelling: Opportunity. Ignore row 35.
  >
  > **Note (Claude):** xTRA Status is column A of the Phase 1 Extraction tab. Every other row with a label says
  > "Include", which reads as "in scope for Phase 1". Content Description is treated as Include from now on. The
  > missing Single / Multiple values are taken up in D6.
  >
  > **Note (Claude), second pass:** Seth fixed the typo in the sheet, and
  > [`phase1-extraction.csv`](phase1-extraction.csv) was re-read on 2026-11-02. Two things changed:
  > - Both rows are now spelled `targetLearningOpportunity`.
  > - Row 24's column F lost its parent and now reads just `ceterms:targetLearningOpportunity`. Row 28 still reads
  >   `ceterms:recommends>ceterms:targetLearningOpportunity`.
  >
  > Content Description's xTRA Status is still blank. See D10.

- **"Required" comes from the Course tab of the same sheet.** Its Required Properties block lists:
  - External Identifier, Learning Type, Name, Description, Subject Webpage, Life Cycle Status Type and Language.
  - Of these, only identifier, name, description and subjectWebpage have a column F label.
  - Coded Notation isn't required by the template. It is the Studio's course key (`rulesets.first_settings`,
    `model.code_rule_for`).

  > **Answer:** That's correct. For the required fields that have no column F label, use the column E shorthand for
  > now. I'm not really sure what the course key is. Grill me on that in the next step.
  >
  > **Note (Claude):**
  > - Column E (CTDL Shorthand URI) gives `ceterms:lifeCycleStatusType` and `ceterms:inLanguage`. Those are the
  >   names the Studio already uses for them.
  > - Learning Type has no column E shorthand: its Term cell on the Course tab is blank. See the note on Learning
  >   Type below.
  > - The course key is explained in D1.

- **One hard-coded list drives every column today.**
  - `model.PROPERTIES` (`src/golden_datasets/model.py:25`) holds eight (label, term) pairs.
  - The display order, `IN_SCOPE` at v2 import, Studio columns, golden files and the home table all come from it.
  - `scores.NOT_IN_STUDIO` (`scores.py:623`) hard-codes `creditValue`, `creditUnitType` and `prerequisite`.

  > **Answer:** Grill me on that.
  >
  > **Note (Claude):** See D2.

- **The Rules tab order is fixed in the server.**
  - It is set in `routes_review.py:231`: by locator, then `PROPERTY_ORDER`. Any label that isn't in `PROPERTIES`
    sorts last (99).
  - Nothing in the code knows "required". It appears only in spec §2 (`03-spec.md:73`).

  > **Answer:** Grill me on that. I'm not sure what it means.
  >
  > **Note (Claude):** See D3.

- **"Human annotated before" already has a signal.**
  - An expert's verdict sets `RowState.human` (`review.py:20`).
  - `scores._column_counts` counts human / rule / found per column.
  - `/annotators` counts annotations per rule.

  > **Answer:** That's great. Use that signal to decide which labels come first.

- **Human-reviewed values per column today (live, from the Azure root):**

  | Catalog | Human-reviewed values per column |
  |---|---|
  | AVC | 14 |
  | CCSF | 63–65 |
  | Marshall | 13 |
  | UALR | 10 |
  | UARK training | 0 (and no codedNotation or identifier rule) |
  | WVU | 83–84 |

  - Every one of the seven columns has been annotated in the catalogs that have reviews. None of the new labels has
    been annotated, so "annotated before" orders only the old columns.

  > **Answer:** Grill me on that. I'm not really sure what it means.
  >
  > **Note (Claude):** See D4.

- **A field rule gives exactly one string per course.**
  - `engine.run_field` takes one element with `select_one`, then applies a regex, transforms and an optional `map`.
  - `value_index` is always 0, and `MATCHES.value` is a string.
  - Six labels are Multiple in the sheet: deliveryType, learningMethodType, keyword, subject, prerequisite and
    estimatedDuration.
  - Three have controlled vocabularies (deliveryType, learningMethodType, and lifeCycleStatusType, which has no
    label).

  > **Answer:** I don't really understand that section.
  >
  > **Note (Claude):** It's explained again, in plain terms, in D5.

- **Nothing in the Studio is nested.**
  - Golden files are flat `fields: [{ctdl_property, property, value, …}]` (`golden.py:18`).
  - xtra's scorer reads the baseline only as flat `{ctdl_property, value}` (`score_extraction_match.py:284`).

  > **Answer:** I think that's good. We want flat fields. We just want to describe nested values in a flat
  > presentation.
  >
  > **Note (Claude):** This settles A3.10 and A4.15. A nested value is one flat field whose `ctdl_property` is its
  > column F path (`ceterms:creditValue>schema:minValue`). No nested CTDL view is built in this work.

- **xtra-cli has three names for the same credit range.**
  - `catalog extract` writes the flat keys `ceterms:creditMinValue` / `creditMaxValue`.
  - `lib/mapping.py` writes `schema:minValue` inside a `ValueProfile`.
  - The scorer flattens a profile through `ceterms:minValue` / `maxValue` / `unitText`.

  > **Answer:** Don't worry about what xtra-cli is doing right now. That's out of scope for this work. We just want
  > to focus on the Golden Dataset UI.

- **v2 already had credit rules, and import dropped them.** Credit Value, Min / Max, Credit Unit Type Description and
  Is Non-Credit (through `map`) are in `research/data-model.md:242`. `import_v2` kept only `IN_SCOPE` labels and counted
  the rest as `skipped_out_of_scope_rules`.

  > **Answer:** I think you're pulling that from review-ui-v2. Let's not worry about those.
  >
  > **Note (Claude):** Yes, they are review-ui-v2's rules. They're out of scope. A5.18 and B5 are dropped.

- **The spec rules this out today.** §2 (`03-spec.md:99`) puts "requisites, credit units" out of scope.

- **Learning Type has no CTDL term.** It is a constant `Course` rule that is never written to the golden files.
  Column F instead has `ceterms:learningOpportunityType`.

  > **Answer:** I'm not seeing Learning Type in the Phase 1 Extraction CSV, so tell me where you got that from.
  >
  > **Note (Claude):** Learning Type is not on the Phase 1 Extraction tab. It comes from two other places:
  > - The sheet's **Course** tab, row 4, in the Required Properties block. Its Term is blank, and its specification
  >   says "Provide one of: Learning Program, Course, or Learning Opportunity".
  > - The Studio itself: `model.PROPERTIES` has `("Learning Type", None)` (`model.py:32`). Every catalog has a
  >   constant Learning Type rule today.
  >
  > Whether it stays is A1.4.

---

## Part A — Questions for you

### A1. Which labels, and what they mean

1. **Exactly which rows become rules?** All 33 column F labels, including Content Description, whose status isn't
   Include?
   *Default: all 33, because column F is the list. Content Description is included and flagged "status blank in the
   sheet". The rows without a label are left out: Life Cycle Status Type, Language and the `LearningOpportunityProfile`
   rows. Life Cycle Status Type and Language stay as they are today.*

   > **Answer:** We decided to include Content Description. The rest of the default sounds good.

2. **Is the sheet the source of truth from now on?** Should the Studio read the list from a checked-in file that
   copies column F (so a new row in the sheet means a new rule after a re-sync), or is the list typed into the code
   once?
   *Default: a checked-in `properties.csv` (or `.json`) built from the tab, which replaces `model.PROPERTIES`.
   `golden-datasets properties sync` re-reads the sheet on demand. The Studio never reads Google Sheets at run time.*

   > **Answer:** Yes, a checked-in file that copies column F. A new row in the sheet means a new rule after the
   > re-sync. We want to pull from the sheet, and as the sheet updates, we want to be able to update the app easily.

3. **Do we fix the sheet's typo?** `targetLearningOpporunity` vs `ceterms:targetLearningOpportunity`.
   *Default: the Studio uses the correct CTDL spelling and records the sheet's spelling as an alias. You tell the
   sheet's owner.*

   > **Answer:** Yes, let's fix the typo. Or I can fix it in the sheet right now.
   >
   > **Note (Claude):**
   > - The Studio uses `targetLearningOpportunity` either way.
   > - If the sheet is fixed before the first sync, no alias is needed. [`phase1-extraction.csv`](phase1-extraction.csv)
   >   is then re-read.
   > - Until the sheet is fixed, `properties sync` corrects the spelling and says so.

   > **Answer (second pass):** I've already fixed the typo.
   >
   > **Note (Claude):** The sheet was re-read, so no alias is needed. The fix dropped the `ceterms:prerequisite>`
   > prefix on row 24; see D10.

4. **Learning Type vs `learningOpportunityType`.** Is the new `learningOpportunityType` rule the CTDL home of what
   Learning Type does today (constant `Course`)? If so, should Learning Type go?
   *Default: they are separate. Learning Type stays as it is (required in the template, not written to files).
   `learningOpportunityType` is a new rule that starts with no definition.*

   > **Answer:** Grill me on that. I don't know right now.
   >
   > **Note (Claude):** See D7.

### A2. Order on the Rules tab

5. **Which fields are "required"?** The Course tab's Required Properties block or something else? Does Coded Notation
   count, because it's the course key?
   *Default: required means the Course tab's block that has a rule: identifier, Learning Type, name, description,
   subjectWebpage, lifeCycleStatusType and inLanguage. Coded Notation is listed first among them, as the course key,
   and the Required group is labelled.*

   > **Answer:** The required fields are identifier, Learning Type, name, description, subjectWebpage,
   > lifeCycleStatusType and inLanguage. And Coded Notation? Grill me on that.
   >
   > **Note (Claude):** The Coded Notation half of this question is D1.

6. **What does "annotated before" count?** Expert verdicts only (`human`), or any annotation (engineer ✓ / ✗,
   comments, questions)? In this catalog, or across all catalogs?
   *Default: human-reviewed values in the open catalog. A field with no reviews there falls back to the number of
   catalogs where it has any, then to the sheet's order.*

   > **Answer:** Expert verdicts only: human review only. Count across all catalogs.
   >
   > **Note (Claude):** The order is the same in every catalog, then. A field's count is the sum of human-reviewed
   > values for that label over all six catalogs.

7. **Is the order recomputed live,** so a field moves up as soon as someone annotates it? Or is it fixed per
   ruleset version?
   *Default: live, but only between groups. Within "Other fields" the order is human-reviewed count (descending),
   then sheet row. A field never jumps while you're on it; the new order applies on the next load.*

   > **Answer:** Yes, we can do live if it's not too disruptive for the user. We can try that and fix it later.

8. **Nested labels in the list:** shown under their parent (`creditValue` › min / max / unit type), or as flat rows
   in their own place?
   *Default: under their parent, indented, as one block that sorts by the parent's annotations. Each child is still
   its own field rule with its own status, Approve and annotations.*

   > **Answer:** We shouldn't show that as a flat value, a flat label with the caret. We don't want to show
   > hierarchy through nested values in the sidebar.
   >
   > **Note (Claude):** Read as: neither the raw `>` path nor an indented tree in the rule list. Each child is a
   > row with its own readable name. That changes this default; D9 checks the reading and asks which name to show.

9. **33+ rules is a long list.** Should there be collapsible groups ("Required", "Other fields", "Not started")? A
   filter for "has a rule yet"?
   *Default: three groups: **Required**, **Annotated**, and **Not started** (no definition yet). The last one is
   collapsed by default.*

   > **Answer:** Collapse them into Required, Other fields and Not started. Maybe add a search input, so you can
   > search for the field you're looking for.
   >
   > **Note (Claude):** The groups are **Required**, **Other fields** and **Not started**. Other fields is ordered
   > by human reviews (A2.6), so the "Annotated" group from the default goes. A search box filters all three groups.

### A3. Nested values: what a child label is

10. **What is a child rule's value?** Take `ceterms:creditValue>schema:minValue` on "3–5 units": is it a field rule
    that extracts "3" by itself, in the same course record, whose path says where the value goes in CTDL?
    *Default: yes. A child is an ordinary field rule (same locator, its own selector / regex) whose `ctdl_property`
    is the full path `ceterms:creditValue>schema:minValue`. The Studio stores it flat.*

    > **Note (Claude):** Settled by the answer on "Nothing in the Studio is nested": flat fields, with the path as
    > the name.

    > **Answer:** Yes.

11. **A parent that has children (`creditValue`, `prerequisite`, `recommends`, `estimatedDuration`): is it a rule
    with its own value?** The sheet lists `ceterms:creditValue` as Single, with sample `3`, next to its three
    children.
    *Default: yes, the parent is also a rule. For credits it holds the single value (`schema:value`) when the page
    prints one number. For condition and duration profiles it holds the verbatim text of the whole block. That text
    is often the easiest thing to find on a page, and the children are carved out of it.*

    > **Answer:** If it's obvious that an extracted value maps to a specific child, it goes to that child. If it
    > isn't obvious, the whole paragraph can go to the parent, and we'll map it to the child values in the
    > transformation phase.
    >
    > **Note (Claude):** Every parent is a rule. It holds the whole text when the parts aren't clear, and children
    > hold the parts that are. A course can have both.

12. **Values we "can't extract directly from a web page".** Some children are implied, not printed. Examples: a
    `creditUnitType` of "Semester Hours" when the page just says "3 units", or `alternativeCondition`. How should those
    work? Are they constants, `map`s from text, or values only a person can enter?
    *Default: three ways, all as rules. **constant**: a fixed value per catalog, `location: null`, which the scorer
    skips as implied (same as `inLanguage` today). **map**: from printed text to a CTDL concept, with a location.
    **Human-entered on a row**: allowed, and kept as an annotation that the next rule version must reproduce. The
    Rules tab says which kind each value is.*

    > **Answer:** Get as close as you can to the correct values. They don't need to be the CTDL vocabulary values
    > exactly. We'll map any value extracted from a web page to the CTDL schema in the transformation step. Right
    > now we're only focusing on extraction: extracting a value that is seen on a page and assigning it, as closely
    > as we can, to the labels that represent CTDL items. The transformation step turns that into the right values
    > later.
    >
    > **Note (Claude):** Field rules extract the page's own words ("3 units", "Online"). There is no `map` to CTDL
    > concepts for vocabulary fields and no per-catalog constants for implied values. A child that isn't printed has
    > no value, and its text stays in the parent (A3.11).

13. **Repeating profiles.** A course can have several prerequisites, each with its own `description` /
    `targetLearningOpportunity`. How do children of the same profile stay together?
    *Default: every value of a child carries a `group_index` (0, 1, …) beside `value_index`, from a shared "repeat"
    selector on the parent rule. Records with one profile (most credits) always use index 0.*

    > **Answer:** That's a transformation concern too. We want to be able to know that a course has prerequisites.
    > When we work on transformation, we'll collect all the values that are related and do the final mapping there.
    > It's out of scope for this work.
    >
    > **Note (Claude):** No `group_index` and no shared "repeat" on parents. Several prerequisites are several
    > values of the same rule (A3.14). Pairing a child with its profile is left to transformation.

14. **Multiple values in general** (keyword, subject, deliveryType…): one rule giving a list, or one value joined
    with `|` as in the bulk-upload sheet?
    *Default: a list. A field rule can say `multiple: true` and then gives one match per element (`value_index` 0…n).
    The golden files hold one field per value, and the upload format is left to the exporter.*

    > **Note (Claude):** D5 asks this again in plainer terms.

    > **Answer:** Default to a list, and yes, we can say `multiple`. I need an example of what this actually means,
    > so grill me on it.
    >
    > **Note (Claude):** D5 now has a worked example.

### A4. The golden dataset

15. **How do nested values look in the golden files?**
    *Default: still flat fields, one per leaf, with `ctdl_property` set to the full path
    (`ceterms:creditValue>schema:minValue`) plus a `group_index`. Today's files, lineage and `tree_pages` keep
    working.*

    > **Note (Claude):** Settled by the answer on "Nothing in the Studio is nested". The nested CTDL view that was in
    > the first draft of this default is dropped.

    > **Answer:** Still flat fields, one per leaf, with the CTDL property set to the full path plus a group index.
    > Sounds good.
    >
    > **Note (Claude):** A3.13 then puts grouping out of scope, so `group_index` is dropped. The files keep
    > `value_index`, which already orders several values of one field. Research checks that nothing else needs a
    > group index (R4).

16. ~~**Who fixes xtra-cli's three names for credit min / max?**~~
    > **Note (Claude):** Dropped. xtra-cli is out of scope.
    > - The Studio writes the column F names as they are. There is no alias table for xtra's names.
    > - The Evals tab keeps scoring the seven columns it scores today.
    > - A new column scores as "—" until xtra writes the same names. That is outside this work.

    > **Answer:** Yes, xtra-cli is out of scope.

17. **Does a new column join the golden dataset the way the old ones did?** That means a column is published only
    when its rule is approved, and the home table shows the new columns (most as "—" for now).
    *Default: yes to both. The home table shows Required columns, then any column with at least one human review.
    The rest are behind "Show all 33".*

    > **Answer:** Yes to both. That sounds good.

### A5. Where the first rule versions come from

18. ~~**Seed the new rules from v2?**~~
    > **Note (Claude):** Dropped. review-ui-v2's rules are out of scope, so every new label starts as a stub (no
    > definition, status **Not started**).

    > **Answer:** Correct. We're dropping it. Review UI's rules are out of scope.

19. **How does a stub get its first definition?** Through the usual loop (annotate rows → Improve with Claude →
    `rule publish`)? A stub has no rows to annotate.
    *Default: the Improve prompt covers stubs: "write a first version of this rule". Claude reads saved pages through
    the CLI and drafts it, and the scorecard shows how many courses it finds. Until then, the Records tab can show
    the field as an empty column you can annotate (select the text on the page, the same as ✗ missing).*

    > **Answer:** Through the usual loop: annotate rows, Improve with Claude, `rule publish`. Good.

20. **One ruleset version for all the new rules,** or a version each time a group of labels is added?
    *Default: one ruleset version per catalog that adds every stub at once. After that, rules version as they do
    today.*

    > **Answer:** Sure. You can grill me on that one.
    >
    > **Note (Claude):** See D8.

### A6. Scope and process

21. **The spec's scope changes.** §2 keeps requisites and credit units out of scope, and spec §4.4 says one page
    rule, one locator and 8 field rules. Is updating the main spec part of this work?
    *Default: yes. This folder's spec says what changes. The main spec gets a short note at each place it no longer
    holds, as was done for Evals.*

    > **Answer:** Yes, we can update the spec's scope.

22. **Which catalogs?** All six, or AVC first?
    *Default: AVC first, for every step. The other five get the stubs at the same time, so the Rules tab looks the
    same everywhere.*

    > **Answer:** Let's do all six.

23. **Where does the work happen?** I've checked out `origin/golden-dataset-studio` locally as
    `golden-dataset-studio-local`. Should this go on its own branch (for example `golden-dataset-studio-field-rules`)?
    *Default: its own branch off `golden-dataset-studio`. Nothing is committed until you've reviewed it.*

    > **Answer:** A new branch off Golden Dataset Studio. Yes, call it local. We'll merge it into Golden Dataset
    > Studio when we're ready.
    >
    > **Note (Claude):** The branch is `golden-dataset-studio-local`, off `origin/golden-dataset-studio` at
    > `5dbb778`.

24. **How far does this QRSPI go?** As before: questions, research, spec, plan, then a build prompt?
    *Default: yes. No building in this process.*

    > **Answer:** Let's do QRS: questions, research, spec.

---

## Part B — Facts I'll find out myself (research phase)

- B1. **What each label looks like on the saved pages** of the five catalogs:
  - which labels are printed, which are implied, and which are absent;
  - for the Multiple ones, how many values a course usually has;
  - a sample of real text for each nested child (credit ranges, prerequisite blocks, durations).
- B2. **CTDL check:** for each column F path, confirm the term and its range against the CTDL schema, including
  `schema:minValue` and the `targetLearningOpportunity` spelling. Also check which concept schemes the controlled
  vocabularies use.
- B3. **Everything that reads `model.PROPERTIES` / `PROPERTY_ORDER` / `CTDL_TERM` / `IN_SCOPE` / `NOT_IN_STUDIO`**,
  and what has to change in each place to load the list from a file instead.
- B4. **What the engine needs for `multiple` and `group_index`:** `select` vs `select_one`, the
  `MATCHES` / `GOLDEN` / `LINEAGE` Parquet schemas, comparing two versions, verdict re-attachment, and annotations
  on multi-piece values (`expected.segments`).
- ~~B5. v2's credit / non-credit rules.~~ Dropped: review-ui-v2 is out of scope.
- ~~B6. xtra's scorer on `>` paths.~~ Dropped: xtra-cli is out of scope. Research only checks that the Evals tab
  still works for the seven columns when the golden files hold `>` paths.
- B7. **Rules tab and home table with 33+ rules:** list length, the selected-rule default (`course-description`),
  how the tour and screenshots are affected, and how the Evals tab reads per-column data.
- B8. **The cost of 33 rules:** extraction time and Parquet size for WVU (22k courses) with four times the field
  rules.
- B9. **Syncing from the sheet:** read the tab through a CSV export link, or from a downloaded file? Who can read the
  sheet, and what `properties sync` prints when a row is added, removed or renamed.

> **Answer:** These all look good.
>
> **Note (Claude):** B4 loses `group_index` (A3.13). B1 no longer needs CTDL vocabulary matches, only the page's own
> words (A3.12).

---

## Part C — Work streams and order (first guess)

| # | Work stream | Depends on | Can start now? |
|---|---|---|---|
| F1 | **Property list from the sheet:** a checked-in `properties.csv` from column F (column E where F is blank for a required field), with path, label, profile, Single/Multiple, required and vocabulary; it replaces `model.PROPERTIES`; `properties sync` | A1, D2, B2, B3, B9 | **Yes** |
| F2 | **Rules tab order:** Required / Annotated / Not started groups, nested children under their parent, live human-review counts | F1, A2, D3, D4 | After F1 |
| F3 | **Stubs:** one ruleset version per catalog that adds every new label without a definition; the Improve prompt handles stubs | F1 | After F1 |
| F4 | **Engine: `multiple` and `group_index`**, Parquet schema, compare, verdicts, Records tab | B4, D5 | **Yes**, alongside F1 |
| F5 | **Golden files for paths:** flat `>` fields plus `group_index`, the home table's columns | F1, F4 | After F4 |
| F6 | **Spec, tour, screens and `check` rules** | each stream | With each stream |

Order: **(F1, F4) → F2, F3 → F5**, with F6 alongside. F1–F3 alone already meet the prompt's main request: every
label as a field rule, in the right order. F4–F5 are what let the nested and multiple-value labels be reviewed
properly.

> **Answer:** The work streams look good for now.
>
> **Note (Claude):**
> - F4 is now `multiple` only, with no `group_index`.
> - F5's files are flat `>` fields with `value_index`.
> - F2's groups are Required, Other fields and Not started, plus search.

---

## Part D — Second pass of questions

These cover the points Seth asked to be grilled on. Each one first explains the point in plain terms, then asks.
Until it's answered, research works from the **assumption**.

**D1. The course key (Coded Notation).**
- The Studio needs one value that says "these rows are the same course". It needs it to pair a course in rule
  version 1 with the same course in version 2, and to keep an annotation on the right course after a rule changes.
  That value is the course code, for example `ENG 101`, which is the Coded Notation field. In the code,
  `rulesets.first_settings` picks the course key rule by finding the rule labelled "Coded Notation".
- Coded Notation isn't required by the template, but if its rule is wrong, every other field's annotations can land
  on the wrong course.
- **Should Coded Notation sit in the Required group,** at the top, because everything else depends on it? Or should
  it sort with the other fields?

*Assumption: first in the Required group, marked "course key".*

**D2. One hard-coded list.**
- Today the eight fields the Studio knows about are typed into the code as one list (`model.PROPERTIES`). It holds
  each field's name and its CTDL term, in display order. Every part of the Studio reads that list. A field not on it
  doesn't exist for the Studio: v2 import drops it, it gets no column on the home table, and it is never written to
  the golden files.
- A1.2 replaces the list with a file synced from the sheet. The question is what goes in that file besides column F.
  Learning Type, Life Cycle Status Type and Language are on today's list but not in column F.
- **Is the file column F plus those three,** so nothing the Studio does today disappears? Or column F only?

*Assumption: column F, plus the required fields that have no label, named by their column E shorthand
(`ceterms:lifeCycleStatusType`, `ceterms:inLanguage`), plus Learning Type as a Studio-only row with no CTDL term.*

**D3. Rules tab order, and "required".**
- The order of the field rules on the Rules tab comes only from where each field sits on the hard-coded list (D2).
  A field that isn't on the list goes to the bottom. Nothing in the code marks a field as required. The word
  appears only in the spec's prose.
- To put required fields first, the Studio has to be told which ones they are.
- **Should the synced file have a `required` column,** filled from the Course tab's Required Properties block? Or do
  you want to mark required fields some other way, for example by hand in the file or in the UI?

*Assumption: a `required` column, filled by `properties sync` from the Course tab's Required Properties block.*

> **Note (Claude), second pass:** A2.5's answer names the same seven fields as that block, so the assumption gives
> what Seth asked for. What's still open is whether the sheet or the checked-in file is where "required" is decided.

**D4. What "annotated before" can order today.**
- Seven fields have human reviews in every catalog that has any reviews, for example 14 each in AVC. The 28 new
  labels (column F's 33 minus the five the Studio already has) have none anywhere, because they don't exist yet.
- So on day one, "annotated before" puts the old fields above the new ones, and all the new ones tie at zero. The
  ordering only gets interesting once people start reviewing new fields.
- **How should the new labels be ordered while they tie?** By the sheet's row order, alphabetically, or by how often
  the field turns up on the catalog's pages (B1)?

*Assumption: the sheet's row order. As soon as a new field gets its first human review, in any catalog (A2.6), it
moves above the fields nobody has reviewed. All of this happens inside **Other fields** (A2.9).*

**D5. One value per field, and lists (`multiple`).**
- **One value per field.** Today a field rule finds one piece of text per course, for example one description. Some
  labels naturally have several values. A course can have several keywords, subjects or prerequisites. The rule has
  to be able to return a list.
- **Fixed vocabularies:** settled by A3.12. A rule keeps the page's own words ("Online", "Hybrid"). Turning them
  into Delivery Type's allowed values (Online Only, Blended Delivery, …) is transformation, later.
- **A worked example.** A course page shows:

  > **BIOL 101 — Intro to Biology** · Subjects: Biology, Life Sciences · Offered: Online, In Person ·
  > Prerequisites: MATH 090; ENGL 100 or placement.

  **Today, one value per rule.** The Subjects rule can only return one string. Either it picks the first element
  (`Biology`, so Life Sciences is lost), or it takes the whole line as one value (`Biology, Life Sciences`). An
  annotator who marks it ✗ can only fix it as one string.

  **With `multiple: true`, the rule returns a list:**

  | Rule | `value_index` 0 | `value_index` 1 |
  |---|---|---|
  | `ceterms:subject` | Biology | Life Sciences |
  | `ceterms:deliveryType` | Online | In Person |
  | `ceterms:prerequisite` | MATH 090 | ENGL 100 or placement |

  - In the golden file, that's two `ceterms:subject` fields on the course, one per row.
  - On the Rules tab, each item is its own row, and each row can be marked ✓ or ✗ on its own. An annotator can say
    "Life Sciences is right, but you missed Health", and add a missing item by selecting it on the page.
  - The alternative is the bulk-upload sheet's style: one value, `Biology | Life Sciences`. It's simpler to build,
    but one wrong item makes the whole value wrong, and someone has to split it later.
- **Is it right that a `multiple` rule returns a list,** one golden field per item, each reviewed on its own?
- **How does a rule split a list?** By one match per element on the page (each `<li>`), or by splitting one piece
  of text on a separator ("," or ";")? Or both, per rule?

*Assumption: yes to the list. A rule can do either kind of split, and says which in its definition. Which one each
catalog needs is research (R1).*

**D6. Single or Multiple where the sheet is blank.** Delivery Type Description, `hasPart`, `recommends` and the
ConditionProfile children have no Single / Multiple value in the sheet.
*Assumption: `hasPart`, `prerequisite` and `recommends` (and so their children, one per profile) are Multiple;
Delivery Type Description is Single. `properties sync` reports any row left blank.*

**D7. Learning Type vs `ceterms:learningOpportunityType`** (A1.4).
- **Learning Type** answers "what kind of thing is this?": Learning Program, Course or Learning Opportunity. The
  bulk-upload format uses it to pick which CTDL class to publish (`ceterms:Course`, …), so it has no CTDL property
  of its own. In the Studio it's a constant rule that says `Course` for every record, because the Studio only
  extracts Courses.
- **`ceterms:learningOpportunityType`** is a real CTDL property. It's a finer type, chosen from a vocabulary, that
  sits on the record itself. Research confirms its vocabulary (R2). It reads like "Lab", "Seminar" or "Workshop".
  Column F lists it as a flat label with nothing in Single / Multiple.
- So they are different things: one picks the class, the other describes the course.
- **Keep both?** Learning Type stays the constant `Course` rule (required, never written to the files), and
  `learningOpportunityType` is a new rule that extracts whatever finer type the page prints.

*Assumption: keep both, as described. Research checks what pages actually print for it (R1, R2).*

**D8. One ruleset version for all the new rules** (A5.20).
- Every change to rules makes a new **ruleset version** (v4, v5…). A ruleset version is the full list of rules and
  their own versions at that moment. The Studio reruns it over every page, and **Compare** shows what changed since
  the previous version.
- Adding 28 empty rules changes no values, because a stub finds nothing. So the question is only how the history
  reads:
  - **One version per catalog that adds all 28 stubs.** One line in the history ("v4: added 28 field rules from
    the Phase 1 sheet"). Compare v3 → v4 shows no value changes.
  - **One version each time the sheet adds rows** (`properties sync`). Same, later: every sync that adds rows makes
    a version that adds just those stubs.
  - **No version at all until a stub gets a definition.** The stub shows on the Rules tab straight from the synced
    file, and joins a ruleset version only when its first definition is published. That's fewer empty versions, but
    the rule list is no longer exactly "the rules in the current version".
- **Which one?**

*Assumption: the first, for the initial 28, and the second for later syncs. Every sync that adds rows makes one
version that adds those stubs, so the rule list always equals the current ruleset version.*

**D9. How nested labels look in the rule list** (A2.8).
- The answer was: not the raw `>` path, and not an indented tree. My reading is that each child is just another
  row in its group, with a readable name. The question is which name.
- The sheet's column D (CTDL Property Label) has names for some children: "Credit Unit Min Value", "Exact
  Duration". The ConditionProfile children have none. For those, the name can be built from the parent and the
  child, for example "Prerequisite: Description" or "Recommends: Target Learning Opportunity".
- **Is the reading right?** And should a child's row show its parent anywhere, for example as small grey text under
  the name ("in Credit Value") or in the tooltip, so "Description" under Prerequisite isn't confused with the
  course's Description?

*Assumption: the reading is right. The name is column D, or "Parent: Child" where D is blank. The `>` path shows
only in the rule's detail pane, beside the CTDL term.*

**D10. Two things in the re-read sheet.**
- **Row 24's column F is now `ceterms:targetLearningOpportunity`**, without `ceterms:prerequisite>`. Row 28 kept
  `ceterms:recommends>`. Read as it is, row 24 is a new flat label on the course, and the prerequisite profile has
  only two children. Was the prefix lost while fixing the typo?
  *Assumption: yes. The Studio treats it as `ceterms:prerequisite>ceterms:targetLearningOpportunity`, and
  `properties sync` warns until the sheet says so too.*
- **Content Description's xTRA Status is still blank.** A1.1 says to include it anyway. Should `properties sync`
  ignore xTRA Status altogether, so that any row with a column F label is a rule? Or should it read "Include", so
  that the sheet has to be fixed?
  *Assumption: any row with a column F label is a rule, and a blank status is reported as a warning.*
