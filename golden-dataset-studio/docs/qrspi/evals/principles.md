# Evals: principles

Eric, 2026-10-28, after using the POC ([`poc.md`](poc.md)). These replace the POC's assumptions wherever the two
disagree. Open questions are at the end. The spec that follows from them will be written once they're answered.

## Who the tab is for

- **The Studio is for domain experts** (Jared and other product people) who are building the golden dataset. The Evals
  tab shows their point of view.
- **Only engineers iterate on xtra-cli.** Product people never run `xtra extract`, in this UI or anywhere else. When
  engineers run it, the output is saved to a bucket. The Studio reads that output and never produces it.

## What the Studio writes

The Studio writes only two things:
1. **rules**, which only the Studio uses (xtra-cli never does);
2. **published golden datasets**.

So the Evals tab is a **read-only view** of:
- golden datasets, which this UI published earlier;
- xtra extract outputs, which engineers produced outside this UI.

It **can run a score** (see the open questions on where scores are kept). It **doesn't trigger extractions**. That
may come one day, but it's out of scope for now, partly because a large unmerged xtra-cli branch (Nicolas's) is in
flight and we don't want to touch xtra-cli. We keep using the extract outputs already saved.

## The shape of the data

- **Crawls are rare. Extractions are frequent.** Engineers iterate on extraction logic against a fixed crawl output, many
  times over. An eval is about an extraction from documents that were already crawled.
- **A golden dataset version is a ruleset version**, so golden datasets are browsed by ruleset.
- **Columns only grow.** The number of columns (`ceterms:` properties) in a golden dataset grows monotonically with the
  ruleset version. The latest ruleset always has the same columns as any earlier published golden dataset, or more.
- **After a new golden dataset is published, a new score is needed.** That shows whether the change to the golden
  dataset made the xtra extract output look better or worse.

## What an eval must make easy

1. **Missing:** which golden dataset records (and values) are missing from the extracted set.
2. **Not matching:** which values don't match, and how far off they are (partial ≥ 0.8, wrong < 0.8).
3. **Matching:** the values that match exactly.

The POC's bars and data explorer (property, outcome, group by, rows, the page with both values highlighted) are the
right tools for this.

## Presentation

- **One view, two scopes.** One Evals view covers **all catalogs**. A catalog's Evals tab is the same view, filtered to
  that catalog.
- **Columns are named by their CTDL term** (`ceterms:description`, not "Description"), so there's one less layer of
  translation.
- **Not crowded.** Wherever there are several of something (extract outputs, golden dataset versions), choose one from a
  searchable dropdown. Default to the latest of everything.
- **No legacy container.** The Studio doesn't mention `xtra-golden-sets-verified`. Its hand-checked values may be
  imported as Studio annotations instead (to be explored).
- **Confusing counts go.** Counts like "33 records · 75 fields" next to a baseline are moved somewhere they explain
  themselves, or removed.

## Answers

The questions of 2026-10-28 and Eric's answers are recorded as decisions in [`03-spec.md`](03-spec.md) §1.
