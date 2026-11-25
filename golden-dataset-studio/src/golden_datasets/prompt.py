"""The prompt for Claude Code (spec §7.5, screen 09): the same text from the UI's **Copy prompt** button and from
`golden-datasets prompt`.

Deterministic: the same annotations always give the same text (everything is sorted; no "now"). It holds the task,
the setup (install the CLI from this branch with uv, point it at the root; for `target="azure"`, the Azure root after
`az login`), the limits, each in-scope rule's definition and what / how / why, its open annotations, the values marked
correct (which must not change) and its signals as tables, the questions for the institution (listed apart, not
bugs), the `golden-datasets` commands that fetch all of this and more, and the publish rule, plus the comments on each rule and on the ruleset (Rules tab sidebar). No raw HTML: pages are
referenced by stem, fetched with `golden-datasets pages get`.

The module reads top-down: the command, the improve prompt and its sections, the first-rules prompt and its sections,
the sections both share, small helpers, and last the prompt's fixed text.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from . import manifest, model, properties
from .catalogs import info
from .cli import DEFAULT_AZURE_ROOT, ENV_FILE
from .context import Ctx
from .errors import UserError
from .loop import current_review, ordered_rule_ids, rule_annotations, rule_or_error, short
from .review import Review, norm

REPO = "https://github.com/CredentialEngine/ctdl-xtra.git"
SUBDIR = "golden-dataset-studio"
TARGETS = ("local", "azure", "k2")
# k2: the remote agent (agent_runs.py) on K2. Its workspaces are folders under K2_WORK, and the SAS tokens for the
# shared root sit in `<K2_WORK>/golden-datasets.env`. $GOLDEN_DATASETS_K2_WORK names another folder (a K2 daemon on a
# laptop, for a test).
K2_WORK = "/var/lib/k2/work"
#: a run's tools are removed this long after it started (runs end within 90 minutes)
TOOLS_KEPT_MINUTES = 24 * 60
KIND_NAME = {"page": "page rule", "locator": "record locator", "property": "property rule"}
TOPIC_NAME = {"new-rule": "suggests a new rule", "approach": "suggests an approach",
              "question-rule": "questions this rule", "other": "comment", None: "comment"}


def cmd_prompt(args) -> int:
    ctx = Ctx.from_args(args)
    if args.first_rules:
        out = build_first_rules_prompt(ctx, target=args.target, azure_root=args.azure_root)
        print(out["text"], end="")
        return 0
    if args.rule is None and not args.needs_work:
        args.needs_work = True
    out = build_prompt(ctx, args.rule, args.needs_work, target=args.target, azure_root=args.azure_root)
    if has_raw_html(out["text"]):
        print("golden-datasets: warning: an annotation quotes something that looks like HTML", file=sys.stderr)
    print(out["text"], end="")
    return 0


# =====================================================================================================
# Improve rules: the prompt behind Copy prompt and every AI run on rules
# =====================================================================================================
def build_prompt(ctx: Ctx, rule: str | None = None, needs_work: bool = False, rv: Review | None = None,
                 target: str = "local", azure_root: str | None = None, run: dict | None = None,
                 rules: list[str] | None = None) -> dict:
    """{text, chars, tokens, page_refs, rules, annotations, scope, target, root, warning}
    (web/src/api/types.ts `PromptResponse`). `target`: Claude works on this root ("local") or the Azure one.
    `rules`: the rules to improve (the goal, one-rule-runs spec §3.1); else one `rule`, or every rule needing work."""
    if target not in TARGETS:
        raise ValueError(f"target must be one of {TARGETS}")
    rv = rv or current_review(ctx)
    targets, rule, needs_work = _prompt_scope(rv, rule, needs_work, rules)
    p = _Prompt(ctx, rv, targets, target, run, _root_uri(ctx, target, azure_root), picked=bool(rules))
    text = _finish(_improve_lines(p), target)
    return {"scope": {"rule": rule if not needs_work else None, "needs_work": needs_work},
            "text": text, "chars": len(text), "tokens": round(len(text) / 4), "page_refs": len(p.refs),
            "rules": targets, "annotations": p.n_open, "target": target, "root": p.root_uri,
            "warning": cli_source()["warning"]}


@dataclass
class _Prompt:
    """What the improve prompt's sections read, and what they collect (page refs, questions, open annotations)."""
    ctx: Ctx
    rv: Review
    targets: list[str]
    target: str
    run: dict | None
    root_uri: str
    picked: bool  # the rules to improve were picked, not "every rule that needs work"
    refs: set[str] = field(default_factory=set)
    questions: dict[str, tuple[str, dict]] = field(default_factory=dict)
    n_open: int = 0

    @property
    def snap(self):
        return self.rv.snap

    @cached_property
    def discussion(self) -> dict:
        return self.rv.discussion()

    @cached_property
    def names(self) -> dict[str, str]:
        from .report import rule_names

        return rule_names(self.snap.rules)

    @cached_property
    def past(self):
        """The catalog's AI runs, for each rule's last run (k2 only)."""
        from .agent_runs import AgentRuns

        return AgentRuns(self.ctx) if self.target == "k2" else None


def _prompt_scope(rv: Review, rule: str | None, needs_work: bool, rules: list[str] | None):
    """(the rules to improve, the one `rule` in scope, whether the scope is "needs work")."""
    if not rules:
        needs_work = needs_work or not rule
        return scope_rules(rv, rule, needs_work), rule, needs_work
    for r in rules:
        rule_or_error(rv, r)
    targets = [r for r in ordered_rule_ids(rv.snap.rules) if r in set(rules)]
    return targets, (targets[0] if len(targets) == 1 else None), False


def scope_rules(rv: Review, rule: str | None, needs_work: bool) -> list[str]:
    if rule and not needs_work:
        rule_or_error(rv, rule)
        return [rule]
    return [rid for rid in ordered_rule_ids(rv.snap.rules) if rv.rule_status(rid)["status"] == "needs work"]


def _improve_lines(p: _Prompt) -> list[str]:
    lines = _title_lines(p) + ["", INTRO, ""] + (_run_header(p.run, p.ctx) if p.target == "k2" else [])
    lines += _setup(p.ctx, p.target, p.root_uri, p.targets[0] if p.targets else "<rule_id>", run=p.run)
    lines += _context_lines(p) + _limits_lines(p) + _rules_table_lines(p)
    for rid in p.targets:
        lines += _rule_lines(p, rid)
    lines += _ruleset_comment_lines(p) + _question_lines(p) + _how_to_work_lines(p)
    return lines + (_run_close(p.run) if p.target == "k2" else
                    ["Report back: what changed and why, the final scorecard, and anything you could not fix."])


def _title_lines(p: _Prompt) -> list[str]:
    name = info(p.ctx.catalog)["name"]
    if len(p.targets) == 1:
        return [f"# Improve rule `{p.targets[0]}` — {name} catalog"]
    if p.targets:
        return [f"# Improve {len(p.targets)} rules{'' if p.picked else ' that need work'} — {name} catalog"]
    return [f"# No rule needs work — {name} catalog"]


def _context_lines(p: _Prompt) -> list[str]:
    meta = info(p.ctx.catalog)
    platform = f", {meta['platform']} platform" if meta.get("platform") else ""
    lines = ["## Context", ""] + table(["", ""], [
        ["Catalog", f"`{p.ctx.catalog}` ({meta['name']}{platform})"],
        ["Crawl", f"`{p.ctx.crawl}`, {len(p.snap.page):,} saved pages (scripts already ran at crawl time)"],
        ["Ruleset", f"v{p.snap.ruleset_version} (extraction `{p.snap.ext}`)"],
        ["Storage root", f"`{p.root_uri}`"],
        ["A saved page", "`golden-datasets pages get <page_stem>` prints its local path and live URL"],
    ]) + [""]
    kinds = {p.snap.rules[t]["kind"] for t in p.targets}
    return lines + [FORMAT[kind] for kind in ("page", "locator", "property") if kind in kinds] + [""]


def _limits_lines(p: _Prompt) -> list[str]:
    lines = ["## Limits", *EDIT_LIMITS]
    if p.targets:
        lines.append(_goal_limit(p.targets))
    lines.append(f"- Only the properties of `properties/{p.ctx.cls}.csv` count (`golden-datasets properties list`): "
                 "don't add rules for anything else.")
    lines += WORK_LIMITS
    if p.target == "k2":
        lines.append("- List every rule you changed that isn't a goal under `also_changed` in your report, with one "
                     "line on why.")
    return lines + [""]


