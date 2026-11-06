# ctdl-xtra — Hypothesized Improvements

_Code-review findings on the extraction path, ranked by expected impact. Each is a testable hypothesis; Phase 4 (WGU scoring) confirms or refutes._

---

## H1 — Field coverage is the dominant gap, not accuracy · impact: ★★★★★

**Observation.** xTRA extracts 4 fields for a Credential (name, description, type, language) and 3 for a Learning Program. The CTDL Registry Minimum Data Policy plus recommended fields cover ~25–30 properties, most of which are present on a typical WGU program page: tuition, time-to-complete, delivery mode, admission requirements, learning outcomes, career/occupation targets, accreditation, credit hours. **None of these are attempted.**

**Why it's this way.** The `catalogueTypes.ts` schema is hand-maintained; each new field means writing a prompt description + updating TS types + adding a CSV column. The team appears to have started narrow (Course id/name/description/credits) and not expanded.

**Claude intervention.** Widen `CredentialStructuredData` and `LearningProgramStructuredData` to ~25 CTDL-aligned fields with proper types (numbers, enums, nested objects). Claude with structured tool-use handles a 25-field schema in one pass; the incremental cost is negligible. This is the single highest-leverage change and is mostly a schema/prompt edit, not new architecture.

**Evidence to gather:** For each WGU page, count CTDL-relevant facts on the page vs fields xTRA populates → the "not-attempted" bucket in the failure taxonomy.

---

## H2 — Prompt contradictions and typos degrade credential extraction · impact: ★★★★

**Observation.** `catalogueTypes.ts:447-454` (Credentials `desiredOutput`):
- "Do not list Certifications, those are not credentials" — but `Certification` is in the `credential_type` enum at :499. The model is told to skip a valid answer.
- "Ignore stackable certificates" — arbitrary; many institutions publish these as first-class credentials.
- Typos: "prof of completion", "Don not include" (:459).
- `credential_name` prompt says "Do not include the type of credential in the name" → so "Bachelor of Science in Computer Science" should extract as "Computer Science"? That contradicts CTDL practice (Registry records use full names).

**Evidence in their own tests:** `ivytech.test.ts:19,28` — `credential_name: expect.like("Applied Science") // TODO: this is not the correct credential name`. The model is following the "strip the type" instruction and producing bad names.

**Claude intervention.** Rewrite the credential prompt with CTDL definitions in-context and 2–3 few-shot examples pulled from Registry records. Remove the contradictions. This is a prompt-only fix.

---

## H3 — Temperature=1 causes run-to-run inconsistency · impact: ★★★

**Observation.** `openai.ts:135` — `temperature: options?.temperature ?? 1`. No catalogue type sets a lower value for extraction. Temperature 1 is appropriate for creative generation, not deterministic extraction.

**Maps to open issue #134** (inconsistent mapping of identical source text).

**Claude intervention.** Set `temperature: 0` for all extraction calls. One-line change; free.

---

## H4 — All-string schema loses type safety and CTDL formatting · impact: ★★★

**Observation.** `extractEntityData.ts:258-262` — every property is `{type: "string"}` in the tool schema (except `credits_type`). Credits are parsed to float in post-processing but duration, cost, dates, booleans are all free text. CTDL wants ISO 8601 durations (`P24M`), typed cost profiles, controlled vocabularies. The model isn't asked for them, so it can't provide them.

**Claude intervention.** Use JSON Schema with proper types, formats, and enums per CTDL controlled vocabularies. Where CTDL wants a nested object (ConditionProfile, CostProfile, DurationProfile), define the nested schema. Claude tool-use enforces these at the API layer.

---

## H5 — Single-page extraction misses facts on sibling pages · impact: ★★★★

**Observation.** WGU (and most universities) split program info across tabs/pages: overview, tuition, admissions, courses, careers. xTRA extracts from **one** DETAIL page. `exploreDuringExtraction` exists but only Competencies enable it, and it only follows outcome-specific links.

**Claude intervention.** An agentic "gather" step: given the program overview page, follow the tuition/admissions/courses/outcomes sibling links (same-origin, same-program), concatenate the simplified markdown, then extract once from the combined context. This is where Claude's larger context window and better instruction-following on multi-document synthesis pay off.

---

