"""The Claude loop (spec §3.1, §6 "For Claude"): `rule list / show / annotations / draft / try / publish` and
`pages get / sample`.

Claude Code works only through these commands, never on the storage root directly:
- `rule show` / `rule annotations` / `pages get` / `pages sample` give it the context;
- `rule draft R… > draft.json` gives it the current versions to edit (definition + what / how / why + examples);
- `rule try draft.json` reruns the draft over the whole crawl and prints the scorecard (writes nothing);
- `rule publish draft.json` writes the new rule versions, a ruleset version and its extraction, and refuses when a
  value marked correct changes (unless `--force`).

`golden-datasets` assigns versions and hashes (`rulesets.plan_versions`), never the draft.

The commands come first, section by section; the shared reads (also used by prompt.py and the server) are last.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass
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
DRAFT_FIELDS = ("rule_id", "kind", "ctdl_property", "property_label", "definition", "what", "how", "why", "examples")
PAD = "   "


# =====================================================================================================
# rule list / show / annotations
# =====================================================================================================
def cmd_rule_list(args) -> int:
    ctx = Ctx.from_args(args)
    rv = current_review(ctx)
    print(_header(ctx, rv))
    lines = [("kind", "rule", "ver", "status", "reviewed", "fill", "signals")]
    lines += [_rule_list_line(rv, rid) for rid in ordered_rule_ids(rv.snap.rules)]
    widths = [max(len(x[i]) for x in lines) for i in range(6)]
    for x in lines:
        print("  ".join(f"{c:<{widths[i]}}" if i not in (2, 4, 5) else f"{c:>{widths[i]}}"
                        for i, c in enumerate(x[:6])) + "  " + x[6])
    return 0


def cmd_rule_show(args) -> int:
    ctx = Ctx.from_args(args)
    rv = current_review(ctx)
    cur = rv.snap.rules.get(args.rule_id)
    versions = ctx.rule_versions(args.rule_id)
    if cur is None and not versions:
        rule_or_error(rv, args.rule_id)
    version = _shown_version(args, cur, versions)
    r = ctx.rule(args.rule_id, version)
    _print_rule_head(ctx, rv, args.rule_id, r, version, cur)
    _print_rule_body(r)
    _print_versions(versions, cur)
    if cur is not None:
        _print_rule_brief(rule_brief(rv, args.rule_id))
    return 0


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


def _header(ctx: Ctx, rv: Review) -> str:
    return (f"{info(ctx.catalog)['name']} · {ctx.catalog} · crawl {ctx.crawl} · ruleset v{rv.snap.ruleset_version}"
            f" · extraction {rv.snap.ext}")


def _rule_list_line(rv: Review, rid: str) -> tuple[str, ...]:
    r = rv.snap.rules[rid]
    b = rule_brief(rv, rid)
    sig = ", ".join(f"{k} {n:,}" for k, n in list(b["signals"].items())[:3])
    return (r["kind"], rid, f"v{r['version']}", b["status"], f"{b['reviewed']:,} / {b['total']:,}",
            f"{b['fill']['found']:,} / {b['fill']['rows']:,}", sig or "—")


def _shown_version(args, cur: dict | None, versions: list[int]) -> int:
    version = args.version or (cur["version"] if cur else versions[-1])
    if version not in versions:
        raise UserError(f"{args.rule_id} has no version {version} (versions: {', '.join(map(str, versions))})")
    return version


def _print_rule_head(ctx: Ctx, rv: Review, rule_id: str, r: dict, version: int, cur: dict | None) -> None:
    print(f"{rule_id} v{version} — {r['kind']} rule"
          + (f", {r['property_label']} ({r.get('ctdl_property') or 'no CTDL term'})" if r.get("property_label") else ""))
    print(_header(ctx, rv))
    if cur is None:
        print(f"  not in the current ruleset (v{rv.snap.ruleset_version})")
    elif version != cur["version"]:
        print(f"  not the current version: v{cur['version']} is (status, fill and signals below are for v{cur['version']})")


def _print_rule_body(r: dict) -> None:
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


def _print_versions(versions: list[int], cur: dict | None) -> None:
    marks = [f"v{v}" + (" (current)" if cur and v == cur["version"] else "") for v in versions]
    print(f"versions:     {', '.join(marks)}")


def _print_rule_brief(b: dict) -> None:
    print(f"status:       {b['status']}" + (f" (by {b['approved_by']} {b['approved_at']})" if b["approved_by"] else ""))
    print(f"reviewed:     {b['reviewed']:,} / {b['total']:,} rows · open wrong {b['open_wrong']} · open missing "
          f"{b['open_missing']} · questions {b['questions']}")
    print(f"fill:         {b['fill']['found']:,} of {b['fill']['rows']:,} rows have a value")
    print("signals:      " + (", ".join(f"{k} {n:,}" for k, n in b["signals"].items()) or "none"))


def format_annotation(ctx: Ctx, a: dict, i: int | None = None) -> str:
    lines = [_annotation_title(a, i), f"{PAD}by {a['author']} on {a['at'][:10]} · {a['annotation_id']}"]
    lines += _where_lines(ctx, a)
    lines += _value_lines(a)
    lines += _expected_lines(a["expected"])
    if a["note"]:
        lines.append(f"{PAD}note: {a['note']}")
    lines += [_comment_line(c) for c in a["comments"]]
    return "\n".join(lines)


def _annotation_title(a: dict, i: int | None) -> str:
    head = a["record_external_identifier"] or a["page_title"] or a["page_stem"]
    verdict = (a["verdict"] or a["type"]).upper()
    state = STATE_LABEL.get(a["state"], a["state"])
    return (f"{'' if i is None else f'{i}. '}{verdict} — {head} — {state}{' (re-attached)' if a['reattached'] else ''}"
            f"{' · page question' if a['page_level'] else ''}")


def _where_lines(ctx: Ctx, a: dict) -> list[str]:
    lines = []
    if a["page_stem"]:
        lines.append(f"{PAD}page: {page_ref(ctx, a['page_stem'])}")
        if a["url"]:
            lines.append(f"{PAD}live: {a['url']}")
    if a["occurrence_key"]:
        lines.append(f"{PAD}occurrence css_path: {a['occurrence_css_path'] or a['occurrence_key'].split('@', 1)[1]}")
    return lines


def _value_lines(a: dict) -> list[str]:
    lines = []
    if a["value_seen"] is not None:
        lines.append(f"{PAD}value seen (v{a['rule_version_seen']}): {json.dumps(a['value_seen'], ensure_ascii=False)}")
    if a["has_row"] and a["rule_kind"] != "property":
        lines.append(f"{PAD}current (v{a['rule_version']}): the rule still finds it"
                     + (f" ({a['current_value']})" if a["current_value"] else ""))
    elif a["has_row"]:
        same = a["value_seen"] is not None and norm(a["value_seen"]) == norm(a["current_value"])
        lines.append(f"{PAD}current value (v{a['rule_version']}): "
                     + ("same as seen" if same else json.dumps(a["current_value"], ensure_ascii=False)))
        if a["current_css_path"]:
            lines.append(f"{PAD}current css_path: {a['current_css_path']}")
    return lines


def _expected_lines(exp: dict | None) -> list[str]:
    if not exp:
        return []
    lines = [f"{PAD}expected: {json.dumps(exp['text'], ensure_ascii=False)}"]
    if exp.get("segments"):  # the value is in several pieces on the page, joined by line breaks above
        lines += [_segment_line(i, s) for i, s in enumerate(exp["segments"], 1)]
    elif exp.get("css_path"):
        lines.append(f"{PAD}expected at: {exp['css_path']} chars {exp['char_start']}–{exp['char_end']}"
                     " (DOM textContent offsets)")
    return lines


def _segment_line(i: int, s: dict) -> str:
    what = "NOT in the answer" if s.get("polarity") == "out" else "expected piece"  # `out`: text the value must not have
    return (f"{PAD}{what} {i}: {s['css_path']} chars {s['char_start']}–{s['char_end']}"
            f" (DOM textContent offsets): {json.dumps(s['text'], ensure_ascii=False)}")


def _comment_line(c: dict) -> str:
    on = f" on {json.dumps(c['on'], ensure_ascii=False)}" if c.get("on") else ""  # the text it is about
    return f"{PAD}comment ({c['author']}, {c['at'][:10]}, {c['annotation_id']}){on}: {c['note']}"


# =====================================================================================================
# rule draft
# =====================================================================================================
def cmd_rule_draft(args) -> int:
    ctx = Ctx.from_args(args)
    if not args.rule_ids and not args.all:
        raise UserError("name the rules to draft, or --all")
    print(json.dumps(draft_of(ctx, [] if args.all else args.rule_ids, args.for_catalog), indent=2, ensure_ascii=False))
    return 0


def draft_of(ctx: Ctx, rule_ids: list[str], for_catalog: str | None = None) -> dict:
    """The rules as an editable draft. `for_catalog`: a template for another catalog's first ruleset (every rule
    of this one, with its settings), to be adapted to that catalog's pages."""
    v = ctx.latest_ruleset()
    rs, rules = ctx.ruleset_rules(v)
    out = [_draft_rule(rules, rid, v) for rid in rule_ids or ordered_rule_ids(rules)]
    if for_catalog:
        keep = ("content_root", "page_title", "signals")
        settings = {k: rs["settings"][k] for k in keep if k in rs["settings"]}
        return {"catalog": for_catalog, "base_ruleset": None, "template": f"{ctx.catalog} ruleset v{v}",
                "settings": settings, "rules": out}
    return {"catalog": ctx.catalog, "base_ruleset": v, "rules": out}


