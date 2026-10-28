"""Match extracted records against a baseline.

A baseline file is a list of entities, each a list of
{ctdl_property, value, source_url} fields. The script does not care whether
the baseline is verified; it only compares what was extracted with it.

Two modes, never blended:

- exact: a field matches only when the extracted value is identical to the
  baseline value. The share of exact matches is what extraction aims for.
- partial: the exact matches are set aside and only the rest is looked at,
  each by text similarity. A similarity of PARTIAL_THRESHOLD or more is
  partial, anything lower is wrong. This tells how much non-exactness the
  extractor shows, and exact matches cannot hide it.

- Text similarity - for similarity algorithm See `similarity()`.

Nothing is averaged. A report carries counts, and every field that is not
an exact match is listed in `outliers`, worst first.

A baseline field with `"location": null` is implied, not printed on the page.
It is counted under `skipped_implied` and never scored.

A property the extractor never emitted counts as missing, and a property the
baseline does not have is listed as an extra and never costs anything.
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

REPORT_SCHEMA = "xtra-extraction-match-report-1"

MODE_EXACT = "exact"
MODE_PARTIAL = "partial"
MODES = (MODE_EXACT, MODE_PARTIAL)

PARTIAL_THRESHOLD = 0.8

OUTCOME_MATCH = "match"
OUTCOME_MISMATCH = "mismatch"
OUTCOME_PARTIAL = "partial"
OUTCOME_WRONG = "wrong"
OUTCOME_MISSING = "missing"
MODE_OUTCOMES = {
    MODE_EXACT: (OUTCOME_MATCH, OUTCOME_MISMATCH, OUTCOME_MISSING),
    MODE_PARTIAL: (OUTCOME_PARTIAL, OUTCOME_WRONG, OUTCOME_MISSING),
}

STATUS_SCORED = "scored"
STATUS_SKIPPED = "skipped"

CREDIT_VALUE = "ceterms:creditValue"
CREDIT_MIN = "ceterms:creditMinValue"
CREDIT_MAX = "ceterms:creditMaxValue"
CREDIT_UNIT = "ceterms:creditUnitType"
SUBJECT_WEBPAGE = "ceterms:subjectWebpage"
NAME = "ceterms:name"

# How the keys of a nested creditValue profile read as baseline properties.
# A single printed credit is both the minimum and the maximum.
CREDIT_PROFILE_KEYS = {
    "ceterms:value": (CREDIT_MIN, CREDIT_MAX),
    "ceterms:minValue": (CREDIT_MIN,),
    "ceterms:maxValue": (CREDIT_MAX,),
    "ceterms:unitText": (CREDIT_UNIT,),
}

OUTLIERS_SHOWN = 20
VALUE_WIDTH = 32

_NUMBER_RE = re.compile(r"^[+-]?\d+(\.\d+)?$")
_SPACE_RE = re.compile(r"\s+")
_NOT_ALNUM_RE = re.compile(r"[\W_]+")
_TRAILING_PUNCTUATION = " .,;:"


class ExtractionMatchError(Exception):
    """Matching could not run at all, as opposed to a page matching badly."""


def extracted_values(record: dict) -> dict[str, list[Any]]:
    """What the record's `expected` says, as {ctdl property: [values]}.

    `expected` is a flat {ceterms property: value} object. Credits are read
    the way the baseline prints them, so a creditValue of 3 can satisfy a
    baseline creditMinValue of 3. A record without `expected` has no values.
    """
    pool: dict[str, list[Any]] = {}

    def add(prop: str, value: Any) -> None:
        pool.setdefault(prop, []).append(value)

    for prop, value in (record.get("expected") or {}).items():
        if value is None:
            continue
        for item in value if isinstance(value, list) else [value]:
            _add_profile(prop, item, add)

    if record.get("source_url") and SUBJECT_WEBPAGE not in pool:
        add(SUBJECT_WEBPAGE, record["source_url"])
    return pool


def _add_profile(prop: str, item: Any, add) -> None:
    if not isinstance(item, dict):
        add(prop, item)
        if prop == CREDIT_VALUE:
            add(CREDIT_MIN, item)
            add(CREDIT_MAX, item)
        return
    if prop == CREDIT_VALUE:
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


def is_implied(field: dict) -> bool:
    """The golden data says the value is not on the page (location: null)."""
    return "location" in field and field["location"] is None


def is_exact(baseline: Any, candidate: Any) -> bool:
    """Identical as printed. No case, spacing or punctuation leniency."""
    return baseline == candidate or str(baseline) == str(candidate)


def similarity(baseline: Any, candidate: Any) -> float:
    """0..1: how close one extracted value is to one baseline value.

    Numbers compare as numbers: 1.0 when equal, else 0.0. Text is scored
    with rapidfuzz `fuzz.ratio` (normalized Indel similarity,
    2 * LCS / (len(a) + len(b))) on the normalized values and on the
    same values with punctuation and spaces stripped, keeping the higher.
    """
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


def outcome_for(mode: str, exact: bool, score: float) -> str:
    if mode == MODE_EXACT:
        return OUTCOME_MATCH if exact else OUTCOME_MISMATCH
    return OUTCOME_PARTIAL if score >= PARTIAL_THRESHOLD else OUTCOME_WRONG


def match_entity(
    baseline_fields: list[dict], record: dict | None, mode: str
) -> dict:
    """Match one baseline entity against its record, or against nothing.

    Exact pairs are taken first. What is left is paired by similarity, best
    pair first, so each extracted value answers only one baseline value. In
    partial mode the exact pairs are counted but left out of `fields`.
    Implied baseline fields are not scored, only counted.
    """
    skipped_implied = sum(1 for f in baseline_fields if is_implied(f))
    baseline_fields = [f for f in baseline_fields if not is_implied(f)]
    pool =extracted_values(record) if record else {}

    by_property: dict[str, list[int]] = {}
    for index, field in enumerate(baseline_fields):
        by_property.setdefault(field["ctdl_property"], []).append(index)

    results: list[dict | None] = [None] * len(baseline_fields)
    for prop, indexes in by_property.items():
        candidates = pool.get(prop) or []
        taken_baseline: set[int] = set()
        taken_candidate: set[int] = set()

        for i in indexes:
            for j, candidate in enumerate(candidates):
                if j not in taken_candidate and is_exact(
                    baseline_fields[i]["value"], candidate
                ):
                    taken_baseline.add(i)
                    taken_candidate.add(j)
                    results[i] = _field_result(
                        baseline_fields[i], 1.0, candidate, True, mode
                    )
                    break

        pairs = sorted(
            (
                (similarity(baseline_fields[i]["value"], candidate), i, j)
                for i in indexes
                if i not in taken_baseline
                for j, candidate in enumerate(candidates)
                if j not in taken_candidate
            ),
            key=lambda pair: (-pair[0], pair[1], pair[2]),
        )
        for score, i, j in pairs:
            if i in taken_baseline or j in taken_candidate:
                continue
            taken_baseline.add(i)
            taken_candidate.add(j)
            results[i] = _field_result(
                baseline_fields[i], score, candidates[j], False, mode
            )

    exact_count = sum(1 for r in results if r and r["exact"])
    fields = [
        result or _missing_result(baseline_fields[i])
        for i, result in enumerate(results)
    ]
    if mode == MODE_PARTIAL:
        fields = [f for f in fields if not f["exact"]]
    for field in fields:
        del field["exact"]
    return {
        "record_id": record.get("record_id") if record else None,
        "fields": fields,
        "excluded_exact": exact_count if mode == MODE_PARTIAL else 0,
        "skipped_implied": skipped_implied,
        "unscored_extras": sorted(set(pool) - set(by_property)),
    }


def _field_result(
    field: dict, score: float, extracted: Any, exact: bool, mode: str
) -> dict:
    return {
        "ctdl_property": field["ctdl_property"],
        "baseline_value": field["value"],
        "extracted_value": extracted,
        "similarity": round(score, 4),
        "outcome": outcome_for(mode, exact, score),
        "exact": exact,
    }


def _missing_result(field: dict) -> dict:
    return {
        "ctdl_property": field["ctdl_property"],
        "baseline_value": field["value"],
        "extracted_value": None,
        "similarity": None,
        "outcome": OUTCOME_MISSING,
        "exact": False,
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


def _outlier_order(outlier: dict) -> tuple:
    similarity_ = outlier["similarity"]
    return (
        outlier["outcome"] != OUTCOME_MISSING,
        0.0 if similarity_ is None else similarity_,
        outlier["stem"],
        outlier["entity"],
        outlier["ctdl_property"],
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

    No score is averaged anywhere. `outliers` lists every field that is not
    an exact match, worst first, so problems surface instead of dissolving
    into a mean.
    """
    outcomes = MODE_OUTCOMES[mode]
    all_fields: list[dict] = []
    by_property: dict[str, list[dict]] = {}
    outliers: list[dict] = []
    page_rows: list[dict] = []
    excluded_exact = 0
    skipped_implied = 0

    for page in pages:
        page_fields: list[dict] = []
        for index, entity in enumerate(page["entities"]):
            excluded_exact += entity["excluded_exact"]
            skipped_implied += entity["skipped_implied"]
            for field in entity["fields"]:
                page_fields.append(field)
                by_property.setdefault(field["ctdl_property"], []).append(field)
                if field["outcome"] != OUTCOME_MATCH:
                    outliers.append(
                        {
                            "stem": page["stem"],
                            "entity": index,
                            "record_id": entity["record_id"],
                            **field,
                        }
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
    report.update(
        {
            "by_property": {
                prop: {"fields": len(fields), **_counts(outcomes, fields)}
                for prop, fields in sorted(by_property.items())
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


def format_table(report: dict) -> str:
    """The report as compact counts and the worst outliers, for a terminal."""
    mode = report["mode"]
    outcomes = MODE_OUTCOMES[mode]
    head = (
        f"Extraction match ({mode}): {report['fields_total']} fields, "
        + ", ".join(f"{report['outcomes'][o]} {o}" for o in outcomes)
    )
    if mode == MODE_EXACT:
        rate = report["exact_match_rate"]
        head += f"; exact match rate {'n/a' if rate is None else f'{rate:.4f}'}"
    else:
        head += (
            f"; {report['excluded_exact']} exact set aside, "
            f"partial at {report['partial_threshold']} similarity"
        )
    lines = [
        head,
        f"  {report['pages_scored']} scored, "
        f"{report['pages_skipped']} skipped, "
        f"{report['pages_out_of_scope']} out of scope, "
        f"{len(report['malformed'])} malformed, "
        f"{report['skipped_implied']} implied skipped",
        "",
        f"{'property':<36}{'fields':>7}"
        + "".join(f"{o:>10}" for o in outcomes),
    ]
    for prop, stats in report["by_property"].items():
        lines.append(
            f"{prop:<36}{stats['fields']:>7}"
            + "".join(f"{stats[o]:>10}" for o in outcomes)
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
    return "\n".join(lines)
