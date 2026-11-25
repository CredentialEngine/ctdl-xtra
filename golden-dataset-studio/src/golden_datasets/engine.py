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

from .model import key_rule_for, record_key

#: What a property rule reads: the course record (default), the whole page, the page URL, or another rule's output.
INPUTS = ("record", "page", "url", "rule")
SPLITS = ("elements", "separator", "regex")
_EMPTY = {"status": "empty", "value": None, "raw_text": None, "css_path": None, "char_start": None, "char_end": None}

_WS = re.compile(r"\s+")
_TRANSLATOR = HTMLTranslator()
_NOT_TEXT = (etree._Comment, etree._ProcessingInstruction, etree._Entity)
_NO_TEXT_TAGS = ("script", "style")  # their text isn't a value (G8)
_LABEL_END = ""
_TRANSFORMS = {
    "strip": str.strip,
    "collapse_ws": lambda value: _WS.sub(" ", value).strip(),
    "upper": str.upper,
    "lower": str.lower,
    "remove_spaces": lambda value: _WS.sub("", value),
}


def run_page(stem: str, url: str, html: bytes, rules: dict[str, dict], settings: dict, need: dict) -> dict:
    """Run what `need` asks for on one page.

    need = {"labels": bool, "matched": [page rule ids] | None (when labels aren't recomputed),
            "locators": [ids], "properties": [ids], "page_facts": bool}
    Returns {"page_labels", "occurrences", "matches", "facts"}."""
    page = _PageRun(stem, url, parse(html), rules, need)
    page.find_content_root(settings["content_root"])
    matched = page.label_page() if need["labels"] else list(need["matched"] or [])
    for locator_id in need["locators"]:
        page.run_locator(locator_id, matched)
    if need.get("page_facts"):
        page.out["facts"] = page.page_facts(settings)
    return page.out