def _draft_rule(rules: dict[str, dict], rid: str, v: int) -> dict:
    if rid not in rules:
        raise UserError(f"no rule {rid!r} in ruleset v{v} (a new rule: write it into the draft by hand)")
    r = rules[rid]
    return {k: r.get(k) for k in DRAFT_FIELDS} | {"examples": r.get("examples") or []}


# =====================================================================================================
# rule try / publish
# =====================================================================================================
class _Stop(Exception):
    """Ends `rule publish` early with an exit code; what to say was already printed."""

    def __init__(self, code: int):
        super().__init__(code)
        self.code = code


@dataclass
class _Published:
    plan: dict
    ev: dict
    version: int
    names: str
    rebased: str | None
    extraction: str = ""
    meta: dict | None = None
    upload_started: float = 0.0


def cmd_rule_try(args) -> int:
    t0 = time.perf_counter()
    ctx = Ctx.from_args(args)
    plan = plan_draft(ctx, read_draft(args.draft))
    refusal = _refuse_try(plan)
    if refusal is not None:
        return refusal
    ev = evaluate(ctx, plan, log=_say, inferred=read_inferred(args.inferred))
    elapsed = time.perf_counter() - t0
    if plan["latest"]:
        save_last_try(ctx, ev, plan["latest"], None)
    if args.json:
        print(json.dumps(_try_json(ctx, plan, ev, elapsed), indent=2, ensure_ascii=False))
    else:
        _print_try(ctx, plan, ev, elapsed)
    return 0


