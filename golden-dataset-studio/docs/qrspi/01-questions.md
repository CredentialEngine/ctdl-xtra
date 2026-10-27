# Q — Questions

Phase 1 of QRSPI (questions, research, structure, plan, implement) for the **rule-centric review UI**, now called
**review-ui-v3**. Today's tool (v2) is built around pages and records: you open a page and accept or reject the
values on it. v3 is built around rules: you pick a rule (for example "locate and extract Course ID"), see every
value it produced across the whole catalog, annotate the records where it went wrong, give those notes to Claude
Code, publish a new version of the rule, rerun it, and compare the two versions.
Extracted values are immutable and disposable. **The rules are the thing that changes.**

- Original prompt: [`prompt.md`](prompt.md)
- Folder: `review-ui-v2/qrspi/` for now (moves to the v3 folder once it exists, see A8.2)
- Asked and answered: 2026-10-26
- **The goal of QRSPI here is a spec and an order of work. The build doesn't start in this process.** Code is
  written or run only when it helps answer a question.
- Answers are Eric's, dictated by voice and tidied only for readability. Notes from Claude are marked **Note** and
  kept separate from the answers.
- Part D holds the second pass of questions. Eric asked me not to wait for answers on those, so each one records the
  assumption research works from.

### What I already looked at (so the questions are grounded)

- **Rules already have IDs, and values already record where they came from, partly.** `engine.py` gives every
  extracted field a `rule_id`, and every entity a `root_path`, `index` and a `css_path` that the browser can resolve
  again. That provenance is dropped when you **Save golden dataset**: `golden.py` keeps only `ctdl_property`,
  `value` and `source_url`.

  > **Answer:** Honestly, I think that's maybe good. Some people said it was too noisy, where it was found on the
  > page. Then again, maybe not. Where you found it on the page is an immutable fact, so I think there's a case to
  > keep it in the same table as the things found.

- **Versions apply to the whole ruleset, not to single rules.** `rules publish` refuses a `version` that is not
  higher than the published one, and only the latest ruleset is kept.

  > **Answer:** Yeah, that makes sense. What do you think? Is there a downside to versioning individual rules, and
  > then making a ruleset as a set of those versioned rules? We definitely want to be able to iterate on just one
  > rule, but whether that requires a whole ruleset version is maybe less important. I'd like to know your thoughts
  > on the pros and cons.
  >
  > **Note (Claude):** The pros and cons are in research (R-versioning). A1.3 already settles on versioning both.

- **The CSS problem is probably not "we only read `<body>`".** The page pane renders only the `content_root`
  fragment, so site CSS that depends on ancestors can no longer match. That's a new third hypothesis.

  > **Answer:** Great. I love that we have that hypothesis. We should definitely look into how we can render it then.

- **A Claude Code loop already exists, as files** (`export-feedback` → `feedback.md`, plus `ITERATE.md`).

  > **Answer:** Interesting. I didn't see that in the UI in an obvious place. I'd like to see it in action then. If it
  > exists, maybe you could run the UI locally, drive it, and take screenshots with the Chrome MCP server, and make
  > me a little walkthrough: show me how you use the UI, leave an annotation, export this thing, provide it to Claude
  > Code, and then go again. I want to see the entire iteration process as a blog post with screenshots from start
  > to finish, if it already exists. Otherwise, don't worry about it, because we're going to be building this
  > momentarily.
  >
  > **Note (Claude):** It does exist (`review-ui-v2 export-feedback` on the CLI, and **Download → feedback.md** in
  > the UI). The walkthrough is a research item, written as `02a-walkthrough-v2-loop.md`. It runs only against a
  > local copy of the data, so nothing in Azure changes.

- **Extraction writes one small file per record**, and the README calls that the slower part against Azure.
  *(No answer needed.)*

---

## Part A — Questions for you

### A1. What a "rule" is

1. **What is the unit you review: one field rule, or something bigger?**
   *Default: a field rule.*

   > **Answer:** Let's start by being able to look at both types of rules. I don't really understand the difference
   > between a label rule and a field rule, but I can definitely understand that there's a difference between
   > locating which pages and locating stuff on a page. So elaborate on that. But you can go ahead with the decision
   > that I want to be able to review all kinds of rules, and that we need an intuitive user interface and user
   > experience for that.
   >
   > **Note (Claude):** The difference between label rules and field rules is explained in research (R-rule-kinds).

