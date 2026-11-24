# Answers, pass 2 (Eric, 2026-11-24, by voice, tidied)

These are Eric's reactions to the wave 1 spec (`03-spec-draft.md`) and its drawing-set page.

## Decisions confirmed

- **Classes:** Course was the first class and LearningProgram is the second. More classes will follow, five to start with.
- **Source of truth:** the sheet's *Learning Program Properties* tab, for this implementation only. The Studio won't
  fetch from it live. Issue #415 is ignored.
- **Tiers:** Required (CTDL) first, then the rest of Phase 1, then Phase 2. Phase 2 works the way Course handles it.
- **Identifier, class name, values:**
  - External Identifier follows issue #368.
  - The class is written `LearningProgram`, with no space.
  - Available At is verbatim text, one value per location.
- **Rules:** each class has its own rule ids, with class-name prefixes such as `learningprogram-`. Merging rules
  across classes may come later. Course rules may serve as inspiration.
- **Programs:** minors, concentrations, certificates and tracks each count as a program for now.
- **Publishing:** one golden dataset version per catalog and class. Course-only UI is hidden for LearningProgram.
- **Course:** gets the three tiers. Coded Notation moves from Required into Phase 1. The record key becomes the
  External Identifier.
- **xtra-cli:** changes to it are out of scope.
- **Language:** don't take it from `<html lang>`. That says what language the website is in, not what language a
  course or program is taught in.
- **CLI and storage:**
  - Class slugs `course` and `learningprogram`.
  - `properties sync --class X` reads that class's tab.
  - Phase comes from the sheet's xTRA Status column.
  - The `<catalog>/golden-dataset-studio/<class>` layout is fine.
- **`--class`:** only for commands that read or write one class's data. `serve` and `hash-password` don't take it.
- **Migration:** write the scripts that rewrite files into the new format, such as `course_key` →
  `record_external_identifier`. Keep the old data for legacy. The UI reads only the new format.
- **Old links:** no backward compatibility for today's class-less links.
- **Evals and daily scores:** their own story, out of scope here, but keep planning them, especially where score files
  are written.

## Feedback on the wave 1 sheets

- **Home:**
  - Keep the columns side by side, one group per class ("really smart").
  - The class switch will get too long as classes are added, so make it a dropdown with multi-select.
  - The table needs horizontal scroll.
  - Drop the option with one row per catalog and class.
  - Keep UARK's explicit "Not a LearningProgram source".
- **Rules tab:**
  - Approved. The class dropdown in the top bar is "excellent".
  - The *External Identifier* chip under each row repeats the left column. Move the URL pattern and the identifier's
    source into a tooltip or progressive disclosure on that left column, and keep the UI minimal.
- **Top bar:** Eric is open to seeing *All classes*. That dropdown should govern every tab to its right and the AI
  button. He wants a concept of each tab under it.
- **AI run dialog:**
  - With one class chosen at the top, show only that class, with no switch in the dialog.
  - With *All classes*, show a long scrolling list so several classes can be improved at once.
- **Records tab:**
  - Drop the per-value *program page* tags and the "found on" line, unless a program's values span several pages.
  - Do they?
- **Evals tab:**
  - The green bar at the bottom is good.
  - Consider how the tab looks with several classes.
- **xtra score:**
  - A line without a y-axis means nothing. Use small bar charts with x and y axes.
  - Show the tables stacked by class.
  - Show all properties, not one at a time.
  - Show more variations, because many catalogs and many classes will break the current design.
- **Storage:** investigate where xtra-cli should write in the bucket. Extract outputs and scores belong to xtra-cli, not
  under the Studio's folder.
- **Questions:**
  - Don't reference IDs (M1, F2): give the context in each question.
  - The asks for Jared and Jeanne also need enough context to decide.
  - Show mockups for the Evals questions.
- **Course lines on program pages:** show examples. Why would course rules read program pages at all?
- **Datasets tab:** draw it.
