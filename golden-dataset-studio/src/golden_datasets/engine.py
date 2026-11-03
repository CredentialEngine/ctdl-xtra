"""Run a ruleset's page rules, record locators and property rules on one saved page (spec §2, §4).

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
_NO_TEXT_TAGS = ("script", "style")  # their text isn't a value (G8)


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
def text_of(el) -> tuple[str, list[tuple[int, int]]]:
    """v2's visible text of an element (a <br> reads as a newline; `script` and `style` text is left out, spec G8)
    and how its offsets differ from the DOM's textContent: [(position, delta)], in order. A br newline isn't in
    textContent (delta -1); left-out script text is (delta +its length)."""
    parts: list[str] = []
    marks: list[tuple[int, int]] = []
    pos = 0

    def walk(node) -> None:
        nonlocal pos
        for child in node:
            if isinstance(child, _NOT_TEXT):
                pass
            elif child.tag == "br":
                marks.append((pos, -1))
                parts.append("\n")
                pos += 1
            elif child.tag in _NO_TEXT_TAGS:
                hidden = "".join(child.itertext())
                if hidden:
                    marks.append((pos, len(hidden)))
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
    return "".join(parts), marks


def to_text_content(offset: int, marks: list[tuple[int, int]]) -> int:
    """An offset in text_of's text → the same place in textContent."""
    out = offset
    for pos, delta in marks:
        if pos > offset:
            break
        if delta > 0:
            out += delta
        elif pos < offset:
            out -= 1
    return out


def text_content(el) -> str:
    """The DOM's textContent (script text included)."""
    parts: list[str] = []

    def walk(node) -> None:
        for child in node:
            if not isinstance(child, _NOT_TEXT):
                if child.text:
                    parts.append(child.text)
                walk(child)
            if child.tail:
                parts.append(child.tail)

    if el.text and not isinstance(el, _NOT_TEXT):
        parts.append(el.text)
    walk(el)
    return "".join(parts)


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
    """A path relative to the occurrence; one outside it (a rule reading the whole page) stays a document-root path."""
    if path == occ_path:
        return ""
    if not path.startswith(occ_path + " > "):
        return path
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


# --- property rules (property-rules spec §4.2–§4.4) ----------------------------------------------------------
#: What a property rule reads: the course record (default), the whole page, the page URL, or another rule's output.
INPUTS = ("record", "page", "url", "rule")
SPLITS = ("elements", "separator", "regex")
_EMPTY = {"status": "empty", "value": None, "raw_text": None, "css_path": None, "char_start": None, "char_end": None}


def input_of(definition: dict) -> dict:
    return definition.get("input") or {"from": "record"}


def property_order(rules: dict[str, dict], ids: list[str]) -> list[str]:
    """Property rules, parents (their `input.rule`) before children, else by id."""
    out: list[str] = []
    seen: set[str] = set()

    def visit(rid: str, stack: tuple = ()) -> None:
        if rid in seen:
            return
        if rid in stack:
            raise ValueError(f"input cycle through {rid}")
        parent = input_of(rules[rid]["definition"]).get("rule")
        if parent and parent in rules:
            visit(parent, (*stack, rid))
        seen.add(rid)
        out.append(rid)

    for rid in sorted(ids):
        visit(rid)
    return out


class _Text:
    """Text read from the page, with where it came from (so a value's offsets point into the page)."""

    def __init__(self, text: str, el=None, marks=None, base: int = 0, offsets: bool = True):
        self.text, self.el, self.marks, self.base = text, el, marks or [], base
        self.offsets = offsets  # False: not page text (an attribute, joined text): the element only

    def location(self, paths: Paths, occ_path: str, span: tuple[int, int] | None) -> dict:
        if self.el is None:
            return {"css_path": None, "char_start": None, "char_end": None}
        if span is None or not self.offsets:
            return {"css_path": relative(occ_path, paths(self.el)), "char_start": None, "char_end": None}
        a, b = self.base + span[0], self.base + span[1]
        return {"css_path": relative(occ_path, paths(self.el)), "char_start": to_text_content(a, self.marks),
                "char_end": to_text_content(b, self.marks)}


def _element_text(el) -> _Text:
    text, marks = text_of(el)
    return _Text(text, el, marks)


def _sibling_text(sib) -> str:
    if not isinstance(sib.tag, str) or sib.tag in _NO_TEXT_TAGS:
        return ""
    return "\n" if sib.tag == "br" else text_of(sib)[0]


