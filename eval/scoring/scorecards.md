# ctdl-xtra Evaluation — Scorecards

## Headline numbers

**xTRA baseline captures 7/84 CTDL fields present on WGU pages (8.3% recall). Enhanced schema captures 76/84 (90.5% recall).**

Counting partial matches as captures: baseline **10/84 (11.9%)**, enhanced **81/84 (96.4%)**.

**5/5 baseline `credential_name` values are wrong** due to the "strip type from name" prompt instruction — every extracted name drops the degree/credential type (`"Computer Science"` instead of `"Bachelor of Science, Computer Science"`; `"Business Leadership"` instead of `"Business Leadership Certificate"`), directly contradicting `ceterms:name` which is the full credential title.

**5/5 baseline `language` values are wrong-format** — xTRA emits `"English"` where CTDL `ceterms:inLanguage` requires a BCP-47 tag (`"en"`).

The baseline schema simply does not attempt **14 of 18** page-scrapeable CTDL fields. Of the 4 it does attempt, only `description` is reliably correct (5/5).

---

## 1. Per-page recall

| page | on-page fields | baseline populated | baseline correct | enhanced populated | enhanced correct | baseline recall | enhanced recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| bs-computer-science | 18 | 4 | 1 (+1p) | 16 | 15 (+1p) | 5.6% | 83.3% |
| mba | 16 | 4 | 2 | 16 | 16 | 12.5% | 100.0% |
| ms-nursing-education | 18 | 4 | 1 (+1p) | 18 | 16 (+2p) | 5.6% | 88.9% |
| bs-accounting | 18 | 4 | 1 (+1p) | 18 | 16 (+2p) | 5.6% | 88.9% |
| cert-leadership | 14 | 4 | 2 | 14 | 13 | 14.3% | 92.9% |
| **TOTAL** | **84** | **20** | **7 (+3p)** | **82** | **76 (+5p)** | **8.3%** | **90.5%** |

`(+Np)` = additional partial matches (correct but less specific / incomplete). Recall percentages are strict-correct ÷ on-page.

---

## 2. Per-field reliability

| CTDL field | on-page (0–5) | registry has (of 4°) | baseline correct | enhanced correct |
|---|---:|---:|---:|---:|
| name | 5 | 4 | 0 | 5 |
| description | 5 | 4 | **5** | 5 |
| credentialType | 5 | 4 | 2 (+3p) | 3 (+2p) |
| subjectWebpage | 5 | 4 | n/a | 5 |
| inLanguage | 5 | 4 | 0 | 4 |
| credentialStatusType | 5 | 4 | n/a | 5 |
| learningDeliveryType | 5 | 4 | n/a | 5 |
| audienceLevelType | 4 | 4 | n/a | 3 |
| estimatedDuration | 5 | 4 | n/a | 4 (+1p) |
| creditValue | 4 | 0 | n/a | 2 (+1p) |
| estimatedCost | 5 | 4 | n/a | 5 |
| requires (admission) | 5 | 4 | n/a | 5 |
| teaches (competencies) | 5 | 0 | n/a | 5 |
| occupationType | 4 | 4 | n/a | 4 |
| industryType | 5 | 4 | n/a | 5 |
| hasPart (courses) | 5 | 1 | n/a | 4 (+1p) |
| accreditedBy | 4 | 2 | n/a | 4 |
| industryCertifications | 3 | 0 | n/a | 3 |

° Registry column counts the 4 degree records only; cert-leadership has no published Registry record (marked n/a in matrix). `n/a` in baseline column = field not in xTRA's 4-field schema.

**Observations:**
- Baseline's only reliably correct field is `description` (5/5).
- Enhanced achieves 5/5 on 10 of 18 fields.
- Weakest enhanced field is `creditValue` (2/4) — WGU's competency-unit model rarely states a program-total credit count on the page.
- Enhanced missed `audienceLevelType` for bs-computer-science (left null despite "bachelor's degree" being explicit) — extractor inconsistency, not a page gap.
- Enhanced captures fields WGU itself doesn't publish to the Registry: `teaches` (0 registry, 5 enhanced), `industryCertifications` (0 registry, 3 enhanced), `hasPart` course lists (1 registry, 5 enhanced).

---

## 3. Failure taxonomy — baseline

90 total (page, field) cells. 7 correct, **83 misses** bucketed:

