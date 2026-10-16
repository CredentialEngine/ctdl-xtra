# Every input, cleaned up

Eric's inputs to Claude Code while making the xTRA mockup, in order. Most were dictated by voice. Here they
are tidied: filler words and false starts are removed, transcription errors are fixed ("CDTL" → CTDL,
"crispy" → QRSPI, "Quen" → Qwen), and long read-alouds are broken into points. Meaning is unchanged; nothing is
added. For the exact wording, see [03-inputs-verbatim.md](03-inputs-verbatim.md).

All of this happened on 7 and 8 October 2026, in three Claude Code sessions, following Q.R.S.P.I.
(Questions → Research → Specification → Plan → Implement).

---

## Phase 1 — The prompt (Wed 7 Oct, 3:14 PM)

The original prompt is in [01-original-prompt.md](01-original-prompt.md). In short: start from the University
of Arkansas course catalog; crawl it; extract courses into valid CTDL using rules where possible and a local
language model where not; **remember the exact region of the page behind every extracted value**; build a mini
web app with the source on one side and the JSON-LD on the other, where clicking a field scrolls to and
highlights its source and shows the reasoning (the rule that matched, or a language model's argument citing
the CTDL definition).

---

## Phase 2 — Answering Claude's questions (Wed 7 Oct, 3:27 PM)

Claude asked ten clarifying questions. Eric answered them aloud:

1. **What does "valid CTDL" mean?** Well-formed JSON-LD using real CTDL terms. Find a concrete example JSON-LD
   object from Credential Engine. Target the Registry's required and recommended properties and validate
   against the published CTDL schema, *without publishing*.
2. **Is each catalog entry a `ceterms:Course`?** "I think it's a course, but you tell me." Make the case.
3. **Required fields the page doesn't contain** (CTID, owning organization, language, lifecycle status)?
   Don't assume them. Actually look them up and discover them.
4. **How much to scrape?** Two separate steps. A **crawl** step that keeps lookup information so pages and
   documents (PDFs, images) are never fetched twice — no unnecessary load on the site. An **extract** step
   (rules and model calls) that only reads the cached files. Build it to handle all 168 subjects, but run on
   a small subset (three to five) for now.
5. **How structured should prerequisites be?** "I don't know enough about CTDL to know the trade-offs. I need
   you to tell me."
6. **Can the source pane be a local snapshot?** Yes — but make it reliable, because other sites may use
   JavaScript or be login-protected. Preserve style and formatting as much as possible. Link to the original
   as deeply as possible, at least for the highlighted regions, "to maximize how traceable and verifiable this
   all is."
7. **Use Qwen 3.5 9B?** Yes, with structured JSON output, and verify its quotes are real substrings of the
   source. Chosen because it's already installed, not because it's known to be good.
8. **Stack?** Python pipeline run with `uv`, emitting static JSON; a small Vite + React viewer, no backend.
9. **Should the viewer support review?** Read-only for v1. But later: reviewers must be able to **accept,
   reject or correct** each field, **annotate why** ("where they think we went wrong"), and have a
   **streamlined, structured experience — tabbing field by field** so they can annotate and move on.
10. **One-off or general?** Think only about this one site for now. Keep the rules as a declarative registry
    anyway, for readability. Generalization comes later.

Housekeeping: save the questions and answers in a `qrspi/` folder; do the work in a repo called
`xtra-mockup`; save the original prompt as `qrspi/prompt.md`.

**On the research questions**, Eric realised he was a CTDL novice:

> "I understand that it's a data model for representing credentials and learning programs, but that's the
> extent of my knowledge. So any time the definitions can provide an example of what the different values
> might be, and maybe links to all your options, that would be a good thing — to help the human understand
> what they're doing here. This exercise is allowing the humans to correct, and it's also **teaching the
> humans** and helping them become more expert themselves. That's a theme I want to capture."

---

## Phase 3 — Reading the research aloud (Wed 7 Oct, 4:36 PM)

