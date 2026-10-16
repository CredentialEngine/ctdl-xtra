# Risks and future considerations

The standing place for "make a note of that". Started 2026-10-07. Each entry says where it came from; `C` numbers
refer to review comments in `02-research.md`.

## Risks

### R1. The CTDL reference material is an archived copy, not the live site

- **What:** `credreg.net` is the correct, official home of the CTDL schema. It blocks automated access, so the
  schema, Minimum Data Policy, handbook and "About the CTID" page were taken from Internet Archive snapshots
  dated June 2026.
- **Why it matters:** every CTDL definition the tool shows a reviewer comes from this copy. If a term changed
  after June, the tool would quote an outdated definition with full confidence.
- **History:** Eric raised the concern that the source might be out of date, then confirmed credreg.net is the
  right site and asked that the concern stay visible (C6).
- **To close it:** save the live terms page from a browser into `reference/ctdl/` and compare it with the snapshot.
- **Until then:** any report or screen that quotes a CTDL definition should state the snapshot date.

### R2. The output must not be published

- **What:** nothing this project produces should be sent to the Credential Registry. Its validity is unproven (C2).
- **Why it matters:** the Registry is public and the University of Arkansas has a real record there. A wrong
  course record published under its name would be a real-world error.
- **Guard:** no publish step exists in the design. Minted CTIDs are placeholders and should be labelled as such.

### R3. The language model reads logic unreliably

- **What:** in a 15-sentence probe, `qwen3.5:9b` quoted the source exactly every time but mislabelled "and" as
  "one of" and once invented five course codes.
- **Why it matters:** a check that quotes are real does not catch a wrong reading.
- **Guards identified:** every course code in the output must appear in the input; none may be dropped; the
  verbatim sentence is always kept.
- **Status:** quality is deliberately not a concern yet. The language model is to be replaceable and evaluated
  later (C23). The probe was small: 15 sentences, four checked by hand.

### R4. Patterns were measured on 5 of 168 subjects

- **What:** every figure about title lines and labelled sentences comes from ACCT, CHEM, CSCE, ENGL and NURS.
- **Why it matters:** music, languages and engineering may use forms not seen here.
- **Guard:** rules must count and list whatever they fail to match, so gaps show up as numbers.

### R5. Other sites may need a real browser, or a login

- **What:** this catalog is plain HTML. Other sites build their pages with JavaScript or sit behind a login (C20).
- **Why it matters:** saving the raw HTML of such a page captures little or nothing.
- **Known technique:** load the page in a real browser, then save the rendered result with its styles inlined
  into one file. Credential Engine's own tool crawls with a headless browser by default.
- **Status:** not needed for this site. A reason to keep "fetch a page" separate from everything after it.

### R6. The site's stylesheets may not be crawled

- **What:** `robots.txt` disallows `/css/`, `/js/`, `/fonts/` and `/images/`.
- **Why it matters:** the goal is to preserve the page's look in the source pane.
- **Options:** let the reader's browser load the live stylesheets, which is ordinary browsing; or write a small
  stylesheet that imitates the look. The first depends on the live site staying up and unchanged.

### R7. Deep links to the live page can fail silently

- **What:** text-fragment links (`#:~:text=…`) make a browser scroll to and highlight a phrase (C21).
- **Why it matters:** if the live wording changes, the link still opens the page but highlights nothing, with no
  error. Not yet tested against this site.
- **Guard:** the local snapshot remains the record of evidence. The live link is a convenience.

### R8. The Course rules in the Minimum Data Policy are marked pending

- **What:** every Course row is flagged "Pending Policy".
- **Why it matters:** the required set could change before it takes force.
- **Mitigation:** the six required properties match the rules already in force for the parent class.

### R9. No known rule for when a course needs a new CTID

- **What:** the schema says different versions need different CTIDs. No Credential Engine guidance was found
  on what counts as a new version of a course (C8).
- **Why it matters:** it decides whether a CTID ledger is keyed by course, or by course and catalog year.
  Choosing wrong either breaks links or loses history.
- **To close it:** ask Credential Engine.

### R10. Links to courses that have not been scraped

- **What:** prerequisites often name courses in other subjects, for example `MATH 20503` from an ACCT course.
- **Why it matters:** a structured link needs a target record. With five subjects scraped, many targets are missing.
- **Options:** mint placeholder identities for referenced courses, or keep those references as text until the
  subject is scraped.

### R11. The picture of "what publishers do" rests on a skewed sample

- **What:** the 1,000 published courses examined came from five publishers, one of which owns 691.
- **Why it matters:** statements such as "nobody structures prerequisites" describe those five.

