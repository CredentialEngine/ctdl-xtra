# WGU Test Pages — Index

Captured 2026-07-01 for reproducible CTDL-extraction eval runs.

Each program has two files: `<slug>.html` (raw source, `curl -sL`) and `<slug>.md` (readable markdown + CTDL field annotations at top).

| Slug | Resolved URL | HTML bytes | Credential type |
|---|---|---:|---|
| `bs-computer-science` | https://www.wgu.edu/online-it-degrees/computer-science.html | 470,464 | Bachelor's |
| `mba` | https://www.wgu.edu/online-business-degrees/mba-masters-business-administration-program.html | 405,510 | Master's |
| `ms-nursing-education` | https://www.wgu.edu/online-nursing-health-degrees/bsn-to-msn-nursing-education-masters-program.html | 421,483 | Master's |
| `bs-accounting` | https://www.wgu.edu/online-business-degrees/accounting-bachelors-program.html | 447,914 | Bachelor's |
| `cert-leadership` | https://www.wgu.edu/online-business-degrees/certificates/leadership.html | 230,578 | Certificate |

## Page-structure notes

**Platform:** All five pages are Adobe Experience Manager (AEM) — server-side rendered, NOT a JS SPA. Full body text is present in the raw HTML (verifiable by `<p>` count: 54–189 per page). No client-side hydration needed to read content; `curl` alone is sufficient for reproducible extraction.

**Tabs & accordions:** Heavy use everywhere. All degree pages use `role="tab"` (47–49 per page) for the top nav (Overview / Courses / Cost & Time / Career Outlook / Admissions). Course lists and FAQs live inside `.accordion` / `.cmp-accordion` blocks (54–252 accordion markers per page). All tab/accordion panel content IS in the initial HTML — collapsed via CSS/ARIA, not lazy-loaded — so a headless browser is not required, but naive text-extraction that respects `aria-hidden` may miss it.

**JSON-LD structured data:** Present on every page (`application/ld+json`): 1 block on CS, 2 on MBA/MSN/Accounting, 3 on the certificate. Likely `schema.org/Course` or `EducationalOccupationalProgram` — a high-signal shortcut for CTDL mapping. Worth extracting separately.

**PDF program guides:** Each degree page links to exactly 1 PDF (the official Program Guidebook, e.g. `.../program-guides/information-technology/BSCS.pdf`). The certificate page links 4 PDFs. These PDFs contain the authoritative competency-unit counts and course codes that the marketing HTML omits.

**Per-page quirks:**
- `bs-computer-science` — richest CTDL surface: ABET accreditation, 5 embedded certifications (mix of industry + WGU-issued), 37 named courses with descriptions, explicit CU-per-term figure, precalculus prerequisite. Also references a distinct accelerated BS+MS pathway (separate credential).
- `mba` — cleanest/shortest degree page. 11 courses fully listed. No embedded certs. No credit-hour figure. Large FAQ accordion (~15 Q&A).
- `ms-nursing-education` — only page with a **blended** delivery mode (online + required in-person field experience) and licensure prereq (active RN license). Transfer-credit cap explicitly quantified (17 credits / 47%). CCNE accreditation.
- `bs-accounting` — largest course list (40). Includes an interactive tuition-calculator widget (values are static in HTML). `isPreparationFor` → CPA exam is explicit. 3 embedded WGU certificates. Heaviest accordion use (172).
- `cert-leadership` — half the byte size of the degree pages; simpler layout. Only page with an explicit **credit-hour** figure ("9 total credits"), fixed total price, monthly-subscription overrun pricing, and hardware/OS entry requirements. No accreditation body named. Stackability into WGU bachelor's is stated.

## Common CTDL-field coverage across all 5

