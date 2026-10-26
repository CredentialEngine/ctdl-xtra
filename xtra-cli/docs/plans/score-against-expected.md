# Score extraction against `expected`, not `ctdl_expected`

## Context
`xtra score extraction match` read its extracted values from
`record["ctdl_expected"]["properties"]`. It now scores the record's flat
`expected` object, keyed by ceterms properties:

```json
"expected": {
  "ceterms:creditValue": 5.0,
  "ceterms:creditUnitType": "Units",
  "ceterms:description": "…",
  "ceterms:codedNotation": "ABDY 112"
}
```

A separate PR changes extraction so `expected` is written with ceterms keys;
this change is scorer-only.

## Decisions
- No fallback to `ctdl_expected`: a record without `expected` scores as all missing.
- A flat `ceterms:creditValue` counts as `creditMinValue`, `creditMaxValue` and `creditValue`, same as the nested-profile rule.
- `None` values are skipped.

## Changes
- `src/implementations/score_extraction_match.py`: `extracted_values()` walks `expected`; `_add_profile()` fans a scalar `creditValue` out to min and max.
- `README.md` (~line 797): describes `expected` and the credit rule.
- `tests/implementations/test_score_extraction_match.py`, `tests/xtra/scoring/extraction/test_match.py`: records now carry `expected`; new tests for flat creditValue, missing `expected`, list values.

## Verification
`pytest -q` from `xtra-cli`.
