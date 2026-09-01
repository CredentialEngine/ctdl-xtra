# Where xTRA Could Go From Here
---

## Table of Contents

1. [Where we are](#where-we-are)
2. [The hierarchy problem](#the-hierarchy-problem)
3. [Schema-driven extraction](#schema-driven-extraction)
4. [Descriptions and extraction instructions](#descriptions-and-extraction-instructions)
5. [How these pieces fit](#how-these-pieces-fit)

---

## Where we are

xTRA crawls institution catalogues and turns pages into structured items for the [Credential Registry](https://credentialengine.org/credential-transparency/credential-registry/) - but currently, that work is still mostly **flat**: each catalogue type is extracted on its own, and the fields we ask the model for are **hand-built in the product** rather than taken from the Registry’s published schema.

Today a catalogue is one type at a time. A course extraction yields a list of courses. A learning-program extraction yields a list of programs. Competencies and credentials are similar lists. The items are useful, but they are not a graph.

The fields themselves are also manual. Course extraction asks for `course_id`, `course_name`, `course_description`, credits, prerequisites, and so on. Those names and rules live in the product. Some of them *correspond* to Credential Registry / CTDL terms; they are not *driven* by those terms. Adding a new property means a developer encodes it, writes a prompt-like description, and ships a release.

That was a reasonable way to get courses (and then programs, credentials, and competencies) out the door. It does not scale to the rest of the Registry, and it does not produce the relationships the Registry expects.

---

## The hierarchy problem

Credential Registry data is not flat, but is a **network of related resources**. A degree or other credential is awarded for completing a learning program. That program is made of courses (or other learning opportunities). Courses and programs teach, require, or align to competencies that sit in a competency framework and so on. There is a parent-child relationship among entity types.

Until hierarchy is a first-class output, xTRA will keep producing useful spreadsheets that still need a human to reconstruct the Registry graph. xTRA still has to solve how to reliably connect the nodes together but starting with the schema definition used by the Registry should be among the most important heuristics. More will have to be developed based on how institutions publish their catalogues. One that could be useful is URL hierarchy, for cases where a course would list its competencies. These could be linked by their URL. However, this will not be universal, for catalogues that do not use URLs, this heuristic is unavailable. It has not been argued but it should be at least considered where is the gap of what an institution is responsible to provide as a catalogue UX and how much should xTRA counter balance any deficiencies. If catalogue is intended to behave like a websites but does not do so, should xTRA work around or should the institution be put on hold until the issues are resolved?

Regardless of the URL based parent-child indicator, xTRA should find more to account for the variation of institutions and how they publish there information.

---

## Schema-driven extraction

Besides hierarchy, extraction should **rely more on Credential Engine’s Credential Registry schema** — CTDL for credentials, courses, and learning programs; CTDL-ASN for competencies and frameworks — instead of manually engineering each field at development time.

The published terms already carry the contract we have been rewriting by hand: labels, comments, descriptions, expected types, and which classes a property belongs on. `ceterms:name`, `ceterms:description`, `ceterms:codedNotation`, credit properties, credential subclasses, `ceasn:Competency`, framework membership, and the relationship predicates that express hierarchy are all defined there. xTRA should treat that as the source of truth for *what an item is* and *which attributes it may have*.

What that changes in practice:

- **Stop inventing parallel field names** (`course_name` vs the Registry’s name property, a custom credits type list vs the published credit concepts). Map to schema terms; keep xTRA-only fields only where the Registry has no term and we still need an operational handle.
- **Stop shipping a new release to add a property.** If the schema already defines the term, extraction should be able to request it because the term exists, not because someone added it to a TypeScript property map.
- **Let class and property metadata drive prompts and structured output.** The model should see the same meaning a Registry consumer would see — the official comment and description — not a developer paraphrase that drifts over time.
- **Let relationships be schema relationships.** Course-to-program and program-to-framework links should be expressed with the predicates the Registry already has, so export is closer to a graph than to four unrelated CSVs.

Manual engineering will not disappear overnight. Pages are messy, and some Registry terms will still need extra guidance to extract well (see the next section). The shift is *where the default meaning comes from*: the Credential Registry schema first, product-specific overrides second.

---

## Descriptions and extraction instructions

Schema-driven extraction only works if the **descriptions of schema elements are accurate and usable**. Models (and people) extract what they understand. Vague or overloaded wording is how we get competencies mixed with course lists, credential blurbs mixed with program marketing, or credits filled in when the page never stated them.

Two kinds of text are easy to conflate and should not be:

1. **What the term means** — the Registry definition: label, comment, description, domain, and range. This should stay aligned with Credential Engine’s published schema. The better and more precise that text is, the better extraction tends to be. Investing in those descriptions (and in keeping them in sync with the schema) is leverage: every catalogue benefits.
2. **How to find it on a real page** — heuristics that are not part of the data model: “only the first few paragraphs,” “do not treat advised courses as corequisites,” “this header usually means learning outcomes, not admissions requirements,” “if the URL never changes, look in the expanded panel.” That is operational knowledge. It belongs next to the term, not stuffed into the same sentence as the official definition.

xTRA should invest in a dedicated **extraction instructions** field on schema elements (and, where useful, on catalogue types or recipes). That field would tell humans and AI agents how to *identify* the item or property in the wild: what to look for, what to ignore, and how this term differs from a neighbour that often appears on the same page.

That split pays off in both directions:

- **Humans** — operators and reviewers can read “what this is” (schema) separately from “how we pull it here” (instructions). Tuning extraction becomes editing instructions, not rewriting the meaning of `ceterms:description`.
- **AI agents** — whether the current extraction LLM or a future agentic crawler, the model gets a stable definition plus an explicit hunt strategy. Competency work already showed that dumping every edge case into one prompt degrades results; a first-class instructions field is a place to put that guidance without poisoning the schema text.

The more accurate the schema-element descriptions are, the less those instructions have to compensate. Instructions should stay thin and specific. The schema should carry the meaning.

---

## How these pieces fit

| Direction | Problem it addresses | What “done” looks like |
|-----------|----------------------|-------------------------|
| **Hierarchy** | Items are extracted in isolation | Courses, programs/degrees, credentials, competency frameworks, and other Registry classes are linked with schema relationships |
| **Schema-driven fields** | Properties are invented and maintained in product code | Extraction targets Credential Registry / CTDL (and CTDL-ASN) terms; new terms do not require a custom field to be engineered first |
| **Descriptions + extraction instructions** | Meaning and page-hunting rules are mixed, so quality is fragile | Official descriptions stay accurate; a separate instructions field guides humans and agents to the right content |

Crawl improvements (recipes vs agentic, better handling of SPAs) still matter for *reaching* pages. The next leap for xTRA as a Registry tool is **what we do with those pages**: emit a linked graph grounded in Credential Engine’s schema, and make the meaning of each element clear enough that both people and models can identify it consistently.
