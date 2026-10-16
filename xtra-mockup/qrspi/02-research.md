# R — Research findings

Phase 2 of Q.R.S.P.I. Research date: 2026-10-07. This document records facts only. Where it makes a
recommendation, the recommendation is labelled as one, and the decision belongs to the next phase.

## Review comments

Eric reviewed this document aloud on 2026-10-07. His remarks are recorded inline, next to the passage they
refer to, as numbered threads in this form:

> 💬 **C0 · Eric:** a comment, tidied from speech.
>
> ↳ **Reply:** the response, where one was needed.

They are plain Markdown block quotes, so they display the same on GitHub and in VS Code. Search for `💬` to jump
between them.

| # | Comment | Outcome |
|---|---|---|
| C1 | How do you know 48,580 courses are published? | Answered; citation added |
| C2 | Never publish the output | Recorded as R2 |
| C3 | Keep CTID minting pure, DDD-style, without over-abstracting | Direction for design phase |
| C4 | Do not give up on structured prerequisite logic | Direction for design phase; section 9 updated |
| C5 | Study the ctdl-xtra repository | Done; see section 13 |
| C6 | Is credreg.net current and correct? | Recorded as R1 |
| C7 | The alignment-object wrapper is confusing | Answered |
| C8 | What does Credential Engine recommend on new version versus new CTID? | Researched; no explicit rule found. Open item 9 |
| C9 | inLanguage means the language of teaching | Confirmed |
| C10 | Evidence on another page means multiple source previews | Direction for design phase |
| C11 | What is the difference between ownedBy and offeredBy? | Answered |
| C12 | Why is requires one block of text? Can it be more granular? | Answered; ties to C4 |
| C13 | What do multiple values in inLanguage mean? | Answered |
| C14 | What does dateEffective mean? | Answered |
| C15 | Why is creditValue a list of one ValueProfile? Show rationale versus alternatives | Answered; direction for design phase |
| C16 | Text-only prerequisites seem unjustified | Clarified |
| C17 | Rules for concept mapping need evaluation; 'model' was ambiguous | Wording fixed; evaluation approach noted |
| C18 | Store a digest of each page | Direction for design phase |
| C19 | 'Shape' and 'span' wording; toggle rendered view and HTML tree; surface every kind of evidence | Wording fixed; direction for design phase |
| C20 | Where do notes go? Create a risks and future considerations document | Done |
| C21 | Use text-fragment deep links if they work | Direction for design phase; untested, R7 |
| C22 | What does 'the crawler must not fetch it' mean? | Answered; reworded |
| C23 | Model quality is not a concern now; make it pluggable | Direction for design phase |
| C24 | Open items are out of scope for now | Acknowledged |

**Direction for the design phase**, gathered from the threads:

- Never publish (C2).
- CTID minting is a small, pure domain service (C3).
- Structured prerequisite logic is a goal (C4, C12).
- One field may need several source documents shown (C10).
- Every field explains why this property, why this structure, and what the alternatives were (C15).
- Pages are identified by a digest of their bytes (C18).
- The source pane can switch between the rendered page and its HTML, and every kind of evidence has a
  presentation (C19).
- Deep links to the live page use text fragments (C21).
- The language model is replaceable; its quality is a later concern (C23).

## 1. Headlines

1. **Each catalog entry is a `ceterms:Course`.** The class definition fits, the catalog's own wording fits, and
   48,580 courses are already published in the Registry under that type (source in comment C1). Case in section 4.
2. **The University of Arkansas is already in the Credential Registry.** Its CTID is
   `ce-57603921-78ce-455c-88b5-00506fb33701`. It has published 298 credentials (degrees and certificates) and
   **zero courses**, so no course CTIDs exist to reuse. Section 5.
3. **Six properties are required to publish a course; the page supplies two directly.** Name and description are
   on the page. Language, lifecycle status and owner can be evidenced from the pages and the Registry. The
   CTID has to be minted. Section 6.
4. **Almost everything on the page is extractable by rule.** All 546 title lines in the five sampled subjects fit
   one pattern with three variants. Offering term, corequisites, repeat rules, cross-listing and equivalency are
   all labelled, formulaic sentences. Section 8.
5. **The one hard field is prerequisite logic.** Real publishers do not attempt it: in a sample of 1,000
   published courses, every prerequisite was plain text. Section 9 lays out the options.
6. **The local language model quotes faithfully but reasons unreliably.** 31 of 31 quotes were verbatim, at about 2.4
   seconds each. But it mislabelled AND as OR and invented course codes. Substring checks catch fabricated
   text, not wrong logic. Section 11.
7. **Credential Engine's own tool, `ctdl-xtra`, would skip these pages.** It uses rules only, maps five fields,
   keeps prerequisites as text, and skips any page with more than one course. It has a provenance record in
   an older code path that the current tool discards. Section 13.

> 💬 **C1 · Eric** *(on headline 1)*: I'm interested to see how you know that. I'm a little sceptical, since you didn't cite a finding there.
>
> ↳ **Reply:** Fair. The number comes from the Registry itself, not from a document. Its open search address,
> `https://credentialengineregistry.org/ce-registry/search?resource_type=course`, returns the total in a response
> header: `x-total: 48580`. I re-ran it during this review and got the same figure. You can check it with:
>
> ```
> curl -sI "https://credentialengineregistry.org/ce-registry/search?resource_type=course&per_page=1" | grep -i x-total
> ```
>
> Two limits on the claim. I confirmed the type on the 1,000 records I downloaded (all `ceterms:Course`), not on
> all 48,580. And the count moves as publishers add records. The citation is now in section 4.

> 💬 **C2 · Eric** *(on headline 2)*: Good. To reiterate, we definitely don't want to publish what we're about to do, because we don't know how valid it is.
>
> ↳ **Reply:** Agreed. Recorded as risk R2 in `risks-and-future-considerations.md`. The design will have no publish step at all.

> 💬 **C3 · Eric** *(on headline 3)*: I'm okay referencing the Registry. On minting the CTID: follow domain-driven design to some degree, and keep the
> minting process as pure as you can, referencing the bare minimum number of objects, the way services are
> intended to work in domain-driven design. Don't go overkill with the abstractions. I just want thought to have
> gone into the organisation.
>
> ↳ **Reply:** Noted as design direction for the next phase. The research supports a very small footprint. Minting needs to
> know only two things: which organisation, and which course code. It needs one collaborator: the ledger that
> remembers what was minted before. It needs to know nothing about pages, extraction or CTDL. The CTID page backs
> this framing: "The recommended approach, in general, is to generate and store CTIDs as a field along with the
> relevant data." 