def cmd_rule_publish(args) -> int:
    from .publishing import publish_lock

    t0 = time.perf_counter()
    ctx = Ctx.from_args(args)
    doc = read_draft(args.draft)
    inferred = read_inferred(args.inferred)
    run = _run_record(ctx)
    try:
        with publish_lock(ctx, run.get("run_id"), args.by, say=_lock_waiter(ctx)):
            published = _publish_under_lock(ctx, args, doc, inferred, run)
    except _Stop as stop:
        return stop.code
    _after_publish(ctx, published, t0)
    return 0


def cmd_rule_downstream(args) -> int:
    """The rules that read each rule, directly or not (one-rule-runs spec §3.2): the blast radius of an edit."""
    from .report import rule_names

    ctx = Ctx.from_args(args)
    _, rules = ctx.ruleset_rules(ctx.latest_ruleset())
    names = rule_names(rules)
    for rid in args.rule_ids:
        if rid not in rules:
            raise UserError(f"no rule {rid!r} in ruleset v{ctx.latest_ruleset()}")
        _print_downstream(rules, names, rid)
    return 0


def cmd_ruleset_revert(args) -> int:
    """Publish one new version with every rule a version changed back to its previous version (spec §3.6)."""
    from .publishing import revert

    ctx = Ctx.from_args(args)
    try:
        out = revert(ctx, args.version, args.by, say=_say)
    except FileNotFoundError as exc:
        raise UserError(str(exc)) from None
    print(out["suite"]["line"])
    listed = ", ".join(f"{r['name']} v{r['from_version']} to v{r['to_version']}" if r["to_version"]
                       else f"{r['name']} removed" for r in out["rules"])
    print(f"published ruleset v{out['version']}, reverting v{out['reverted']}: {listed}")
    print(f"extraction {out['extraction']}")
    return 0


# ---- rule try ------------------------------------------------------------------------------------------------

def _refuse_try(plan: dict) -> int | None:
    if plan["example_failures"]:
        _report_examples(plan["example_failures"])
        return 1
    if not plan["changed"] and not plan["settings_changed"]:
        print(f"nothing to try: no definition or setting differs from ruleset v{plan['latest']}")
        return 0
    return None


def _try_json(ctx: Ctx, plan: dict, ev: dict, elapsed: float) -> dict:
    s = ev["suite"]
    return {"catalog": ctx.catalog, "base_ruleset": plan["latest"],
            "base_extraction": ev["parent_extraction"], "changed_rules": plan["changed"],
            "planned_versions": {r: plan["rules"][r]["version"] for r in plan["changed"]},
            "totals": ev["totals"], "cards": ev["cards"],
            "suite": {k: s[k] for k in ("rules", "golden", "now_right", "inferred", "got_worse",
                                        "regressions", "changed")} | {"line": ev["suite_lines"][0]},
            "rerun_rules": ev["result"]["meta"]["rerun_rules"],
            "elapsed_s": round(elapsed, 2)}


def _print_try(ctx: Ctx, plan: dict, ev: dict, elapsed: float) -> None:
    base = f"ruleset v{plan['latest']} ({ev['parent_extraction']})" if plan["latest"] else "no ruleset yet"
    print(f"rule try on {base} + draft, {info(ctx.catalog)['name']}, "
          f"{ev['result']['meta']['pages_total']:,} pages\n")
    _print_results(plan, ev, "draft")
    meta = ev["result"]["meta"]
    print(f"reran {len(meta['rerun_rules'])} rules on {meta['rerun_pages']:,} pages; nothing written")
    print(f"elapsed {elapsed:.1f} s (run {ev['compute_s']:.1f} s)")


# ---- rule publish --------------------------------------------------------------------------------------------

def _lock_waiter(ctx: Ctx):
    """Says each wait for the publish lock; the first one also becomes a run note."""
    waited = []

    def say(m: str) -> None:
        print(m, file=sys.stderr)
        if not waited:
            run_note(ctx, f"Publishing: {m.split(' (')[0]}")
        waited.append(m)
    return say


def _publish_under_lock(ctx: Ctx, args, doc: dict, inferred: list[dict], run: dict) -> _Published:
    ctx.invalidate()
    doc, rebased = _rebase_on_latest(ctx, doc)
    plan = plan_draft(ctx, doc, warn=lambda m: None if rebased else _say(m))
    _require_changes(plan)
    if rebased:
        print(rebased)
        run_note(ctx, rebased)
    ev = evaluate(ctx, plan, log=_say, inferred=inferred)
    _print_results(plan, ev, "publish")
    _refuse_worse(ctx, args, plan, ev)
    published = _Published(plan, ev, plan["latest"] + 1, _changed_names(plan), rebased)
    _publish_ruleset(ctx, args, published, run)
    _write_extraction(ctx, args, published)
    return published


def _rebase_on_latest(ctx: Ctx, doc: dict) -> tuple[dict, str | None]:
    from .publishing import rebase
    from .report import rule_names

    if not ctx.ruleset_versions():
        return doc, None
    _, latest_rules = ctx.ruleset_rules(ctx.latest_ruleset())
    try:
        return rebase(ctx, doc, rule_names(latest_rules))
    except UserError as exc:
        run_note(ctx, f"Redoing on v{ctx.latest_ruleset()}: {exc}")
        print(f"refusing to publish (nothing written): {exc}", file=sys.stderr)
        raise _Stop(2) from None


def _require_changes(plan: dict) -> None:
    if plan["example_failures"]:
        _report_examples(plan["example_failures"])
        print("refusing to publish: examples fail (nothing written)", file=sys.stderr)
        raise _Stop(2)
    if not plan["changed"] and not plan["settings_changed"]:
        print(f"nothing to publish: no definition or setting differs from ruleset v{plan['latest']} (no-op)")
        raise _Stop(0)