| CTDL concept | CS | MBA | MSN-Ed | Acct | Cert |
|---|:-:|:-:|:-:|:-:|:-:|
| name / description | ✓ | ✓ | ✓ | ✓ | ✓ |
| credentialType | ✓ | ✓ | ✓ | ✓ | ✓ |
| estimatedDuration | ✓ | ✓ | ✓ | ✓ | ✓ |
| estimatedCost | ✓ | ✓ | ✓ | ✓ | ✓ |
| creditValue (numeric) | ~ (CU/term) | ✗ | ~ (implied) | ~ (FAQ) | ✓ |
| entryCondition | ✓ | ✓ | ✓ | ✓ | ✓ |
| deliveryType | ✓ | ✓ | ✓ (blended) | ✓ | ✓ |
| teaches (competencies) | ✓ | ✓ | ✓ | ✓ | ✓ |
| hasPart (courses) | ✓ (37) | ✓ (11) | ✓ (15) | ✓ (40) | ✓ (3) |
| occupationType | ✓ | ✓ | ✓ | ✓ | ~ (industries only) |
| accreditedBy | ABET | ACBSP | CCNE | ACBSP | ✗ |
| embedded credentials | ✓ (5) | ✗ | ✓ (1) | ✓ (3) | n/a |
# WGU Ground-Truth CTDL Records

Canonical CTDL JSON-LD records published by Western Governors University to the Credential Registry.