> 💬 **C4 · Eric** *(on headline 5)*: I don't want to give up on prerequisite logic. I want to make sure we do that.
>
> ↳ **Reply:** Understood. That changes my recommendation in section 9: structured logic becomes a goal, not an optional
> extra. The research suggests how to get there without leaning entirely on the language model. Most of these
> sentences follow a small grammar: course codes, "and", "or", commas and brackets, with the codes already marked
> up as links. A deterministic parser can handle that part, and the language model can take what is left over.
> The verbatim text is still always kept alongside, so a wrong structure never destroys information.

> 💬 **C5 · Eric** *(on headline 7, which originally said "I listed its files but did not study it")*: I would like you to study it, actually.
>
> ↳ **Reply:** Done. Findings are in section 13.

## 2. Where the facts came from

| Source | How obtained | Note |
|---|---|---|
| CTDL schema (all classes, properties, concept schemes) | Internet Archive copy of `credreg.net/ctdl/schema/encoding/json`, captured 2026-06-07 | `credreg.net` returns HTTP 403 to scripts (Cloudflare). The copy is four months old. Saved at `reference/ctdl/ctdl-schema.json`. |
| Minimum Data Policy | Internet Archive copy of `credreg.net/registry/policy`, captured 2026-06-14; page says "Last Updated on 2/3/2025" | Saved as text at `reference/ctdl/minimum-data-policy.txt`. |
| CTDL Handbook | Internet Archive copy, captured 2026-06-07 | Saved as text at `reference/ctdl/handbook.txt`. |
| Credential Registry records | Live, from `credentialengineregistry.org` (open, no key needed) | Organisation record, example courses, and a 1,000-course sample. |
| Catalog pages | Live, from `catalog.uark.edu`: the index plus ACCT, CHEM, CSCE, ENGL, NURS | Six requests total, one second apart. |
| Local language model | `qwen3.5:9b` on ollama 0.40.0 | 15-sentence probe; raw output at `reference/llm-probe-prerequisites.json`. |

**Not verified:** I could not load `credreg.net` or `credentialfinder.org` live, so the schema may have changed
since June. A person can open those sites in a browser normally.

> 💬 **C6 · Eric:** I worried that credreg might be out of date, since this is all available on official CTDL pages as well. Then I
> checked: credreg.net actually is the correct site, so good job. I have a page called "terms". You're probably
> fine with the one you downloaded. Just make sure you call that out visibly in a final report somewhere that we
> had this concern.
>
> ↳ **Reply:** Recorded as risk R1, the first entry in `risks-and-future-considerations.md`, so it travels with the project.
> The specific concern is that my copy is an archived snapshot from June 2026, not that the site is wrong. If you
> can save the terms page from your browser into `reference/ctdl/`, I can compare it with the snapshot and close
> the risk.

## 3. CTDL in five minutes

CTDL (Credential Transparency Description Language) is a vocabulary for describing credentials, courses,
organisations and how they relate. It is written as JSON-LD, which is ordinary JSON with a few reserved keys.

| Term | Plain meaning | Example |
|---|---|---|
| **Class** | A kind of thing. Goes in `@type`. | `ceterms:Course`, `ceterms:CredentialOrganization` |
| **Property** | A fact about a thing. A JSON key. | `ceterms:name`, `ceterms:creditValue` |
| **Domain / range** | Which classes may carry a property, and what kind of value it takes. | `ceterms:creditValue` is allowed on a Course and its value must be a `ceterms:ValueProfile`. |
| **Concept scheme** | A fixed list of allowed values. | The Credit Unit scheme contains `creditUnit:SemesterHour`, `creditUnit:QuarterHour` and 13 others. |
| **CTID** | A globally unique ID: `ce-` followed by a UUID. | `ce-57603921-78ce-455c-88b5-00506fb33701` |
| **Language map** | Text values are wrapped by language. | `"ceterms:name": {"en-US": "Accounting Principles"}` |
| **Profile** | A small nested object that groups related facts. | A `ConditionProfile` describes one requirement; a `ValueProfile` describes one credit amount. |
| **Alignment object** | The wrapper used to pick a value from a concept scheme. | See `lifeCycleStatusType` in the example in section 7. |

> 💬 **C7 · Eric:** The alignment object does not make sense to me. There's a lot of abstraction here. I can appreciate that it probably reduces the total number of tables. We'll look at that more later.
>
> ↳ **Reply:** A plainer way to see it. CTDL could have written the credit unit as a bare word:
>
> ```json
> "creditUnitType": "SemesterHour"
> ```
>
> It writes a small labelled card:
>
> ```json
> "creditUnitType": [{
>   "@type": "ceterms:CredentialAlignmentObject",
>   "ceterms:framework": "https://credreg.net/ctdl/terms/CreditUnit",
>   "ceterms:targetNode": "creditUnit:SemesterHour",
>   "ceterms:targetNodeName": { "en-US": "Semester Hour" }
> }]
> ```
>
> The card says: "the value is Semester Hour, and it comes from the list called Credit Unit." The reason is that
> the same card can point at any list, including ones CTDL does not own, such as the federal codes for subjects
> or occupations. One wrapper covers every pick-from-a-list field. For the viewer, this suggests collapsing the
> card to a single labelled chip by default, with the full object one click away.

Browsable references (open in a browser; scripts are blocked):

- All terms: <https://credreg.net/ctdl/terms>
- One term, for example Course: <https://credreg.net/ctdl/terms/Course>
- Handbook: <https://credreg.net/ctdl/handbook>
- Minimum Data Policy: <https://credreg.net/registry/policy>
- Any Registry record as JSON: `https://credentialengineregistry.org/resources/<CTID>`
- The same record for humans: `https://credentialfinder.org/resources/<CTID>`

## 4. The case for `ceterms:Course`

**The definition fits.** CTDL defines Course as:

> "Single structured sequence of one or more educational activities that aims to develop a prescribed set of
> competencies of learners."

with the note: "Course is distinct from Program, which aggregates several courses."

**The catalog says the same thing in its own words.** The index page states:

> "The word 'course' refers to a unit of academic instruction, while the word 'class' refers to a course that
> has been scheduled during a semester or summer session…"

So a catalog entry is the durable unit of instruction, not a scheduled section. That is the CTDL Course.

**The alternatives are worse fits.**

| Candidate | Why not |
|---|---|
| `ceterms:LearningOpportunityProfile` | The generic parent class. Course is its subclass, so choosing the parent discards information. Course also unlocks `ceterms:prerequisite`, which only Courses may carry. |
| `ceterms:LearningProgram` | Defined as a set of learning opportunities leading to an outcome such as a degree. That is a major, not a course. |
| `ceterms:CourseComponent` | A stand-in for a course inside a pathway diagram. Not the course itself. |

**It is what publishers do.** The Registry holds 48,580 records of type `ceterms:Course`. Source: the Registry's
open search address, `https://credentialengineregistry.org/ce-registry/search?resource_type=course`, reports
`x-total: 48580` in its response headers (checked twice on 2026-10-07). All 1,000 records I downloaded from it
were of type `ceterms:Course`.

