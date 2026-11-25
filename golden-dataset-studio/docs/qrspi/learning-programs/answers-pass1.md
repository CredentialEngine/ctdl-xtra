# Answers, pass 1 (2026-11-23, by voice)

Eric's answers to [`01-questions.md`](01-questions.md), tidied for readability. Transcription noise is left out.
Questions marked **→ Jared/Jeanne** go on the follow-up list for the SMEs. Studio goes ahead with the answer given
here until they reply.

## Framing

- Learning Program is not "the first of five classes". Course was the first class; Learning Program is another class.
- The sheet is the source of truth. Issue #415 is ignored for property lists.
- The `course` hardcoding is a concern. There should be outside-in tests, agnostic to those details, so that the
  refactor can show it hasn't broken existing behaviour. (Research checks which tests exist.)

## Part A

- **A1.** Minimum = every Phase 1 row (check the count; it should be about 13). CTDL "required" is technically
  different, so a Required set is fine, **as long as the rest of the Phase 1 fields come right after it.**
- **A2.** Three tiers: Required, the rest of Phase 1, Phase 2.
- **A3.** Do whatever is already done for courses. If courses have rules for Phase 2 properties, do the same; if not,
  Phase 2 stays out of scope. Course may need rearranging into the three tiers too. Build it so rules can be added
  later without fuss.
- **A4.** Find the GitHub issue where the team discusses **external identifiers** and use what they decided.
  **→ Jared/Jeanne**
- **A5.** Follow the sheet (no Coded Notation). **→ Jared/Jeanne**
- **A6.** Follow the sheet (no Prerequisite). **→ Jared/Jeanne**
- **A7.** `LearningProgram` (no space). **→ Jared/Jeanne**
- **A8.** Verbatim text, one value per location; Place is built at transformation. **→ Jared/Jeanne**
- **A9.** Separate rule ids per class (`program-…`). Consolidating rules can be explored later.
- **A10.** Drawing inspiration from course rules is fine. Doubtful many will carry over; Eric doubts programs have
  credit values, but if they do, fine.

## Part B

- **B1.** Unknown. **→ Jared/Jeanne.** Keep a running section of follow-up asks for them.
- **B2.** Yes for now. **→ Jared/Jeanne**
- **B3.** Yes, probably one page with many records, as courses already work.
- **B4.** Eric thinks the programs are already crawled. Check by looking inside the crawls.

## Part C

- **C1.** Wants mockups of several views. Three needs:
  1. one class, all its properties, **all catalogs side by side**;
  2. one catalog, **all classes** and all their properties;
  3. **all classes and all properties for all catalogs**.
  Experiment with a few views to find the most ergonomic.
- **C2.** Show both (one row per catalog; one row per catalog × class).
- **C3.** Program name leads the row, URL as tooltip. Good starting point.
- **C4.** Show both (score per catalog; per catalog × class).
- **C5.** Course runs could already pick one rule, a subset, or all. The same philosophy may apply to classes. Show a
  mockup; the simplest approach is one class at a time by default.
- **C6.** Yes, one golden version per catalog × class.
- **C7.** Yes, hide course-only parts when the class is LearningProgram.
- **C8.** `LearningProgram`, spelled out, no space.

## Part D

- **D1.** Yes: a class folder under each catalog, and migrate existing data into it.
- **D2.** Yes, `--class` on every command, but **no default**. It must be explicit; every caller gets updated.
- **D3.** One properties file per class.
- **D4.** Rename `course_key` to **`record_external_identifier`**, following Jared's "external identifier" term.
- **D5.** It should score every class. Check whether it does yet.
- **D6.** xtra-cli changes are out of scope for now.

## New: Evals and daily scores

- The Evals UI has to accommodate multiple classes; how is open.
- There is a Google Sheet where daily scores are published. Eric would rather view them in the Studio. Find the
  sheet and think about how the Evals UI could show those scores in one place.
- The green part of each score bar is at the top. It should be at the bottom, so that it grows up and to the right as
  scores improve.
- In or out of scope is undecided. Write questions about it.

## What comes next

A partial spec: answers, follow-up questions, research findings, and a first wave of mockups. **Mockups must be
pixel-perfect representations of what is recommended**, so no polish is left to guess.
