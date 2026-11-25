"""Publishing rule versions and ruleset versions (spec §4.3).

`golden-datasets` assigns versions, never a person or Claude: a rule whose `content_hash` (its own definition) is
unchanged keeps its version; a changed one gets the next number. Every publish makes a ruleset version, which
lists every rule version plus the catalog's settings. Publishing nothing new is a no-op.
"""

from __future__ import annotations

from datetime import UTC, datetime

from . import layout, manifest, model
from .context import Ctx
from .errors import ConflictError, UserError

RULE_FIELDS = ("rule_id", "kind", "ctdl_property", "property_label", "definition", "what", "how", "why", "examples",
               "depends_on")
#: A label a value starts with (`Prerequisite:`): the `label_text` signal's pattern, from review-ui-v2.
LABEL_TEXT = (r"^\s*(Prerequisites?|Corequisites?|Advisory|Recommended Preparation|Units?|Description|Course)\s*:"
              r"|\b(Prerequisites?|Corequisites?)\s*:")


def plan_versions(ctx: Ctx, drafts: dict[str, dict], base: dict[str, dict]) -> dict[str, dict]:
    """Complete rule documents for `drafts` (rule_id → fields), with versions and hashes assigned.

    `base` is the current ruleset's rules; a draft whose definition hashes the same as an existing version of that
    rule reuses it (prose-only edits don't make a new version: what/how/why describe a definition)."""
    out = {}
    for rid, d in drafts.items():
        h = model.sha(d["definition"])
        versions = ctx.rule_versions(rid)
        out[rid] = _version_with_hash(ctx, rid, versions, h) or _new_rule_version(ctx, rid, d, base, versions, h)
    return out


def publish(ctx: Ctx, rules: dict[str, dict], settings: dict, note: str, by: str,
            extra: dict | None = None) -> dict | None:
    """Write new rule versions and one new ruleset version. `rules` is the complete new ruleset (from
    plan_versions). Returns the ruleset document, or None when nothing changed."""
    validate_ruleset(rules)
    versions = ctx.ruleset_versions()
    parent = versions[-1] if versions else None
    base_rules, base_settings = _base_of(ctx, parent)
    changed = sorted(rid for rid, r in rules.items()
                     if rid not in base_rules or base_rules[rid]["content_hash"] != r["content_hash"])
    removed = sorted(set(base_rules) - set(rules))
    if parent and not changed and not removed and base_settings == settings:
        return None
    _write_rule_versions(ctx, rules, by)
    version = (parent or 0) + 1
    doc = ruleset_doc(ctx, version, rules, settings, parent, changed + removed, note, by, extra)
    _write_ruleset(ctx, version, doc)
    _register_ruleset(ctx, rules, version)
    return doc


def ruleset_doc(ctx: Ctx, version: int, rules: dict[str, dict], settings: dict, parent: int | None,
                changed: list[str], note: str, by: str, extra: dict | None = None) -> dict:
    listed = sorted(rules.values(), key=lambda r: (model.KIND_ORDER[r["kind"]], r["rule_id"]))
    return {"catalog": ctx.catalog, "version": version, "parent_version": parent, "published_by": by,
            "published_at": now_iso(), "note": note, "settings": settings,
            "rules": [{"rule_id": r["rule_id"], "kind": r["kind"], "version": r["version"],
                       "content_hash": r["content_hash"]} for r in listed],
            "changed_rules": sorted(changed), **(extra or {})}


def _version_with_hash(ctx: Ctx, rid: str, versions: list[int], h: str) -> dict | None:
    """The latest existing version of the rule with this definition hash."""
    for v in reversed(versions):
        doc = ctx.rule(rid, v)
        if doc["content_hash"] == h:
            return doc
    return None


def _new_rule_version(ctx: Ctx, rid: str, d: dict, base: dict[str, dict], versions: list[int], h: str) -> dict:
    parent = base.get(rid)
    rule = {"catalog": ctx.catalog, "rule_id": rid, "version": (max(versions) if versions else 0) + 1,
            "kind": d["kind"], "parent_version": parent["version"] if parent else None}
    for key in RULE_FIELDS[1:]:
        if key in d:
            rule[key] = d[key]
    rule.setdefault("depends_on", model.dependencies(rule))
    rule.setdefault("examples", [])
    for key in ("what", "how", "why"):
        rule.setdefault(key, "")
    rule["content_hash"] = h
    if "imported_from" in d:
        rule["imported_from"] = d["imported_from"]
    return rule


def _base_of(ctx: Ctx, parent: int | None) -> tuple[dict[str, dict], dict | None]:
    """The parent ruleset's rules and settings (none for a catalog's first ruleset)."""
    if not parent:
        return {}, None
    rs, base_rules = ctx.ruleset_rules(parent)
    return base_rules, rs["settings"]


def _write_rule_versions(ctx: Ctx, rules: dict[str, dict], by: str) -> None:
    for r in rules.values():
        path = layout.rule_version(ctx.catalog, ctx.cls, r["rule_id"], r["version"])
        if not ctx.root.exists(path):
            r = {**r, "published_by": by, "published_at": now_iso()}
            ctx.root.write_json(path, _ordered(r), if_none_match=True)


