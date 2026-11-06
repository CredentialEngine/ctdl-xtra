# ctdl-xtra — Architecture Notes

_How the extraction pipeline works today. Synthesized from a full read of `server/src/`, `common/`, tests, and docs._

---

## TL;DR

xTRA is a **crawl-then-extract** system: an LLM first reverse-engineers an institution's catalog structure into a reusable "recipe" (a crawl plan), then a second LLM pass extracts structured records from each detail page. The extractor is **OpenAI-only** (default `gpt-5.4-mini`), pulls a **narrow field set** (4 fields for a Credential, 3 for a Learning Program), and emits **Registry bulk-upload CSVs** — not CTDL JSON-LD. Hallucination is guarded by a verbatim-text-inclusion check with up to 3 retries.

---

## 1. Pipeline

```
Institution URL
   │
   ▼ Phase A — Recipe detection (one-time, LLM-driven)
recursivelyDetectConfiguration
   • detectCatalogueType   → COURSES | LEARNING_PROGRAMS | COMPETENCIES | CREDENTIALS
   • detectPageType        → DETAIL | DETAIL_LINKS | CATEGORY_LINKS
   • detectPagination      → {page_num}/{offset} template + total pages
   • detectUrlRegexp       → JS regex to harvest child URLs
   → RecipeConfiguration (JSON tree, saved to Postgres)
   │
   ▼ Phase B — Crawl (BullMQ)
fetchPage worker
   • Puppeteer (rebrowser + stealth) → raw HTML + webp screenshot
   • simplifyHtml → strip attrs, drop head/footer/iframe, collapse divs
   • turndown → simplified Markdown
   • follow recipe: paginate, regex-extract child URLs, enqueue
   │
   ▼ Phase C — Extract (BullMQ, per detail page)
extractData worker → extractAndVerifyEntityData
   • [optional] presencePrompt gate (competencies only)
   • [courses only] chunk if >1000 tokens & multi-course
   • extractEntityData → OpenAI structured-output OR forced tool-call
   • reportTextInclusion → is each field verbatim in the page?
   • retry ≤3× with bad extraction fed back
   • [competencies only] exploreAdditionalPages → follow outcome links
   → dataItem rows (Postgres)
   │
   ▼ Export
csv.ts → Registry Bulk Upload CSV (per catalogue type)
```

**Queues** (BullMQ/Redis): `detectConfiguration`, `fetchPage`, `extractData`, `extractDataWithApi`, `updateExtractionCompletion`.

---

## 2. LLM layer

| | |
|---|---|
| **Provider** | OpenAI only (`common/types.ts:96-98` — `enum Provider { OpenAI = "openai" }`, single member). No Claude anywhere. |
| **Models** | `gpt-4o`, `gpt-4.1`, `o3-mini`, `o4-mini`, `gpt-5`, `gpt-5-nano`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano` |
| **Default** | `gpt-5.4-mini` for all four catalogue types (`catalogueTypes.ts:212,305,345,455`); wrapper fallback `gpt-5` |
| **Output mode** | Forced function-call (Courses, Programs, all `detect*`) or `response_format: json_schema, strict:true` (Competencies, Credentials) |
| **System msg** | None — everything is a single `role:"user"` message |
| **Multimodal** | Page screenshot sent as `image_url` unless `skipScreenshot` (Competencies skip); silently dropped on `invalid_base64` |
| **Temperature** | Default `1` (!) — only Competencies overrides (`temperature:1, top_p:0.5`) |
| **Retry** | 10× exponential on API errors; separate 3× extraction retry with prior output as negative example |
| **Embeddings** | `text-embedding-3-small` (used in test similarity assertions) |

Wrapper: `server/src/openai.ts` — `simpleToolCompletion()` and `structuredCompletion()`. Cost tracked per call (`ModelPrices` table + `createModelApiCallLog`).

---

## 3. What it extracts (complete field inventory)

| Entity | Fields | Count |
|---|---|---|
| **Course** | `course_id`\*, `course_name`\*, `course_description`\*, `course_prerequisites`, `course_non_credit`, `course_credits_min`, `course_credits_max`, `course_credits_type` (CTDL enum), `course_ceu_credits` | 9 |
| **Learning Program** | `learning_program_id`\*, `learning_program_name`\*, `learning_program_description`\* | 3 |
| **Competency** | `text`\*, `competency_framework`, `competency_category` (`outcomes`/`course_objectives`/`unknown`), `language` | 4 |
| **Credential** | `credential_name`\*, `credential_description`\*, `credential_type`\* (38-value CTDL enum), `language` | 4 |

**20 fields total.** Notably **not** extracted for any type: cost/tuition, duration, delivery mode, location, occupation/industry codes, assessment info, admission requirements (beyond course prereqs), accreditation, offered-by/owned-by organization, subject webpage, keywords, outcome data, CTID, credit hours for programs.

Schema lives in `common/catalogueTypes.ts` (prompt descriptions) + `common/types.ts` (TS interfaces). All non-enum fields are typed `string` in the LLM schema.

---

## 4. Prompt design

Assembled per call from `catalogueTypes[type]` in `extractEntityData.ts:getBasePrompt()`:

```
Your goal is to extract {entity} data from this page.
   Extract the data EXACTLY as it shows up in the page.
   NEVER paraphrase, rewrite or change content unless requested.

