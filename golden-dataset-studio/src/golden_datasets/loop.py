"""The Claude loop (spec §3.1, §6 "For Claude"): `rule list / show / annotations / draft / try / publish` and
`pages get / sample`.

Claude Code works only through these commands, never on the storage root directly:
- `rule show` / `rule annotations` / `pages get` / `pages sample` give it the context;
- `rule draft R… > draft.json` gives it the current versions to edit (definition + what / how / why + examples);
- `rule try draft.json` reruns the draft over the whole crawl and prints the scorecard (writes nothing);
- `rule publish draft.json` writes the new rule versions, a ruleset version and its extraction, and refuses when a
  value marked correct changes (unless `--force`).

`golden-datasets` assigns versions and hashes (`rulesets.plan_versions`), never the draft.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

from . import engine, extract, layout, model, rulesets, scorecard
from .catalogs import info
from .context import Ctx
from .errors import UserError
from .review import LOADER, OPEN, Review, Snapshot, norm
from .signals import CATALOG as SIGNALS

VERDICT_ORDER = {"wrong": 0, "missing": 1, "question": 2, "correct": 3}
STATE_LABEL = {"wrong": "wrong", "still-wrong": "still wrong", "fixed": "fixed", "correct": "correct",
               "changed-since-correct": "changed since marked correct", "question": "question for the institution",
               "missing": "missing (still not found)", "found-now": "missing → found now",
               "no-row": "no row now (the rule no longer finds it)", None: "—"}


# =====================================================================================================
# Shared read helpers (also used by prompt.py and the server)
# =====================================================================================================
def current_review(ctx: Ctx) -> Review:
    """The latest ruleset's extraction + the annotation log."""
    v = ctx.latest_ruleset()
    ext = ctx.extraction_for(v)
    if not ext:
        raise UserError(f"ruleset v{v} has no extraction on crawl {ctx.crawl}; run `golden-datasets extract`")
    return Review(LOADER.snapshot(ctx, ext), LOADER.log(ctx).events())


def page_ref(ctx: Ctx, stem: str) -> str:
    """A saved page's path, resolved against $GOLDEN_DATASETS_ROOT (spec §7.5: pages by path, never raw HTML)."""
    return f"$GOLDEN_DATASETS_ROOT/{layout.page_html(ctx.catalog, ctx.crawl, stem)}"


def rule_or_error(rv: Review, rule_id: str) -> dict:
    if rule_id not in rv.snap.rules:
        known = ", ".join(sorted(rv.snap.rules))
        raise UserError(f"no rule {rule_id!r} in ruleset v{rv.snap.ruleset_version} (rules: {known})")
    return rv.snap.rules[rule_id]


def rule_annotations(rv: Review, rule_id: str, page_questions: bool = True) -> list[dict]:
    """Every live annotation on a rule (superseded ones dropped; the latest verdict per target), with the
    verdict carried to the current version (`state`), the current value, and whether it still needs work.

    `page_questions`: also the page-level questions (no rule) on pages this rule has rows on."""
    snap = rv.snap
    rule_or_error(rv, rule_id)
    rows = snap.rows(rule_id)
    states = rv.row_states(rule_id, rows)
    by_event: dict[str, tuple[dict, object]] = {}
    for row in rows:
        st = states[row["key"]]
        if st.verdict is not None:
            by_event.setdefault(st.verdict["annotation_id"], (row, st))
    open_missing = {e["annotation_id"] for e in rv.missing_events(rule_id)}
    v = rv.verdicts_for(rule_id)
    out = []
    for key, e in v["latest"].items():
        row, st = by_event.get(e["annotation_id"], (None, None))
        if st is not None:
            state = st.state
        elif e["verdict"] == "missing":
            state = "missing" if e["annotation_id"] in open_missing else "found-now"
        elif e["verdict"] == "question":
            state = "question"
        else:
            state = "no-row"
        out.append(_record(rv, rule_id, e, row, state, v["comments"].get(key, []),
                           reattached=bool(st is not None and st.reattached)))
    for key, cs in v["comments"].items():
        if key not in v["latest"]:
            out.append(_record(rv, rule_id, cs[-1], None, None, cs[:-1]))
    if page_questions:
        stems = {r["page_stem"] for r in rows}
        for e in rv.verdicts_for(None)["latest"].values():
            if e["verdict"] == "question" and e["target"].get("page_stem") in stems:
                out.append(_record(rv, rule_id, e, None, "question", [], page_level=True))
    out.sort(key=lambda r: (not r["open"], VERDICT_ORDER.get(r["verdict"] or "", 4), r["course_key"] or "",
                            r["page_stem"] or "", r["annotation_id"]))
    return out


