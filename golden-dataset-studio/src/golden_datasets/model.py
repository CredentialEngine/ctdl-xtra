"""The data model of spec §4: Parquet schemas, hashes, and rule / ruleset documents.

Keys (spec §4.2):
- `occurrence_key` = `<page_stem>@<css_path of the occurrence from the document root>`;
- matches store `css_path` relative to their occurrence ("" = the occurrence element itself);
- `record_external_identifier` (the record's External Identifier, issue #368) lives only on occurrences; matches
  get it through a join;
- character offsets are positions in the element's DOM `textContent`.

`content_hash` = hash of a rule's own `definition` (its identity: decides version numbers and what an approval
refers to). `input_hash` = hash of the definition, its dependencies' input hashes and the ruleset's `content_root`
(decides what an extraction reruns and what it copies from its parent).
"""

from __future__ import annotations

import functools
import hashlib
import json
import re

import pyarrow as pa

KINDS = ("page", "locator", "property")
KIND_ORDER = {"page": 0, "locator": 1, "property": 2}
#: Rule versions stored before the rename say "field"; they're immutable, so readers rename them (spec P13).
OLD_KINDS = {"field": "property"}

#: The eight properties the Studio started with (spec §4.4). Frozen: re-importing v2 must not bring in its other rules,
#: and publications from before the property list name only these (property-rules spec §3).
FIRST_EIGHT = [
    ("Coded Notation", "ceterms:codedNotation"),
    ("External Identifier", "ceterms:identifier"),
    ("Learning Opportunity Name", "ceterms:name"),
    ("Description", "ceterms:description"),
    ("Subject Webpage", "ceterms:subjectWebpage"),
    ("Learning Type", None),
    ("Life Cycle Status Type", "ceterms:lifeCycleStatusType"),
    ("Language", "ceterms:inLanguage"),
]


@functools.lru_cache(maxsize=16)
def _ordered(cls: str, mtime: float) -> tuple[dict, ...]:
    from . import properties

    rows = properties.active(cls)
    req = {p: i for i, p in enumerate(properties.required_order(cls))}
    return tuple(sorted(rows, key=lambda r: (0, req.get(r["path"], 99), r["sheet_row"]) if r["required"]
                        else (1 if properties.tier(r) == "phase1" else 2, 0, r["sheet_row"])))


def property_rows(cls: str = "course") -> tuple[dict, ...]:
    """A class's properties file in its fixed order (property-rules spec §4.8): Required first in the class's order,
    then Phase 1, then Phase 2, each in sheet order. (The Rules tab also sorts by human-reviewed counts, which change;
    this order doesn't.)"""
    from . import properties

    f = properties.file_of(cls)
    return _ordered(properties.classes.get(cls).slug, f.stat().st_mtime if f.exists() else 0.0)


def properties_of(cls: str = "course") -> list[tuple[str, str | None]]:
    """Every property of a class (label, path or None), in display order."""
    return [(r["label"], r["path"] or None) for r in property_rows(cls)]


def property_order(cls: str = "course") -> dict[str, int]:
    """label → its place in the class's order (cached: sort keys call it per row; don't change it)."""
    rows = property_rows(cls)
    got = _ORDERS.get(id(rows))
    if got is None or got[0] is not rows:
        got = _ORDERS[id(rows)] = (rows, {r["label"]: i for i, r in enumerate(rows)})
    return got[1]


_ORDERS: dict[int, tuple[tuple, dict[str, int]]] = {}  # property_rows' cached tuple → its order


def ctdl_term(cls: str = "course") -> dict[str, str | None]:
    return dict(properties_of(cls))


FIRST_EIGHT_ORDER = {label: i for i, (label, _) in enumerate(FIRST_EIGHT)}
DERIVED_RULE_TYPES = ("constant", "source_url")  # nothing is read from the page
#: A property rule's types (property-rules spec §4.3): `none` is a property with no rule yet (§4.6).
RULE_TYPES = ("css", "css+regex", "regex", "labelled", "constant", "source_url", "none")

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
    ("locator_index", pa.int32()), ("record_external_identifier", pa.string()),
])
MATCHES = pa.schema([
    ("rule_id", pa.string()), ("rule_version", pa.int32()), ("occurrence_key", pa.string()),
    ("value_index", pa.int32()), ("page_stem", pa.string()), ("status", pa.string()), ("value", pa.string()),
    ("raw_text", pa.string()), ("css_path", pa.string()), ("char_start", pa.int32()), ("char_end", pa.int32()),
    # a list-of-objects rule's object: each field's location, JSON (profiles_rule.py); null otherwise
    ("fields", pa.string()),
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


def current_kind(doc: dict) -> dict:
    """A rule (or a ruleset's rule entry) with its stored kind read in today's words."""
    if doc.get("kind") in OLD_KINDS:
        doc = {**doc, "kind": OLD_KINDS[doc["kind"]]}
    return doc


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
    if rule["kind"] == "property":
        parent = (d.get("input") or {}).get("rule")
        return [d["locator"], *([parent] if parent else [])]
    return []


def code_key(code: str | None) -> str | None:
    """'ABDY 113' and 'ABDY113' are the same course: spaces removed, upper case (issue #368's identifier from a
    printed code: `CHEM212A`)."""
    return re.sub(r"\s+", "", code).upper() if code else None


def record_key(value: str | None, from_code: bool) -> str | None:
    """A record's External Identifier (issue #368): its External Identifier rule's value as read (at most 100
    characters), or, read from a Coded Notation rule, the code without spaces in upper case."""
    if not value:
        return None
    return code_key(value) if from_code else " ".join(value.split())[:100] or None


def ext_id(ruleset_version: int, suffix: str = "") -> str:
    return f"rs-{ruleset_version:04d}{suffix}"


def sort_rows(table: str, rows: list[dict]) -> list[dict]:
    cols = TABLE_SORT[table]
    return sorted(rows, key=lambda r: tuple("" if r.get(c) is None else str(r[c]).zfill(8) if isinstance(r.get(c), int)
                                            else r[c] for c in cols))


def key_rule_for(locator_id: str, rules: dict[str, dict]) -> tuple[str | None, bool]:
    """The property rule whose value is the `record_external_identifier` of this locator's records, and whether it
    is a Coded Notation rule: the locator's External Identifier rule, else (none, or one with no rule yet) its Coded
    Notation rule."""
    on = sorted((rid, r) for rid, r in rules.items() if r["kind"] == "property"
                and r["definition"].get("locator") == locator_id and r["definition"].get("rule_type") != "none")
    for term, from_code in (("ceterms:identifier", False), ("ceterms:codedNotation", True)):
        rid = next((rid for rid, r in on if r.get("ctdl_property") == term), None)
        if rid:
            return rid, from_code
    return None, False


def full_css_path(occ_path: str, rel: str | None) -> str | None:
    """A match's document-root path. A value read outside its occurrence (input: page) keeps its own root path."""
    if rel is None:
        return None
    if rel == "html" or rel.startswith("html >"):
        return rel
    return f"{occ_path} > {rel}" if rel else occ_path


def stem_of(occurrence_key: str) -> str:
    return occurrence_key.split("@", 1)[0]
