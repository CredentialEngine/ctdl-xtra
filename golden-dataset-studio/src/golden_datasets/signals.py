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
    "empty": ("property", "high"),
    "no-match": ("property", "high"),
    "shape-outlier": ("property", "medium"),
    "length-outlier": ("property", "low"),
    "contains-label-text": ("property", "medium"),
    "duplicate-value": ("property", "low"),
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


# =====================================================================================================
# Extract-time signals
# =====================================================================================================
def compute(tables: dict, rules: dict, settings: dict, facts: list[dict], url_of: dict,
            old_page_signals: list[dict] | None) -> list[dict]:
    sig = thresholds(settings)
    occ_key = {o["occurrence_key"]: o["record_external_identifier"] for o in tables["occurrences"]}
    out = _property_signals(tables["matches"], rules, sig, occ_key) + _locator_signals(tables["occurrences"])
    # page signals need the parsed pages; they are copied from the parent when nothing they depend on changed
    if old_page_signals is not None:
        return out + list(old_page_signals)
    return out + _page_signals(tables, facts, url_of, sig)


def score(rows: list[dict]) -> tuple[int, int]:
    """(max severity, count) of a row's signals: the Rules tab's ordering key."""
    if not rows:
        return (0, 0)
    return (max(SEVERITY_RANK[r["severity"]] for r in rows), len(rows))


def _property_signals(matches: list[dict], rules: dict, sig: dict, occ_key: dict) -> list[dict]:
    """Value and cross-row signals of property rules."""
    by_rule = defaultdict(list)
    for m in matches:
        by_rule[m["rule_id"]].append(m)
    label_re = re.compile(sig["label_text_pattern"], re.I)
    out = []
    for rid, rows in by_rule.items():
        out += _status_signals(rid, rows)
        found = [r for r in rows if r["status"] == "found"]
        if found and rules[rid]["definition"]["rule_type"] not in DERIVED_RULE_TYPES:
            out += _value_signals(rid, found, sig, occ_key, label_re)
    return out


def _locator_signals(occurrences: list[dict]) -> list[dict]:
    per_page = Counter((o["page_stem"], o["record_external_identifier"], o["locator_rule_id"]) for o in occurrences)
    out = []
    for o in occurrences:
        key = o["record_external_identifier"]
        if key is None:
            out.append(_signal("occurrence", o["locator_rule_id"], o["occurrence_key"], o["page_stem"], "no-course-key",
                               "the Coded Notation rule found nothing in this course block"))
        elif (n := per_page[(o["page_stem"], key, o["locator_rule_id"])]) > 1:
            out.append(_signal("occurrence", o["locator_rule_id"], o["occurrence_key"], o["page_stem"],
                               "duplicate-occurrence", f"{key} occurs {n}× on this page"))
    return out


def _page_signals(tables: dict, facts: list[dict], url_of: dict, sig: dict) -> list[dict]:
    matched = defaultdict(set)
    for lb in tables["page_labels"]:
        if lb["matched"]:
            matched[lb["page_stem"]].add(lb["rule_id"])
    occ_count = Counter((o["page_stem"], o["locator_rule_id"]) for o in tables["occurrences"])
    allow = [re.compile(p) for p in sig["page_allow"]]
    out = []
    for f in facts:
        out += _unclassified_page(f, matched, url_of, allow, sig) + _block_count_mismatches(f, occ_count) \
            + _uncovered_codes(f)
    return out