def _goal_limit(targets: list[str]) -> str:
    return (f"- **Your goal is the rule{'' if len(targets) == 1 else 's'} in this prompt**: "
            f"{', '.join(f'`{t}`' for t in targets)}. You may change any other rule if a goal needs it: a page "
            "rule, a locator, a rule a goal reads or that reads it. Keep every change as small as possible. "
            "`golden-datasets rule downstream <rule>` shows what reads a rule.")


def _rules_table_lines(p: _Prompt) -> list[str]:
    if len(p.targets) <= 1:
        return []
    rows = []
    for rid in p.targets:
        r = p.snap.rules[rid]
        n = sum(1 for a in rule_annotations(p.rv, rid) if a["open"])
        rows.append([f"`{rid}`", f"v{r['version']}", KIND_NAME[r["kind"]], r.get("property_label") or "—", n])
    return ([f"## The {len(p.targets)} rules", ""]
            + table(["Rule", "Version", "Kind", "Property", "Open annotations"], rows) + [""])


def _rule_lines(p: _Prompt, rid: str) -> list[str]:
    r = p.snap.rules[rid]
    anns = rule_annotations(p.rv, rid)
    for a in anns:
        if a["verdict"] == "question":
            p.questions.setdefault(a["annotation_id"], (rid, a))
    return (_rule_head_lines(p, rid, r) + _definition_lines(r) + _open_lines(p, rid, r, anns)
            + _correct_lines(rid, r, anns) + _changed_lines(anns) + _rule_comment_lines(p, rid)
            + _past_run_lines(p, rid) + _signal_lines(p, rid) + [""])


def _rule_head_lines(p: _Prompt, rid: str, r: dict) -> list[str]:
    from .publishing import downstream

    st = p.rv.rule_status(rid)
    fill = p.snap.fill(rid)
    prop = f", {r['property_label']} (`{r.get('ctdl_property') or 'no CTDL term'}`)" if r.get("property_label") else ""
    return [f"## Rule `{rid}` v{r['version']} — {KIND_NAME[r['kind']]}{prop} — status: **{st['status']}**",
            ""] + table(["", ""], [
                ["**What**", r.get("what") or "(empty)"],
                ["**How**", r.get("how") or "(empty)"],
                ["**Why**", r.get("why") or "(empty: imported from v2)"],
                ["Depends on", ", ".join(f"`{d}`" for d in r.get("depends_on") or []) or "—"],
                ["Read by", ", ".join(f"`{d}`" for d in downstream(p.snap.rules, rid)) or "no rule"],
                ["Rows", f"{fill['rows']:,}, {fill['found']:,} with a value; {st['reviewed']:,} reviewed"],
            ]) + [""]


def _definition_lines(r: dict) -> list[str]:
    lines = ["```json", json.dumps(r["definition"], indent=2, ensure_ascii=False), "```"]
    if r.get("examples"):
        lines += ["", "Examples (`golden-datasets rule try` checks each: the definition applied to `input` must give "
                  "`output`):", "```json", json.dumps(r["examples"], indent=2, ensure_ascii=False), "```"]
    return lines + [""]


def _open_lines(p: _Prompt, rid: str, r: dict, anns: list[dict]) -> list[str]:
    open_ = [a for a in anns if a["open"]]
    p.n_open += len(open_)
    lines = [f"### Open annotations ({len(open_)})", ""]
    if not open_:
        return lines + ["None: every wrong / missing verdict on this rule is fixed."]
    head = ["#", "Verdict", "Course", "Page", "Extracted", "Expected", "Notes"] if r["kind"] == "property" \
        else ["#", "Verdict", "Course / page", "Page", "Problem", "Notes"]
    return lines + table(head, [_annotation_row(r, a, i, p.refs) for i, a in enumerate(open_, 1)]) + [
        "", f"Full css paths, character offsets (DOM textContent) and page paths: "
            f"`golden-datasets rule annotations {rid} --open`."]


def _correct_lines(rid: str, r: dict, anns: list[dict]) -> list[str]:
    correct = [a for a in anns if a["state"] == "correct"]
    if not correct:
        return []
    lines = ["", f"### Marked correct: must not change ({len(correct)})", ""]
    if r["kind"] == "property":
        lines += table(["Course", "Current value"], [[_who(a), f"\"{short(a['current_value'], 120)}\""] for a in correct])
    else:
        lines.append(", ".join(_who(a) for a in correct))
    return lines + ["", f"Every annotation, these included: `golden-datasets rule annotations {rid}`."]


def _changed_lines(anns: list[dict]) -> list[str]:
    changed = [a for a in anns if a["state"] == "changed-since-correct"]
    if not changed:
        return []
    return ["", f"**Marked correct, but the value changed since ({len(changed)}); the expert will look again:** "
            + ", ".join(a["record_external_identifier"] or a["page_stem"] for a in changed)]


def _rule_comment_lines(p: _Prompt, rid: str) -> list[str]:
    talk = p.discussion["rules"].get(rid, [])
    if not talk:
        return []
    lines = ["", f"### Comments on this rule ({len(talk)})", ""] + _comment_table(talk)
    if any(e.get("topic") == "question-rule" for e in talk):
        lines += ["", "Someone questions whether this rule should exist at all. Don't remove or rewrite it for that: "
                  "say in your report what you think, and why."]
    return lines


def _past_run_lines(p: _Prompt, rid: str) -> list[str]:
    from .agent_runs import context_lines

    if p.past is None or (p.past.goals().get(rid) or {}).get("state") in (None, "waiting", "sending", "running"):
        return []
    return (["", f"### This rule's last run (`golden-datasets run context {rid}`)", ""]
            + context_lines(p.past, rid, p.names, p.rv.events)[2:])


def _signal_lines(p: _Prompt, rid: str) -> list[str]:
    sig = _signal_rows(p.rv, rid)
    if not sig:
        return []
    return (["", f"### Signals on this rule in `{p.snap.ext}`", ""] + table(["Signal", "Rows", "Examples"], sig)
            + ["", f"Pages behind a signal: `golden-datasets pages sample --rule {rid} --signal <signal> -n 20`."])


def _ruleset_comment_lines(p: _Prompt) -> list[str]:
    if not p.discussion["ruleset"]:
        return []
    return (["## Comments on the ruleset", "", RULESET_COMMENTS_ABOUT, "", RULESET_HEURISTICS, ""]
            + _comment_table(p.discussion["ruleset"]) + [""])


def _question_lines(p: _Prompt) -> list[str]:
    if not p.questions:
        return []
    rows = []
    for _, (_rid, a) in sorted(p.questions.items(), key=lambda kv: (kv[1][1]["page_stem"] or "", kv[0])):
        if a["page_stem"]:
            p.refs.add(a["page_stem"])
        said = f"\"{short(a['note'], 400)}\"" if a["note"] else "(flagged, no note)"
        rows.append([_who(a), f"`{a['page_stem']}`" if a["page_stem"] else "—", a["author"], said])
    return (["## Questions for the institution (not bugs)", "",
             "Only the college can answer these. Don't change a rule for them, but mention them in your report.", ""]
            + table(["Course / page", "Page", "From", "Question"], rows) + [""])


def _how_to_work_lines(p: _Prompt) -> list[str]:
    first = p.targets[0] if p.targets else "<rule_id>"
    names_line = " ".join(p.targets) or "<rule_id>"
    draft = f"drafts/{p.targets[0]}.json" if len(p.targets) == 1 else \
        ("drafts/rules.json" if p.picked else "drafts/needs-work.json")
    steps = [[cell.format(first=first, names=names_line, draft=draft) for cell in row] for row in IMPROVE_STEPS]
    return (["## How to work", "",
             "Everything above comes from these commands; run them for more, or when the annotations change.", ""]
            + table(["Step", "Command", "What it gives"], steps) + ["", BEFORE_PUBLISHING, ""])


def _comment_table(events: list[dict]) -> list[str]:
    return table(["From", "When", "About", "Comment"],
                 [[e["author"], e["at"][:10], TOPIC_NAME.get(e.get("topic"), "comment"),
                   f"\"{short(e.get('note'), 500)}\""] for e in events])


def _annotation_row(rule: dict, a: dict, n: int, refs: set) -> list:
    label = {"still-wrong": "STILL WRONG", "missing": "MISSING"}.get(a["state"], (a["verdict"] or "").upper())
    if a["page_stem"]:
        refs.add(a["page_stem"])
    page = f"`{a['page_stem']}`" if a["page_stem"] else "—"
    if rule["kind"] == "property":
        return [n, f"**{label}**", _who(a), page, _seen(rule, a), _expected(a), _notes(a)]
    return [n, f"**{label}**", _who(a), page, _problem(rule, a), _notes(a)]


