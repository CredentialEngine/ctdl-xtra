"""Score extracted records against the verified golden sets.

A golden file is a list of entities, each a list of
{ctdl_property, value, source_url} fields. A record scores high when every
golden field appears in its ctdl_expected with an accurate value. The score
is recall over the golden fields, every field weighing the same: a property
the extractor never emitted counts as 0, and a property the golden set does
not have is listed as an extra and never costs anything.

Values are compared as printed. A controlled-vocabulary term and its label
(English and en) are not yet treated as equal.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from rapidfuzz import fuzz

from common.keys import (
    extract_report_key,
    golden_run_prefix,
    records_prefix,
)

REPORT_SCHEMA = "xtra-extraction-score-report-1"

MATCH_THRESHOLD = 0.95
PARTIAL_THRESHOLD = 0.6

OUTCOME_MATCH = "match"
OUTCOME_PARTIAL = "partial"
OUTCOME_WRONG = "wrong"
OUTCOME_MISSING = "missing"
OUTCOMES = (OUTCOME_MATCH, OUTCOME_PARTIAL, OUTCOME_WRONG, OUTCOME_MISSING)

STATUS_SCORED = "scored"
STATUS_SKIPPED = "skipped"

CREDIT_VALUE = "ceterms:creditValue"
CREDIT_MIN = "ceterms:creditMinValue"
CREDIT_MAX = "ceterms:creditMaxValue"
CREDIT_UNIT = "ceterms:creditUnitType"
SUBJECT_WEBPAGE = "ceterms:subjectWebpage"
NAME = "ceterms:name"

# How the keys of a nested creditValue profile read as golden properties.
# A single printed credit is both the minimum and the maximum.
CREDIT_PROFILE_KEYS = {
    "ceterms:value": (CREDIT_MIN, CREDIT_MAX),
    "ceterms:minValue": (CREDIT_MIN,),
    "ceterms:maxValue": (CREDIT_MAX,),
    "ceterms:unitText": (CREDIT_UNIT,),
}

WORST_PAGES_SHOWN = 10

_NUMBER_RE = re.compile(r"^[+-]?\d+(\.\d+)?$")
_SPACE_RE = re.compile(r"\s+")
_NOT_ALNUM_RE = re.compile(r"[\W_]+")
_TRAILING_PUNCTUATION = " .,;:"


class ExtractionScoreError(Exception):
    """Scoring could not run at all, as opposed to a page scoring low."""


def extracted_values(record: dict) -> dict[str, list[Any]]:
    """What the record says, as {ctdl property: [values]}.

    Nested profiles are read the way the golden set prints them, so a
    creditValue of 3 can satisfy a golden creditMinValue of 3.
    """
    pool: dict[str, list[Any]] = {}

    def add(prop: str, value: Any) -> None:
        pool.setdefault(prop, []).append(value)

    ctdl = record.get("ctdl_expected") or {}
    for entry in ctdl.get("properties") or []:
        prop = entry.get("property")
        value = entry.get("value")
        if not prop:
            continue
        if isinstance(value, list):
            for item in value:
                _add_profile(prop, item, add)
        else:
            add(prop, value)

    if record.get("source_url") and SUBJECT_WEBPAGE not in pool:
        add(SUBJECT_WEBPAGE, record["source_url"])
    return pool


def _add_profile(prop: str, item: Any, add) -> None:
    if not isinstance(item, dict):
        add(prop, item)
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


def value_score(golden: Any, candidate: Any) -> float:
    """0..1: how well one extracted value reproduces one golden value."""
    golden_number = as_number(golden)
    candidate_number = as_number(candidate)
    if golden_number is not None and candidate_number is not None:
        return 1.0 if golden_number == candidate_number else 0.0

    left, right = normalize(golden), normalize(candidate)
    if left == right:
        return 1.0
    squashed = fuzz.ratio(
        _NOT_ALNUM_RE.sub("", left), _NOT_ALNUM_RE.sub("", right)
    )
    return max(fuzz.ratio(left, right), squashed) / 100


def outcome_for(score: float) -> str:
    if score >= MATCH_THRESHOLD:
        return OUTCOME_MATCH
    if score >= PARTIAL_THRESHOLD:
        return OUTCOME_PARTIAL
    return OUTCOME_WRONG


def score_entity(golden_fields: list[dict], record: dict | None) -> dict:
    """Score one golden entity against its record, or against nothing."""
    pool = extracted_values(record) if record else {}

    by_property: dict[str, list[int]] = {}
    for index, field in enumerate(golden_fields):
        by_property.setdefault(field["ctdl_property"], []).append(index)

    results: list[dict | None] = [None] * len(golden_fields)
    for prop, indexes in by_property.items():
        candidates = pool.get(prop) or []
        pairs = sorted(
            (
                (value_score(golden_fields[i]["value"], candidate), i, j)
                for i in indexes
                for j, candidate in enumerate(candidates)
            ),
            key=lambda pair: (-pair[0], pair[1], pair[2]),
        )
        taken_golden: set[int] = set()
        taken_candidate: set[int] = set()
        for score, i, j in pairs:
            if i in taken_golden or j in taken_candidate:
                continue
            taken_golden.add(i)
            taken_candidate.add(j)
            results[i] = _field_result(
                golden_fields[i], score, candidates[j], outcome_for(score)
            )

    fields = [
        result or _field_result(golden_fields[i], 0.0, None, OUTCOME_MISSING)
        for i, result in enumerate(results)
    ]
    return {
        "record_id": record.get("record_id") if record else None,
        "score": _mean([f["score"] for f in fields]),
        "fields_total": len(fields),
        "by_outcome": {
            outcome: sum(1 for f in fields if f["outcome"] == outcome)
            for outcome in OUTCOMES
        },
        "fields": fields,
        "unscored_extras": sorted(set(pool) - set(by_property)),
    }


def _field_result(
    field: dict, score: float, extracted: Any, outcome: str
) -> dict:
    return {
        "ctdl_property": field["ctdl_property"],
        "golden_value": field["value"],
        "extracted_value": extracted,
        "score": round(score, 4),
        "outcome": outcome,
    }


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def golden_entities(payload: object) -> list[list[dict]]:
    """Each entity's usable fields. Raises ValueError for a malformed file."""
    entities = [payload] if isinstance(payload, dict) else payload
    if not isinstance(entities, list) or not entities:
        raise ValueError("a golden file is a non-empty list of entities")
    out: list[list[dict]] = []
    for entity in entities:
        fields = entity.get("fields") if isinstance(entity, dict) else None
        if not isinstance(fields, list) or not fields:
            raise ValueError("every golden entity needs a list of fields")
        for field in fields:
            if (
                not isinstance(field, dict)
                or not field.get("ctdl_property")
                or "value" not in field
            ):
                raise ValueError(
                    "every golden field needs ctdl_property and value"
                )
        out.append(fields)
    return out


