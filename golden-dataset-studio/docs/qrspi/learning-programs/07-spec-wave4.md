# S (draft, wave 4): moving the running-notes workflow into the Studio

**Only what is still open.** Approved items, including wave 3's, are in [`05-approved.md`](05-approved.md).

**This wave covers:**
- pieces of the running-notes Google Doc, each shown next to the Studio surface and workflow that replaces it;
- choosing classes and properties;
- findings, property status and discussion;
- the Studio running the scorer itself, with the xtra-cli version recorded.

Written 2026-11-24.

- **Doc pictures** (`page/screens/doc/`): real renders of the doc's PDF export.
- **Studio pictures:** the real app with mockup edits, as before. Seth's codes and texts are real. Counts, states and
  comments not taken from the doc are illustrative.

---

## 1. The doc, piece by piece, and what replaces it

### 1.1 The list of properties with their status

**In the doc:** the tab *Collated Reports for COURSE* has one heading per property, marked *(Needs Review)* or
*(Done)*. The empty headings are the properties still waiting for a report, such as In Language, which Jared asked
about today.

![Doc: property headings with status](page/screens/doc/status-headings.png)

**In the Studio:** the score view with *Rows: Properties* lists every property, with its status beside the name. A
property with no golden values yet shows no score, just as its heading in the doc is empty.

![Studio: properties with status](page/screens/w4-scores-by-property-status.png)

**Workflow:**
1. Jared publishes golden values for In Language.
2. The Studio scores it.
3. The row fills in with *Needs review*.
4. When the team agrees, someone sets it to *Done*.

There is no Slack message and no pasting.

### 1.2 The score table

**In the doc:** one table per property, with one row per catalog plus All, four ratio columns ("n/d (pct)"), and exact
and exact + partial mixed together.

![Doc: score table](page/screens/doc/score-table.png)

**In the Studio:** the *one property, all catalogs* view (2.3 in wave 3), now with a dotted 90% line. It is computed,
keeps exact and partial apart, and has history.

![Studio: one property, all catalogs](page/screens/w4-property-review.png)

### 1.3 "Why values are missing" and the mismatch codes

**In the doc:** reason codes, counted per catalog, then each code written up as **Cause / Fix / Assessment**, with
"whose error".

![Doc: why values are missing](page/screens/doc/why-missing.png)

![Doc: description mismatches](page/screens/doc/mismatch-table.png)