def _labelled(definition: dict, el) -> _Text | None:
    """`rule_type: labelled` (G6): the text after the first element whose text starts with `label`, up to the next
    sibling named by `until` (a tag, default `br`, or a css selector) or the end of its parent. The text after a
    label is often a bare text node, which no selector reaches."""
    label = definition["label"].strip()
    until = definition.get("until") or "br"
    is_tag = until.isalnum()
    for cand in el.iter():
        if cand is el or not isinstance(cand.tag, str) or cand.getparent() is None:
            continue
        own = text_of(cand)[0].strip()
        if not own.startswith(label) or len(own) > len(label) + 40:
            continue
        parent = cand.getparent()
        tail = cand.tail
        cand.tail = "\ue000" + (tail or "")  # where the label ends, in the parent's text
        pos = text_of(parent)[0].index("\ue000")
        cand.tail = tail
        text, marks = text_of(parent)
        captured = tail or ""
        for sib in cand.itersiblings():
            if isinstance(sib.tag, str) and (sib.tag == until if is_tag else select_one(sib, until, True) is not None):
                break
            captured += _sibling_text(sib) + (sib.tail or "")
        return _Text(text[pos:pos + len(captured)], parent, marks, pos)
    return None


def _sources(definition: dict, el, url: str, parent_out: list[dict] | None) -> list[_Text] | None:
    """The texts a rule reads, before its regex: one per element for `split: elements`, else one. None: the selector
    found nothing (no_match)."""
    inp = input_of(definition)
    if inp["from"] == "url":
        return [_Text(url)]
    if inp["from"] == "rule":
        if inp.get("use") == "element":
            els = [p["_el"] for p in parent_out or [] if p.get("_el") is not None]
            return [x for e in els for x in (_sources({**definition, "input": {"from": "record"}}, e, url, None) or [])]
        return [p["_text"] for p in parent_out or [] if p.get("_text") is not None]
    rtype = definition["rule_type"]
    if rtype == "labelled":
        t = _labelled(definition, el)
        return [t] if t is not None else None
    sel = definition.get("selector")
    split = (definition.get("multiple") or {}).get("split")
    if sel and (split == "elements" or definition.get("join") is not None):
        targets = select(el, sel)
    else:
        target = select_one(el, sel) if sel else el
        targets = [target] if target is not None else []
    if not targets:
        return None
    attr = definition.get("attribute")
    if attr:
        return [_Text(t.get(attr) or "", t, offsets=False) for t in targets]
    if definition.get("join") is not None:
        texts = [_element_text(t) for t in targets]
        joined = definition["join"].join(x.text.strip() for x in texts if x.text.strip())
        return [_Text(joined, targets[0], offsets=False)] if len(texts) > 1 else texts
    return [_element_text(t) for t in targets]


def _pieces(definition: dict, src: _Text) -> list[tuple[str, tuple[int, int] | None]]:
    """(raw text, span in src) for each value one source gives: the regex match, or every split item."""
    multiple = definition.get("multiple") or {}
    split = multiple.get("split")
    text = src.text
    pattern = definition.get("regex")
    joined = not src.offsets
    whole = None if joined else (0, len(text))
    if split == "regex":
        out = []
        for m in re.finditer(multiple["regex"], text, re.MULTILINE):
            g = 1 if m.re.groups else 0
            if m.group(g) is not None:
                out.append((m.group(g), None if joined else m.span(g)))
        return out
    if pattern:
        m = re.search(pattern, text, re.MULTILINE)
        if not m:
            return []
        g = definition.get("group", 1 if m.re.groups else 0)
        if m.group(g) is None:
            return []
        raw, span = m.group(g), (None if joined else m.span(g))
    else:
        raw, span = text, whole
    if split == "separator":
        sep = multiple.get("separator") or ","
        parts = re.split(r"\n" if sep in ("newline", "\\n", "\n") else re.escape(sep), raw)
        out, at = [], 0
        for part in parts:
            i = raw.find(part, at)
            at = i + len(part)
            out.append((part, None if span is None else (span[0] + i, span[0] + i + len(part))))
        return out
    return [(raw, span)]