2. **Is "locating the records" a rule you review on its own?**
   *Default: yes, a record locator rule.*

   > **Answer:** Yes, yes, yes.

3. **Should each rule have its own version, or do we keep one version for the whole ruleset?**
   *Default: both.*

   > **Answer:** I like your idea of versioning both. Let's go with that. I really like individual rules and rulesets
   > having their own versions. Maybe we'll talk about this later, but for the diff, we need to publish all the
   > things a rule matched together with the rule, so that we can diff them. Using DuckDB, or whatever we decide on
   > for the backing data store, we should be able to load the extracted values of two versions of a rule for the
   > same record primary key. Maybe we join, or maybe we select a particular record for two different rule versions,
   > so that we can compare them side by side.

4. **Must rules stay declarative?**
   *Default: yes, for now.*

   > **Answer:** Yes, let's stay declarative for now.

5. **One ruleset per catalog (institution), across every crawl of that catalog?**
   *Default: yes.*

   > **Answer:** A crawl should only download the HTML, CSS and JavaScript files. The crawl shouldn't necessarily
   > extract, but extraction should use a single ruleset. I think we should build a separate CLI, so we don't confuse
   > what belongs in xtra-cli: a CLI just for the review UI project, for building these golden datasets. That CLI
   > points to a pile of documents and applies a set of rules. It's out of scope right now to think about changes to
   > xtra-cli. Maybe xtra-cli will one day adopt some of these rules and how we run them, but for now that's
   > completely out of scope.

6. **Only Course for now?**

   > **Answer:** Yes, just Course for now. And only the minimal list of fields for Course, which you can find
   > somewhere; Seth has been working on that. I think it's just the fields considered required for the Course
   > resource type. I think there are about seven, but I could be wrong. Those are the only ones we want to build
   > rules for.
   >
   > **Note (Claude):** It's seven. `templates/course.properties.json` lists seven properties with
   > `"required": true`: External Identifier, Learning Type, Learning Opportunity Name, Description, Subject Webpage,
   > Life Cycle Status Type and Language. Today's rulesets also extract Coded Notation and Credit Value/Min/Max,
   > which aren't on that list. See D1.

### A2. What reviewing and annotating mean now

1. **Does accept/reject still exist in the rule-centric view?**
   *Default: a verdict per (record, rule) of correct / wrong / missing, with an expected value and a note.*

   > **Answer:** Yes, it does exist. It doesn't mean we keep that particular copy of a record. It means we accept that
   > the rule's categorization of the record is correct. Accept says the rule was right about this record; reject
   > says the rule was wrong. But if correct / wrong / missing is more intuitive for the user, I like that.
   >
   > For the expected value: if the UI can let someone select or tag a portion of the HTML document that's already
   > up, that could be a really nice way to indicate what the correct value should have been. If they can highlight
   > a piece of text and the UI captures exactly where that text was on the page, that's really good information for
   > Claude to use in the prompt to iterate.

2. **How do we know a record is the same record after a rule changes?**
   *Default: page URL + record locator position, falling back to the course code.*

   > **Answer:** I think we actually have to use the course ID, unfortunately. You're suggesting the locator's
   > position, but that has the same issue: if the record locators change, you can't join the records together. But
   > doing what you propose and then falling back to matching on the course ID could be OK. To the user, though,
   > anything other than the course ID will be confusing. If you think this is too ambiguous and deserves more
   > discussion, bring it up again after this.
   >
   > **Note (Claude):** I'm bringing it up again in D3. The course code isn't always unique (CCSF program pages make
   > stub records with the same code as the full record), and a value that comes out wrong can't serve as its own
   > key.