class _PageRun:
    """One page's run: what it reads (document, content root, css paths) and the rows it gives."""

    def __init__(self, stem: str, url: str, doc, rules: dict[str, dict], need: dict):
        self.stem, self.url, self.doc, self.rules = stem, url, doc, rules
        self.wanted = set(need["properties"])
        self.root = None
        self.paths = Paths()
        self.found_blocks: dict[str, list] = {}
        self.out: dict = {"page_labels": [], "occurrences": [], "matches": [], "facts": None}

    def find_content_root(self, selector: str) -> None:
        roots = select(self.doc, selector, True)
        self.root = roots[0] if roots else None

    def label_page(self) -> list[str]:
        matched = []
        for rule_id, rule in sorted(self.rules.items()):
            if rule["kind"] != "page":
                continue
            reason = label_reason(rule["definition"], self.url, self.root)
            if reason == "matched":
                matched.append(rule_id)
            self.out["page_labels"].append(self.page_label(rule_id, rule, reason))
        return matched

    def run_locator(self, locator_id: str, matched: list[str]) -> None:
        locator = self.rules[locator_id]
        page_rule = next((p for p in locator["definition"].get("page_rules", []) if p in matched), None)
        if page_rule is None or self.root is None:
            return
        elements = locate(locator["definition"], self.root)
        self.found_blocks[locator_id] = elements
        code_rule, from_code = key_rule_for(locator_id, self.rules)
        order = property_order(self.rules, self.rules_to_run(locator_id, code_rule))
        page_out: dict[str, list[dict]] = {}  # input: page rules give one output per page
        for index, el in enumerate(elements):
            occ_path = self.paths(el)
            code_value = self.run_rules_on(el, occ_path, order, code_rule, page_out)
            self.out["occurrences"].append(self.occurrence(occ_path, page_rule, locator_id, index,
                                                           record_key(code_value, from_code)))

    def rules_to_run(self, locator_id: str, code_rule: str | None) -> list[str]:
        """The wanted rules, the key rule, and every rule they read."""
        properties = self.locator_properties(locator_id)
        to_run: set[str] = set()
        for rule_id in properties:
            if rule_id in self.wanted or rule_id == code_rule:
                self.add_with_parents(rule_id, to_run)
        return [rule_id for rule_id in properties if rule_id in to_run]

    def locator_properties(self, locator_id: str) -> list[str]:
        return [rule_id for rule_id, rule in self.rules.items() if rule["kind"] == "property"
                and rule["definition"]["locator"] == locator_id and rule["definition"].get("rule_type") != "none"]

    def add_with_parents(self, rule_id: str | None, to_run: set[str]) -> None:
        while rule_id and rule_id not in to_run and rule_id in self.rules:
            to_run.add(rule_id)
            rule_id = input_of(self.rules[rule_id]["definition"]).get("rule")

    def run_rules_on(self, el, occ_path: str, order: list[str], code_rule: str | None, page_out: dict) -> str | None:
        key = f"{self.stem}@{occ_path}"
        code_value = None
        found: dict[str, list[dict]] = {}
        for rule_id in order:
            results = self.run_rule(rule_id, el, occ_path, found, page_out)
            found[rule_id] = [r for r in results if r["status"] == "found"]
            if rule_id == code_rule and results[0]["status"] == "found":
                code_value = results[0]["value"]
            if rule_id in self.wanted:
                self.add_matches(rule_id, key, results)
        return code_value

    def run_rule(self, rule_id: str, el, occ_path: str, found: dict, page_out: dict) -> list[dict]:
        definition = self.rules[rule_id]["definition"]
        source = input_of(definition)
        if source["from"] != "page":
            return run_property(definition, el, self.url, self.paths, occ_path, found.get(source.get("rule")))
        if rule_id not in page_out:
            page_out[rule_id] = run_property(definition, self.doc, self.url, self.paths, occ_path)
        return [self.anchor_to_document(result) for result in page_out[rule_id]]

    def anchor_to_document(self, result: dict) -> dict:
        if result.get("_el") is None or result["css_path"] is None:
            return {**result}
        return {**result, "css_path": self.paths(result["_el"])}

    def add_matches(self, rule_id: str, key: str, results: list[dict]) -> None:
        for i, result in enumerate(results):
            self.out["matches"].append({"rule_id": rule_id, "rule_version": self.rules[rule_id]["version"],
                                        "occurrence_key": key, "value_index": i, "page_stem": self.stem,
                                        **public(result)})

    def page_label(self, rule_id: str, rule: dict, reason: str) -> dict:
        return {"page_stem": self.stem, "rule_id": rule_id, "rule_version": rule["version"],
                "matched": reason == "matched", "reason": reason}

    def occurrence(self, occ_path: str, page_rule: str, locator_id: str, index: int, external_id) -> dict:
        return {"occurrence_key": f"{self.stem}@{occ_path}", "page_stem": self.stem, "page_rule_id": page_rule,
                "locator_rule_id": locator_id, "locator_rule_version": self.rules[locator_id]["version"],
                "css_path": occ_path, "locator_index": index, "record_external_identifier": external_id}

    def page_facts(self, settings: dict):
        from .signals import page_facts

        return page_facts(self.stem, self.root, self.rules, settings, self.found_blocks, self.paths)


def run_property(definition: dict, el, url: str, paths: Paths, occ_path: str,
                 parent_out: list[dict] | None = None) -> list[dict]:
    """A property rule on one occurrence: one result per value (status found), or one result with status empty |
    no_match. Each result has value, raw_text, css_path (relative to the occurrence, or from the document root when
    the text is outside it), offsets, and private `_text` / `_el` for rules that read it (§4.2). A list of objects
    (`profile`, profiles_rule.py) gives one object per item; `absent_if` (absent.py) turns nothing found into the
    rule's "not on the page" claim (status absent); `fallback` (a definition of its own) is read when the rule finds
    nothing: the External Identifier a page prints, else one generated from the name (issue #368)."""
    if definition.get("fallback"):
        return _run_with_fallback(definition, el, url, paths, occ_path, parent_out)
    if definition.get("profile") or definition.get("absent_if"):
        return _run_profile_or_claim(definition, el, url, paths, occ_path, parent_out)
    constant = _constant(definition, url)
    if constant is not None:
        return constant
    if input_of(definition)["from"] == "rule" and not parent_out:
        return [dict(_EMPTY)]  # the parent found nothing here: nothing to read
    sources = _sources(definition, el, url, parent_out)
    if sources is None:
        return [{**_EMPTY, "status": "no_match"}]
    return _found_values(definition, sources, paths, occ_path) or [dict(_EMPTY)]


