# Research B1: what each column F label looks like on the saved pages

Research phase of QRSPI for "every CLI extraction label as a field rule" (`../01-questions.md`, Part B, B1). Facts
only. Data comes from the shared Azure root `zz-scratch-review-ui-v3`, read only, on 2026-11-02. Page files were
downloaded to the local cache (`~/.cache/golden-datasets`) with `pages get`. Nothing in Azure was written. Anything
**inferred** rather than checked is marked *Inferred*.

The question for each label is what the page **prints**, in its own words (A3.12). Mapping to CTDL vocabularies is
out of scope. Row 24 is read as `ceterms:prerequisite>ceterms:targetLearningOpportunity` (D10).

Words used below:

- **printed**: the record shows the value as text.
- **implied**: the value follows from something printed (a number, a URL, a field label), but the words aren't there.
- **outside**: printed on the page, but outside the course record (the occurrence element). A field rule can't reach
  it today (see "Limits of today's rule types").
- **absent**: not on the page.

---

## Sample

One course occurrence per page, from the latest extraction's `locator-course-page`, 22 pages per catalog, picked by
`md5(page_stem)` (repeatable). For the catalogs with many courses per page (CCSF, Marshall, WVU) the counts were also
run over **every** course on those 22 pages, to check rare labels.

| Catalog | Platform | Locator (record) | Sample | Every course on the 22 pages | Wider page scan |
|---|---|---|---|---|---|
| AVC | eLumen | the whole `#mainContent` of a course page | 22 | (1 per page) | 100 pages |
| CCSF | CurricUNET | `.course-summary-wrapper` | 22 | 265 | all 118 course pages |
| Marshall | CourseLeaf | `div.courseblock` | 22 | 658 | all 223 course pages |
| UALR | Acalog | the content root `td.block_content` of a course page | 22 | (1 per page) | 100 pages |
| WVU | CourseLeaf | `div.courseblock` | 22 | 18,358 | (the 22 pages hold 18,358 of 22,023 courses) |
| UARK training | custom portal | the whole content root of a course page | 22 | (1 per page) | all 118 pages |

UARK training's catalog folder is `training-uark-edu-portal-training`.

---

## Summary table: label × catalog

Count = sampled courses (of 22) where the label is printed (P), implied (I) or outside the record (O). 0 = absent.
"=parent" means the text is the same as the parent label's text.