def _refuse_worse(ctx: Ctx, args, plan: dict, ev: dict) -> None:
    worse = ev["suite"]["got_worse"]
    if worse and not args.force:
        print(f"\nrefusing to publish: {worse} golden value(s) that were right got worse (nothing written). "
              "Change the draft so they don't, or ask the expert; --force overrides.", file=sys.stderr)
        if plan["latest"]:
            save_last_try(ctx, ev, plan["latest"], None)
        raise _Stop(2)


def _changed_names(plan: dict) -> str:
    return ", ".join(f"{r} v{plan['rules'][r]['version']}" for r in plan["changed"]) or "settings only"


def _publish_ruleset(ctx: Ctx, args, p: _Published, run: dict) -> None:
    from .check import check_before_write

    check_before_write(ctx, {"settings": p.plan["settings"]}, p.plan["rules"], p.ev["result"]["tables"])
    note = args.note or f"{p.names} (rule publish)"
    p.upload_started = time.perf_counter()
    published = rulesets.publish(ctx, p.plan["rules"], p.plan["settings"], note, args.by,
                                 extra=_publish_extra(run, p.ev["suite"]["got_worse"]) or None)
    if published is None:
        print("nothing changed: no-op")
        raise _Stop(0)
    if published["version"] != p.version:
        raise UserError(f"published ruleset v{published['version']}, but the draft was run against "
                        f"v{p.plan['latest']}; run `golden-datasets extract --ruleset {published['version']}`")


def _publish_extra(run: dict, worse: int) -> dict:
    return {k: v for k, v in run.items() if v} | ({"forced": True, "got_worse": worse} if worse else {})


def _write_extraction(ctx: Ctx, args, p: _Published) -> None:
    p.extraction = extract.next_extraction_id(ctx, p.version, again=False)
    p.meta = extract.write_extraction(ctx, p.extraction, p.version, p.ev["parent_extraction"], p.ev["result"],
                                      args.by)


def _after_publish(ctx: Ctx, p: _Published, t0: float) -> None:
    if p.plan["latest"]:
        save_last_try(ctx, p.ev, p.plan["latest"], p.version)
        _record_publish(ctx, p.ev, p.plan, p.version, p.rebased)
    upload = time.perf_counter() - p.upload_started
    latest, meta = p.plan["latest"], p.meta
    print(f"\npublished ruleset v{p.version}" + (f" (parent v{latest})" if latest else " (the first)")
          + f": {p.names}" + (". FORCED: golden values got worse" if p.ev["suite"]["got_worse"] else ""))
    rows = ", ".join(f"{k.split('.')[0]} {v['rows']:,}" for k, v in meta["files"].items())
    print(f"extraction {p.extraction} (parent {meta['parent_extraction']}): {rows}")
    print(f"  reran {len(meta['rerun_rules'])} rules on {meta['rerun_pages']:,} pages")
    print(f"upload {upload:.1f} s, total {time.perf_counter() - t0:.1f} s")


def _record_publish(ctx: Ctx, ev: dict, plan: dict, version: int, rebased: str | None) -> None:
    """In a Studio run: what this publish changed, kept for the report (`published.json`, oldest first)."""
    run_id = os.environ.get("GOLDEN_DATASETS_RUN")
    if not run_id:
        return
    path = f"{layout.agent_run_dir(ctx.catalog, ctx.cls, run_id)}/published.json"
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


def _print_downstream(rules: dict[str, dict], names: dict[str, str], rid: str) -> None:
    from .publishing import downstream

    down = downstream(rules, rid)
    reads = rules[rid].get("depends_on") or model.dependencies(rules[rid])
    print(f"{names[rid]} ({rid}) reads: " + (", ".join(f"{names.get(r, r)} ({r})" for r in reads) or "nothing"))
    print(f"  read by {len(down)} rule{'' if len(down) == 1 else 's'}"
          + (": " + ", ".join(f"{names.get(r, r)} ({r})" for r in down) if down else ""))


# ---- shared by try and publish: the draft, its plan, its evaluation, the printout ------------------------------

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


def read_inferred(path: str | None) -> list[dict]:
    """`inferred.json` (one-rule-runs spec §4): [{rule, course, annotation, value}], the values Claude worked out for
    courses marked wrong with no expected value. `path` None: `./inferred.json` if there is one."""
    p = Path(path) if path else Path("inferred.json")
    if not p.is_file():
        if path:
            raise UserError(f"no inferred values file {path}")
        return []
    items = _inferred_items(p)
    for i, x in enumerate(items):
        missing = [k for k in ("rule", "course", "annotation", "value") if k not in x]
        if missing or not isinstance(x["value"], str):
            raise UserError(f"{p}[{i}]: needs rule, course, annotation and value (text; \"\" for empty)")
    return items


def _inferred_items(p: Path) -> list[dict]:
    try:
        doc = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise UserError(f"{p}: not valid JSON ({exc})") from None
    items = doc.get("inferred") if isinstance(doc, dict) else doc
    if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
        raise UserError(f"{p}: a list of {{rule, course, annotation, value}}")
    return items


