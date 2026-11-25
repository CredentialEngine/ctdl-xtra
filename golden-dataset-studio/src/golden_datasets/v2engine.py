"""Vendored, unmodified copy of review-ui-v2/server/review_ui/engine.py (branch review-ui-v2-vscode-79248126).

Used only by tests/test_engine_equivalence.py, which checks the Studio engine against v2 on real pages. Only the
import of ROOT_ID changed (it came from review_ui.runs).
"""
# ruff: noqa


from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag
from bs4.element import PreformattedString

ROOT_ID = "xtra-root"

_WS = re.compile(r"\s+")


def text_of(element: Tag) -> str:
    """Visible text of an element, with <br> as a newline."""
    parts: list[str] = []
    for node in element.descendants:
        if isinstance(node, Tag):
            if node.name == "br":
                parts.append("\n")
        elif not isinstance(node, PreformattedString):  # skip comments etc.
            parts.append(str(node))
    return "".join(parts)


def css_path(element: Tag) -> str:
    """Stable selector from the ``#xtra-root`` wrapper down; re-resolvable in the browser."""
    parts: list[str] = []
    node: Tag | None = element
    while node is not None and node.name not in (None, "[document]"):
        if node.get("id") == ROOT_ID:
            parts.append(f"#{ROOT_ID}")
            break
        siblings = [s for s in node.parent.find_all(node.name, recursive=False)]
        position = next(i for i, s in enumerate(siblings, 1) if s is node)
        parts.append(f"{node.name}:nth-of-type({position})")
        node = node.parent
    return " > ".join(reversed(parts))


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
            value = value.rstrip(name[len("rstrip:") :])
    return value


def extract_from_text(
    rule: dict, text: str
) -> tuple[str | None, str | None, tuple[int, int] | None]:
    """Run a rule's regex + transforms on already-selected text.

    Returns (value, raw_text, span-within-text); value is None when absent.
    """
    props = rule["properties"]
    raw, span = text, (0, len(text))
    pattern = props.get("regex")
    if pattern:
        match = re.search(pattern, text, re.MULTILINE)
        if not match:
            return None, None, None
        group = props.get("group", 1 if match.re.groups else 0)
        if match.group(group) is None:
            return None, None, None
        raw, span = match.group(group), match.span(group)
    value = apply_transforms(raw, props.get("transforms", []))
    if "map" in props:
        value = props["map"].get(value, "")  # a value the table lacks is absent
    if not value:
        return None, None, None
    return value, raw, span


def _label_matches(rule: dict, url: str, soup: BeautifulSoup | None) -> bool:
    if "url_regex" in rule and not re.search(rule["url_regex"], url):
        return False
    if "requires_selector" in rule and (
        soup is None or soup.select_one(rule["requires_selector"]) is None
    ):
        return False
    forbidden = (
        soup is not None
        and "forbids_selector" in rule
        and soup.select_one(rule["forbids_selector"]) is not None
    )
    return not forbidden


def _passes_filter(repeat_filter: dict, root: Tag) -> bool:
    """Keep a repeated element only if its text matches (e.g. a coded course row)."""
    selector = repeat_filter.get("selector")
    element = root.select_one(selector) if selector else root
    return element is not None and bool(
        re.search(repeat_filter["regex"], text_of(element), re.MULTILINE)
    )


def _absent(rule: dict) -> dict:
    return {
        "canonical_label": rule["canonical_label"],
        "ctdl_property": rule.get("ctdl_property"),
        "rule_id": rule["rule_id"],
        "rule_type": rule["rule_type"],
        "presence": "absent",
        "value": None,
        "raw_text": None,
        "location": None,
    }


def _run_field_rule(rule: dict, root: Tag | None, url: str) -> dict:
    result = _absent(rule)
    rtype, props = rule["rule_type"], rule["properties"]
    if rtype == "constant":
        value, raw, span, element = props["value"], props["value"], None, None
    elif rtype == "source_url":
        value, raw, span, element = url, url, None, None
    else:
        if root is None:
            return result
        element = root.select_one(props["selector"]) if props.get("selector") else root
        if element is None:
            return result
        value, raw, span = extract_from_text(rule, text_of(element))
    if value is None:
        return result
    result.update(presence="present", value=value, raw_text=raw)
    if element is not None:
        result["location"] = {
            "css_path": css_path(element),
            "char_start": span[0],
            "char_end": span[1],
        }
    return result


def _page_title(rules: list[dict], url: str, soup: BeautifulSoup | None) -> str | None:
    """First title rule whose url_regex matches and whose selector yields text."""
    if soup is None:
        return None
    for rule in rules:
        if "url_regex" in rule and not re.search(rule["url_regex"], url):
            continue
        element = soup.select_one(rule["selector"])
        if element is None:
            continue
        value, _, _ = extract_from_text({"properties": rule}, text_of(element))
        if value:
            return value
    return None


def run_page(ruleset: dict, url: str, main_html: str | None) -> dict:
    soup = (
        BeautifulSoup(f'<div id="{ROOT_ID}">{main_html}</div>', "lxml")
        if main_html
        else None
    )
    labels = [
        {"label": rule["label"], "rule_id": rule["rule_id"]}
        for rule in ruleset["label_rules"]
        if _label_matches(rule, url, soup)
    ]
    matched = {entry["rule_id"]: entry["label"] for entry in labels}

    entities: list[dict] = []
    for label_rule_id, label in matched.items():
        # root element -> entity, per (scope, repeat) so rules sharing a root merge.
        groups: dict[tuple, dict] = {}
        for rule in ruleset["field_rules"]:
            if label_rule_id not in rule["applies_to"]:
                continue
            props = rule["properties"]
            scope_sel = props.get("scope", f"#{ROOT_ID}")
            repeat_sel = props.get("repeat")
            scope_el = soup.select_one(scope_sel) if soup else None
            if scope_el is None:
                continue
            roots = scope_el.select(repeat_sel) if repeat_sel else [scope_el]
            if "repeat_filter" in props:
                roots = [r for r in roots if _passes_filter(props["repeat_filter"], r)]
            for root in roots:
                entity = groups.setdefault(
                    (scope_sel, repeat_sel, id(root)),
                    {
                        "label_rule_id": label_rule_id,
                        "label": label,
                        "root_path": css_path(root),
                        "fields": [],
                    },
                )
                entity["fields"].append(_run_field_rule(rule, root, url))
        for index, entity in enumerate(groups.values()):
            entity["index"] = index
            entities.append(entity)
    return {
        "url": url,
        "labels": labels,
        "entities": entities,
        "title": _page_title(ruleset.get("page_title", []), url, soup),
    }


def check_examples(ruleset: dict) -> list[str]:
    """Run every rule's example_input through its pipeline; list the mismatches."""
    failures = []
    for rule in ruleset["field_rules"]:
        if rule["rule_type"] in ("constant", "source_url"):
            continue
        if "example_input" not in rule or "example_output" not in rule:
            continue
        value, _, _ = extract_from_text(rule, rule["example_input"])
        if (value or "") != rule["example_output"]:
            failures.append(
                f"{rule['rule_id']}: {rule['example_input']!r} -> {value!r}, "
                f"expected {rule['example_output']!r}"
            )
    return failures
