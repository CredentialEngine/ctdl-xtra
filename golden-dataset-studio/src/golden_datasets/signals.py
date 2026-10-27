"""Uncertainty signals (spec §8): deterministic reasons to look at a match, an occurrence or a page.

Signals are computed, never entered by people, and never shown to Jared as tags. They order the rows of the Rules
tab, and their counts appear in Compare and in `rule try`.

- **Value, cross-row and page signals** are computed at extract time into `signals.parquet` (`compute`).
- **History signals** depend on the mutable annotation log and on the two versions being compared, so they are
  computed when read (`history`), never stored.

Thresholds live in the ruleset's `settings.signals`.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from .model import DERIVED_RULE_TYPES

SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}

DEFAULTS = {
    "course_code_pattern": r"\b[A-Z]{2,5} ?\d{3}[A-Z]?\b",
    "label_text_pattern": r"^\s*(Prerequisites?|Corequisites?|Advisory|Recommended Preparation|Units?|Description|Course)\s*:"
                          r"|\b(Prerequisites?|Corequisites?)\s*:",
    "shape_outlier_max_share": 0.02,
    "shape_dominance": 0.5,
    "length_outlier_percentiles": [1, 99],
    "length_outlier_min_rows": 50,
    "missed_page_min_codes": 5,
    "page_allow": [],
}

# signal → (applies to, severity), spec §8
CATALOG = {
    "empty": ("field", "high"),
    "no-match": ("field", "high"),
    "shape-outlier": ("field", "medium"),
    "length-outlier": ("field", "low"),
    "contains-label-text": ("field", "medium"),
    "duplicate-value": ("field", "low"),
    "no-course-key": ("locator", "high"),
    "duplicate-occurrence": ("locator", "high"),
    "block-count-mismatch": ("locator", "high"),
    "uncovered-code": ("locator", "high"),
    "unclassified-page-with-codes": ("page", "medium"),
    # history (read time)
    "previously-wrong": ("any", "high"),
    "previously-correct": ("any", "high"),
    "changed-since-correct": ("any", "high"),
    "new-in-version": ("any", "medium"),
    "vanished-in-version": ("any", "medium"),
}


def thresholds(settings: dict) -> dict:
    return {**DEFAULTS, **(settings.get("signals") or {})}


def shape(value: str) -> str:
    return re.sub(r"\d+", "9", re.sub(r"[A-Za-z]+", "A", value))


def _norm(v: str) -> str:
    return re.sub(r"\s+", " ", v).strip().lower()


# =====================================================================================================
# Page facts: gathered while the page is parsed (engine.run_page), used by the page and locator signals.
# =====================================================================================================
def page_facts(stem: str, root, rules: dict, settings: dict, found_blocks: dict[str, list], paths) -> dict:
    from .engine import select, text_of, to_text_content

    sig = thresholds(settings)
    pattern = re.compile(sig["course_code_pattern"])
    facts = {"stem": stem, "has_content_root": root is not None, "codes": [], "uncovered": [], "candidates": {}}
    if root is None:
        return facts
    text, _ = text_of(root)
    facts["codes"] = sorted({re.sub(r"\s", "", c) for c in pattern.findall(text)})
    for loc_id, elements in found_blocks.items():
        d = rules[loc_id]["definition"]
        if not d.get("repeat") or not elements:
            continue
        # block-count-mismatch: blocks the repeat selector finds that name a course code, vs occurrences kept.
        scope = root if not d.get("scope") else (select(root, d["scope"], True) or [None])[0]
        if scope is not None:
            cands = select(scope, d["repeat"], not d.get("scope"))
            facts["candidates"][loc_id] = sum(1 for c in cands if pattern.search(text_of(c)[0]))
        facts["uncovered"].extend(_uncovered(loc_id, elements, pattern, paths, text_of, to_text_content))
    return facts


def _uncovered(loc_id: str, elements: list, pattern, paths, text_of, to_text_content) -> list[dict]:
    """Text that looks like a course code, inside the area where this locator found courses (their nearest common
    ancestor) but outside every found block: the `uncovered-code` signal."""
    from lxml import etree

    found = set(elements)
    chains = [list(e.iterancestors()) for e in elements]
    area = next((a for a in chains[0] if all(a in c for c in chains[1:])), None)
    if area is None:
        return []
    out = []

    def inside_found(el) -> bool:
        while el is not None:
            if el in found:
                return True
            if el is area:
                return False
            el = el.getparent()
        return False

    # Each text node is an element's .text or a child's .tail; its parent element is where it is shown.
    for el in area.iter():
        if isinstance(el, (etree._Comment, etree._ProcessingInstruction)):
            continue
        pieces = []
        if el.text and not inside_found(el):
            pieces.append((el, "text", el.text))
        if el is not area and el.tail and not inside_found(el.getparent()):
            pieces.append((el.getparent(), ("tail", el), el.tail))
        for parent, where, s in pieces:
            for m in pattern.finditer(s):
                full, brs = text_of(parent)
                start = _offset_in(parent, where, text_of)
                line = re.sub(r"\s+", " ", full).strip()
                out.append({"locator": loc_id, "code": m.group(0), "css_path": paths(parent),
                            "char_start": to_text_content(start + m.start(), brs),
                            "char_end": to_text_content(start + m.end(), brs), "line": line[:160]})
    return out


def _offset_in(parent, where, text_of) -> int:
    """Offset (in v2 text of `parent`) where a text node starts: its .text, or a child's .tail."""
    if where == "text":
        return 0
    child = where[1]
    pos = len(parent.text or "")
    for c in parent:
        pos += 1 if c.tag == "br" else len(text_of(c)[0])
        if c is child:
            return pos
        pos += len(c.tail or "")
    return pos