| # | Label (column F) | AVC | CCSF | Marshall | UALR | WVU | UARK |
|---|---|---|---|---|---|---|---|
| 1 | `ceterms:identifier` | 22 P | 22 P | 22 P | 22 P ¹ | 22 P | 0 ² |
| 2 | `ceterms:name` | 22 P | 22 P | 22 P | 22 P | 22 P | 22 P |
| 3 | `ceterms:description` | 22 P | 22 P | 19 P | 19 P ³ | 22 P | 22 P |
| 4 | `ceterms:subjectWebpage` | 22 I (URL) | 22 I | 22 I | 22 I | 22 I | 22 I |
| 5 | `ceterms:codedNotation` | 22 P | 22 P | 22 P | 22 P ¹ | 22 P | 0 |
| 6 | `ceterms:isNonCredit` | 2 I ("0.0 Units") | 22 P ("Credit (Degree Applicable)") ⁴ | 0 ⁵ | 0 | 0 | 6 P, 22 I |
| 7 | `ceterms:deliveryType` | 0 | 0 | 0 ⁶ | 0 | 1 (prose) | 22 P |
| 8 | `ceterms:deliveryTypeDescription` | 0 | 0 | 0 | 0 | 0 | 0 ⁷ |
| 9 | `ceterms:inCatalog` | 22 I | 22 I | 22 I | 22 I ⁸ | 22 I | 22 I |
| 10 | `ceterms:contentDescription` | 0 ⁹ | 0 ⁹ | 0 ⁹ | 0 ⁹ | 0 ⁹ | 14 P? ¹⁰ |
| 11 | `ceterms:learningMethodType` | 22 I (hour labels) | 22 P | 0 | 7 P | 0 | 21 P |
| 12 | `ceterms:learningMethodDescription` | 0 | 0 | 0 | 7 P | 0 | 0 ⁷ |
| 13 | `ceterms:keyword` | 0 | 0 | 4 P? (Attributes) | 1 P? (law: Practice Area) | 0 | 0 |
| 14 | `ceterms:subject` | 0 | 22 O (+ code in record) | 22 O | 0 | 0 | 0 |
| 15 | `ceterms:creditValue` | 22 P | 22 P | 22 P | 21 P | 22 P | 0 ¹¹ |
| 16 | `ceterms:creditValue>schema:minValue` | 22 P (labelled) | 1 P (range) | 6 P | 3 P (words) | 5 P | 0 |
| 17 | `ceterms:creditValue>schema:maxValue` | 22 P (labelled) | 1 P | 6 P | 3 P (words) | 5 P | 0 |
| 18 | `ceterms:creditValue>ceterms:creditUnitType` | 22 P ("Units") | 22 I (no word) | 22 P ("Credit hours") | 21 P ("credit hours") | 22 P ("Hours") | 0 |
| 19 | `ceterms:prerequisite` | 9 P | 6 P | 7 P | 16 P | 12 P | 0 |
| 20 | `ceterms:prerequisite>ceterms:description` | 9 =parent | 6 =parent | 7 =parent | 16 =parent | 12 =parent | 0 |
| 21 | `ceterms:prerequisite>ceterms:targetLearningOpportunity` | 7 P | 5 P | 7 P (links) | 5 P (links) | 9 P (links) | 0 |
| 22 | `ceterms:prerequisite>ceterms:alternativeCondition` | 7 ("or") | 2 | 0 | 3 | 5 | 0 |
| 23 | `ceterms:recommends` | 5 P ("Advisory:") | 11 P ("Recommended Prep:") | 0 | 1 P | 0 | 14 P? ("Prior Learning") |
| 24 | `ceterms:recommends>ceterms:description` | 5 =parent | 11 =parent | 0 | 1 =parent | 0 | 14 =parent |
| 25 | `ceterms:recommends>ceterms:targetLearningOpportunity` | 5 P | 10 P | 0 | 1 P | 0 | 0 |
| 26 | `ceterms:recommends>ceterms:alternativeCondition` | 3 ("or") | 7 | 0 | 0 | 0 | 0 |
| 27 | `ceterms:hasPart` | 0 | 0 | 0 | 0 | 0 | 0 ¹² |
| 28 | `ceterms:learningOpportunityType` | 3 (title word) | 5 (title word) | 7 (title word) | 8 (title word) | 11 (title word) | 22 ("course" / "program") |
| 29 | `ceterms:estimatedDuration` | 22 hours only ¹³ | 22 hours only | 0 | 4 ("per week") | 0 | 22 P |
| 30 | `ceterms:estimatedDuration>ceterms:exactDuration` | 0 | 0 | 0 | 0 | 0 | 22 P? ¹⁴ |
| 31 | `ceterms:estimatedDuration>ceterms:minimumDuration` | 0 | 0 | 0 | 0 | 0 | 0 |
| 32 | `ceterms:estimatedDuration>ceterms:maximumDuration` | 0 | 0 | 0 | 0 | 0 | 0 |
| 33 | `ceterms:estimatedDuration>ceterms:description` | 0 | 0 | 0 | 4 P (sentence) | 0 | 1 P (sentence) |

Notes:

1. UALR law courses print the code after the title (`Advanced Delta Divorce Clinic - LAWW 61893`). Today's
   `course-code` rule found 20 of 22, missing the 2 law courses.
2. UARK prints no course code. The only stable key is the URL's `course=` slug.
3. Counts for description use today's `course-description` matches. Marshall's 3 misses print no description (only
   "Grade Mode"). UALR's misses are records that print only "Was ASCI 8344.".