def _record(rv: Review, rule_id: str, e: dict, row: dict | None, state: str | None, comments: list,
            reattached: bool = False, page_level: bool = False) -> dict:
    t = e["target"]
    snap = rv.snap
    stem = t.get("page_stem") or (model.stem_of(t["occurrence_key"]) if t.get("occurrence_key") else None)
    page = snap.page.get(stem) or {}
    occ = snap.occurrences.get(t.get("occurrence_key") or "")
    exp = e.get("expected") or None
    return {
        "annotation_id": e["annotation_id"], "type": e["type"], "verdict": e.get("verdict"), "state": state,
        "open": state in OPEN, "author": e["author"], "at": e["at"], "rule_id": rule_id,
        "target_kind": t.get("kind"), "page_level": page_level,
        "course_key": t.get("course_key") or (row or {}).get("course_key"), "page_stem": stem,
        "url": page.get("url"), "page_title": page.get("title"),
        "occurrence_key": t.get("occurrence_key"), "occurrence_css_path": (occ or {}).get("css_path"),
        "rule_version_seen": t.get("rule_version_seen"), "value_seen": t.get("value_seen"),
        "rule_version": snap.rules[rule_id]["version"], "rule_kind": snap.rules[rule_id]["kind"],
        "has_row": row is not None, "current_value": (row or {}).get("value"),
        "current_css_path": (row or {}).get("css_path"),
        "expected": None if not exp else {k: exp.get(k) for k in ("text", "css_path", "char_start", "char_end")}
        | ({"segments": [{k: s.get(k) for k in ("text", "css_path", "char_start", "char_end")}
                          | {"polarity": s.get("polarity") or "in"} for s in exp["segments"]]}
           if exp.get("segments") else {}),
        "note": e.get("note"), "reattached": reattached,
        "comments": [{"annotation_id": c["annotation_id"], "author": c["author"], "at": c["at"], "note": c.get("note")}
                     | ({"on": c["anchor"].get("text")} if c.get("anchor") else {}) for c in comments],
    }


def rule_brief(rv: Review, rule_id: str) -> dict:
    """Status, reviewed / total, fill and signal counts of one rule in the current extraction."""
    st = rv.rule_status(rule_id)
    sig = rv.snap.signal_counts.get(rule_id, {})
    return {**st, "fill": rv.snap.fill(rule_id),
            "signals": dict(sorted(sig.items(), key=lambda kv: (-kv[1], kv[0])))}


def ordered_rule_ids(rules: dict[str, dict]) -> list[str]:
    return sorted(rules, key=lambda r: (model.KIND_ORDER[rules[r]["kind"]], r))


def short(v: str | None, n: int = 160) -> str:
    v = (v or "").replace("\n", "⏎ ")
    return v if len(v) <= n else v[: n - 1] + "…"


# =====================================================================================================
# rule list / show / annotations
# =====================================================================================================
def _header(ctx: Ctx, rv: Review) -> str:
    return (f"{info(ctx.catalog)['name']} · {ctx.catalog} · crawl {ctx.crawl} · ruleset v{rv.snap.ruleset_version}"
            f" · extraction {rv.snap.ext}")


def cmd_rule_list(args) -> int:
    ctx = Ctx.from_args(args)
    rv = current_review(ctx)
    print(_header(ctx, rv))
    lines = [("kind", "rule", "ver", "status", "reviewed", "fill", "signals")]
    for rid in ordered_rule_ids(rv.snap.rules):
        r = rv.snap.rules[rid]
        b = rule_brief(rv, rid)
        sig = ", ".join(f"{k} {n:,}" for k, n in list(b["signals"].items())[:3])
        lines.append((r["kind"], rid, f"v{r['version']}", b["status"], f"{b['reviewed']:,} / {b['total']:,}",
                      f"{b['fill']['found']:,} / {b['fill']['rows']:,}", sig or "—"))
    widths = [max(len(x[i]) for x in lines) for i in range(6)]
    for x in lines:
        print("  ".join(f"{c:<{widths[i]}}" if i not in (2, 4, 5) else f"{c:>{widths[i]}}"
                        for i, c in enumerate(x[:6])) + "  " + x[6])
    return 0


def cmd_rule_show(args) -> int:
    ctx = Ctx.from_args(args)
    rv = current_review(ctx)
    cur = rule_or_error(rv, args.rule_id) if args.rule_id in rv.snap.rules else None
    versions = ctx.rule_versions(args.rule_id)
    if cur is None and not versions:
        rule_or_error(rv, args.rule_id)
    version = args.version or (cur["version"] if cur else versions[-1])
    if version not in versions:
        raise UserError(f"{args.rule_id} has no version {version} (versions: {', '.join(map(str, versions))})")
    r = ctx.rule(args.rule_id, version)
    print(f"{args.rule_id} v{version} — {r['kind']} rule"
          + (f", {r['property_label']} ({r.get('ctdl_property') or 'no CTDL term'})" if r.get("property_label") else ""))
    print(_header(ctx, rv))
    if cur is None:
        print(f"  not in the current ruleset (v{rv.snap.ruleset_version})")
    elif version != cur["version"]:
        print(f"  not the current version: v{cur['version']} is (status, fill and signals below are for v{cur['version']})")
    for key in ("what", "how", "why"):
        print(f"\n{key}:\n  {r.get(key) or '(empty)'}")
    print("\ndefinition:")
    print("  " + json.dumps(r["definition"], indent=2, ensure_ascii=False).replace("\n", "\n  "))
    print(f"\nexamples ({len(r.get('examples') or [])}):")
    for ex in r.get("examples") or []:
        print(f"  input:  {json.dumps(ex.get('input'), ensure_ascii=False)}")
        print(f"  output: {json.dumps(ex.get('output'), ensure_ascii=False)}")
    print(f"\ndepends on:   {', '.join(r.get('depends_on') or []) or '—'}")
    print(f"content_hash: {r['content_hash']}")
    print(f"published:    {r.get('published_at', '?')} by {r.get('published_by', '?')}")
    marks = []
    for v in versions:
        tag = " (current)" if cur and v == cur["version"] else ""
        marks.append(f"v{v}{tag}")
    print(f"versions:     {', '.join(marks)}")
    if cur is not None:
        b = rule_brief(rv, args.rule_id)
        print(f"status:       {b['status']}" + (f" (by {b['approved_by']} {b['approved_at']})" if b["approved_by"] else ""))
        print(f"reviewed:     {b['reviewed']:,} / {b['total']:,} rows · open wrong {b['open_wrong']} · open missing "
              f"{b['open_missing']} · questions {b['questions']}")
        print(f"fill:         {b['fill']['found']:,} of {b['fill']['rows']:,} rows have a value")
        print("signals:      " + (", ".join(f"{k} {n:,}" for k, n in b["signals"].items()) or "none"))
    return 0