def _seen(rule: dict, a: dict) -> str:
    seen = f"v{a['rule_version_seen']}: \"{short(a['value_seen'], 200)}\""
    if a["rule_version_seen"] != rule["version"] and a["has_row"]:
        seen += " → now unchanged" if norm(a["value_seen"]) == norm(a["current_value"]) \
            else f" → now (v{rule['version']}): \"{short(a['current_value'], 140)}\""
    return seen


def _expected(a: dict) -> str:
    exp = a["expected"] or {}
    if a["verdict"] == "missing" and not exp.get("text"):
        return "a value: the rule finds nothing here"
    return f"\"{short(exp['text'], 200)}\"{_location(a)}" if exp.get("text") is not None else "—"


def _problem(rule: dict, a: dict) -> str:
    if a["verdict"] == "missing":
        exp = a["expected"] or {}
        return (f"not found: \"{short(exp['text'], 160)}\"" + (f" at `{exp['css_path']}`" if exp.get("css_path") else "")
                if exp.get("text") else "the rule should find this page (or a course on it) and doesn't")
    what = "recognises this page" if rule["kind"] == "page" else "finds this course block"
    return f"wrong that the rule {what}" + (f" (shown as \"{short(a['value_seen'], 80)}\")" if a["value_seen"] else "")


def _location(a: dict) -> str:
    exp = a["expected"] or {}
    if exp.get("segments"):  # a value in several pieces on the page; an `out` piece is text the value must not have
        return f" ({len(exp['segments'])} pieces: " + "; ".join(
            ("NOT in the answer: " if s.get("polarity") == "out" else "")
            + (_where(a, s).removeprefix(" (").removesuffix(")") or json.dumps(s.get("text"), ensure_ascii=False))
            for s in exp["segments"]) + ")"
    return _where(a, exp)


def _where(a: dict, exp: dict) -> str:
    if not exp.get("css_path") or exp.get("char_start") is None:
        return ""
    if exp["css_path"] == a["current_css_path"]:
        where = "of the extracted element"
    elif a["occurrence_css_path"] and exp["css_path"].startswith(a["occurrence_css_path"] + " > "):
        where = f"of `<occurrence> > {exp['css_path'][len(a['occurrence_css_path']) + 3:]}`"
    else:
        where = f"of `…{' > '.join(exp['css_path'].split(' > ')[-2:])}`"
    return f" (chars {exp['char_start']}–{exp['char_end']} {where})"


def _who(a: dict) -> str:
    return a["record_external_identifier"] or a["page_title"] or a["page_stem"] or "—"


def _notes(a: dict) -> str:
    said = [f"{a['author']}: \"{short(a['note'], 300)}\"" if a["note"] else f"by {a['author']}"]
    said += [f"{c['author']}: \"{short(c['note'], 300)}\"" for c in a["comments"]]
    return "; ".join(said)


def _signal_rows(rv: Review, rid: str) -> list[list]:
    snap = rv.snap
    examples: dict[str, list[tuple[str, str]]] = {}
    for row in snap.rows(rid):
        for s in row["signals"]:
            examples.setdefault(s["signal"], []).append((row["record_external_identifier"] or row["page_stem"], s["detail"] or ""))
    counts = snap.signal_counts.get(rid, {})
    out = []
    for name, total in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        ex = sorted(set(examples.get(name, [])))[:3]
        out.append([f"`{name}`", f"{total:,}", "; ".join(f"{who}: {short(d, 90)}" for who, d in ex) or "—"])
    return out


# =====================================================================================================
# The first rules of a catalog added from the picker (spec §7.1)
# =====================================================================================================
def build_first_rules_prompt(ctx: Ctx, target: str = "azure", azure_root: str | None = None,
                             run: dict | None = None) -> dict:
    """The prompt behind **Generate rules** on a new catalog's card: write and publish its first ruleset, starting from
    the rules of a catalog already in the Studio."""
    p = _first_prompt(ctx, target, azure_root, run)
    text = _finish(_first_rules_lines(p), target)
    return {"text": text, "chars": len(text), "tokens": round(len(text) / 4), "template": p.tmpl,
            "template_name": info(p.ready[p.tmpl])["name"] if p.tmpl in p.ready else p.tmpl,
            "target": target, "root": p.root_uri, "warning": cli_source()["warning"]}


@dataclass
class _FirstPrompt:
    """What the first-rules prompt's sections read."""
    ctx: Ctx
    target: str
    run: dict | None
    root_uri: str
    name: str
    seed: str | None
    pages: list[dict]
    urls: list[str]
    ready: dict[str, str]           # short name → folder of the catalogs that already have rules (the templates)
    guess: tuple[str, str] | None   # (short name, platform) of the template whose platform the pages name
    tmpl: str
    mine: dict[str, dict]           # this catalog's rules so far (none for a new catalog)
    draft: str


def _first_prompt(ctx: Ctx, target: str, azure_root: str | None, run: dict | None) -> _FirstPrompt:
    entry = ctx.entry() or {}
    seed = entry.get("seed_url")
    pages = ctx.pages()
    urls = sorted(p["url"] for p in pages)
    ready = _ready_templates(ctx)
    guess = template_for(" ".join([seed or "", *urls[:400], _sample_html(ctx, pages)]), ready)
    tmpl = guess[0] if guess else "marshall" if "marshall" in ready else next(iter(sorted(ready)), "<catalog>")
    mine = ctx.ruleset_rules(ctx.latest_ruleset())[1] if ctx.ruleset_versions() else {}
    return _FirstPrompt(ctx, target, run, _root_uri(ctx, target, azure_root),
                        entry.get("name") or info(ctx.catalog)["name"], seed, pages, urls, ready, guess, tmpl, mine,
                        "drafts/more-rules.json" if mine else "drafts/first-rules.json")


def _ready_templates(ctx: Ctx) -> dict[str, str]:
    from .catalogs import CATALOGS

    return {info(c["catalog"])["short"]: c["catalog"] for c in ctx.manifest()["catalogs"]
            if c["catalog"] in CATALOGS and manifest.has_rules(c, ctx.cls)}