def score_page(entities: list[list[dict]], records: list[dict]) -> dict:
    """Pair golden entities with the page's records and score each pair.

    The first golden entity belongs to the page's own record and the rest to
    the extra-entity records, in record id order. An entity with no record
    left to pair with scores as all-missing.
    """
    results = [
        score_entity(fields, records[index] if index < len(records) else None)
        for index, fields in enumerate(entities)
    ]
    fields = [f for result in results for f in result["fields"]]
    return {
        "score": _mean([f["score"] for f in fields]),
        "entities": results,
    }


def summarize(
    *,
    catalog_folder: str,
    run_id: str,
    pages: list[dict],
    out_of_scope: list[str],
    malformed: list[dict],
) -> dict:
    """The report: overall score, per-property accuracy, per-page detail.

    Each page weighs the same in the overall score. The by-property tallies
    count every golden field of every scored or skipped page.
    """
    by_property: dict[str, dict[str, Any]] = {}
    outcomes = dict.fromkeys(OUTCOMES, 0)
    for page in pages:
        for entity in page["entities"]:
            for field in entity["fields"]:
                stats = by_property.setdefault(
                    field["ctdl_property"],
                    {"fields": 0, "total": 0.0, **dict.fromkeys(OUTCOMES, 0)},
                )
                stats["fields"] += 1
                stats["total"] += field["score"]
                stats[field["outcome"]] += 1
                outcomes[field["outcome"]] += 1
    for stats in by_property.values():
        stats["score"] = round(stats.pop("total") / stats["fields"], 4)

    return {
        "schema": REPORT_SCHEMA,
        "catalog_folder": catalog_folder,
        "run_id": run_id,
        "overall": _mean([p["score"] for p in pages]) if pages else None,
        "pages_scored": sum(1 for p in pages if p["status"] == STATUS_SCORED),
        "pages_skipped": sum(1 for p in pages if p["status"] == STATUS_SKIPPED),
        "pages_out_of_scope": len(out_of_scope),
        "outcomes": outcomes,
        "by_property": dict(sorted(by_property.items())),
        "pages": sorted(pages, key=lambda p: (p["score"], p["stem"])),
        "out_of_scope": sorted(out_of_scope),
        "malformed": sorted(malformed, key=lambda m: m["stem"]),
    }


