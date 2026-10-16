# Q — Questions and answers

Phase 1 of Q.R.S.P.I. for the xTRA mockup: extract University of Arkansas catalog courses into
CTDL JSON-LD, with field-level provenance shown in a side-by-side viewer.

- Start page: <https://catalog.uark.edu/undergraduatecatalog/coursesofinstruction/>
- Asked and answered: 2026-10-07
- Answers below are Eric's, dictated by voice and tidied for readability. Nothing has been added to them.

## The original request, in brief

1. Scrape the catalog (a web scraper is fine for phase one).
2. Extract key fields by predictable patterns and locations (regex-matchable rules).
3. For fields that are ambiguous and not discoverable by a rule, use a local ollama model or another probabilistic method.
4. For **every** extracted value, remember the exact region of the page it came from.
5. Build a mini web app: source documents on the left, extracted JSON-LD on the right. Clicking a field must
   - scroll to and highlight the source region, and
   - show the reasoning: the deterministic rule that matched, or a snippet of AI reasoning that cites the CTDL
     definition and argues why the highlighted text satisfies it.

## Decisions

| # | Question | Answer |
|---|----------|--------|
| 1 | What does "valid CTDL" mean? | Well-formed JSON-LD using real CTDL terms. Target the Registry's required and recommended properties and validate against the published CTDL schema, **without publishing**. Find a concrete example JSON-LD object from Credential Engine. |
| 2 | Is each catalog entry a `ceterms:Course`? | "I think it's a course, but you tell me." Make the case. |
| 3 | Required fields the page doesn't contain (CTID, owning organization, language, lifecycle status)? | Do not assume them. Actually look them up and discover them. |
| 4 | How much to scrape? | Two separate steps. **Crawl**: runs over some number of pages and keeps lookup information so that pages and documents (PDFs, images) are never fetched more than once. **Extract**: rules and model calls run only against the cached files. Build it so it could run over all 168 subjects, but for now use a small subset of five. |
| 5 | How structured should prerequisites be? | "I don't know enough about CTDL to know the trade-offs. I need you to tell me." |
| 6 | Can the source pane be a local snapshot? | Yes. Make it reliable, because other sites may use JavaScript or be auth-protected. Preserve style and formatting as far as possible. Link to the original as deeply as possible, at least for the highlighted regions, to maximise traceability and verifiability. |
| 7 | Use `qwen3.5:9b`? | Yes, with structured JSON output, and verify that quotes are real substrings of the source. Chosen because it is already installed, not because it is known to be good. |
| 8 | Stack? | Python pipeline run with `uv`, emitting static JSON. Small Vite + React viewer, no backend. |
| 9 | Should the viewer support review? | Read-only for v1. See "Later versions" below. |
| 10 | One-off or general? | Think only about this one site for now. Keep rules as a declarative registry anyway, for readability. Generalisation comes later. |

## Housekeeping instructions

- Do the work in a repo at `~/repos/xtra-mockup`.
- Keep Q.R.S.P.I. documents in a `qrspi/` folder: this file, then a research document.

## Later versions (captured now, not built in v1)

- Reviewers can **accept, reject or correct** each field.
- Reviewers can **annotate why** they made a correction: where they think the extraction went wrong.
- The review experience is **streamlined and structured**, for example tabbing field by field so a reviewer can annotate and move on.

## A theme to carry through

Eric describes himself as a CTDL novice: he knows it is a data model for credentials and learning programs, and
not much more. The tool's users will be in the same position. So:

- Wherever a definition is shown, include **examples of the values it can take** and **links to all the options**.
- The exercise has two purposes at once: it lets humans correct the machine, and it **teaches humans**, making
  them more expert as they go.

## Research questions approved

Several of these used terms Eric did not recognise ("ACTS equivalency", "title-line variants", "labelled
sentences", "cross-listing"). They are approved as research topics, and the research document explains each in
plain language.

**CTDL**
- Exact domain, range and definition text for each candidate property, from the live schema.
- The Registry's minimum required set for a course.
- Whether credit value should carry semester-hour units; which concept schemes cover offer frequency and delivery type.
- Whether "ACTS Equivalency = ACCT 2003" has a faithful CTDL home.
- How corequisites, cross-listings and "may be repeated" are modelled.

**Source data**
- How many title-line variants exist.
- Which labelled sentences occur in descriptions and how often.
- Which fields are truly rule-resistant and need the LLM.
- Whether course codes encode level or credits.
- Whether subject pages carry department or college context.

**Provenance mechanics**
- Which anchoring scheme survives re-rendering.
- How to represent multi-span evidence and derived values.
- How reliably the 9B model returns verbatim quotes.