{desiredOutput}
We are looking for the following fields:
{field}: {description} (REQUIRED)
...

PAGE URL: {url}

SIMPLIFIED PAGE CONTENT:
```markdown
{markdown}
```
```

Per-field descriptions in `catalogueTypes.ts` are the substantive instructions. Notable prompt-text observations:

- **Credentials `desiredOutput`** (`:447-454`): says "Do not list Certifications, those are not credentials" — but `Certification` **is** in the `credential_type` enum. Internal contradiction. Also: typo "prof of completion", "Don not include". Also: "Ignore stackable certificates" with no rationale.
- **Courses `credits_type`** (`:257-278`) — 20-line rule block; the most engineered prompt in the codebase.
- **Programs** — bare-bones; description says "take only the first few paragraphs" (deliberately truncates).
- **No CTDL context** — the LLM is never told what CTDL is, what the Registry expects, or given field-level examples of good CTDL values.
- **No few-shot** — `examples` field exists on the schema but no catalogue type populates it.

---

## 5. Hallucination guard

`extractAndVerifyEntityData.ts:reportTextInclusion()` — for each extracted field, checks whether the value (lowercased, alphanumeric-only) appears as a substring of the source markdown. Result stored as `TextInclusion<T>` booleans and rolled up to a `Text Verification Average` column in the CSV. If any `propertiesRequiredAsPhrases` field fails, the extraction is retried (≤3×) with the bad output fed back as a negative example ("Your previous extraction (INCORRECT) was: …").

This catches fabrication but **not** wrong-field routing (extracting the description into the name field), missed fields, or paraphrases that preserve some source words.

---

## 6. Output

`server/src/csv.ts` → Registry Bulk Upload CSV, one variant per catalogue type. Several columns are **hard-coded**: `Language="English"`, `Life Cycle Status Type="Active"`, `Learning Type="Course"/"Learning Program"`. Credential `External Identifier` is a `randomUUID()` (no natural key).

**No JSON-LD output.** Competency CSV borrows `@type`/`ceasn:*` header names but there's no `@context`, no graph, no `ceterms:` emitter.

---

## 7. Tests

`server/tests/extractions/` — golden tests that fetch real institution URLs live and assert extracted fields. 21 competency, 14 credential, 7 program, 3 course institution files. Helper `extractCredentials(url)` (`tests/index.ts:280`) is the **de-facto CLI** — it bypasses BullMQ/Postgres, calls Puppeteer + `extractAndVerifyEntityData` directly.

Tests themselves acknowledge extraction problems: `ivytech.test.ts` has `// TODO: this is not the correct credential name` on multiple assertions and comments-out description checks as "[volatile]".

---

## 8. Local run requirements

Full app: Postgres + Redis + Chromium + `OPENAI_API_KEY` all hard-required (import-time throws). No docker-compose; README gives raw `docker run` for PG+Redis.

**Minimal path for extraction-only:** the `tests/index.ts` helpers (`extractCredentials`, `extractCompetencies`) need only Chromium + `OPENAI_API_KEY` — but the import chain still pulls `data/index.ts`, so `DATABASE_URL` + `ENCRYPTION_KEY` must be set to *something* even if never connected. `checkDetection.ts` is a CLI for Phase A only.

---

## References

- `server/src/openai.ts` — wrapper
- `server/src/extraction/llm/*.ts` — 10 LLM call sites
- `common/catalogueTypes.ts` — prompts + schemas (554 lines)
- `common/types.ts` — TS interfaces + enums
- `server/src/csv.ts` — export
- `server/src/extraction/recursivelyDetectConfiguration.ts` — Phase A orchestrator
- `server/src/workers/{fetchPage,extractData}.ts` — Phase B/C workers
- `doc/worker-queues.md` — their own flow diagram
- `server/tests/index.ts` + `server/tests/extractions/**` — golden tests