| Bucket | Count | Share of misses | Example |
|---|---:|---:|---|
| **not-attempted (schema gap)** | 70 | 84.3% | `estimatedCost` — bs-computer-science page states "$4,125 per six-month term + $200 e-books fee" plainly; xTRA schema has no cost field. 64 of these 70 cells have on-page evidence going uncaptured. |
| **wrong-format** | 10 | 12.0% | `name` × 5: prompt instruction strips credential type → `"Accounting"` instead of `"Bachelor of Science, Accounting"`. `inLanguage` × 5: emits natural-language `"English"` instead of BCP-47 `"en"`. |
| **wrong-CTDL-value** | 3 | 3.6% | `credentialType` for bs-cs, msn, bs-acct: baseline emits parent type `BachelorDegree` / `MasterDegree` where page + Registry support the subtype `BachelorOfScienceDegree` / `MasterOfScienceDegree`. Valid CTDL, but loses precision. |
| **on-page-but-missed** | 0 | 0% | — (every attempted field found *something*) |
| **hallucinated** | 0 | 0% | — (no fabricated values observed) |

**Takeaway:** baseline's problem is overwhelmingly **schema coverage**, not extraction quality. The 4-field schema ignores 78% of the CTDL signal present on a typical program page. Of the 4 fields it does extract, 2 are systematically mis-formatted by prompt design.

---

## 4. Notable enhanced-extraction wins

Concrete examples of what the 22-field schema captures that baseline structurally cannot:

1. **37 courses enumerated for BS Computer Science** (`hasPart`) — full course list from "Introduction to Computer Science" through "Advanced Java", matching the 37-course count stated on page and the 37 `targetLearningOpportunity` refs in WGU's Registry record.
2. **CCNE accreditation with URL for MSN** (`accreditedBy`) — `{name: "Commission on Collegiate Nursing Education", acronym: "CCNE", subjectWebpage: "http://www.ccneaccreditation.org"}`. WGU's own Registry record for this program does *not* populate `accreditedBy`.
3. **P12M ISO minimum duration + $9,610 aggregate cost for MBA** (`estimatedDuration`, `estimatedCost`) — parsed "as little as 12 months" → `minimumDuration: "P12M"` and captured the advertised one-year total alongside the $4,805/term breakdown.
4. **Full admission ConditionProfile for MSN** (`requires`) — BSN degree + active unencumbered RN license (state-of-residence or employment) + criminal background check via DISA + immunization proof + 5-year transfer-credit window. Registry record has only a generic "must satisfy learning opportunities" stub.
5. **P4M / 9 credits / $1,125 total for cert-leadership** (`estimatedDuration`, `creditValue`, `estimatedCost`) — the certificate page's compact facts table fully structured, including the $499/mo overtime subscription and 4×$281.25 installment plan.
6. **120-credit total + 3 embedded Badgr certificates for BS Accounting** (`creditValue`, `hasPart`) — pulled 120 credits from FAQ text and captured the three stackable WGU certificates (Accounting, Strategic Thinking & Innovation, Leadership) with their badgr.com URLs.

---

## 5. Enhanced-extraction misses (for completeness)

| page | field | issue |
|---|---|---|
| bs-computer-science | audienceLevelType | Left null; should be `BachelorsDegreeLevel` (trivially derivable, extractor was inconsistent — filled it for bs-accounting). |
| bs-computer-science | creditValue | Left null; page gives "37 courses × 3–4 units" but no total. Defensible omission. |
| bs-computer-science | estimatedDuration | Description-only, no ISO value (competency-based; page gives no fixed duration). Partial. |
| ms-nursing-education | credentialType | `MasterDegree` — page/Registry support `MasterOfScienceDegree`. Partial. |
| ms-nursing-education | creditValue | `value: null`, description infers ~36. Partial. |
| bs-accounting | credentialType | `BachelorDegree` — page/Registry support `BachelorOfScienceDegree`. Partial. |
| bs-accounting | hasPart | 40 courses summarized in one CourseSet blob rather than enumerated individually. Partial. |
| cert-leadership | inLanguage | `"English"` — should be `"en"`. Same format bug as baseline; enhanced schema didn't enforce BCP-47 here. |

---

*Source data: `runs/*.json` (baseline + enhanced extractions), `wgu-test-pages/*.md` (on-page annotations), `wgu-ground-truth/*.summary.md` + `INDEX.md` (Registry records). Full 90-row detail: `scoring/field-matrix.csv`.*
