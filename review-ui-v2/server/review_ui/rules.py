"""Declarative extraction rules: data, never code.

A ruleset is JSON. ``label_rules`` decide which CTDL classes apply to a page;
``field_rules`` pull property values out of the page for pages carrying a label.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import soupsieve

RULE_TYPES = ("css", "regex", "css+regex", "constant", "source_url")

TRANSFORM_NAMES = ("strip", "collapse_ws", "upper", "lower", "remove_spaces")
TRANSFORM_PREFIXES = ("rstrip:",)

_SELECTOR_PROPS = {"scope", "repeat", "selector"}

RULESET_SCHEMA = {
    "type": "object",
    "required": [
        "ruleset_id",
        "version",
        "catalog_folder",
        "entity_type",
        "content_root",
        "page_types",
        "label_rules",
        "field_rules",
    ],
    "properties": {
        "ruleset_id": {"type": "string"},
        "version": {"type": "integer", "minimum": 1},
        "catalog_folder": {"type": "string"},
        "entity_type": {"const": "Course"},
        "label_vocabulary": {"type": "array", "items": {"type": "string"}},
        "content_root": {"type": "string", "minLength": 1},
        "pane_css": {"type": "string"},
        "page_types": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["type", "url_regex"],
                "additionalProperties": False,
                "properties": {
                    "type": {"type": "string"},
                    "url_regex": {"type": "string"},
                },
            },
        },
        "sample": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "target": {"type": "integer", "minimum": 1},
                "quotas": {
                    "type": "object",
                    "additionalProperties": {"type": "integer", "minimum": 0},
                },
                "strata": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["name", "quota"],
                            "additionalProperties": False,
                            "properties": {
                                "name": {"type": "string"},
                                "quota": {"type": "integer", "minimum": 0},
                                "pattern": {"type": "string"},
                            },
                        },
                    },
                },
                "size_pattern": {"type": "string"},
                "small_page": {"type": "integer", "minimum": 1},
                "spread": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
            },
        },
        "page_title": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["selector"],
                "additionalProperties": False,
                "properties": {
                    "url_regex": {"type": "string"},
                    "selector": {"type": "string"},
                    "regex": {"type": ["string", "null"]},
                    "group": {"type": "integer", "minimum": 0},
                    "transforms": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "label_rules": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["rule_id", "label"],
                "additionalProperties": False,
                "properties": {
                    "rule_id": {"type": "string"},
                    "label": {"type": "string"},
                    "description": {"type": "string"},
                    "url_regex": {"type": "string"},
                    "requires_selector": {"type": "string"},
                    "forbids_selector": {"type": "string"},
                },
            },
        },
        "field_rules": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "entity_type",
                    "rule_id",
                    "rule_type",
                    "canonical_label",
                    "applies_to",
                    "properties",
                ],
                "additionalProperties": False,
                "properties": {
                    "entity_type": {"const": "Rule"},
                    "rule_id": {"type": "string"},
                    "rule_type": {"enum": list(RULE_TYPES)},
                    "canonical_label": {"type": "string"},
                    "ctdl_property": {"type": ["string", "null"]},
                    "applies_to": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                    "properties": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "scope": {"type": "string"},
                            "repeat": {"type": ["string", "null"]},
                            "repeat_filter": {
                                "type": "object",
                                "required": ["regex"],
                                "additionalProperties": False,
                                "properties": {
                                    "selector": {"type": "string"},
                                    "regex": {"type": "string"},
                                },
                            },
                            "selector": {"type": ["string", "null"]},
                            "regex": {"type": ["string", "null"]},
                            "group": {"type": "integer", "minimum": 0},
                            "transforms": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "value": {"type": "string"},
                            "map": {
                                "type": "object",
                                "additionalProperties": {"type": "string"},
                            },
                        },
                    },
                    "description": {"type": "string"},
                    "example_input": {"type": "string"},
                    "example_output": {"type": "string"},
                },
            },
        },
    },
}


class RulesetError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("invalid ruleset:\n  - " + "\n  - ".join(problems))
        self.problems = problems


def load_ruleset(path: Path | str, known_properties: set[str] | None = None) -> dict:
    ruleset = json.loads(Path(path).read_text("utf-8"))
    validate_ruleset(ruleset, known_properties)
    return ruleset


def validate_ruleset(ruleset: dict, known_properties: set[str] | None = None) -> None:
    """Raise RulesetError listing every problem found, not just the first."""
    validator = jsonschema.Draft202012Validator(RULESET_SCHEMA)
    problems = [
        f"{'/'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}"
        for err in validator.iter_errors(ruleset)
    ]
    if problems:
        raise RulesetError(problems)

    problems += _selector_problems("content_root", ruleset["content_root"])
    for position, entry in enumerate(ruleset["page_types"]):
        problems += _regex_problems(f"page_types[{position}]", entry["url_regex"])
    problems += _sample_problems(ruleset.get("sample", {}), ruleset["page_types"])

    label_ids = [r["rule_id"] for r in ruleset["label_rules"]]
    rule_ids = [r["rule_id"] for r in ruleset["field_rules"]]
    for ident in {
        i for i in label_ids + rule_ids if (label_ids + rule_ids).count(i) > 1
    }:
        problems.append(f"duplicate rule_id {ident!r}")

    for rule in ruleset["label_rules"]:
        rid = rule["rule_id"]
        if "url_regex" in rule:
            problems += _regex_problems(rid, rule["url_regex"])
        for key in ("requires_selector", "forbids_selector"):
            if key in rule:
                problems += _selector_problems(rid, rule[key])
        if not any(k in rule for k in ("url_regex", "requires_selector")):
            problems.append(f"{rid}: needs url_regex or requires_selector")

    for position, rule in enumerate(ruleset.get("page_title", [])):
        rid = f"page_title[{position}]"
        if "url_regex" in rule:
            problems += _regex_problems(rid, rule["url_regex"])
        if rule.get("regex"):
            problems += _regex_problems(rid, rule["regex"])
        problems += _selector_problems(rid, rule["selector"])
        problems += _transform_problems(rid, rule.get("transforms", []))

    for rule in ruleset["field_rules"]:
        rid, rtype, props = rule["rule_id"], rule["rule_type"], rule["properties"]
        for target in rule["applies_to"]:
            if target not in label_ids:
                problems.append(f"{rid}: applies_to unknown label rule {target!r}")
        if known_properties is not None and (
            rule["canonical_label"] not in known_properties
        ):
            problems.append(
                f"{rid}: canonical_label {rule['canonical_label']!r} is not a "
                "template property"
            )
        for key in _SELECTOR_PROPS:
            if props.get(key):
                problems += _selector_problems(rid, props[key])
        if props.get("regex"):
            problems += _regex_problems(rid, props["regex"])
        if "repeat_filter" in props:
            if not props.get("repeat"):
                problems.append(f"{rid}: repeat_filter needs properties.repeat")
            problems += _regex_problems(rid, props["repeat_filter"]["regex"])
            if props["repeat_filter"].get("selector"):
                problems += _selector_problems(rid, props["repeat_filter"]["selector"])
        problems += _transform_problems(rid, props.get("transforms", []))
        if rtype == "constant" and "value" not in props:
            problems.append(f"{rid}: constant rule needs properties.value")
        if rtype in ("regex", "css+regex") and not props.get("regex"):
            problems.append(f"{rid}: {rtype} rule needs properties.regex")
        if rtype in ("css", "css+regex") and not props.get("selector"):
            problems.append(f"{rid}: {rtype} rule needs properties.selector")

    if problems:
        raise RulesetError(problems)


def _sample_problems(sample: dict, page_types: list[dict]) -> list[str]:
    known = {entry["type"] for entry in page_types} | {"info"}
    problems: list[str] = []
    for key in ("quotas", "strata", "spread"):
        for page_type in sample.get(key, {}):
            if page_type not in known:
                problems.append(f"sample.{key}: unknown page type {page_type!r}")
    for page_type, strata in sample.get("strata", {}).items():
        names = [s["name"] for s in strata]
        if len(set(names)) != len(names):
            problems.append(f"sample.strata.{page_type}: duplicate stratum names")
        for stratum in strata:
            if "pattern" in stratum:
                problems += _regex_problems(
                    f"sample.strata.{page_type}.{stratum['name']}", stratum["pattern"]
                )
    for key in ("size_pattern",):
        if key in sample:
            problems += _regex_problems(f"sample.{key}", sample[key])
    for page_type, pattern in sample.get("spread", {}).items():
        problems += _regex_problems(f"sample.spread.{page_type}", pattern)
        if re.compile(pattern).groups < 1:
            problems.append(f"sample.spread.{page_type}: needs a capture group")
    return problems


def _transform_problems(rid: str, transforms: list[str]) -> list[str]:
    return [
        f"{rid}: unknown transform {t!r}"
        for t in transforms
        if t not in TRANSFORM_NAMES and not t.startswith(TRANSFORM_PREFIXES)
    ]


def _regex_problems(rid: str, pattern: str) -> list[str]:
    try:
        re.compile(pattern)
    except re.error as exc:
        return [f"{rid}: bad regex {pattern!r}: {exc}"]
    return []


def _selector_problems(rid: str, selector: str) -> list[str]:
    try:
        soupsieve.compile(selector)
    except (soupsieve.SelectorSyntaxError, ValueError, TypeError) as exc:
        return [f"{rid}: bad selector {selector!r}: {exc}"]
    return []