3. **When rule v3 replaces v2, what happens to annotations made against v2?**
   *Default: they carry forward as fixed / still wrong / newly wrong.*

   > **Answer:** Yes, because the outputs are immutable and the versions are immutable, so we can keep them around.
   > That helps us track where we've improved or regressed as we iterate on these rules.
   >
   > I like the idea of Parquet files. Maybe we can co-locate them in the folders with the crawls they belong to. If
   > our DuckDB queries are smart enough to understand that folder layout, we can query the files without thinking
   > about where they are. One thing on Parquet, though: I only want to move to Parquet and DuckDB if we think it
   > will dramatically improve performance and our ability to explore this data. That assumption needs to be
   > checked, through more design discussion and an assessment of why it's slow now, before we launch into DuckDB.

4. **Do you tab through every value, or a sample?**
   *Default: every value, with likely problems first.*

   > **Answer:** I think that's a great idea. Surfacing areas of uncertainty, because of missing values or other
   > reasons, is a very important idea. Flesh it out a little more: how might we discover areas of uncertainty for a
   > row? That concept should be made a first-class concept here.
   >
   > **Note (Claude):** This is now **uncertainty signals** in research (R-uncertainty).

5. **How do you record "this course is missing" when the rule didn't produce a row for it?**
   *Default: an Add missing record action on a page, where you select text.*

   > **Answer:** Five sounds great, with one caveat: maybe the course isn't on that page at all. Given a page, yes, we
   > want to be able to identify all the courses on it, so definitely add a missing record action. But there could
   > also be pages we should have looked at for courses and somehow missed. That may be a separate UX, but we need
   > to consider that case too.

6. **Who annotates, and at the same time?**

   > **Answer:** We're never going to have annotators working simultaneously, or if we do, maybe two or three people
   > on the same video call, but not a high volume of things. As long as we keep decisions append-only, it won't
   > matter if several people work at the same time.

7. **How does the golden dataset come out of this?**
   *Default: publish golden from a ruleset version's full extraction plus corrections, with provenance.*

   > **Answer:** That's fine. If we move to DuckDB this would change slightly, but that's fine. One change we might
   > make is to include the provenance data. Rule IDs are not relevant, but the location on the page is certainly an
   > immutable fact.

8. **Flags for an expert: keep them in the rule view?**
   *Default: yes, as a fourth kind of verdict.*

   > **Answer:** Yes, I think flags for an expert are a good idea.

### A3. The rule-centric view

1. **Layout: rules on the left, the rule's values in the middle, the page on the right?**

   > **Answer:** On the left, the rules. I'd want to see something like a red X or a green check mark. Not just
   > emojis, but something pretty that shows whether the rule has been approved and we think it's 100% correct, or
   > it's red, it's been rejected, and there are notes to make it better. In the middle, the rule's values, one row
   > per record, with the page title and verdict: yes, sounds good. I'd like to see a proof of concept; you could
   > work on it and we can massage it together. On the right, the original page with the matched element
   > highlighted and scrolled into view, and Tab moves through the values: yes, I like it.

2. **What do you want to see for each rule at a glance?**

   > **Answer:** I like all those.

3. **Keep the record-centric view as it is, in its own tab?**

   > **Answer:** Yes, apart from my note about a prettier browser [see "Ideas" below], just leave it as is. We may
   > need to talk about the data it captures. Maybe the underlying data format needs to change because we want to
   > annotate things in a rule-centric way. I'll leave it to you to bring that up if you think it's too ambiguous.
   >
   > **Note (Claude):** Brought up in D6.

4. **Whole page or only the content root?**

   > **Answer:** I want to see it rendered beautifully with CSS. Maybe even JavaScript, since there are pop-ups
   > sometimes. If you need to remove scripts, so be it, but sometimes that may get in the way. We'll have to see. If
   > it comes up later, we can change the UI.

### A4. Comparing rule versions

1. **What answers "is this new version a step in the right direction?"**

   > **Answer:** Before I even read this, I'm imagining something like GitHub, where you choose two branches and see
   > the diff between them. In this view you could click on two ruleset versions, and maybe a more granular view
   > lets you choose a rule's versions too. You could diff a whole ruleset or a single rule. It defaults to the
   > latest and the second latest.
   >
   > I worry that a scorecard could get noisy, but some summary statistics would be good. The problem is you don't
   > know what's still wrong and newly wrong. Our domain expert, Jared, only has so much time. So definitely show him
   > anything he explicitly rejected or explicitly accepted before. Default to showing those side by side, so we can
   > see if they're any better. Then, if you have any further insight, show those records in the diff too.
   > Otherwise we can just show a bunch of records after that. If you think that's a bad idea, push back.

