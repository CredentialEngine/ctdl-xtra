# Research: profile values (item 10)

Done on 2026-11-04, before any answers. Code was read, and the CTDL schema and the Registry were checked; nothing was
changed. Paths are relative to `golden-dataset-studio/` unless they start with `xtra-cli/`.

## The Studio today: flat in every layer

| Layer | Today | What a profile list needs |
|---|---|---|
| Rule definition | `rule_type` css / css+regex / regex / labelled / constant / source_url / none (`model.py:60`). `multiple` splits by elements / separator / regex (`engine.py:341-446`). | A rule that emits objects with named fields. `split: regex` with named groups is the closest hook (`engine.py:383-389`). |
| Extraction table | `matches(rule_id, occurrence_key, value_index, value: str)` (`model.py:77`) | A group index, or a field name per value |
| Parent → child | A child reads `input: {from: "rule"}` and runs once per parent item, but its results are flattened. `value_index` counts across the flattened list, and skipped items shift it (`engine.py:264-282, 429-445`). | Keep the parent item index |
| Rows / review | A list row has `items[]`, ✓/✕ per item and a missing-item flow (`review.py:193-210`, `ListItems.tsx:20-46`) | ✓/✕ per profile, an edit per field |
| Annotation | `expected {text, css_path, char_start, char_end, segments[]}`. `segments` is one value in several pieces (`query.py:28-33`). | `expected.fields{name: {text, css_path, …}}` per profile |
| Golden JSON | One `fields[]` entry per value, `ctdl_property` = flat `a>b` path (`golden.py:18, 552-555`) | Profile objects, or a group index on flat fields |
| Scoring | xtra `score_extraction_match`: per property, exact pairs first, then greedy one-to-one by rapidfuzz ratio ≥ 0.8; extras cost nothing (`:187-257`) | Pair the objects, then score each field |

The deferral being reversed: `docs/qrspi/property-rules/01-questions.md:16-17` and A3.13 (`:328-333`); spec O3 and
row 13 (`03-spec.md:51, 80`).

## CTDL (Credential Engine Schema-Development repo, 2026-10-05; credreg.net blocks scripted fetches)

| Class | Property → kind |
|---|---|
| DurationProfile | `exactDuration`, `minimumDuration`, `maximumDuration`, `timeRequired` (status *unstable*) → `schema:Duration` (ISO 8601, `PT54H`); `description` → language map |
| ValueProfile | `schema:value` / `minValue` / `maxValue`, `qdata:percentage` → float; `schema:description` → language map; `creditUnitType`, `creditLevelType` → Concept (published as CAO); `subject` → CAO |
| ConditionProfile | `name`, `description`, `condition`, `experience` → language map; `targetLearningOpportunity` → references; `creditValue` → ValueProfile; `alternativeCondition` → ConditionProfile; plus `minimumAge`, `yearsOfExperience`, `weight`, `dateEffective`, … |
| IdentifierValue | `identifierType` URI, `identifierTypeName` language map, `identifierValueCode` string |

On a Course: `prerequisite` → **Course only**; `entryCondition`, `corequisite` → ConditionProfile; `requires`,
`recommends` → ConditionProfile and others.

## The Registry

- AVC is published only as an organization record (`ce-c67bf86a-7ed0-4ea0-9d0e-049a7f18c345`). It has no courses.
- None of the ~200 California community-college courses checked has more than one DurationProfile. Most have none.
- Examples:
  - ART-16 (`ce-11ca713a-…`): `estimatedDuration: [{minimumDuration: PT72H, maximumDuration: PT81H}]`, and
    `creditValue: [{schema:value: 3.0, creditUnitType: [CAO SemesterHour]}]`.
  - WORKEXP-697 (`ce-d84ae762-…`): `requires: [{ConditionProfile, name: "Course Recommendations/Requirements",
    description: "Other: Must be employed or have an internship."}]`.
- Saved responses: the session scratchpad `reg/` folder (not committed).

## xtra-cli (out of scope, A3.16): what it does with profiles

- **Extraction:** flat fields: `course_credits(_min|_max|_unit)`, `course_prerequisites`, and lecture/lab hours.
  Lecture and lab hours map to no CTDL term (`xtra-cli/lib/inventory.py:10-17`).
- **Transform:** builds a correct ValueProfile from those fields (`xtra-cli/lib/mapping.py:45-74`). It writes
  prerequisites to `requires: [{name}]` (`:132-142`). `extract.py:57` writes them to `prerequisite` instead.
- **Scorer** (`xtra-cli/src/implementations/score_extraction_match.py:64-77, 113-125`):
  - It looks for `ceterms:value` / `ceterms:minValue` keys, which neither the Registry nor `mapping.py` uses.
  - DurationProfiles and ConditionProfiles are reduced to `ceterms:name`, so a DurationProfile, which has no name,
    scores nothing.
  - This was found by reading the code, not by running it.

## Scoring sketch (input for the spec)

1. For each course and profile property, pair golden profiles with extracted ones one to one. Match on a **key field**
   (description for Duration and Condition, unit type for Value) with xtra's normalised similarity (≥ 0.8).
2. Score each paired field:
   - Text by similarity.
   - Durations and numbers by value after parsing (`54.0` = `PT54H`). A range compares as min and max.
   - Lists inside a profile (`targetLearningOpportunity`) as a multiset.
3. Unpaired golden profiles count as missed (recall). Unpaired extracted profiles count as extra (precision).
4. Roll up three numbers per property: profile recall, profile precision, and field accuracy over the paired profiles.
