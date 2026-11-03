# Research: the sheet and CTDL (B2, B9, D7, D10)

- Researched: 2026-11-02
- Nothing was written anywhere except this file and the session scratchpad.
- *Inferred* marks things concluded rather than checked.

## 1. Reading the sheet without signing in (B9)

**The sheet is shared by link, so anyone with the URL can read it.** No Google credentials are needed:

```sh
ID=1zFG1Qzn4NTrvb5KTxucKnz-gPd8H_W0oYYRdh7jT8ro
curl -sL "https://docs.google.com/spreadsheets/d/$ID/export?format=xlsx" -o bu.xlsx          # every tab
curl -sL "https://docs.google.com/spreadsheets/d/$ID/export?format=csv&gid=1596676506" -o p1.csv  # Phase 1 tab only
```

| Way | Result |
|---|---|
| `export?format=xlsx` | 307 redirect to `googleusercontent.com`, then the full workbook. All four tabs: Course, Phase 1 Extraction, Condition Profiles, Learning Program |
| `export?format=csv&gid=1596676506` | the Phase 1 tab only. Its column F is identical to `phase1-extraction.csv`, which was read through the Drive connector |
| `gviz/tq?tqx=out:csv&sheet=…` | **don't use it.** It runs the header rows together into one cell (`"xTRA Status Include Include …"`) |
| `export?format=csv&gid=0` | an HTML page: the Course tab isn't gid 0. Its gid isn't known without signing in |

- **One download gives both tabs.** `properties sync` needs the Phase 1 tab (the labels) and the Course tab (the
  Required block). The xlsx export is the only anonymous way to get the Course tab, so it's the one download to use.
- **The Required block parses cleanly** with `openpyxl`:
  - Rows 3–9 sit under the merged section row "Required Properties" (`A2:G2`). The next section row is
    "Availability and Offering" (`A10:H10`).
  - It holds External Identifier (`ceterms:identifier`), Learning Type (no term), Learning Opportunity Name,
    Description, Subject Webpage, Life Cycle Status Type and Language.
  - That is exactly A2.5's list.
- **Responses aren't cached** (`cache-control: no-cache, no-store`). A sync always sees the sheet as it is now.
- *Inferred:*
  - If the sheet's sharing is ever narrowed, the anonymous export stops working.
  - `properties sync` should then accept a downloaded `.xlsx` (`--from bu.xlsx`) as well as the URL.
  - The checked-in file means the app never depends on the sheet being reachable.

## 2. Each column F term against CTDL (B2)

**Source:** the published CTDL schema could not be reached. `credreg.net` and `purl.org/ctdl/terms` answer 403
behind a Cloudflare check, for both curl and WebFetch. Instead, the terms were read from Credential Engine's own
schema repository, which stores one JSON-LD file per property. It was last changed 2026-07-21, and the repository
2026-10-05:

```sh
gh api "repos/CredentialEngine/Schema-Development/contents/src/Schema/ctdl/Split/properties/ceterms_<term>.jsonld" \
  -H "Accept: application/vnd.github.raw"
```

That folder has 396 properties.

| Column F label | In the schema? | On `ceterms:Course`? | Range | Notes |
|---|---|---|---|---|
| identifier | yes | yes | `IdentifierValue` | |
| name, description | yes | yes | `langString` | |
| subjectWebpage | yes | yes | `anyURI` | |
| codedNotation | yes | yes | `string` | |
| isNonCredit | yes | yes | `boolean` | term status *unstable* |
| deliveryType | yes | yes | `CredentialAlignmentObject` | vocabulary |
| deliveryTypeDescription | yes | yes | `langString` | |
| inCatalog | yes | yes | `anyURI` | *unstable* |
| **contentDescription** | **no** | — | — | not in the schema repo. The Registry Assistant publishes it as `ceterms:contentDescription` ("Description of the topics, concepts, theories, and practices addressed by this resource"; `RA.Models/Input/LearningOpportunityRequest.cs:378-386`). *Inferred:* a newer term, not yet in the repo |
| learningMethodType | yes | yes | `CredentialAlignmentObject` | vocabulary |
| learningMethodDescription | yes | yes | `langString` | |
| keyword | yes | yes | `langString` | |
| subject | yes | yes | `CredentialAlignmentObject` | |
| creditValue | yes | yes | `ValueProfile` | |
| ›`schema:minValue` / `schema:maxValue` / `schema:value` | yes | on ValueProfile | `float` | the `schema:` prefix in column F is right |
| ›`ceterms:creditUnitType` | yes | on ValueProfile | `skos:Concept` | |
| **prerequisite** | yes | yes | **`ceterms:Course` only** | "Course that is required as a prior condition to this course." **Not a ConditionProfile** (see §3) |
| ›description / targetLearningOpportunity / alternativeCondition | yes | on ConditionProfile | | all three are ConditionProfile properties |
| recommends | yes | yes | includes `ConditionProfile` | the column F children fit |
| hasPart | yes | yes | many classes, including `Course` | |
| **learningOpportunityType** | **no** | — | — | see §4 |
| estimatedDuration | yes | yes | `DurationProfile` | |
| ›exactDuration / minimumDuration / maximumDuration | yes | on DurationProfile | `schema:Duration` | |
| ›description | yes | on DurationProfile | | |
| lifeCycleStatusType *(column E)* | yes | yes | `CredentialAlignmentObject` | *unstable* |
| inLanguage *(column E)* | yes | yes | `language` | |

## 3. `prerequisite` isn't a ConditionProfile (D10)

- In CTDL, **`ceterms:prerequisite` points straight at another Course**. It has domain Course and range Course.
- The property whose range is a ConditionProfile is **`ceterms:requires`** ("Requirement or set of requirements
  for this resource"). `recommends` has ConditionProfile in its range too.
- So the sheet's `ceterms:prerequisite>ceterms:description`, `>targetLearningOpportunity` and
  `>alternativeCondition` describe a profile that CTDL hangs off `requires`, not `prerequisite`.
- Row 24 now reads just `ceterms:targetLearningOpportunity` (D10).
- For extraction this matters little. A3.11–A3.13 put the mapping to CTDL in the transformation step, and the
  Studio only stores the page's words under the sheet's label.
- *Inferred:* keep the sheet's labels as they are. The spec should note that the transformation step will need
  `requires` (or `prerequisite` → Course), and the sheet's owner should hear about it.

## 4. `learningOpportunityType` vs Learning Type (D7)

- **`ceterms:learningOpportunityType` is not a CTDL property.** It isn't in the schema repo's 396 properties.
  In Credential Engine's repositories it appears only in the Registry Assistant (the publishing API). There it
  means **which of the three classes** a record is: `IsLearningOpportunityType` in `EntityReference.cs:115`, and
  the sample `PublishLearningOpportunityTypes.cs:12-15`: "The Learning Opportunity, Course and Learning Program
  all use the same input request class".
- That is exactly what the Studio's **Learning Type** does: Learning Program, Course or Learning Opportunity (the
  Course tab's specification).
- So D7's assumption ("they're different things") is probably wrong. *Inferred:* `learningOpportunityType` in
  column F is the sheet's name for Learning Type.
- The sheet also lists `learningOpportunityType` under `LearningOpportunityProfile` (row 32, no label), which fits
  the same reading.
- What pages actually print for it is in [`pages.md`](pages.md).
