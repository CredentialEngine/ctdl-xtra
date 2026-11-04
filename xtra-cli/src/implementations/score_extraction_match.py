"""Match extracted records against a baseline.

A baseline file is a list of entities, each a list of
{ctdl_property, value, source_url} fields. The script does not care whether
the baseline is verified; it only compares what was extracted with it.

What is compared is a unit, per entity and property:

- a value: a string or a number, for an ordinary property;
- an object: one dict, for a list-of-objects property such as
  ceterms:estimatedDuration ({ceterms:description, ceterms:timeRequired});
  several baseline fields with the same property form the list;
- absent: a baseline field `{"value": null, "absent": true}` says the
  property is not on the page. In a record, an explicit `null` is the
  extractor's claim that it is not on the page; a missing key is no claim.

Matching, per entity and property: exact pairs first, then the rest
greedily by similarity, best pair first, one to one. Objects pair by their
key field (OBJECT_KEYS) and are exact only when every field is. Each unit
gets one outcome:

- match: exact (an absent baseline against an extracted null too);
- partial: paired, similarity >= PARTIAL_THRESHOLD, not exact (an
  object: every field at least that close);
- wrong: paired below the threshold (an object: any field below it);
- missing: a baseline unit with no partner;
- unsure: the baseline says absent and the record has no key for the
  property at all, so the extractor made no claim;
- extra: an extracted unit with no partner, for a property the baseline
  entity covers (an absent one included). Properties it does not cover are
  listed in `unscored_extras` and cost nothing.

Two modes, never blended, decide what `fields` lists:

- exact: a field matches only when the extracted value is identical to the
  baseline value. Paired but not identical is a mismatch.
- partial: the exact matches are set aside and only the rest is looked at,
  partial or wrong by similarity. This tells how much non-exactness the
  extractor shows, and exact matches cannot hide it.

Both modes report the same unit numbers, micro-averaged (summed over every
entity), per property and overall: `found` (recall) = match / baseline
units, `right` (precision) = match / extracted units of covered
properties, and `entities_exact` = entities whose every covered unit
matched / entities. `exact_match_rate` = match / baseline units = found.

- Text similarity - for similarity algorithm See `similarity()`.

A baseline field with `"location": null` and no `absent` flag is implied,
not printed on the page. It is counted under `skipped_implied` and never
scored. Every field that is not an exact match is listed in `outliers`,
worst first, and every extra in `extras`.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from rapidfuzz import fuzz

from common.keys import (
    baseline_run_prefix,
    extract_report_key,
    records_prefix,
)

REPORT_SCHEMA = "xtra-extraction-match-report-2"

MODE_EXACT = "exact"
MODE_PARTIAL = "partial"
MODES = (MODE_EXACT, MODE_PARTIAL)

PARTIAL_THRESHOLD = 0.8

OUTCOME_MATCH = "match"
OUTCOME_MISMATCH = "mismatch"
OUTCOME_PARTIAL = "partial"
OUTCOME_WRONG = "wrong"
OUTCOME_MISSING = "missing"
OUTCOME_UNSURE = "unsure"
OUTCOME_EXTRA = "extra"
MODE_OUTCOMES = {
    MODE_EXACT: (
        OUTCOME_MATCH,
        OUTCOME_MISMATCH,
        OUTCOME_MISSING,
        OUTCOME_UNSURE,
    ),
    MODE_PARTIAL: (
        OUTCOME_PARTIAL,
        OUTCOME_WRONG,
        OUTCOME_MISSING,
        OUTCOME_UNSURE,
    ),
}
# Every unit's outcome, whichever the mode: the baseline side, then extra.
UNIT_OUTCOMES = (
    OUTCOME_MATCH,
    OUTCOME_PARTIAL,
    OUTCOME_WRONG,
    OUTCOME_MISSING,
    OUTCOME_UNSURE,
    OUTCOME_EXTRA,
)

UNIT_VALUE = "value"
UNIT_OBJECT = "object"
UNIT_ABSENT = "absent"

STATUS_SCORED = "scored"
STATUS_SKIPPED = "skipped"

CREDIT_VALUE = "ceterms:creditValue"
CREDIT_MIN = "ceterms:creditMinValue"
CREDIT_MAX = "ceterms:creditMaxValue"
CREDIT_UNIT = "ceterms:creditUnitType"
SUBJECT_WEBPAGE = "ceterms:subjectWebpage"
NAME = "ceterms:name"
DESCRIPTION = "ceterms:description"

# How the keys of a nested creditValue profile read as baseline properties.
# A single printed credit is both the minimum and the maximum. CTDL, the
# Registry and lib/mapping.py write a ValueProfile's numbers as
# schema:value / schema:minValue / schema:maxValue; the ceterms: spellings
# are kept for older records.
CREDIT_PROFILE_KEYS = {
    "ceterms:value": (CREDIT_MIN, CREDIT_MAX),
    "ceterms:minValue": (CREDIT_MIN,),
    "ceterms:maxValue": (CREDIT_MAX,),
    "schema:value": (CREDIT_MIN, CREDIT_MAX),
    "schema:minValue": (CREDIT_MIN,),
    "schema:maxValue": (CREDIT_MAX,),
    "ceterms:unitText": (CREDIT_UNIT,),
}

# List-of-objects properties: an extracted dict is kept whole, and objects
# pair by this field. A baseline dict under any other property pairs by
# its description, else by its first field.
OBJECT_KEYS = {"ceterms:estimatedDuration": DESCRIPTION}

OUTLIERS_SHOWN = 20
VALUE_WIDTH = 32

_NUMBER_RE = re.compile(r"^[+-]?\d+(\.\d+)?$")
_SPACE_RE = re.compile(r"\s+")
_NOT_ALNUM_RE = re.compile(r"[\W_]+")
_TRAILING_PUNCTUATION = " .,;:"


class ExtractionMatchError(Exception):
    """Matching could not run at all, as opposed to a page matching badly."""


def extracted_claims(record: dict) -> tuple[dict[str, list[Any]], set[str]]:
    """What the record's `expected` says: ({ctdl property: [values]}, the
    properties it claims are not on the page).

    `expected` is a flat {ceterms property: value} object. Credits are read
    the way the baseline prints them, so a creditValue of 3 can satisfy a
    baseline creditMinValue of 3. A list-of-objects property keeps its
    dicts. A `null` value is the claim "not on the page"; a key left out
    is no claim. A record without `expected` has no values.
    """
    pool: dict[str, list[Any]] = {}
    nulls: set[str] = set()

    def add(prop: str, value: Any) -> None:
        pool.setdefault(prop, []).append(value)

    for prop, value in (record.get("expected") or {}).items():
        if value is None:
            nulls.add(prop)
            continue
        for item in value if isinstance(value, list) else [value]:
            _add_profile(prop, item, add)

    if record.get("source_url") and SUBJECT_WEBPAGE not in pool:
        add(SUBJECT_WEBPAGE, record["source_url"])
    if CREDIT_VALUE in nulls:
        nulls |= {CREDIT_MIN, CREDIT_MAX}
    return pool, {prop for prop in nulls if prop not in pool}


def extracted_values(record: dict) -> dict[str, list[Any]]:
    """What the record's `expected` says, as {ctdl property: [values]}."""
    return extracted_claims(record)[0]