**It maps outward.** The schema declares `ceterms:Course` equivalent to `schema:Course`.

## 5. Discovering the fields the page doesn't state

You asked me to look these up, not assume them. Results:

### Owning organisation: found

The University of Arkansas has a Registry record:

- Name: "University of Arkansas Fayetteville"
- CTID: `ce-57603921-78ce-455c-88b5-00506fb33701`
- URI: <https://credentialengineregistry.org/resources/ce-57603921-78ce-455c-88b5-00506fb33701>
- Type: `ceterms:CredentialOrganization`, four-year, public, lifecycle Active
- Saved at `reference/registry-examples/uark-organization.json`

Courses should point `ceterms:ownedBy` and `ceterms:offeredBy` at that URI. No new organisation record is needed.

Page evidence that this is the right organisation: the index page says the listing is of "all courses approved
for offering by the University of Arkansas", and every page title ends "< University of Arkansas".

Beware near-misses in the Registry: there are separate records for University of Arkansas at Little Rock, Fort
Smith, Pine Bluff, Monticello, Grantham, Medical Sciences and several community colleges.

### Course CTIDs: none exist

I fetched all 298 resources the university owns. They are degrees and certificates:

| Type | Count |
|---|---|
| Bachelor's degrees (BS, BA, generic) | 107 |
| Master's degrees (MS, MA, generic) | 102 |
| Doctorates (research, professional, generic) | 42 |
| Certificates (post-baccalaureate, post-master's, technical) | 45 |
| Specialist degrees | 2 |
| **Courses** | **0** |

So CTIDs must be minted. The handbook defines a CTID as "a UUIDv4 prefixed with `ce-`". Because UUIDv4 is
random, the only way to be idempotent is to mint once and remember: a ledger file keyed by organisation and
course code. Re-running extraction must never produce a new CTID for the same course.

The schema note on `ceterms:ctid` adds a wrinkle: "Different versions of a resource are considered distinct
expressions and each must be assigned its own CTID." Whether a new catalog year is a new version is a policy
question for the publisher, not something the page answers.

> 💬 **C8 · Eric:** Add a follow-up question to that. What does Credential Engine recommend as far as when a publisher should
> consider it a new course or not? Surely they have an opinion on what to recommend for that policy, and the
> opinion must be based in actual trade-offs. What do you get if you do it, or what do you lose if you don't?
>
> ↳ **Reply:** I searched the handbook, the Minimum Data Policy, the publishing guide and the "About the CTID" page. **I did
> not find an explicit rule for what counts as a new version of a course.** What I did find:
>
> - The schema note on `ceterms:ctid`: "The CTID is the equivalent of a version identifier for the resource.
>   Different versions of a resource are considered distinct expressions and each must be assigned its own CTID."
> - The schema separates two cases. `ceterms:supersedes` is for a resource that is "outright replaced… and is not
>   simply an older version of the same" thing. Version-chain properties (`previousVersion`, `nextVersion`,
>   `latestVersion`) cover the other case, but **they are not available on Course**. Course gets
>   `versionIdentifier`, `versionCode`, `supersedes`, `supersededBy`, `dateEffective` and `expirationDate`.
> - The "About the CTID" page: "The recommended approach, in general, is to generate and store CTIDs as a field
>   along with the relevant data." That treats the CTID as a stable key that lives with the record.
> - Practice. The Brookdale course in section 7 has `dateEffective` 1999 and a version identifier of "2024-2025
>   Catalog" on one CTID. That publisher keeps the CTID across catalog years and updates the record in place.
>
> The trade-off, which is my analysis and not a quoted position:
>
> | | Keep one CTID across years | Mint a new CTID per version |
> |---|---|---|
> | Links from programs, pathways and other courses' prerequisites | Keep working | All need updating |
> | History | Overwritten; the Registry shows only the latest | Preserved; each version stays retrievable |
> | A learner's record pointing at "the course I took in 2019" | Now describes today's course | Describes exactly what was taken |
> | Search results | One entry per course | Several near-duplicates unless old ones are marked ceased |
>
> This is worth asking Credential Engine directly. Added as open item 9 in section 14 and as risk R9.

### Language: evidenced, not stated

- Every page declares `<html lang="en">`.
- The course text is in English.
- The schema's own usage note covers the edge case: "A course offered in English to teach Spanish would have an
  inLanguage of English." So Arabic, Chinese or French courses in this catalog are still `en`.

Published courses use `"ceterms:inLanguage": ["en"]`.

> 💬 **C9 · Eric:** So it's the language the course is taught in. (I first read "in" as short for "instruction"; that's a coincidence.)
>
> ↳ **Reply:** Yes. It is the language the course is delivered in, not the subject being taught.

### Lifecycle status: evidenced, not stated

The allowed values are Active, Ceased, Ceasing, Developing, Suspended and Teach Out. Evidence for Active:

- Pages are labelled "2026-27 Edition", the current catalog.
- The index says the listing is of "all courses approved for offering".

There is a nuance worth showing a reviewer: 219 of 546 sampled courses say "Typically offered: Irregular". They
are approved but not regularly scheduled. Active is still the closest value, since Suspended means "temporarily
not active".

### Credit unit: evidenced on a different page

Course title lines say "3 Hours" without saying what kind. The index page supplies it: "Successful completion
of a class usually earns a specified number of **semester hours** of credit toward a degree." That justifies
`creditUnit:SemesterHour`.

This matters for the viewer's design: **the evidence for one field can sit on a different page from the course
itself.**

> 💬 **C10 · Eric:** This is a great insight, and it's definitely going to be true. That probably means we have to display multiple previews.
>
> ↳ **Reply:** Noted as a requirement for the design phase: the source pane must be able to show more than one document for a single field.

## 6. What the Registry requires for a course

From the Minimum Data Policy. Note that every Course row is marked "Pending Policy": the Course-specific rules
are published but flagged as pending. They match the rules already in force for the parent class, Learning
Opportunity Profile.

### Required

| Property | CTDL definition | Where our value comes from |
|---|---|---|
| `ceterms:name` | "Name or title of the resource." | Title line, by rule |
| `ceterms:description` | "Statement, characterization or account of the entity." | Description paragraph, by rule |
| `ceterms:ctid` | "Globally unique Credential Transparency Identifier (CTID)…" | Minted once, kept in a ledger |
| `ceterms:inLanguage` | "The primary language or languages of the entity, even if it makes use of other languages." | Page `lang` attribute |
| `ceterms:lifeCycleStatusType` | "Type of state of the resource in terms of its stage in a life cycle…" | Catalog edition plus index wording |
| `ceterms:ownedBy` or `ceterms:offeredBy` | "Agent with an enforceable claim or legal title to the resource." / "Agent that offers the resource." | Registry lookup |