2. **Consecutive versions or any two?**

   > **Answer:** Any two, defaulting to the most recent two. [Answered in A4.1.]

3. **Can a new version go live in the UI before you accept it?**

   > **Answer:** I don't know what you mean by "candidate". If we say a rule has passed all scrutiny and we think
   > it's perfect, then yes, I want a life cycle to approve that rule so we no longer need to look at it. But new rule
   > versions need to show up in the UI before they're approved, because we need to see unapproved rules in order to
   > review them and go through this process.
   >
   > **Note (Claude):** So: new versions show up in the UI right away (as "in review"). **Approved** is a separate,
   > deliberate state for a rule that needs no more review. "Candidate" is dropped.

### A5. The Claude Code loop

1. **One rule or the whole ruleset?**

   > **Answer:** Either. It's most convenient if we can do the whole ruleset and publish new versions of many rules
   > at once, maybe a ruleset containing them all, as a batch. But I want the option to do one rule as well as the
   > whole ruleset. We should be able to iterate on one rule at a time. We shouldn't have to address every rule
   > before we can push a fix to one rule, apply it, and see if it fixed things. Realistically, as a domain expert,
   > I'd go through one rule at a time until it's perfect, then move to the next one.

2. **What should the generated prompt contain?**

   > **Answer:** No raw HTML, because that would make the feedback potentially massive. But a reference to it, yes.
   > That reference should be resolvable in whatever file system we're pointing at. Claude should be able to use a
   > deterministic helper tool to fetch all the referenced HTML files into a folder, or use them directly if I
   > already have them on my laptop. We want to be able to point at different sources.

3. **How does Claude on your laptop get the rest of the context?**
   *Default: new CLI commands.*

   > **Answer:** I think this is a nice CLI tool. I'm in favor of it.

4. **How does a new version get off your laptop?**

   > **Answer:** Two things need to be published: the rules, and the things the rules matched, with all the
   > provenance and metadata. That should be researched. The change to DuckDB and possibly Parquet may affect it.

5. **Should Claude check its own work before publishing?**

   > **Answer:** Yes. I don't want to spend human attention on new rulesets that aren't any better. We should have
   > the option to publish anything, but we should only publish ones where we think there's an improvement. That
   > said, as we've discussed, maybe it's not obvious when there was an improvement. If we changed a record finder
   > rule, we may not be sure we're comparing the same courses. That's a good follow-up question to research.

6. **Should the UI ever start Claude Code itself?**

   > **Answer:** No, it should not. I think the loop is: in the UI, running in the cloud, we add some annotations and
   > click a button that gives us a prompt. A developer runs that prompt locally on their laptop. Claude Code
   > generates the rules, fetches the data, runs the rules, and decides if the result is any better. Then Claude uses
   > the tool to publish the results back to the UI, where they can be viewed, and the process repeats. I think a
   > sequence diagram is in order. Generate one to illustrate the flow I just described.
   >
   > **Note (Claude):** The sequence diagram is in research (R-loop).

### A6. CSS in the page pane

1. **Which catalogs and pages look wrong?**

   > **Answer:** I don't know off the top of my head. It's probably all of them. If you don't have a good guess,
   > check yourself in research. I'll make sure you've got a Chrome MCP server.

2. **Is it OK for the pane to load CSS from the institution's live site every time?**

   > **Answer:** If we're not already fetching the CSS, I'd like you to do that. Update the crawler so it grabs the
   > CSS if it doesn't already.
   >
   > **Note (Claude):** The crawler is part of xtra-cli, which A1.5 and A8.4 put out of scope. Brought up in D7.