4. CCSF prints a credit status on every course. Over all 118 pages: `Credit (Degree Applicable)` 1,719,
   `Noncredit` 192, `Credit (Non-Degree Applicable)` 16. None of the 22 sampled courses is Noncredit.
5. Marshall prints the attribute `Not Degree Applicable` (60 times on 223 pages) and grade mode
   `Credit/No Credit Grade Only`. Neither says the course carries no credit.
6. Marshall's Attributes hold `Online Course` and `HyFlex Course` once each on 223 pages. Not in the sample.
7. UARK explains each Modality value in a popover, but the text is in the `data-bs-content` **attribute**, not in
   visible text.
8. UALR prints the catalog's name in the record (`2026-2027 Undergraduate Catalog`, `2025-2026 Law School Catalog`),
   not its URL.
9. No separate field. Some descriptions contain a topics sentence ("Topics include …"): AVC 7, CCSF 2, Marshall 1,
   UALR 3, WVU 4.
10. UARK prints `Learning Objectives` / `Course Outcomes` lists (14 of 22). They're outcomes, not topics. Two of 118
    pages have a `Course Content` heading.
11. One UARK course says credit can be awarded for a university course: "you will be awarded three credit hours for
    DASC 16003". That's another course's credit.
12. UARK prints series membership ("This is the fifth course of the COVID-19 and the History of Pandemics series",
    10 of 118 pages). That's the inverse of `hasPart`.
13. "Hours only" means total contact hours (AVC `Total Course In-Class (Contact) Hours 54.0`, CCSF
    `Hours: Lecture - 52.5`), not a span of time. Whether they count as a duration is a decision, not a fact.
14. UARK's `Access to Course: 6 Months` is how long you can access the course, which may not be how long it takes.

---

## Per catalog

### AVC (eLumen), course pages

Record = the course page's `#mainContent`. Stem example: `avc-elumenapp-com-catalog-2026-27-course-cfe116-adfe84a9c1`.

- **Credit.** Printed twice:
  - `p.header-x-meta`: `3.0 Units`, `1.0 - 8.0 Units` (CFE 199, ANTH 199).
  - A "Units and Hours" card with labelled values: `Minimum Credit Units 3.0`, `Maximum Credit Units 3.0`. Min and max
    are printed **even when they're equal**. So min and max are obvious children on every course, and the unit word is
    `Units`.
  - 2 of 22 records have a second card (`Variable Lab Hours`, `Profile Name`). ANTH 199's second card is all zeros.
- **Requisites** sit in `.introtext`, one per line (`<br>`), before the description:
  - `Prerequisite: Completion of ATH 100 and completion of or concurrent enrollment in ATH 103.` (ATH103L)
  - `Advisory: Completion of ENGL C1000 or C1000H.` (CFE122): this is `recommends`.
  - `Corequisite: Concurrent enrollment in RADT 101.` and `Limitation on Enrollment: …` have no column F label.
  - CFE116 prints three lines: Limitation, Advisory, Prerequisite.
  - DA205 puts its advisory and description in one line: `Advisory: Completion of DA 125 or at least two years of tap
    dance experience. This course is a continuation …`. A "line" rule overruns there. This is why today's
    `course-description` v3 regex is so long.
  - Course codes in requisites are plain text, not links (`ACRV 112 and ACRV 113`).
- **Hours.** The card prints `Total Course Lecture Hours 54.0` and `Total Course Lab Hours 0.0`. The method words are
  the field labels. A method is implied when its hours are above 0: Lecture only 17, Lecture + Lab 5 (CA183), Lab only
  (ATH103L).
- **Noncredit.** `0.0 Units` is printed on RE 903 and BUS 912 (2 of 22; 9 of 100 pages). The word "Noncredit" shows
  only in the site's navigation menu, which is on every page and outside the record.
- No delivery, keyword or subject in the record.

### CCSF (CurricUNET), department pages

Record = `.course-summary-wrapper`, many per page. Stem example: `ccsf-curricunet-com-catalog-iq-courses-3-131-b16b97a1a9`.
Each value is its own span:

