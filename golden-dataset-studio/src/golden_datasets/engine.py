"""Run a ruleset's page rules, record locators and field rules on one saved page (spec §2, §4).

It keeps review-ui-v2's rule semantics (its `engine.py` is vendored as `v2engine.py` and checked against this one
on real pages by `tests/test_engine_equivalence.py`), with three differences the spec asks for:

- one parse with lxml of the **whole** page; no fragment re-parse;
- css paths are anchored at the **document root** (`html > body:nth-of-type(1) > …`), memoized per element, and
  resolve directly in the browser; a match's path is stored relative to its occurrence;
- character offsets are positions in the element's DOM **textContent**. Values keep v2's text (a `<br>` reads as a
  newline), so only the offsets are converted.

v2 evaluated selectors inside a `<div id="xtra-root">` wrapper holding a copy of the content root. The wrapper is
gone here, so the same selectors are evaluated from the content root with `descendant-or-self::` (what v2's
wrapper saw) and from any other element with `descendant::` (soupsieve never matches the element itself).
"""

from __future__ import annotations

import re
from functools import lru_cache

import lxml.html
from cssselect import HTMLTranslator
from lxml import etree

from .model import code_rule_for, course_key

_WS = re.compile(r"\s+")
_TRANSLATOR = HTMLTranslator()
_NOT_TEXT = (etree._Comment, etree._ProcessingInstruction, etree._Entity)


# --- parsing ----------------------------------------------------------------------------------------
def parse(html: bytes | str):
    doc = lxml.html.document_fromstring(html)
    _html5_tables(doc)
    return doc


def _html5_tables(doc) -> None:
    """Browsers put a table's direct <tr> children into an implied <tbody>; libxml2 doesn't. Do what the browser
    does, so css paths through tables resolve in the page pane. (Pages saved by Playwright already have it.)"""
    for table in doc.iter("table"):
        run: list = []
        for child in list(table):
            if getattr(child, "tag", None) == "tr":
                run.append(child)
                continue
            _wrap(table, run)
            run = []
        _wrap(table, run)


def _wrap(table, rows: list) -> None:
    if not rows:
        return
    tbody = etree.Element("tbody")
    table.insert(table.index(rows[0]), tbody)
    for r in rows:
        tbody.append(r)  # moves it (tail travels with it)


@lru_cache(maxsize=4096)
def _xpath(selector: str, self_too: bool) -> etree.XPath:
    prefix = "descendant-or-self::" if self_too else "descendant::"
    return etree.XPath(_TRANSLATOR.css_to_xpath(selector, prefix=prefix))


def select(el, selector: str, self_too: bool = False) -> list:
    return _xpath(selector, self_too)(el)


def select_one(el, selector: str, self_too: bool = False):
    found = _xpath(selector, self_too)(el)
    return found[0] if found else None


# --- text --------------------------------------------------------------------------------------------
def text_of(el) -> tuple[str, list[int]]:
    """v2's visible text of an element (a <br> reads as a newline) and the positions of those br newlines.

    textContent is the same string without the br newlines, so an offset `o` in it is `o - #brs before o`."""
    parts: list[str] = []
    brs: list[int] = []
    pos = 0

    def walk(node) -> None:
        nonlocal pos
        for child in node:
            if isinstance(child, _NOT_TEXT):
                pass
            elif child.tag == "br":
                brs.append(pos)
                parts.append("\n")
                pos += 1
            else:
                if child.text:
                    parts.append(child.text)
                    pos += len(child.text)
                walk(child)
            if child.tail:
                parts.append(child.tail)
                pos += len(child.tail)

    if el.text and not isinstance(el, _NOT_TEXT):
        parts.append(el.text)
        pos += len(el.text)
    walk(el)
    return "".join(parts), brs


def to_text_content(offset: int, brs: list[int]) -> int:
    import bisect

    return offset - bisect.bisect_left(brs, offset)


def text_content(el) -> str:
    text, brs = text_of(el)
    if not brs:
        return text
    return "".join(ch for i, ch in enumerate(text) if i not in set(brs))


# --- css paths ---------------------------------------------------------------------------------------
class Paths:
    """Document-root css paths, memoized per element (each is its parent's path plus one step)."""

    def __init__(self):
        self._memo: dict = {}

    def __call__(self, el) -> str:
        got = self._memo.get(el)
        if got is not None:
            return got
        parent = el.getparent()
        if parent is None:
            path = el.tag
        else:
            n = 1
            for sib in el.itersiblings(preceding=True):
                if sib.tag == el.tag:
                    n += 1
            path = f"{self(parent)} > {el.tag}:nth-of-type({n})"
        self._memo[el] = path
        return path


def relative(occ_path: str, path: str) -> str:
    if path == occ_path:
        return ""
    assert path.startswith(occ_path + " > "), (occ_path, path)
    return path[len(occ_path) + 3:]


# --- the v2 rule primitives ----------------------------------------------------------------------------
def apply_transforms(value: str, transforms: list[str]) -> str:
    for name in transforms:
        if name == "strip":
            value = value.strip()
        elif name == "collapse_ws":
            value = _WS.sub(" ", value).strip()
        elif name == "upper":
            value = value.upper()
        elif name == "lower":
            value = value.lower()
        elif name == "remove_spaces":
            value = _WS.sub("", value)
        elif name.startswith("rstrip:"):
            value = value.rstrip(name[len("rstrip:"):])
    return value


