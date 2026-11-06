# CredentialEngine/ctdl-xtra — Open Issues Survey

**Snapshot:** 2026-07-01 · 46 open issues · source: GitHub `list_issues state=OPEN`

Categorized by relevance to extraction quality. Within each bucket, issues are listed newest-first.

---

## ★ Top issues where a better LLM extraction pipeline would help most

These are the 8 issues where the root cause is the model's extraction behavior (hallucination, field-boundary errors, inconsistency, missed fields, over-emission) rather than crawling or plumbing. A stronger LLM + tighter prompting/schema would move the needle directly.

| # | Title | Why it's an LLM-pipeline problem |
|---|---|---|
| **[#63](https://github.com/CredentialEngine/ctdl-xtra/issues/63)** | Revised course description (SOC 220) | **Hallucination.** Extracted description is a plausible paraphrase, not the verbatim catalog text. Smoking-gun case for grounding/faithfulness failure. |
| **[#134](https://github.com/CredentialEngine/ctdl-xtra/issues/134)** | CCSF inconsistencies — credit unit type, prerequisites | **Inconsistency.** Identical source phrasing ("Credit type: Credit/Degree Applicable") maps to different output values across rows in the same run. |
| **[#34](https://github.com/CredentialEngine/ctdl-xtra/issues/34)** | Course descriptions contain learning objectives | **Field-boundary bleed.** Model concatenates adjacent page sections (objectives) into `description` instead of stopping at the field boundary. |
| **[#265](https://github.com/CredentialEngine/ctdl-xtra/issues/265)** / **[#208](https://github.com/CredentialEngine/ctdl-xtra/issues/208)** | Prerequisites dumped in Description instead of Condition Profiles | **Field routing.** Structured prereq/coreq/advisory text is left as prose instead of decomposed into typed `ConditionProfile` entries. |
| **[#251](https://github.com/CredentialEngine/ctdl-xtra/issues/251)** | Missing credential descriptions | **Missed required field.** Description present on page but extract cell is blank — recall failure on a mandatory field. |
| **[#249](https://github.com/CredentialEngine/ctdl-xtra/issues/249)** / **[#253](https://github.com/CredentialEngine/ctdl-xtra/issues/253)** / **[#203](https://github.com/CredentialEngine/ctdl-xtra/issues/203)** | Boilerplate emitted when source has no data | **Over-emission / negative case.** Model fills ConditionProfile / CreditUnit scaffolding even when the page has nothing — should emit null. |
| **[#262](https://github.com/CredentialEngine/ctdl-xtra/issues/262)** / **[#116](https://github.com/CredentialEngine/ctdl-xtra/issues/116)** | Duplicate competencies / duplicate program rows | **Entity dedup.** Same competency or program emitted many times per framework/run; a smarter pipeline would recognize and collapse repeats. |
| **[#257](https://github.com/CredentialEngine/ctdl-xtra/issues/257)** | Asterisks in External ID / Coded Notation | **Verbatim fidelity.** Model carries HTML footnote markers (`*`) into the coded-notation field instead of returning the clean course code. |

Honorable mention: **[#266](https://github.com/CredentialEngine/ctdl-xtra/issues/266)** (constrain "Degree" credential type by institution locale) — a constraint-aware model could enforce controlled-vocab rules that today require post-hoc cleanup.

---

## 1. Extraction accuracy / missed fields / hallucination — 12 issues

| # | Title | Labels | Gist |
|---|---|---|---|
| [#265](https://github.com/CredentialEngine/ctdl-xtra/issues/265) | Prerequisites need to be pulled into Condition Profiles | — | Prereq text lands in `Description` prose instead of structured `ConditionProfile` rows. |
| [#262](https://github.com/CredentialEngine/ctdl-xtra/issues/262) | Competencies repeat within framework and throughout extract | — | Same 4 competencies emitted many times per framework — no dedup. |
| [#257](https://github.com/CredentialEngine/ctdl-xtra/issues/257) | Asterisks in External ID + Coded Notation fields | — | Course codes extracted with stray `*` chars not present on the catalog page. |
| [#253](https://github.com/CredentialEngine/ctdl-xtra/issues/253) | If no Credit data, remove Credit Unit Type Description | bug | Model emits placeholder credit-unit text even when no credit value exists. |
| [#251](https://github.com/CredentialEngine/ctdl-xtra/issues/251) | Missing Credential Descriptions | — | Required `Description` column blank for some credentials that do have descriptions on-page. |
| [#249](https://github.com/CredentialEngine/ctdl-xtra/issues/249) | If no condition listed, all Condition Profile fields should be blank | — | ConditionProfile scaffold rows emitted with empty description → creates blank profiles in Registry. |
| [#208](https://github.com/CredentialEngine/ctdl-xtra/issues/208) | Separation of Prerequisites, Corequisites, other Recommendations | — | Need distinct condition-profile types (prereq vs coreq vs advisory) instead of one blob. |
| [#203](https://github.com/CredentialEngine/ctdl-xtra/issues/203) | Course extractions: Selective condition profile info | — | Only populate ConditionProfile columns when a description was actually extracted. |
| [#134](https://github.com/CredentialEngine/ctdl-xtra/issues/134) | CCSF spreadsheet inconsistencies — credit unit type, prerequisites | — | Same source phrasing mapped inconsistently across rows in one extraction. |
| [#116](https://github.com/CredentialEngine/ctdl-xtra/issues/116) | Learning Program extraction pulling multiple pages / duplicate rows | bug | One program yields 3–6 rows from same or related URLs — no entity resolution. |
| [#63](https://github.com/CredentialEngine/ctdl-xtra/issues/63) | Revised course description: SOC 220 | bug, Catalogue | Extracted description is a hallucinated rewrite, not the catalog text. |
| [#34](https://github.com/CredentialEngine/ctdl-xtra/issues/34) | Course Descriptions contain course learning objectives | Crawler App Issue, MVP | `description` field bleeds into adjacent "Learning Objectives" section. |

---

## 2. Crawl / page-fetch / JS-rendering — 14 issues

| # | Title | Labels | Gist |
|---|---|---|---|
| [#261](https://github.com/CredentialEngine/ctdl-xtra/issues/261) | Berkeley City College URLs linking to blank pages | — | Emitted `Page URL` values resolve to an empty catalog shell page. |
| [#258](https://github.com/CredentialEngine/ctdl-xtra/issues/258) | Mt. San Antonio College course extract pulled 0 data | — | Run finished with 0 items — likely budget/crawl exhaustion; needs rerun. |
| [#228](https://github.com/CredentialEngine/ctdl-xtra/issues/228) | Linkless pagination support | CA Project | Catalog paginates via JS click handlers, no `<a href>` — need simulated interaction. |
| [#223](https://github.com/CredentialEngine/ctdl-xtra/issues/223) | Probing catalogue failures | CA Project | Need diagnostics for crawl failures that only reproduce on the deployed server. |
| [#221](https://github.com/CredentialEngine/ctdl-xtra/issues/221) | Dynamic Curricunet — pages broken on deployed environment | CA Project | Pages render fully locally but only partially in prod headless; no error surfaced. |
| [#211](https://github.com/CredentialEngine/ctdl-xtra/issues/211) | Support extracting "linkless" catalogues | CA Project | SPA catalogs with JS-router navigation (no URLs) need simulated-user crawling. |
| [#207](https://github.com/CredentialEngine/ctdl-xtra/issues/207) | Extracted course not found on resolved webpage | — | Content captured from a pre-redirect page; final `inCatalog` URL doesn't contain the course. |
| [#206](https://github.com/CredentialEngine/ctdl-xtra/issues/206) | inCatalog extractions with incomplete URLs | — | `inCatalog` emitted as relative path only, missing scheme/host. |
| [#191](https://github.com/CredentialEngine/ctdl-xtra/issues/191) | [California] Auto recipe creation failed | — | Auto-recipe detection silently fails to save for Coastline College catalog. |
| [#125](https://github.com/CredentialEngine/ctdl-xtra/issues/125) | eLumen catalog vendor — is recipe possible? | Catalogue | New vendor layout (sidebar categories → programs+courses) — feasibility ask. |
| [#122](https://github.com/CredentialEngine/ctdl-xtra/issues/122) | Manual recipe config does not detect link/pagination patterns | bug | "Detect" returns "Unknown" for both links and pagination on NWACC catalog. |
| [#114](https://github.com/CredentialEngine/ctdl-xtra/issues/114) | Address pages that have lazy loading | Improvement | Infinite-scroll catalog: pagination detected but 0 extractions produced. |
| [#79](https://github.com/CredentialEngine/ctdl-xtra/issues/79) | East Stroudsburg (SmartCatalogIQ) failed to detect valid config | — | Recipe auto-detect fails on SmartCatalogIQ vendor. |
| [#22](https://github.com/CredentialEngine/ctdl-xtra/issues/22) | Support "load more" pagination | Improvement | Handle button-click / lazy-load pagination patterns. |

---

## 3. CTDL mapping / schema / output-format — 9 issues

| # | Title | Labels | Gist |
|---|---|---|---|
| [#266](https://github.com/CredentialEngine/ctdl-xtra/issues/266) | Adjust degree type based on institution location | — | Restrict "Degree" credential type to non-US institutions per CTDL vocab rules. |
| [#254](https://github.com/CredentialEngine/ctdl-xtra/issues/254) | Change "In Catalog" header to "Subject Webpage" | — | Rename output column so credential extracts match Registry upload template. |
| [#252](https://github.com/CredentialEngine/ctdl-xtra/issues/252) | "is Part of" column pulling incorrect IDs | — | Competency `isPartOf` points at course/program ID, not the framework CTID. |
| [#250](https://github.com/CredentialEngine/ctdl-xtra/issues/250) | UUIDs generated instead of CTIDs | — | ID columns emit raw UUIDs; Registry needs `ce-`-prefixed CTIDs. |
| [#205](https://github.com/CredentialEngine/ctdl-xtra/issues/205) | Option for SubjectWebpage instead of inCatalog | — | Recipe-level toggle for which URL header to emit (non-catalog sources). |
| [#204](https://github.com/CredentialEngine/ctdl-xtra/issues/204) | Option for downloading data using a custom template | — | Let users supply an Excel template and map extracted fields into it. |
| [#202](https://github.com/CredentialEngine/ctdl-xtra/issues/202) | Add column with CTIDs | — | Add CTID column to output (no body). |
| [#179](https://github.com/CredentialEngine/ctdl-xtra/issues/179) | Implement updated template for course pre/co-requisites | — | New output template for prereq/coreq columns (no body). |
| [#141](https://github.com/CredentialEngine/ctdl-xtra/issues/141) | Linking Classes | — | Study/implement CTDL cross-class linking schema. |

---

## 4. New-field / coverage requests — 3 issues

| # | Title | Labels | Gist |
|---|---|---|---|
| [#255](https://github.com/CredentialEngine/ctdl-xtra/issues/255) | Allow regional selection in Language column | — | Let user pick `en-US` / `en-GB` etc. instead of hard-coded `en`. |
| [#143](https://github.com/CredentialEngine/ctdl-xtra/issues/143) | Expansion to new CTDL classes | — | Add extraction support for SupportService, AssessmentProfile, Metric, AccreditAction. |
| [#142](https://github.com/CredentialEngine/ctdl-xtra/issues/142) | Expansion of terms for the 4 classes | — | Extract additional CTDL properties beyond the current minimum set. |

---

## 5. UI / infra / other — 8 issues (not detailed)

[#259](https://github.com/CredentialEngine/ctdl-xtra/issues/259) meta tracking list · [#168](https://github.com/CredentialEngine/ctdl-xtra/issues/168) login UX bug · [#164](https://github.com/CredentialEngine/ctdl-xtra/issues/164) disk space · [#159](https://github.com/CredentialEngine/ctdl-xtra/issues/159) prod stack · [#154](https://github.com/CredentialEngine/ctdl-xtra/issues/154) proxy cost telemetry · [#62](https://github.com/CredentialEngine/ctdl-xtra/issues/62) explore batch API · [#40](https://github.com/CredentialEngine/ctdl-xtra/issues/40) recipe-config UX · [#21](https://github.com/CredentialEngine/ctdl-xtra/issues/21) role mgmt / notification emails.

---

## Takeaways for an eval

- **Largest bucket is crawl/render (14)**, not model quality — but those are engineering fixes, not LLM upgrades.
- **12 issues are pure extraction-quality** and cluster into 5 recurring failure modes a better pipeline should target:
  1. Hallucinated / paraphrased values (#63)
  2. Field-boundary bleed & wrong-field routing (#34, #265, #208)
  3. Inconsistent mapping of identical source text (#134)
  4. Over-emission when source is empty (#249, #253, #203)
  5. Missed required fields & duplicates (#251, #262, #116, #257)
- The **CTDL-mapping bucket (9)** is mostly deterministic post-processing (IDs, headers, templates) — low LLM leverage, high leverage for a schema/validation layer.