| Span | Example | Label |
|---|---|---|
| `.course-unit-range` | `(3.0)`, `(0.5-3.0)` (GEOL91) | creditValue, min / max when a range (1 of 22; 5 of 265) |
| `.course-Type` | `Credit (Degree Applicable)`, `Noncredit` | isNonCredit |
| `.course-lab-lec-label > span` (`.lec-hours`, `.lab-hours`, …) | `Lecture - 52.5`; `Lab - 17.5` | learningMethodType (1 per course 18, 2 per course 4; 194 / 71 of 265). Kinds seen: Lecture, Lab, Activity, Work Experience |
| `.course-requisites` | `Prerequisite: Intermediate algebra or higher`⏎`Corequisite: PHTC 102`⏎`Recommended Prep: Readiness for college-level English or ESL 188` | prerequisite, recommends (lines split by `<br>`) |
| `.course-Field-Trips` | `Field Trips: Optional` | none |
| `.course-uc-xfer` | `UC Transferable` | none |
| `.course-notes` | `Catalog Notes: Formerly …` | none |
| `.course-subject` | `MGT `, `R F ` | the subject's code |

- No unit word is printed next to the credit number (`(3.0)`).
- A Noncredit record (EMT 5005, stem `…courses-3-69-3005021253`): `(0.0) Noncredit Hours: 40`. It shows total hours with
  no lecture / lab split.
- The subject's name is the page heading `MGT - Management`, **outside** the record.
- Course codes in requisites are plain text. They use spaced subjects (`O H 50`), so a code regex has to allow them.

### Marshall (CourseLeaf), subject pages

Record = `div.courseblock`. Stem example: `catalog-marshall-edu-undergraduate-courses-az-cybr-4310ecfb80`.

- **Credit:** `span.credits`, `3 Credit hours`, `1-4 Credit hours` (6 of 22; 162 of 658 are ranges).
- **Prerequisite:** a second `.courseblockextra` that starts with `Pre-req:`. Its course codes are separate links,
  `a.bubblelink.code`: `CS 105 or CS 110 or CS 110H.` (CYBR 210). Links per prerequisite on the 658 courses: 1 (118),
  2 (30), 3 (38), 4 (17), up to 13.
  - 23 of 658 also put one in the description, in brackets: `(PR: MTH 546)`, `(Prerequisite: MKT 340)`.
  - `or` appears in 82 of 658 prerequisites.
- **Attributes:** `Attributes: No Textbook Required, Onsite Learning Experience`. One text, split by `,` (137 of 658).
  The values are mostly gen-ed tags (Natural Sciences 271, Onsite Learning Experience 264, No Textbook Required 245,
  Capstone Course 99, …, Thesis 59, PE Activity 51, Online Course 1, HyFlex Course 1, on 223 pages). They're the
  nearest thing to `keyword`. A few are delivery (`Online Course`, `HyFlex Course`) or type (`Capstone Course`,
  `Thesis`) words.
- **Subject:** the page `h1`, `Statistics (STA)`, **outside** the record.
- `Grade Mode: Normal Grading Mode` on every course has no label.

### UALR (Acalog), course pages

Record = the content root `td.block_content`. Stem example: `catalog-ualr-edu-preview-course-nopop-php-catoid-43-coid-136333-5ef9159f35`.

- **Most fields are bare text nodes** between `<br>`s, not elements: the credit line, the hours, the description and
  the text of `<strong>Prerequisites:</strong>`. Only the label (`strong`) and the course links are elements.
- **Credit is in words.** Examples:
  - `Three credit hours.`
  - `One, two, three, or four credit hours.` (GEOL 49901)
  - `One to nine credit hours to be determined at the time of registration.` (IFSC 90003, in the description)
  - Law: `<strong>Credits Hours:</strong> 3`.
  - Min and max are obvious to a reader but they're number **words**.