def format_annotation(ctx: Ctx, a: dict, i: int | None = None) -> str:
    head = a["course_key"] or a["page_title"] or a["page_stem"]
    verdict = (a["verdict"] or a["type"]).upper()
    state = STATE_LABEL.get(a["state"], a["state"])
    lines = [f"{'' if i is None else f'{i}. '}{verdict} — {head} — {state}{' (re-attached)' if a['reattached'] else ''}"
             f"{' · page question' if a['page_level'] else ''}"]
    pad = "   "
    lines.append(f"{pad}by {a['author']} on {a['at'][:10]} · {a['annotation_id']}")
    if a["page_stem"]:
        lines.append(f"{pad}page: {page_ref(ctx, a['page_stem'])}")
        if a["url"]:
            lines.append(f"{pad}live: {a['url']}")
    if a["occurrence_key"]:
        lines.append(f"{pad}occurrence css_path: {a['occurrence_css_path'] or a['occurrence_key'].split('@', 1)[1]}")
    if a["value_seen"] is not None:
        lines.append(f"{pad}value seen (v{a['rule_version_seen']}): {json.dumps(a['value_seen'], ensure_ascii=False)}")
    if a["has_row"] and a["rule_kind"] != "property":
        lines.append(f"{pad}current (v{a['rule_version']}): the rule still finds it"
                     + (f" ({a['current_value']})" if a["current_value"] else ""))
    elif a["has_row"]:
        same = a["value_seen"] is not None and norm(a["value_seen"]) == norm(a["current_value"])
        lines.append(f"{pad}current value (v{a['rule_version']}): "
                     + ("same as seen" if same else json.dumps(a["current_value"], ensure_ascii=False)))
        if a["current_css_path"]:
            lines.append(f"{pad}current css_path: {a['current_css_path']}")
    exp = a["expected"]
    if exp:
        lines.append(f"{pad}expected: {json.dumps(exp['text'], ensure_ascii=False)}")
        if exp.get("segments"):  # the value is in several pieces on the page, joined by line breaks above
            for i, s in enumerate(exp["segments"], 1):  # an `out` piece: text the value has but must not
                what = "NOT in the answer" if s.get("polarity") == "out" else "expected piece"
                lines.append(f"{pad}{what} {i}: {s['css_path']} chars {s['char_start']}–{s['char_end']}"
                             f" (DOM textContent offsets): {json.dumps(s['text'], ensure_ascii=False)}")
        elif exp.get("css_path"):
            lines.append(f"{pad}expected at: {exp['css_path']} chars {exp['char_start']}–{exp['char_end']}"
                         " (DOM textContent offsets)")
    if a["note"]:
        lines.append(f"{pad}note: {a['note']}")
    for c in a["comments"]:
        on = f" on {json.dumps(c['on'], ensure_ascii=False)}" if c.get("on") else ""  # the text it is about
        lines.append(f"{pad}comment ({c['author']}, {c['at'][:10]}, {c['annotation_id']}){on}: {c['note']}")
    return "\n".join(lines)


def cmd_rule_annotations(args) -> int:
    ctx = Ctx.from_args(args)
    rv = current_review(ctx)
    rule = rule_or_error(rv, args.rule_id)
    anns = rule_annotations(rv, args.rule_id)
    if args.open:
        anns = [a for a in anns if a["open"]]
    print(f"{args.rule_id} v{rule['version']} · {_header(ctx, rv)}")
    n_open = sum(a["open"] for a in anns)
    print(f"{len(anns)} annotation(s){' that still need work' if args.open else f', {n_open} still need work'}\n")
    for i, a in enumerate(anns, 1):
        print(format_annotation(ctx, a, i))
        print()
    return 0


# =====================================================================================================
# rule draft
# =====================================================================================================
DRAFT_FIELDS = ("rule_id", "kind", "ctdl_property", "property_label", "definition", "what", "how", "why", "examples")


def draft_of(ctx: Ctx, rule_ids: list[str], for_catalog: str | None = None) -> dict:
    """The rules as an editable draft. `for_catalog`: a template for another catalog's first ruleset (every rule
    of this one, with its settings), to be adapted to that catalog's pages."""
    v = ctx.latest_ruleset()
    rs, rules = ctx.ruleset_rules(v)
    rule_ids = rule_ids or ordered_rule_ids(rules)
    out = []
    for rid in rule_ids:
        if rid not in rules:
            raise UserError(f"no rule {rid!r} in ruleset v{v} (a new rule: write it into the draft by hand)")
        r = rules[rid]
        out.append({k: r.get(k) for k in DRAFT_FIELDS} | {"examples": r.get("examples") or []})
    if for_catalog:
        keep = ("content_root", "page_title", "course_key_rule", "signals")
        settings = {k: rs["settings"][k] for k in keep if k in rs["settings"]}
        if "course_key_rule" in settings:  # only the record locators this ruleset still has
            settings["course_key_rule"] = {loc: f for loc, f in settings["course_key_rule"].items() if loc in rules}
        return {"catalog": for_catalog, "base_ruleset": None, "template": f"{ctx.catalog} ruleset v{v}",
                "settings": settings, "rules": out}
    return {"catalog": ctx.catalog, "base_ruleset": v, "rules": out}