> 💬 **C11 · Eric:** I'm curious to know more about owned by and offered by.
>
> ↳ **Reply:** - **Owned by**: "Agent with an enforceable claim or legal title to the resource." Whoever designed the course
>   and controls its content.
> - **Offered by**: "Agent that offers the resource." Whoever teaches it to students.
>
> For most university courses these are the same organisation. They differ when one body writes a curriculum and
> others deliver it: a vendor course taught at a college, or a statewide common course taught on many campuses.
>
> The policy requires at least one of the two. In the 1,000-course sample, 999 gave only `ownedBy` and one gave
> both. The organisation's own record carries the mirror-image lists, `owns` and `offers`; the University of
> Arkansas lists the same 298 credentials under each. For our courses the university is both, so the question for
> the design phase is only whether to emit both or follow the common practice of `ownedBy` alone.

### Recommended, and present in this catalog

| Property | Source on the page |
|---|---|
| `ceterms:codedNotation` | Course code in the title line |
| `ceterms:creditValue` (with credit unit type) | "3 Hours" in the title line |
| `ceterms:subjectWebpage` | The subject page URL |
| `ceterms:inCatalog` | The catalog URL |
| `ceterms:prerequisite` / `ceterms:requires` | "Prerequisite:" sentence |
| `ceterms:coPrerequisite` | "Pre- or Corequisite:" sentence |
| `ceterms:audienceLevelType` | Derivable from course number (unverified; see section 14) |
| `ceterms:learningMethodType` | "Lecture 3 hours per week", "Laboratory" in some entries |
| `ceterms:dateEffective` | Not on the page |

Also recommended but absent from this catalog: delivery type, cost, duration, financial assistance, occupation
and industry types, assessment methods, competencies taught, accreditation.

## 7. A real published course

This is a live Registry record from Brookdale Community College, unedited. It is the closest analogue I found
to our ACCT courses. Saved at `reference/registry-examples/course-brookdale-acct101.json`.

```json
{
  "@id": "https://credentialengineregistry.org/resources/ce-a1dff327-b792-406a-9547-edc9c803a78f",
  "@type": "ceterms:Course",
  "@context": "https://credreg.net/ctdl/schema/context/json",
  "ceterms:ctid": "ce-a1dff327-b792-406a-9547-edc9c803a78f",
  "ceterms:name": { "en-US": "ACCT101 - Principles of Accounting I" },
  "ceterms:ownedBy": [
    "https://credentialengineregistry.org/resources/ce-fe60bc94-5aa8-410c-9f2c-da21130a3c6b"
  ],
  "ceterms:requires": [
    {
      "@type": "ceterms:ConditionProfile",
      "ceterms:name": { "en-US": "Prerequisites" },
      "ceterms:description": {
        "en-US": "MATH-012, MATH-015 or satisfactory completion of the College's foundational studies requirement in computation; and READ-092, READ-095 or satisfactory completion of the College's foundational studies requirement in reading"
      }
    }
  ],
  "ceterms:inLanguage": ["en"],
  "ceterms:creditValue": [
    {
      "@type": "ceterms:ValueProfile",
      "schema:value": 3.0,
      "ceterms:creditUnitType": [
        {
          "@type": "ceterms:CredentialAlignmentObject",
          "ceterms:framework": "https://credreg.net/ctdl/terms/CreditUnit",
          "ceterms:targetNode": "creditUnit:SemesterHour",
          "ceterms:frameworkName": { "en-US": "Credit Unit" },
          "ceterms:targetNodeName": { "en-US": "Semester Hour" },
          "ceterms:targetNodeDescription": { "en-US": "Credit that is issued or accepted at a semester level." }
        }
      ]
    }
  ],
  "ceterms:description": { "en-US": "An introduction to basic concepts and principles of recording and posting financial information… (Prerequisites: …)" },
  "ceterms:codedNotation": "ACCT101",
  "ceterms:dateEffective": "1999-01-02",
  "ceterms:subjectWebpage": "https://catalog.brookdalecc.edu/courses/ACCT101",
  "ceterms:versionIdentifier": [
    {
      "@type": "ceterms:IdentifierValue",
      "ceterms:identifierTypeName": { "en-US": "Catalog Year" },
      "ceterms:identifierValueCode": "2024-2025 Catalog"
    }
  ],
  "ceterms:lifeCycleStatusType": {
    "@type": "ceterms:CredentialAlignmentObject",
    "ceterms:framework": "https://credreg.net/ctdl/terms/LifeCycleStatus",
    "ceterms:targetNode": "lifeCycle:Active",
    "ceterms:frameworkName": { "en-US": "Life Cycle Status" },
    "ceterms:targetNodeName": { "en-US": "Active" },
    "ceterms:targetNodeDescription": { "en-US": "Resource is active, current, ongoing, offered, operational, or available." }
  }
}
```

Things to notice:

- The prerequisite is **text only**, inside a `ConditionProfile`.
- This course has fixed credit, so it carries a single number: `"schema:value": 3.0`. A course with a credit
  range, such as our "1-3 Hour" internships, drops `schema:value` and carries two numbers in its place:
  `"schema:minValue": 1.0, "schema:maxValue": 3.0`. It is still one entry in the list. (Seen on five records in
  the sample, not on this one.)
- The catalog year is carried in `ceterms:versionIdentifier`.
- The concept-scheme values repeat their own label and definition inline. That is handy for a teaching UI.

> 💬 **C12 · Eric** *(on the `requires` entry in the example)*: This is a ground-truth example, and it confuses me. The `requires` element is describing multiple things, with
> options between them. I would have expected one entry in the `requires` list per course. Could this be expressed
> more granularly in CTDL? Should it be, and can it be?
>
> ↳ **Reply:** **Can it be?** Yes. One correction to the mental model first: each entry in `requires` is one *set of
> requirements* (a ConditionProfile), not one course. Courses hang off a profile through
> `targetLearningOpportunity`. Sibling profiles mean "and"; profiles under `alternativeCondition` mean "or".
> Brookdale's computation requirement could have been written like this:
>
> ```json
> "ceterms:requires": [{
>   "@type": "ceterms:ConditionProfile",
>   "ceterms:name": { "en-US": "Computation requirement" },
>   "ceterms:alternativeCondition": [
>     { "@type": "ceterms:ConditionProfile", "ceterms:targetLearningOpportunity": ["<URI of MATH-012>"] },
>     { "@type": "ceterms:ConditionProfile", "ceterms:targetLearningOpportunity": ["<URI of MATH-015>"] },
>     { "@type": "ceterms:ConditionProfile",
>       "ceterms:condition": { "en-US": "Satisfactory completion of the College's foundational studies requirement in computation" } }
>   ]
> }]
> ```
>
> with a second sibling profile for the reading requirement. Section 9 sets out the mechanics.
>
> There is also `ceterms:prerequisite`, which is the one-entry-per-course list you expected: a plain list of links
> to other courses. It cannot say "or", so it only fits sentences that are a straight list.
>
> **Should it be?** If anyone is going to compute with it (draw prerequisite chains, check a student's
> eligibility), yes. Publishers skip it, in my reading, because their student systems hold the prerequisite as one
> text field, and copying text is free while structuring it is work. That is the gap this tool could close.

