"""The data model of spec §4: Parquet schemas, hashes, and rule / ruleset documents.

Keys (spec §4.2):
- `occurrence_key` = `<page_stem>@<css_path of the occurrence from the document root>`;
- matches store `css_path` relative to their occurrence ("" = the occurrence element itself);
- `course_key` (normalized code) lives only on occurrences; matches get it through a join;
- character offsets are positions in the element's DOM `textContent`.

`content_hash` = hash of a rule's own `definition` (its identity: decides version numbers and what an approval
refers to). `input_hash` = hash of the definition, its dependencies' input hashes and the ruleset's `content_root`
(decides what an extraction reruns and what it copies from its parent).
"""

from __future__ import annotations

import hashlib
import json
import re

import pyarrow as pa

KINDS = ("page", "locator", "field")
KIND_ORDER = {"page": 0, "locator": 1, "field": 2}

# The eight in-scope properties (spec §4.4), in display order.
PROPERTIES = [
    ("Coded Notation", "ceterms:codedNotation"),
    ("External Identifier", "ceterms:identifier"),
    ("Learning Opportunity Name", "ceterms:name"),
    ("Description", "ceterms:description"),
    ("Subject Webpage", "ceterms:subjectWebpage"),
    ("Learning Type", None),
    ("Life Cycle Status Type", "ceterms:lifeCycleStatusType"),
    ("Language", "ceterms:inLanguage"),
]
PROPERTY_ORDER = {label: i for i, (label, _) in enumerate(PROPERTIES)}
CTDL_TERM = dict(PROPERTIES)
DERIVED_RULE_TYPES = ("constant", "source_url")  # nothing is read from the page

PAGES = pa.schema([
    ("crawl", pa.string()), ("page_stem", pa.string()), ("url", pa.string()), ("requested_url", pa.string()),
    ("http_status", pa.int32()), ("retrieved_at", pa.string()), ("bytes", pa.int64()), ("sha256", pa.string()),
    ("html_path", pa.string()), ("title", pa.string()),
])
PAGE_LABELS = pa.schema([
    ("page_stem", pa.string()), ("rule_id", pa.string()), ("rule_version", pa.int32()),
    ("matched", pa.bool_()), ("reason", pa.string()),
])
OCCURRENCES = pa.schema([
    ("occurrence_key", pa.string()), ("page_stem", pa.string()), ("page_rule_id", pa.string()),
    ("locator_rule_id", pa.string()), ("locator_rule_version", pa.int32()), ("css_path", pa.string()),
    ("locator_index", pa.int32()), ("course_key", pa.string()),
])
MATCHES = pa.schema([
    ("rule_id", pa.string()), ("rule_version", pa.int32()), ("occurrence_key", pa.string()),
    ("value_index", pa.int32()), ("page_stem", pa.string()), ("status", pa.string()), ("value", pa.string()),
    ("raw_text", pa.string()), ("css_path", pa.string()), ("char_start", pa.int32()), ("char_end", pa.int32()),
])
SIGNALS = pa.schema([
    ("target_kind", pa.string()), ("rule_id", pa.string()), ("occurrence_key", pa.string()),
    ("value_index", pa.int32()), ("page_stem", pa.string()), ("signal", pa.string()), ("severity", pa.string()),
    ("detail", pa.string()), ("css_path", pa.string()), ("char_start", pa.int32()), ("char_end", pa.int32()),
])
ASSETS = pa.schema([
    ("crawl", pa.string()), ("url", pa.string()), ("final_url", pa.string()), ("status", pa.int32()),
    ("content_type", pa.string()), ("sha256", pa.string()), ("bytes", pa.int64()),
    ("referenced_by", pa.string()), ("fetched_at", pa.string()),
])
PAGE_ASSETS = pa.schema([
    ("crawl", pa.string()), ("page_stem", pa.string()), ("url", pa.string()), ("kind", pa.string()),
])
LINEAGE = pa.schema([
    ("publication", pa.string()), ("golden_record_id", pa.string()), ("page_stem", pa.string()), ("property", pa.string()),
    ("ctdl_property", pa.string()), ("value_index", pa.int32()), ("extraction", pa.string()),
    ("rule_id", pa.string()), ("rule_version", pa.int32()), ("occurrence_key", pa.string()),
    ("match_value_index", pa.int32()), ("annotation_ids", pa.list_(pa.string())),
    ("approval", pa.string()), ("approved_by", pa.string()), ("approved_at", pa.string()),
])
# One row per value of a golden dataset version (golden.parquet): what its page files hold, in one read (Evals §4.1).
GOLDEN = pa.schema([
    ("catalog", pa.string()), ("crawl", pa.string()), ("stem", pa.string()), ("golden_record_id", pa.string()),
    ("property", pa.string()), ("ctdl_property", pa.string()), ("value_index", pa.int32()), ("value", pa.string()),
    ("source_url", pa.string()),
    ("location", pa.struct([("css_path", pa.string()), ("char_start", pa.int32()), ("char_end", pa.int32())])),
    ("approval", pa.string()), ("approved_by", pa.string()), ("approved_at", pa.string()),
])
# One row per scored value of a score (scores.py): the golden value, the extracted value and the scorer's outcome, for
# the human-reviewed values (`basis` human) and for every rule-matched value (`basis` rule).
SCORE_VALUES = pa.schema([
    ("basis", pa.string()), ("column", pa.string()), ("ctdl_property", pa.string()), ("property", pa.string()),
    ("golden_record_id", pa.string()), ("page_stem", pa.string()), ("entity", pa.int32()),
    ("outcome", pa.string()), ("similarity", pa.float64()), ("golden_value", pa.string()),
    ("extracted_value", pa.string()), ("source_url", pa.string()), ("golden_css_path", pa.string()),
    ("golden_char_start", pa.int32()), ("golden_char_end", pa.int32()), ("approval", pa.string()),
    ("approved_by", pa.string()), ("approved_at", pa.string()),
])
TABLE_SCHEMAS = {"page_labels": PAGE_LABELS, "occurrences": OCCURRENCES, "matches": MATCHES, "signals": SIGNALS}
TABLE_SORT = {
    "page_labels": ("page_stem", "rule_id"),
    "occurrences": ("occurrence_key",),
    "matches": ("rule_id", "occurrence_key", "value_index"),
    "signals": ("target_kind", "rule_id", "occurrence_key", "page_stem", "signal", "css_path", "char_start"),
}


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(obj) -> str:
    return "sha256:" + hashlib.sha256(canon(obj).encode()).hexdigest()