3. **How close to the original does it need to look?**

   > **Answer:** Fonts and layout, yes, and as close to pixel-perfect as possible. Some catalogs build part of the
   > page with JavaScript, and we remove scripts, so come up with a fallback for when a lot of JavaScript is
   > necessary. Maybe treat those as two separate cases. I do think we should fetch the JavaScript as part of the
   > crawl, in addition to the CSS, so we have a good archive of the data and don't need to put more traffic on these
   > sites.

### A7. Speed and storage

1. **Where and how is it slow?**

   > **Answer:** You need to figure that out.

2. **Are you set on DuckDB as a file that we change in blob storage?**

   > **Answer:** I want you to propose different options, with pros and cons. I also want you to propose a data
   > model, and the data model should address everything we've discussed here.
   >
   > **Note (Claude):** The options are in research (R-storage). The data model itself is the main output of S, and
   > research gives it a first draft.

3. **What should provenance contain for each value?**
   *Default: rule_id, rule version, ruleset version, page URL and file, record locator `css_path`/index, element
   `css_path`, raw text, offsets.*

   > **Answer:** Yeah, good default. I like that.

4. **Should provenance go into the golden output?**

   > **Answer:** Put everything except the rule ID in the review data. [**Note (Claude):** read in context as: the
   > golden output gets all the provenance except the rule ID.] But I do want us to store something that lets us look
   > up the original from a particular record in the golden dataset. Maybe we need primary keys or an association
   > table; I trust you to figure that out. My only requirement is that the final golden dataset contains only things
   > relevant to the domain of golden data. It shouldn't reveal any implementation details. CSS paths are immutable
   > facts, so they're fine. Rule IDs are an implementation detail, so I don't want them in the final golden dataset,
   > but I do want to be able to look up the rule ID that was used for each golden dataset record.

5. **Where did you see provenance before?**

   > **Answer:** I don't know. If it wasn't there, fine. What matters is that it needs to be there.

### A8. Scope, people and timing

1. **Is BYU the first catalog?**

   > **Answer:** No. Only consider the five catalogs we've been using so far.
   >
   > **Note (Claude):** Those are the five with published rulesets in `xtra-cli-output/review-ui-index/rulesets/`:
   > **AVC** (eLumen), **CCSF** (CurricUNET), **Marshall**, **UALR** and **WVU**.

2. **Is this refactor yours alone or shared with Seth?**

   > **Answer:** Consider this a v3, honestly. This is going to be review-ui-v3, so let's keep it in a separate
   > folder from v2. But you're welcome to draw inspiration from v1 and v2.

3. **Is there a date?**

   > **Answer:** Forget that. Let's not talk about dates.

4. **What isn't in scope?** *Login/auth, deploying to Azure, xtra-cli changes, requisites.*

   > **Answer:** Correct, those are not in scope.

### A9. This process

1. **Should research run things against real Azure data?**

   > **Answer:** Yes, just don't mutate anything in Azure. You're welcome to create a subfolder in an existing Azure
   > bucket just for the scratch work, but call out very clearly what it is. I want it to be a scratch area where, if
   > I delete the folder, it'll be as though we never worked on this. I do want the scratch folder to mirror the
   > folder hierarchy we're working with, so you may need to copy in HTML crawls and so on, or run a crawl to
   > populate those folders. Only rerun a crawl if key data is missing, like CSS or JavaScript. Otherwise, just copy
   > the data.

2. **Which steps after Q?**

   > **Answer:** Do another pass on questions, but I'm not going to review your follow-up questions. Once you have
   > the next pass of questions, begin the research.

3. **Commit these files or keep them local?** *(Not answered. Kept local for now.)*

---

## Ideas Eric added while answering

These came up between questions. They're requirements, not answers to a particular question.

- **I1. Each rule describes itself in prose.**

  > A big idea I have: rules should have a description of what they're looking for and how they're looking for it,
  > the *what* and the *how*. I want the prompt and the data model to encourage Claude to store these as two
  > separate values. They should be human-readable prose. The audience is both engineers and the product owner. The
  > product owner is fairly aware of HTML and documents, but we still want to keep it high level. A third value we
  > should capture is *why* Claude thinks this is an improvement: why this approach is good and why it improves on
  > the last approach. That one is only valid if there was a previous version of the rule.

  > **Note (Claude):** The answer says "all four of those things" but names three: *what*, *how* and *why it's
  > better*. My guess is that the fourth is the existing `description`, or the example input/output. Listed in D10.