> 💬 **C13 · Eric** *(on `inLanguage` in the example)*: `inLanguage` is an array, so there could be multiple languages in there. Would that mean one course alternates
> between two languages being taught, or that you can select the English version or the Spanish version?
>
> ↳ **Reply:** The schema does not distinguish those two. Its definition is "the primary language or languages of the
> entity", and its only multi-language example is "a credential in Quebec could have an inLanguage of both French
> and English." So two entries say only that both are primary languages of the thing described. If a publisher
> wanted to say "there is an English section and a separate Spanish section", the more precise tool would be
> separate offerings (`ceterms:hasOffering`) or separate course records. Every one of the 1,000 sampled courses
> had exactly `["en"]`.

> 💬 **C14 · Eric** *(on `dateEffective` in the example)*: What does date effective mean? (The example says 1999-01-02.)
>
> ↳ **Reply:** Definition: "Date after which this resource is available or applicable." Brookdale is saying this course came
> into force in January 1999. It is the start of the course's life, not of this catalog year. Our pages do not
> state it, so we would leave it out.

> 💬 **C15 · Eric** *(on `creditValue` in the example)*: The credit value is a list, and the one object in it is a value profile. As a non-expert: why is there only one
> entry in this list? Why not multiple? What would it mean if there were multiple? Why is this object a value
> profile specifically? These are questions about the schema and its edge cases. Whenever one of these choices is
> made, the tool should also carry the rationale for why each value was used instead of the alternatives. That
> helps us learn the schema.
>
> ↳ **Reply:** **Why a value profile and not a number?** A bare `3` is ambiguous: three what? The handbook describes the
> ValueProfile as a number or a range, plus optionally a unit, a level and a subject. Its own example is "3 Degree
> Credits at the Lower Division Level for the subject of Finance".
>
> **Why a list?** Because a course can carry more than one statement of credit. Plausible cases: 3 semester hours
> and also 45 contact hours; or credit counted at two different levels. Each statement is one entry.
>
> **Why only one here?** Because this course makes one statement: 3 semester hours. That is the norm. In the
> sample, 966 courses had exactly one entry and 34 had none; none had two.
>
> **What a second entry does not mean.** A range. "1-3 hours" is one entry with a minimum and a maximum, not two
> entries.
>
> One caveat: the schema does not spell out how to read multiple entries. The above is my reading of the handbook.
>
> **On carrying the rationale.** Noted as a requirement for the design phase. Each field in the viewer should be
> able to answer three questions: why this property, why this structure, and what the alternatives were. Sections
> 9 and 12 of this document already contain that material for prerequisites, ACTS, cross-listing and offering
> terms, so the content exists; the design needs to give it a home.

### What publishers actually populate

Property usage across 1,000 published courses. **Caveat:** the sample is the first 1,000 the search returned and
is dominated by five publishers, one of which owns 691 records. Treat it as indicative.

| Property | Records |
|---|---|
| ctid, name, description, ownedBy, inLanguage, lifeCycleStatusType | 1,000 |
| creditValue | 966 |
| codedNotation | 944 |
| inCatalog | 835 |
| identifier | 692 |
| requires | 311 |
| subjectWebpage | 165 |
| dateEffective, versionIdentifier | 109 each |
| teaches, availableOnlineAt | 55 each |
| deliveryType | 28 |
| prerequisite, corequisite, coPrerequisite, offerFrequencyType | **0** |

All 311 `requires` values looked the same: a name and a description, nothing structured.

> 💬 **C16 · Eric:** Text-only prerequisites strike me as odd and unjustified. And they don't use the prerequisite, corequisite,
> co-prerequisite or offer-frequency properties at all. That is shocking, to be honest. I find it kind of
> irresponsible.
>
> ↳ **Reply:** One clarification so the finding is not overstated. Publishers do record prerequisites: 311 of the 1,000 have
> them. They put them in the general `requires` property as text. What none of them use is the more specific
> properties or any structure. And the sample is dominated by five publishers, so "none" means "none of these
> five", not "nobody in 48,580". The underlying point stands: the structured forms exist and are, on this
> evidence, rarely used.

## 8. What is on the page

### Scale and layout

- The index links to **168 subject pages**. The five sampled hold 546 courses (ACCT 46, CHEM 86, CSCE 98,
  ENGL 171, NURS 145). My earlier figure of 138 for ACCT was wrong; I had counted markup occurrences, not courses.
- Pages are static HTML from the CourseLeaf catalog system. No JavaScript is needed to see the content.
- Each course is one `div.courseblock` holding exactly two paragraphs: `courseblocktitle` and `courseblockdesc`.
- **Courses have no anchors or IDs of their own.** The page can only be linked as a whole (see section 10).
- The "undergraduate" catalog includes graduate courses: 236 of the 546 are numbered 5000 or above.
- `robots.txt` allows the course pages. It disallows `/search/`, `/css/`, `/js/`, `/images/`, `/fonts/` and
  `/pdf/`. Two consequences: prerequisite links (which point at `/search/`) must not be followed, and the
  crawler must not download the site's stylesheets.

### Title lines

"Title-line variants" means: how many different forms does the heading of a course take? Answer: one pattern,
three variants that can combine. All 546 match.

```
ACCT 20103.  Accounting Principles (ACTS Equivalency = ACCT 2003).  3 Hours.
└─┬┘ └─┬─┘   └────────┬─────────┘ └────────────┬────────────────┘   └──┬───┘
subject number       name            optional transfer tag           credit
```

| Variant | Example | Count |
|---|---|---|
| Standard | `ACCT 20103. Accounting Principles. 3 Hours.` | 475 |
| Honors (H in fourth position) | `CHEM 142H3. Honors University Chemistry II. 3 Hours.` | 33 |
| Variable credit (V in last position) | `ACCT 3100V. Accounting Internship. 1-3 Hour.` | 32 |
| Honors and variable | `ACCT 310HV. Honors Accounting Internship. 1-3 Hour.` | 6 |

**The course number encodes the credit.** In all 546 courses, the last character equals the credit hours, or
is `V` when credit is a range. This gives a free cross-check: if the number
says 3 and the title says 4, something is wrong.

**The first digit tracks level** (0 through 7 seen), but I have not found the catalog's statement of what each
digit means.

**ACTS tags** appear on 23 courses, in three spellings: `ACTS Equivalency = CHEM 1414 Lab`, `ACTS Equiv=…`,
`ACTS = …`. Explained in section 12.

