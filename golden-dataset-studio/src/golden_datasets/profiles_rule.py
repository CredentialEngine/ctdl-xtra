"""List-of-objects property rules (sme-fixes spec §5): a rule whose value is a list of objects with named fields.

A property rule may declare, on top of a `multiple` split,

    "profile": {"fields": {"ceterms:description": <sub-definition>, "ceterms:timeRequired": <sub-definition>},
                "key": "ceterms:description"}

Each split item (e.g. each "Total Course … Hours 54.0 - 432.0" line) becomes one object; each field is read from the
item with its own sub-definition (regex / css / css+regex / labelled, like any rule; a selector applies inside the
item's element, a regex to the item's text). Values are the page's words, unparsed ("54.0 - 432.0").

One match row per object: `value` is the object as canonical JSON text (`model.canon`: keys sorted), `raw_text` and
the location are the item's, and `fields` holds each field's own location as JSON:
`{"ceterms:description": {"text", "css_path", "char_start", "char_end"}, …}` (css paths relative to the occurrence,
like a match's).

Only `ceterms:estimatedDuration` is a list of objects for now. `fold_rules` turns a catalog's Estimated Duration
rule and its five child rules (description, exact / minimum / maximum duration, time required) into the one profile
rule: the parent keeps its split, the description and time-required children become its fields, and the five
children leave the ruleset (`properties apply` publishes it; nobody annotated them, so nothing migrates).
"""

from __future__ import annotations

import json

from . import model

#: The properties that are lists of objects, their fields (in display order) and the field objects pair on.
PROFILES = {"ceterms:estimatedDuration": {"fields": ["ceterms:description", "ceterms:timeRequired"],
                                          "key": "ceterms:description"}}
#: Children of a profile property that are no longer rules of their own (properties.csv drops them).
FOLDED_CHILDREN = {"ceterms:estimatedDuration": ["ceterms:description", "ceterms:exactDuration",
                                                 "ceterms:minimumDuration", "ceterms:maximumDuration",
                                                 "ceterms:timeRequired"]}


def is_profile(definition: dict | None) -> bool:
    return bool((definition or {}).get("profile"))


def field_names(definition: dict) -> list[str]:
    return list((definition.get("profile") or {}).get("fields") or {})


def key_field(definition: dict) -> str | None:
    p = definition.get("profile") or {}
    return p.get("key") or next(iter(p.get("fields") or {}), None)


def parse(value: str | None) -> dict | None:
    """A profile match's value (JSON text) as an object; None for anything else."""
    if not value or not value.startswith("{"):
        return None
    try:
        got = json.loads(value)
    except ValueError:
        return None
    return got if isinstance(got, dict) else None


def shown(obj: dict, names: list[str] | None = None) -> str:
    """An object in words: its field values joined by " · " (field order)."""
    return " · ".join(str(obj[k]) for k in (names or list(obj)) if obj.get(k) not in (None, ""))


def _item_definition(definition: dict) -> dict:
    return {k: v for k, v in definition.items() if k not in ("profile", "absent_if")}


def _field_definition(definition: dict, sub: dict, item: dict) -> dict:
    """A field's sub-definition as a rule reading one item (`input: rule`; its element when it selects)."""
    use_element = bool(sub.get("selector")) or sub.get("rule_type") == "labelled"
    return {"rule_type": "regex", **sub, "locator": definition.get("locator"),
            "input": {"from": "rule", "rule": "_item", **({"use": "element"} if use_element else {})}}


def run(definition: dict, el, url: str, paths, occ_path: str, parent_out: list[dict] | None = None) -> list[dict]:
    """A profile rule on one occurrence: one result per object (status found), or the item rule's empty / no_match."""
    from . import engine

    items = engine.run_property(_item_definition(definition), el, url, paths, occ_path, parent_out)
    if not items or items[0]["status"] != "found":
        return items
    fields = (definition.get("profile") or {}).get("fields") or {}
    out = []
    for item in items:
        obj, locs = {}, {}
        for name, sub in fields.items():
            got = engine.run_property(_field_definition(definition, sub, item), el, url, paths, occ_path, [item])
            first = next((g for g in got if g["status"] == "found"), None)
            if first is None:
                continue
            obj[name] = first["value"]
            locs[name] = {"text": first["value"], "css_path": first["css_path"], "char_start": first["char_start"],
                          "char_end": first["char_end"]}
        if not obj:
            continue
        out.append({**item, "value": model.canon(obj), "fields": model.canon(locs)})
    return out or [{**engine._EMPTY}]