def plan_draft(ctx: Ctx, doc: dict, warn=lambda m: print(m, file=sys.stderr)) -> dict:
    """Merge a draft into the latest ruleset and assign versions (nothing is written)."""
    if doc.get("catalog") and ctx.catalog != doc["catalog"] and info(ctx.catalog)["short"] != doc["catalog"]:
        raise UserError(f"the draft is for {doc['catalog']}, not {ctx.catalog}")
    latest, rs, base = _draft_base(ctx)
    if latest and doc.get("base_ruleset") not in (None, latest):
        warn(f"note: the draft was made from ruleset v{doc['base_ruleset']}; merging it into the latest, v{latest}")
    drafts = _merge_drafts(doc.get("rules", []), base, warn)
    planned = rulesets.plan_versions(ctx, drafts, base)
    settings = _planned_settings(rs, base, planned, doc.get("settings"))
    _warn_unversioned(planned, drafts, base, warn)
    rules = _valid_rules(base, planned, latest)
    return {"latest": latest, "ruleset": rs, "base": base, "drafts": drafts, "rules": rules, "settings": settings,
            "changed": _changed_rules(rules, base), "settings_changed": settings != rs["settings"],
            "example_failures": check_examples(drafts)}


def _draft_base(ctx: Ctx) -> tuple[int, dict, dict]:
    """(latest version, its ruleset, its rules); a catalog's first rules (added from the picker) have none."""
    if not ctx.ruleset_versions():
        return 0, {"version": None, "parent_version": None, "settings": None}, {}
    latest = ctx.latest_ruleset()
    rs, base = ctx.ruleset_rules(latest)
    return latest, rs, base


def _merge_drafts(items: list[dict], base: dict[str, dict], warn) -> dict[str, dict]:
    drafts: dict[str, dict] = {}
    for item in items:
        item = model.current_kind(item)
        rid = item.get("rule_id")
        if not rid or "definition" not in item:
            raise UserError("each rule in a draft needs rule_id and definition")
        if rid in drafts:
            raise UserError(f"{rid} appears twice in the draft")
        drafts[rid] = _merged_rule(rid, item, base.get(rid), warn)
    return drafts


def _merged_rule(rid: str, item: dict, old: dict | None, warn) -> dict:
    ignored = sorted(set(item) - set(DRAFT_FIELDS))
    if ignored:
        warn(f"note: {rid}: ignoring {', '.join(ignored)} (golden-datasets assigns versions and hashes)")
    if old is None and not item.get("kind"):
        raise UserError(f"{rid} is a new rule: give its kind (page, locator or property)")
    if old is not None and item.get("kind") not in (None, old["kind"]):
        raise UserError(f"{rid}: the kind of an existing rule can't change ({old['kind']})")
    merged = {k: old.get(k) for k in DRAFT_FIELDS if old is not None and k in old}
    merged.update({k: item[k] for k in DRAFT_FIELDS if k in item})
    merged.setdefault("examples", [])
    _validate_definition(rid, merged)
    return merged


def _planned_settings(rs: dict, base: dict, planned: dict, drafted: dict | None) -> dict:
    if rs["settings"] is None:
        return rulesets.first_settings({**base, **planned}, drafted)
    return {**rs["settings"], **(drafted or {})}


def _warn_unversioned(planned: dict, drafts: dict, base: dict, warn) -> None:
    for rid, r in planned.items():
        if rid in base and r["content_hash"] == base[rid]["content_hash"] and \
                any(drafts[rid].get(k) != base[rid].get(k) for k in ("what", "how", "why", "examples")):
            warn(f"note: {rid}: definition unchanged, so no new version (what/how/why/examples describe a "
                 "definition; they change only with it)")


def _valid_rules(base: dict, planned: dict, latest: int) -> dict:
    rules = {**base, **planned}
    rulesets.validate_ruleset(rules)
    if not latest and not rules:
        raise UserError("the draft has no rules; a catalog's first ruleset needs at least a page rule, a record locator "
                        "and property rules")
    return rules


def _changed_rules(rules: dict, base: dict) -> list[str]:
    return sorted(rid for rid, r in rules.items()
                  if rid not in base or base[rid]["content_hash"] != r["content_hash"])


def _validate_definition(rid: str, rule: dict) -> None:
    """Catch broken regexes and selectors before running anything (worker errors are hard to read)."""
    d = rule["definition"]
    if not isinstance(d, dict):
        raise UserError(f"{rid}: definition must be an object")
    for key, pattern in _definition_regexes(d):
        if pattern:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise UserError(f"{rid}: {key} is not a valid regex: {exc}") from None
    for sel in _definition_selectors(d):
        if sel:
            try:
                engine.select(engine.parse(b"<html><body></body></html>"), sel)
            except Exception as exc:  # cssselect raises several error types
                raise UserError(f"{rid}: {sel!r} is not a valid CSS selector: {exc}") from None


def _definition_regexes(d: dict) -> list[tuple[str, str | None]]:
    """(where, pattern) of every regex in a definition, in the order they are checked."""
    multiple = d.get("multiple") if isinstance(d.get("multiple"), dict) else {}
    found = [(f"definition.{key}", d.get(key)) for key in ("regex", "url_regex")]
    found += [("definition.multiple.regex", multiple.get("regex")), ("definition.multiple.keep", multiple.get("keep"))]
    if isinstance(d.get("repeat_filter"), dict):
        found.append(("repeat_filter.regex", d["repeat_filter"].get("regex")))
    return found


def _definition_selectors(d: dict) -> list[str | None]:
    sels = [d.get(k) for k in ("selector", "repeat", "requires_selector", "forbids_selector")]
    if d.get("until") and not str(d["until"]).isalnum():
        sels.append(d["until"])
    if isinstance(d.get("repeat_filter"), dict):
        sels.append(d["repeat_filter"].get("selector"))
    return sels


def check_examples(drafted: dict[str, dict]) -> list[str]:
    """Each example of a drafted property rule: its definition (regex + group + transforms + map) applied to `input`
    must give `output`."""
    failures = []
    for rid in sorted(drafted):
        r = drafted[rid]
        if r["kind"] != "property" or r["definition"].get("rule_type") in (*model.DERIVED_RULE_TYPES, "none"):
            continue
        for i, ex in enumerate(r.get("examples") or [], 1):
            failure = _example_failure(r["definition"], ex)
            if failure:
                failures.append(f"{rid} example {i}: {failure}")
    return failures