### Labelled sentences in descriptions

"Labelled sentences" means: sentences that begin with a fixed label, such as "Prerequisite:", which a rule can
find reliably. The description paragraph is free prose followed by a fairly rigid tail.

| Sentence | Courses | Distinct wordings | Rule-extractable? |
|---|---|---|---|
| `Prerequisite: …` | 337 | Many | Locating it: yes. Understanding it: see section 9. |
| `Corequisite: …` | 83 | About 20 | Half of them. 42 are a single course code. The rest include prose: "Lab component", "related course component drill section". |
| `Pre- or Corequisite: …` | 35 | 11, in four spellings | Mostly |
| `(Typically offered: …)` | 546 of 546 | 12 distinct values | Yes, fully |
| `May be repeated for [up to N hours of] degree credit.` | 134 | 2 | Yes, fully |
| `This course is cross-listed with X.` | 14 | 1 | Yes, fully |
| `This course is equivalent to X.` | 34 | 1 | Yes, fully |
| `Graduate degree credit will not be given for both X and Y.` | 21 | 1 | Yes, fully |
| `Lecture N hours [, laboratory N hours] per week.` | 20 | 5 | Yes |

Course codes inside descriptions are hyperlinks (921 of them across the five pages), which makes references
unambiguous without any text parsing.

"Typically offered" values seen: Irregular (219), Fall and Spring (107), Fall Spring and Summer (68), Spring
(59), Fall (54), Summer (12), and six rarer ones including "Fall Even Years".

Prerequisite sentences split three ways: 192 contain the word "or"; 74 have no "or" but include prose such as
"graduate standing" or "with a grade of C or better"; and 71 are nothing but course codes joined by "and".

### Which fields truly need a language model

Only two:

1. **Prerequisite logic**: the AND/OR/grade/population structure inside the prerequisite sentence.
2. **Choosing a concept-scheme value when the page's wording doesn't match the scheme's**, for example mapping
   "Typically offered: Fall Even Years" to a schedule-frequency concept. Even this is a 12-row lookup table for
   this site, so a rule may serve better than a language model.

> 💬 **C17 · Eric:** I'm open to attempting a rules-based approach. We just need a way to evaluate it. Also, "model" confused me,
> because it can mean a couple of different things. I see you meant machine learning model.
>
> ↳ **Reply:** Wording fixed throughout: it now says "language model" wherever that is meant, and "design" or "data model"
> is no longer shortened to "model".
>
> On evaluation: a lookup table can be checked completely, because there are only 12 distinct values in the
> sample. Two measures cover it. Coverage: what share of courses hit a row in the table, with every miss listed.
> Correctness: a person reviews the 12 rows once. The same hand-checked set can later score a language model on
> the same task.

Everything else is positional or labelled.

## 9. Prerequisites: the options and their trade-offs

### What CTDL offers

| Property | Value type | Definition |
|---|---|---|
| `ceterms:requires` | ConditionProfile | "Requirement or set of requirements for this resource." |
| `ceterms:prerequisite` | **Course** (a direct link, Course-to-Course only) | "Course that is required as a prior condition to this course." |
| `ceterms:corequisite` | ConditionProfile | "Resources that must be pursued concurrently." |
| `ceterms:coPrerequisite` | ConditionProfile (marked unstable) | "Resource that must be completed prior to, or pursued at the same time as, this resource." |
| `ceterms:entryCondition` | ConditionProfile | Entry requirements. The schema says: "For Courses required to be taken before entry into another Course, use prerequisite." |

The last three are all declared as more specific forms of `requires`. The schema's advice: "Consider using the
more specific subproperties of requires… where appropriate."

A **ConditionProfile** can hold free text (`description`, `condition`), links to courses
(`targetLearningOpportunity`), credit amounts, years of experience, and nested alternatives.

**How AND and OR work**, from the handbook:

> "ConditionProfiles in the same array for a requirements property should be interpreted as having their
> conditions aggregated together, while ConditionProfiles in the same array for the alternativeCondition
> property should be considered as alternatives for one another."

So siblings mean AND, and `alternativeCondition` means OR. There is **no structured field for a minimum grade**;
"with a grade of C or better" can only be text.

### The three options

Using this real sentence: *"(CHEM 36203 and CHEM 36201) or (CHEM 362H3 and CHEM 362H2)."*

**Option A: text only.** One ConditionProfile under `requires`, with the sentence copied verbatim.

- For: always correct. Found by rule, with an exact highlight. It is what every publisher in the sample does.
- Against: a machine cannot tell which courses are involved or follow the links.

**Option B: text plus a flat list of linked courses.** As A, with `targetLearningOpportunity` listing the four
courses.

- For: the links come from the page's hyperlinks, so they are extracted by rule.
- Against: **it can state something false.** Courses listed together in one profile read as "all required".
  For an "or" sentence that is wrong. It is only safe when the sentence contains no "or".

**Option C: full structure.** Nested `alternativeCondition` profiles mirroring the logic.

- For: machine-actionable. Enables prerequisite graphs and pathway tools.
- Against: needs a language model or a real parser. The language model got the logic wrong on this exact sentence (section 11).
  Grades and populations ("Walton College majors") still end up as text. No publisher in the sample does it, so
  consuming tools may not read it.

### Recommendation (for the next phase to decide)

*Revised after review comment C4: structured logic is a goal, not an optional extra.*

- Always emit **A**. It is the safe, verifiable floor.
- Add direct `ceterms:prerequisite` links **only when a rule can prove the sentence is a plain list**: one or
  more course codes joined by "and" or commas, with no "or". In the sample that covers 71 of 337 prerequisite
  sentences and 42 of 83 corequisite sentences.
- Pursue **C** for every sentence, in two tiers. First a deterministic parser for the part that follows a
  grammar: course codes, "and", "or", commas and brackets, where the codes are already hyperlinks. Then the
  language model for what the parser cannot read, such as populations ("Walton College majors") and standing
  requirements. Both tiers pass the same guards: no course code that is not in the sentence, and none dropped.
- Show which tier produced each structure. This is the natural place for the future accept/reject/correct workflow.

One further constraint: a link needs a target. `MATH 20503` is outside the five sampled subjects, so its course
record will not exist yet. Either mint CTIDs for referenced-but-unscraped courses, or leave those as text.

## 10. Provenance and the source pane

### Anchoring

"Anchoring" means recording where on the page a value came from, robustly enough to find it again.

The W3C Web Annotation standard defines two selectors that are normally stored together:

- **Position**: character offsets into the page's text. Exact, but breaks if the text shifts.
- **Quote**: the exact text plus a little before and after. Survives shifts, and is human-readable.

Storing both lets one verify the other. If the text at the stored offsets no longer equals the stored quote,
the anchor is stale, and that is detectable.

