# S (draft, wave 3): scores, and replacing the running-notes reports

**Only what is still open.** Everything you approved in waves 1–2 is in [`05-approved.md`](05-approved.md), for
implementation. The pending asks for Jared and Jeanne are in [`asks-jared-jeanne.md`](asks-jared-jeanne.md). Neither
is repeated here.

**Small fix, already drawn.** The identifier hover card now sets page text and URL patterns as inline code, like
`In-Person Major Code: 2166` and `/graduate/*` (`page/screens/w2-rules-id-card.png`).

Written 2026-11-24. Research: [`research/running-notes.md`](research/running-notes.md).

---

## 1. What the running-notes reports are today

Jared posted this morning that `ceterms:inLanguage` and `ceterms:lifeCycleStatusType` are "ready to be scored", and
that the report goes in the engineering running notes under "In Language". That heading is in the tab **Collated
Reports for COURSE**.

**The tab.** There is one heading per Course property, each with a status: *Needs Review* or *Done*. Under a heading
go three things:

1. **A score table.** One row per catalog plus *All*, and four columns: golden exact, golden exact + partial, silver
   exact and silver exact + partial. Each cell is "n/d (pct)".
2. **Why values are missing.** Reason codes (M1–M4), each with a count per catalog and a *Cause / Fix / Assessment*
   written by Seth.
3. **Mismatches.** Reason codes per property (N1–N4 for name, D1–D9 for description), with counts, examples quoting
   the golden and extracted values, and "whose error" (silver, extractor, baseline or normalization).

**How it gets there.**
1. Jared finishes a property's golden set and rules, and says so in Slack.
2. Someone runs xtra's scorer.
3. They assemble the tables by hand, partly with Claude.
4. They paste the result into the doc.

**What the doc doesn't record:** no command, no xtra-cli version and no golden version. The team flagged this
themselves:
- the Nov 19 notes: "Pasting in Google doc is manual… Automate through Argo workflows and integrate in UI";
- Rohit, in a comment: "Let's also not generate these things in Claude. These should be outputs from CLI";
- Rohit, on the combined column: "We should not mix exact + partial in metrics… report accurately the partial matches
  independently."

The Nov 24 agenda says Learning Program, Credential and the other classes will get the same kind of tab.

### Does the Studio replace it?

**Yes, for the numbers. No, for the analysis.** The argument:

| The doc has | The Studio, after this work |
|---|---|
| A score table per property, assembled by hand when someone gets to it | **Replaced, and better.** Computed whenever the golden set or xtra's output changes, by the CLI's own scorer rather than by Claude. Exact and partial are kept apart, as Rohit asked. Every catalog, class and property, with history (§2). |
| Mismatch examples, picked by hand | **Replaced, and better.** The Evals tab already lists every mismatch down to the record, with the page. A score row links straight to it. |
| *Why values are missing* and *Cause / Fix / Assessment*, written by Seth | **Not replaced.** This is a person's diagnosis, and no score computes it. |
| Status per property: *Needs Review*, *Done* | **Not replaced** today. This is the one small thing worth adding (question 1). |
| Comment threads on single mismatches | **Not replaced.** They stay with the analysis. |

**Recommendation:**
- The Studio becomes where the scores live.
- The doc keeps only the written analysis, with each property heading linking to its view in the Studio.
- The *Copy as a table* link stays, for anyone who wants a snapshot in the doc.
- Once a property's status lives in the Studio, the tab is just notes.

---

## 2. Scores: four views, one per question Jared asks

**Picking a view.** Two menus pick it: **Catalog** (All, or one) and **Property** (All, or one). The four
combinations are your four user stories. Each view's rows open the next one down, and the deepest one links into that
catalog's Evals tab, which goes down to the records.

| Catalog | Property | The question | Rows | A row opens |
|---|---|---|---|---|
| All | All | Where are we overall, and what's weakest? | catalogs, or properties (a *Rows* switch) | that catalog, or that property |
| One | All | How is this catalog doing across its properties? | its properties | that catalog and property |
| All | One | How is this property doing across catalogs? (hill-climbing one property) | catalogs | that catalog and property |
| One | One | Is this catalog's property getting better over time? | its scores over time | the Evals tab at that property |

**The same in every view:**
- **Classes stacked:** each class is its own table, one above the next, chosen with the same *Classes* menu as the
  golden view. Classes don't share properties, so a property list never mixes classes.
- **Two lines per row:** *Golden*, scored against human-reviewed values, and *Silver*, scored against rule-matched
  values.
- **A cell is a stacked bar** of every outcome in the Evals tab's colours: exact, partial, unsure, wrong, missing.
  Beside it are **exact** and **partial** as separate numbers.
- **Bars | Numbers:** the switch turns the bar into one column per outcome, with counts. Each column heading is set in
  its outcome's colour.