- **Hours / method** come in one sentence: `Three hours lecture. Three hours laboratory per week. Four credit hours.`
  (BIOL 23394, 7 of 22). That sentence is the closest thing to `learningMethodDescription`, and the words `lecture` /
  `laboratory` to `learningMethodType`.
- The title (`h1`) and the credit text run together in the record's text: `Computer SecurityThree hours lecture.`
  (CPSI 56003). A regex can still find the credit words, but not by line.
- **Prerequisites:** `Prerequisites: HIST 21103 , HIST 21203 , and six hours of upper-level United States history.`
  Course codes are links (`a[aria-label^="View course details"]`), but other links in the record (corequisites,
  description) are the same kind of link.
  - `ENGL 10103  recommended.` (RELS 20503) is a recommendation inside a prerequisite.
  - `Prerequisite or Corequisite: GEOL 11103 .` (GEOL 11101).
- **Law catalog** (2 of 22, `catoid=44`) has a different layout. It prints:
  - `Practice Area: Civil Practice , Family Law , Practice Skills , Litigation , Public Interest Law`, five links split
    by ","
  - `Fulfills these Designated Graduation Requirements: Experiential Learning`
  - `Required: Elective`

### WVU (CourseLeaf), school and all-courses pages

Record = `div.courseblock`. Stem example: `catalog-wvu-edu-undergraduate-courses-fb2fb84d0b`.

- **Credit** is the end of the title: `3 Hours.`, `1-6 Hours.` (min / max obvious: 6,528 of 18,358). Other shapes:
  `1,2 Hour.` (NSG 486, a list, not a range) and `50-75 Hours`. 128 of 18,358 titles don't fit `N Hours.` / `N-M Hours.`.
- **Prerequisite** is the first sentence(s) of `.courseblockdesc`: `PR: ECON 202 and (ECON 225 or STAT 211 or STAT 215)
  with a minimum grade of C- in all.`
  - It's prerequisite text, then the description, in one paragraph. The `PR:` part ends at a `.` that's followed by
    a capital letter.
  - 10,155 of 18,358 courses have one.
  - Course codes are `a.bubblelink.code` links. Links in the whole description: 1 to 15 per course. The prerequisite
    can also hold a corequisite (`… and PR or CONC: FIS 324.`, 536 courses), so "all links" mixes the two.
- **Delivery** appears only in prose, in 114 of 18,358 descriptions: `This course is offered in an online synchronous
  format`, `Online, 3-credit graduate course`.

### UARK training (workforce portal)

Record = the whole content root of a course page. Stem example:
`training-uark-edu-portal-training-cmd-catalog-course-bookkeeping-quickbooks-16d255cb82`.

- **Modality** is a list of links, `p.course-descr.fw-bold a.btn-link`: `Online` `Self-Paced`.
  - It mixes delivery (Online, Hybrid, In-Person, Blended) with method (Self-Paced, Instructor-led, Instructor
    Interaction).
  - Counts on 118 pages: Online 119, Self-Paced 107, Instructor-led 25, Hybrid 10, In-Person 5, Blended 3.
  - Usually 2 values per course (21 of 22).
  - The same words print again in the side panel (`Register NowOnline   Self-Paced`).
- **Duration:**
  - `Contact Hours:  120` (22 of 22).
  - `Access to Course:  6 Months` (22 of 22, in months, days, weeks or a year).
  - Prose, once: `Approximately 16 hours to complete the course. Registrants will have 4 weeks to complete the course.`
    (asphalt course).
- **Noncredit:** printed in prose, `This noncredit course is beginner-friendly …` (6 of 22; 30 of 118). *Inferred:* every
  UARK course is noncredit (a workforce catalog with no credit values).
- **Prior Learning** section (14 of 22; 67 of 118): `This professional skills training course is beginner-friendly,
  with no prior expertise required. However, to ensure success, students should:` then a `ul` of items. It's advice,
  not a requirement, so it reads as `recommends`. No page prints "Prerequisite".
- **Type words:** `This online program …`, `this certificate, the third of a three-certificate series`,
  `This noncredit course`.