Eric read Claude's research document aloud and reacted as he went. Claude then recorded these as comment
threads in `qrspi/02-research.md`. The substantive reactions:

**Sources and trust**
- "Each catalog entry is a `ceterms:Course` … 48,000 courses are already published under that type" —
  "I'm interested to see how you know that. I'm a little bit skeptical, since you didn't cite a finding."
- Worried the copy of credreg.net might be out of date versus the live CTDL pages. Fine to use the downloaded
  copy, but **"call that out visibly in a final report somewhere."**
- Confirmed: don't publish anything — "we don't know how valid it is."
- Credential Engine has a public `ctdl-xtra` repository doing the same job: "I would like you to study it,
  actually."

**CTIDs and design**
- CTID minting: follow domain-driven design to a degree — keep minting as pure as possible, depending on as
  few objects as possible, the way services are meant to work in DDD. "Don't go overkill with the
  abstractions. I just want thought to have gone into the organization."
- Minted CTIDs must be idempotent (a ledger), never a new CTID for the same course on re-run. Agreed.
- New catalog year = new CTID? Follow-up question: **what does Credential Engine recommend**, and what are the
  actual trade-offs — what do you gain or lose either way?

**Learning CTDL (the teaching theme)**
- On the Brookdale example record: why does one `requires` entry hold several alternatives? "I would have
  expected one entry per course. Could this be expressed more granularly in CTDL? Should it be, and can it
  be?"
- Why is `inLanguage` an array — does a course alternate languages, or can you pick a version?
- Why is `creditValue` a list with one `ValueProfile` in it? What would several mean? Why a ValueProfile?
  > "Whenever one of these choices is made, we also need the **rationale for why each value was used instead
  > of alternatives** — to help us learn the schema."
- "Profile … the wrapper used to pick a value from a concept scheme" — "That does not make sense to me.
  There's a lot of abstractions here."
- The variable-credit note (`minValue`/`maxValue`) was badly worded, "but with clearer wording this would be
  a good note to teach people about the schema inline."
- Concept-scheme values carrying their own label and definition: "handy for the teaching UI."

**Data quality observations**
- Published courses don't list prerequisites, corequisites or offer frequency at all: "That is shocking, to be
  honest. I find that kind of irresponsible."
- Prerequisite in the example record is plain text inside a ConditionProfile: "odd and unjustified."
- "I don't want to give up on prerequisite logic. I want to make sure we do that."
- "The evidence for one field can sit on a different page from the course itself — that's definitely going
  to be true. So we probably have to **display multiple previews**."

**Rules vs. the language model**
- Mapping "Typically offered: Fall, even years" to a frequency concept with a lookup table instead of a
  model: "I'm open to attempting a rules-based thing. **We just need a way to evaluate it.**"
- The model got and/or logic wrong in probes: "We don't necessarily need to worry about how good the model is
  right now. We'll plug in any model and evaluate and improve it later."
- Loved the measurements of the model probe: "These are fantastic metrics."

**Provenance**
- Store position *and* quote (W3C Web Annotation style) so stale anchors are detectable — yes. "Computing a
  digest of the pages would also make sense."