def _add_profile(prop: str, item: Any, add) -> None:
    if not isinstance(item, dict):
        add(prop, item)
        if prop == CREDIT_VALUE:
            add(CREDIT_MIN, item)
            add(CREDIT_MAX, item)
        return
    if prop in OBJECT_KEYS:
        add(prop, item)
    elif prop == CREDIT_VALUE:
        for key, targets in CREDIT_PROFILE_KEYS.items():
            if item.get(key) is not None:
                for target in targets:
                    add(target, item[key])
    elif item.get(NAME) is not None:
        add(prop, item[NAME])


def as_number(value: Any) -> float | None:
    """The number a value prints, or None for text."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and _NUMBER_RE.match(value.strip()):
        return float(value.strip())
    return None


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    text = _SPACE_RE.sub(" ", text).strip()
    return text.rstrip(_TRAILING_PUNCTUATION)


def is_absent(field: dict) -> bool:
    """The golden data says the property is not on the page at all."""
    return field.get("absent") is True


def is_implied(field: dict) -> bool:
    """The golden value is implied, not printed on the page (location:
    null). An absent field is scored, whatever its location says."""
    return (
        not is_absent(field)
        and "location" in field
        and field["location"] is None
    )


def is_exact(baseline: Any, candidate: Any) -> bool:
    """Identical as printed. No case, spacing or punctuation leniency."""
    return baseline == candidate or str(baseline) == str(candidate)


def similarity(baseline: Any, candidate: Any) -> float:
    """0..1: how close one extracted value is to one baseline value.

    Numbers compare as numbers: 1.0 when equal, else 0.0. Text is scored
    with rapidfuzz `fuzz.ratio` (normalized Indel similarity,
    2 * LCS / (len(a) + len(b))) on the normalized values and on the
    same values with punctuation and spaces stripped, keeping the higher.
    Something against nothing (an object's missing field) is 0.0.
    """
    if baseline is None or candidate is None:
        return 1.0 if baseline is None and candidate is None else 0.0
    baseline_number = as_number(baseline)
    candidate_number = as_number(candidate)
    if baseline_number is not None and candidate_number is not None:
        return 1.0 if baseline_number == candidate_number else 0.0

    left, right = normalize(baseline), normalize(candidate)
    if left == right:
        return 1.0
    squashed = fuzz.ratio(
        _NOT_ALNUM_RE.sub("", left), _NOT_ALNUM_RE.sub("", right)
    )
    return max(fuzz.ratio(left, right), squashed) / 100


def object_key(prop: str, golden: dict) -> str | None:
    """The field this property's objects pair by."""
    if prop in OBJECT_KEYS:
        return OBJECT_KEYS[prop]
    if DESCRIPTION in golden:
        return DESCRIPTION
    return min(golden) if golden else None


def compare_objects(prop: str, golden: dict, candidate: Any) -> dict:
    """{field: {baseline, extracted, similarity, exact}} over the golden
    object's fields. A flat extracted value is read as the key field; a
    field the golden object lacks is not scored."""
    got = (
        candidate
        if isinstance(candidate, dict)
        else {object_key(prop, golden): candidate}
    )
    out = {}
    for name, want in golden.items():
        have = got.get(name)
        out[name] = {
            "baseline": want,
            "extracted": have,
            "similarity": round(similarity(want, have), 4),
            "exact": have is not None and is_exact(want, have),
        }
    return out


def outcome_for(mode: str, exact: bool, score: float) -> str:
    if mode == MODE_EXACT:
        return OUTCOME_MATCH if exact else OUTCOME_MISMATCH
    return OUTCOME_PARTIAL if score >= PARTIAL_THRESHOLD else OUTCOME_WRONG


def unit_outcome(exact: bool, score: float) -> str:
    """A paired unit's outcome, whichever the mode."""
    if exact:
        return OUTCOME_MATCH
    return OUTCOME_PARTIAL if score >= PARTIAL_THRESHOLD else OUTCOME_WRONG


class _AbsentClaim:
    """The record's null for a property: "not on the page"."""

    def __repr__(self) -> str:
        return "<absent claim>"


ABSENT_CLAIM = _AbsentClaim()


def compare(prop: str, golden: Any, candidate: Any) -> dict:
    """One possible pair: {exact, similarity, pairing, object_fields}.

    A value's similarity is also what it pairs by. An object pairs by its
    key field's similarity; its similarity is its worst field's, and it is
    exact only when every field is.
    """
    if isinstance(golden, dict):
        fields = compare_objects(prop, golden, candidate)
        if not fields:
            return {
                "exact": False,
                "similarity": 0.0,
                "pairing": 0.0,
                "object_fields": fields,
            }
        key = object_key(prop, golden)
        worst = min(f["similarity"] for f in fields.values())
        exact = all(f["exact"] for f in fields.values())
        return {
            "exact": exact,
            "similarity": 1.0 if exact else worst,
            "pairing": fields[key]["similarity"] if key in fields else worst,
            "object_fields": fields,
        }
    if isinstance(candidate, dict):  # an object where a value is due
        return {
            "exact": False,
            "similarity": 0.0,
            "pairing": 0.0,
            "object_fields": None,
        }
    exact = is_exact(golden, candidate)
    score = 1.0 if exact else similarity(golden, candidate)
    return {
        "exact": exact,
        "similarity": score,
        "pairing": score,
        "object_fields": None,
    }


def _unit_of(value: Any) -> str:
    if value is ABSENT_CLAIM:
        return UNIT_ABSENT
    return UNIT_OBJECT if isinstance(value, dict) else UNIT_VALUE


def _baseline_unit(field: dict) -> str:
    return UNIT_ABSENT if is_absent(field) else _unit_of(field["value"])


def match_entity(
    baseline_fields: list[dict], record: dict | None, mode: str
) -> dict:
    """Match one baseline entity against its record, or against nothing.

    Per property: an absent baseline field pairs with the record's null
    claim; exact pairs are taken next; what is left is paired by
    similarity, best pair first, so each extracted unit answers only one
    baseline unit. An unpaired baseline unit is missing, or unsure when it
    is absent and the record has no key for the property at all. An
    unpaired extracted unit of a property the entity covers is an extra.
    In partial mode the exact pairs are counted but left out of `fields`.
    Implied baseline fields are not scored, only counted.
    """
    skipped_implied = sum(1 for f in baseline_fields if is_implied(f))
    baseline_fields = [f for f in baseline_fields if not is_implied(f)]
    pool, absent = extracted_claims(record) if record else ({}, set())
    claimed = set(pool) | absent

    by_property: dict[str, list[int]] = {}
    for index, field in enumerate(baseline_fields):
        by_property.setdefault(field["ctdl_property"], []).append(index)

    results: list[dict | None] = [None] * len(baseline_fields)
    extras: list[dict] = []
    for prop, indexes in by_property.items():
        candidates: list[Any] = list(pool.get(prop) or [])
        if prop in absent:
            candidates.append(ABSENT_CLAIM)
        taken: set[int] = set()

        def take(
            i: int, j: int, pair: dict, taken=taken, candidates=candidates
        ) -> None:
            taken.add(j)
            results[i] = _field_result(
                baseline_fields[i], candidates[j], pair, mode
            )

        values = [i for i in indexes if not is_absent(baseline_fields[i])]
        real = [j for j, c in enumerate(candidates) if c is not ABSENT_CLAIM]
        claim = next(
            (j for j, c in enumerate(candidates) if c is ABSENT_CLAIM), None
        )
        for i in indexes:
            if claim is not None and claim not in taken and i not in values:
                take(i, claim, {"exact": True, "similarity": 1.0})

        pairs = {
            (i, j): compare(prop, baseline_fields[i]["value"], candidates[j])
            for i in values
            for j in real
        }
        for i in values:
            for j in real:
                if j not in taken and pairs[(i, j)]["exact"]:
                    take(i, j, pairs[(i, j)])
                    break

        ranked = sorted(
            (
                (pairs[(i, j)]["pairing"], pairs[(i, j)]["similarity"], i, j)
                for i in values
                if results[i] is None
                for j in real
                if j not in taken
            ),
            key=lambda pair: (-pair[0], -pair[1], pair[2], pair[3]),
        )
        for _, _, i, j in ranked:
            if results[i] is None and j not in taken:
                take(i, j, pairs[(i, j)])

        for i in indexes:
            if results[i] is None:
                unsure = (
                    record is not None
                    and is_absent(baseline_fields[i])
                    and prop not in claimed
                )
                results[i] = _missing_result(
                    baseline_fields[i],
                    OUTCOME_UNSURE if unsure else OUTCOME_MISSING,
                )
        extras += [
            _extra_result(prop, candidate)
            for j, candidate in enumerate(candidates)
            if j not in taken
        ]

    done = [r for r in results if r is not None]
    units = [
        {"ctdl_property": r["ctdl_property"], "outcome": r.pop("unit_outcome")}
        for r in done
    ] + [
        {"ctdl_property": e["ctdl_property"], "outcome": OUTCOME_EXTRA}
        for e in extras
    ]
    exact_count = sum(1 for r in done if r["exact"])
    fields = done
    if mode == MODE_PARTIAL:
        fields = [f for f in fields if not f["exact"]]
    for field in fields:
        del field["exact"]
    return {
        "record_id": record.get("record_id") if record else None,
        "fields": fields,
        "extras": extras,
        "units": units,
        "excluded_exact": exact_count if mode == MODE_PARTIAL else 0,
        "skipped_implied": skipped_implied,
        "unscored_extras": sorted(claimed - set(by_property)),
    }


def _field_result(field: dict, extracted: Any, pair: dict, mode: str) -> dict:
    exact, score = pair["exact"], pair["similarity"]
    result = {
        "ctdl_property": field["ctdl_property"],
        "unit": _baseline_unit(field),
        "baseline_value": field["value"],
        "extracted_value": None if extracted is ABSENT_CLAIM else extracted,
        "similarity": round(score, 4),
        "outcome": outcome_for(mode, exact, score),
        "unit_outcome": unit_outcome(exact, score),
        "exact": exact,
    }
    if pair.get("object_fields") is not None:
        result["object_fields"] = pair["object_fields"]
    return result


def _missing_result(field: dict, outcome: str) -> dict:
    return {
        "ctdl_property": field["ctdl_property"],
        "unit": _baseline_unit(field),
        "baseline_value": field["value"],
        "extracted_value": None,
        "similarity": None,
        "outcome": outcome,
        "unit_outcome": outcome,
        "exact": False,
    }


def _extra_result(prop: str, extracted: Any) -> dict:
    return {
        "ctdl_property": prop,
        "unit": _unit_of(extracted),
        "baseline_value": None,
        "extracted_value": None if extracted is ABSENT_CLAIM else extracted,
        "similarity": None,
        "outcome": OUTCOME_EXTRA,
    }


def baseline_entities(payload: object) -> list[list[dict]]:
    """Each entity's usable fields. Raises ValueError for a malformed file."""
    entities = [payload] if isinstance(payload, dict) else payload
    if not isinstance(entities, list) or not entities:
        raise ValueError("a baseline file is a non-empty list of entities")
    out: list[list[dict]] = []
    for entity in entities:
        fields = entity.get("fields") if isinstance(entity, dict) else None
        if not isinstance(fields, list) or not fields:
            raise ValueError("every baseline entity needs a list of fields")
        for field in fields:
            if (
                not isinstance(field, dict)
                or not field.get("ctdl_property")
                or "value" not in field
            ):
                raise ValueError(
                    "every baseline field needs ctdl_property and value"
                )
        out.append(fields)
    return out


def match_page(
    entities: list[list[dict]], records: list[dict], mode: str
) -> dict:
    """Pair baseline entities with the page's records and match each pair.

    The first baseline entity belongs to the page's own record and the rest to
    the extra-entity records, in record id order. An entity with no record
    left to pair with matches as all-missing.
    """
    return {
        "entities": [
            match_entity(
                fields, records[index] if index < len(records) else None, mode
            )
            for index, fields in enumerate(entities)
        ]
    }


def _counts(outcomes: tuple[str, ...], fields: list[dict]) -> dict[str, int]:
    return {
        outcome: sum(1 for f in fields if f["outcome"] == outcome)
        for outcome in outcomes
    }


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def unit_numbers(units: list[dict]) -> dict:
    """{golden, extracted, <each outcome>, found, right} of some units.

    golden = match + partial + wrong + missing + unsure; extracted = match
    + partial + wrong + extra; found (recall) = match / golden; right
    (precision) = match / extracted; None when there is nothing to divide.
    """
    counts = _counts(UNIT_OUTCOMES, units)
    golden = sum(counts[o] for o in UNIT_OUTCOMES if o != OUTCOME_EXTRA)
    extracted = sum(
        counts[o]
        for o in (OUTCOME_MATCH, OUTCOME_PARTIAL, OUTCOME_WRONG, OUTCOME_EXTRA)
    )
    return {
        "golden": golden,
        "extracted": extracted,
        **counts,
        "found": _ratio(counts[OUTCOME_MATCH], golden),
        "right": _ratio(counts[OUTCOME_MATCH], extracted),
    }


def _outlier_order(outlier: dict) -> tuple:
    similarity_ = outlier["similarity"]
    return (
        outlier["outcome"] != OUTCOME_MISSING,
        0.0 if similarity_ is None else similarity_,
        outlier["stem"],
        outlier["entity"],
        outlier["ctdl_property"],
    )


def _extra_order(extra: dict) -> tuple:
    return (
        extra["stem"],
        extra["entity"],
        extra["ctdl_property"],
        json.dumps(extra["extracted_value"], sort_keys=True, default=str),
    )


def summarize(
    *,
    mode: str,
    catalog_folder: str,
    run_id: str,
    pages: list[dict],
    out_of_scope: list[str],
    malformed: list[dict],
) -> dict:
    """The report: counts by outcome, by property and by page, then outliers.

    No score is averaged across pages or entities: `found`, `right` and
    `entities_exact` are ratios of counts summed over every entity
    (micro-averaged). `outliers` lists every field that is not an exact
    match, worst first, and `extras` every extracted unit with no partner,
    so problems surface instead of dissolving into a mean.
    """
    outcomes = MODE_OUTCOMES[mode]
    all_fields: list[dict] = []
    all_units: list[dict] = []
    by_property: dict[str, list[dict]] = {}
    units_by_property: dict[str, list[dict]] = {}
    exact_by_property: dict[str, list[bool]] = {}
    outliers: list[dict] = []
    extras: list[dict] = []
    page_rows: list[dict] = []
    excluded_exact = 0
    skipped_implied = 0
    entities = 0
    entities_exact = 0

    for page in pages:
        page_fields: list[dict] = []
        for index, entity in enumerate(page["entities"]):
            excluded_exact += entity["excluded_exact"]
            skipped_implied += entity["skipped_implied"]
            where = {
                "stem": page["stem"],
                "entity": index,
                "record_id": entity["record_id"],
            }
            for field in entity["fields"]:
                page_fields.append(field)
                by_property.setdefault(field["ctdl_property"], []).append(field)
                if field["outcome"] != OUTCOME_MATCH:
                    outliers.append({**where, **field})
            extras += [{**where, **extra} for extra in entity["extras"]]

            mine: dict[str, list[dict]] = {}
            for unit in entity["units"]:
                mine.setdefault(unit["ctdl_property"], []).append(unit)
            for prop, units in mine.items():
                units_by_property.setdefault(prop, []).extend(units)
                exact_by_property.setdefault(prop, []).append(
                    all(u["outcome"] == OUTCOME_MATCH for u in units)
                )
            if entity["units"]:
                all_units += entity["units"]
                entities += 1
                entities_exact += all(
                    u["outcome"] == OUTCOME_MATCH for u in entity["units"]
                )
        all_fields += page_fields
        counts = _counts(outcomes, page_fields)
        page_rows.append(
            {
                "stem": page["stem"],
                "status": page["status"],
                "fields": len(page_fields),
                "outcomes": counts,
                "not_exact": len(page_fields) - counts.get(OUTCOME_MATCH, 0),
            }
        )

    totals = unit_numbers(all_units)
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "mode": mode,
        "catalog_folder": catalog_folder,
        "run_id": run_id,
        "pages_scored": sum(1 for p in pages if p["status"] == STATUS_SCORED),
        "pages_skipped": sum(1 for p in pages if p["status"] == STATUS_SKIPPED),
        "pages_out_of_scope": len(out_of_scope),
        "fields_total": len(all_fields),
        "outcomes": _counts(outcomes, all_fields),
        "skipped_implied": skipped_implied,
    }
    if mode == MODE_EXACT:
        matched = report["outcomes"][OUTCOME_MATCH]
        report["exact_match_rate"] = (
            round(matched / len(all_fields), 4) if all_fields else None
        )
    else:
        report["partial_threshold"] = PARTIAL_THRESHOLD
        report["excluded_exact"] = excluded_exact

    def property_row(prop: str) -> dict:
        fields = by_property.get(prop, [])
        exact = exact_by_property.get(prop, [])
        return {
            "fields": len(fields),
            **_counts(outcomes, fields),
            **unit_numbers(units_by_property.get(prop, [])),
            "entities": len(exact),
            "entities_exact": _ratio(sum(exact), len(exact)),
        }

    report.update(
        {
            "units": totals,
            "found": totals["found"],
            "right": totals["right"],
            "unsure": totals[OUTCOME_UNSURE],
            "entities": entities,
            "entities_exact": _ratio(entities_exact, entities),
            "extras": {
                "count": len(extras),
                "outliers": sorted(extras, key=_extra_order),
            },
            "by_property": {
                prop: property_row(prop)
                for prop in sorted(set(by_property) | set(units_by_property))
            },
            "pages": sorted(
                page_rows, key=lambda p: (-p["not_exact"], p["stem"])
            ),
            "outliers": sorted(outliers, key=_outlier_order),
            "out_of_scope": sorted(out_of_scope),
            "malformed": sorted(malformed, key=lambda m: m["stem"]),
        }
    )
    return report


