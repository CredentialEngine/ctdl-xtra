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


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def first_settings(rules: dict[str, dict], given: dict | None = None) -> dict:
    """Settings for a catalog's first ruleset (one added from the picker has none to inherit): import-v2's defaults,
    `given` (a draft's `settings`) on top, and each record locator's course key read by its Coded Notation rule
    unless the draft names one."""
    from .import_v2 import LABEL_TEXT

    given = given or {}
    code_rules = {}
    for loc in sorted(rid for rid, r in rules.items() if r["kind"] == "locator"):
        code = next((rid for rid, r in sorted(rules.items()) if r["kind"] == "field"
                     and r["definition"].get("locator") == loc and r.get("property_label") == "Coded Notation"), None)
        if code:
            code_rules[loc] = code
    signals = {"course_code_pattern": r"\b[A-Z]{2,5} ?\d{3}[A-Z]?\b", "label_text_pattern": LABEL_TEXT,
               "shape_outlier_max_share": 0.02, "shape_dominance": 0.5, "length_outlier_percentiles": [1, 99],
               "missed_page_min_codes": 5, "page_allow": [], **(given.get("signals") or {})}
    return {"content_root": "body", "page_title": [], "pane_css": "", **given,
            "course_key_rule": given.get("course_key_rule") or code_rules, "signals": signals}


def plan_versions(ctx: Ctx, drafts: dict[str, dict], base: dict[str, dict]) -> dict[str, dict]:
    """Complete rule documents for `drafts` (rule_id → fields), with versions and hashes assigned.

    `base` is the current ruleset's rules; a draft whose definition hashes the same as an existing version of that
    rule reuses it (prose-only edits don't make a new version: what/how/why describe a definition)."""
    out = {}
    for rid, d in drafts.items():
        h = model.sha(d["definition"])
        versions = ctx.rule_versions(rid)
        existing = None
        for v in reversed(versions):
            doc = ctx.rule(rid, v)
            if doc["content_hash"] == h:
                existing = doc
                break
        if existing is not None:
            out[rid] = existing
            continue
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
        out[rid] = rule
    return out


def validate_ruleset(rules: dict[str, dict]) -> None:
    for rid, r in rules.items():
        if r["kind"] not in model.KINDS:
            raise UserError(f"{rid}: kind must be one of {model.KINDS}")
        for dep in model.dependencies(r):
            if dep not in rules:
                raise UserError(f"{rid} depends on {dep}, which isn't in the ruleset")
        if r["kind"] == "field":
            d = r["definition"]
            if d.get("rule_type") not in ("css", "css+regex", "regex", "constant", "source_url"):
                raise UserError(f"{rid}: unknown rule_type {d.get('rule_type')!r}")
            if rules[d["locator"]]["kind"] != "locator":
                raise UserError(f"{rid}: definition.locator must name a record locator")


def ruleset_doc(ctx: Ctx, version: int, rules: dict[str, dict], settings: dict, parent: int | None,
                changed: list[str], note: str, by: str, extra: dict | None = None) -> dict:
    listed = sorted(rules.values(), key=lambda r: (model.KIND_ORDER[r["kind"]], r["rule_id"]))
    return {"catalog": ctx.catalog, "version": version, "parent_version": parent, "published_by": by,
            "published_at": now_iso(), "note": note, "settings": settings,
            "rules": [{"rule_id": r["rule_id"], "kind": r["kind"], "version": r["version"],
                       "content_hash": r["content_hash"]} for r in listed],
            "changed_rules": sorted(changed), **(extra or {})}


def publish(ctx: Ctx, rules: dict[str, dict], settings: dict, note: str, by: str,
            extra: dict | None = None) -> dict | None:
    """Write new rule versions and one new ruleset version. `rules` is the complete new ruleset (from
    plan_versions). Returns the ruleset document, or None when nothing changed."""
    validate_ruleset(rules)
    versions = ctx.ruleset_versions()
    parent = versions[-1] if versions else None
    base_rules, base_settings = {}, None
    if parent:
        rs, base_rules = ctx.ruleset_rules(parent)
        base_settings = rs["settings"]
    changed = sorted(rid for rid, r in rules.items()
                     if rid not in base_rules or base_rules[rid]["content_hash"] != r["content_hash"])
    removed = sorted(set(base_rules) - set(rules))
    if parent and not changed and not removed and base_settings == settings:
        return None
    for r in rules.values():
        path = layout.rule_version(ctx.catalog, r["rule_id"], r["version"])
        if not ctx.root.exists(path):
            r = {**r, "published_by": by, "published_at": now_iso()}
            ctx.root.write_json(path, _ordered(r), if_none_match=True)
    version = (parent or 0) + 1
    doc = ruleset_doc(ctx, version, rules, settings, parent, changed + removed, note, by, extra)
    try:
        ctx.root.write_json(layout.ruleset(ctx.catalog, version), doc, if_none_match=True)
    except ConflictError:
        raise UserError(f"ruleset v{version} was published by someone else meanwhile; try again") from None

    log_exists = ctx.root.exists(layout.annotations(ctx.catalog))

    def change(m: dict) -> None:
        cat = manifest.catalog_entry(m, ctx.catalog)
        for r in rules.values():
            manifest.add_unique(cat["rule_versions"], layout.rule_version(ctx.catalog, r["rule_id"], r["version"]))
        cat["rule_versions"].sort()
        manifest.add_unique(cat["rulesets"], {"version": version, "path": layout.ruleset(ctx.catalog, version)},
                            key=lambda x: x["version"])
        if log_exists:  # a catalog's first ruleset has no annotations yet; readers find the log by its path
            cat["annotations"] = layout.annotations(ctx.catalog)

    manifest.update(ctx.root, change)
    return doc


def _ordered(rule: dict) -> dict:
    keys = ["catalog", "rule_id", "version", "kind", "parent_version", "published_by", "published_at",
            "ctdl_property", "property_label", "definition", "what", "how", "why", "examples", "depends_on",
            "imported_from", "content_hash"]
    return {k: rule[k] for k in keys if k in rule} | {k: v for k, v in rule.items() if k not in keys}