def values_of_text(definition: dict, text: str) -> list[str]:
    """What a rule gives for one text (a draft's examples): its values, in order (a list of objects: its objects)."""
    if definition.get("profile"):
        from .profiles_rule import values_of_text as objects

        return objects(definition, text)
    values = [value for raw, _ in _kept_pieces(definition, _Text(text)) if (value := _value_of(definition, raw))]
    return values if definition.get("multiple") else values[:1]


def public(res: dict) -> dict:
    return {k: v for k, v in res.items() if not k.startswith("_")}


def input_of(definition: dict) -> dict:
    return definition.get("input") or {"from": "record"}


def property_order(rules: dict[str, dict], ids: list[str]) -> list[str]:
    """Property rules, parents (their `input.rule`) before children, else by id."""
    order: dict[str, None] = {}
    for rule_id in sorted(ids):
        _visit_parents_first(rules, rule_id, (), order)
    return list(order)


def _visit_parents_first(rules: dict[str, dict], rule_id: str, stack: tuple, order: dict[str, None]) -> None:
    if rule_id in order:
        return
    if rule_id in stack:
        raise ValueError(f"input cycle through {rule_id}")
    parent = input_of(rules[rule_id]["definition"]).get("rule")
    if parent and parent in rules:
        _visit_parents_first(rules, parent, (*stack, rule_id), order)
    order[rule_id] = None


def _run_with_fallback(definition: dict, el, url: str, paths: Paths, occ_path: str,
                       parent_out: list[dict] | None) -> list[dict]:
    """The rule, else (when it finds nothing) its fallback: a code, else a generated id."""
    plain = {k: v for k, v in definition.items() if k != "fallback"}
    results = run_property(plain, el, url, paths, occ_path, parent_out)
    if _any_found(results):
        return results
    fallback = {"locator": definition.get("locator"), **definition["fallback"]}
    fallback_results = run_property(fallback, _fallback_element(fallback, el), url, paths, occ_path, parent_out)
    return fallback_results if _any_found(fallback_results) else results


def _fallback_element(fallback: dict, el):
    """A fallback that reads the whole page (a heading above the content root) reads it from the document."""
    if input_of(fallback)["from"] == "page" and el is not None:
        return el.getroottree().getroot()
    return el


def _any_found(results: list[dict]) -> bool:
    return any(r["status"] == "found" for r in results)


def _run_profile_or_claim(definition: dict, el, url: str, paths: Paths, occ_path: str,
                          parent_out: list[dict] | None) -> list[dict]:
    from . import absent, profiles_rule

    if definition.get("profile"):
        results = profiles_rule.run(definition, el, url, paths, occ_path, parent_out)
    else:
        plain = {k: v for k, v in definition.items() if k not in ("profile", "absent_if")}
        results = run_property(plain, el, url, paths, occ_path, parent_out)
    return absent.claim_or(definition, el, paths, occ_path, results)


def _constant(definition: dict, url: str) -> list[dict] | None:
    rule_type = definition["rule_type"]
    if rule_type == "constant":
        return [{**_EMPTY, "status": "found", "value": definition["value"], "raw_text": definition["value"]}]
    if rule_type == "source_url" and input_of(definition)["from"] == "record":
        return [{**_EMPTY, "status": "found", "value": url, "raw_text": url}]
    return None


def _found_values(definition: dict, sources: list[_Text], paths: Paths, occ_path: str) -> list[dict]:
    multiple = bool(definition.get("multiple"))
    found = []
    for source in sources:
        for raw, span in _kept_pieces(definition, source):
            value = _value_of(definition, raw)
            if not value:
                continue
            found.append(_found(value, raw, source, span, paths, occ_path))
            if not multiple:
                return found
    return found