- The list of evidence types (one text segment; several on a page; a segment on another page; markup that
  isn't visible; an external record; derived from another value; no source at all) — "This is such a good
  list. This is the best. This is so valuable." **"We're going to want ways to surface all of those."**
- For evidence that lives in markup, not visible text: "Maybe we should have a way to **toggle between an
  HTML DOM tree view and a rendered view.**"
- Text fragments (`#:~:text=`) for deep links to the live page: "That's amazing. If that works, do that."
- JavaScript-rendered or login-protected sites: not needed now, but note it as a future risk.

**Words**
- "Model" is ambiguous — say *language model* or *machine learning model*.
- Don't say "span" unless it's an HTML `<span>`; say **text segment**. "Shape" for data structure was
  confusing.
- "Make a note" means: add it to a **`risks-and-future-considerations.md`** document.

**Process**
- Reading a markdown document aloud should work like Google Docs comments: Claude should inject Eric's remarks
  as comments next to the passage, as markdown that renders in GitHub and VS Code, **and reply** to any that
  ask a question.

---

## Phase 4 — Reviewing the specification and its mockups (Wed 7 Oct, 4:45 PM and 5:12 PM)

Asked for: draft the spec, with mockups of each area embedded as images, so the whole thing reads from the
markdown file.

Reaction to the first mockup:

- "This looks really exciting. But the whole mockup looks a bit busy." Use **progressive disclosure** so the
  user isn't overwhelmed on arrival. The first screen should be much more bare; detail appears as you click.
- A **maximally verbose view** is welcome as an option, "but beginning with that is way too much. I think
  there's an in-between." (→ Brief / Standard / Full.)
- A small copy icon instead of a "Copy" button. Reduce busyness in general.
- **The review loop:** "I imagine a linear experience where verifiers go through an outer loop verifying each
  course and other resource one at a time. For each of those, the inner loop is they tab through each of the
  values and resource-type choices that were made — with the option to focus on judgement-based ones, like
  the ones from a language model. Our rules might be wrong too, but they're less likely to be."
- **Value vs. choice of field:** "Sometimes it's the value of the field we're verifying, and sometimes it's the
  choice of field — we're trying to defend why we used that field over the alternatives."
- A way to unfold all fields in the JSON-LD.
- Show all the documents involved in a resource more clearly, without visual busyness.
- Decisions: each entry is a course (yes); bare name with the code in its own property (fine); the acceptance
  criteria "look great."

---

## Phase 5 — Building and refining the viewer (Wed 7 Oct 6:10 PM – Thu 8 Oct 1:14 PM)

"Build the mockup app from the specification." Then, while it was being built and after, a steady stream of
review feedback. Grouped by theme, in roughly the order given:

### Layout and look

- **Make the source side look like a browser**, "kinda like how this take on the problem looks" (an
  "xTRA Labeling Studio" design):

  ![The "xTRA Labeling Studio" reference Eric pasted](images/input-labeling-studio-reference.jpeg)

- Default the record to a **non-JSON view** (cards like the screenshot), with JSON one click away. Each card:
  **accept**, a **confidence** of low/medium/high, a way to **edit** the value, and — with a field selected —
  **drag across the page to re-attribute** the evidence if you don't like the system's choice. In the name of
  progressive disclosure, clicking the confidence reveals all the reasoning.
- Layout left to right: a **show/hide sidebar** of every course and other CTDL resource under review → the
  CTDL record → the browser on the far right.
- Make the value visually distinct — a text-box-like bubble in a distinctive font — "while simultaneously
  avoiding useless visual clutter."
- Rename the views: **Pretty** and **Raw**. Copy belongs only in Raw.
- "Low/medium/high" text is clutter: use a **colour-coded right border** instead.
- "It's not obvious what the red circles mean." → recognisable icons (warning triangle; star for language
  model).
- Sidebar show/hide is clunky: smooth animation. Same for the info box expanding.
- Sidebar shows **progress**: a check or shade on finished items, a faint progress-bar fill behind each subject
  (e.g. ACCT); later, every row is itself a progress bar.
- Default the HTML tree view to fully expanded.
- Rename to **"xTRA Review"**; remove the format-check dropdown, the "Not published" notice and the menu; add a
  **"Show the tour"** button.
- The "valid ✓" next to the record heading "is semantically confusing. Due to its placement it's seemingly
  communicating that all the fields are confident." (→ removed.)
- In Pretty, the card "jumps around" when you go to click; put action buttons **beneath, bottom-right**; the
  card can grow on hover.
- The icons down the right of Raw only link back to Pretty: reduce them.

### Traceability

- **"For both views, ANY value string that I click: if it came directly from the source document, it should
  take me there."**
- Leave the definition tab and go to the source when a value is clicked.
- Make it easy to switch a field between Pretty and Raw (`V`).

### Explaining the machine's reasoning

- A failed check read "like a 5-paragraph essay instead of a structured response." Make rule vs. violation
  visually distinct.
- Still "better but not there yet. **If it's missing specific entries, say it. We need more specifics.**"
- "Make it more obvious what the output of the language model is."
- **"'A rule read it' — can you go deeper? What was the rule?"** Every rule needs an identifier, a plain
  description, a more visual way of showing how it works, and its code (the regex). **Hovering the regex
  should light up what it matches on the page.** Raw defaults to Full detail.

### Teaching CTDL to the reviewer

- Click a field name (not hover; hover only underlines) to open its **CTDL definition as a tab** in the
  browser frame. `ceterms:Course` at the top should link too and look clickable.
- Make definition pages richer: "Holds: Value Profile" should link to Value Profile. Then: show everything
  CTDL's own term page shows (URI, label, definition, comment, usage note, type, status, domain, range,
  history).