def _status_signals(rid: str, rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        if r["status"] == "no_match":
            out.append(_signal("match", rid, r["occurrence_key"], r["page_stem"], "no-match",
                               "the selector matched no element", r["value_index"]))
        elif r["status"] == "empty":
            out.append(_signal("match", rid, r["occurrence_key"], r["page_stem"], "empty",
                               "the element is there but gives no value", r["value_index"]))
    return out


def _value_signals(rid: str, found: list[dict], sig: dict, occ_key: dict, label_re) -> list[dict]:
    stats = _value_stats(found, sig, occ_key)
    out = []
    for r in found:
        v, occ = r["value"], r["occurrence_key"]
        details = (("shape-outlier", _shape_outlier(v, stats, sig)), ("length-outlier", _length_outlier(v, stats, sig)),
                   ("duplicate-value", _duplicate_value(v, occ, stats, occ_key)),
                   ("contains-label-text", _label_text(v, label_re)))
        out += [_signal("match", rid, occ, r["page_stem"], name, detail, r["value_index"])
                for name, detail in details if detail]
    return out


def _value_stats(found: list[dict], sig: dict, occ_key: dict) -> dict:
    """A rule's found values at a glance: their shapes, length percentiles and the courses holding each value."""
    shapes = Counter(shape(r["value"]) for r in found)
    top_shape, top_n = shapes.most_common(1)[0]
    lens = sorted(len(r["value"]) for r in found)
    lo_p, hi_p = sig["length_outlier_percentiles"]
    by_value = defaultdict(set)
    for r in found:
        by_value[_norm(r["value"])].add(occ_key.get(r["occurrence_key"]))
    return {"n": len(found), "shapes": shapes, "top_shape": top_shape, "dominant": top_n / len(found) >= sig["shape_dominance"],
            "lens": lens, "lo_p": lo_p, "hi_p": hi_p, "lo": lens[max(0, int(len(lens) * lo_p / 100) - 1)],
            "hi": lens[min(len(lens) - 1, int(len(lens) * hi_p / 100))], "by_value": by_value}


def _shape_outlier(v: str, st: dict, sig: dict) -> str | None:
    s = shape(v)
    if st["dominant"] and st["shapes"][s] / st["n"] < sig["shape_outlier_max_share"]:
        return f"shape '{s}' is {st['shapes'][s]} of {st['n']} values; most common '{st['top_shape']}'"
    return None


def _length_outlier(v: str, st: dict, sig: dict) -> str | None:
    if len(st["lens"]) >= sig["length_outlier_min_rows"] and (len(v) < st["lo"] or len(v) > st["hi"]):
        return f"{len(v)} chars; {st['lo_p']}st–{st['hi_p']}th percentile is {st['lo']}–{st['hi']}"
    return None


def _duplicate_value(v: str, occ: str, st: dict, occ_key: dict) -> str | None:
    keys = st["by_value"][_norm(v)]
    if len(keys) <= 1:
        return None
    others = sorted(k for k in keys if k and k != occ_key.get(occ))
    return f"same value on {len(keys)} courses: " + ", ".join(others[:5]) + ("…" if len(others) > 5 else "")


def _label_text(v: str, label_re) -> str | None:
    lab = label_re.search(v)
    return f"value includes the label text '{lab.group(0).strip()}'" if lab else None


def _unclassified_page(f: dict, matched: dict, url_of: dict, allow: list, sig: dict) -> list[dict]:
    stem = f["stem"]
    if matched[stem] or len(f["codes"]) < sig["missed_page_min_codes"] \
            or any(a.search(url_of.get(stem, "")) for a in allow):
        return []
    return [_signal("page", None, None, stem, "unclassified-page-with-codes",
                    f"no page rule matched, but the page names {len(f['codes'])} course codes "
                    f"({', '.join(f['codes'][:4])}…): possible missed page")]


def _block_count_mismatches(f: dict, occ_count: Counter) -> list[dict]:
    out = []
    for loc_id, n in f["candidates"].items():
        got = occ_count[(f["stem"], loc_id)]
        if n != got and n > got:
            out.append(_signal("page", loc_id, None, f["stem"], "block-count-mismatch",
                               f"{n} blocks on the page name a course code, but this rule found {got}"))
    return out


def _uncovered_codes(f: dict) -> list[dict]:
    return [_signal("page", u["locator"], None, f["stem"], "uncovered-code",
                    f"'{u['code']}' in “{u['line']}” is outside every course this rule found: possible missed course",
                    where={"css_path": u["css_path"], "char_start": u["char_start"], "char_end": u["char_end"]})
            for u in f["uncovered"]]


def _signal(kind, rule_id, occ, page, name, detail, vi=None, where=None) -> dict:
    return {"target_kind": kind, "rule_id": rule_id, "occurrence_key": occ,
            "value_index": vi if kind == "match" else None, "page_stem": page, "signal": name,
            "severity": CATALOG[name][1], "detail": detail,
            **(where or {"css_path": None, "char_start": None, "char_end": None})}


# =====================================================================================================
# Page facts: gathered while the page is parsed (engine.run_page), used by the page and locator signals.
# =====================================================================================================
def page_facts(stem: str, root, rules: dict, settings: dict, found_blocks: dict[str, list], paths) -> dict:
    from .engine import text_of

    pattern = re.compile(thresholds(settings)["course_code_pattern"])
    facts = {"stem": stem, "has_content_root": root is not None, "codes": [], "uncovered": [], "candidates": {}}
    if root is None:
        return facts
    text, _ = text_of(root)
    facts["codes"] = sorted({re.sub(r"\s", "", c) for c in pattern.findall(text)})
    for loc_id, elements in found_blocks.items():
        d = rules[loc_id]["definition"]
        if d.get("repeat") and elements:
            _add_locator_facts(facts, loc_id, d, elements, root, pattern, paths)
    return facts


def _add_locator_facts(facts: dict, loc_id: str, d: dict, elements: list, root, pattern, paths) -> None:
    from .engine import select, text_of, to_text_content

    # block-count-mismatch: blocks the repeat selector finds that name a course code, vs occurrences kept.
    scope = root if not d.get("scope") else (select(root, d["scope"], True) or [None])[0]
    if scope is not None:
        cands = select(scope, d["repeat"], not d.get("scope"))
        facts["candidates"][loc_id] = sum(1 for c in cands if pattern.search(text_of(c)[0]))
    facts["uncovered"].extend(_uncovered(loc_id, elements, pattern, paths, text_of, to_text_content))


def _uncovered(loc_id: str, elements: list, pattern, paths, text_of, to_text_content) -> list[dict]:
    """Text that looks like a course code, inside the area where this locator found courses (their nearest common
    ancestor) but outside every found block: the `uncovered-code` signal."""
    chains = [list(e.iterancestors()) for e in elements]
    area = next((a for a in chains[0] if all(a in c for c in chains[1:])), None)
    if area is None:
        return []
    return [_uncovered_code(loc_id, m, parent, where, paths, text_of, to_text_content)
            for parent, where, s in _loose_text(area, set(elements)) for m in pattern.finditer(s)]


def _loose_text(area, found: set):
    """(parent element, where, text) of each text node in `area` outside the found blocks. Each text node is an
    element's .text or a child's .tail; its parent element is where it is shown."""
    from lxml import etree

    for el in area.iter():
        if isinstance(el, (etree._Comment, etree._ProcessingInstruction)):
            continue
        if el.text and not _inside_found(el, found, area):
            yield el, "text", el.text
        if el is not area and el.tail and not _inside_found(el.getparent(), found, area):
            yield el.getparent(), ("tail", el), el.tail


def _uncovered_code(loc_id: str, m, parent, where, paths, text_of, to_text_content) -> dict:
    full, brs = text_of(parent)
    start = _offset_in(parent, where, text_of)
    line = re.sub(r"\s+", " ", full).strip()
    return {"locator": loc_id, "code": m.group(0), "css_path": paths(parent),
            "char_start": to_text_content(start + m.start(), brs),
            "char_end": to_text_content(start + m.end(), brs), "line": line[:160]}


def _inside_found(el, found: set, area) -> bool:
    while el is not None:
        if el in found:
            return True
        if el is area:
            return False
        el = el.getparent()
    return False


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


# --- small helpers ---------------------------------------------------------------------------------
def thresholds(settings: dict) -> dict:
    return {**DEFAULTS, **(settings.get("signals") or {})}


def shape(value: str) -> str:
    return re.sub(r"\d+", "9", re.sub(r"[A-Za-z]+", "A", value))


def _norm(v: str) -> str:
    return re.sub(r"\s+", " ", v).strip().lower()