def _found(value: str, raw: str, source: _Text, span, paths: Paths, occ_path: str) -> dict:
    location = source.location(paths, occ_path, span)
    return {"status": "found", "value": value, "raw_text": raw, **location,
            "_text": source.piece(raw, span), "_el": source.el}


def _kept_pieces(definition: dict, source: _Text) -> list[tuple[str, tuple[int, int] | None]]:
    keep = (definition.get("multiple") or {}).get("keep")
    return [(raw, span) for raw, span in _pieces(definition, source) if not keep or re.search(keep, raw.strip())]


def _sources(definition: dict, el, url: str, parent_out: list[dict] | None) -> list[_Text] | None:
    """The texts a rule reads, before its regex: one per element for `split: elements`, else one. None: the selector
    found nothing (no_match)."""
    source = input_of(definition)
    if source["from"] == "url":
        return [_Text(url)]
    if source["from"] == "rule":
        return _parent_sources(definition, source, url, parent_out)
    if definition["rule_type"] == "labelled":
        text = _labelled(definition, el)
        return [text] if text is not None else None
    targets = _targets(definition, el)
    if not targets:
        return None
    return _target_texts(definition, targets)


def _parent_sources(definition: dict, source: dict, url: str, parent_out: list[dict] | None) -> list[_Text]:
    if source.get("use") == "element":
        elements = [p["_el"] for p in parent_out or [] if p.get("_el") is not None]
        as_record = {**definition, "input": {"from": "record"}}
        return [text for e in elements for text in (_sources(as_record, e, url, None) or [])]
    return [p["_text"] for p in parent_out or [] if p.get("_text") is not None]


def _targets(definition: dict, el) -> list:
    selector = definition.get("selector")
    split = (definition.get("multiple") or {}).get("split")
    if selector and (split == "elements" or definition.get("join") is not None):
        return select(el, selector)
    target = select_one(el, selector) if selector else el
    return [target] if target is not None else []


def _target_texts(definition: dict, targets: list) -> list[_Text]:
    attribute = definition.get("attribute")
    if attribute:
        return [_Text(t.get(attribute) or "", t, offsets=False) for t in targets]
    texts = [_element_text(t) for t in targets]
    if definition.get("join") is None or len(texts) <= 1:
        return texts
    joined = definition["join"].join(x.text.strip() for x in texts if x.text.strip())
    return [_Text(joined, targets[0], offsets=False)]


def _labelled(definition: dict, el) -> _Text | None:
    """`rule_type: labelled` (G6): the text after the first element whose text starts with `label`, up to the next
    sibling named by `until` (a tag, default `br`, or a css selector) or the end of its parent. The text after a
    label is often a bare text node, which no selector reaches."""
    label = definition["label"].strip()
    for candidate in el.iter():
        if _is_label(candidate, el, label):
            return _text_after_label(candidate, definition.get("until") or "br")
    return None


def _is_label(candidate, el, label: str) -> bool:
    if candidate is el or not isinstance(candidate.tag, str) or candidate.getparent() is None:
        return False
    own = text_of(candidate)[0].strip()
    return own.startswith(label) and len(own) <= len(label) + 40


def _text_after_label(label_el, until: str) -> _Text:
    parent = label_el.getparent()
    start = _label_end(label_el)
    text, marks = text_of(parent)
    captured = (label_el.tail or "") + _siblings_until(label_el, until)
    return _Text(text[start:start + len(captured)], parent, marks, start)


def _label_end(label_el) -> int:
    """Where the label ends in its parent's text: found by marking its tail for a moment."""
    tail = label_el.tail
    label_el.tail = _LABEL_END + (tail or "")
    end = text_of(label_el.getparent())[0].index(_LABEL_END)
    label_el.tail = tail
    return end


def _siblings_until(label_el, until: str) -> str:
    is_tag = until.isalnum()
    captured = ""
    for sib in label_el.itersiblings():
        if isinstance(sib.tag, str) and (sib.tag == until if is_tag else select_one(sib, until, True) is not None):
            break
        captured += _sibling_text(sib) + (sib.tail or "")
    return captured