def cmd_rule_draft(args) -> int:
    ctx = Ctx.from_args(args)
    if not args.rule_ids and not args.all:
        raise UserError("name the rules to draft, or --all")
    print(json.dumps(draft_of(ctx, [] if args.all else args.rule_ids, args.for_catalog), indent=2, ensure_ascii=False))
    return 0


# =====================================================================================================
# rule try / publish
# =====================================================================================================
def read_draft(path: str) -> dict:
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text()
    except FileNotFoundError:
        raise UserError(f"no draft file {path}") from None
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UserError(f"{path}: not valid JSON ({exc})") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("rules", []), list):
        raise UserError(f"{path}: a draft is {{\"catalog\", \"base_ruleset\", \"rules\": [...], \"settings\"?}}")
    return doc


def _validate_definition(rid: str, rule: dict) -> None:
    """Catch broken regexes and selectors before running anything (worker errors are hard to read)."""
    d = rule["definition"]
    if not isinstance(d, dict):
        raise UserError(f"{rid}: definition must be an object")
    for key in ("regex", "url_regex"):
        if d.get(key):
            try:
                re.compile(d[key])
            except re.error as exc:
                raise UserError(f"{rid}: definition.{key} is not a valid regex: {exc}") from None
    multiple = d.get("multiple") if isinstance(d.get("multiple"), dict) else {}
    for key, pattern in (("multiple.regex", multiple.get("regex")), ("multiple.keep", multiple.get("keep"))):
        if pattern:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise UserError(f"{rid}: definition.{key} is not a valid regex: {exc}") from None
    sels = [d.get(k) for k in ("selector", "repeat", "requires_selector", "forbids_selector")]
    if d.get("until") and not str(d["until"]).isalnum():
        sels.append(d["until"])
    if isinstance(d.get("repeat_filter"), dict):
        sels.append(d["repeat_filter"].get("selector"))
        if d["repeat_filter"].get("regex"):
            try:
                re.compile(d["repeat_filter"]["regex"])
            except re.error as exc:
                raise UserError(f"{rid}: repeat_filter.regex is not a valid regex: {exc}") from None
    for sel in sels:
        if sel:
            try:
                engine.select(engine.parse(b"<html><body></body></html>"), sel)
            except Exception as exc:  # cssselect raises several error types
                raise UserError(f"{rid}: {sel!r} is not a valid CSS selector: {exc}") from None


def check_examples(drafted: dict[str, dict]) -> list[str]:
    """Each example of a drafted property rule: its definition (regex + group + transforms + map) applied to `input`
    must give `output`."""
    failures = []
    for rid in sorted(drafted):
        r = drafted[rid]
        d = r["definition"]
        if r["kind"] != "property" or d.get("rule_type") in (*model.DERIVED_RULE_TYPES, "none"):
            continue
        for i, ex in enumerate(r.get("examples") or [], 1):
            if not isinstance(ex, dict) or "input" not in ex:
                failures.append(f"{rid} example {i}: needs \"input\" and \"output\"")
                continue
            got = engine.values_of_text(d, ex["input"])
            value = got if d.get("multiple") else (got[0] if got else None)
            want = ex.get("output")
            if (value or "") != (want or "") and not (d.get("multiple") and value == [] and not want):
                failures.append(f"{rid} example {i}: got {json.dumps(value, ensure_ascii=False)}, "
                                f"expected {json.dumps(ex.get('output'), ensure_ascii=False)}")
    return failures


