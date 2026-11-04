"""A rule's claim that a property is not on the page (sme-fixes spec §6).

A property rule ends one of three ways on a course: a value (`found`); **"not on the page"** (`absent`, the rule's
claim); or nothing found (`no_match` / `empty`: the rule made no claim, so the property may still be on the page).

A rule claims absence only through an explicit check in its definition:

    "absent_if": {"within": "<selector, relative to the record>", "missing": "<selector or label>"}

It applies when the rule found no value: the `within` container was found on the record and the property's element
(`missing` as a css selector) or label (`missing` as text, or `{"label": "…"}`) is not in it. The match then has
status `absent`, no value, and the container's location (the Studio draws it dashed: "rule looked here").
"""

from __future__ import annotations

from cssselect import SelectorError


def _has(container, missing) -> bool:
    from . import engine

    if isinstance(missing, dict):
        if missing.get("selector"):
            return engine.select_one(container, missing["selector"]) is not None
        label = missing.get("label") or ""
    else:
        try:
            return engine.select_one(container, missing) is not None
        except (SelectorError, SyntaxError, ValueError):
            label = missing  # not a selector: a label's words
    return label.strip().lower() in engine.text_of(container)[0].lower()


def check(definition: dict, el, paths, occ_path: str) -> dict | None:
    """The `absent` result when the definition's `absent_if` holds on this record, else None."""
    from . import engine

    spec = definition.get("absent_if")
    if not spec or el is None or not spec.get("within") or not spec.get("missing"):
        return None
    container = engine.select_one(el, spec["within"], True)
    if container is None or _has(container, spec["missing"]):
        return None
    return {**engine._EMPTY, "status": "absent", "css_path": engine.relative(occ_path, paths(container))}


def claim_or(definition: dict, el, paths, occ_path: str, results: list[dict]) -> list[dict]:
    """A rule's results, with "nothing found" turned into the absent claim when its check holds."""
    if not definition.get("absent_if") or (results and results[0]["status"] == "found"):
        return results
    got = check(definition, el, paths, occ_path)
    return [got] if got is not None else results
