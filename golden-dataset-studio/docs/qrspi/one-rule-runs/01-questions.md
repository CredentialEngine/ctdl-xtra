# Q — Questions: one rule per AI run, several runs at once, a report you can act on (2026-11-05)

**The problem.** In the Studio, the button that asks Claude to fix a catalog's rules sends Claude every rule marked
**Needs work** at once. Claude works unattended for several minutes and then writes a single report covering all of
them. On AVC, a run on 6 rules came back with "8 things to fix before Claude can publish": 8 numbered to-dos and 46
links, most of them pointing to courses the reader has to open to understand the to-do. Screenshot of that report
(served locally from branch `studio-report-links`):
[`../report-links/screens/report-sim.png`](../report-links/screens/report-sim.png).

Reading it aloud, Eric found that:
- it is too much at once: 8 to-dos and dozens of links;
- to-dos like "Save this as ACCT199's expected value" can't be understood without opening several links: *which*
  value, saved *where*, and what "Then:" and "Value to save:" mean;
- to-do 2 (Subject Webpage: "decide whether Subject Webpage should be empty for catalog courses; if so, re-mark the 13
  courses marked correct") was clear and actionable, but Jared couldn't act on it and get a new run without first
  clearing to-dos 1 and 3–8;
- a course marked wrong with **no expected value** stops a rule from publishing, and annotators often won't fill in an
  expected value.

**The goal.**
1. You can improve **one rule** at a time, from that rule's row in the Rules tab sidebar, and see that rule's past AI
   runs (and its prompt) there.
2. **Several runs can work at the same time**: start a run on Subject Webpage, move to the next rule, start another.
3. **The report of a one-rule run is short and self-contained**: quotes are shown inline, each followed by a link as a
   citation, so you rarely have to click anything to understand a to-do.
4. **A missing expected value doesn't block a rule.**
5. An "improve every rule that needs work" button still exists, with a summary view.
6. The CLI, not Claude's prose, still guarantees the report's structure and links.

- Original prompt (verbatim): [`prompt.md`](prompt.md)
- Each question has a **default**. Research and the spec work from the defaults until you answer.
- Code was read; nothing was changed.

---

## 0. What exists today (no input needed)

**Starting a run.** The Rules tab's run bar has one button. It starts a run with scope `needs_work` (every rule
marked Needs work) or `first_rules` (every rule not written yet) (`server/routes_agent.py:29`). You can't start a
one-rule run from the UI: an earlier spec ruled that out (`docs/qrspi/k2-runs/03-spec.md:152`, a one-rule scope
returns `422`). The prompt builder can already build a prompt for one rule (`prompt.py:307`,
`build_prompt(ctx, rule=…)`); the old Prompt tab used that.

**One run per catalog.** A run holds the catalog's lock, `<catalog>/golden-dataset-studio/agent-runs/current.json`,
until it ends (`agent_runs.py:7`). While it runs, nobody can start another run on that catalog.

**One Claude on the K2 server.** The Studio sends the prompt to a single K2 agent, `golden-rules`
(`POST /v1/w/golden-rules/message`, `agent_runs.py:76`). If that agent is already working, even on another
catalog, K2 answers `409 busy` and the run waits and retries every 20 s (`agent_runs.py:41`, `:281`). So across the
whole Studio, only one Claude works at a time.

**Publishing.** A run that succeeds publishes a new ruleset version for the catalog (v9 → v10), containing every rule
it changed.

**The report.** On branch `studio-report-links` (not merged yet), Claude writes `report.json`, and
`golden-datasets run done --report report.json` checks every id in it and renders the Markdown with Studio links
(`report.py`). It has no structure for quotes.

---

## 1. One-rule runs

**Q1.1 Where is the button for one rule?**
- **A.** A small "Improve with AI" icon button on each rule's row in the sidebar. It shows on hover and on the selected
  row only, so the sidebar doesn't fill with buttons.
- **B.** Only in the selected rule's header, above the course list (one button on screen at a time).
- **C.** Both.
- **Default: A** (what you asked for). To keep it from crowding the sidebar, the button is a small icon with a tooltip
  ("Improve Subject Webpage with AI"), shown on hover and on the selected row. The open question is whether it should
  always be visible on every row instead. Mockups will show both.

**Q1.2 Which rules get the button?**
- **Default:** every rule the reader can see. On a rule marked Needs work it reads "Improve with AI"; on a rule not
  written yet, "Write with AI"; on an Approved rule it's hidden behind the row's `⋯` menu.

**Q1.3 May a one-rule run change other rules?** Fixes often cross rules. Example from the AVC report: emptying
Subject Webpage "moves the address to In Catalog", and Credit Value's fix needs Credit Unit Type to read a different box.
- **A.** No. The run publishes only its own rule. If the fix needs another rule changed, the report has a to-do
  "Start a run on In Catalog" with a button.
- **B.** Yes, it may also publish the other rules it needs (the report says which).
- **Default: A.** Predictable, and it keeps two runs from editing the same rule at once (see §2).

**Q1.4 What does "improve every rule that needs work" become?**
- **A.** Today's single run that covers every rule, with one combined report.
- **B.** One one-rule run per rule marked Needs work, started together, plus a summary list: one line per rule
  ("Subject Webpage: 1 thing to decide · Description: published v11 · …") linking to each rule's report.
- **Default: B.** Each rule gets the short report you asked for, and the batch is just several one-rule runs (they
  queue if fewer Claudes are free than rules; see §2).