def content_hash(rule: dict) -> str:
    return sha(rule["definition"])


def input_hashes(rules: dict[str, dict], content_root: str) -> dict[str, str]:
    """Per rule: definition + the input hashes of what it depends on + content_root (spec §4.3)."""
    out: dict[str, str] = {}

    def h(rid: str, stack: tuple = ()) -> str:
        if rid in out:
            return out[rid]
        if rid in stack:
            raise ValueError(f"dependency cycle through {rid}")
        r = rules[rid]
        deps = {d: h(d, (*stack, rid)) for d in sorted(dependencies(r))}
        out[rid] = sha({"definition": r["definition"], "deps": deps, "content_root": content_root})
        return out[rid]

    for rid in rules:
        h(rid)
    return out


def dependencies(rule: dict) -> list[str]:
    d = rule["definition"]
    if rule["kind"] == "locator":
        return list(d.get("page_rules") or [])
    if rule["kind"] == "field":
        return [d["locator"]]
    return []


def course_key(code: str | None) -> str | None:
    """'ABDY 113' and 'ABDY113' are the same course: spaces removed, upper case."""
    return re.sub(r"\s+", "", code).upper() if code else None


def ext_id(ruleset_version: int, suffix: str = "") -> str:
    return f"rs-{ruleset_version:04d}{suffix}"


def sort_rows(table: str, rows: list[dict]) -> list[dict]:
    cols = TABLE_SORT[table]
    return sorted(rows, key=lambda r: tuple("" if r.get(c) is None else str(r[c]).zfill(8) if isinstance(r.get(c), int)
                                            else r[c] for c in cols))


def code_rule_for(locator_id: str, rules: dict[str, dict], settings: dict) -> str | None:
    """The field rule whose value gives occurrences of this locator their course_key."""
    explicit = (settings.get("course_key_rule") or {}).get(locator_id)
    if explicit:
        return explicit
    for rid, r in sorted(rules.items()):
        if r["kind"] == "field" and r["definition"].get("locator") == locator_id \
                and r.get("ctdl_property") == "ceterms:codedNotation":
            return rid
    return None


def full_css_path(occ_path: str, rel: str | None) -> str | None:
    if rel is None:
        return None
    return f"{occ_path} > {rel}" if rel else occ_path


def stem_of(occurrence_key: str) -> str:
    return occurrence_key.split("@", 1)[0]
