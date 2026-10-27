"""The prompt for Claude Code (spec §7.5, screen 09): the same text from the UI's **Copy prompt** button and from
`golden-datasets prompt`.

Deterministic: the same annotations always give the same text (everything is sorted; no "now"). It holds the task
and its limits, the catalog / crawl / ruleset / storage root, each in-scope rule's definition and what / how / why,
every open annotation, the values marked correct (which must not change), the questions for the institution
(listed apart, not bugs), the `golden-datasets` commands for more context, and the publish rule. No raw HTML: pages
are referenced by path, resolved against `$GOLDEN_DATASETS_ROOT`.
"""

from __future__ import annotations

import json
import re
import sys

from . import model
from .catalogs import info
from .context import Ctx
from .loop import current_review, ordered_rule_ids, page_ref, rule_annotations, rule_or_error, short
from .review import Review, norm

INTRO = ("You are improving the declarative extraction rules of **CTDL Golden Rules Studio** for one catalog. "
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
    "field": "- Field rule format: `definition` has `locator`, `rule_type` (css / css+regex / regex / constant / "
             "source_url), `selector` (CSS, evaluated inside one course occurrence), optional `regex` + `group`, "
             "`transforms` (strip, collapse_ws, upper, lower, remove_spaces, rstrip:<chars>), optional `map`. Order: "
             "the element's raw text (a `<br>` reads as a newline; HTML indentation is still there) → `regex` (Python, "
             "MULTILINE) → `group` → `transforms` → `map`.",
}
KIND_NAME = {"page": "page rule", "locator": "record locator", "field": "field rule"}
IN_SCOPE = ", ".join(label for label, _ in model.PROPERTIES)


def scope_rules(rv: Review, rule: str | None, needs_work: bool) -> list[str]:
    if rule and not needs_work:
        rule_or_error(rv, rule)
        return [rule]
    return [rid for rid in ordered_rule_ids(rv.snap.rules) if rv.rule_status(rid)["status"] == "needs work"]


def _location(a: dict) -> str:
    exp = a["expected"] or {}
    if not exp.get("css_path") or exp.get("char_start") is None:
        return ""
    if exp["css_path"] == a["current_css_path"]:
        where = "of the extracted element"
    elif a["occurrence_css_path"] and exp["css_path"].startswith(a["occurrence_css_path"] + " > "):
        where = f"of `<occurrence> > {exp['css_path'][len(a['occurrence_css_path']) + 3:]}`"
    else:
        where = f"of `…{' > '.join(exp['css_path'].split(' > ')[-2:])}`"
    return f" (chars {exp['char_start']}–{exp['char_end']} {where})"


def _annotation_lines(ctx: Ctx, rule: dict, a: dict, n: int, refs: set) -> list[str]:
    head = a["course_key"] or a["page_title"] or a["page_stem"]
    label = {"still-wrong": "STILL WRONG", "missing": "MISSING"}.get(a["state"], (a["verdict"] or "").upper())
    out = [f"{n}. **{label}** — {head}"]
    if a["page_stem"]:
        refs.add(a["page_stem"])
        out.append(f"   - page: `{page_ref(ctx, a['page_stem'])}`")
    if a["url"]:
        out.append(f"   - url: {a['url']}")
    if rule["kind"] == "field":
        out.append(f"   - extracted (v{a['rule_version_seen']}): \"{short(a['value_seen'], 220)}\"")
        if a["expected"] and a["expected"].get("text") is not None:
            out.append(f"   - expected: \"{short(a['expected']['text'], 220)}\"{_location(a)}")
        if a["rule_version_seen"] != rule["version"] and a["has_row"]:
            now = "unchanged" if norm(a["value_seen"]) == norm(a["current_value"]) \
                else f"\"{short(a['current_value'], 160)}\""
            out.append(f"   - current (v{rule['version']}): {now}")
    elif a["verdict"] == "missing":
        exp = a["expected"] or {}
        if exp.get("text"):
            out.append(f"   - not found by the rule: \"{short(exp['text'], 160)}\""
                       + (f" at `{exp['css_path']}`" if exp.get("css_path") else ""))
        else:
            out.append("   - the expert says this rule should find this page (or a course on it), and it doesn't")
    else:
        what = "recognises this page" if rule["kind"] == "page" else "finds this course block"
        seen = f" (it was shown as \"{short(a['value_seen'], 80)}\")" if a["value_seen"] else ""
        out.append(f"   - the expert marked it wrong that the rule {what}{seen}")
    if a["note"]:
        out.append(f"   - note ({a['author']}): \"{short(a['note'], 400)}\"")
    else:
        out.append(f"   - by {a['author']}")
    for c in a["comments"]:
        out.append(f"   - comment ({c['author']}): \"{short(c['note'], 400)}\"")
    return out


