# CTDL Field Specification — Reference for xTRA Evaluation

Distilled from the [CTDL term list](https://credreg.net/ctdl/terms), the [Registry Minimum Data Policy](https://credreg.net/registry/policy), the [Registry Assistant / bulk-upload docs](https://credreg.net/registry/assistant), the CTDL JSON-LD schema (`https://credreg.net/ctdl/schema/encoding/json`), and the [xTRA product page](https://credentialengine.org/toolkit/credential-engine-ctdl-xtra-tool/) + [xTRA course-review guidance](https://guidance.credentialengine.org/xtra-tool-review-and-publish-course-data/). Compiled July 2026.

---

## 1. Entity types xTRA cares about

| CTDL class | One-line definition | xTRA status |
|---|---|---|
| **`ceterms:Credential`** (and ~30 subclasses — `BachelorDegree`, `Certificate`, `License`, `MicroCredential`, …) | A qualification, achievement, or authority issued to a person on successful completion of requirements. | In development |
| **`ceterms:LearningOpportunityProfile`** ("Learning Program") | A structured set of learning activities (a program) that leads to an outcome, usually a credential. | Ready for pilot |
| **`ceterms:Course`** | A single structured sequence of educational activities — the unit inside a program/catalog. | **In pilot** (most mature) |
| **`ceasn:Competency`** / **`ceasn:CompetencyFramework`** | A statement of measurable skill/knowledge/ability, and the container that groups related competencies. | Ready for pilot |
| **`ceterms:CredentialOrganization`** | The org that owns, offers, or QA's credentials — the publisher record every other entity hangs off. | Not extracted by xTRA (user supplies) |

---

## 2. Field table — Credential & Learning Opportunity / Course

Requirement levels are from the Registry Minimum Data Policy: **Req** = must be present to publish, **Rec** = Recommended-Benchmark tier, **Opt** = optional. Where Credential and LearningOpp differ, both are shown as `Cred / LOpp`.

| CTDL property | Plain-English meaning | Req level (Cred / LOpp) | Typical source on a program webpage | Example value |
|---|---|---|---|---|
| `ceterms:ctid` | Registry-assigned globally unique ID | **Req / Req** | *Not on page* — generated at publish time | `ce-4f36b9b1-…` |
| `ceterms:name` | Official title of the credential or program | **Req / Req** | Page `<h1>` / catalog title | "Bachelor of Science in Data Analytics" |
| `ceterms:description` | Narrative overview of purpose, content, outcomes | **Req / Req** | "About this program" / lead paragraph | "Prepares students to collect, model and interpret data …" |
| `ceterms:subjectWebpage` | Canonical public URL for this credential | **Req / Req** | The page URL itself | `https://catalog.example.edu/bs-data-analytics` |
| `ceterms:ownedBy` \| `offeredBy` | Org that owns / delivers it (at least one) | **Req / Req** | Header/footer institution name; "Offered by the College of Engineering" | ref → CredentialOrganization |
| *Credential subclass* (`@type`) | Which of the ~30 credential types this is | **Req / —** | Degree-type label on page ("Bachelor's", "Graduate Certificate") | `ceterms:BachelorDegree` |
| `ceterms:credentialStatusType` | Lifecycle state of the credential | **Req / —** *(LOpp uses `lifeCycleStatusType`, Opt)* | Rarely stated; assume Active unless "no longer offered" | `credentialStat:Active` |
| `ceterms:inLanguage` | Language of instruction | **Req / Opt** | "Taught in English"; often implicit | `en-US` |
| `ceterms:learningDeliveryType` / `deliveryType` | Modality: online / in-person / blended | Rec / Rec | "100% online", "On-campus", "Hybrid" badges | `deliveryType:OnlineOnly` |
| `ceterms:audienceLevelType` | Educational level targeted | Rec / Rec | "Undergraduate", "Graduate program" | `audLevel:BachelorsDegreeLevel` |
| `ceterms:audienceType` | Who it's for (population) | Opt / Opt | "For working professionals", "veterans welcome" | `audience:PartTime` |
| `ceterms:estimatedDuration` | Typical time to complete → `DurationProfile` | Rec / Rec | "4-year program", "18 months", "120 contact hours" | `{ exactDuration: "P4Y" }` |
| `ceterms:estimatedCost` | Tuition / fees → `CostProfile` | Rec / Rec | Tuition & fees table; "Cost per credit" | `{ price: 24800, currency: "USD", costType: costType:Tuition }` |
| `ceterms:creditValue` | Credits awarded → `ValueProfile` | — / Rec | "120 credit hours", "3 credits" | `{ value: 120, creditUnitType: creditUnit:DegreeCredit }` |
| `ceterms:creditUnitTypeDescription` | Free-text credit-system note | Opt / Opt | Footnote on credit table | "Semester credit hours" |
| `ceterms:requires` | Entry / completion requirements → `ConditionProfile` | Rec / Rec | "Admission Requirements", "Prerequisites" section | `{ description: "High-school diploma; GPA ≥ 2.5" }` |
| `ceterms:recommends` | Suggested (not mandatory) preparation | Rec / Rec | "Recommended background" | `{ description: "Prior stats coursework recommended" }` |
| `ceterms:corequisite` | Must be taken concurrently | Rec / Opt | "Co-requisites" line in catalog | ref → Course |
| `ceterms:entryCondition` | Admission-specific gate (LOpp) | — / Opt | "Admissions" tab | `{ description: "TOEFL ≥ 80 for intl. applicants" }` |
| `ceterms:teaches` | Competencies / learning outcomes delivered | Opt / Opt | "Learning outcomes", "You will learn to…" bullets | list of Competency refs or free-text outcomes |
| `ceterms:isPreparationFor` | What this leads to (next credential, exam, job) | Rec / Rec | "Prepares you for the PMP exam", "Pathway to MS" | ref → Credential / Occupation |
| `ceterms:occupationType` | Related occupations (O*NET / SOC coded) | Rec / Rec | "Careers" / "Job outcomes" section | `15-2051` (Data Scientists) |
| `ceterms:industryType` | Related industries (NAICS coded) | Rec / Rec | "Industries hiring our grads" | `5415` (Computer Systems Design) |
| `ceterms:keyword` | Free-text search tags | Rec / Rec | Meta keywords; repeated topical phrases | `["data analytics","SQL","visualization"]` |
| `ceterms:subject` | Subject-area classification (CIP or free text) | Rec / Opt | Department / discipline label | "Computer and Information Sciences" |
| `ceterms:degreeMajor` | Primary field of study (Degree only) | Opt / — | "Major: Data Analytics" | "Data Analytics" |
| `ceterms:degreeConcentration` | Track / specialization inside a degree | Opt / — | "Concentrations: Business Analytics, Health Informatics" | "Health Informatics" |
| `ceterms:availableAt` | Physical delivery location → `Place` | Rec / Rec | Campus address block | `{ addressLocality: "Tempe", addressRegion: "AZ" }` |
| `ceterms:availableOnlineAt` | URL where it's delivered online | Rec / Rec | "Apply / enroll online" link | `https://online.example.edu/…` |
| `ceterms:dateEffective` | Date this version became active | Rec / Rec | "Effective Fall 2025" catalog note | `2025-08-15` |
| `ceterms:codedNotation` / `identifier` | Institution's own code (course no., program code) | Opt / Opt | "CS 350", "Program code: BSDA" | `"CS 350"` |
| `ceterms:accreditedBy` / `approvedBy` | External QA body | Rec / Rec | Accreditation-logo footer | ref → QACredentialOrganization (e.g. ABET) |
| `ceterms:financialAssistance` | Aid available → `FinancialAssistanceProfile` | Rec* / Rec | "Financial aid available", "GI Bill approved" | `{ name: "Federal Pell Grant" }` |

\* Conditionally required for Certification, License, Degree, Apprenticeship subclasses.

---

## 3. Value-format notes

### Controlled vocabularies (must map to a concept URI, not free text)

| Property | Concept scheme | Allowed values (from CTDL JSON schema) |
|---|---|---|
| `credentialStatusType` | `ceterms:CredentialStatus` | `credentialStat:` **Active**, Ceasing, Deprecated, Probationary, Suspended, TeachOut |
| `lifeCycleStatusType` (LOpp/Course) | `ceterms:LifeCycleStatus` | `lifeCycle:` Active, Ceasing, Developing, Suspended, TeachOut |
| `audienceLevelType` | `ceterms:AudienceLevel` | `audLevel:` BeginnerLevel, IntermediateLevel, AdvancedLevel, SecondaryLevel, PostSecondaryLevel, LowerDivisionLevel, UpperDivisionLevel, UndergraduateLevel, AssociatesDegreeLevel, BachelorsDegreeLevel, GraduateLevel, MastersDegreeLevel, DoctoralDegreeLevel, ProfessionalLevel, … (19 total) |
| `audienceType` | `ceterms:Audience` | `audience:` Citizen, Resident/NonResident, FullTime/PartTime, CurrentMilitary/FormerMilitary, CurrentStudent, PublicEmployee, … (29 total) |
| `learningDeliveryType` / `deliveryType` / `assessmentDeliveryType` | `ceterms:Delivery` | `deliveryType:` **InPerson**, **OnlineOnly**, **BlendedDelivery**, VariableSite (only 4) |
| `creditUnitType` (inside `creditValue`) | `ceterms:CreditUnit` | `creditUnit:` DegreeCredit, ContactHour, ContinuingEducationUnit, CertificateCredit, … |
| `costType` (inside `estimatedCost`) | `ceterms:CostType` | `costType:` Tuition, ApplicationFee, RoomBoardArrangement, TechnologyFee, … |
| *Credential* `@type` | subclass list | ~30 subclasses — `Certificate`, `Certification`, `License`, `Badge`/`DigitalBadge`/`OpenBadge`, `MicroCredential`, `Diploma`, `SecondarySchoolDiploma`, `GeneralEducationDevelopment`, `AssociateDegree`, `BachelorDegree`, `MasterDegree`, `DoctoralDegree`, `ProfessionalDoctorate`, `SpecialistDegree`, `ApprenticeshipCertificate`, `JourneymanCertificate`, `QualityAssuranceCredential`, … |

### External code lists (`CredentialAlignmentObject` with a framework URL)

- `occupationType` → O*NET-SOC or ISCO codes
- `industryType` → NAICS or ISIC codes
- `instructionalProgramType` / `subject` → CIP codes (US) or free text

### ISO-typed scalars

- **Durations** — `estimatedDuration` → `ceterms:DurationProfile` whose `exactDuration` / `minimumDuration` / `maximumDuration` are `schema:Duration` = **ISO 8601 duration** strings (`P4Y`, `P18M`, `PT120H`).
- **Dates** — `dateEffective`, `expirationDate`, `renewalFrequency` → ISO 8601 date (`YYYY-MM-DD`) or duration.
- **Language** — `inLanguage` → BCP-47 tag (`en`, `en-US`, `es-MX`).

### Language-map strings (`rdf:langString`)

All human-readable text is serialized as a language map, not a bare string:

```json
"ceterms:name": { "en-US": "Bachelor of Science in Data Analytics" }
```

Applies to `name`, `description`, `keyword` (langString array), `subject`, `degreeMajor`, `degreeConcentration`, `creditUnitTypeDescription`, and every `description` inside a sub-profile (`ConditionProfile`, `CostProfile`, `DurationProfile`).

### Structured sub-objects (not flat scalars)

| Property | Range class | Min viable payload |
|---|---|---|
| `estimatedDuration` | `DurationProfile` | `{ exactDuration }` or `{ minimumDuration, maximumDuration }` |
| `estimatedCost` | `CostProfile` | `{ costType, price, currency }` |
| `creditValue` | `ValueProfile` | `{ value, creditUnitType }` |
| `requires` / `recommends` / `corequisite` / `entryCondition` | `ConditionProfile` | `{ description }` (≥ 15 chars) or `{ targetCredential / targetLearningOpportunity }` |
| `availableAt` | `Place` | `{ streetAddress, addressLocality, addressRegion, postalCode, addressCountry }` |
| `occupationType` / `industryType` / `subject` | `CredentialAlignmentObject` | `{ targetNodeName, codedNotation, framework }` |
| `financialAssistance` | `FinancialAssistanceProfile` | `{ name, financialAssistanceType }` |

---

## 4. What xTRA claims to extract

**Input** → a public URL (course catalog page, program page, competency list). No auth'd pages, no PDFs mentioned.
**Output** → a CSV pre-shaped for the Registry bulk-upload template.
**Process** → extract → transform to CTDL columns → "validate against original content" → CSV.

### Entity coverage claimed on the product page

| Entity | Claimed status |
|---|---|
| Course | **In pilot** |
| Learning Program (LearningOpportunityProfile) | Ready for pilot |
| Competency Framework | Ready for pilot |
| Credential | In development |

### Fields the Course pipeline actually populates (per CE's own review-guidance doc)

| Bulk-upload column | How xTRA fills it |
|---|---|
| Course number / `codedNotation` | Extracted |
| `name` | Extracted |
| `description` | Extracted |
| `subjectWebpage` (catalog URL) | Extracted |
| `creditValue` — value | Extracted |
| `creditValue` — `creditUnitType` | Extracted **when determinable**; flagged for user when not |
| `requires` (`ConditionProfile.description`) — prerequisites | Extracted when present |
| `identifier` (External Identifier) | Auto-set = course number |
| `inLanguage` | Auto-set = `en` |
| `lifeCycleStatusType` | Auto-set = `Active` |

### Not claimed / user must supply or verify

- Anything vocabulary-mapped beyond the three auto-sets: `deliveryType`, `audienceLevelType`, `audienceType`, credential `@type`.
- `estimatedDuration`, `estimatedCost`, `occupationType`, `industryType`, `teaches` (learning outcomes).
- De-duplication ("check for duplicate course numbers"), min-length on `ConditionProfile.description` (≥ 15 chars), and general accuracy — CE recommends spot-checking 10–15 random rows against the source catalog.

**No accuracy metric is published.** The product page positions xTRA as a bootstrap for the bulk-upload CSV, explicitly *not* a replacement for API/native-CTDL publishing.

---

## Bulk-upload template note

The Registry bulk-upload template is **generated per-publisher** in the [Publisher tool](https://apps.credentialengine.org/publisher/): the user picks properties in "Step 2 — Select Your Properties" and the tool emits a CSV whose column headers = the chosen CTDL property names (Row 1), with optional sample-data + instruction rows. There is no single canonical column list — the Required set above is the floor; xTRA targets the Course template's default column set.