def _sample_html(ctx: Ctx, pages: list[dict]) -> str:
    """The start of three saved pages, spread over the crawl."""
    sample = [p["page_stem"] for p in sorted(pages, key=lambda p: p["page_stem"])[:: max(1, len(pages) // 3)][:3]]
    return " ".join(ctx.page_path(stem).read_text(errors="replace")[:200_000] for stem in sample)


def _first_rules_lines(p: _FirstPrompt) -> list[str]:
    lines = [f"# {'Write the rules still missing' if p.mine else 'Write the first rules'} — {p.name} catalog", "",
             MORE_INTRO if p.mine else FIRST_INTRO, ""]
    lines += _run_header(p.run, p.ctx) if p.target == "k2" else []
    lines += _setup(p.ctx, p.target, p.root_uri, "", check='golden-datasets sql "SELECT count(*) AS pages FROM pages"',
                    run=p.run)
    lines += _first_context_lines(p) + _page_shape_lines(p) + _template_lines(p) + FIRST_FORMATS
    lines += _every_property_lines(p) + RULE_TYPE_LINES + FIRST_LIMITS + _first_how_to_work_lines(p)
    return lines + (_run_close(p.run) if p.target == "k2" else
                    [f"Report back, per property: the rule written, or why none; the final `rule try` table; and "
                     f"coverage (properties with a rule, of {len(model.property_rows(p.ctx.cls))})."])


def _first_context_lines(p: _FirstPrompt) -> list[str]:
    return ["## Context", ""] + table(["", ""], [
        ["Catalog", f"`{p.ctx.catalog}` ({p.name})"],
        ["Catalog URL", p.seed or "—"],
        ["Crawl", f"`{p.ctx.crawl}`, {len(p.pages):,} saved pages (scripts already ran at crawl time)"],
        ["Ruleset", f"v{p.ctx.latest_ruleset()}: this catalog's rules so far" if p.mine else "none yet: you publish v1"],
        ["Storage root", f"`{p.root_uri}`"],
        ["A saved page", "`golden-datasets pages get <page_stem>` prints its local path and live URL"],
    ])


def _page_shape_lines(p: _FirstPrompt) -> list[str]:
    return (["", "### What the saved pages look like", "",
             "The most common URL shapes (digits as `N`, the last folder as `*`):", ""]
            + table(["Shape", "Pages", "Example"], url_shapes(p.urls)))


def _template_lines(p: _FirstPrompt) -> list[str]:
    rows = []
    for sn in sorted(p.ready):
        meta = info(p.ready[sn])
        rows.append([f"`{sn}`", meta["name"], meta["platform"] or "—",
                     "**suggested**" if p.guess and p.guess[0] == sn else ""])
    if p.guess:
        advice = (f"This catalog's pages look like {p.guess[1]}, the platform of `{p.guess[0]}`: start from its "
                  "rules. If another template's markup is closer, use that.")
    else:
        advice = (f"No template's platform shows in the URLs: look at a few pages, then start from the closest "
                  f"(`{p.tmpl}` if unsure).")
    return ["", "### Templates: catalogs that already have rules", ""] + \
        table(["Catalog", "Name", "Platform", ""], rows) + ["", advice, ""]


def _every_property_lines(p: _FirstPrompt) -> list[str]:
    cls = p.ctx.cls
    return (["## Every property", "",
             f"One property rule per row ({len(model.property_rows(cls))} in all), with the rule id of "
             f"`properties/{cls}.csv` (`golden-datasets properties list --class {cls}`). Paths are stored with `>` "
             "and shown here with arrows. *How catalogs read it* is each catalog's current rule, a starting point "
             "for a page like theirs.", ""]
            + table(["Property", "Path", "Parent", "Values", "Tier", "The sheet's definition", "Sample",
                     "How catalogs read it"], property_table(p.ctx, _rules_by_catalog(p))))


def _rules_by_catalog(p: _FirstPrompt) -> dict[str, dict[str, dict]]:
    """Each template catalog's latest rules, and this catalog's own rules so far."""
    rules_by_catalog = {}
    for sn, folder in sorted(p.ready.items()):
        try:
            other = Ctx(p.ctx.root, folder, cls=p.ctx.cls)
            rules_by_catalog[sn] = other.ruleset_rules(other.latest_ruleset())[1]
        except (UserError, FileNotFoundError):
            continue
    if p.mine:
        rules_by_catalog.setdefault(info(p.ctx.catalog)["short"], p.mine)
    return rules_by_catalog


def _first_how_to_work_lines(p: _FirstPrompt) -> list[str]:
    return (["## How to work", "", FIRST_ORDER, ""]
            + table(["Step", "Command", "What it gives"], [*LOOK_STEPS, _start_step(p), *_write_steps(p)])
            + ["", "Do not commit or push anything.", ""])


def _start_step(p: _FirstPrompt) -> list[str]:
    if p.mine:
        return ["2. Start", f"`golden-datasets rule draft --all > {p.draft}`",
                "this catalog's rules so far: the ones with `rule_type: none` are yours to write"]
    return ["2. Template", f"`golden-datasets rule draft --catalog {p.tmpl} --all --for {p.ctx.catalog} > {p.draft}`",
            f"every rule of `{p.tmpl}` and its settings, as a draft for this catalog"]


def _write_steps(p: _FirstPrompt) -> list[list[str]]:
    note = "More property rules" if p.mine else f"First rules, from {p.tmpl}'s"
    return [["3. Write", f"edit `{p.draft}`",
             "one rule per property of the table: its `definition`, and `what` / `how` / `why` and the examples for "
             "this catalog; `none` where the pages don't print it"],
            ["4. Try", f"`golden-datasets rule try {p.draft}`",
             "runs the draft over the whole crawl (writes nothing): per rule, how many pages / courses / values it "
             "finds. Iterate until the locator finds about as many courses as the catalog has and each property has "
             "a value wherever the page prints it; spot-check values against a few pages"],
            ["5. Publish", f"`golden-datasets rule publish {p.draft} --note \"{note}\"`",
             "the ruleset and its extraction: the catalog opens in the Studio"]]


def property_table(ctx: Ctx, rules_by_catalog: dict[str, dict[str, dict]]) -> list[list]:
    """Every property of the class's properties file: its name, path, parent, list, tier, the sheet's definition and
    sample, and how each catalog with a rule reads it."""
    tiers = dict(properties.TIERS)
    return [_property_row(r, tiers, rules_by_catalog) for r in model.property_rows(ctx.cls)]


def _property_row(r: dict, tiers: dict, rules_by_catalog: dict[str, dict[str, dict]]) -> list:
    how = []
    for sn, rules in sorted(rules_by_catalog.items()):
        rule = rules.get(r["rule_id"])
        if rule is not None and rule["definition"].get("rule_type") != "none":
            how.append(f"{sn}: {_how_read(rule)}")
    definition = re.sub(r"\s+", " ", r["definition_text"])[:140]
    return [r["label"], f"`{r['path'].replace('>', ' → ')}`" if r["path"] else "—",
            r["parent"].split(":", 1)[-1] if r["parent"] else "", "list" if r["multiple"] else "single",
            ("record key, " if r["record_key"] else "") + tiers[properties.tier(r)], definition,
            re.sub(r"\s+", " ", r["sample"])[:40], "; ".join(how) or "none yet"]


def _how_read(rule: dict) -> str:
    """How a rule reads its property, in a few words (Generate rules' property table)."""
    d = rule["definition"]
    inp = (d.get("input") or {}).get("from", "record")
    bits = [d.get("rule_type", "?")]
    if inp != "record":
        bits.append(f"input {inp}" + (f" {d['input'].get('rule')}" if inp == "rule" else ""))
    if d.get("multiple"):
        bits.append(f"split {d['multiple'].get('split')}")
    for k in ("attribute", "join", "label"):
        if d.get(k):
            bits.append(k)
    return ", ".join(bits)


def url_shapes(urls: list[str], n: int = 12) -> list[list]:
    """The most common URL shapes (digits folded to N, query values dropped), with a count and an example."""
    from collections import Counter

    shapes: Counter = Counter()
    example: dict[str, str] = {}
    for u in urls:
        shape = _url_shape(u)
        shapes[shape] += 1
        example.setdefault(shape, u)
    return [[f"`{sh}`", f"{c:,}", example[sh]] for sh, c in shapes.most_common(n)]


def _url_shape(url: str) -> str:
    from urllib.parse import parse_qsl, urlsplit

    p = urlsplit(url)
    parts = (re.sub(r"\d+", "N", p.path.rstrip("/")) or "/").split("/")
    if len(parts) > 2:  # keep the folders; the last segment is usually the record's own slug
        parts[-1] = "*"
    return "/".join(parts) + ("?" + "&".join(sorted(k for k, _ in parse_qsl(p.query))) if p.query else "")


def template_for(text: str, ready: dict[str, str]) -> tuple[str, str] | None:
    """(short name, platform) of the Studio catalog whose platform `text` (URLs and a few pages' HTML) names."""
    for pattern, platform, sn in PLATFORM_HINTS:
        if sn in ready and re.search(pattern, text, re.I):
            return sn, platform
    return None


# =====================================================================================================
# Sections both prompts share: a run's header, the setup, a run's ending
# =====================================================================================================
def _run_header(run: dict | None, ctx: Ctx) -> list[str]:
    """target k2: who started this run, that nobody will answer, and how to report (agent_runs.py)."""
    rid, d = _run_id(run), _run_dir(run)
    who = run["started_by"] if run else "someone"
    return ["## This is a Golden Dataset Studio run", "",
            f"Run `{rid}`, started by {who} from the Studio. You're working unattended: nobody will answer "
            "questions, and people are watching your progress notes in the Studio. You may delegate parts of the "
            "work to subagents; give them the run id and the commands below.", "",
            REPORT_AS_YOU_GO, "",
            "```sh", f'cd {d} && ./bin/golden-datasets run note "<one line>"', "```", "",
            FIRST_NOTE, "",
            _every_command_line(d), "",
            "Report with `./bin/golden-datasets run note` and `run done` only; don't use `k2 respond` or `k2 done`.",
            ""]


def _every_command_line(d: str) -> str:
    return (f"**Start every command with `cd {d} && ./bin/golden-datasets`** (Setup installs this run's own copy of "
            "the CLI there). Your shell returns to the workspace folder whenever a command leaves it, and only this "
            "folder's settings name this run's root and catalog. When you finish, the last section says how to end "
            "the run. If something blocks you, write a note saying what, and end the run as failed rather than "
            "working around it (if the install itself fails, these commands don't exist: stop and say so in your "
            "reply).")


def _setup(ctx: Ctx, target: str, root_uri: str, first_rule: str, check: str | None = None,
           run: dict | None = None) -> list[str]:
    if target == "k2":
        return _setup_k2(ctx, root_uri, first_rule, check, run)
    azure = root_uri.startswith("azure://")  # the root decides: a Studio that serves Azure gives Azure either way
    lines = ["## Setup", "",
             f"Do this once, in the folder you work in. Your shell commands don't share `export`s, so `golden-datasets` "
             f"reads its root and catalog from `{ENV_FILE}` in the current folder (or a parent).", ""]
    lines += _install_lines(cli_source())
    if azure:
        lines.append(_azure_sign_in(2, re.sub(r"^azure://https?://([^./]+).*", r"\1", root_uri)))
    lines += _point_cli_lines(ctx, root_uri, check or f"golden-datasets rule show {first_rule}", azure)
    return lines + [AZURE_ROOT_NOTE if azure else LOCAL_ROOT_NOTE, ""]


def _install_lines(src: dict) -> list[str]:
    return [f"1. Install the CLI from the `{src['ref']}` branch (needs uv; if `uv` is missing: "
            "`curl -LsSf https://astral.sh/uv/install.sh | sh`):",
            "", "   ```sh", f"   uv tool install --reinstall '{src['spec']}'", "   golden-datasets --help", "   ```", "",
            f"   Without installing: `uvx --from '{src['spec']}' golden-datasets …`."]


def _azure_sign_in(n: int, account: str) -> str:
    return (f"{n}. Sign in to Azure. `az account show` says whether you are; if not, `az login` (no browser here: "
            "`az login --use-device-code`, and give the person the code). The CLI reads the storage key through "
            f"`az` itself, so nothing secret goes in a file or an `export`: you only need an Azure account that "
            f"can read the keys of the `{account}` storage account. If `az` is missing: "
            "`brew install azure-cli`, or https://aka.ms/InstallAzureCLI.")


def _point_cli_lines(ctx: Ctx, root_uri: str, check: str, azure: bool) -> list[str]:
    n = 3 if azure else 2
    return [f"{n}. Point the CLI at the {'shared Azure' if azure else 'Studio'} root and check it:",
            "", "   ```sh", f"   cat > {ENV_FILE} <<'EOF'", f"   GOLDEN_DATASETS_ROOT={root_uri}",
            f"   GOLDEN_DATASETS_CATALOG={info(ctx.catalog)['short']}", f"   GOLDEN_DATASETS_CLASS={ctx.cls}", "   EOF",
            f"   {check}", "   ```", ""]


def _setup_k2(ctx: Ctx, root_uri: str, first_rule: str, check: str | None, run: dict | None) -> list[str]:
    src, d = cli_source(), _run_dir(run)
    check = (check or f"golden-datasets rule show {first_rule}").replace("golden-datasets ", "./bin/golden-datasets ", 1)
    return (["## Setup", "",
             f"`golden-datasets` reads its settings from `{ENV_FILE}` files in the current folder and its parents. "
             f"Azure access is set up on this machine: SAS tokens for the storage containers are in `{k2_work()}/{ENV_FILE}`, "
             "which every folder below it reads. No `az login`.", "",
             K2_MAKE_FOLDER, ""]
            + _k2_install_lines(ctx, root_uri, run, src, check)
            + [f"   If the install fails, don't install another version: `golden-datasets run` exists only on "
               f"`{src['ref']}`. Stop and say so in your reply.", "",
               f"2. Keep your drafts in this run's folder (`{d}/drafts/`), and the values you work out in "
               f"`{d}/inferred.json`. Pages download once into a local cache; `rule publish` uploads the new versions, "
               "and the Studio shows them within seconds.", ""])


def _k2_install_lines(ctx: Ctx, root_uri: str, run: dict | None, src: dict, check: str) -> list[str]:
    d, tools = _run_dir(run), _tools_root()
    t = f"{tools}/{_run_id(run)}"
    return ["   ```sh",
            f"   find {tools} -mindepth 1 -maxdepth 1 -mmin +{TOOLS_KEPT_MINUTES} -exec rm -rf {{}} + 2>/dev/null; true",
            f"   mkdir -p {d} {t} && cd {d} && UV_TOOL_DIR={t} UV_TOOL_BIN_DIR={d}/bin uv tool install '{src['spec']}'",
            f"   printf '%s\\n' 'GOLDEN_DATASETS_ROOT={root_uri}' "
            f"'GOLDEN_DATASETS_CATALOG={info(ctx.catalog)['short']}' 'GOLDEN_DATASETS_CLASS={ctx.cls}' "
            f"'GOLDEN_DATASETS_RUN={_run_id(run)}' > {d}/{ENV_FILE}",
            f"   cd {d} && {check}", "   ```", ""]


def _run_close(run: dict | None) -> list[str]:
    d = _run_dir(run)
    return (["## End the run", "",
             f"When you have published (or can't), write `{d}/report.json` and end the run with it. The CLI checks "
             "every reference and quote, then writes the report people read in the Studio: each course as its row in "
             "the Rules tab (title, value, verdicts, comments), what changed per rule, and the whole-suite check of "
             "your last `rule try` or `rule publish` (saved for you; don't copy numbers).", ""]
            + REPORT_GUIDE
            + ["```sh", f"cd {d} && ./bin/golden-datasets run done --report report.json", "```", "",
               "If it lists problems (an unknown id, a quote not found, a changed rule missing from `also_changed`), "
               "fix `report.json` and run it again. Your row comments are saved on the rows only once the report "
               "passes. Then stop, and give the report it prints as your reply."])


# =====================================================================================================
# Helpers
# =====================================================================================================
def _root_uri(ctx: Ctx, target: str, azure_root: str | None) -> str:
    """The root Claude works on: this Studio's, unless a local Studio hands the work to the Azure root."""
    if target == "local" or ctx.root.uri.startswith("azure://"):
        return ctx.root.uri
    return azure_root or DEFAULT_AZURE_ROOT


def _finish(lines: list[str], target: str) -> str:
    text = "\n".join(lines) + "\n"
    if target == "k2":  # this run's own copy of the CLI (Setup installs it into the run folder)
        text = text.replace("`golden-datasets ", "`./bin/golden-datasets ")
    return text


def has_raw_html(text: str) -> bool:
    return bool(_HTML.search(text))


def cli_source() -> dict:
    """Where Claude installs `golden-datasets` from: this checkout's branch on GitHub ($GOLDEN_DATASETS_GIT_REF wins;
    `main` outside a checkout). `warning` says when the branch has commits GitHub doesn't."""
    ref = os.environ.get("GOLDEN_DATASETS_GIT_REF") or _git("rev-parse", "--abbrev-ref", "HEAD")
    warning = None
    if not ref or ref == "HEAD":
        ref = "main"
    elif not os.environ.get("GOLDEN_DATASETS_GIT_REF") and _git("rev-parse", "--git-dir"):
        warning = _unpushed_warning(ref)
    return {"ref": ref, "spec": f"git+{REPO}@{ref}#subdirectory={SUBDIR}", "warning": warning}


def _unpushed_warning(ref: str) -> str | None:
    ahead = _git("rev-list", "--count", "@{u}..HEAD")
    if ahead is None:
        return f"Branch {ref} isn't on GitHub: push it, or the install step fails."
    if ahead != "0":
        return f"Branch {ref} has {ahead} commit(s) not pushed to GitHub: Claude's CLI won't have them."
    return None


def _git(*args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(Path(__file__).resolve().parent), *args],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def k2_work() -> str:
    return (os.environ.get("GOLDEN_DATASETS_K2_WORK") or K2_WORK).rstrip("/")


def _run_id(run: dict | None) -> str:
    return run["run_id"] if run else "<run_id>"


def _run_dir(run: dict | None) -> str:
    """This run's folder on K2: absolute, because Claude Code moves the shell back to the workspace folder whenever a
    command leaves it, so every command `cd`s here first."""
    agent = ((run or {}).get("k2") or {}).get("agent") or "golden-rules"
    return f"{k2_work()}/{agent}/runs/{_run_id(run)}"


def _tools_root() -> str:
    """Where runs install their own copy of the CLI: next to K2's work folder, never inside a workspace. K2 stops
    trusting a workspace it can't scan whole (over 20,000 folders); a Python environment is ~440 folders, so keeping
    one per run in `runs/<run_id>/.tools` held every run with `folder_trust_pending` after ~55 runs (2026-11-12)."""
    return f"{k2_work().rsplit('/', 1)[0]}/.cache/golden-datasets-tools"


def table(header: list[str], rows: list[list]) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + \
           ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]


def cell(v) -> str:
    """Text safe inside a Markdown table cell: one line, no bare `|`."""
    return str(v).replace("\n", "⏎ ").replace("|", "\\|")


# =====================================================================================================
# The prompts' fixed text
# =====================================================================================================
INTRO = ("You are improving the declarative extraction rules of **CTDL Golden Dataset Studio** for one catalog. "
         "A domain expert reviewed the extracted values and left annotations. Your job: change the rule(s) below so "
         "the annotated problems are fixed without breaking anything the expert marked correct, then publish a new "
         "version. Work only through the `golden-datasets` CLI; never edit files in the storage root yourself.")

FORMAT = {
    "page": "- Page rule format: `definition` has `url_regex` (on the page URL), optional `requires_selector` / "
            "`forbids_selector` (CSS, evaluated from the content root), `label`. A page is recognised when every "
            "test passes.",
    "locator": "- Record locator format: `definition` has `page_rules` (the page rules whose pages it runs on), "
               "optional `scope` (CSS), `repeat` (CSS: each match is one course occurrence; null = the content root "
               "is one course), optional `repeat_filter` {`selector`, `regex`} (keep a match only when that text "
               "matches).",
    "property": "- Property rule format: `definition` has `locator`, `rule_type` (css / css+regex / regex / labelled / "
                "constant / source_url / none), optional `input` (what it reads: `{\"from\": \"record\"}` by "
                "default, `page`, `url`, or `{\"from\": \"rule\", \"rule\": <rule id>}` for another rule's "
                "output), `selector` (CSS, inside one course occurrence), optional `attribute`, `join`, `regex` + "
                "`group`, `multiple` (a list: `{\"split\": \"elements\" | \"separator\" | \"regex\", …, "
                "\"keep\": <regex>}`), `transforms` (strip, collapse_ws, upper, lower, remove_spaces, "
                "generated_id:<type> (issue #368's `{type}-{normalized name}`, e.g. `program-anthropology-b.a.`; with "
                "`fallback`, a definition read when the rule finds nothing, an identifier is the printed code, else "
                "generated), "
                "rstrip:<chars>), optional `map`. Order: the element's text (a `<br>` reads as a newline, script and "
                "style text is left out) → `regex` (Python, MULTILINE) → `group` → the split → `keep` → `transforms` "
                "→ `map`.",
}
#: The first-pass prompt (sme-fixes §3): a template's locator text says what *its* pages are ("one course per course
#: page" on AVC); a catalog whose pages list many courses (CCSF's department pages) needs its own words.
LOCATOR_NAMING = (
    "- Name and describe the record locator and its page rule by what they do on **this** catalog, not in the "
    "template's words. First count the courses on a few pages: **one course per page** → `repeat: null`, `what` "
    "\"The whole page is one course\", page rule `what` \"Pages that are one course's own page\"; **many courses per "
    "page** (a department or subject page) → `repeat: <the CSS of one course's block>`, `what` \"Each `<repeat>` block "
    "on a page is one course\", page rule `what` \"Pages that list courses\". Keep the rule ids (`course-page`, "
    "`locator-course-page`): property rules point at them. The Studio titles the locator from `repeat` (\"Course "
    "blocks: every … on the page\" or \"Whole page is one course\").")

EDIT_LIMITS = [
    "- You edit a draft file only (`golden-datasets rule draft …`). Never write to the storage root, the "
    "annotation log or the saved pages.",
    "- `golden-datasets` assigns versions and hashes: don't add `version` or `content_hash` to a draft.",
]
WORK_LIMITS = [
    "- Rules stay declarative (the formats above). If the format can't express the fix, stop and say so.",
    "- Every `rule try` checks all the catalog's rules against all their golden values (values marked "
    "correct, expected values, and the values you infer). Publish only when it says nothing that was right "
    "got worse (`0 got worse`). Never use `--force`.",
    "- **Inferred values.** When a course is marked wrong with no expected value, work out the value from the "
    "page and the annotations. Record it in `inferred.json` in your folder (`[{\"rule\", \"course\", "
    "\"annotation\", \"value\"}]`, `\"\"` for empty), with the quotes it rests on in your report. Publish "
    "when nothing marked correct changes and every open annotation is right, against its expected value or "
    "the value you inferred.",
    "- If `rule publish` says another run changed one of your rules meanwhile, run `rule draft` again and "
    "redo your change on the latest version.",
]
RULESET_COMMENTS_ABOUT = (
    "About the catalog's rules as a whole: new rules, other approaches, whether a rule is needed. Within the "
    "limits above, act on what fits the rule(s) in this prompt, and answer the rest in your report.")
RULESET_HEURISTICS = (
    "A suggested rule may be a domain expert's heuristic rather than something read off the page, e.g. "
    "\"every course in this catalog is in English\": that is a property rule with `rule_type` `constant` "
    "(or `source_url` for the page's address), applied to every course the locator finds. Use the expert's "
    "heuristic when the pages can't contradict it; say so in `why`.")
#: The improve prompt's steps; {first}, {names} and {draft} are filled per prompt.
IMPROVE_STEPS = [
    ["1. Read", "`golden-datasets rule show {first}`",
     "definition, what/how/why, examples, versions, status, fill and signal counts (one rule per call); "
     "`golden-datasets rule list`: every rule"],
    ["", "`golden-datasets rule annotations {first} --open`",
     "every open annotation, with full css paths, character offsets and page paths; without `--open`: every "
     "annotation, including the values marked correct"],
    ["", "`golden-datasets pages get <page_stem>`",
     "makes a saved page available locally and prints `<path><TAB><url>` (a unique part of the stem works, e.g. "
     "`course-geog222`); read it, searching for the expected text"],
    ["", "`golden-datasets pages sample --rule {first} [--signal <signal>] -n 20`", "more pages where the rule fires"],
    ["", "`golden-datasets rule downstream {names}`", "the rules that read each rule: what an edit can move"],
    ["", "`golden-datasets run context {names}`", "each rule's last AI run and the annotations since"],
    ["", "`golden-datasets sql \"SELECT …\"`",
     "DuckDB over the views `pages`, `occurrences`, `matches`, `signals`, `annotations`, `rules` "
     "(`--format json`: one object per line)"],
    ["2. Draft", "`golden-datasets rule draft {names} > {draft}`",
     "the current version(s) as an editable draft. Change only `definition`, `what`, `how`, `why` and `examples` "
     "(update an example your fix makes wrong)"],
    ["3. Try", "`golden-datasets rule try {draft}`",
     "reruns every rule over the whole crawl (writes nothing). First line: the whole suite, every rule against "
     "every golden value (\"1 now right, 0 got worse\"), then the rules whose values changed; then per changed "
     "rule fixed / still wrong / newly wrong, values changed, signal counts before → after. Reads "
     "`inferred.json`. Iterate until every open annotation is right and nothing got worse"],
    ["4. Publish", "`golden-datasets rule publish {draft} --note \"…\"`",
     "new rule version(s), a new ruleset version and its extraction; one publish at a time per catalog. It "
     "reruns the whole suite and refuses if anything that was right got worse. If another run published "
     "meanwhile, it rebases your rules on the latest version, or refuses if that run changed the same rules"],
]
BEFORE_PUBLISHING = (
    "Before publishing, fill the draft's text: *what* says what the rule finds, in page terms; *how* says how; "
    "*why* says why this version is better than the last, citing the course codes and the expert's notes. "
    "Add one example per fix (`{\"input\": <the selected text>, \"output\": <the value>}`). Do not commit or "
    "push anything.")

REPORT_AS_YOU_GO = (
    "Report as you go, one short line per step: what you're checking, what you found, what you changed, "
    "what you published. People read these to know you're still working:")
FIRST_NOTE = (
    "**Your first action is a note.** As soon as Setup's first step has installed the CLI and made the "
    "folder, before anything else, write one (`\"Starting: <what you'll do first>\"`). If no note arrives "
    "within 5 minutes, the Studio tells people you may have stopped.")
K2_MAKE_FOLDER = (
    "1. Make this run's folder, install this run's own copy of the CLI into it (uv is installed; another run "
    "may be installing its copy at the same time, so never install into the shared tool folder), and name "
    "the run's root, catalog and class:")
AZURE_ROOT_NOTE = ("   Pages download once into a local cache (`~/.cache/golden-datasets`); `rule publish` uploads the "
                   "new versions, and the Studio shows them when it serves this root.")
LOCAL_ROOT_NOTE = ("   This root is a folder on the machine that runs the Studio: run Claude Code on that machine. "
                   "`rule publish` writes there, and the Studio shows the new version right away.")

REFERENCES = [
    ["`{\"course\": \"ACCT199\"}`", "a course: the report shows its row (title, value, verdicts, comments)"],
    ["`{\"value\": {\"course\": \"GEOG222\", \"rule\": \"<rule id>\"}}`", "a course's value in a rule"],
    ["`{\"note\": \"an-39127172c8e8\"}`", "a verdict's note or a comment (ids from `rule annotations`)"],
    ["`{\"page\": {\"course\": \"BIOL110\", \"quote\": \"<words copied from the page>\"}}`",
     "a passage of the course's saved page"],
    ["`{\"courses\": {\"rule\": \"<rule id>\", \"verdict\": \"correct\"}}` or `{\"courses\": [\"AERO199\", \"AJ912\"]}`",
     "a set of courses: by their verdict in a rule (`correct` or `wrong`), or listed"],
]
REPORT_FIELDS = [
    ["`ending`", "`published` (you published a new ruleset), `needs_you` (you stopped because only people can "
     "unblock it) or `failed` (something broke: install, storage, a command)"],
    ["`reason`", "`failed` only: what broke, in one line"],
    ["`rules`", "one per rule to improve: `{rule, outcome, now, why}`. `outcome`: `published`, `held`, `not changed` "
     "or `failed`; `now`: what its values are now, in a few words (\"empty on every course\"); `why`: optional, one line"],
    ["`also_changed`", "every other rule you changed: `{rule, because, why}`. `because`: `{\"reads\": <rule>}` or "
     "`{\"read_by\": <rule>}` when that is the link; `why`: one line. The CLI checks this list against what you "
     "published"],
    ["`rows`", "`{rule, course, comment}`: for a row you changed or reason about, one sentence: what the value is "
     "now and why. It appears on that row, next to the reviewers' comments. Don't tell people what to press or what "
     "to do"],
    ["`inferred`", "the values in `inferred.json`: `{rule, course, annotation, value, evidence, left_out}`. "
     "`evidence`: the quotes the value rests on; `left_out`: `[{\"quote\": <page words the value leaves out>}]`"],
    ["`to_do`", "at most 3 decisions for people, most important first: `{ask, why, about, evidence, options, "
     "effect}`. `ask`: the question; `why`: at most two short sentences of plain context, naming the courses and "
     "rules; `about`: references; `evidence`: quotes, or `{\"set\": <courses reference>, \"label\": \"marked "
     "correct\"}`; `options`: `[{answer, label, do: {mark, courses, rule}, then: {publish: [rule ids]}}]`: `label` is "
     "the action in a few words, as its button says it (\"mark the 13 courses Not on the page\"), `mark` one of "
     "`correct`, `wrong`, `not_on_page`, `save_expected`, and `then.publish` lists every rule the next run would "
     "publish after that answer; `effect`: `[{rule, after}]` (`after`: the value, `\"\"` for empty, or "
     "`{\"source\": \"page_url\"}`)"],
    ["`together`", "optional: rules linked by meaning, not by data: `{rules, because: <quote>}`"],
    ["`notes`", "optional, at most 5 lines: anything that fits nowhere else"],
]
REPORT_EXAMPLE = {
    "ending": "needs_you",
    "rules": [{"rule": "course-subject-webpage", "outcome": "held", "now": "the page's address on every course"}],
    "rows": [{"rule": "course-subject-webpage", "course": "ACCT199",
              "comment": "The value is the page's address, as on the 13 courses marked correct."}],
    "to_do": [{"ask": "Is Jared Diener's note on ACCT199 right for every course in the catalog?",
               "why": "His note on ACCT199 says a course in a catalog uses In Catalog instead of Subject Webpage. "
                      "But he marked 13 courses with the page's address in Subject Webpage correct.",
               "about": [{"course": "ACCT199"}],
               "evidence": [{"quote": "use the property ceterms:inCatalog instead of ceterms:subjectWebpage",
                             "from": {"note": "an-39127172c8e8"}},
                            {"set": {"courses": {"rule": "course-subject-webpage", "verdict": "correct"}},
                             "label": "marked correct"}],
               "options": [{"answer": "yes", "label": "mark the 13 courses Not on the page",
                            "do": {"mark": "not_on_page", "courses": {
                                "rule": "course-subject-webpage", "verdict": "correct"}},
                            "then": {"publish": ["course-subject-webpage", "course-in-catalog"]}},
                           {"answer": "no", "label": "mark ACCT199 correct",
                            "do": {"mark": "correct", "courses": ["ACCT199"], "rule": "course-subject-webpage"}}],
               "effect": [{"rule": "course-subject-webpage", "after": ""},
                          {"rule": "course-in-catalog", "after": {"source": "page_url"}}]}],
}
WRITING = ("Write plainly and briefly, for someone who knows the catalog: short sentences, everyday words, one idea "
           "per sentence. Don't join fragments with `·` or other separators. No file names, command names, JSON field "
           "names or scorecard words (\"rule try\", \"got worse\").")
#: How to write report.json, between "End the run"'s first paragraph and the `run done` command.
REPORT_GUIDE = [
    "**Your text is only titles and reasons.** Never restate a value, a course's details, a comment or a "
    "page passage in your own words: refer to it, and the report shows it. References:", "",
    *table(["Reference", "What the report shows"], REFERENCES), "",
    "A quote is `{\"quote\": \"<the exact words>\", \"from\": {\"note\": \"an-…\"}}` (or `{\"page\": "
    "\"<course>\"}`, or `{\"value\": {\"course\", \"rule\"}}`); the words must be in that source, and `…` "
    "joins pieces that appear in that order.", "",
    *table(["Field", "What"], REPORT_FIELDS), "",
    "**Each to-do is something the reviewer does.** Lead with what they must decide: `ask` is the question "
    "and `why` says, in at most two short sentences, why it needs them (name the courses and rules, e.g. "
    "\"Jared Diener's note on ACCT199 says … but he marked 13 courses … correct\"). Make every option an "
    "action the reviewer can take from the report: a `do` that marks courses, with a `label` saying what it "
    "does. The Studio shows each option as a button, then the evidence below. Keep it short, and never show "
    "a bare course code without saying what it is (\"ACCT199, the course Jared Diener marked wrong\"). "
    "Write each `ask` so someone who knows the catalog could answer it from the evidence you attach. A "
    "short example:", "",
    "```json", json.dumps(REPORT_EXAMPLE, indent=1, ensure_ascii=False), "```", "",
    WRITING, "",
]

FIRST_INTRO = ("This catalog was just added to **CTDL Golden Dataset Studio** from a crawl and has no rules yet. Write its "
               "**first ruleset**: a page rule that recognises its course pages, a record locator that finds each course "
               "on them, and **a property rule for every property in the table below**, then publish it as ruleset v1. "
               "A domain expert reviews every value in the Studio afterwards, so aim for rules that are right on nearly "
               "every course, and say where you're unsure. Work only through the `golden-datasets` CLI; never edit "
               "files in the storage root yourself.")
MORE_INTRO = ("This catalog already has rules in **CTDL Golden Dataset Studio**. Write a rule for **every property in the "
              "table below that has no rule here yet** (`rule_type: none`), and publish them as a new ruleset version. "
              "Leave the rules that already work as they are. A domain expert reviews every value afterwards, so aim "
              "for rules that are right on nearly every course, and say where you're unsure. Work only through the "
              "`golden-datasets` CLI; never edit files in the storage root yourself.")
FIRST_FORMATS = [
    FORMAT["page"], FORMAT["locator"], LOCATOR_NAMING, FORMAT["property"],
    "- Settings (the draft's `settings`): `content_root` (CSS: the part of every page that holds the content; "
    "rules evaluate inside it), `page_title`, `signals.course_code_pattern` (a regex for this catalog's course "
    "codes, e.g. `ACCT 2310`).", "",
]
#: One line per rule type and input, each with a real example from the saved pages (property-rules spec §4.3, §4.4).
RULE_TYPES = [
    ["`css`", "an element's text", "AVC `p.header-x-meta` → `3.0 Units`"],
    ["`css+regex`", "part of an element's text", "WVU title `CCMD 741. Behavioral Science … 2 Hours.` → `2 Hours.`"],
    ["`regex`", "part of the input's text (the record, or another rule's output)", "Credit Unit Max Value on Marshall "
     "`1-4 Credit hours`, `-\\s*(\\d+)` → `4`"],
    ["`labelled`", "the text after a label, up to `until` (default `br`): text no selector reaches",
     "UALR `<strong>Prerequisites:</strong> HIST 21103 , HIST 21203 , and six hours…<br>`"],
    ["`constant`", "a fixed value", "Learning Type `Course`; Language `English` when every course is in English"],
    ["`source_url`", "the page URL", "Subject Webpage"],
    ["`none`", "no rule yet: the property isn't on this catalog's pages", "`entryCondition` on most catalogs"],
    ["`input: page`", "the whole saved page (headings outside the record); one value per page",
     "Marshall `h1` `Statistics (STA)` for Subjects"],
    ["`input: url`", "the page URL as text, with a regex", "UARK `course=bookkeeping-quickBooks` for identifier"],
    ["`input: rule`", "another property rule's output on the same course (`\"use\": \"element\"` for its element)",
     "Content Description reads Description's value: AVC `Topics include Linear Functions, Matrices, …`"],
    ["`multiple.split: elements`", "every matched element, one value each", "CCSF `.course-lab-lec-label > span`: "
     "`Lecture - 87.5`, `Lab - 35`"],
    ["`multiple.split: separator`", "one text split on `,` `;` or a line break", "Marshall `No Textbook Required, "
     "Onsite Learning Experience`"],
    ["`multiple.split: regex`", "every match of a regex in one text", "AVC `Total Course In-Class (Contact) Hours "
     "180.0 Total Course Out-of-Class Hours 90.0`: two durations"],
    ["`multiple.keep`", "only the items that match a regex", "UARK modality links: Delivery Type keeps `Online`, "
     "Learning Method Type keeps `Self-Paced`"],
    ["`attribute`", "an attribute instead of the text", "UARK `data-bs-content` popovers, any `href`"],
    ["`join`", "every matched element, in page order, as one value", "UARK description + its `Prior Learning` section"],
    ["`profile`", "a list of objects: each `multiple` item becomes one object, each of `profile.fields` read from the "
     "item with its own sub-definition (`regex`, or a `selector` inside the item's element); `key` is the field "
     "objects pair on. **Only Estimated Duration** is one (fields `ceterms:description`, `ceterms:timeRequired`, key "
     "`ceterms:description`)", "AVC `Total Course In-Class (Contact) Hours 54.0 - 432.0` → "
     "`{\"ceterms:description\": \"Total Course In-Class (Contact) Hours\", \"ceterms:timeRequired\": \"54.0 - "
     "432.0\"}`"],
    ["`absent_if`", "the rule's claim \"not on the page\": `{\"within\": <selector, from the record>, \"missing\": "
     "<selector or label>}`. When the rule finds no value, the `within` container is there and the property's "
     "element or label isn't in it, the course reads *Not on the page (rule's claim)* instead of *Nothing found*. "
     "**Claim it only after seeing pages where the property is truly missing** from a container that always holds "
     "it when present", "Marshall `{\"within\": \".courseblock\", \"missing\": \"Prerequisite\"}`: a course block "
     "with no Prerequisite line"],
]
REQUISITE_WORDS = [
    "- `PR` means prerequisite. `Consent` is a prerequisite's text (WVU MUSC 720S: the prerequisite is `Consent`; the "
    "courses named in the course description aren't requisites).",
    "- `CONC`, \"concurrent\" and `Co-req` mean corequisite.",
    "- **A condition's text goes whole into its `→ description`**, course codes and all (`MATH 124 and 125`, "
    "`BIOL 219 with a minimum grade of C-`). The parent (`ceterms:prerequisite`, …) and its targets get no rule for "
    "now (`none`): they're parsed out of the description later.",
    "- **Prerequisite** is text labelled Prerequisite, `Pre-req`, `PR` and the like. **Corequisite** is text labelled "
    "Corequisite, concurrent, concurrent enrollment, `CR` and the like.",
    "- **\"Before or at the same time\" is Co-Prerequisite: Description**: `Prerequisite or Corequisite:`, `Pre- or "
    "Corequisite:`, \"PR or CONC\", `Concurrent PR:`, \"Completion of or concurrent enrollment in\" and \"(may be "
    "taken concurrently)\".",
    "- **Prerequisite: Description keeps the full sentence**, even when part of it is also the Co-Prerequisite's text "
    "(AVC ATH103L `Completion of ATH 100 and completion of or concurrent enrollment in ATH 103.` → Prerequisite the "
    "whole sentence, Co-Prerequisite `completion of or concurrent enrollment in ATH 103.`). Conditions stay flat text: "
    "no list of objects.",
    "- **A corequisite inside the prerequisite sentence is left out of it** and goes to Corequisite: Description "
    "(WVU `PR: Corequisite of AGBI 514L` → Corequisite: Description `Corequisite of AGBI 514L`).",
    "- \"Advisory\", \"Recommended Prep\" and \"Recommended\" go to Recommends: Description.",
    "- **Credits are a Value Profile: Credit Value itself gets no rule (`none`).** One number is **Credit Unit Value** "
    "(Marshall `7 Credit hours` → `7`). A range is **Credit Unit Min Value** and **Max Value** (`1-4 Credit hours` → "
    "`1`, `4`), with Value left empty. The words are **Credit Unit Type** (`Credit hours`). Each reads the page (the "
    "credits element), not Credit Value.",
    "- **Any other requirement to enroll or take part is Entry Condition: Description** (AVC `LIMITATION ON "
    "ENROLLMENT: To participate in work experience education, students must …`).",
    "- Contact hours are **Estimated Duration, one rule whose value is a list of objects** (`profile`): one object per "
    "kind of hours (in-class, out-of-class, lecture, lab), with fields `ceterms:description` (the kind's words, `Total "
    "Course In-Class (Contact) Hours`) and `ceterms:timeRequired` (its hours as printed, `54.0 - 432.0`), key "
    "`ceterms:description`. It has no child rules: exact, minimum and maximum duration are parsed from timeRequired "
    "at transformation. Lecture / lab hours are also a Learning Method Type each.",
    "- **Keep whole text blocks**: a value is the page's words as one block (a description with its paragraphs, a "
    "range `54.0 - 432.0`); don't split or parse at extraction.",
    "- Extract the page's words, as close as possible: no vocabulary mapping (`Units`, not `AcademicUnit`) and no "
    "numbers from words (`Three`, not 3). That's transformation, later.",
]
#: Every rule type, the requisite words, and where a text with no clear property goes.
RULE_TYPE_LINES = (
    ["", "## Every rule type and input", ""] + table(["Type / input", "Reads", "Real example"], RULE_TYPES)
    + ["", "## Requisite words", ""] + REQUISITE_WORDS
    + ["", "## When it isn't clear which property a text belongs to", "",
       "**Put it in the course's description** (with `join` if it's a separate section). Never drop page text: "
       "transformation, or a later round of extraction, moves it. Better in the description than lost.", ""])
FIRST_LIMITS = [
    "## Limits",
    "- You edit a draft file only. Never write to the storage root or the saved pages.",
    "- `golden-datasets` assigns versions and hashes: don't add `version` or `content_hash` to a draft.",
    "- One rule per property of the table, with its rule id. A property the pages don't print keeps "
    "`\"rule_type\": \"none\"`: **never invent a value** a page doesn't print.",
    "- Rules stay declarative (the formats above). If the pages can't be read with them, stop and say so.",
    "- If the crawl has no course pages at all (only program or index pages), don't invent rules: say so; "
    "the catalog needs a new crawl.",
    "- Notes for the experts: whenever a value is ambiguous (\"PR or CONC\"), say so in the rule's `why`; the "
    "Rules tab shows it.", "",
]
FIRST_ORDER = ("Order: page rule → record locator → required properties → parents → children (`input: rule`, the "
               "parent) → the rest. Run `rule try` after each group.")
LOOK_STEPS = [
    ["1. Look", "`golden-datasets sql \"SELECT url, title FROM pages WHERE url LIKE '%cour%' LIMIT 50\"`",
     "the saved pages (`pages` has `page_stem`, `url`, `title`); find the pages that hold courses"],
    ["", "`golden-datasets pages get <page_stem>`",
     "a saved page's local path: read its HTML for the content root, each course's block and its properties"],
]

# A catalog platform's name in its pages' markup or URLs → a Studio catalog already on it, whose rules make the best
# template.
PLATFORM_HINTS = [(r"elumen", "eLumen", "avc"), (r"curr?[iq]+[cq]?unet", "CurricUNET", "ccsf"),
                  (r"courseleaf", "CourseLeaf", "marshall"), (r"acalog|preview_course(_nopop)?\.php", "Acalog", "ualr")]
_HTML = re.compile(r"<\s*(html|body|div|span|script|style|head)\b", re.I)
