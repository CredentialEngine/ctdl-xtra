# S — Spec: run reports the CLI writes, with links (2026-11-04)

Decisions: [`02-research.md`](02-research.md) §1 (pass 1) and [`answers-pass2.md`](answers-pass2.md) (pass 2,
verbatim). In short: Claude writes facts by ID, and the CLI checks them and writes the report. There's a third
ending ("N things to fix before Claude can publish"). The run bar says only how the run ended, and a button opens the
details. Claude keeps a short notes section. Nothing new is added to the Rules tab rows beyond the `?note=` outline
(R4: no).

## 1. Report file (`report.json`, written by Claude)

```json
{
  "ending": "published | needs_you | failed",
  "summary": "one or two plain sentences (optional)",
  "reason": "failed only: what broke, one line",
  "to_do": [{"rule": "<rule id>", "course": "<course code, optional>", "notes": ["<annotation id>", "…"],
             "do": "what the reader does", "value": "the value to save (optional)", "then": "what happens next (optional)"}],
  "rules": [{"rule": "<rule id>", "asked": ["<annotation id>"], "tried": "what Claude tried",
             "result": "published | not published | not tried", "why": "optional"}],
  "notes": "free text, at most 5 lines (optional)"
}
```

Checks (`run done` refuses with one line per problem, and nothing is written):
- `ending` is one of the three; `needs_you` needs at least one `to_do` item; `failed` needs `reason`; `published`
  needs a ruleset newer than the run's starting one.
- Every `rule` is in the catalog's latest ruleset. Every `course` is a course of the catalog. Every annotation id is an
  annotation of that item's rule. `do` and `tried` aren't empty. `notes` is at most 5 lines.
- Unknown fields are refused, so a typo doesn't silently drop text.

## 2. Rendering (the CLI writes `summary.md`)

Always in this order. Sections with nothing in them are left out.

1. **Headline** (also the run's `outcome`): `published` → "Claude published ruleset vN"; `needs_you` → "N things to
   fix before Claude can publish" (1 → "1 thing"); `failed` → "Claude couldn't finish: <reason>". Then the catalog,
   and the ruleset ("ruleset v9 unchanged" or "v9 → v10, Compare").
2. `summary`.
3. **What you need to do**: a numbered list. Each item: **rule name · course** (links), `do`, the `value` in code,
   annotation links ("Jared's note", "note 2" …), and *Then:* `then`.
4. **Rule by rule**: a table: Rule | Asked (annotation links, named by author) | Claude tried | Result (+ `why`).
5. **Claude's last try** (not published) or **What publishing changed** (published): from the last `rule try` or
   `rule publish` of the run (§3), totals as *now right · still wrong · were marked correct and would change ·
   unchanged*, then the courses still wrong or that would change, per rule, as links.
6. **Notes**: `notes`.
7. "[This report](…)".

Links (`<studio>` = the Studio address saved with the run; every link opens a new tab):

| What | Link |
|---|---|
| rule | `<studio>#/c/<catalog>/rules/<rule>` |
| course in a rule | `…/rules/<rule>?row=<course>&by=anyone` |
| annotation | `…/rules/<rule>?row=<course>&by=anyone&note=<annotation id>` |
| Compare | `<studio>#/c/<catalog>/compare?a=<before>&b=<after>` |
| this report | `<studio>#/c/<catalog>/rules?run=<run id>` |

Text fields (`summary`, `do`, `then`, `tried`, `why`, `notes`): a word that is a course code of the catalog links to
that course in the item's rule (or the rule's page, in `summary`/`notes`, which have no rule). A word that is a rule id
becomes the rule's Studio name, linked. `ACCT199@<rule id>` links a course in another rule. Anything else stays text.
A run with no Studio address (started outside the Studio) gets the same report without links.

## 3. CLI

- The run folder's `golden-datasets.env` also sets `GOLDEN_DATASETS_RUN=<run id>`. With it set, `rule try` and
  `rule publish` save their scorecard to the run (`agent-runs/<run id>/last-try.json`), and `run done` /
  `run note` default `--run` to it.
- `golden-datasets run done --report report.json` checks, renders, saves `summary.md` + `report.json`, ends the run
  (state `finished` for `published`, `needs_you`, or `failed`), and prints the Markdown. `--outcome`, `--failed`
  and `--summary-file` still work (old prompts); `--report` replaces them.

## 4. Studio

- **Start:** the browser sends its address (`location.origin + pathname`); the run keeps it as `studio_url`.
- **New state `needs_you`** ("Things to fix"): ended, like `failed`, but with the question icon and a neutral
  (yellow) background, not red. The run also keeps `to_do_count`.
- **Run bar, ended run:** only *how it ended*: "Claude published ruleset v10" / "5 things to fix before Claude can
  publish" / "Claude couldn't finish" / "Run cancelled" … · started by X. No outcome text. Buttons: **Read the report**
  (+ Compare when it published).
- **Report panel and past runs:** the same words; the details (the outcome line and the report) stay there.
- **`?run=<id>`** on any catalog page opens Past AI runs on that run, then drops the parameter.
- **`?note=<annotation id>`** with `?row=`: the row's history outlines that annotation and scrolls to it.
- **Markdown links** show the external-link icon after the label (they already open a new tab).

## 5. Prompt (`_run_close`)

Replaced by: write `report.json` (the fields above, one line each), name things only by id (the CLI makes the links),
the three endings, "write for someone who knows the catalog but not these tools: no file names, ruleset ids, command
or field names", end with `golden-datasets run done --report report.json`, fix whatever it refuses, and reply with
the Markdown it prints.

## 6. Tests

Python: checks (each refusal), rendering (sections, links, auto-linking, no Studio address), the `needs_you` ending,
`last-try.json` saved by `rule try`, the env default for `--run`, the prompt text. Web: bar words per state and no
outcome text, `?run=` opens the panel, `?note=` outline, the link icon.

## 7. Review: a simulated run

AVC is copied to the scratch prefix `zz-scratch-report-links-sim/` of `xtra-cli-output`, so the run never touches
the shared Studio's data. A local Studio on that root starts a real run, and a stand-in agent service takes the
prompt. A Claude subagent that sees only that prompt does the run against Azure. Eric then reads the report in the
local Studio.