### R12. The official tool takes the opposite position on two points

- **What:** `ctdl-xtra` lists as non-goals both language-model extraction and inventing CTIDs. This project does both.
- **Why it matters:** if the mockup is meant to inform that tool, these differences need to be argued for, not
  assumed. See section 13 of `02-research.md`.

### R13. CTDL may not express every prerequisite structure exactly

- **What:** as read from the handbook, one ConditionProfile holds a single set of alternatives. A requirement
  such as "one of these four, and one of these three" has two. Found while writing `03-specification.md`,
  section 7.4, on the real sentence for ACCT 20103.
- **Why it matters:** such sentences can only be written "partly structured", with the rest as text.
- **Status:** this reading is not confirmed by a Credential Engine example. Worth asking them, alongside R9.

### R14. The catalog's course-numbering policy appears to be on the index page

- **What:** the index page has a second tab, "Course Numbering", that the research did not read. Found during
  the build, 2026-10-07, in the stored copy of the page.
- **Why it matters:** decision D11 leaves course level out because "the catalog's numbering policy has not been
  found". If that tab states what each first digit means, `ceterms:audienceLevelType` could be evidenced.
- **Status:** not acted on. Version 1 still leaves level out and reports it as left out.

### R15. A possible way around R13

- **What:** the handbook says ConditionProfiles side by side under one property are "aggregated together". A
  sentence with two sets of choices might therefore be written as two sibling profiles, each with one set.
- **Why it matters:** it could remove most "partly structured" results.
- **Status:** not done. The specification asks for one profile per sentence, and this reading is as unconfirmed
  as R13 itself. Worth putting to Credential Engine in the same question.

### R16. No stable CTID, and no check of whether a course is already in the Registry

- **Noted by Eric, 2026-10-08.**
- **What:** a CTID is made at random the first time a course is seen and is stable only because the ledger
  on this machine remembers it. Nothing looks in the Registry to see whether the course is already there.
- **Why it matters:** a reviewer cannot tell a new course from one the Registry already holds. Proposing a
  course that exists would create a duplicate under a second CTID. A second machine, or a lost ledger, would
  mint different CTIDs for the same courses.
- **What is needed:**
  1. An algorithm that arrives at the same CTID for the same resource every time, for anyone, from what the
     resource is. It depends on R9: what counts as the same course across catalog years.
  2. A look-up of that CTID in the Registry, shown to the reviewer beside the proposal, so that they verify
     whether the course already exists.
  3. Probably also a search by owner and course code, because a course the university published itself
     would carry a CTID of its own choosing that no algorithm of ours would arrive at.
- **Probable approach (Eric, 2026-10-08):** by class of resource. For a course, take its course ID from the
  catalog and the owning organization, and look for it in Credential Engine's Credential Finder database.
  A match is shown to the reviewer beside the proposal; its CTID is the one to use. A stable way to make a
  CTID is then needed only for courses that are new.
- **State:** not built. The viewer holds a place for it: the CTID field, first in each record, marked
  "not built yet", whose detail shows the reviewer's two verdicts disabled (specification RG1 to RG3).
  It makes no request to the Registry.
- **To close it:** ask Credential Engine whether CTIDs may be derived (for example a name-based UUID from the
  owner's CTID and the course code) and how they expect existing records to be found.

## Future considerations

Not for version 1. Recorded so they shape decisions made now.

### Review workflow (from `01-questions.md`)

- Reviewers accept, reject or correct each field.
- Reviewers annotate why they corrected something: where the extraction went wrong.
- The experience is streamlined, for example moving field by field with the keyboard.
- `ctdl-xtra` has an unbuilt design for this with two independent reviewers and three statuses (candidate,
  reviewed, signed). Worth reading before designing ours.

### Teaching as a purpose

- Reviewers are expected to be new to CTDL. The tool should make them more expert as they use it.
- Wherever a definition appears, show example values and link to all the options.
- Every field should be able to explain why this property, why this structure, and what the alternatives were (C15).

### Evaluation

- A hand-checked reference set, so that rules and language models can be scored on the same task (C17, C23).
- `ctdl-xtra` picks its reference pages by coverage of rare features, which is a useful way to choose them.

### Beyond this site

- Other CourseLeaf catalogs, then other catalog systems. Rules are kept as a declarative registry for
  readability now, which also prepares for this.
- Documents other than web pages: PDFs and images were named in the crawl requirements.

### CTDL gaps worth raising with Credential Engine

- No property for "may be repeated for up to N hours of credit".
- No way to say which terms a course runs in; only how often.
- No structured field for a minimum grade in a prerequisite.
- No dedicated property for cross-listed courses.