def _example_failure(d: dict, ex) -> str | None:
    if not isinstance(ex, dict) or "input" not in ex:
        return "needs \"input\" and \"output\""
    got = engine.values_of_text(d, ex["input"])
    value = got if d.get("multiple") else (got[0] if got else None)
    want = ex.get("output")
    if (value or "") != (want or "") and not (d.get("multiple") and value == [] and not want):
        return (f"got {json.dumps(value, ensure_ascii=False)}, "
                f"expected {json.dumps(ex.get('output'), ensure_ascii=False)}")
    return None


def evaluate(ctx: Ctx, plan: dict, log=lambda m: None, inferred: list[dict] | None = None) -> dict:
    """Run the planned ruleset over the whole crawl (every rule, every page: the whole golden suite, one-rule-runs
    spec §3.3), score the rules that changed and check every golden value. Writes nothing."""
    t0 = time.perf_counter()
    parent_ext, result, draft = _run_draft(ctx, plan, log)
    compute_s = time.perf_counter() - t0
    events = LOADER.log(ctx).events()
    review = _review_with_inferred(draft, events, inferred or [])
    base_snap = LOADER.snapshot(ctx, parent_ext) if parent_ext else None
    cards = _scorecards(plan, base_snap, draft, review)
    return {"parent_extraction": parent_ext, "result": result, "cards": cards, "totals": _totals(cards),
            "snapshot": draft, **_suite_fields(base_snap, draft, events, inferred, plan),
            "inferred_values": _inferred_values(draft, inferred or []),
            "compute_s": round(compute_s, 2), "total_s": round(time.perf_counter() - t0, 2)}


def _run_draft(ctx: Ctx, plan: dict, log) -> tuple[str | None, dict, Snapshot]:
    parent_ext = ctx.extraction_for(plan["latest"]) or extract.pick_parent(ctx, plan["ruleset"])
    result = extract.compute(ctx, plan["rules"], plan["settings"], None, log=log)
    draft = Snapshot(ctx, "draft", tables=result["tables"], ruleset={"settings": plan["settings"], "version": None},
                     rules=plan["rules"], meta={"ruleset_version": None, "parent_extraction": parent_ext})
    return parent_ext, result, draft


def _review_with_inferred(draft: Snapshot, events: list[dict], inferred: list[dict]) -> Review:
    review = Review(draft, events)
    problems = check_inferred(review, inferred)
    if problems:
        raise UserError("inferred.json has problems:\n  " + "\n  ".join(problems))
    return review


def check_inferred(review: Review, inferred: list[dict]) -> list[str]:
    """Each inferred value must answer a live ✕ on that rule and course that has no expected value."""
    problems = (_inferred_problem(review, i, x) for i, x in enumerate(inferred))
    return [p for p in problems if p]


def _inferred_problem(review: Review, i: int, x: dict) -> str | None:
    e = review.by_id.get(x["annotation"])
    live = e is not None and any(ev is e for ev in review.live)
    t = (e or {}).get("target") or {}
    if not live or e["type"] != "verdict" or e.get("verdict") != "wrong":
        return f"inferred[{i}]: {x['annotation']} is not a live wrong verdict"
    if t.get("rule_id") != x["rule"] or (t.get("record_external_identifier") and t["record_external_identifier"] != x["course"]):
        return (f"inferred[{i}]: {x['annotation']} is on {t.get('rule_id')} {t.get('record_external_identifier')}, "
                f"not {x['rule']} {x['course']}")
    if (e.get("expected") or {}).get("text") is not None:
        return f"inferred[{i}]: {x['annotation']} already has an expected value"
    return None


def _scorecards(plan: dict, base_snap: Snapshot | None, draft: Snapshot, review: Review) -> list[dict]:
    if base_snap is None:
        return [scorecard.rule_scorecard(rid, None, draft, review) for rid in ordered_rule_ids(plan["drafts"])]
    ids = set(plan["drafts"]) | set(scorecard.changed_rules(base_snap, draft))
    return [scorecard.rule_scorecard(rid, base_snap, draft, review)
            for rid in ordered_rule_ids({r: plan["rules"].get(r) or base_snap.rules[r] for r in ids})]


def _totals(cards: list[dict]) -> dict:
    return {k: sum(c["annotated"][k] for c in cards) for k in ("fixed", "still_wrong", "newly_wrong", "unchanged")}


def _suite_fields(base_snap: Snapshot | None, draft: Snapshot, events: list[dict], inferred: list[dict] | None,
                  plan: dict) -> dict:
    from . import suite
    from .report import rule_names

    s = suite.score(base_snap, draft, events, inferred, drafted=plan["changed"])
    names = rule_names({**(base_snap.rules if base_snap else {}), **plan["rules"]})
    return {"suite": s, "suite_lines": suite.lines(s, names), "names": names, "inferred": inferred or []}


def _inferred_values(draft: Snapshot, inferred: list[dict]) -> dict[str, dict]:
    """rule → course → the value the draft gives for each inferred value."""
    produced: dict[str, dict] = {}
    for x in inferred:
        row = next((r for r in draft.rows(x["rule"]) if r.get("record_external_identifier") == x["course"]), None) \
            if x["rule"] in draft.rules else None
        produced.setdefault(x["rule"], {})[x["course"]] = row["value"] if row else None
    return produced