def score_extraction_run(
    records_store: object,
    golden_store: object,
    catalog_folder: str,
    run_id: str,
) -> dict:
    """Score every golden page of one run against the records it wrote.

    A golden page extract considered but skipped scores 0, since that is an
    extractor miss. One extract never considered, outside discovery or
    outside --only-golden-sample, is listed and left out of the mean.
    """
    golden_stems = _golden_stems(golden_store, catalog_folder, run_id)
    if not golden_stems:
        raise ExtractionScoreError(
            f"no golden files for {catalog_folder} {run_id} in "
            f"{golden_store.describe_location()}"
        )

    record_keys = _record_keys_by_stem(records_store, catalog_folder, run_id)
    skipped = _skipped_stems(records_store, catalog_folder, run_id)

    pages: list[dict] = []
    out_of_scope: list[str] = []
    malformed: list[dict] = []
    for stem, golden_key in sorted(golden_stems.items()):
        try:
            entities = golden_entities(golden_store.get_json(golden_key))
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
            {"stem": stem, "status": status, **score_page(entities, records)}
        )

    return summarize(
        catalog_folder=catalog_folder,
        run_id=run_id,
        pages=pages,
        out_of_scope=out_of_scope,
        malformed=malformed,
    )


def _golden_stems(
    golden_store: object, catalog_folder: str, run_id: str
) -> dict[str, str]:
    """{stem: key} for every <run>/<stem>/<stem>.json in the golden store."""
    prefix = golden_run_prefix(catalog_folder, run_id)
    stems: dict[str, str] = {}
    for key in golden_store.list_keys(prefix):
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


def format_table(report: dict) -> str:
    """The report as a compact table for a terminal."""
    overall = report["overall"]
    lines = [
        "Extraction score: "
        + ("n/a" if overall is None else f"{overall:.4f}")
        + f"  ({report['pages_scored']} scored, "
        f"{report['pages_skipped']} skipped, "
        f"{report['pages_out_of_scope']} out of scope, "
        f"{len(report['malformed'])} malformed)",
        "",
        f"{'property':<36}{'fields':>7}{'score':>8}"
        f"{'match':>7}{'partial':>9}{'wrong':>7}{'missing':>9}",
    ]
    for prop, stats in report["by_property"].items():
        lines.append(
            f"{prop:<36}{stats['fields']:>7}{stats['score']:>8.4f}"
            f"{stats[OUTCOME_MATCH]:>7}{stats[OUTCOME_PARTIAL]:>9}"
            f"{stats[OUTCOME_WRONG]:>7}{stats[OUTCOME_MISSING]:>9}"
        )
    if report["pages"]:
        lines += ["", f"Lowest scoring pages (up to {WORST_PAGES_SHOWN}):"]
        for page in report["pages"][:WORST_PAGES_SHOWN]:
            lines.append(
                f"  {page['score']:.4f}  {page['status']:<8} {page['stem']}"
            )
    return "\n".join(lines)