- **Script text inside the record.** The content root holds inline `<script>` and `<style>`. `text_of` includes their
  text (`document.title = …`, CSS rules). Any `regex` rule over the whole record sees it.

---

## Multiple-value labels (D5: how a rule splits a list)

| Label | Catalog | Values per course (sample) | How the items are printed |
|---|---|---|---|
| learningMethodType | CCSF | 1 (18), 2 (4) | **separate elements** (`.lec-hours`, `.lab-hours`), also "; " between them |
| learningMethodType | AVC | 1 (17), 2 (5) | implied by two labelled numbers; no list on the page |
| learningMethodType | UALR | 1 (4), 2 (3) of 7 | **all regex matches** in one sentence (`N hours lecture`, `N hours laboratory`) |
| deliveryType + learningMethodType | UARK | 1 (1), 2 (21) | **separate elements** (`a.btn-link`), one list for both labels |
| keyword (Attributes) | Marshall | 1–3 | **one text split by ","** |
| keyword / subject (Practice Area) | UALR law | 5 | separate links, also "," between them |
| prerequisite | all | 1 per course in every sample | one block per course. AVC / CCSF: **lines split by `<br>`** in one element, picked by their start word (Prerequisite / Advisory / Recommended Prep / Corequisite) |
| prerequisite>targetLearningOpportunity | Marshall | 1–13 (658 courses) | **separate links** inside the prerequisite element |
| prerequisite>targetLearningOpportunity | WVU, UALR | 1–15 | links, but **not scoped**: the same kind of link appears in the corequisite and description |
| prerequisite>targetLearningOpportunity | AVC, CCSF | 1–4 | plain text: **all regex matches** of a course code in the prerequisite text |
| estimatedDuration | UARK | 2 (contact hours, access period) | two separate labelled rows |
| subject | CCSF, Marshall | 1 | the page heading, outside the record |
| creditValue (list, not range) | WVU | `1,2 Hour.` | one text split by "," (rare) |

So all three split styles occur: one match per element, one text split on a separator (",", ";", line break), and
every match of a regex in one text. Element splitting alone can't do CCSF requisite lines, Marshall attributes, or
codes in AVC / CCSF / UALR text. *Inferred:* the WVU and UALR course links need a regex over the prerequisite text,
not "all links", to avoid catching corequisites.

---

## Nested children: are the parts obvious?

| Parent | Obvious parts | Stays in the parent |
|---|---|---|
| creditValue | AVC: min and max are labelled fields. CCSF / Marshall / WVU: `N-M` ranges (min, max) and the unit word (except CCSF, which has none). | UALR number words (`One, two, three, or four`), WVU `1,2`, AVC's second "profile" card |
| prerequisite | `targetLearningOpportunity`: course codes (links in Marshall / WVU / UALR, text in AVC / CCSF). `description` is the same text as the parent in every catalog. | `alternativeCondition`: "or" is in 2–7 of 22. Simple splits exist (`PHTC 101 or PHTC 125`, `Delta Divorce Clinic - LAWW 60254 or … LAWW 60166`), but most mix and / or / brackets / non-course text (`ECON 202 and (ECON 225 or STAT 211 or STAT 215) with a minimum grade of C- in all`; `Intermediate Algebra or higher or placement by multiple measures`) |
| recommends | course codes (AVC `CA 182`, CCSF `HIT 50A`) | the same "or" problem (CCSF `Readiness for college-level English or ESL 188`: 7 of 11) |
| estimatedDuration | UARK: `Access to Course: 6 Months` (exact? see note 14), `Contact Hours: 120` | UARK prose ("Approximately 16 hours … 4 weeks"), UALR "per week" sentences. No catalog prints a min–max time range |

*Inferred:* `prerequisite>description` and `recommends>description` would hold the same text as their parents on
every catalog sampled. Nothing on these pages separates a "description" part from the rest.

---

## D7: what pages print for a learning opportunity type