**Q1.5 What does the run work from?** A run reads the annotations as they are when it starts. If Jared re-marks
courses on Subject Webpage while its run is working, the run doesn't see the changes.
- **Default:** the report says "Based on annotations as of 2:31 PM", and the rule's row shows "annotations changed
  since this run" when that's true. No automatic restart.

## 2. Several runs at once

**Q2.1 How many Claudes at once?** Each running Claude uses the K2 server's CPU and memory and counts against the
Claude subscription's usage limits.
- **Default:** up to **3** running at once, Studio-wide. More runs wait in a queue, shown as "waiting for a free
  Claude (2nd in line)". Research will measure what one run costs (memory, time, tokens) before the spec fixes the
  number.

**Q2.2 How should K2 run several Claudes?** Today there's one agent, `golden-rules`, that takes one message at a time.
- **A.** A fixed pool of agents (`golden-rules-1` … `-3`), each in its own K2 workspace folder. The Studio sends each
  run to a free one.
- **B.** One new K2 session (or worker agent) per run, created through K2's API and closed when the run ends.
- **Default:** whichever K2 supports with the least new setup. Research will check K2's API (host sessions, worker
  agents) and the deploy scripts, and the spec will say what changes on the K2 side and what changes in the Studio.

**Q2.3 One run per rule?**
- **Default:** yes. A rule that already has a live run can't get a second one, and its button shows "Running · open".
  Two different rules on the same catalog can run at the same time (today's lock is per catalog; it becomes per rule).

**Q2.4 Two runs publishing at the same time.** Run A publishes Subject Webpage while run B publishes Description, both
starting from v9.
- **Default:** each publish makes a new ruleset version from the latest one, changing only its own rule (v10 = v9 +
  Subject Webpage; v11 = v10 + Description). If they collide, the second one re-reads and retries. This gives more
  ruleset versions (one per rule fixed). **Is that OK**, or do you want versions grouped (for example, a batch
  publishes once at the end)?

## 3. Expected values

**Q3.1 What should a run do with a course marked wrong that has no expected value?** Example: an annotator marks
ACCT199's Description wrong and leaves a comment ("the Limitation on Enrollment line shouldn't be part of it") but no
expected text. Today Claude can't score a draft against it, so the rule can't publish.
- **A.** Claude works out the value it believes is right (from the page and the comment), uses it when it checks its
  draft, and publishes. The report lists the values it assumed ("I took ACCT199's expected Description to be: …
  [quote]"), each with a one-click "That's right" that saves it as the expected value.
- **B.** Same as A, but the rule doesn't publish until someone confirms the assumed values.
- **C.** Courses with no expected value are left out of the check; the report says how many were left out.
- **Default: A.** Missing expected values never block publishing, and confirming a value takes one click. A wrong
  guess is caught the next time someone reviews that course.

**Q3.2 Courses marked correct.** A "correct" mark already means the extracted value is the expected value; nothing to
ask.

## 4. The report of a one-rule run

**Q4.1 Shape.** Default, for one rule:
1. One headline: what happened ("Published v11: Subject Webpage now empty for catalog courses" or "1 thing to decide
   before Claude can publish Subject Webpage").
2. **At most 3 to-dos.** Each one stands on its own: it names the course and the rule, shows the current value and the
   proposed value side by side, quotes the page or the comment in a quote block followed by a single citation link,
   and says in plain words what Claude will do once you've done it. No "Then:" / "Value to save:" labels.
3. Anything past 3 is folded under "More (n)".
4. What Claude changed (if it published), in a few lines.
- **Default:** as above. Mockups will use the real Subject Webpage and In Catalog cases from the AVC run.

**Q4.2 Links.** Default: a course is a link once, the first time it appears in a to-do; a quote's source is a citation
link at the end of the quote; no other links. A list of 13 courses becomes "13 courses (list)", and opening the list
shows them.

**Q4.3 Can the CLI check quotes?** Default: yes. `report.json` gets a `quote` field (`text` plus its source: a page of a
course, or a comment). `run done --report` refuses a quote whose text doesn't appear in that page or comment, so Claude
can't misquote. Formatting stays the CLI's job, as on `studio-report-links`.

**Q4.4 Acting from the report.** Today, links open the course in the Rules tab, and you do the change there.
- **A.** Links only (today).
- **B.** For the commonest action, "save this as the expected value", the to-do has a small **Save** button that saves
  it without leaving the report. Everything else stays a link.
- **Default: B**, limited to that one action, because it's what most to-dos in the AVC report asked for.

## 5. The sidebar: AI status and history per rule

**Q5.1 Where does a rule's AI history live?**
- **Default:** a rule with a live or past run shows a small icon on its sidebar row (spinner while running; a dot when
  a run needs you; nothing otherwise). Clicking it opens the right-hand panel on **that rule's runs**: the latest
  report first, older runs below, and "Open the prompt". The catalog-wide "Past AI runs" list stays and gains a
  filter by rule.

**Q5.2 Who can open the prompt?** Today only Eric and Seth see "Open the prompt".
- **Default:** keep it to Eric and Seth. Say if everyone should see it.

**Q5.3 Progressive disclosure.** Default: a reviewer who never uses AI sees no new buttons on sidebar rows except
status icons on rules that have runs; the AI button appears on hover and on the selected row (Q1.1 A), and in the run
panel. A first-time tooltip on the header button explains it once.

## 6. Today's batch runs

**Q6.1** Past multi-rule runs (like AVC's 6-rule run) stay readable in "Past AI runs", unchanged. Default: yes.