- **I2. A prettier browser, like v1.**

  > I really like my original review UI that I committed. I thought its browser was clean: it had the buttons and
  > tabs, and it let you learn about and explore the CTDL. Look at how we might change the way the browser looks in
  > the UI to make it prettier, like review UI v1.
  >
  > **Note (Claude):** "v1" here is Eric's **xtra-reviewer mockup** (`xtra-mockup/`, commit `a88c93f`, branch
  > `docs/mockup-human-inputs`), not the `../review-ui` folder Seth's README calls v1.

- **I3. Develop locally against two kinds of storage.**

  > As we work on this, I don't want to rely on deploying to Azure. It'd be nice to develop locally. Maybe I could
  > have a scratch path in Azure that keeps the real data paths clean. That would let me check realistic load times,
  > since keeping the data remote is a good indication of how it will work in production. We could also have a
  > version where we download certain things from Azure in advance to a local file system, and a local UI works
  > against that. I think both would be good. Any reads and writes should be able to point to either location.

---

## Part B — Facts I'll find out myself (research phase)

Unchanged from the first pass. Research also covers the new items marked **R-…** in the notes above.

- B1. The exact shape of each extraction output, and where provenance fields are dropped.
- B2. Whether a value can be traced back to a ruleset version; how hard a per-rule content hash would be.
- B3. How decisions, notes and flags are keyed today, and how carry-over works.
- B4. What makes first paint slow (measured against Azure).
- B5. How long a full `extract` takes; whether rerunning one rule would make a real difference.
- B6. DuckDB + Parquet on Azure: whether it works with our credentials, and how fast it is.
- B7–B9. CSS: whether the stylesheet URLs load, the ancestor-selector hypothesis, and smaller causes.
- B10–B11. What the rule format can express; whether one rule can run on its own.
- B12. ~~BYU~~ The five catalogs: platform, page count, crawl, and review state of each.
- B13. Whether v2 is deployed anywhere.
- B14. What `feedback.md` / `ITERATE.md` contain.

---

## Part C — Work streams and order (updated after the answers)

The answers change three things: v3 is its own folder with **its own CLI** (separate from xtra-cli), the **crawl
needs CSS and JS** (which touches xtra-cli, see D7), and **local development against either Azure scratch or a local
folder** is a requirement of its own.