def plan_draft(ctx: Ctx, doc: dict, warn=lambda m: print(m, file=sys.stderr)) -> dict:
    """Merge a draft into the latest ruleset and assign versions (nothing is written)."""
    if doc.get("catalog") and ctx.catalog != doc["catalog"] and info(ctx.catalog)["short"] != doc["catalog"]:
        raise UserError(f"the draft is for {doc['catalog']}, not {ctx.catalog}")
    if ctx.ruleset_versions():
        latest = ctx.latest_ruleset()
        rs, base = ctx.ruleset_rules(latest)
    else:  # the catalog's first rules (added from the picker): every rule in the draft is new
        latest, rs, base = 0, {"version": None, "parent_version": None, "settings": None}, {}
    if latest and doc.get("base_ruleset") not in (None, latest):
        warn(f"note: the draft was made from ruleset v{doc['base_ruleset']}; merging it into the latest, v{latest}")
    drafts: dict[str, dict] = {}
    for item in doc.get("rules", []):
        item = model.current_kind(item)
        rid = item.get("rule_id")
        if not rid or "definition" not in item:
            raise UserError("each rule in a draft needs rule_id and definition")
        if rid in drafts:
            raise UserError(f"{rid} appears twice in the draft")
        ignored = sorted(set(item) - set(DRAFT_FIELDS))
        if ignored:
            warn(f"note: {rid}: ignoring {', '.join(ignored)} (golden-datasets assigns versions and hashes)")
        old = base.get(rid)
        if old is None and not item.get("kind"):
            raise UserError(f"{rid} is a new rule: give its kind (page, locator or property)")
        if old is not None and item.get("kind") not in (None, old["kind"]):
            raise UserError(f"{rid}: the kind of an existing rule can't change ({old['kind']})")
        merged = {k: old.get(k) for k in DRAFT_FIELDS if old is not None and k in old}
        merged.update({k: item[k] for k in DRAFT_FIELDS if k in item})
        merged.setdefault("examples", [])
        _validate_definition(rid, merged)
        drafts[rid] = merged
    planned = rulesets.plan_versions(ctx, drafts, base)
    if rs["settings"] is None:
        settings = rulesets.first_settings({**base, **planned}, doc.get("settings"))
    else:
        settings = {**rs["settings"], **(doc.get("settings") or {})}
    for rid, r in planned.items():
        if rid in base and r["content_hash"] == base[rid]["content_hash"] and \
                any(drafts[rid].get(k) != base[rid].get(k) for k in ("what", "how", "why", "examples")):
            warn(f"note: {rid}: definition unchanged, so no new version (what/how/why/examples describe a "
                 "definition; they change only with it)")
    rules = {**base, **planned}
    rulesets.validate_ruleset(rules)
    if not latest and not rules:
        raise UserError("the draft has no rules; a catalog's first ruleset needs at least a page rule, a record locator "
                        "and property rules")
    changed = sorted(rid for rid, r in rules.items()
                     if rid not in base or base[rid]["content_hash"] != r["content_hash"])
    return {"latest": latest, "ruleset": rs, "base": base, "drafts": drafts, "rules": rules, "settings": settings,
            "changed": changed, "settings_changed": settings != rs["settings"],
            "example_failures": check_examples(drafts)}


def read_inferred(path: str | None) -> list[dict]:
    """`inferred.json` (one-rule-runs spec §4): [{rule, course, annotation, value}], the values Claude worked out for
    courses marked wrong with no expected value. `path` None: `./inferred.json` if there is one."""
    p = Path(path) if path else Path("inferred.json")
    if not p.is_file():
        if path:
            raise UserError(f"no inferred values file {path}")
        return []
    try:
        doc = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise UserError(f"{p}: not valid JSON ({exc})") from None
    items = doc.get("inferred") if isinstance(doc, dict) else doc
    if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
        raise UserError(f"{p}: a list of {{rule, course, annotation, value}}")
    for i, x in enumerate(items):
        missing = [k for k in ("rule", "course", "annotation", "value") if k not in x]
        if missing or not isinstance(x["value"], str):
            raise UserError(f"{p}[{i}]: needs rule, course, annotation and value (text; \"\" for empty)")
    return items


def check_inferred(review: Review, inferred: list[dict]) -> list[str]:
    """Each inferred value must answer a live ✕ on that rule and course that has no expected value."""
    out = []
    for i, x in enumerate(inferred):
        e = review.by_id.get(x["annotation"])
        live = e is not None and any(ev is e for ev in review.live)
        t = (e or {}).get("target") or {}
        if not live or e["type"] != "verdict" or e.get("verdict") != "wrong":
            out.append(f"inferred[{i}]: {x['annotation']} is not a live wrong verdict")
        elif t.get("rule_id") != x["rule"] or (t.get("course_key") and t["course_key"] != x["course"]):
            out.append(f"inferred[{i}]: {x['annotation']} is on {t.get('rule_id')} {t.get('course_key')}, "
                       f"not {x['rule']} {x['course']}")
        elif (e.get("expected") or {}).get("text") is not None:
            out.append(f"inferred[{i}]: {x['annotation']} already has an expected value")
    return out


def evaluate(ctx: Ctx, plan: dict, log=lambda m: None, inferred: list[dict] | None = None) -> dict:
    """Run the planned ruleset over the whole crawl (every rule, every page: the whole golden suite, one-rule-runs
    spec §3.3), score the rules that changed and check every golden value. Writes nothing."""
    from . import suite
    from .report import rule_names

    t0 = time.perf_counter()
    latest = plan["latest"]
    parent_ext = ctx.extraction_for(latest) or extract.pick_parent(ctx, plan["ruleset"])
    result = extract.compute(ctx, plan["rules"], plan["settings"], None, log=log)
    t_compute = time.perf_counter() - t0
    draft = Snapshot(ctx, "draft", tables=result["tables"], ruleset={"settings": plan["settings"], "version": None},
                     rules=plan["rules"], meta={"ruleset_version": None, "parent_extraction": parent_ext})
    events = LOADER.log(ctx).events()
    review = Review(draft, events)
    problems = check_inferred(review, inferred or [])
    if problems:
        raise UserError("inferred.json has problems:\n  " + "\n  ".join(problems))
    cards = []
    base_snap = LOADER.snapshot(ctx, parent_ext) if parent_ext else None
    if base_snap is not None:
        ids = set(plan["drafts"]) | set(scorecard.changed_rules(base_snap, draft))
        for rid in ordered_rule_ids({r: plan["rules"].get(r) or base_snap.rules[r] for r in ids}):
            cards.append(scorecard.rule_scorecard(rid, base_snap, draft, review))
    else:
        for rid in ordered_rule_ids(plan["drafts"]):
            cards.append(scorecard.rule_scorecard(rid, None, draft, review))
    totals = {k: sum(c["annotated"][k] for c in cards) for k in ("fixed", "still_wrong", "newly_wrong", "unchanged")}
    s = suite.score(base_snap, draft, events, inferred, drafted=plan["changed"])
    names = rule_names({**(base_snap.rules if base_snap else {}), **plan["rules"]})
    produced = {}
    for x in inferred or []:
        row = next((r for r in draft.rows(x["rule"]) if r.get("course_key") == x["course"]), None) \
            if x["rule"] in draft.rules else None
        produced.setdefault(x["rule"], {})[x["course"]] = row["value"] if row else None
    return {"parent_extraction": parent_ext, "result": result, "cards": cards, "totals": totals, "snapshot": draft,
            "suite": s, "suite_lines": suite.lines(s, names), "names": names, "inferred": inferred or [],
            "inferred_values": produced,
            "compute_s": round(t_compute, 2), "total_s": round(time.perf_counter() - t0, 2)}


