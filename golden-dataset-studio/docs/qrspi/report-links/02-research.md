# R — Research: links and a fixed shape for Claude's run reports (2026-11-04)

Follows [`01-questions.md`](01-questions.md). Eric's answers to it, verbatim: [`answers-pass1.md`](answers-pass1.md).
Code was read; nothing was changed. The section **5. Proposal** ends with the questions still open.

## 1. Decided (Eric, pass 1)

| # | Decision |
|---|---|
| 1 | Full web addresses (`https://<studio>/#/c/…`) that work anywhere, including Slack. The browser sends the Studio's address when it starts a run. |
| 2a | A link can open **one annotation** (e.g. each of ACCT199's two contradicting Description notes). |
| 2b | No link to an unpublished draft. The report has to give enough information to get unstuck without it. |
| 2c | A run's report gets its own link, so it can be shared. |
| 3 | Whichever way of guaranteeing links is simplest and uses the fewest tokens (Claude's judgment; see 5.3). |
| 4 | The name is the link (`[ACCT199](…)`). **Every link opens in a new tab and shows the external-link icon.** |
| 5 | Write for someone who knows the catalog but not Claude's tools. |
| new | **What the reader must do to get unstuck comes first**, in a fixed shape. Today a run that stops for decisions reads like a crash ("Claude couldn't finish"). |
| new | Look into the CLI giving the report its shape, so it depends less on Claude writing it well each time. |

## 2. How a run ends today

- The prompt's last section (`prompt.py:255`, `_run_close`) asks for a free-form `summary.md` ("what changed and why,
  the final scorecard, what people need to decide, anything you could not fix") and one of:
  `golden-datasets run done --run <id> --summary-file summary.md --outcome "…"`, or the same with `--failed`.
- The CLI stores the file as is (`agent_runs.py:345`). Nothing checks or shapes it.
- A run has **two possible endings Claude can choose: `finished` or `failed`** (`agent_runs.py:39`). The run bar shows
  `failed` as **"Claude couldn't finish"** with the needs-work icon (`RunBar.tsx:30, 88`). That's how a run that did
  its job (found five things only a person can answer) ends up looking like a crash: Claude has no other ending.
- The outcome line is free text, so its wording changes from run to run. The AVC one: *"Couldn't publish (ruleset v9
  stays): the 6 ACCT199 annotations have no expected values; inCatalog draft ready, …"*.

## 3. What the CLI knows when the run ends

Claude runs every command from the run's folder, and that folder's settings name the run's catalog and storage.
`run done` gets `--run <id>`. From those, the CLI can read, with no extra work from Claude:

| Fact | Where |
|---|---|
| Catalog, rules and their names as the Studio shows them ("In Catalog", "Entry Condition: Description") | the current ruleset; `rule_title` (`routes_review.py:46`) |
| Which courses each rule has a row for | the current extraction |
| Every annotation: id, rule, course, author, verdict, note | the annotation log (`rule annotations` reads it, `loop.py:263`) |
| Ruleset before the run, and after, if Claude published | `run.json` (`ruleset_before`, `ruleset_after`) |
| The Studio's web address | **nothing yet**: the start request (`routes_agent.py:81`) would store the browser's address in `run.json` |
| The scorecard of Claude's last try | **nothing yet**: `rule try` prints it and forgets it (`loop.py:514`). It can already print JSON (`--json`). |

## 4. Links: what exists and what's missing

| Opens | Link (after `https://<studio>/`) | Today |
|---|---|---|
| A course in a rule, selected, its page beside it | `#/c/avc/rules/course-in-catalog?row=ACCT199` | works (`?row=` takes a course code, `routes_review.py:279`) |
| A course across all its fields | `#/c/avc/records/ACCT199` | works |
| Two published rulesets, one rule | `#/c/avc/compare?a=9&b=10&rule=course-in-catalog` | works |
| One annotation on a course | `…/rules/course-description?row=ACCT199&note=<annotation id>` | **new**: the row opens; the annotation would be scrolled to and outlined in the row's history |
| A run's report | `#/c/avc/rules?run=<run id>` | **new**: opens the past-runs panel on that run (`openRuns(runId)`, `api.ts:95`, already exists; it needs only a URL parameter, like `?prompt=1` in `App.tsx:55`) |

The Studio's Markdown renderer makes only `https://` links clickable and already opens them in a new tab
(`markdown.tsx:107`). It doesn't show the external-link icon yet. The icon exists (`icons.tsx:17`, used for "open
K2" in `RunBar.tsx:137`). Full addresses (decision 1) need no renderer change apart from adding the icon.

## 5. Proposal

### 5.1 Claude writes facts; the CLI writes the report

Instead of `summary.md`, Claude writes a short `report.json` that names things by **id** (rule ids, course codes,
annotation ids) and never builds a link. `run done --report report.json` checks it, then **renders the Markdown
itself**: always the same sections, in the same order, in the same words, with every link built by the CLI from the
Studio address in `run.json`.

What Claude writes for the AVC run (abridged):

```json
{
  "ending": "needs_you",
  "headline": "5 decisions from you before In Catalog can be published",
  "to_do": [
    {"rule": "course-in-catalog", "course": "ACCT199", "notes": ["an-7f3a"],
     "do": "Save the page address as ACCT199's expected value",
     "value": "https://avc.elumenapp.com/catalog/2026-27/course/acct199",
     "then": "The next run publishes the In Catalog rule as drafted: it fills 1,062 courses with their page address."},
    {"rule": "course-description", "course": "ACCT199", "notes": ["an-91c2", "an-91c7"],
     "do": "Pick one of the two notes: drop the Limitation on Enrollment text, or leave it in",
     "then": "If it goes, AERO199, CFE114 and NS922L change too: re-mark them."}
  ],
  "rules": [
    {"rule": "course-credit-value", "asked": ["an-5d10"], "tried": "Leave Credit Value empty",
     "result": "not published",
     "why": "Credit Unit Type reads Credit Value, so 998 of its values would vanish, ACCT199 among them."}
  ],
  "notes": "optional, short free text"
}
```

What the CLI renders (and the Studio shows; every underlined name is a link that opens in a new tab ↗):

> **Claude needs 5 decisions from you** · AVC · ruleset v9 unchanged
>
> ## What you need to do
> 1. **[In Catalog](…) · [ACCT199](…)**: Save the page address as ACCT199's expected value:
>    `https://avc.elumenapp.com/catalog/2026-27/course/acct199`. ([Jared's note](…))
>    *Then:* the next run publishes the In Catalog rule as drafted: it fills 1,062 courses with their page address.
> 2. **[Description](…) · [ACCT199](…)**: Pick one of the two notes: drop the Limitation on Enrollment text, or
>    leave it in. ([note 1](…), [note 2](…))
>    *Then:* if it goes, [AERO199](…), [CFE114](…) and [NS922L](…) change too: re-mark them.
>
> ## Rule by rule
> | Rule | Asked | Claude tried | Result |
> |---|---|---|---|
> | [Credit Value](…) | [Jared on ACCT199](…) | Leave Credit Value empty | Not published: [Credit Unit Type](…) reads Credit Value, so 998 of its values would vanish, [ACCT199](…) among them. |
>
> ## Claude's last try (not published)
> 0 now right · 1 still wrong ([ACCT199](…)) · 0 that were marked correct and would change · 40 unchanged
>
> [This report](…)

**Why this is the simplest option and uses the fewest tokens (decision 3):**
- Claude writes ids (`ACCT199`, `an-7f3a`), about 3 tokens each, instead of copying about 30 links of about 30 tokens
  each. No list of links to fetch, copy or check.
- Links can't be wrong, because the CLI builds them. Only the ids need checking: the rule exists, the rule has a row
  for the course, the annotation exists. A bad id makes `run done` refuse with one line per problem
  (`to_do[1].notes: an-91c9 is not an annotation on course-description`), and Claude fixes the JSON and runs it again.
  That's the cheapest loop: short errors, and only when Claude made a mistake.
- Section order, headings, verdict words, the scorecard and the "this report" link stay the same on every run,
  whoever writes the JSON.

**Course codes and rule ids inside text** (`then`, `why`, `notes`): the CLI links every word that is one of the
catalog's course codes, to that item's rule, and every rule id, to the rule, shown under its Studio name. Claude does
nothing extra. To link a course in a different rule, Claude writes `ACCT199@course-credit-value-credit-unit-type`.
A word the CLI doesn't recognise stays plain text, so a stray code never breaks the report.

**The scorecard comes from the CLI:** `rule try` saves its result in the run's folder (it can already print it as
JSON), and `rule publish` does the same. The report shows the last one, in plain words: *now right / still wrong /
were marked correct and would change / unchanged*, replacing *fixed / still wrong / newly wrong / UNKNOWN*. Claude
doesn't type numbers, so they can't be mistyped.

### 5.2 A third ending: "Claude needs your decisions"

`ending` is one of:

| ending | When | Run bar | Icon |
|---|---|---|---|
| `published` | a new ruleset was published (possibly with to-dos left) | **Claude published ruleset v10** | approved |
| `needs_you` | nothing published, because only a person can unblock it | **Claude needs N decisions from you** | a question mark, not the error one |
| `failed` | something broke (install, storage, a command that errors) | **Claude couldn't finish** | needs work (as today) |

A run that ends `needs_you` with an empty `to_do` is refused, and so is a `failed` run with no reason. The outcome
line in the run bar is the CLI's headline, not free text. `--failed`, `--outcome` and `--summary-file` stay for runs
the Studio ends by itself (timeouts, couldn't connect) and for older prompts.

### 5.3 The prompt

`_run_close` shrinks to: the `report.json` fields with one sentence each, the three endings, "name things by id; the
CLI makes the links", and "write for someone who knows the catalog but not these tools: no file names, ruleset ids,
command names or JSON field names". `run done` prints the rendered report, and Claude gives it as its reply.

### 5.4 Open questions

**R1. Is `needs_you` its own state in the Studio**, so the run history and the run bar can tell "waiting on you"
from "broke"? Default: **yes**. Today's `failed` runs stay as they are.

**R2. Free text.** `notes` is the only free-form part (Claude's observations that fit no section). Keep it, capped at
about 5 lines? Default: **yes**.

**R3. Is "Claude needs 5 decisions from you" the right headline?** Each item is one thing to do in the Studio. Other
wording: "5 things to fix before Claude can publish". Default: **"Claude needs N decisions from you"**.

**R4. Show the to-do list outside the report?** For example, a small "Claude asked" mark on each row named in
`to_do`. Default: **no**. The report's links take you to the row, and the Studio keeps new UI to a minimum. Say if
you want it.