| # | Work stream | Depends on | Can start now? |
|---|---|---|---|
| W0 | **Storage switch + Azure scratch mirror** (I3): one store interface over local and Azure, plus a scratch prefix that mirrors the real layout | nothing (v2's `Store` is a starting point) | **Yes** |
| W1 | **Page rendering**: full-page render, CSS (and JS) archived, a fallback for JS-heavy pages | crawl assets (D7) for the archive part | Investigation yes |
| W2 | **Speed**: measure, then decide JSON vs Parquet/DuckDB | nothing | **Yes, first** |
| W3 | **Data model**: rule and ruleset versions, immutable match sets with provenance, record keys, append-only annotations, golden + association table | W2 result, D-answers | Design yes |
| W4 | **v3 CLI**: extract (all rules or one), `rule try`, context commands, publish rule + matches | W3 | After S |
| W5 | **Rule-centric UI** + v2-style record tab + prettier browser (I2) | W3 shape; proof of concept can use today's JSON | Proof of concept yes |
| W6 | **Compare versions** (GitHub-style, Jared's past verdicts first) | W3, W4 | No |
| W7 | **Prompt generator** + the Claude loop end to end | W3 annotations, W4 commands | No |

Order: **W2 → W3 → W4 → (W5, W6) → W7**, with W0 and W1 alongside. A final version will be in the plan.

---

## Part D — Second pass of questions

Eric isn't reviewing these. Each one records the **assumption research and S will work from**, unless he overrides
it later.

**D1. Which fields are in scope?** The seven `required` properties in the template (External Identifier, Learning
Type, Learning Opportunity Name, Description, Subject Webpage, Life Cycle Status Type, Language), or those plus Coded
Notation and Credit Value, which the rulesets extract today and which hold the "course ID" Eric keeps mentioning?
*Assumption: the seven required ones plus Coded Notation, because the record key depends on it (D3). Credit Value is
left out. Research checks which property is "course ID" on each catalog (External Identifier vs Coded Notation).*

**D2. Kinds of rule in v3.** *Assumption: three kinds, all reviewable: **page rules** (which pages hold Course
records: today's `page_types` and label rules), **record locator rules** (where on a page each course record
starts and ends: today's `repeat`), and **field rules** (one property per record). A page rule's "values" are
pages. A record locator rule's values are records.*

**D3. Record key.** Eric wants to use the course ID. Problems: (a) if the Course ID rule extracts wrongly, the key
is wrong too; (b) codes repeat (CCSF stub records on program pages share the full record's code; the same course can
appear on several pages); (c) a record with no code has no key.
*Assumption: what the user sees is the course code. Underneath, the stable key is **(catalog, normalized course
code)** when the code is present. Each **occurrence** of the course on a page is keyed by (page, locator position).
Annotations attach to the occurrence and also store the code, so they can be re-attached by code when locators move.
Research checks how unique codes are across the five catalogs.*

**D4. Missed pages** ("courses on pages we never looked at"). *Assumption: a **page coverage** view under the page
rule: pages the rule classified as not-course but which contain course-like patterns, plus a manual "this page has
courses" verdict. This is an uncertainty signal (R-uncertainty), not a separate tool.*

**D5. Highlight-to-annotate.** Eric wants to select text in the rendered page as the expected value.
*Assumption: store the selected text, the `css_path` of the nearest element, and character offsets within that
element's text (like the W3C Web Annotation "TextQuoteSelector + position"). This works only if the page pane
renders the saved HTML so that paths can be resolved, which ties it to W1.*

**D6. The record view's data.** *Assumption: the v3 record tab shows the same annotations as the rule view, stored in
the same annotation log. A verdict made in the record tab on a field is a verdict on (record, the field's rule). v2's
`decisions.json` is not carried forward. Research checks whether Jared's existing v2 decisions (for example
AVC 145 accepted / 26 rejected) are worth importing as annotations, so his past work counts in A4.1.*

**D7. CSS/JS in the crawl.** Updating the crawler means changing xtra-cli, which is out of scope.
*Assumption: the v3 CLI gets its own **`assets fetch`** step that reads the saved pages, downloads the CSS, JS,
fonts and images they reference once, and stores them next to the crawl in the scratch mirror. xtra-cli is not
touched. Research checks first whether the crawl already saved any assets.*

**D8. "Approved" life cycle.** *Assumption: a rule version is in one of three states: `in review` (the default when
published) → `approved` (a person says it's 100% correct) or `needs work` (it has open wrong/missing annotations). The
left column shows these as a check / cross / neutral icon. Approval belongs to a rule version. A new version of an
approved rule starts again at `in review`.*

**D9. What counts as "better" when a record locator changes** (A5.5). *Assumption: compare at the level of the course
code. "Same course" means the same normalized code. Records with no code are compared by page and are listed
separately as "can't match". Research looks at how often that happens.*

**D10. The fourth prose value for each rule** (I1). *Assumption: **what** (what it finds), **how** (how it finds it),
**why** (why this version is better than the last one, empty for v1), and the existing **examples**
(input → output) as the fourth. Every version stores all of them. The UI shows them on the rule's header.*

**D11. Whole ruleset vs one rule when publishing.** *Assumption: the publishing unit is a **ruleset version**,
always. Changing one rule makes a new ruleset version that reuses every other rule version unchanged. That way
"iterate on one rule" and "publish a batch" are the same operation. Discussed in R-versioning.*

**D12. Where the scratch area goes.** *Assumption: a new top-level prefix **`zz-scratch-review-ui-v3/`** in
`xtra-cli-output`, mirroring `<catalog>/<run>/…` and `review-ui-index/` underneath it. Deleting that prefix removes
everything. Nothing is written outside it. A matching local folder (`~/review-ui-v3-data/`) has the same layout.*