def _print_cards(plan: dict, ev: dict, b_label) -> None:
    for c in ev["cards"]:
        print(scorecard.format_card(c, b_label(c)))
        newly = [r for r in c["annotated_rows"] if r["outcome"] == "newly wrong"]
        still = [r for r in c["annotated_rows"] if r["outcome"] == "still wrong"]
        for title, rows in (("newly wrong (marked correct, value changed)", newly), ("still wrong", still)):
            if rows:
                print(f"  {title}: " + ", ".join(r["course_key"] or r["page_stem"] for r in rows))
        print()
    t = ev["totals"]
    print(f"total: fixed {t['fixed']}, still wrong {t['still_wrong']}, newly wrong {t['newly_wrong']}, "
          f"unchanged {t['unchanged']}")
    sys.stdout.flush()


def _print_first(plan: dict, ev: dict) -> None:
    """A first ruleset has nothing to compare with: what each rule finds instead."""
    snap = ev["snapshot"]
    print(f"{'rule':<28} {'kind':<8} {'rows':>7} {'with a value':>13}  signals")
    for rid in ordered_rule_ids(plan["rules"]):
        f = snap.fill(rid)
        sig = ", ".join(f"{k} {n:,}" for k, n in sorted(snap.signal_counts.get(rid, {}).items(), key=lambda kv: -kv[1]))
        print(f"{rid:<28} {plan['rules'][rid]['kind']:<8} {f['rows']:>7,} {f['found']:>13,}  {sig or '—'}")
    if not any(snap.fill(r)["rows"] for r in plan["rules"] if plan["rules"][r]["kind"] == "locator"):
        print("\nno record locator finds a course: check the page rules' url_regex / requires_selector against "
              "the saved pages (`golden-datasets sql \"SELECT url, title FROM pages LIMIT 50\"`)")
    print()
    sys.stdout.flush()


def _label(plan: dict, prefix: str):
    def f(card: dict) -> str:
        r = plan["rules"].get(card["rule_id"])
        if card["rule_id"] in plan["changed"]:
            return f"{prefix} (v{r['version']})" if prefix == "draft" else f"v{r['version']}"
        return f"v{r['version']} (unchanged rule)" if r else "removed"
    return f


def _report_examples(failures: list[str]) -> None:
    print(f"{len(failures)} example(s) fail; fix the definition or the examples:", file=sys.stderr)
    for f in failures:
        print(f"  {f}", file=sys.stderr)


def save_last_try(ctx: Ctx, ev: dict, base: int, published: int | None) -> None:
    """In a Studio run (`GOLDEN_DATASETS_RUN`, set by the run folder's settings), keep this try for the run's report
    (report.py): its last `rule try` or `rule publish`, with the whole suite and the inferred values."""
    from .report import last_try_doc

    run_id = os.environ.get("GOLDEN_DATASETS_RUN")
    if run_id:
        d = layout.agent_run_dir(ctx.catalog, run_id)
        ctx.root.write_json(f"{d}/last-try.json", last_try_doc(ev, base, published))
        if ev["inferred"]:
            ctx.root.write_json(f"{d}/inferred.json", ev["inferred"])


def run_note(ctx: Ctx, text: str) -> None:
    """In a Studio run, one progress line the Studio shows (publishing waits, rebases)."""
    run_id = os.environ.get("GOLDEN_DATASETS_RUN")
    if run_id:
        from .agent_runs import AgentRuns

        AgentRuns(ctx).log(run_id, "note", text, by="golden-datasets")


def _print_suite(ev: dict) -> None:
    for line in ev["suite_lines"]:
        print(line)
    print()


def cmd_rule_try(args) -> int:
    t0 = time.perf_counter()
    ctx = Ctx.from_args(args)
    plan = plan_draft(ctx, read_draft(args.draft))
    if plan["example_failures"]:
        _report_examples(plan["example_failures"])
        return 1
    if not plan["changed"] and not plan["settings_changed"]:
        print(f"nothing to try: no definition or setting differs from ruleset v{plan['latest']}")
        return 0
    ev = evaluate(ctx, plan, log=lambda m: print(m, file=sys.stderr), inferred=read_inferred(args.inferred))
    elapsed = time.perf_counter() - t0
    if plan["latest"]:
        save_last_try(ctx, ev, plan["latest"], None)
    if args.json:
        s = ev["suite"]
        print(json.dumps({"catalog": ctx.catalog, "base_ruleset": plan["latest"],
                          "base_extraction": ev["parent_extraction"], "changed_rules": plan["changed"],
                          "planned_versions": {r: plan["rules"][r]["version"] for r in plan["changed"]},
                          "totals": ev["totals"], "cards": ev["cards"],
                          "suite": {k: s[k] for k in ("rules", "golden", "now_right", "inferred", "got_worse",
                                                      "regressions", "changed")} | {"line": ev["suite_lines"][0]},
                          "rerun_rules": ev["result"]["meta"]["rerun_rules"],
                          "elapsed_s": round(elapsed, 2)}, indent=2, ensure_ascii=False))
        return 0
    base = f"ruleset v{plan['latest']} ({ev['parent_extraction']})" if plan["latest"] else "no ruleset yet"
    print(f"rule try on {base} + draft, {info(ctx.catalog)['name']}, "
          f"{ev['result']['meta']['pages_total']:,} pages\n")
    if plan["latest"]:
        _print_suite(ev)
        _print_cards(plan, ev, _label(plan, "draft"))
    else:
        _print_first(plan, ev)
    meta = ev["result"]["meta"]
    print(f"reran {len(meta['rerun_rules'])} rules on {meta['rerun_pages']:,} pages; nothing written")
    print(f"elapsed {elapsed:.1f} s (run {ev['compute_s']:.1f} s)")
    return 0