## H6 — Verbatim-inclusion check misses wrong-field routing and paraphrase · impact: ★★★

**Observation.** `reportTextInclusion` only checks substring presence. If the model puts the program description in the `credential_name` field, the text is still "on the page" → passes verification. Open issue #34 (objectives leak into description) is exactly this.

**Claude intervention.** A second-pass validator: given the extracted record + source markdown, ask a fresh model instance "for each field, is this the *right* value for this field, or did it come from elsewhere on the page?" with a per-field confidence score. Cheap (small model, short output) and catches the failure mode substring-matching can't.

---

## H7 — No CTDL-schema validation before export · impact: ★★

**Observation.** CSV rows are written with hard-coded `Language="English"`, `Life Cycle Status="Active"`, no check against the Registry's Minimum Data Policy or CTDL JSON Schema. Invalid `credential_type` values would only surface at Registry upload.

**Claude intervention.** A Claude-driven validate step: render the extracted record as CTDL JSON-LD, ask Claude to check it against the CTDL schema + Minimum Data Policy, report missing-required and invalid-enum. Or (cheaper) use `CredentialEngine/CTDL_Json_Validation_Schema` programmatically and have Claude explain failures.

---

## H8 — 1000-token chunk threshold + LLM-generated split regex is fragile · impact: ★★

**Observation.** `splitChunks.ts` — pages >1000 tokens with multiple courses are split by an LLM-generated regex, retried up to 10× until chunk count matches expected ±10%. Regex generation for arbitrary HTML-derived markdown is brittle; the 1000-token limit is a `gpt-4`-era artifact.

**Claude intervention.** With 200K context, drop chunking entirely for pages under ~50K tokens (nearly all). For genuine mega-pages, semantic chunking (ask model for entity boundaries as character offsets, not a regex).

---

## H9 — `detectUrlRegexp` regex generation is a known reliability sink · impact: ★★

**Observation.** `detectUrlRegexp.ts` (256 lines of prompt) asks the LLM to write a JS regex matching detail-page URLs from a sample. Regex generation is notoriously unreliable; several open issues in the crawl/fetch bucket trace to bad regexes missing pages.

**Claude intervention.** Replace regex-generation with a per-URL classifier: for each discovered link, ask "is this a {entity} detail page? y/n" in a batched call. More LLM calls but far more reliable, and Claude Haiku-class makes it cheap.

---

## H10 — No confidence / provenance in output · impact: ★★

**Observation.** CSV has a `Text Verification Average` column but no per-field confidence, no source-span citation. Reviewers (per CE's own guidance) must "spot-check 10–15 random rows" blind.

**Claude intervention.** Emit per-field `{value, confidence, sourceQuote, sourceUrl}`. Trivial schema extension; huge UX win for the human review step.

---

## Engineering-hygiene findings (lower priority for the pitch)

- **Copy-paste bug**: `detectChunkSplitRegexp.ts` logs `callSite: "detectUrlRegexp"` — cost attribution is wrong.
- **`@ts-ignore` in hot path** (`extractEntityData.ts:322`) — schema type mismatch papered over.
- **Offset pagination is a TODO** (`fetchPage.ts:60-62`) — returns `[]`, silently drops pages.
- **`randomUUID()` as External Identifier** for credentials — no stable key; re-running an extraction produces new IDs, breaking Registry updates.
- **No system message** — all instructions in the user turn; misses a cheap prompt-engineering lever.
- **`assertNumber` regex** (`openai.ts:426`) only matches integers (`^\d+$`), rejects floats — inconsistent with `parseCreditValue` which uses `parseFloat`.

---

## Test plan mapping

| Hypothesis | WGU test | Pass/fail signal |
|---|---|---|
| H1 coverage | Count CTDL facts on page vs fields populated | "not-attempted" ≫ "missed" in failure taxonomy |
| H2 prompt bugs | Credential name for BS CompSci, MBA | Name comes back as "Computer Science" not "Bachelor of Science in Computer Science" |
| H3 temp=1 | Run same page 3× | Output varies |
| H4 typing | Duration/cost fields | Free text, not ISO/structured |
| H5 multi-page | Tuition, admission reqs on WGU | Absent from extraction (they're on sibling tabs) |
| H6 wrong-routing | Description content | Description contains outcome bullets or vice versa |
