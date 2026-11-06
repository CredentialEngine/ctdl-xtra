# Q — Questions: links in Claude's run reports (2026-11-04)

**The problem.** When someone clicks the Studio's button that asks Claude to fix a catalog's rules, Claude works
unattended and ends with a report (Markdown). People read it in the Studio, in the panel that shows the current run
and in the list of past runs. The report names courses (ACCT199, AERO199…), rules (course-in-catalog…), drafts and
scores, but a reader can't click any of them. They have to find each course in each rule by hand. Example:
[`example-report.md`](example-report.md) (the AVC report of 2026-11-04; nothing in it is a link).

**The goal.** Claude's report links every course, rule and decision it raises to the exact Studio screen where the
reader can check it or fix it, and every link it writes opens the right place.

- Original prompt: [`prompt.md`](prompt.md)
- Each question has a **default**: what research and the spec work from until you answer.
- Code was read; nothing was changed.
- **Answered 2026-11-04 (pass 1):** [`answers-pass1.md`](answers-pass1.md), verbatim; decisions and the research that
  followed are in [`02-research.md`](02-research.md) §1.

---

## 0. What exists today (no input needed)

**How the report gets written.** The run prompt (`src/golden_datasets/prompt.py:255`, `_run_close`) tells Claude to
write `summary.md` "for people, in Markdown" and end with
`golden-datasets run done --run <id> --summary-file summary.md --outcome "…"`. The prompt says nothing about links.
The Studio stores the file (`agent_runs.py:345`) and shows it as Markdown (`RunBar.tsx:177`, `RunsPanel.tsx:93`).

**What Claude can see.** Claude reads annotations with `golden-datasets rule annotations` (`loop.py:219`). Each one
shows the course code, rule, annotation id, page file and the college's live URL, **but no Studio link**. Claude
doesn't know the Studio's web address either: the server never records it.

**Links that already work** (hash routes, `web/src/shell/router.ts`):

| What it opens | Link |
|---|---|
| One course in one rule, selected and scrolled to, with its page beside it | `#/c/avc/rules/course-in-catalog?row=ACCT199` |
| One course across all its fields | `#/c/avc/records/ACCT199` (`?prop=` picks a field) |
| Two published rulesets side by side, one rule | `#/c/avc/compare?a=8&b=9&rule=course-description` |
| Evals for a catalog | `#/c/avc/evals?…` |

`?row=` accepts a course code (`ACCT199`, any case, spaces ignored), an occurrence key or a page file name
(`routes_review.py:279`). If the rule has no row for that course (ACCT199 in course-entry-condition is empty), the
Rules tab says so and still shows the page.

**What a link can't open today:**
- one annotation or comment (links select a row; the row shows its annotations, but not one in particular);
- a draft Claude tried but didn't publish (`drafts/needs-work.json` lives only in the run's folder; Compare opens only
  published rulesets);
- a past run's report (the list of past runs has no address of its own).

**Why some links would show as plain text.** The Studio's Markdown renderer only makes `http(s)://` links clickable,
and opens them in a new tab (`web/src/prompt/markdown.tsx:107`). A `#/c/avc/…` link would show as text.

---

## 1. Where must the links work?

The report is read in the Studio. It is also Claude's final reply in the agent session, and people may paste it into
Slack or email.

- **A. Full web addresses** (`https://<studio>/#/c/avc/rules/…`). They work anywhere. The Studio has to give Claude
  its own address: the browser that starts the run knows it, and sends it with the start request. Links that point at
  the Studio open in the same tab; links to college pages keep opening a new tab.
- **B. Studio-only links** (`#/c/avc/…`). Shorter, and they never point at the wrong server, but they only work inside
  the Studio.

**Default: A.**

## 2. What should Claude be able to link to?

Already possible: a course in a rule, a course's record, Compare between two published rulesets. Each new one below
is extra Studio work.

- **2a. One annotation** (`?row=ACCT199&note=<annotation id>`: opens the row with that annotation highlighted). Useful
  when a course has several notes, like ACCT199's two contradicting Description notes.
  **Default: yes.**
- **2b. A draft Claude tried but didn't publish**, so a reader can see "what would change" (e.g. the In Catalog draft
  that fills 1,062 values). This means storing the draft with the run and letting Compare show "v9 → this run's draft".
  The largest item here. **Default: no, for now.** The report keeps describing the draft in words.
- **2c. The run's own report**, so it can be shared (`#/c/avc/runs/<run id>`). Small. **Default: yes.**
- **2d. A list of courses at once** (e.g. "the 13 courses marked correct that would change"): one link to the rule
  filtered to those courses, instead of 13 links. **Default: no.** Each course code is its own link; 13 short links
  in a table cell is fine.

## 3. How do we make sure every link works?

The point is that Claude never hand-builds a link that turns out wrong (a misspelled rule id, a course the rule
doesn't have, a ruleset that doesn't exist).

- **A. The CLI gives Claude the links.** Every course `rule annotations`, `rule show` and `rule try` print comes with
  its ready link, and a new `golden-datasets link <rule> <course>` prints one on demand after checking the rule and
  course exist. The prompt tells Claude to copy links from the CLI, never build them.
- **B. `run done` checks the report.** Before saving `summary.md`, it checks every Studio link in it (catalog, rule,
  course, ruleset numbers, annotation id). Then either:
  - **B1. refuses** the report and lists the broken links, so Claude fixes them and runs `run done` again; or
  - **B2. accepts** it and turns each broken link back into plain text, with a note in the run's progress notes.

**Default: A + B1.** If Claude ignores the refusal, the run stays open and the Studio says Claude stopped responding
after 5 minutes, which people already understand.

## 4. What should the links look like in the report?

- **A. The name is the link**: `[ACCT199](…)` and `[course-in-catalog](…)`. Compact, and fits table cells.
- **B. A separate "Open →" link** after each item.

**Default: A.** Rule links use the rule's name as the Studio shows it (e.g. "In Catalog") with the id in
`code` after it, so the reader recognises the screen it opens.

## 5. Should the report also stop assuming the reader knows how Claude works?

Links fix "where is this?". The example also uses words only Claude knows: "rule try", "UNKNOWN", "newly wrong",
"rs-0009", `drafts/needs-work.json`, `source_url`. The prompt could also tell Claude to write for someone who knows
the catalog but not Claude's tools: Studio names for things, no file paths, verdicts in plain words.

**Default: yes, in this same change** (a few lines in the prompt, no Studio work). Say no if you want this change to be
about links only.