def _sibling_text(sib) -> str:
    if not isinstance(sib.tag, str) or sib.tag in _NO_TEXT_TAGS:
        return ""
    return "\n" if sib.tag == "br" else text_of(sib)[0]


def _pieces(definition: dict, source: _Text) -> list[tuple[str, tuple[int, int] | None]]:
    """(raw text, span in source) for each value one source gives: the regex match, or every split item."""
    multiple = definition.get("multiple") or {}
    if multiple.get("split") == "regex":
        return _regex_split(multiple["regex"], source)
    piece = _matched_piece(definition, source)
    if piece is None:
        return []
    if multiple.get("split") == "separator":
        return _separator_split(multiple.get("separator") or ",", *piece)
    return [piece]


def _regex_split(pattern: str, source: _Text) -> list[tuple[str, tuple[int, int] | None]]:
    pieces = []
    for match in re.finditer(pattern, source.text, re.MULTILINE):
        group = 1 if match.re.groups else 0
        if match.group(group) is not None:
            pieces.append((match.group(group), match.span(group) if source.offsets else None))
    return pieces


def _matched_piece(definition: dict, source: _Text) -> tuple[str, tuple[int, int] | None] | None:
    if not definition.get("regex"):
        return source.text, ((0, len(source.text)) if source.offsets else None)
    piece = _regex_group(definition, source.text)
    if piece is None or source.offsets:
        return piece
    return piece[0], None


def _separator_split(separator: str, raw: str, span) -> list[tuple[str, tuple[int, int] | None]]:
    parts = re.split(r"\n" if separator in ("newline", "\\n", "\n") else re.escape(separator), raw)
    pieces, at = [], 0
    for part in parts:
        i = raw.find(part, at)
        at = i + len(part)
        pieces.append((part, None if span is None else (span[0] + i, span[0] + i + len(part))))
    return pieces


def _regex_group(definition: dict, text: str) -> tuple[str, tuple[int, int]] | None:
    match = re.search(definition["regex"], text, re.MULTILINE)
    if not match:
        return None
    group = definition.get("group", 1 if match.re.groups else 0)
    if match.group(group) is None:
        return None
    return match.group(group), match.span(group)


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

    def piece(self, raw: str, span: tuple[int, int] | None) -> _Text:
        """The part of this text a value came from, for rules that read this rule's output."""
        if span is not None and self.offsets and self.el is not None:
            return _Text(raw, self.el, self.marks, self.base + span[0])
        return _Text(raw, self.el, offsets=False)


def _element_text(el) -> _Text:
    text, marks = text_of(el)
    return _Text(text, el, marks)


def label_reason(definition: dict, url: str, root) -> str:
    if "url_regex" in definition and not re.search(definition["url_regex"], url):
        return "url_mismatch"
    if "requires_selector" in definition and (root is None or select_one(root, definition["requires_selector"], True) is None):
        return "missing_required_element"
    if "forbids_selector" in definition and root is not None \
            and select_one(root, definition["forbids_selector"], True) is not None:
        return "forbidden_element_present"
    return "matched"


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


def passes_filter(repeat_filter: dict, el) -> bool:
    sel = repeat_filter.get("selector")
    target = select_one(el, sel) if sel else el
    return target is not None and bool(re.search(repeat_filter["regex"], text_of(target)[0], re.MULTILINE))


def extract_from_text(definition: dict, text: str) -> tuple[str | None, str | None, tuple[int, int] | None]:
    """Regex + group + transforms + map on already-selected text: (value, raw_text, span) or (None, None, None)."""
    raw, span = text, (0, len(text))
    if definition.get("regex"):
        piece = _regex_group(definition, text)
        if piece is None:
            return None, None, None
        raw, span = piece
    value = _value_of(definition, raw)
    return (value, raw, span) if value else (None, None, None)


def _value_of(definition: dict, raw: str) -> str:
    value = apply_transforms(raw, definition.get("transforms", []))
    if "map" in definition:
        value = definition["map"].get(value, "")
    return value