- **Last 7 outputs:** stacked bars with a y-axis from 0 to 100, a dashed 90 line, and the first and last day.
- **Removed clutter:** no issue numbers, and no breadcrumb plus a second dropdown. The two menus are the navigation.

**The data:** Course ceterms:name golden values for the latest output are Seth's figures. Everything else is
illustrative.

### 2.1 All catalogs, all properties

Each catalog's bar is averaged over the class's minimum properties. The *All* row is averaged over every catalog.

![All catalogs, all properties, bars](page/screens/w3-scores-all.png)

The same, with **Numbers**:

![All catalogs, all properties, numbers](page/screens/w3-scores-all-numbers.png)

The same, with **Rows: Properties**. Each property is averaged over all catalogs, so the weakest property stands out.
Clicking one opens 2.3.

![All catalogs, rows by property](page/screens/w3-scores-all-by-property.png)

### 2.2 One catalog, all properties

WVU, each property's latest bars and history. *Evals →* opens WVU's Evals tab at that property.

![One catalog, all properties](page/screens/w3-scores-one-catalog.png)

### 2.3 All catalogs, one property

ceterms:name in every catalog, for each class that has the property. This is the running notes' table, with outcomes
instead of four ratio columns.

![All catalogs, one property](page/screens/w3-scores-one-property.png)

### 2.4 One catalog, one property, over time

Two large history charts, Golden and Silver, with the latest outputs listed under them. The link opens WVU's Evals tab
at ceterms:name, where every record can be compared.

![One catalog, one property](page/screens/w3-scores-one-catalog-one-property.png)

**How this relates to the Evals tab:**
- **Evals tab:** one catalog. It goes from bars down to single records.
- **These views:** many catalogs and classes, but they stop at the score.
- **The link between them:** the one-catalog views (2.2, 2.4) link into Evals at the same catalog and property.

---

## 3. When a score is computed, and where it goes

**Triggers.** A new score is computed when either side of the comparison changes:

| Trigger | What gets scored |
|---|---|
| A golden version is published: Jared approves a rule or gives verdicts, then publishes | The latest xtra extract output for that catalog and class, against the new golden and silver versions. Only the properties that changed. |
| xtra writes a new extract output: an xtra-cli change, or a new run | That output, against the current golden and silver versions, for every property of every class. |

**Steps:**
1. Run xtra's own scorer, the library the Studio already calls, filtered to the class.
2. Write each result to xtra-cli's paths: `xtra-cli-output/<catalog>/<crawl>/extract/<run-id>/scores/<baseline>/<class>/<property>/`.
3. Append one line to `xtra-cli-output/scores/<class>/<property>/<catalog>.jsonl`. The line holds the time, the
   extract run, the golden version, the trigger and the outcome counts.
4. The Studio's score views and Evals tab read only those files.

**Who runs it.** The Studio already has a score scheduler: it scores an extract output the first time it sees one.
It would also run on publish, and write to the xtra-cli paths instead of its own folder. That needs no xtra-cli
changes. Later, an Argo workflow (mentioned in the Nov 19 notes) or xtra-cli itself could take over, writing to the
same files, and the Studio wouldn't change.

**What this replaces.** Jared's message this morning becomes: he publishes in the Studio, and the scores appear on the
home page's *xtra score* view a few minutes later. Nobody has to paste anything.

---

## 4. Questions

> **1. Should a property's status move into the Studio?**
>
> - **Today:** the doc marks each property *Needs Review* or *Done* by hand, and that is how the team tracks which
>   properties are finished.
> - **The proposal:** a status per catalog, class and property, set in the one-property view (2.3), with an optional
>   one-line note. It would show as a small mark next to the property in 2.1 and 2.2.
> - **Option 1:** add it. The doc then keeps only the written analysis.
> - **Option 2:** leave status in the doc.
>
> **Working answer:** option 1. It's small, and it's the one thing that keeps people in the doc.

> **2. Which number is held to 90%?**
>
> - **The four numbers:** golden exact, golden partial, silver exact and silver partial. Rohit asked that exact and
>   partial not be combined.
> - **Option 1:** golden exact must reach 90%, and partial is shown beside it.
> - **Option 2:** exact + partial together must reach 90%, as the doc's second column does today.
>
> **Working answer:** option 1. The red numbers in the pictures follow it.

> **3. What does the history chart count?**
>
> A score is computed whenever the golden set or xtra's output changes. That can be several times a day, or not for
> days.
> - **Option 1:** the last 7 scores, each bar marked with what triggered it (a new golden version or a new output).
> - **Option 2:** one bar per day, that day's latest score.
>
> **Working answer:** option 1. A rise after a golden publish and a rise after an extractor change mean different
> things.

> **4. At the top level, are rows catalogs or properties?**
>
> - **Rows: Catalogs** answers "which catalog is weakest".
> - **Rows: Properties** answers "which property is weakest".
>
> **Working answer:** catalogs, with the switch one click away.