def _record_publish(ctx: Ctx, ev: dict, plan: dict, version: int, rebased: str | None) -> None:
    """In a Studio run: what this publish changed, kept for the report (`published.json`, oldest first)."""
    run_id = os.environ.get("GOLDEN_DATASETS_RUN")
    if not run_id:
        return
    path = f"{layout.agent_run_dir(ctx.catalog, run_id)}/published.json"
    try:
        doc = ctx.root.read_json(path)
    except FileNotFoundError:
        doc = {"publishes": []}
    doc["publishes"].append({"version": version, "base": plan["latest"], "rebased": rebased,
                             "changed_rules": plan["changed"], "values_changed": ev["suite"]["changed"],
                             "suite": {k: ev["suite"][k] for k in ("rules", "golden", "now_right", "inferred",
                                                                    "got_worse")}})
    ctx.root.write_json(path, doc)


def _run_record(ctx: Ctx) -> dict:
    """This run (in a Studio run), for the ruleset's record of who published it."""
    run_id = os.environ.get("GOLDEN_DATASETS_RUN")
    if not run_id:
        return {}
    from .agent_runs import AgentRuns

    run = AgentRuns(ctx).run(run_id) or {}
    return {"run_id": run_id, "started_by": run.get("started_by")}


def cmd_rule_publish(args) -> int:
    from .check import check_before_write
    from .publishing import publish_lock, rebase
    from .report import rule_names

    t0 = time.perf_counter()
    ctx = Ctx.from_args(args)
    doc = read_draft(args.draft)
    inferred = read_inferred(args.inferred)
    run = _run_record(ctx)
    waited = []

    def say(m: str) -> None:
        print(m, file=sys.stderr)
        if not waited:
            run_note(ctx, f"Publishing: {m.split(' (')[0]}")
        waited.append(m)

    with publish_lock(ctx, run.get("run_id"), args.by, say=say):
        ctx.invalidate()
        rebased = None
        if ctx.ruleset_versions():
            _, latest_rules = ctx.ruleset_rules(ctx.latest_ruleset())
            try:
                doc, rebased = rebase(ctx, doc, rule_names(latest_rules))
            except UserError as exc:
                run_note(ctx, f"Redoing on v{ctx.latest_ruleset()}: {exc}")
                print(f"refusing to publish (nothing written): {exc}", file=sys.stderr)
                return 2
        plan = plan_draft(ctx, doc, warn=lambda m: None if rebased else print(m, file=sys.stderr))
        if plan["example_failures"]:
            _report_examples(plan["example_failures"])
            print("refusing to publish: examples fail (nothing written)", file=sys.stderr)
            return 2
        if not plan["changed"] and not plan["settings_changed"]:
            print(f"nothing to publish: no definition or setting differs from ruleset v{plan['latest']} (no-op)")
            return 0
        if rebased:
            print(rebased)
            run_note(ctx, rebased)
        ev = evaluate(ctx, plan, log=lambda m: print(m, file=sys.stderr), inferred=inferred)
        version = plan["latest"] + 1
        if plan["latest"]:
            _print_suite(ev)
            _print_cards(plan, ev, _label(plan, "publish"))
        else:
            _print_first(plan, ev)
        worse = ev["suite"]["got_worse"]
        if worse and not args.force:
            print(f"\nrefusing to publish: {worse} golden value(s) that were right got worse (nothing written). "
                  "Change the draft so they don't, or ask the expert; --force overrides.", file=sys.stderr)
            if plan["latest"]:
                save_last_try(ctx, ev, plan["latest"], None)
            return 2
        check_before_write(ctx, {"settings": plan["settings"]}, plan["rules"], ev["result"]["tables"])
        names = ", ".join(f"{r} v{plan['rules'][r]['version']}" for r in plan["changed"]) or "settings only"
        note = args.note or f"{names} (rule publish)"
        t_up = time.perf_counter()
        extra = {k: v for k, v in run.items() if v} | ({"forced": True, "got_worse": worse} if worse else {})
        published = rulesets.publish(ctx, plan["rules"], plan["settings"], note, args.by, extra=extra or None)
        if published is None:
            print("nothing changed: no-op")
            return 0
        if published["version"] != version:
            raise UserError(f"published ruleset v{published['version']}, but the draft was run against "
                            f"v{plan['latest']}; run `golden-datasets extract --ruleset {published['version']}`")
        ext = extract.next_extraction_id(ctx, version, again=False)
        meta = extract.write_extraction(ctx, ext, version, ev["parent_extraction"], ev["result"], args.by)
    if plan["latest"]:
        save_last_try(ctx, ev, plan["latest"], version)
        _record_publish(ctx, ev, plan, version, rebased)
    upload = time.perf_counter() - t_up
    print(f"\npublished ruleset v{version}" + (f" (parent v{plan['latest']})" if plan["latest"] else " (the first)")
          + f": {names}" + (". FORCED: golden values got worse" if worse else ""))
    rows = ", ".join(f"{k.split('.')[0]} {v['rows']:,}" for k, v in meta["files"].items())
    print(f"extraction {ext} (parent {meta['parent_extraction']}): {rows}")
    print(f"  reran {len(meta['rerun_rules'])} rules on {meta['rerun_pages']:,} pages")
    print(f"upload {upload:.1f} s, total {time.perf_counter() - t0:.1f} s")
    return 0


