# The running-notes score reports: today's process

Research for wave 3, 2026-11-24.

**Source:** the Google Doc "CTDL xTRA Engineering Running Notes (Shared)", read in full, with its comment threads.

**Trigger:** today Jared posted in #xtra-project-flexion: "I've completed the golden sets + rules for
ceterms:inLanguage. This is ready to be scored. You can put the report in [the doc] … under the header 'In Language'."
He then added: "Same with ceterms:lifeCycleStatusType".

## The tabs

- **Collated Reports for COURSE**, headed "Evaluation Reports for Course". This is where Jared's link points: it is the
  only tab with an empty "In Language" heading.
  - There is one heading per property, with a status in brackets: "Needs Review" or "Done".
  - **Required properties:**
    - External Identifier (Needs Review): has a score table.
    - Name and Description (Needs Review): pasted notes.
    - Subject Webpage, In Language and Life Cycle Status Type: empty.
  - **Additional properties:**
    - Coded Notation (Done): a per-catalog table.
    - In Catalog, Credit Value and its parts: empty.
  - The Nov 24 agenda: "Review document tab: Collated Reports for COURSE … If yes, then we will take the same
    approach with Learning Program, Credential, etc."
- **Extraction Report - 2026.11.18:** Seth's detailed report on name, description and identifier.
- **Scoring Reports:** older raw entries in CLI-text form (Nov 12–19). Some are only screenshots.

## One property's report

**Header:** none. There is no author, no xtra-cli version or command, no golden version, and only the date in the
tab name.

**Scores:** one table per property, one row per catalog plus **All**. Identifier, verbatim:

| Catalog | Golden exact | Golden exact + partial | Silver exact | Silver exact + partial |
|---|---|---|---|---|
| AVC | 34/34 (100.0%) | 34/34 (100.0%) | 1,062/1,062 (100.0%) | 1,062/1,062 (100.0%) |
| UALR | 25/30 (83.3%) | 25/30 (83.3%) | 2,915/3,130 (93.1%) | 2,915/3,130 (93.1%) |
| CCSF | 56/69 (81.2%) | 56/69 (81.2%) | 1,751/1,927 (90.9%) | 1,751/1,927 (90.9%) |
| … | | | | |
| **All** | **191/210 (91.0%)** | **191/210 (91.0%)** | **34,549/34,944 (98.9%)** | **34,549/34,944 (98.9%)** |

**Why values are missing:** reason codes M1–M4, each with a count per property and per catalog. Each code has bold
**Cause / Fix / Assessment** bullets and linked example pages. For example: "M2 Discovery labels the page Unknown, so
it isn't read as a course."

**Mismatches:** reason codes per property, with counts:
- name uses N1–N4;
- description uses D1–D9, with an extra "Whose error" column (silver / extractor / baseline / normalization).

Each code has examples that quote the golden value and the extracted value.

**Comments on the doc:**
- **Rohit, on the "Golden exact + partial" column:** "We should not mix exact + partial in metrics… report accurately
  the partial matches independently."
- **Rohit, on the 11.17 report:** "Just make them formal columns… Let's also not generate these things in Claude. These
  should be outputs from CLI."
- **Seth:** "Creating a standard template is part of my plan."
- **Triage:** Jared and Seth discuss single mismatches ("The golden sample is correct…", "This is a course, not a
  credential").

## How it's produced

- **No command or path in the doc.** The report is assembled by hand, partly with Claude, from xtra's scorer output and
  pasted in.
- **Wishes recorded in the notes:**
  - "Track scoring in a tab until available in UI." (Nov 10)
  - "Where should we output daily scoring reports? Pasting in Google doc is manual… Automate through Argo workflows and
    integrate in UI." (Nov 19)
  - "Store scoring reports at the root level of the catalog, some kind of index." (Oct 23)
- **When it runs:** called "daily", but in practice a report is made when Jared finishes a property's golden set and
  rules, as with today's message.

## Targets

- "Set extraction accuracy target at 90%." (Jared and Rohit, Nov 20)
- "95-100% accuracy on these properties: Coded Notation, Identifier, Name, Subject Webpage/In Catalog. Description
  should probably be lower." (Jared, Nov 18)
- "If score isn't 100%, we need to document the reasons why." (Nov 19)

**Saved copies:** the full text and comments are in the session scratchpad (`running-notes.txt`,
`running-notes-comments.json`). They are not kept in the repo.