![Doc: one code's cause and fix](page/screens/doc/cause-fix.png)

**In the Studio, two steps:**

**1. Make a finding where the evidence is.** The Evals tab already has *Where it's wrong*. It groups every unit that
isn't an exact match by its likely cause, with an example and the courses. This is today's screen, AVC, description:

![Studio today: Where it's wrong](page/screens/t08-evals-where-wrong.png)

Each group gets a **Finding** column:
- **Finding:** either the finding it belongs to, or *+ Add finding*.
- **Discuss:** a link with its comment count.

![Studio: Where it's wrong with findings](page/screens/w4-evals-findings.png)

Opening a finding shows its editor:
- **The same fields as Seth's write-ups:** code, title, whose error, cause, fix and assessment.
- **The units it covers:** counted per catalog, golden and silver, and kept current as scores change.
- **Discussion:** the finding's thread.

![Studio: the finding editor](page/screens/w4-evals-finding-panel.png)

**2. See every finding for the property in one place.** Below the score table, the property's review page lists its
findings across all catalogs:
- code and kind (missing or mismatch);
- counts for partial, wrong and missing, each as golden / silver;
- catalogs, whose error, state (open or fixed) and comments.

The status control sits at the top of the page. This page is the doc's per-property section, made from data. (Same
picture as 1.2, lower down.)

### 1.4 Mismatch examples and comment threads

**In the doc:** examples quoting the golden and extracted values, and comment threads on single mismatches. A real
thread:

> Rohit: "Is "w/" what is in the original page? If so, then the golden sample is incorrect."
>
> Jared: "The golden sample is correct. The name as displayed at the top of the page is verbatim in the golden sample.
> The extracted value is from a 2nd listing of the course name at the bottom of the page…"

![Doc: a mismatch example](page/screens/doc/mismatch-example.png)

**In the Studio:**
- **Examples:** these are the units themselves. Every unit is a row in Evals, with golden and candidate values and a
  link to the page in Rules.
- **Comments:** a thread can sit on a group, on a finding, or on one unit. Each thread shows the unit's golden and
  extracted values, so a reply like Jared's has its evidence beside it.

The Studio already has per-row comments in the Rules tab, with the *3 comment* verdict and *Discuss*. Evals threads
would use the same store.

### 1.5 What stays in the doc

Nothing has to stay. The doc can link to each property's review page, and *Copy as a table* stays for anyone who wants
a snapshot.

---

## 2. Choosing classes and properties

- **Three menus, in order:** Catalogs, Classes, Properties.
- **Classes:** the default is all of them.
- **Properties:** listed **under their class**, and ticking a class ticks all of its properties. A property always
  belongs to one class, so "ceterms:name" is never picked across classes at once. It is *Course › ceterms:name*.
- **Choosing one property** narrows Classes to that class.

![Studio: the Properties menu](page/screens/w4-scores-props-menu.png)

---

## 3. The Studio runs the scorer, and every score says which xtra-cli

**Today.**
- **The scorer:** the Studio calls xtra's scorer in-process. `xtra-cli` is a path dependency of the Studio
  (`pyproject.toml`: `xtra-cli = { path = "../xtra-cli" }`).
- **Its version:** the xtra-cli from the same monorepo commit the Studio was deployed from.
- **What's recorded:** each score already records that commit (`scores.py:311`, `xtra_cli_commit`), but nothing on
  screen shows it.

**Proposed.**
- **Scored with:** every score row shows its golden version and its xtra-cli version (package version and commit).
  Each bar in the history chart is marked *golden* or *output*, for what triggered it.
- **Score now:** rescores the selected catalog and property right away, so you don't wait for a trigger.
- **Which xtra-cli:** see the question below.

![Studio: one catalog, one property, with versions](page/screens/w4-scores-one-catalog-one-property.png)

> **Question: which xtra-cli does the Studio score with?**
>
> - **Option 1: the one deployed with the Studio**, as today.
>   - The version changes whenever the Studio is deployed from main.
>   - Simple, with nothing installed at run time.
>   - A newer xtra-cli on main isn't used until the next Studio deploy.
> - **Option 2: install a chosen xtra-cli per score.**
>   - "Score now with xtra-cli main ▾" installs that ref into its own environment, the way AI runs already install
>     their CLI outside the workspace, and runs the scorer there.
>   - Always the latest, and an older ref can be re-run for comparison.
>   - Slower, with one more moving part.
>
> **Working answer:** option 1 for automatic scores, plus option 2 behind *Score now* for when someone wants main
> right now.

> **Question: also show which xtra-cli *extracted* the output?**
>
> - **Two different versions:** the version that scored the output isn't always the one that produced it.
> - **Where to show it:** if the extract report records its own version, show it as "extracted with" beside "scored
>   with".
>
> **Working answer:** yes, when the report has it.

---

## 4. Questions on findings and status

> **1. Who can set *Done*?**
>
> - **Option 1:** anyone.
> - **Option 2:** only the subject-matter expert role (Jared), as with verdicts.
>
> **Working answer:** anyone can set *Needs review*. Only the SME role can set *Done*. The status remembers who set it
> and when.

> **2. Are findings per class and property across all catalogs, or per catalog?**
>
> - **How Seth writes them:** per property, across catalogs. D3, for example, is WVU 194 and AVC 4.
>
> **Working answer:** per class and property. A finding's counts are split by catalog, as drawn.

> **3. Should a finding close by itself?**
>
> - **When it could:** once a new score leaves it no units.
> - **Option 1:** it shows *0 units*, and a person marks it fixed.
> - **Option 2:** it is marked fixed automatically.
>
> **Working answer:** option 1. "Fixed" is a claim someone should make.