def match_extraction_run(
    records_store: object,
    baseline_store: object,
    catalog_folder: str,
    run_id: str,
    mode: str,
) -> dict:
    """Match every baseline page of one run against the records it wrote.

    A baseline page whose extract was considered but skipped is all missing,
    since that is an extractor miss. One never considered, outside discovery
    or outside --only-golden-sample, is listed and not counted.
    """
    baseline_stems = _baseline_stems(baseline_store, catalog_folder, run_id)
    if not baseline_stems:
        raise ExtractionMatchError(
            f"no baseline files for {catalog_folder} {run_id} in "
            f"{baseline_store.describe_location()}"
        )

    record_keys = _record_keys_by_stem(records_store, catalog_folder, run_id)
    skipped = _skipped_stems(records_store, catalog_folder, run_id)

    pages: list[dict] = []
    out_of_scope: list[str] = []
    malformed: list[dict] = []
    for stem, baseline_key in sorted(baseline_stems.items()):
        try:
            entities = baseline_entities(baseline_store.get_json(baseline_key))
        except (FileNotFoundError, ValueError) as exc:
            malformed.append({"stem": stem, "detail": str(exc)})
            continue

        keys = record_keys.get(stem)
        if keys:
            status = STATUS_SCORED
            records = [records_store.get_json(key) for key in keys]
        elif stem in skipped:
            status = STATUS_SKIPPED
            records = []
        else:
            out_of_scope.append(stem)
            continue
        pages.append(
            {
                "stem": stem,
                "status": status,
                **match_page(entities, records, mode),
            }
        )

    return summarize(
        mode=mode,
        catalog_folder=catalog_folder,
        run_id=run_id,
        pages=pages,
        out_of_scope=out_of_scope,
        malformed=malformed,
    )