# =====================================================================================================
# Extract-time signals
# =====================================================================================================
def compute(tables: dict, rules: dict, settings: dict, facts: list[dict], url_of: dict,
            old_page_signals: list[dict] | None) -> list[dict]:
    sig = thresholds(settings)
    out: list[dict] = []
    occ_key = {o["occurrence_key"]: o["course_key"] for o in tables["occurrences"]}

    def add(kind, rule_id, occ, page, name, detail, vi=None, where=None):
        out.append({"target_kind": kind, "rule_id": rule_id, "occurrence_key": occ,
                    "value_index": vi if kind == "match" else None, "page_stem": page, "signal": name,
                    "severity": CATALOG[name][1], "detail": detail,
                    **(where or {"css_path": None, "char_start": None, "char_end": None})})

    # -- field rules: value + cross-row signals --------------------------------------------------------
    by_rule = defaultdict(list)
    for m in tables["matches"]:
        by_rule[m["rule_id"]].append(m)
    label_re = re.compile(sig["label_text_pattern"], re.I)
    for rid, rows in by_rule.items():
        derived = rules[rid]["definition"]["rule_type"] in DERIVED_RULE_TYPES
        for r in rows:
            if r["status"] == "no_match":
                add("match", rid, r["occurrence_key"], r["page_stem"], "no-match", "the selector matched no element",
                    r["value_index"])
            elif r["status"] == "empty":
                add("match", rid, r["occurrence_key"], r["page_stem"], "empty", "the element is there but gives no value",
                    r["value_index"])
        found = [r for r in rows if r["status"] == "found"]
        if derived or not found:
            continue
        shapes = Counter(shape(r["value"]) for r in found)
        top_shape, top_n = shapes.most_common(1)[0]
        dominant = top_n / len(found) >= sig["shape_dominance"]
        lens = sorted(len(r["value"]) for r in found)
        lo_p, hi_p = sig["length_outlier_percentiles"]
        lo = lens[max(0, int(len(lens) * lo_p / 100) - 1)]
        hi = lens[min(len(lens) - 1, int(len(lens) * hi_p / 100))]
        by_value = defaultdict(set)
        for r in found:
            by_value[_norm(r["value"])].add(occ_key.get(r["occurrence_key"]))
        for r in found:
            v, occ, page, vi = r["value"], r["occurrence_key"], r["page_stem"], r["value_index"]
            if dominant and shapes[shape(v)] / len(found) < sig["shape_outlier_max_share"]:
                add("match", rid, occ, page, "shape-outlier",
                    f"shape '{shape(v)}' is {shapes[shape(v)]} of {len(found)} values; most common '{top_shape}'", vi)
            if len(lens) >= sig["length_outlier_min_rows"] and (len(v) < lo or len(v) > hi):
                add("match", rid, occ, page, "length-outlier", f"{len(v)} chars; {lo_p}st–{hi_p}th percentile is {lo}–{hi}",
                    vi)
            keys = by_value[_norm(v)]
            if len(keys) > 1:
                others = sorted(k for k in keys if k and k != occ_key.get(occ))
                add("match", rid, occ, page, "duplicate-value",
                    f"same value on {len(keys)} courses: " + ", ".join(others[:5]) + ("…" if len(others) > 5 else ""), vi)
            lab = label_re.search(v)
            if lab:
                add("match", rid, occ, page, "contains-label-text", f"value includes the label text '{lab.group(0).strip()}'",
                    vi)

    # -- record locators -------------------------------------------------------------------------------
    per_page = Counter((o["page_stem"], o["course_key"], o["locator_rule_id"]) for o in tables["occurrences"])
    for o in tables["occurrences"]:
        if o["course_key"] is None:
            add("occurrence", o["locator_rule_id"], o["occurrence_key"], o["page_stem"], "no-course-key",
                "the Coded Notation rule found nothing in this course block")
        else:
            n = per_page[(o["page_stem"], o["course_key"], o["locator_rule_id"])]
            if n > 1:
                add("occurrence", o["locator_rule_id"], o["occurrence_key"], o["page_stem"], "duplicate-occurrence",
                    f"{o['course_key']} occurs {n}× on this page")

    # -- page signals (need the parsed pages; copied from the parent when nothing they depend on changed) -------
    if old_page_signals is not None:
        out.extend(old_page_signals)
        return out
    matched = defaultdict(set)
    for lb in tables["page_labels"]:
        if lb["matched"]:
            matched[lb["page_stem"]].add(lb["rule_id"])
    occ_count = Counter((o["page_stem"], o["locator_rule_id"]) for o in tables["occurrences"])
    allow = [re.compile(p) for p in sig["page_allow"]]
    for f in facts:
        stem = f["stem"]
        if not matched[stem] and len(f["codes"]) >= sig["missed_page_min_codes"] \
                and not any(a.search(url_of.get(stem, "")) for a in allow):
            add("page", None, None, stem, "unclassified-page-with-codes",
                f"no page rule matched, but the page names {len(f['codes'])} course codes "
                f"({', '.join(f['codes'][:4])}…): possible missed page")
        for loc_id, n in f["candidates"].items():
            got = occ_count[(stem, loc_id)]
            if n != got and n > got:
                add("page", loc_id, None, stem, "block-count-mismatch",
                    f"{n} blocks on the page name a course code, but this rule found {got}")
        for u in f["uncovered"]:
            add("page", u["locator"], None, stem, "uncovered-code",
                f"'{u['code']}' in “{u['line']}” is outside every course this rule found: possible missed course",
                where={"css_path": u["css_path"], "char_start": u["char_start"], "char_end": u["char_end"]})
    return out


def score(rows: list[dict]) -> tuple[int, int]:
    """(max severity, count) of a row's signals: the Rules tab's ordering key."""
    if not rows:
        return (0, 0)
    return (max(SEVERITY_RANK[r["severity"]] for r in rows), len(rows))