def run_property(definition: dict, el, url: str, paths: Paths, occ_path: str,
                 parent_out: list[dict] | None = None) -> list[dict]:
    """A property rule on one occurrence: one result per value (status found), or one result with status empty |
    no_match. Each result has value, raw_text, css_path (relative to the occurrence, or from the document root when
    the text is outside it), offsets, and private `_text` / `_el` for rules that read it (§4.2)."""
    rtype = definition["rule_type"]
    if rtype == "constant":
        return [{**_EMPTY, "status": "found", "value": definition["value"], "raw_text": definition["value"]}]
    if rtype == "source_url" and input_of(definition)["from"] == "record":
        return [{**_EMPTY, "status": "found", "value": url, "raw_text": url}]
    if input_of(definition)["from"] == "rule" and not parent_out:
        return [dict(_EMPTY)]  # the parent found nothing here: nothing to read
    sources = _sources(definition, el, url, parent_out)
    if sources is None:
        return [{**_EMPTY, "status": "no_match"}]
    keep = (definition.get("multiple") or {}).get("keep")
    out = []
    for src in sources:
        for raw, span in _pieces(definition, src):
            if keep and not re.search(keep, raw.strip()):
                continue
            value = apply_transforms(raw, definition.get("transforms", []))
            if "map" in definition:
                value = definition["map"].get(value, "")
            if not value:
                continue
            loc = src.location(paths, occ_path, span)
            child = _Text(raw, src.el, src.marks, src.base + span[0]) if span is not None and src.offsets \
                and src.el is not None else _Text(raw, src.el, offsets=False)
            out.append({"status": "found", "value": value, "raw_text": raw, **loc, "_text": child, "_el": src.el})
            if not definition.get("multiple"):
                break
        if out and not definition.get("multiple"):
            break
    return out or [dict(_EMPTY)]


def values_of_text(definition: dict, text: str) -> list[str]:
    """What a rule gives for one text (a draft's examples): its values, in order."""
    keep = (definition.get("multiple") or {}).get("keep")
    out = []
    for raw, _ in _pieces(definition, _Text(text)):
        if keep and not re.search(keep, raw.strip()):
            continue
        value = apply_transforms(raw, definition.get("transforms", []))
        if "map" in definition:
            value = definition["map"].get(value, "")
        if value:
            out.append(value)
    return out if definition.get("multiple") else out[:1]


def public(res: dict) -> dict:
    return {k: v for k, v in res.items() if not k.startswith("_")}


# --- one page -------------------------------------------------------------------------------------------
def run_page(stem: str, url: str, html: bytes, rules: dict[str, dict], settings: dict, need: dict) -> dict:
    """Run what `need` asks for on one page.

    need = {"labels": bool, "matched": [page rule ids] | None (when labels aren't recomputed),
            "locators": [ids], "properties": [ids], "page_facts": bool}
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

    props_wanted = set(need["properties"])
    found_blocks: dict[str, list] = {}
    for loc_id in need["locators"]:
        loc = rules[loc_id]
        page_rule = next((p for p in loc["definition"].get("page_rules", []) if p in matched), None)
        if page_rule is None or root is None:
            continue
        elements = locate(loc["definition"], root)
        found_blocks[loc_id] = elements
        code_rule = code_rule_for(loc_id, rules, settings)
        props = [f for f, r in rules.items() if r["kind"] == "property" and r["definition"]["locator"] == loc_id
                 and r["definition"].get("rule_type") != "none"]
        # what has to run: the wanted rules, the code rule, and every rule they read (parents first)
        run: set[str] = set()
        for fid in props:
            if fid in props_wanted or fid == code_rule:
                while fid and fid not in run and fid in rules:
                    run.add(fid)
                    fid = input_of(rules[fid]["definition"]).get("rule")
        order = property_order(rules, [f for f in props if f in run])
        page_out: dict[str, list[dict]] = {}  # input: page rules give one output per page
        for index, el in enumerate(elements):
            occ_path = paths(el)
            key = f"{stem}@{occ_path}"
            code_value = None
            got: dict[str, list[dict]] = {}
            for fid in order:
                d = rules[fid]["definition"]
                frm = input_of(d)["from"]
                if frm == "page":
                    if fid not in page_out:
                        page_out[fid] = run_property(d, doc, url, paths, occ_path)
                    res = [{**r, "css_path": paths(r["_el"]) if r.get("_el") is not None and r["css_path"] is not None
                            else r["css_path"]} for r in page_out[fid]]
                else:
                    res = run_property(d, el, url, paths, occ_path, got.get(input_of(d).get("rule")))
                got[fid] = [r for r in res if r["status"] == "found"]
                if fid == code_rule and res[0]["status"] == "found":
                    code_value = res[0]["value"]
                if fid in props_wanted:
                    for i, r in enumerate(res):
                        out["matches"].append({"rule_id": fid, "rule_version": rules[fid]["version"],
                                               "occurrence_key": key, "value_index": i, "page_stem": stem,
                                               **public(r)})
            out["occurrences"].append({"occurrence_key": key, "page_stem": stem, "page_rule_id": page_rule,
                                       "locator_rule_id": loc_id, "locator_rule_version": loc["version"],
                                       "css_path": occ_path, "locator_index": index,
                                       "course_key": course_key(code_value)})

    if need.get("page_facts"):
        from .signals import page_facts

        out["facts"] = page_facts(stem, root, rules, settings, found_blocks, paths)
    return out