def _print_results(plan: dict, ev: dict, prefix: str) -> None:
    if plan["latest"]:
        _print_suite(ev)
        _print_cards(plan, ev, _label(plan, prefix))
    else:
        _print_first(plan, ev)


def _print_suite(ev: dict) -> None:
    for line in ev["suite_lines"]:
        print(line)
    print()


def _print_cards(plan: dict, ev: dict, b_label) -> None:
    for c in ev["cards"]:
        print(scorecard.format_card(c, b_label(c)))
        newly = [r for r in c["annotated_rows"] if r["outcome"] == "newly wrong"]
        still = [r for r in c["annotated_rows"] if r["outcome"] == "still wrong"]
        for title, rows in (("newly wrong (marked correct, value changed)", newly), ("still wrong", still)):
            if rows:
                print(f"  {title}: " + ", ".join(r["record_external_identifier"] or r["page_stem"] for r in rows))
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
        d = layout.agent_run_dir(ctx.catalog, ctx.cls, run_id)
        ctx.root.write_json(f"{d}/last-try.json", last_try_doc(ev, base, published))
        if ev["inferred"]:
            ctx.root.write_json(f"{d}/inferred.json", ev["inferred"])


def run_note(ctx: Ctx, text: str) -> None:
    """In a Studio run, one progress line the Studio shows (publishing waits, rebases)."""
    run_id = os.environ.get("GOLDEN_DATASETS_RUN")
    if run_id:
        from .agent_runs import AgentRuns

        AgentRuns(ctx).log(run_id, "note", text, by="golden-datasets")


def _say(m: str) -> None:
    print(m, file=sys.stderr)


# =====================================================================================================
# pages get / sample
# =====================================================================================================
def cmd_pages_get(args) -> int:
    ctx = Ctx.from_args(args)
    stems = resolve_stems(ctx, args.stems)
    url = {p["page_stem"]: p["url"] for p in ctx.pages()}
    dest = Path(args.to).expanduser() if args.to else None
    if dest:
        dest.mkdir(parents=True, exist_ok=True)
    for stem in stems:
        local = _copy_page(ctx, stem, dest) if dest else ctx.page_path(stem)
        print(f"{local}\t{url.get(stem, '')}")
    return 0


def cmd_pages_sample(args) -> int:
    ctx = Ctx.from_args(args)
    rv = current_review(ctx)
    rows = sample_rows(rv, args.rule, args.signal, args.n)
    print(f"{args.rule}{' · signal ' + args.signal if args.signal else ''} · {len(rows)} row(s), Rules tab order · "
          f"extraction {rv.snap.ext}")
    for r in rows:
        print(page_ref(ctx, r["page_stem"]))
        print(f"   {r['record_external_identifier'] or '—'} · {short(r['value'], 120)!s}"
              + (f" · signals: {', '.join(r['signal_names'])}" if r["signal_names"] else ""))
    return 0


def resolve_stems(ctx: Ctx, wanted: list[str]) -> list[str]:
    """Exact page stems, or any unique part of one (e.g. `course-geog222`)."""
    stems = sorted(p["page_stem"] for p in ctx.pages())
    have = set(stems)
    return [_resolve_stem(w.removesuffix(".html"), stems, have) for w in wanted]


def _resolve_stem(w: str, stems: list[str], have: set[str]) -> str:
    if w in have:
        return w
    hits = [s for s in stems if w in s]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise UserError(f"no saved page matches {w!r}")
    raise UserError(f"{w!r} matches {len(hits)} pages, e.g. {', '.join(hits[:3])}; be more specific")


def _copy_page(ctx: Ctx, stem: str, dest: Path) -> Path:
    """The saved page (and its meta, when there is one) copied into `dest`."""
    shutil.copyfile(ctx.page_path(stem), dest / f"{stem}.html")
    meta = layout.page_meta(ctx.catalog, ctx.crawl, stem)
    if ctx.crawl_root.exists(meta):
        shutil.copyfile(ctx.crawl_root.local_path(meta), dest / f"{stem}.meta.json")
    return dest / f"{stem}.html"


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


# =====================================================================================================
# Shared reads (also used by prompt.py and the server)
# =====================================================================================================
def current_review(ctx: Ctx) -> Review:
    """The latest ruleset's extraction + the annotation log."""
    v = ctx.latest_ruleset()
    ext = ctx.extraction_for(v)
    if not ext:
        raise UserError(f"ruleset v{v} has no extraction on crawl {ctx.crawl}; run `golden-datasets extract`")
    return Review(LOADER.snapshot(ctx, ext), LOADER.log(ctx).events())


def rule_annotations(rv: Review, rule_id: str, page_questions: bool = True) -> list[dict]:
    """Every live annotation on a rule (superseded ones dropped; the latest verdict per target), with the
    verdict carried to the current version (`state`), the current value, and whether it still needs work.

    `page_questions`: also the page-level questions (no rule) on pages this rule has rows on."""
    rule_or_error(rv, rule_id)
    rows = rv.snap.rows(rule_id)
    verdicts = rv.verdicts_for(rule_id)
    out = _verdict_records(rv, rule_id, rows, verdicts) + _comment_records(rv, rule_id, verdicts)
    if page_questions:
        out += _page_question_records(rv, rule_id, rows)
    out.sort(key=lambda r: (not r["open"], VERDICT_ORDER.get(r["verdict"] or "", 4), r["record_external_identifier"] or "",
                            r["page_stem"] or "", r["annotation_id"]))
    return out