- No catalog has a field labelled as a type.
- The type words are in the **course title**: `Special Topics`, `Independent Study`, `Seminar`, `Internship`,
  `Laboratory`, `Practicum`, `Capstone`, `Work Experience`, `Externship`, `Dissertation`. Titles with one: AVC 3,
  CCSF 5, Marshall 7, UALR 8, WVU 11 of 22.
- Other places:
  - CCSF's hour kinds (`Activity`, `Work Experience`).
  - Marshall's Attributes (`Capstone Course`, `Thesis`, `Dissertation`, `PE Activity`).
  - UARK's prose (`course`, `online program`, `certificate`).
- *Inferred:* a `learningOpportunityType` rule would be a regex over the name (or the description), so it overlaps
  `ceterms:name`. CCSF's `.course-Type` (`Credit (Degree Applicable)` / `Noncredit`) is a credit status, not a type.

## Labels that don't exist on these pages

- **`hasPart`:** absent in all six. UARK prints series membership, which points the other way.
- **`inCatalog`:** never printed as a URL in a record. It's implied by the crawl (the catalog home). UALR prints the
  catalog's **name** in the record. AVC's URL holds the year (`/catalog/2026-27/`).
- **`isNonCredit`:** printed only by CCSF (`Noncredit`, about 10% of courses) and UARK (prose). Implied by AVC's
  `0.0 Units`. Absent at Marshall, UALR and WVU.
- **`recommends`:** printed by AVC (`Advisory:`, 5 of 22, 16 of 100 pages), CCSF (`Recommended Prep:`, 11 of 22, 133 of
  265) and UALR (1). UARK's "Prior Learning" reads like it. Absent at Marshall and WVU.
- **`deliveryTypeDescription`, `minimumDuration`, `maximumDuration`:** absent everywhere.
- **`keyword`:** no catalog prints keywords. Marshall's Attributes and UALR law's Practice Area are the nearest.

---

## Limits of today's rule types

Today's types are `css`, `css+regex`, `regex`, `constant` and `source_url`. `engine.run_field`
(`src/golden_datasets/engine.py:227`) takes one element with `select_one`, then applies one `re.search`
(`extract_from_text`, `engine.py:174`).

1. **Lists.** One `select_one` plus one `re.search` gives one value. Lists need one of three splits (see D5 above).
2. **Only inside the record.** `select_one(el, selector)` searches from the occurrence element down. The page heading
   that names the subject (CCSF `MGT - Management`, Marshall `Statistics (STA)`) is outside, so `subject` can't be
   read there today.
3. **Text only, no attributes.** Values come from `text_of`. Nothing can read an `href` or `data-*` attribute. So
   `inCatalog` (a URL) can't come from a link on the page, and UARK's modality popovers can't be read.
   `source_url` gives the whole page URL, with no regex.
4. **Bare text nodes** (UALR) can't be selected by css. Only a `regex` over the whole record reaches them. The record's
   text also joins the title to the next text with no space or newline.
5. **Script and style text** is part of `text_of` (UARK). A whole-record `regex` has to avoid it.
6. **Values in words** (UALR `Three`, `One to nine`) can be extracted as words. Turning them into numbers is
   transformation.
7. **Implied values with no words on the page** need a rule that outputs a value the page doesn't print. Examples: AVC
   `isNonCredit` from `0.0 Units`, AVC `learningMethodType` from hours > 0, `creditUnitType` at CCSF, `inCatalog`
   everywhere. Only `constant` does that today, and A3.12 says no per-catalog constants for implied values. *Inferred:*
   under A3.12 these stay empty, or the rule takes the nearest printed words (`0.0 Units`, `Lecture Hours 54.0`).
8. **Identifier for UARK.** UARK prints no code. The only key is the URL's `course=` slug, which `source_url` can't cut
   out (no regex).

---

## What this changes in Part D

- **D5.** All three split styles are needed (elements, separator, every regex match). Element splitting alone isn't
  enough. The assumption "a rule can do either kind of split" should add the third: every match of a regex.