def values_of_text(definition: dict, text: str) -> list[dict]:
    """What a profile rule gives for one text (a draft's examples): its objects, in order."""
    from . import engine

    fields = (definition.get("profile") or {}).get("fields") or {}
    out = []
    for item in engine.values_of_text(_item_definition(definition), text):
        obj = {}
        for name, sub in fields.items():
            got = engine.values_of_text({"rule_type": "regex", **sub, "multiple": None}, item)
            if got:
                obj[name] = got[0]
        if obj:
            out.append(obj)
    return out


def item_fields(match: dict, occ_css_path: str) -> dict | None:
    """A profile match's fields with document-root css paths (rows and the golden dataset show these)."""
    raw = match.get("fields")
    if not raw:
        return None
    got = json.loads(raw)
    return {k: {**v, "css_path": model.full_css_path(occ_css_path, v.get("css_path"))} for k, v in got.items()}


def row_item(match: dict, occ_css_path: str) -> dict:
    """What a list row's item adds for an object: `fields` (each field's text and location). Nothing for a flat item."""
    fields = item_fields(match, occ_css_path)
    return {"fields": fields} if fields else {}


def row_value(found: list[dict]) -> str:
    """A list row's value: its items one per line; an object as its field values joined by " · "."""
    return "\n".join(shown(o) if (o := parse(x["value"])) is not None and x.get("fields") else x["value"]
                     for x in found)


def with_object_text(expected: dict | None) -> dict | None:
    """An added object's `expected` (`objects: [{fields: {name: {text, css_path, …}}}]`) with `text` set to the object
    as the rule would give it (canonical JSON of its field texts), so the item counts as fixed once the rule finds it."""
    objs = (expected or {}).get("objects") or []
    if not objs:
        return expected
    obj = {k: f.get("text") for k, f in (objs[0].get("fields") or {}).items() if f.get("text")}
    return {**expected, "text": model.canon(obj)}


# --- the ruleset change: six Estimated Duration rules → one (spec §5.1) ---------------------------------------------
def _as_field(child: dict) -> dict:
    """A child rule's definition as a field's sub-definition: no locator or input, and a one-match regex split read
    as a plain regex."""
    d = {k: v for k, v in child["definition"].items() if k not in ("locator", "input")}
    multiple = d.pop("multiple", None) or {}
    if multiple.get("split") == "regex" and not d.get("regex"):
        d["regex"] = multiple["regex"]
    return d


def fold_rules(rules: dict[str, dict]) -> tuple[dict[str, dict], dict[str, dict], list[str]]:
    """(the ruleset without the folded children, drafts for the parents that become profile rules, the removed rule
    ids). A parent with a rule gets the fields its children's rules read; one with no rule (or whose children have
    none) just loses the children."""
    keep = dict(rules)
    drafts: dict[str, dict] = {}
    removed: list[str] = []
    for rid, r in sorted(rules.items()):
        path = r.get("ctdl_property")
        if r["kind"] != "property" or path not in FOLDED_CHILDREN:
            continue
        loc = r["definition"].get("locator")
        children = {x.get("ctdl_property", "").split(">", 1)[1]: (cid, x) for cid, x in rules.items()
                    if x["kind"] == "property" and (x.get("ctdl_property") or "").startswith(path + ">")
                    and x["definition"].get("locator") == loc
                    and x["ctdl_property"].split(">", 1)[1] in FOLDED_CHILDREN[path]}
        if not children:
            continue
        for cid, _ in children.values():
            keep.pop(cid, None)
            removed.append(cid)
        spec = PROFILES[path]
        fields = {}
        for name in spec["fields"]:
            cid, child = children.get(name, (None, None))
            if child is None or child["definition"].get("rule_type") in (None, "none"):
                continue
            if (child["definition"].get("input") or {}).get("rule") != rid:
                continue  # it reads something else: not a field of these items
            fields[name] = _as_field(child)
        if r["definition"].get("rule_type") in (None, "none") or r["definition"].get("profile") or not fields:
            continue
        key = spec["key"] if spec["key"] in fields else next(iter(fields))
        definition = {**r["definition"], "profile": {"fields": fields, "key": key}}
        drafts[rid] = {**{k: r[k] for k in ("rule_id", "kind", "ctdl_property", "property_label") if k in r},
                       "definition": definition,
                       "what": "Each duration the page gives, as one object: its words "
                               f"({', '.join(f.split(':', 1)[-1] for f in fields)}).",
                       "how": (r.get("how") or "").strip() + " Each item's fields are read with the former child rules "
                              f"({', '.join(sorted(c for c, _ in children.values()))}).",
                       "why": "One rule whose value is a list of {description, timeRequired} objects replaces the six "
                              "Estimated Duration rules (sme-fixes §5.1): a description stays paired with its time. "
                              "Exact / minimum / maximum are parsed at transformation.",
                       "examples": []}
        keep[rid] = r  # replaced by the draft's version when published
    return keep, drafts, sorted(removed)