Offsets need a fixed definition of "the page's text". Because the crawl stores the raw bytes of each page and
never refetches, a text extraction computed from that stored file is stable by construction.

> 💬 **C18 · Eric:** Sounds great. I think computing a digest of the pages would also make sense.
>
> ↳ **Reply:** Agreed, and it does three jobs. Stored at crawl time, a digest of the raw bytes lets the crawler recognise
> content it already has. Stored with each piece of evidence, it pins the evidence to one exact version of the
> page. And if a page is ever re-crawled and changes, every piece of evidence tied to the old digest is known to
> need re-checking.

### Kinds of evidence the design must handle

Found in this research, each with a real example:

| Kind of evidence | Example |
|---|---|
| One text segment | Course name from the title line |
| Several text segments on one page | A prerequisite sentence plus the hyperlinks inside it |
| A text segment on a **different page** | "semester hours" on the index page, justifying the credit unit |
| Markup, not visible text | `<html lang="en">` for language |
| An external record | The Registry record for the owning organisation |
| Derived from another value | Level from the first digit of the course number |
| No source at all | The minted CTID |

> 💬 **C19 · Eric:** The word "shape" was confusing here. And be careful not to call it a "span" unless you actually need an HTML
> span; otherwise call it a segment, or even better a text segment.
>
> On "markup, not visible text": that's a great point. We'll need a way to make that visible. Maybe a way to
> toggle between an HTML DOM tree view and a rendered view. I think that would be really good.
>
> External records and derived values: we're going to want ways to surface all of those. This is such a good list.
>
> ↳ **Reply:** Wording fixed: the heading is now "Kinds of evidence", and the rows say "text segment".
>
> The toggle between a rendered view and a view of the underlying HTML is noted for the design phase. So is the
> need to give each of the seven kinds in this table its own presentation, since four of them are not a highlight
> on a rendered page.

### Reproducing the page faithfully

- For this site, saving the raw HTML is enough. Content does not depend on JavaScript.
- Styles: `robots.txt` forbids crawling `/css/`. The viewer can still reference the live stylesheets by absolute
  URL so that the reader's browser loads them; that is ordinary browsing, not crawling. The alternative is a
  small local stylesheet that imitates the look.
- The page loads 8 scripts. They should be stripped from the rendered copy.
- For JavaScript-heavy or login-protected sites (not this one), the usual technique is to capture the page
  after rendering in a real browser and inline its styles into a single file. Not needed now.

> 💬 **C20 · Eric:** Do make a note that that could be an issue in the future. In the past when I've said "make notes", let's define
> where that goes: make a document called risks and future considerations. I don't mind stripping the eight
> scripts.
>
> ↳ **Reply:** Created `qrspi/risks-and-future-considerations.md`. This is R5 there. Notes of this kind go in that file from now on.

### Linking back to the original

Courses have no anchors, so two mechanisms are available:

- **Text fragments.** A URL ending `#:~:text=ACCT%2020103.` makes current browsers scroll to and highlight that
  text on the live page. This gives a deep link per highlighted region with no cooperation from the site.
- **Per-course page.** `https://catalog.uark.edu/search/?P=ACCT%2020103` shows a single course. The viewer can
  offer this as a link for a person to click. Our scraping program must never download it, because the site's
  `robots.txt` file asks automated programs to stay out of `/search/`.

> 💬 **C21 · Eric:** That's amazing. If that works, do that.
>
> ↳ **Reply:** Will do. What I know: it is a web standard supported by current Chrome, Edge, Safari and Firefox. What I have
> not done is test it against this site. One known weakness: if the live page's wording changes, the link still
> opens the page but silently highlights nothing. Recorded as R7.

> 💬 **C22 · Eric:** "The crawler must not fetch it." I don't know what you mean by that.
>
> ↳ **Reply:** Reworded above. The site publishes a file, `robots.txt`, listing addresses it asks automated programs not to
> load. `/search/` is on that list. A person clicking a link is not an automated program, so the viewer may show
> the link. Our scraper is one, so it must never download that address. The practical effect: prerequisite links
> on the page point into `/search/`, and we resolve them by matching the course code against pages we already
> have.

## 11. Local language model probe

Task: turn a prerequisite sentence into alternatives and requirements, giving an exact supporting quote for
each. 15 real sentences, 10 of them long. Model `qwen3.5:9b`, thinking off, temperature 0, JSON-schema
constrained output.

| Measure | Result |
|---|---|
| Valid JSON | 15 of 15 |
| Quotes that are exact substrings of the input | 31 of 31 |
| Median time per sentence | 2.4 s (range 1.7 to 8.0 s) |
| Sentences where a real course code was dropped | 0 |
| Sentences with something invented or misplaced in the course-code field | 3 of 15 |

I read four outputs closely. Two had the logic wrong:

- *"(CHEM 36203 and CHEM 36201) or (…)"*: it found the four alternatives correctly and explained them correctly
  in prose, but labelled each pair "one of" when the sentence says "and".
- *"Completion of Level I courses and NURS 41152, NURS 41534, …"*: it labelled six required courses as "one of",
  and **invented five course codes** (NURS 40001 to 40005) to stand for "Level I courses".

What this establishes:

- Verbatim quoting is reliable enough to build on.
- **A substring check is necessary but not sufficient.** It proves the quote is real, not that the reading is right.
- Cheap deterministic guards catch a lot: every course code in the output must appear in the input, and the set
  of codes must match the set of hyperlinks.
- At 2.4 seconds each, the 337 prerequisite sentences in five subjects take about 15 minutes.
- Sample size is 15, and I checked logic by hand on only four. This is a signal, not a measurement.

> 💬 **C23 · Eric:** I love these measurements. I don't really know what to do about the wrong logic just yet. We don't need to worry
> about how good the language model is right now. We'll just plug in any one, and evaluate and improve it later.
>
> ↳ **Reply:** Noted for the design phase: the language model sits behind a replaceable boundary, and its output is always labelled as such. Its known weakness is R3.

## 12. Terms that came up

**ACTS.** The Arkansas Course Transfer System: the state's list of courses guaranteed to transfer between
Arkansas public institutions. "ACTS Equivalency = ACCT 2003" says this course is the university's version of
statewide course ACCT 2003. The faithful CTDL home is `ceterms:identifier`, whose value names the scheme and the
code:

```json
"ceterms:identifier": [{
  "@type": "ceterms:IdentifierValue",
  "ceterms:identifierTypeName": { "en-US": "Arkansas Course Transfer System (ACTS) Course Index Number" },
  "ceterms:identifierValueCode": "ACCT 2003"
}]
```

CTDL also has `TransferValueProfile` for describing transfer credit formally. That is a separate, heavier record
that the state would own, and I found no ACTS records of that kind in the Registry.

**Corequisite.** A course that must be taken in the same term. CTDL: `ceterms:corequisite`.

