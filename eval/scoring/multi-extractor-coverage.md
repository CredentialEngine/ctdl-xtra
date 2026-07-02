# Would running xTRA's other extractors close the gap?

xTRA classifies each page into one `CatalogueType` and runs only that extractor. Question: if we ran **all four extractors on the same WGU degree page**, how many of the 14 not-attempted CTDL fields would be covered?

Field inventory across all four extractors (union = 20 fields):

| Extractor | Fields |
|---|---|
| Credential | `credential_name`, `credential_description`, `credential_type`, `language` |
| LearningProgram | `learning_program_id`, `learning_program_name`, `learning_program_description` |
| Course | `course_id`, `course_name`, `course_description`, `course_prerequisites`, `course_credits_min`, `course_credits_max`, `course_credits_type`, `course_ceu_credits`, `course_non_credit` |
| Competency | `text`, `competency_framework`, `competency_category`, `language` |

Mapping the 14 not-attempted CTDL fields to any extractor field:

| CTDL field | Any extractor field maps? | Which | Fit |
|---|:---:|---|---|
| `subjectWebpage` | ✗ | — | none |
| `credentialStatusType` | ✗ | — | none |
| `learningDeliveryType` | ✗ | — | none |
| `audienceLevelType` | ✗ | — | none |
| `estimatedDuration` | ✗ | — | none |
| `estimatedCost` | ✗ | — | none |
| `creditValue` | ~ | Course `credits_min/max/type` | poor — course-level credits, not program totals |
| `requires` (admission) | ~ | Course `course_prerequisites` | poor — prompt is course-prereq specific ("corequisites leave blank") |
| `teaches` (competencies) | ✓ | Competency `text` | **good** — Competency extractor already has `exploreDuringExtraction` and would find WGU's outcome bullets |
| `occupationType` | ✗ | — | none |
| `industryType` | ✗ | — | none |
| `hasPart` (courses) | ~ | Course `course_id`/`name` | partial — Course extractor expects one page per course; WGU lists 37 course names on one program page with no IDs |
| `accreditedBy` | ✗ | — | none |
| `industryCertifications` | ✗ | — | none |

**Result: 1 clean win, 3 poor-fit partials, 10 with no home in any extractor.**

## Takeaway

Running the Competency extractor alongside Credential on the same page **would** recover `teaches` — that's a real, cheap improvement (`exploreDuringExtraction` is already built for it). But **10 of 14 gap fields have no field in any of the four schemas**: cost, duration, delivery, audience level, occupations, industries, accreditation, status, subject webpage, and industry certifications simply don't exist in `common/catalogueTypes.ts`.

So "expand which extractors run" and "widen the schema" are **complementary, not alternatives**:

- **Multi-extractor pass** (run Competency + Credential together on program pages) → recovers `teaches`, ~1 field · **effort XS** (config change: enable `exploreDuringExtraction` on Credential type or add a "companion extractors" list)
- **Schema expansion** (P1) → recovers the other 10–13 · **effort S**

The strongest version does both: widen the Credential schema *and* run the Competency extractor as a companion, because competencies benefit from the dedicated presence-check + phrase-verification logic that Competency already has.
