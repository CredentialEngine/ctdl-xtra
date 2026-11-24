# Approved: LearningProgram, waves 1–2

This file lists everything Eric approved in waves 1 and 2 (2026-11-23 and 2026-11-24). It is kept for implementation
and is not repeated in later review waves. Pictures are in `page/screens/`. Where an item came with a tweak, the
tweak is noted.

Sources:
- [`answers-pass1.md`](answers-pass1.md)
- [`answers-pass2.md`](answers-pass2.md)
- Eric's voice review of wave 2 (2026-11-24)
- [`03-spec-draft.md`](03-spec-draft.md) and [`04-spec-wave2.md`](04-spec-wave2.md), which have the detail.

## Classes, properties and identifiers

1. **Classes.** Course was the first class and LearningProgram is the second. More will follow, five to start with.
   Every choice made here is the pattern for the next class.
2. **Source of truth.**
   - The sheet "xTRA: Learning Opportunity BU Template", tab *Learning Program Properties*, is synced into
     `properties/learningprogram.csv`. It is never read live.
   - `properties sync --class X` reads the `<X> Properties` tab, so a new class needs a new tab, not new code.
   - Phase comes from the sheet's xTRA Status column.
   - Issue #415 is ignored.
3. **Three tiers for every class.**
   - Required (CTDL) comes first, then the rest of Phase 1, then Phase 2.
   - Phase 2 works the way it does for Course: a property with no rule is listed as "not started".
   - Rules can be added without new code.