**Pre- or corequisite.** May be taken before or alongside. CTDL: `ceterms:coPrerequisite` (marked unstable).

**Cross-listed.** One course offered under two subject codes, for example an English course that is also a
Gender Studies course. CTDL has no dedicated property. Closest fits: `ceterms:isSimilarTo` ("Another
functionally similar entity") linking the two records, or `ceterms:sameAs` if they are treated as one thing.

**Equivalent to.** In this catalog it mostly pairs a course with its honors twin. Same options as cross-listing.

**May be repeated for up to N hours.** A limit on how many times credit can be earned. **CTDL has no property
for it.** It stays in the description. Worth surfacing in the viewer as "seen on the page, no CTDL home".

**Typically offered.** The terms a course runs. `ceterms:offerFrequencyType` ("Type of frequency at which a
resource is offered… how often something starts") is the property, but its concept scheme speaks in cadences:
Annually, Semi-Annually, Quarterly, Irregular, and so on. There is no concept for "Fall" or "Spring". So "Fall
and Spring" maps to Semi-Annually and loses which semesters. No publisher in the sample uses this property.

## 13. Prior art: `CredentialEngine/ctdl-xtra`

Studied at commit `b51a362` (2026-10-01), by reading the code. Nothing was run. A helper did the reading; I
checked its main claims against the source files myself.

### What it is

Credential Engine's own tool for this job. It has two parts:

- **A Python command-line tool**, which is the real implementation. Four stages: crawl, discover, extract,
  transform. It is working code with a large test suite.
- **A web app**, which is a shell. Its pages for sources, crawls, benchmarks and publishing display fixture
  data, and its buttons show "would…" messages.

The repository has a single commit, so its history is not visible.

### How it compares with this mockup

| Topic | ctdl-xtra | Consequence for us |
|---|---|---|
| Language models | **None, on purpose.** Its stated non-goals include "LLM classification or extraction". Everything is hand-written rules. | Our language-model tier is a deliberate difference. |
| Publishing | A stated non-goal. | Same as ours (C2). |
| CTIDs | Never created. "Never invents CTIDs." It can only look up an existing one by web address. | Minting with a ledger is a deliberate difference. |
| Crawling | Headless browser by default; obeys `robots.txt`; resumes without refetching; stores each page with a sidecar file holding a digest of the bytes, final address, status and time. Very slow by default: one page per 180 seconds. | Confirms the crawl design in C18. The sidecar is worth copying. |
| CourseLeaf | Recognises the same `courseblock` markup and splits the same title line, including five-digit codes. **But extraction skips any page holding more than one course.** | Our subject pages hold 46 to 171 courses each. The official tool would skip all of them. |
| Fields mapped to CTDL | Code, name, description, credits, prerequisites. Corequisites and credit ranges are recognised but left unmapped. | We go further: see section 6. |
| Credit | `creditValue: [{"ceterms:value": 3}]`, with no type and no unit. | Ours follows the published form in section 7. |
| Prerequisites | Text only: `requires: [{"ceterms:name": "…"}]`. No "and"/"or", no links. | Structured logic (C4) is new ground. |
| Owner, language, lifecycle status | Never produced. | We evidence them: see section 5. |
| Provenance | An older code path records, per field: the excerpt, character offsets into a normalised text, digests of the excerpt and the page, and a locator; a validator re-cuts the text and checks it matches. **The current command-line tool drops all of that** and keeps only the raw text and a note. | The idea matches section 10 closely. Persisting it end to end, and showing it, is the gap. |
| Rationale and confidence per field | None. | New ground (C15). |
| Viewer | A two-column "source document" versus "actual/golden" page that renders placeholder text. No highlighting. | The side-by-side layout is the same instinct; ours would be the working version. |
| Human review | Designed on paper (two independent reviewers, statuses of candidate, reviewed and signed) but not built. | Aligns with the later-version plans in `01-questions.md`. |
| Evaluation | Chooses a "golden sample" of pages by coverage of rare features. No scorer exists yet. | The sampling idea is worth borrowing when we evaluate (C17, C23). |

### Worth borrowing

- The evidence record: excerpt, offsets, digests, and a validator that re-cuts and compares.
- Marking each CTDL property with the source fields it came from and how it was mapped, plus an explicit list
  of what could not be mapped.
- "Omit, never invent" as a discipline. For example, a single credit figure never becomes a range.
- Its vocabulary of field names (`course_id`, `course_credits_min`, `course_prerequisites` and so on), if
  alignment with the official tool matters later.

### One tension to resolve

Its rule is never to invent a CTID. Our plan mints them. These are compatible only because we do not publish:
a minted CTID in an unpublished mockup is a placeholder. The viewer should say so wherever it shows one.

## 14. Open items for the next phase

1. **Course level.** The first digit of the course number looks like level, but the catalog's numbering policy
   page was not located. Until it is, `audienceLevelType` would be an unverified derivation.
2. **Schema freshness.** The schema copy is from June 2026. Someone should confirm in a browser that nothing
   relevant changed.
3. **"Pending Policy".** The Course rows in the Minimum Data Policy are all flagged pending. The six required
   properties match the parent class's in-force rules, so the risk is low.
4. **Unresolvable links.** Decide what to do with references to courses outside the scraped subjects.
5. **Catalog year and CTIDs.** Whether a new edition means new CTIDs is the publisher's call.
6. **Description boundaries.** Publishers differ on whether the description keeps the prerequisite sentence (the
   Brookdale example does). Whether ours keeps or trims the labelled tail is a design choice.
7. **Name format.** The Brookdale example puts the code in the name ("ACCT101 - Principles…"). Others don't.
   With `codedNotation` carrying the code, a bare name avoids duplication.
8. **Sample breadth.** Patterns were measured on 5 of 168 subjects. Music, languages and engineering may hold
   variants not seen here. The rules should count and report anything they fail to match.
9. **CTID versioning guidance.** No explicit Credential Engine rule was found on when a changed course needs a new
   CTID (see comment C8). Worth asking them directly.

> 💬 **C24 · Eric:** All very interesting. I'm glad we're saying those are out of scope for right now.

## 15. Files saved alongside this document

| Path | Contents |
|---|---|
| `reference/ctdl/ctdl-schema.json` | Full CTDL schema: 139 classes, 410 properties, 34 concept schemes with 448 concepts |
| `reference/ctdl/ctdl-context.json` | The JSON-LD context |
| `reference/ctdl/minimum-data-policy.txt` | Policy page as text |
| `reference/ctdl/handbook.txt` | Handbook as text |
| `reference/registry-examples/uark-organization.json` | The university's Registry record |
| `reference/registry-examples/course-brookdale-acct101.json` | Example course with a prerequisite |
| `reference/registry-examples/course-brookdale-psyc285.json` | Second example course |
| `reference/llm-probe-prerequisites.json` | Raw language model outputs from section 11 |