def _signal_lines(rv: Review, rid: str) -> list[str]:
    snap = rv.snap
    examples: dict[str, list[tuple[str, str]]] = {}
    for row in snap.rows(rid):
        for s in row["signals"]:
            examples.setdefault(s["signal"], []).append((row["course_key"] or row["page_stem"], s["detail"] or ""))
    counts = snap.signal_counts.get(rid, {})
    out = []
    for name, total in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        ex = sorted(set(examples.get(name, [])))[:3]
        tail = (" — e.g. " + "; ".join(f"{who}: {short(d, 90)}" for who, d in ex)) if ex else ""
        out.append(f"- `{name}` × {total:,}{tail}")
    return out


def build_prompt(ctx: Ctx, rule: str | None = None, needs_work: bool = False, rv: Review | None = None) -> dict:
    """{text, chars, tokens, page_refs, rules, annotations, scope} (web/src/api/types.ts `PromptResponse`)."""
    rv = rv or current_review(ctx)
    needs_work = needs_work or not rule
    targets = scope_rules(rv, rule, needs_work)
    snap = rv.snap
    meta = info(ctx.catalog)
    short_name = meta["short"]
    refs: set[str] = set()
    n_open = 0
    L: list[str] = []
    if len(targets) == 1:
        L.append(f"# Improve rule `{targets[0]}` — {meta['name']} catalog")
    elif targets:
        L.append(f"# Improve {len(targets)} rules that need work — {meta['name']} catalog")
    else:
        L.append(f"# No rule needs work — {meta['name']} catalog")
    L += ["", INTRO, ""]

    L.append("## Context")
    platform = f", {meta['platform']} platform" if meta.get("platform") else ""
    L.append(f"- Catalog: `{ctx.catalog}` ({meta['name']}{platform})")
    L.append(f"- Crawl: `{ctx.crawl}` — {len(snap.page):,} saved pages")
    L.append(f"- Current ruleset: v{snap.ruleset_version} (extraction `{snap.ext}`)")
    L.append("- Storage root: `$GOLDEN_DATASETS_ROOT` (the Studio's root; `golden-datasets` reads it, caches pages "
             "locally). Before any command:")
    L.append("")
    L.append("  ```sh")
    L.append(f"  export GOLDEN_DATASETS_ROOT='{ctx.root.uri}'")
    L.append(f"  export GOLDEN_DATASETS_CATALOG={short_name}")
    L.append("  ```")
    L.append("")
    L.append(f"- Page files: `$GOLDEN_DATASETS_ROOT/{ctx.catalog}/{ctx.crawl}/pages/<page_stem>.html` (full saved "
             "page, scripts already ran at crawl time). `golden-datasets pages get <page_stem>` makes one available "
             "locally and prints its path.")
    for kind in ("page", "locator", "field"):
        if any(snap.rules[t]["kind"] == kind for t in targets):
            L.append(FORMAT[kind])
    L.append("")

    L.append("## Limits")
    L.append("- You edit a draft file only (`golden-datasets rule draft …`). Never write to the storage root, the "
             "annotation log or the saved pages.")
    L.append("- `golden-datasets` assigns versions and hashes: don't add `version` or `content_hash` to a draft.")
    if targets:
        L.append(f"- Change only the rule(s) in this prompt: {', '.join(f'`{t}`' for t in targets)}. Leave every "
                 "other rule as it is.")
    L.append(f"- Only the in-scope Course properties count: {IN_SCOPE}. Requisites, credit units and other "
             "properties are out of scope: don't add rules for them.")
    L.append("- Rules stay declarative (the formats above). If the format can't express the fix, stop and say so.")
    L.append("- Publish only when nothing marked correct changes: `rule try` must say BETTER (fixed > 0, newly wrong "
             "= 0). Never use `--force`.")
    L.append("")

    questions: dict[str, tuple[str, dict]] = {}
    for rid in targets:
        r = snap.rules[rid]
        st = rv.rule_status(rid)
        fill = snap.fill(rid)
        prop = f", {r['property_label']} (`{r.get('ctdl_property') or 'no CTDL term'}`)" if r.get("property_label") else ""
        L.append(f"## Rule `{rid}` v{r['version']} — {KIND_NAME[r['kind']]}{prop} — status: **{st['status']}**")
        L.append("")
        L.append(f"- **what:** {r.get('what') or '(empty)'}")
        L.append(f"- **how:** {r.get('how') or '(empty)'}")
        L.append(f"- **why:** {r.get('why') or '(empty: imported from v2)'}")
        L.append(f"- depends on: {', '.join(f'`{d}`' for d in r.get('depends_on') or []) or '—'}")
        L.append(f"- rows: {fill['rows']:,}, with a value: {fill['found']:,}; reviewed {st['reviewed']:,}")
        L.append("")
        L.append("```json")
        L.append(json.dumps(r["definition"], indent=2, ensure_ascii=False))
        L.append("```")
        if r.get("examples"):
            L.append("")
            L.append("Examples (`golden-datasets rule try` checks each: the definition applied to `input` must give "
                     "`output`):")
            L.append("```json")
            L.append(json.dumps(r["examples"], indent=2, ensure_ascii=False))
            L.append("```")
        L.append("")
        anns = rule_annotations(rv, rid)
        open_ = [a for a in anns if a["open"]]
        correct = [a for a in anns if a["state"] == "correct"]
        changed = [a for a in anns if a["state"] == "changed-since-correct"]
        for a in anns:
            if a["verdict"] == "question":
                questions.setdefault(a["annotation_id"], (rid, a))
        L.append(f"### Open annotations ({len(open_)})")
        L.append("")
        if not open_:
            L.append("None: every wrong / missing verdict on this rule is fixed.")
        for i, a in enumerate(open_, 1):
            L += _annotation_lines(ctx, r, a, i, refs)
        n_open += len(open_)
        if correct:
            L.append("")
            L.append(f"**Marked correct — these values must not change ({len(correct)}):** "
                     + ", ".join(a["course_key"] or a["page_title"] or a["page_stem"] for a in correct))
            if r["kind"] == "field":
                for a in correct:
                    L.append(f"   - {a['course_key'] or a['page_stem']}: \"{short(a['current_value'], 120)}\"")
        if changed:
            L.append("")
            L.append(f"**Marked correct, but the value changed since ({len(changed)}); the expert will look again:** "
                     + ", ".join(a["course_key"] or a["page_stem"] for a in changed))
        sig = _signal_lines(rv, rid)
        if sig:
            L.append("")
            L.append(f"### Signals on this rule in `{snap.ext}`")
            L += sig
            L.append(f"- pages behind a signal: `golden-datasets pages sample --rule {rid} --signal <signal> -n 20`")
        L.append("")

    if questions:
        L.append("## Questions for the institution (not bugs)")
        L.append("")
        L.append("Only the college can answer these. Don't change a rule for them, but mention them in your report.")
        L.append("")
        for _, (_rid, a) in sorted(questions.items(), key=lambda kv: (kv[1][1]["page_stem"] or "", kv[0])):
            head = a["course_key"] or a["page_title"] or a["page_stem"]
            if a["page_stem"]:
                refs.add(a["page_stem"])
            said = f"\"{short(a['note'], 400)}\"" if a["note"] else "(flagged, no note)"
            L.append(f"- {head} — page `{page_ref(ctx, a['page_stem'])}` ({a['author']}): {said}")
        L.append("")

    names = " ".join(targets) or "<rule_id>"
    draft = f"drafts/{targets[0]}.json" if len(targets) == 1 else "drafts/needs-work.json"
    L.append("## How to work")
    L.append("")
    L.append(f"1. `golden-datasets rule show {targets[0] if targets else '<rule_id>'}` — current definition, "
             "what/how/why, examples, versions, status, fill and signal counts (one rule per call). "
             "`golden-datasets rule list` — every rule.")
    L.append("2. `golden-datasets rule annotations <rule_id> --open` — every open annotation above, with full css "
             "paths, character offsets (DOM textContent) and page paths. Without `--open`: every annotation, "
             "including the values marked correct.")
    L.append("3. `golden-datasets pages get <page_stem>` — makes a saved page available locally and prints "
             "`<path><TAB><url>` per page (a unique part of the stem works, e.g. `course-geog222`). Read the file you need, searching for the "
             "expected text. `golden-datasets pages sample --rule <rule_id> [--signal <signal>] -n 20` — more pages "
             "where the rule fires. `golden-datasets sql \"SELECT …\"` — DuckDB over the views `pages`, "
             "`occurrences`, `matches`, `signals`, `annotations`, `rules` (`--format json` prints one object per line). "
             "This prompt deliberately contains no raw HTML.")
    L.append(f"4. `golden-datasets rule draft {names} > {draft}` — the current version(s) as an editable draft. "
             "Change only `definition`, `what`, `how`, `why` and `examples` (update an example your fix makes wrong). *What* says what the rule finds, in "
             "page terms; *how* says how; *why* says why this version is better than the last.")
    L.append(f"5. `golden-datasets rule try {draft}` — reruns the draft over the whole crawl (writes nothing) and "
             "prints a scorecard per rule: fixed / still wrong / newly wrong (values marked correct that changed), "
             "values changed, and signal counts before → after. Iterate until every open annotation is fixed and "
             "nothing marked correct changed.")
    L.append("6. Fill `why` from the annotations: cite the course codes and the expert's notes. Add one example per "
             "fix (`examples`: `{\"input\": <the selected text>, \"output\": <the value>}`).")
    L.append(f"7. `golden-datasets rule publish {draft} --note \"…\"` — writes the new rule version(s), a new ruleset "
             "version and its extraction (unchanged rules are copied). It refuses when a value marked correct "
             "changes. Do not commit or push anything.")
    L.append("")
    L.append("Report back: what changed and why, the final scorecard, and anything you could not fix.")
    text = "\n".join(L) + "\n"
    return {"scope": {"rule": rule if not needs_work else None, "needs_work": needs_work},
            "text": text, "chars": len(text), "tokens": round(len(text) / 4), "page_refs": len(refs),
            "rules": targets, "annotations": n_open}


_HTML = re.compile(r"<\s*(html|body|div|span|script|style|head)\b", re.I)


def has_raw_html(text: str) -> bool:
    return bool(_HTML.search(text))


def cmd_prompt(args) -> int:
    ctx = Ctx.from_args(args)
    if args.rule is None and not args.needs_work:
        args.needs_work = True
    out = build_prompt(ctx, args.rule, args.needs_work)
    if has_raw_html(out["text"]):
        print("golden-datasets: warning: an annotation quotes something that looks like HTML", file=sys.stderr)
    print(out["text"], end="")
    return 0