- A list of enum codes (`lifeCycle:Active`, `lifeCycle:Ceased`…) isn't enough: **"If I'm a reviewer, I need to
  know this kind of thing to be able to assess xTRA's judgement in whether it assigned the right one."**
- Terms like "URI", "Label", "Range Includes" — if Credential Engine defines them, link them to a glossary.
  Make `https://` URLs clickable.

### Editing, for non-technical reviewers

![The JSON editor Eric rejected](images/input-json-editor-complaint.png)

- **"This is not a good editing experience. Non-technical users should be able to use this and they don't
  know JSON."** It's bad for arrays, doesn't let you choose the CTDL type, and ignores CTDL's multi-select
  items. "I believe CTDL has a tool to manually enter courses — go explore it and gain some ideas from it."

![The "Kind" vs. label question](images/input-kind-vs-label-question.png)

- "Should the prerequisite label be a different field from the Kind dropdown? Would these ever be different?"

### The review workflow

- **`R` to reject**, which puts the cursor in a popup asking why. **`C` to comment.** "Rejection always comes
  with a comment. But you can also just leave a comment and move on. That counts as acknowledging it."
- Show the course type's **other properties** that xTRA made no proposal for, as blanks with a grey right
  border; a small faint red asterisk on required properties.
- Hovering a button for a second shows its shortcut icon and label.

### The CTID / "already in the Registry?" question

- "We need an algorithm to **stably come up with the CTID** for a resource and **check the Registry** to see if
  it already exists. So the reviewer would be verifying whether the course already exists or not." Stub it in
  the UI.
- The probable approach: depending on the class (e.g. course), look up the course ID in the Credential Finder
  database.
- Then: make it simply the **CTID field**, first in the record, with a "not built yet" callout that opens the
  detail.

### Onboarding tour

- On first open, walk through the user flow:
  1. These are the proposed CTDL resources after running xTRA.
  2. Field by field, accept or reject xTRA's proposed value. Red/yellow/green is **xTRA's own confidence** in
     its recommendation.
  3. Clicking a field shows which elements of which pages informed the value — sometimes a visible element,
     sometimes only in the raw HTML, sometimes the URL. Highlight ("un-grey") an example field so it's clear
     which value is being demonstrated.
- Further steps: clicking a `ceterms:` name shows what the field should contain; xTRA's reasoning for a value;
  an edit step showing a pick-list; rejecting with a reason; the CTID check; the blank fields. Show the
  keyboard shortcuts with the same icons as the UI. Show what the sidebar looks like as you progress.
- "I worry the demo won't show to people. Since this is a mockup, **just always show the tour on page load.**"

### Keeping the spec honest

- "I've asked for many things and we've improved the UI a lot. Please **update the original spec to ask for
  the things I've asked for**, and add better screenshots." Later: "reflect the recent additions to the spec."
  (→ `03-specification.md` now lists every request as C14–C60, each mapped to a numbered requirement.)

### Sharing

- Build the whole site into **one HTML file** with no backend, "such that I can share the one HTML file with my
  non-technical team members." Verify it's high-fidelity.
- Commit, push and deploy to the homelab.