def _write_ruleset(ctx: Ctx, version: int, doc: dict) -> None:
    try:
        ctx.root.write_json(layout.ruleset(ctx.catalog, ctx.cls, version), doc, if_none_match=True)
    except ConflictError:
        raise UserError(f"ruleset v{version} was published by someone else meanwhile; try again") from None


def _register_ruleset(ctx: Ctx, rules: dict[str, dict], version: int) -> None:
    log_exists = ctx.root.exists(layout.annotations(ctx.catalog, ctx.cls))

    def change(m: dict) -> None:
        cat = manifest.class_entry(manifest.catalog_entry(m, ctx.catalog), ctx.cls)
        for r in rules.values():
            manifest.add_unique(cat["rule_versions"], layout.rule_version(ctx.catalog, ctx.cls, r["rule_id"], r["version"]))
        cat["rule_versions"].sort()
        manifest.add_unique(cat["rulesets"], {"version": version, "path": layout.ruleset(ctx.catalog, ctx.cls, version)},
                            key=lambda x: x["version"])
        if log_exists:  # a catalog's first ruleset has no annotations yet; readers find the log by its path
            cat["annotations"] = layout.annotations(ctx.catalog, ctx.cls)

    manifest.update(ctx.root, change)


def _ordered(rule: dict) -> dict:
    keys = ["catalog", "rule_id", "version", "kind", "parent_version", "published_by", "published_at",
            "ctdl_property", "property_label", "definition", "what", "how", "why", "examples", "depends_on",
            "imported_from", "content_hash"]
    return {k: rule[k] for k in keys if k in rule} | {k: v for k, v in rule.items() if k not in keys}


# --- validation ------------------------------------------------------------------------------------
def validate_ruleset(rules: dict[str, dict]) -> None:
    from . import engine

    for rid, r in rules.items():
        _validate_rule(rid, r, rules)
    try:
        engine.property_order(rules, [rid for rid, r in rules.items() if r["kind"] == "property"])
    except ValueError as exc:
        raise UserError(f"rules read each other in a circle: {exc}") from None


def _validate_rule(rid: str, r: dict, rules: dict[str, dict]) -> None:
    if r["kind"] not in model.KINDS:
        raise UserError(f"{rid}: kind must be one of {model.KINDS}")
    for dep in model.dependencies(r):
        if dep not in rules:
            raise UserError(f"{rid} depends on {dep}, which isn't in the ruleset")
    if r["kind"] == "property":
        _validate_property(rid, r["definition"], rules)


def _validate_property(rid: str, d: dict, rules: dict[str, dict]) -> None:
    from . import engine

    if d.get("rule_type") not in model.RULE_TYPES:
        raise UserError(f"{rid}: unknown rule_type {d.get('rule_type')!r} (one of {', '.join(model.RULE_TYPES)})")
    if rules[d["locator"]]["kind"] != "locator":
        raise UserError(f"{rid}: definition.locator must name a record locator")
    _validate_input(rid, d, rules)
    if d["rule_type"] == "labelled" and not d.get("label"):
        raise UserError(f"{rid}: a labelled rule needs `label`")
    split = (d.get("multiple") or {}).get("split") if d.get("multiple") else None
    if d.get("multiple") and split not in engine.SPLITS:
        raise UserError(f"{rid}: multiple.split must be one of {', '.join(engine.SPLITS)}")


def _validate_input(rid: str, d: dict, rules: dict[str, dict]) -> None:
    from . import engine

    inp = engine.input_of(d)
    if inp.get("from") not in engine.INPUTS:
        raise UserError(f"{rid}: input.from must be one of {', '.join(engine.INPUTS)}")
    if inp["from"] != "rule":
        return
    parent = rules.get(inp.get("rule") or "")
    if parent is None or parent["kind"] != "property":
        raise UserError(f"{rid}: input.rule must name a property rule")
    if parent["definition"].get("locator") != d["locator"]:
        raise UserError(f"{rid}: input.rule {inp['rule']} is on another record locator")


# --- settings --------------------------------------------------------------------------------------
def first_settings(rules: dict[str, dict], given: dict | None = None) -> dict:
    """Settings for a catalog's first ruleset (one added from the picker has none to inherit): the defaults, with
    `given` (a draft's `settings`) on top. A record's key isn't a setting: it is the value of its locator's External
    Identifier rule (model.key_rule_for)."""
    given = given or {}
    signals = {"course_code_pattern": r"\b[A-Z]{2,5} ?\d{3}[A-Z]?\b", "label_text_pattern": LABEL_TEXT,
               "shape_outlier_max_share": 0.02, "shape_dominance": 0.5, "length_outlier_percentiles": [1, 99],
               "missed_page_min_codes": 5, "page_allow": [], **(given.get("signals") or {})}
    return {"content_root": "body", "page_title": [], "pane_css": "", **given, "signals": signals}


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