**WGU Organization:** [Credential Finder Org #34](https://credentialfinder.org/Organization/34/) · CTID `ce-036d082d-d80e-41a7-99a0-2d63a4ad3a4a` · [Registry](https://credentialengineregistry.org/resources/ce-036d082d-d80e-41a7-99a0-2d63a4ad3a4a)

---

| # | Target | Actual credential name | CTDL type | CTID | Credential Finder | Registry JSON-LD | wgu.edu page (subjectWebpage) | Local file |
|---|---|---|---|---|---|---|---|---|
| 1 | Bachelor of Science, Computer Science | Bachelor of Science, Computer Science (BSCS_202412) | `ceterms:BachelorOfScienceDegree` | `ce-8f5a2e25-7a30-4eb0-ab9e-ab441ac928c6` | [link](https://credentialfinder.org/resources/ce-8f5a2e25-7a30-4eb0-ab9e-ab441ac928c6) | [link](https://credentialengineregistry.org/resources/ce-8f5a2e25-7a30-4eb0-ab9e-ab441ac928c6) | [https://www.wgu.edu/online-it-degrees/bachelors-programs.html#_](https://www.wgu.edu/online-it-degrees/bachelors-programs.html#_) | `bs-computer-science.json` |
| 2 | Master of Business Administration | Master of Business Administration (MBA_201404) | `ceterms:MasterDegree` | `ce-6977cef9-298a-4f1e-bdac-d66509887ebf` | [link](https://credentialfinder.org/resources/ce-6977cef9-298a-4f1e-bdac-d66509887ebf) | [link](https://credentialengineregistry.org/resources/ce-6977cef9-298a-4f1e-bdac-d66509887ebf) | [https://www.wgu.edu/online-business-degrees/masters-programs.html](https://www.wgu.edu/online-business-degrees/masters-programs.html) | `mba.json` |
| 3 | Master of Science, Nursing – Education | Master of Science, Nursing - Education (BSN to MSN) (MSNUED_202003) | `ceterms:MasterOfScienceDegree` | `ce-6f236de1-9651-471a-9773-d9c7087b92c3` | [link](https://credentialfinder.org/resources/ce-6f236de1-9651-471a-9773-d9c7087b92c3) | [link](https://credentialengineregistry.org/resources/ce-6f236de1-9651-471a-9773-d9c7087b92c3) | [https://www.wgu.edu/online-nursing-health-degrees/masters-programs.html](https://www.wgu.edu/online-nursing-health-degrees/masters-programs.html) | `msn-education.json` |
| 4 | Bachelor of Science, Accounting | Bachelor of Science, Accounting (BSACC_202503) | `ceterms:BachelorOfScienceDegree` | `ce-b75970c9-d352-46a0-b67d-3256c9cdbb31` | [link](https://credentialfinder.org/resources/ce-b75970c9-d352-46a0-b67d-3256c9cdbb31) | [link](https://credentialengineregistry.org/resources/ce-b75970c9-d352-46a0-b67d-3256c9cdbb31) | [https://www.wgu.edu/online-business-degrees/bachelors-programs.html](https://www.wgu.edu/online-business-degrees/bachelors-programs.html) | `bs-accounting.json` |
| 5 | WGU Certificate: AWS Cloud DevOps (OpenBadge / micro-credential) | WGU Certificate: AWS Cloud DevOps v1.1 | `ceterms:OpenBadge` | `ce-727764d7-b909-4e5c-b26a-c4d0fced2159` | [link](https://credentialfinder.org/resources/ce-727764d7-b909-4e5c-b26a-c4d0fced2159) | [link](https://credentialengineregistry.org/resources/ce-727764d7-b909-4e5c-b26a-c4d0fced2159) | [https://api.badgr.io/public/badges/a9STuosRQuOqLKKKYhB9dQ](https://api.badgr.io/public/badges/a9STuosRQuOqLKKKYhB9dQ) | `cert-aws-cloud-devops.json` |

## Notes on selection

WGU publishes **many versions** of each program to the Registry (each catalog revision gets its own CTID, tagged with a `_YYYYMM` suffix). The versions selected here are the newest available as of retrieval:

1. **BS Computer Science** — `BSCS_202412` chosen (newest; older `BSCS_202011` = `ce-0df1babf-43fa-4d94-a7c3-84f6b8785c32` also exists).
2. **MBA** — `MBA_201404` is the only standalone/generic MBA in the Registry. Specialization variants exist (e.g., MBA Healthcare Administration `ce-edeac207-ee37-43b1-a925-dd0f83927989`).
3. **MSN – Education** — `MSNUED_202003` (BSN-to-MSN track) chosen as newest MSN-Education. RN-to-MSN Education variant `MSRNNUEDUG_202302` = `ce-8e533a1f-52bf-440e-937d-cb8f8d381c06` also available.
4. **BS Accounting** — `BSACC_202503` chosen (newest standalone; older `BSBAAC_*` variants under Business Administration umbrella also exist).
5. **Certificate / micro-credential** — `WGU Certificate: AWS Cloud DevOps v1.1` (type `ceterms:OpenBadge`) chosen as a representative non-degree credential. Siblings: AWS Cloud Security `ce-bf50297b-9eb1-4849-a8f6-f466dc3ea420`, Azure Cloud DevOps `ce-c0953e53-17bd-4261-ab2e-47cd9e902a53`.

## Field-population overview

| Property | bs-computer-science | mba | msn-education | bs-accounting | cert-aws-cloud-devops |
|---|:---:|:---:|:---:|:---:|:---:|
| `ceterms:accreditedBy` | ✓ |  |  | ✓ |  |
| `ceterms:alternateName` | ✓ | ✓ | ✓ | ✓ |  |
| `ceterms:assessmentDeliveryType` | ✓ | ✓ | ✓ | ✓ |  |
| `ceterms:audienceLevelType` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `ceterms:availableOnlineAt` | ✓ | ✓ | ✓ | ✓ |  |
| `ceterms:copyrightHolder` | ✓ | ✓ | ✓ | ✓ |  |
| `ceterms:credentialId` |  |  |  |  | ✓ |
| `ceterms:credentialStatusType` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `ceterms:ctid` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `ceterms:dateEffective` | ✓ | ✓ | ✓ | ✓ |  |
| `ceterms:degreeMajor` | ✓ | ✓ |  | ✓ |  |
| `ceterms:description` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `ceterms:estimatedCost` | ✓ | ✓ | ✓ | ✓ |  |
| `ceterms:estimatedDuration` | ✓ | ✓ | ✓ | ✓ |  |
| `ceterms:hasPart` | ✓ |  |  |  |  |
| `ceterms:image` |  | ✓ | ✓ |  | ✓ |
| `ceterms:inLanguage` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `ceterms:industryType` | ✓ | ✓ | ✓ | ✓ |  |
| `ceterms:instructionalProgramType` | ✓ | ✓ | ✓ | ✓ |  |
| `ceterms:isPreparationFor` |  |  |  |  | ✓ |
| `ceterms:keyword` | ✓ | ✓ | ✓ | ✓ |  |
| `ceterms:learningDeliveryType` | ✓ | ✓ | ✓ | ✓ |  |
| `ceterms:name` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `ceterms:occupationType` | ✓ | ✓ | ✓ | ✓ |  |
| `ceterms:offeredBy` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `ceterms:ownedBy` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `ceterms:requires` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `ceterms:revokedBy` |  |  |  | ✓ | ✓ |
| `ceterms:subjectWebpage` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `ceterms:supersedes` |  |  |  | ✓ |  |
| `ceterms:usesVerificationService` |  |  |  |  | ✓ |