def _verdict_records(rv: Review, rule_id: str, rows: list[dict], v: dict) -> list[dict]:
    by_event = _rows_by_verdict(rv, rule_id, rows)
    open_missing = {e["annotation_id"] for e in rv.missing_events(rule_id)}
    out = []
    for key, e in v["latest"].items():
        row, st = by_event.get(e["annotation_id"], (None, None))
        state = st.state if st is not None else _rowless_state(e, open_missing)
        out.append(_record(rv, rule_id, e, row, state, v["comments"].get(key, []),
                           reattached=bool(st is not None and st.reattached)))
    return out


def _rows_by_verdict(rv: Review, rule_id: str, rows: list[dict]) -> dict[str, tuple[dict, object]]:
    """verdict annotation id → (the row it is on now, its state)."""
    states = rv.row_states(rule_id, rows)
    by_event: dict[str, tuple[dict, object]] = {}
    for row in rows:
        st = states[row["key"]]
        if st.verdict is not None:
            by_event.setdefault(st.verdict["annotation_id"], (row, st))
    return by_event


def _rowless_state(e: dict, open_missing: set[str]) -> str:
    if e["verdict"] == "missing":
        return "missing" if e["annotation_id"] in open_missing else "found-now"
    if e["verdict"] == "question":
        return "question"
    return "no-row"


def _comment_records(rv: Review, rule_id: str, v: dict) -> list[dict]:
    """Comments on targets with no verdict: the latest comment, the earlier ones as its thread."""
    return [_record(rv, rule_id, cs[-1], None, None, cs[:-1])
            for key, cs in v["comments"].items() if key not in v["latest"]]


def _page_question_records(rv: Review, rule_id: str, rows: list[dict]) -> list[dict]:
    stems = {r["page_stem"] for r in rows}
    return [_record(rv, rule_id, e, None, "question", [], page_level=True)
            for e in rv.verdicts_for(None)["latest"].values()
            if e["verdict"] == "question" and e["target"].get("page_stem") in stems]


def _record(rv: Review, rule_id: str, e: dict, row: dict | None, state: str | None, comments: list,
            reattached: bool = False, page_level: bool = False) -> dict:
    t = e["target"]
    stem = t.get("page_stem") or (model.stem_of(t["occurrence_key"]) if t.get("occurrence_key") else None)
    return (_annotation_fields(e, state, rule_id, page_level)
            | _target_fields(rv.snap, t, stem, row)
            | _current_fields(rv.snap.rules[rule_id], row)
            | {"expected": _expected_of(e.get("expected")), "note": e.get("note"), "reattached": reattached,
               "comments": [_comment_of(c) for c in comments]})


def _annotation_fields(e: dict, state: str | None, rule_id: str, page_level: bool) -> dict:
    return {"annotation_id": e["annotation_id"], "type": e["type"], "verdict": e.get("verdict"), "state": state,
            "open": state in OPEN, "author": e["author"], "at": e["at"], "rule_id": rule_id,
            "target_kind": e["target"].get("kind"), "page_level": page_level}


def _target_fields(snap: Snapshot, t: dict, stem: str | None, row: dict | None) -> dict:
    page = snap.page.get(stem) or {}
    occ = snap.occurrences.get(t.get("occurrence_key") or "")
    return {"record_external_identifier": t.get("record_external_identifier") or (row or {}).get("record_external_identifier"),
            "page_stem": stem, "url": page.get("url"), "page_title": page.get("title"),
            "occurrence_key": t.get("occurrence_key"), "occurrence_css_path": (occ or {}).get("css_path"),
            "rule_version_seen": t.get("rule_version_seen"), "value_seen": t.get("value_seen")}


def _current_fields(rule: dict, row: dict | None) -> dict:
    return {"rule_version": rule["version"], "rule_kind": rule["kind"],
            "has_row": row is not None, "current_value": (row or {}).get("value"),
            "current_css_path": (row or {}).get("css_path")}


def _expected_of(exp: dict | None) -> dict | None:
    if not exp:
        return None
    keys = ("text", "css_path", "char_start", "char_end")
    segments = [{k: s.get(k) for k in keys} | {"polarity": s.get("polarity") or "in"} for s in exp.get("segments") or []]
    return {k: exp.get(k) for k in keys} | ({"segments": segments} if exp.get("segments") else {})


def _comment_of(c: dict) -> dict:
    return ({"annotation_id": c["annotation_id"], "author": c["author"], "at": c["at"], "note": c.get("note")}
            | ({"on": c["anchor"].get("text")} if c.get("anchor") else {}))


def rule_or_error(rv: Review, rule_id: str) -> dict:
    if rule_id not in rv.snap.rules:
        known = ", ".join(sorted(rv.snap.rules))
        raise UserError(f"no rule {rule_id!r} in ruleset v{rv.snap.ruleset_version} (rules: {known})")
    return rv.snap.rules[rule_id]


def rule_brief(rv: Review, rule_id: str) -> dict:
    """Status, reviewed / total, fill and signal counts of one rule in the current extraction."""
    st = rv.rule_status(rule_id)
    sig = rv.snap.signal_counts.get(rule_id, {})
    return {**st, "fill": rv.snap.fill(rule_id),
            "signals": dict(sorted(sig.items(), key=lambda kv: (-kv[1], kv[0])))}


def ordered_rule_ids(rules: dict[str, dict]) -> list[str]:
    return sorted(rules, key=lambda r: (model.KIND_ORDER[rules[r]["kind"]], r))


def page_ref(ctx: Ctx, stem: str) -> str:
    """A saved page's path in xtra-cli's container, where the crawl is (spec §7.5: pages by path, never raw HTML)."""
    return f"{ctx.crawl_root.uri}/{layout.page_html(ctx.catalog, ctx.crawl, stem)}"


def short(v: str | None, n: int = 160) -> str:
    v = (v or "").replace("\n", "⏎ ")
    return v if len(v) <= n else v[: n - 1] + "…"