4. **Course gets the tiers too.** Coded Notation moves from Required into Phase 1.
5. **Record key.**
   - For every class, the record key is the External Identifier (issue #368). That is the code the resource prints,
     or else `{type}-{normalized name}`, at most 100 characters.
   - `course_key` becomes `record_external_identifier` in every file and API.
6. **Names and slugs.**
   - The class is written `LearningProgram`, with no space.
   - Slugs are `course` and `learningprogram`.
   - Rule ids carry the class: `learningprogram-name`, `course-name`. Merging rules across classes may come later.
   - Course rules may serve as inspiration for program rules.
7. **What a program is.** Minors, concentrations, certificates and tracks each count as a program. A page that lists
   several programs gives several records.
8. **Available At** is verbatim text, one value per location.
9. **Language** is never read from `<html lang>`, because that is the website's language.
10. **Course lines on program pages.** These rules were history only, and they were dropped in ruleset v2. Remove the
    stale `course_key_rule` setting during the migration. (Eric: "I trust your judgment.")

## UI

11. **Class menu in the top bar.**
    - It sits after the catalog chip (`m4-class-menu.png`) and lists each class plus **All classes**.
    - It governs every tab to its right and the AI button.
    - The URL carries it: `#/c/<catalog>/<class>/<tab>`, with `all` for All classes.
    - Today's links that have no class stop working.
12. **Home, golden view** (`w2-home-classes-menu.png`, `w2-home-scrolled.png`).
    - A multi-select *Classes* menu, with the ticked classes' columns side by side under class headings, in the three
      tiers.
    - The table scrolls sideways. That already works today.
    - A catalog with no programs says "Not a LearningProgram source".
    - The layout with one row per catalog and class is dropped.
13. **Rules tab** (`m3-rules-learningprogram.png`, `w2-rules-id-card.png`, `w2-rules-id-generated.png`).
    - **Groups:** Page rules, Record locators, Required, Phase 1, and Phase 2 (folded).
    - **Record key column:** no tags under the rows. The key gets a faint dotted underline. On hover, a card shows the
      identifier, its source on the page, and the page rule with its URL pattern.
    - **Formatting tweak (from wave 2):** quoted page text and patterns are set as inline code, like `In-Person Major
      Code: 2166` and `/graduate/*`.
    - **Generated identifiers** are grey.
14. **Rules, All classes** (`m5-rules-all-classes.png`). There is a heading per class with its counts, and its groups
    are folded under it.
15. **AI runs** (`w2-run-one-class.png`, `w2-run-all-classes.png`).
    - **One class at the top:** the dialog names the class and has no switch.
    - **All classes:** one scrolling list with a heading per class, so you can tick rules in several classes.
    - **Locks:** a run locks only the classes it has a ticked rule in, so each catalog and class has its own lock.
16. **Records** (`w2-records-lp.png`, `w2-records-multi.png`, `w2-records-all.png`).
    - **List:** each row shows the program name with its identifier under it. Search matches either.
    - **No per-value page line, and no "found on" line,** unless the program's values come from more than one page.
      Then the heading says "Values from N pages", each card names its page, and the pane has a tab per page.
    - **All classes:** a folding heading per class.
17. **Datasets** (`w2-datasets-lp.png`, `w2-datasets-all.png`).
    - **Per class:** golden and silver datasets. Silver versions are numbered per class, so LearningProgram starts at
      ruleset-v1.
    - **All classes:** a section per class.
    - **Publishing:** one golden version per catalog and class. Course-only UI is hidden for other classes.
18. **Evals** (`m8-evals-green-bottom.png`, `w2-evals-lp.png`, `w2-evals-all.png`).
    - Matches sit at the bottom of each bar (`.evx-stack` uses `column-reverse`).
    - One class shows that class's bars. All classes shows one row of bars per class.

## CLI, storage, migration

19. **`--class`** is required on commands that read or write one class's data, and refused on the others. It has no
    default.

    | Takes `--class` | Doesn't |
    |---|---|
    | `properties sync / list / apply`, `extract`, `check`, `rule …`, `ruleset revert`, `pages sample`, `run …`, `prompt`, `golden publish / backfill`, `score` | `init`, `assets fetch`, `crawls list / add`, `pages get`, `sync`, `serve`, `hash-password`, `sql` (it gets a `class` column) |

    `import-v2` is removed.
20. **Studio storage.**
    - Catalog level: `<catalog>/<class>/{rules, rulesets, annotations.jsonl, agent-runs, publish.json}`.
    - Crawl level: `<catalog>/<crawl>/{pages.parquet, assets/, <class>/rule-runs/}`.
    - `extractions/` becomes `rule-runs/`.
    - One properties file per class.
21. **xtra-cli owns extraction and scoring data.**
    - The Studio reads crawls, extract outputs and scores from wherever xtra-cli writes them, and stops keeping copies
      under its own folder.
    - The proposed layout is `xtra-cli-output/<catalog>/<crawl>/extract/<run-id>/…`, with scores under each run, plus
      `xtra-cli-output/scores/<class>/<property>/<catalog>.jsonl`.
    - The Studio gets its own container.
    - xtra-cli changes themselves stay out of scope. Eric: the Evals tab and other tabs "would read from that location
      in Azure".
22. **Migration.** A one-time script, run once per root:
    - moves today's data under `course/`;
    - rewrites `course_key` → `record_external_identifier` in every file, including `annotations.jsonl`. The old files
      are kept as `*.legacy`;
    - removes stale settings;
    - moves extract outputs and scores to the xtra-cli paths.

    The app reads only the new format.
23. **Scoring by class.** Records are filtered by class before they are paired.
24. **Tests.** Outside-in tests drive the real CLI and HTTP API (the `test_golden_versions` fixture and `minicat`) for
    a program catalog as well as a course catalog.

## Added from wave 3 (approved 2026-11-24)

25. **The running notes.**
    - The Studio becomes where scores live. They're computed by xtra's own scorer when a golden version is published
      or xtra writes a new extract output.
    - Scores are written to xtra-cli's location in Azure, and the Studio reads them from there.
    - Nobody pastes score tables anymore.
26. **Four score views**, picked by two scopes, Catalogs (All or one) and Properties (All or one):
    - **All catalogs, all properties:** a *Rows: Catalogs | Properties* switch picks what the rows are.
    - **One catalog, all properties.**
    - **All catalogs, one property.**
    - **One catalog, one property over time:** links into that catalog's Evals tab at that property.

    Each view's rows open the next one down. Every view:
    - stacks the classes as separate tables, one above the next;
    - gives each row two lines, Golden and Silver;
    - draws each cell as a stacked bar in the Evals colours (exact, partial, unsure, wrong, missing), with exact and
      partial as separate numbers;
    - has a *Bars | Numbers* switch, where Numbers gives one count column per outcome with headings in matching
      colours;
    - shows the last 7 scores as stacked bars with axes.

    There are no issue numbers on screen, and no breadcrumb with a second dropdown. (`w3-scores-*.png`)
27. **The 90% target is golden exact.** Partial is shown beside it, never added to it.
28. **History bars** show the last 7 scores, each marked with what triggered it: a golden publish or a new output.
29. **Property status** (*Needs review* / *Done*) moves into the Studio.
30. **Wave 3 tweak: the 90% line.** Every horizontal bar gets a clear dotted vertical line at 90%
    (`w4-scores-*.png`).