- **D6.** `prerequisite` and `recommends` had one block per course in every sample. "Multiple" applies to their
  `targetLearningOpportunity` children (1–15 codes), not to the parent. *Inferred:* a parent can be Single per course
  on these catalogs.
- **D7.** Pages print a type only as a word in the title. `learningOpportunityType` is a regex over the name on five
  catalogs, and prose at UARK.
- **A3.12 / implied values.** `inCatalog` is never printed as a URL, so under "no constants for implied values" it
  stays empty everywhere. The same goes for CCSF's `creditUnitType` and most `isNonCredit` values. That needs a
  decision.
- **`subject`** needs a rule that can read outside its record (the page heading), or it stays empty at CCSF and
  Marshall. No catalog prints a subject inside the record, except as the code prefix.
- **Parents vs `>description` children** hold the same text on every catalog. *Inferred:* one of them will always be a
  copy.

---

## Commands (to repeat)

From `golden-dataset-studio/`, with:

```
export AZURE_STORAGE_CONNECTION_STRING="$(az storage account show-connection-string -n ceteststorage --query connectionString -o tsv)"
export GOLDEN_DATASETS_ROOT=azure://https://ceteststorage.blob.core.windows.net/xtra-cli-output/zz-scratch-review-ui-v3
B1=/private/tmp/claude-501/-Users-salt--superset-worktrees-ctdl-xtra-find-branch-latest-golden-d5579781/d8da7483-671f-4022-add7-adcfabd4f4cb/scratchpad/b1
```

1. Current rules per catalog (selectors and locators):
   ```
   uv run golden-datasets sql -c <cat> --format json "select rule_id, version, kind, rule_type, definition from rules qualify version = max(version) over (partition by rule_id)"
   ```
2. The sample, one occurrence per page:
   ```
   uv run golden-datasets sql -c <cat> --format json "with o as (select * from occurrences where locator_rule_id='locator-course-page' and extraction=(select max(extraction) from occurrences)), p as (select *, row_number() over (partition by page_stem order by md5(occurrence_key)) rn from o) select occurrence_key, page_stem, css_path, course_key from p where rn=1 order by md5(page_stem) limit 22" > $B1/sample-<cat>.json
   jq -r .page_stem $B1/sample-<cat>.json | xargs uv run golden-datasets pages get -c <cat> > $B1/paths-<cat>.txt
   ```
3. Every course on those pages (CCSF, Marshall): the same query without `rn=1`, filtered by `page_stem in (…)` →
   `allocc-<cat>.json`.
4. Wider page sets: `select distinct page_stem … order by md5(page_stem||'x') limit N` → `wide-stems-<cat>.txt`, then
   `pages get` → `widepaths-<cat>.txt`.
5. Scripts (in `$B1/scripts/`, run as `uv run python -I <script>` so they use the Studio's own `engine.parse`,
   `select` and `text_of`):
   - `dump.py $B1 <cat>`: each sampled record's text and element outline → `out/<cat>.txt|json`.
   - `scan.py $B1 <cats…>`: cue regexes over the record text → `out/scan.txt`.
   - `proto.py $B1 <cat> sample-<cat>.json` (or `allocc-<cat>.json`, or `all-courseblocks "div.courseblock"` for
     WVU): one prototype extractor per label, written the way a rule would be. It prints courses with a value,
     values-per-course and examples → `out/proto-*.txt`, `out/protoall-*.txt`.
   - `wide.py $B1 <cat>`: distinct values (CCSF `.course-Type`, Marshall Attributes, UARK Modality and sections)
     over the wider page set → `out/wide.txt`.
   - `q.py <cat> <stem-part> <css> [html|text]` and `ctx.py <cat> <i>`: look at one page or record.
6. Existing rule fill on the sample:
   ```
   uv run golden-datasets sql -c <cat> --format csv "select rule_id, count(*) filter (where status='found'), count(*) from matches where extraction=(select max(extraction) from matches) and occurrence_key in (…) group by 1"
   ```

Nothing was run that writes to Azure. Downloads went only to the local page cache and `$B1`.