def extract_from_text(definition: dict, text: str) -> tuple[str | None, str | None, tuple[int, int] | None]:
    """Regex + group + transforms + map on already-selected text: (value, raw_text, span) or (None, None, None)."""
    raw, span = text, (0, len(text))
    pattern = definition.get("regex")
    if pattern:
        match = re.search(pattern, text, re.MULTILINE)
        if not match:
            return None, None, None
        group = definition.get("group", 1 if match.re.groups else 0)
        if match.group(group) is None:
            return None, None, None
        raw, span = match.group(group), match.span(group)
    value = apply_transforms(raw, definition.get("transforms", []))
    if "map" in definition:
        value = definition["map"].get(value, "")
    if not value:
        return None, None, None
    return value, raw, span


def label_reason(definition: dict, url: str, root) -> str:
    if "url_regex" in definition and not re.search(definition["url_regex"], url):
        return "url_mismatch"
    if "requires_selector" in definition and (root is None or select_one(root, definition["requires_selector"], True) is None):
        return "missing_required_element"
    if "forbids_selector" in definition and root is not None \
            and select_one(root, definition["forbids_selector"], True) is not None:
        return "forbidden_element_present"
    return "matched"


def passes_filter(repeat_filter: dict, el) -> bool:
    sel = repeat_filter.get("selector")
    target = select_one(el, sel) if sel else el
    return target is not None and bool(re.search(repeat_filter["regex"], text_of(target)[0], re.MULTILINE))


def locate(definition: dict, root) -> list:
    """The elements a record locator finds under the content root (scope, repeat, repeat_filter)."""
    if root is None:
        return []
    if definition.get("scope"):
        scope = select_one(root, definition["scope"], True)
        if scope is None:
            return []
        elements = select(scope, definition["repeat"]) if definition.get("repeat") else [scope]
    else:
        elements = select(root, definition["repeat"], True) if definition.get("repeat") else [root]
    if definition.get("repeat_filter"):
        elements = [e for e in elements if passes_filter(definition["repeat_filter"], e)]
    return elements


def run_field(definition: dict, el, url: str, paths: Paths, occ_path: str) -> dict:
    """status ∈ found | empty | no_match, value, raw_text, css_path (relative to the occurrence), offsets."""
    rtype = definition["rule_type"]
    out = {"status": "empty", "value": None, "raw_text": None, "css_path": None, "char_start": None, "char_end": None}
    if rtype == "constant":
        out.update(status="found", value=definition["value"], raw_text=definition["value"])
        return out
    if rtype == "source_url":
        out.update(status="found", value=url, raw_text=url)
        return out
    target = select_one(el, definition["selector"]) if definition.get("selector") else el
    if target is None:
        out["status"] = "no_match"
        return out
    text, brs = text_of(target)
    value, raw, span = extract_from_text(definition, text)
    if value is None:
        return out
    out.update(status="found", value=value, raw_text=raw, css_path=relative(occ_path, paths(target)),
               char_start=to_text_content(span[0], brs), char_end=to_text_content(span[1], brs))
    return out


# --- one page -------------------------------------------------------------------------------------------
def run_page(stem: str, url: str, html: bytes, rules: dict[str, dict], settings: dict, need: dict) -> dict:
    """Run what `need` asks for on one page.

    need = {"labels": bool, "matched": [page rule ids] | None (when labels aren't recomputed),
            "locators": [ids], "fields": [ids], "page_facts": bool}
    Returns {"page_labels", "occurrences", "matches", "facts"}."""
    doc = parse(html)
    roots = select(doc, settings["content_root"], True)
    root = roots[0] if roots else None
    paths = Paths()
    out: dict = {"page_labels": [], "occurrences": [], "matches": [], "facts": None}

    if need["labels"]:
        matched = []
        for rid, r in sorted(rules.items()):
            if r["kind"] != "page":
                continue
            reason = label_reason(r["definition"], url, root)
            if reason == "matched":
                matched.append(rid)
            out["page_labels"].append({"page_stem": stem, "rule_id": rid, "rule_version": r["version"],
                                       "matched": reason == "matched", "reason": reason})
    else:
        matched = list(need["matched"] or [])

    fields_wanted = set(need["fields"])
    found_blocks: dict[str, list] = {}
    for loc_id in need["locators"]:
        loc = rules[loc_id]
        page_rule = next((p for p in loc["definition"].get("page_rules", []) if p in matched), None)
        if page_rule is None or root is None:
            continue
        elements = locate(loc["definition"], root)
        found_blocks[loc_id] = elements
        code_rule = code_rule_for(loc_id, rules, settings)
        fields = sorted(f for f, r in rules.items() if r["kind"] == "field" and r["definition"]["locator"] == loc_id)
        for index, el in enumerate(elements):
            occ_path = paths(el)
            key = f"{stem}@{occ_path}"
            code_value = None
            for fid in fields:
                if fid not in fields_wanted and fid != code_rule:
                    continue
                res = run_field(rules[fid]["definition"], el, url, paths, occ_path)
                if fid == code_rule and res["status"] == "found":
                    code_value = res["value"]
                if fid in fields_wanted:
                    out["matches"].append({"rule_id": fid, "rule_version": rules[fid]["version"],
                                           "occurrence_key": key, "value_index": 0, "page_stem": stem, **res})
            out["occurrences"].append({"occurrence_key": key, "page_stem": stem, "page_rule_id": page_rule,
                                       "locator_rule_id": loc_id, "locator_rule_version": loc["version"],
                                       "css_path": occ_path, "locator_index": index,
                                       "course_key": course_key(code_value)})

    if need.get("page_facts"):
        from .signals import page_facts

        out["facts"] = page_facts(stem, root, rules, settings, found_blocks, paths)
    return out