def _baseline_stems(
    baseline_store: object, catalog_folder: str, run_id: str
) -> dict[str, str]:
    """{stem: key} for every <run>/<stem>/<stem>.json in the baseline store."""
    prefix = baseline_run_prefix(catalog_folder, run_id)
    stems: dict[str, str] = {}
    for key in baseline_store.list_keys(prefix):
        parts = key[len(prefix) + 1 :].split("/")
        if len(parts) == 2 and parts[1] == f"{parts[0]}.json":
            stems[parts[0]] = key
    return stems


def _record_keys_by_stem(
    records_store: object, catalog_folder: str, run_id: str
) -> dict[str, list[str]]:
    """Record keys per page, the page's own record first.

    A stem never holds two hyphens in a row, so the text before the first
    "--" is the page the record came from.
    """
    prefix = records_prefix(catalog_folder, run_id)
    by_stem: dict[str, list[str]] = {}
    for key in records_store.list_keys(prefix):
        name = key[len(prefix) + 1 :]
        if "/" in name or not name.endswith(".json"):
            continue
        by_stem.setdefault(name[: -len(".json")].split("--", 1)[0], []).append(
            key
        )
    # "--" sorts before ".", so a plain sort would put the extra-entity
    # records ahead of the page's own.
    return {
        stem: sorted(keys, key=lambda key: (key.count("--"), key))
        for stem, keys in by_stem.items()
    }


