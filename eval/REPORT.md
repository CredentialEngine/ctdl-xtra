# CTDL xTRA — Evaluation & Improvement Proposal

_Prepared for Credential Engine · July 2026_
_Test institution: Western Governors University (wgu.edu)_

---

## Executive summary

We cloned and reviewed [`ctdl-xtra`](https://github.com/CredentialEngine/ctdl-xtra), ran its extraction design against five WGU program pages, and compared the output to (a) what's actually on each page and (b) WGU's own hand-published CTDL records in the Credential Registry.

**The dominant gap is coverage, not accuracy.** xTRA's Credential extractor requests **4 fields** (name, description, type, language). A typical WGU program page contains evidence for **15–18 CTDL properties**, and WGU's Registry records populate **24–27**. The fields xTRA doesn't attempt — cost, duration, delivery mode, admission requirements, courses, competencies, occupations, accreditation — are precisely the ones that make CTDL records useful for search and comparison.

On the fields it *does* attempt, xTRA has a self-inflicted accuracy problem: the prompt instructs the model to strip the degree type from `credential_name` ("Don not include the type of credential in the name"), so "Bachelor of Science in Computer Science" comes back as "Computer Science" — which contradicts CTDL practice and the tool's own golden tests (`ivytech.test.ts` has `// TODO: this is not the correct credential name` on multiple assertions).

An expanded 22-field CTDL-aligned schema, run through Claude with a single-page pass and no other architectural changes, lifts recall from **8.3% to 90.5%** on the same inputs — with correctly typed values (ISO 8601 durations, structured cost profiles, controlled-vocabulary enums). See §3 for the field-by-field matrix.

A second prompt bug: `language` is prompted as "The language in full (example: 'English')" — but CTDL `ceterms:inLanguage` requires a BCP-47 tag (`en`). All 5 baseline values fail Registry validation on this too.

**Recommended first move:** widen `common/catalogueTypes.ts` from 4 to ~22 fields and fix the credential-name prompt. This is a schema/prompt edit — no new architecture — and closes most of the coverage gap in one PR.

---

## 1. How xTRA works today

xTRA is a two-phase system:

1. **Recipe detection.** Given an institution URL, an LLM reverse-engineers the catalog structure — page types, pagination pattern, URL regexes for detail pages — into a reusable `RecipeConfiguration` (Postgres JSONB). This is clever and works well; not the focus here.
2. **Extraction.** A BullMQ worker fetches each detail page (Puppeteer + stealth), simplifies HTML to Markdown (cheerio + turndown), and calls the LLM once with a per-catalogue-type prompt + JSON schema. Output rows are exported as Registry Bulk-Upload CSVs.

**LLM layer:** OpenAI only (`enum Provider { OpenAI }` — single member). Default model `gpt-5.4-mini`; wrapper supports `gpt-4o` through `gpt-5.4`. Two output modes: forced tool-call (Courses, Programs) or `response_format: json_schema` (Credentials, Competencies). No system message; everything is one user turn. Temperature defaults to `1`.

**Field inventory** (`common/catalogueTypes.ts` + `common/types.ts`):

| Entity | Fields extracted | Not attempted |
|---|---|---|
| Credential | name, description, type (38-value enum), language | cost, duration, delivery, requirements, competencies, courses, occupations, industry, accreditation, keywords, credit hours, subject webpage, status, audience level, … |
| Learning Program | id, name, description | *(same)* |
| Course | id, name, description, prereqs, credits (min/max/type), CEU, non-credit flag | delivery, outcomes, cost, … |
| Competency | text, framework, category, language | — |

**Hallucination guard:** `reportTextInclusion` — checks each extracted field appears verbatim (lowercased alphanumeric) in the source markdown. If a required field fails, retry ≤3× with the bad output as a negative example. This catches fabrication but not wrong-field routing (issue #34) or paraphrase.

**Output:** CSV only. Several columns hard-coded (`Language="English"`, `Life Cycle Status="Active"`). Credential `External Identifier` is a fresh `randomUUID()` per run — no stable key.

Full architecture notes: [`code-review/01-architecture.md`](code-review/01-architecture.md).

---

## 2. Code-review findings

Ranked hypotheses from a read of the extraction path (each tested against WGU in §3):

| # | Finding | Impact | Evidence in code |
|---|---|---|---|
| **H1** | Schema attempts 4 credential fields; ~18 present on page | ★★★★★ | `common/types.ts:222-227`, `catalogueTypes.ts:456-476` |
| **H2** | Prompt tells model to strip degree type from name; contradicts own enum ("Do not list Certifications" but `Certification` is a valid `credential_type`) | ★★★★ | `catalogueTypes.ts:447-459`; own test `ivytech.test.ts:19,28` flags wrong names |
| **H3** | `temperature: 1` default for extraction | ★★★ | `openai.ts:135`; maps to open issue #134 (inconsistency) |
| **H4** | All non-enum fields typed `string` — no numbers, durations, nested profiles | ★★★ | `extractEntityData.ts:258-262` |
| **H5** | Single-page extraction; sibling tuition/admissions tabs never followed | ★★★★ | `exploreDuringExtraction` only enabled for Competencies |
| **H6** | Verbatim-substring check misses wrong-field routing | ★★★ | `extractAndVerifyEntityData.ts:reportTextInclusion`; open issue #34 |
| **H7** | No CTDL schema validation before export | ★★ | `csv.ts` — no check against Min-Data Policy |
| **H8** | LLM-generated split regex for chunking; 1000-token threshold is a gpt-4-era artifact | ★★ | `splitChunks.ts:10-73` |
| **H9** | LLM-generated URL regex for link discovery — brittle | ★★ | `detectUrlRegexp.ts` (256-line prompt) |
| **H10** | No per-field confidence or source citation in output | ★★ | `csv.ts` — only aggregate `Text Verification Average` |

Plus engineering hygiene: `assertNumber` regex rejects floats (`openai.ts:426`); `detectChunkSplitRegexp` logs wrong callSite; offset pagination is a `TODO` returning `[]`; `@ts-ignore` in the hot path.

Twelve of xTRA's 46 open issues are extraction-accuracy bugs (hallucination #63, field-bleed #34, inconsistency #134, boilerplate-on-empty #249/#253, dedup #262). Full list: [`code-review/00-open-issues.md`](code-review/00-open-issues.md).

---

## 3. WGU results

**Test set:** 5 program pages spanning bachelor's, master's, healthcare, and non-degree.

| Page | Source md | Registry CTID |
|---|---:|---|
| B.S. Computer Science | 44 KB | `ce-8f5a2e25-…` |
| MBA | 27 KB | `ce-6977cef9-…` |
| M.S. Nursing – Education | 38 KB | `ce-6f236de1-…` |
| B.S. Accounting | 50 KB | `ce-b75970c9-…` |
| Leadership Certificate | 13 KB | (n/a — different cert in Registry) |

**Method:** each page's HTML was simplified to Markdown using xTRA's own `simplifyHtml`+`turndown` pipeline, then extracted twice: once with xTRA's verbatim 4-field prompt/schema (**baseline**), once with a 22-field CTDL-aligned schema and a proper system message (**enhanced**). Both runs used Claude; see Assumptions.

### 3.1 Coverage — baseline vs enhanced

| Page | On-page fields | Baseline correct | Enhanced correct | Baseline recall | Enhanced recall |
|---|---:|---:|---:|---:|---:|
| B.S. Computer Science | 18 | 1 | 15 | 5.6% | 83.3% |
| MBA | 16 | 2 | 16 | 12.5% | 100.0% |
| M.S. Nursing – Education | 18 | 1 | 16 | 5.6% | 88.9% |
| B.S. Accounting | 18 | 1 | 16 | 5.6% | 88.9% |
| Leadership Certificate | 14 | 2 | 13 | 14.3% | 92.9% |
| **Total** | **84** | **7** | **76** | **8.3%** | **90.5%** |

Baseline populates 4 fields on every page but only `description` is reliably correct (5/5); `credential_name` (0/5), `inLanguage` (0/5 — wrong format), and `credentialType` (2/5 correct, 3/5 parent-type-not-subtype) drag it down. Detailed field-by-field: [`scoring/field-matrix.csv`](scoring/field-matrix.csv).

### 3.2 Accuracy — the `credential_name` bug (H2 confirmed)

All 5 baseline names strip the degree type per the prompt's instruction:

| Page | Baseline `credential_name` | Registry `ceterms:name` | Enhanced `name` |
|---|---|---|---|
| B.S. CS | `Computer Science` | Bachelor of Science, Computer Science | Bachelor of Science in Computer Science |
| MBA | `Business Administration` | Master of Business Administration | Master of Business Administration |
| MSN | `Nursing Education (BSN to MSN)` | Master of Science, Nursing - Education (BSN to MSN) | Master of Science in Nursing – Education (BSN to MSN) |
| B.S. Accounting | `Accounting` | Bachelor of Science, Accounting | Bachelor of Science in Accounting |
| Leadership Cert | `Business Leadership` | — | Business Leadership Certificate |

The baseline value would fail Registry validation (name is a required field and must match the credential as awarded) and produces the exact behavior the tool's own tests already flag as wrong.

### 3.3 What enhanced extraction captures that baseline can't

Concrete examples from the runs:

- **B.S. Computer Science** — 37 courses listed by name in `hasPart`; `estimatedCost` = `[{Tuition, 4125, USD, "per 6-month term"}, {TechnologyFee, 200, USD, "per term"}]`; `accreditedBy: ["ABET"]`; `industryCertifications: ["Linux Essentials", "ITIL 4 Foundation", …]`; `occupationType: ["Software Engineer", "Software Developer", …]`.
- **MBA** — `estimatedDuration.minimumDuration = "P12M"` with source quote; `accreditedBy: ACBSP`; 11 courses; 3 cost profiles including 12-month total.
- **M.S. Nursing** — `requires.prerequisiteCredentials: ["BSN", "current unencumbered RN license"]` (the licensure gate CTDL cares most about for healthcare); CCNE accreditation with URL; note in `_extractionNotes` that this MSN does not satisfy NP "3 Ps" — a nuance a human cataloguer would want.
- **Leadership Cert** — `estimatedDuration = P4M`, 9 credits, and the extractor **flagged a pricing discrepancy on the source page** in `_extractionNotes` ($281.25 vs $562.50 installments) — a QA win the baseline can't surface.

### 3.4 Failure taxonomy — baseline, 84 on-page cells

The full grid is 5 pages × 18 fields = 90 cells; 6 cells are n/a (the field isn't on that page — e.g. `accreditedBy` on the Leadership Cert). The 84 on-page cells break down as:

| Bucket | Count | of 84 | Example |
|---|---:|---:|---|
| **Not-attempted** (schema gap) | 64 | 76% | `estimatedCost` on any page — no cost field in schema |
| **Wrong-format** (prompt asks for wrong format) | 10 | 12% | `credential_name` = "Computer Science"; `language` = "English" not "en" |
| **Partial** (enum too coarse) | 3 | 4% | `credential_type` = `BachelorDegree`; Registry has `BachelorOfScienceDegree` |
| **Correct** | 7 | 8% | `description` (5/5), `credential_type` (2/5) |
| Hallucinated / on-page-but-missed | 0 | — | — |

Of the **77 baseline misses**, 64 (83%) are schema gaps — the model was never asked. The other 13 are prompt/enum defects that a text edit fixes. Zero hallucinations, zero cases where the model was asked and the fact was on the page but it failed to find it — this isn't a model-capability problem.

Full scorecards: [`scoring/scorecards.md`](scoring/scorecards.md).

---

## 4. Improvement proposal

Ranked by impact-per-effort. Each item names the file(s) to touch and which WGU misses it fixes.

### P1 — Widen the extraction schema · **effort S** · closes ~78% of the gap

Extend `CredentialStructuredData` and `LearningProgramStructuredData` in `common/types.ts` + `common/catalogueTypes.ts` to ~22 CTDL-aligned fields with proper types: `estimatedDuration` (DurationProfile), `estimatedCost` (CostProfile[]), `requires` (ConditionProfile), `learningDeliveryType`/`audienceLevelType` (enums), `teaches`, `occupationType`, `industryType`, `hasPart`, `accreditedBy`, `creditValue`. Add matching columns to `csv.ts`. The `enhanced-schema.mjs` in this evaluation is a working reference.

*Fixes:* every "not-attempted" cell in the failure taxonomy — cost, duration, delivery, requirements, courses, occupations, accreditation on all 5 WGU pages.

### P2 — Fix the credential prompt · **effort XS** · fixes 100% of name errors

Remove "Don not include the type of credential in the name," the "Do not list Certifications" contradiction, and "Ignore stackable certificates." Add 2–3 few-shot examples drawn from real Registry records. Set `temperature: 0` (or Claude's default) for extraction calls.

*Fixes:* all 5 wrong `credential_name` values; open issue #134 (inconsistency).

### P3 — Add Claude as a provider · **effort S**

`common/types.ts` `Provider` enum has one member. Add `Anthropic`, a `server/src/anthropic.ts` sibling to `openai.ts` (same `simpleToolCompletion`/`structuredCompletion` interface via Claude tool-use), and a `ProviderModel` entry for the Claude model. This is ~200 lines, mostly mirroring the existing wrapper. Makes P1 and P4 practical: the wider schema and multi-page context both benefit from Claude's larger context window and instruction-following on structured output.

### P4 — Multi-page gather step · **effort M** · captures the ~20% of fields that live on sibling tabs

WGU (and most universities) split tuition, admissions, and course lists across tabs/pages. Generalize `exploreDuringExtraction` (currently Competencies-only): before extraction, follow same-origin links whose anchor text matches a small set (tuition, cost, admission, requirements, courses, curriculum, careers), concatenate their simplified markdown into the extraction context. Claude's 200K context makes this a single call rather than N.

*Fixes:* on institutions where cost/admissions live off the overview page (WGU's pages are unusually consolidated, so the WGU test set understates this).

### P5 — Field-level validator pass · **effort S**

After extraction, a second cheap-model call: "for each populated field, does the value match the CTDL definition and appear on the source? Score 0–1 and cite the source sentence." Emit `{value, confidence, sourceQuote}` per field. Replaces the substring-only `reportTextInclusion`. This is what a human reviewer does today by hand (per CE's own guidance to "spot-check 10–15 rows").

*Fixes:* open issues #34 (field bleed), #63 (hallucination), #249/#253 (boilerplate-on-empty).

### P6 — Emit CTDL JSON-LD alongside CSV · **effort S**

Add a JSON-LD emitter that wraps each record in `{"@context": "https://credreg.net/ctdl/schema/context/json", "@type": "ceterms:…", …}`. Validate against `CredentialEngine/CTDL_Json_Validation_Schema` before export. This gives users a Registry-API-ready payload and catches enum/required-field errors that today only surface at upload.

### Suggested pilot

One PR covering P1 + P2 + P3, benchmarked on the 14 institutions already in `server/tests/extractions/credentials/` plus WGU. Metric: mean CTDL fields populated per credential, and % of `credential_name` values that match the Registry record. Estimate: 2–3 engineering days.

---

## 5. Assumptions & limitations

- Baseline runs used Claude with xTRA's exact prompt/schema (no `OPENAI_API_KEY` was available). Coverage findings (H1, H5) are model-independent — the 4-field ceiling is set by the schema. The name bug (H2) is prompt-driven and reproduces regardless of model. For a strict apples-to-apples on `gpt-5.4-mini`, run `harness/run.mjs --provider openai` with a key.
- WGU's Registry records are used as reference, not gospel — several are dated (`MBA_201404`), and `subjectWebpage` on all four degree records points to a college-level index page rather than the program page.
- Five pages is a demonstration, not a benchmark. The `harness/` scripts and `wgu/<slug>/model-input.md` inputs are ready to scale to a larger set.

---

## Appendix

- `code-review/01-architecture.md` — how xTRA works, annotated
- `code-review/02-hypotheses.md` — ranked findings with file:line references
- `code-review/00-open-issues.md` — 46 open issues categorized
- `ctdl-reference/field-spec.md` — CTDL field checklist with Registry policy
- `wgu/<slug>/` — one dir per credential: `page.html`, `page-annotated.md`, `model-input.md`, `registry.json`, `extracted.json` (see `wgu/README.md`)
- `scoring/` — field matrix CSV + scorecards + multi-extractor coverage
- `harness/` — standalone extraction runner (Node, ready for OpenAI or Anthropic key)

---

## 6. Toward a robust eval — detailed design

_Expanded from the summary in §4 above; this is the version to hand an engineer._

The current test suite (`server/tests/extractions/`) fetches live URLs and asserts a handful of fields with `expect.like(...)` — several assertions are commented out as `[volatile]` and two carry `// TODO: this is not the correct credential name`. That's a smoke test, not a benchmark. A benchmark that CE can hill-climb against and cite publicly:

### 6.1 · Golden set = existing Registry records

The truth data already exists: every credential an institution has manually published to the Registry is a labelled `(subjectWebpage → CTDL JSON-LD)` pair. No hand-labelling needed.

- **Selection.** CE nominates ~40 publishers whose Registry records are high-quality and current (the 35 already in `server/tests/extractions/` plus WGU/SNHU/ASU/a state system are a natural start). Pick ~3 credentials per publisher ≈ 120 pairs. Stratify by catalogue vendor (Acalog, CourseLeaf, Kuali, Coursedog, custom) since page structure clusters by vendor.
- **Freeze the inputs.** For each pair: fetch `ceterms:subjectWebpage`, save to `server/tests/fixtures/pages/<institution>/<slug>.html`; save the Registry JSON-LD to `<slug>.truth.json`. Extraction runs against the fixture, not the live URL — deterministic, and CI doesn't hit institution sites.
- **Registry caveat.** Some records are stale (WGU's `subjectWebpage` on all four degree records points to a college index page, not the program page). CE curating the selection filters most of this; where a truth field is empty or clearly outdated, mark it n/a rather than scoring against it.

### 6.2 · Metrics

Per run, emit a CSV with one row per (page, field):

| Column | |
|---|---|
| `page`, `field` | keys |
| `on_page` | Y/N — from truth file |
| `extracted` | value or ∅ |
| `verdict` | `correct` / `partial` / `wrong-format` / `wrong-value` / `not-attempted` / `hallucinated` |
| `source_quote` | if the extractor emits it (P5) |

Roll up to: **field-level recall** (correct ÷ on-page), **precision** (correct ÷ populated), **not-attempted rate**, and a **per-field reliability table** (which properties are ≥90% across the set). Track these per model and per prompt version so changes are attributable.

### 6.3 · Scoring — exact where possible, judge only for free text

Per-field verdict logic is mostly deterministic:

| Field class | Examples | Comparison |
|---|---|---|
| Enum / vocab | `credentialType`, `learningDeliveryType`, `audienceLevelType`, `credentialStatusType`, `inLanguage` | exact match, with a documented parent/child allowance (`BachelorDegree` ⊆ `BachelorOfScienceDegree`) |
| Numeric / structured | `estimatedCost.price`, `creditValue.value`, ISO durations | normalize (currency, ISO 8601) then equality within tolerance |
| Set-of-strings | `hasPart[]` course names, `accreditedBy[]` | Jaccard overlap ≥ threshold after normalization |
| Free text | `description`, `teaches[]`, `requires.description`, `occupationType[]`, cost `paymentPattern` | **judge** |

The **judge** is only for the last row: a cheap-model binary call — *"does the extracted value express the same fact as the reference?"* — so "Tuition: $4,125 per 6-month term" and "$4125/term (six months)" both count as correct, and "Software Developer" ≈ "Software Development Engineer" doesn't get scored as a miss. Calibrate it on ~30 human-labelled pairs and report Cohen's κ so the judge itself is trusted. xTRA already ships `similarEmbedding` in `server/tests/assertions.ts`; the judge is a natural extension of that.

### 6.4 · CI integration

- `pnpm test:eval` runs the frozen set, writes `eval-results/<git-sha>.csv`, and fails the build if recall drops >2pp from `main`'s last green.
- A `scripts/compare-eval.ts` that diffs two result CSVs and prints the field×page cells that changed — the thing you actually look at when a PR moves the number.

### 6.5 · What this unlocks

With a frozen benchmark, the schema-widening PR becomes "recall 8% → 90% on 120 pages, precision 95%" instead of "we added fields." It also lets CE publish an accuracy figure on the xTRA product page (currently there is none), and it's the substrate for A/B-ing model choices (`gpt-5.4-mini` vs Claude vs `gpt-5.4`) on cost-vs-quality.

---