def cmd_rule_downstream(args) -> int:
    """The rules that read each rule, directly or not (one-rule-runs spec §3.2): the blast radius of an edit."""
    from .publishing import downstream
    from .report import rule_names

    ctx = Ctx.from_args(args)
    _, rules = ctx.ruleset_rules(ctx.latest_ruleset())
    names = rule_names(rules)
    for rid in args.rule_ids:
        if rid not in rules:
            raise UserError(f"no rule {rid!r} in ruleset v{ctx.latest_ruleset()}")
        down = downstream(rules, rid)
        reads = rules[rid].get("depends_on") or model.dependencies(rules[rid])
        print(f"{names[rid]} ({rid}) reads: " + (", ".join(f"{names.get(r, r)} ({r})" for r in reads) or "nothing"))
        print(f"  read by {len(down)} rule{'' if len(down) == 1 else 's'}"
              + (": " + ", ".join(f"{names.get(r, r)} ({r})" for r in down) if down else ""))
    return 0


def cmd_ruleset_revert(args) -> int:
    """Publish one new version with every rule a version changed back to its previous version (spec §3.6)."""
    from .publishing import revert

    ctx = Ctx.from_args(args)
    try:
        out = revert(ctx, args.version, args.by, say=lambda m: print(m, file=sys.stderr))
    except FileNotFoundError as exc:
        raise UserError(str(exc)) from None
    print(out["suite"]["line"])
    listed = ", ".join(f"{r['name']} v{r['from_version']} to v{r['to_version']}" if r["to_version"]
                       else f"{r['name']} removed" for r in out["rules"])
    print(f"published ruleset v{out['version']}, reverting v{out['reverted']}: {listed}")
    print(f"extraction {out['extraction']}")
    return 0


# =====================================================================================================
# pages get / sample
# =====================================================================================================
def resolve_stems(ctx: Ctx, wanted: list[str]) -> list[str]:
    """Exact page stems, or any unique part of one (e.g. `course-geog222`)."""
    stems = sorted(p["page_stem"] for p in ctx.pages())
    have = set(stems)
    out = []
    for w in wanted:
        w = w.removesuffix(".html")
        if w in have:
            out.append(w)
            continue
        hits = [s for s in stems if w in s]
        if len(hits) == 1:
            out.append(hits[0])
        elif not hits:
            raise UserError(f"no saved page matches {w!r}")
        else:
            raise UserError(f"{w!r} matches {len(hits)} pages, e.g. {', '.join(hits[:3])}; be more specific")
    return out


def cmd_pages_get(args) -> int:
    ctx = Ctx.from_args(args)
    stems = resolve_stems(ctx, args.stems)
    url = {p["page_stem"]: p["url"] for p in ctx.pages()}
    dest = Path(args.to).expanduser() if args.to else None
    if dest:
        dest.mkdir(parents=True, exist_ok=True)
    for stem in stems:
        local = ctx.page_path(stem)
        if dest:
            shutil.copyfile(local, dest / f"{stem}.html")
            meta = layout.page_meta(ctx.catalog, ctx.crawl, stem)
            if ctx.root.exists(meta):
                shutil.copyfile(ctx.root.local_path(meta), dest / f"{stem}.meta.json")
            local = dest / f"{stem}.html"
        print(f"{local}\t{url.get(stem, '')}")
    return 0


def sample_rows(rv: Review, rule_id: str, signal: str | None, n: int) -> list[dict]:
    rule_or_error(rv, rule_id)
    if signal and signal not in SIGNALS:
        raise UserError(f"unknown signal {signal!r} (signals: {', '.join(sorted(SIGNALS))})")
    out = []
    for row, _ in rv.ordered(rule_id):
        names = {s["signal"] for s in row["signals"]}
        if signal and signal not in names:
            continue
        out.append({**row, "signal_names": sorted(names)})
        if len(out) >= n:
            break
    return out


def cmd_pages_sample(args) -> int:
    ctx = Ctx.from_args(args)
    rv = current_review(ctx)
    rows = sample_rows(rv, args.rule, args.signal, args.n)
    print(f"{args.rule}{' · signal ' + args.signal if args.signal else ''} · {len(rows)} row(s), Rules tab order · "
          f"extraction {rv.snap.ext}")
    for r in rows:
        print(page_ref(ctx, r["page_stem"]))
        print(f"   {r['course_key'] or '—'} · {short(r['value'], 120)!s}"
              + (f" · signals: {', '.join(r['signal_names'])}" if r["signal_names"] else ""))
    return 0