def _skipped_stems(
    records_store: object, catalog_folder: str, run_id: str
) -> set[str]:
    try:
        report = records_store.get_json(
            extract_report_key(catalog_folder, run_id)
        )
    except (FileNotFoundError, json.JSONDecodeError):
        return set()
    return {item["stem"] for item in report.get("skipped") or []}


def _clip(value: Any) -> str:
    text = " ".join(str(value).split())
    if len(text) > VALUE_WIDTH:
        text = text[: VALUE_WIDTH - 1] + "…"
    return text


def _rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _fraction(stats: dict, part: str, whole: str) -> str:
    return f"{stats[part]}/{stats[whole]}"


def format_table(report: dict) -> str:
    """The report as compact counts, found and right per property, and the
    worst outliers and extras, for a terminal."""
    mode = report["mode"]
    outcomes = MODE_OUTCOMES[mode]
    head = (
        f"Extraction match ({mode}): {report['fields_total']} fields, "
        + ", ".join(f"{report['outcomes'][o]} {o}" for o in outcomes)
    )
    if mode == MODE_EXACT:
        head += f"; exact match rate {_rate(report['exact_match_rate'])}"
    else:
        head += (
            f"; {report['excluded_exact']} exact set aside, "
            f"partial at {report['partial_threshold']} similarity"
        )
    units = report["units"]
    lines = [
        head,
        f"  found (recall) {_rate(report['found'])} = "
        f"{_fraction(units, 'match', 'golden')}, "
        f"right (precision) {_rate(report['right'])} = "
        f"{_fraction(units, 'match', 'extracted')}, "
        f"{report['extras']['count']} extra, {report['unsure']} unsure, "
        f"entities exact {_rate(report['entities_exact'])}",
        f"  {report['pages_scored']} scored, "
        f"{report['pages_skipped']} skipped, "
        f"{report['pages_out_of_scope']} out of scope, "
        f"{len(report['malformed'])} malformed, "
        f"{report['skipped_implied']} implied skipped",
        "",
        f"{'property':<36}{'fields':>7}"
        + "".join(f"{o:>10}" for o in outcomes)
        + f"{'extra':>8}{'found':>14}{'right':>14}",
    ]
    for prop, stats in report["by_property"].items():
        lines.append(
            f"{prop:<36}{stats['fields']:>7}"
            + "".join(f"{stats[o]:>10}" for o in outcomes)
            + f"{stats['extra']:>8}"
            + f"{_fraction(stats, 'match', 'golden'):>14}"
            + f"{_fraction(stats, 'match', 'extracted'):>14}"
        )
    outliers = report["outliers"]
    if outliers:
        lines += [
            "",
            f"Outliers, worst first ({min(len(outliers), OUTLIERS_SHOWN)} "
            f"of {len(outliers)}):",
        ]
        for item in outliers[:OUTLIERS_SHOWN]:
            sim = item["similarity"]
            lines.append(
                f"  {item['outcome']:<9}"
                f"{'-' if sim is None else f'{sim:.2f}':>5}  "
                f"{item['stem']}  {item['ctdl_property']}  "
                f"baseline={_clip(item['baseline_value'])}  "
                f"extracted={_clip(item['extracted_value'])}"
            )
    extras = report["extras"]["outliers"]
    if extras:
        lines += [
            "",
            f"Extras ({min(len(extras), OUTLIERS_SHOWN)} of {len(extras)}):",
        ]
        for item in extras[:OUTLIERS_SHOWN]:
            shown = (
                "(not on the page)"
                if item["unit"] == UNIT_ABSENT
                else _clip(item["extracted_value"])
            )
            lines.append(
                f"  {item['stem']}  {item['ctdl_property']}  extracted={shown}"
            )
    return "\n".join(lines)