def apply_transforms(value: str, transforms: list[str]) -> str:
    for name in transforms:
        value = _transform(name, value)
    return value


def _transform(name: str, value: str) -> str:
    if name in _TRANSFORMS:
        return _TRANSFORMS[name](value)
    if name.startswith("rstrip:"):
        return value.rstrip(name[len("rstrip:"):])
    if name.startswith("generated_id:"):
        return generated_id(name[len("generated_id:"):], value)
    return value


def generated_id(kind: str, name: str) -> str:
    """Issue #368's External Identifier for a resource that prints none: `{type}-{normalized name}`, at most 100
    characters (`program`, "Anthropology, B.A." → `program-anthropology-b.a.`)."""
    slug = re.sub(r"[^a-z0-9.\s-]", "", name.lower())
    return f"{kind}-{'-'.join(slug.split())}"[:100].rstrip("-")


class Paths:
    """Document-root css paths, memoized per element (each is its parent's path plus one step)."""

    def __init__(self):
        self._memo: dict = {}

    def __call__(self, el) -> str:
        path = self._memo.get(el)
        if path is None:
            path = self._step_from_parent(el)
            self._memo[el] = path
        return path

    def _step_from_parent(self, el) -> str:
        parent = el.getparent()
        if parent is None:
            return el.tag
        n = 1 + sum(1 for sib in el.itersiblings(preceding=True) if sib.tag == el.tag)
        return f"{self(parent)} > {el.tag}:nth-of-type({n})"


def relative(occ_path: str, path: str) -> str:
    """A path relative to the occurrence; one outside it (a rule reading the whole page) stays a document-root path."""
    if path == occ_path:
        return ""
    if not path.startswith(occ_path + " > "):
        return path
    return path[len(occ_path) + 3:]


def text_of(el) -> tuple[str, list[tuple[int, int]]]:
    """v2's visible text of an element (a <br> reads as a newline; `script` and `style` text is left out, spec G8)
    and how its offsets differ from the DOM's textContent: [(position, delta)], in order. A br newline isn't in
    textContent (delta -1); left-out script text is (delta +its length)."""
    visible = _VisibleText()
    if el.text and not isinstance(el, _NOT_TEXT):
        visible.add(el.text)
    visible.read_children(el)
    return "".join(visible.parts), visible.marks


class _VisibleText:
    def __init__(self):
        self.parts: list[str] = []
        self.marks: list[tuple[int, int]] = []
        self.pos = 0

    def read_children(self, node) -> None:
        for child in node:
            self.read_child(child)
            if child.tail:
                self.add(child.tail)

    def read_child(self, child) -> None:
        if isinstance(child, _NOT_TEXT):
            return
        if child.tag == "br":
            self.marks.append((self.pos, -1))
            self.add("\n")
        elif child.tag in _NO_TEXT_TAGS:
            self.leave_out("".join(child.itertext()))
        else:
            if child.text:
                self.add(child.text)
            self.read_children(child)

    def add(self, text: str) -> None:
        self.parts.append(text)
        self.pos += len(text)

    def leave_out(self, hidden: str) -> None:
        if hidden:
            self.marks.append((self.pos, len(hidden)))


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


def parse(html: bytes | str):
    """The crawler saves every page as UTF-8. Without being told, libxml2 reads a page with no <meta charset>
    (Slate's) as ISO-8859-1, and "’" becomes "â\\x80\\x99"."""
    doc = lxml.html.document_fromstring(html, parser=lxml.html.HTMLParser(encoding="utf-8"))
    _html5_tables(doc)
    return doc


def select(el, selector: str, self_too: bool = False) -> list:
    return _xpath(selector, self_too)(el)


def select_one(el, selector: str, self_too: bool = False):
    found = _xpath(selector, self_too)(el)
    return found[0] if found else None


@lru_cache(maxsize=4096)
def _xpath(selector: str, self_too: bool) -> etree.XPath:
    prefix = "descendant-or-self::" if self_too else "descendant::"
    return etree.XPath(_TRANSLATOR.css_to_xpath(selector, prefix=prefix))


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
