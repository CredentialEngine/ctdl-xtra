"""The prompt for Claude Code (spec §7.5, screen 09): the same text from the UI's **Copy prompt** button and from
`golden-datasets prompt`.

Deterministic: the same annotations always give the same text (everything is sorted; no "now"). It holds the task,
the setup (install the CLI from this branch with uv, point it at the root; for `target="azure"`, the Azure root after
`az login`), the limits, each in-scope rule's definition and what / how / why, its open annotations, the values marked
correct (which must not change) and its signals as tables, the questions for the institution (listed apart, not
bugs), the `golden-datasets` commands that fetch all of this and more, and the publish rule. No raw HTML: pages are
referenced by stem, fetched with `golden-datasets pages get`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from . import model
from .catalogs import info
from .cli import DEFAULT_AZURE_ROOT, ENV_FILE
from .context import Ctx
from .loop import current_review, ordered_rule_ids, rule_annotations, rule_or_error, short
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
REPO = "https://github.com/CredentialEngine/ctdl-xtra.git"
SUBDIR = "golden-dataset-studio"
TARGETS = ("local", "azure")


def _git(*args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(Path(__file__).resolve().parent), *args],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def cli_source() -> dict:
    """Where Claude installs `golden-datasets` from: this checkout's branch on GitHub ($GOLDEN_DATASETS_GIT_REF wins;
    `main` outside a checkout). `warning` says when the branch has commits GitHub doesn't."""
    ref = os.environ.get("GOLDEN_DATASETS_GIT_REF") or _git("rev-parse", "--abbrev-ref", "HEAD")
    warning = None
    if not ref or ref == "HEAD":
        ref = "main"
    elif not os.environ.get("GOLDEN_DATASETS_GIT_REF") and _git("rev-parse", "--git-dir"):
        ahead = _git("rev-list", "--count", "@{u}..HEAD")
        if ahead is None:
            warning = f"Branch {ref} isn't on GitHub: push it, or the install step fails."
        elif ahead != "0":
            warning = f"Branch {ref} has {ahead} commit(s) not pushed to GitHub: Claude's CLI won't have them."
    return {"ref": ref, "spec": f"git+{REPO}@{ref}#subdirectory={SUBDIR}", "warning": warning}


def cell(v) -> str:
    """Text safe inside a Markdown table cell: one line, no bare `|`."""
    return str(v).replace("\n", "⏎ ").replace("|", "\\|")


def table(header: list[str], rows: list[list]) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + \
           ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]


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


def _who(a: dict) -> str:
    return a["course_key"] or a["page_title"] or a["page_stem"] or "—"


def _notes(a: dict) -> str:
    said = [f"{a['author']}: \"{short(a['note'], 300)}\"" if a["note"] else f"by {a['author']}"]
    said += [f"{c['author']}: \"{short(c['note'], 300)}\"" for c in a["comments"]]
    return "; ".join(said)


def _annotation_row(rule: dict, a: dict, n: int, refs: set) -> list:
    label = {"still-wrong": "STILL WRONG", "missing": "MISSING"}.get(a["state"], (a["verdict"] or "").upper())
    if a["page_stem"]:
        refs.add(a["page_stem"])
    page = f"`{a['page_stem']}`" if a["page_stem"] else "—"
    if rule["kind"] == "field":
        seen = f"v{a['rule_version_seen']}: \"{short(a['value_seen'], 200)}\""
        if a["rule_version_seen"] != rule["version"] and a["has_row"]:
            seen += " → now unchanged" if norm(a["value_seen"]) == norm(a["current_value"]) \
                else f" → now (v{rule['version']}): \"{short(a['current_value'], 140)}\""
        exp = a["expected"] or {}
        expected = f"\"{short(exp['text'], 200)}\"{_location(a)}" if exp.get("text") is not None else "—"
        if a["verdict"] == "missing" and not exp.get("text"):
            expected = "a value: the rule finds nothing here"
        return [n, f"**{label}**", _who(a), page, seen, expected, _notes(a)]
    if a["verdict"] == "missing":
        exp = a["expected"] or {}
        problem = (f"not found: \"{short(exp['text'], 160)}\"" + (f" at `{exp['css_path']}`" if exp.get("css_path") else "")
                   if exp.get("text") else "the rule should find this page (or a course on it) and doesn't")
    else:
        what = "recognises this page" if rule["kind"] == "page" else "finds this course block"
        problem = f"wrong that the rule {what}" + (f" (shown as \"{short(a['value_seen'], 80)}\")" if a["value_seen"] else "")
    return [n, f"**{label}**", _who(a), page, problem, _notes(a)]


def _signal_rows(rv: Review, rid: str) -> list[list]:
    snap = rv.snap
    examples: dict[str, list[tuple[str, str]]] = {}
    for row in snap.rows(rid):
        for s in row["signals"]:
            examples.setdefault(s["signal"], []).append((row["course_key"] or row["page_stem"], s["detail"] or ""))
    counts = snap.signal_counts.get(rid, {})
    out = []
    for name, total in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        ex = sorted(set(examples.get(name, [])))[:3]
        out.append([f"`{name}`", f"{total:,}", "; ".join(f"{who}: {short(d, 90)}" for who, d in ex) or "—"])
    return out


def _setup(ctx: Ctx, target: str, root_uri: str, first_rule: str) -> list[str]:
    src = cli_source()
    azure = root_uri.startswith("azure://")  # the root decides: a Studio that serves Azure gives Azure either way
    short_name = info(ctx.catalog)["short"]
    L = ["## Setup", "",
         f"Do this once, in the folder you work in. Your shell commands don't share `export`s, so `golden-datasets` "
         f"reads its root and catalog from `{ENV_FILE}` in the current folder (or a parent).", ""]
    L.append(f"1. Install the CLI from the `{src['ref']}` branch (needs uv; if `uv` is missing: "
             "`curl -LsSf https://astral.sh/uv/install.sh | sh`):")
    L += ["", "   ```sh", f"   uv tool install --reinstall '{src['spec']}'", "   golden-datasets --help", "   ```", "",
          f"   Without installing: `uvx --from '{src['spec']}' golden-datasets …`."]
    n = 2
    if azure:
        account = re.sub(r"^azure://https?://([^./]+).*", r"\1", root_uri)
        L.append(f"{n}. Sign in to Azure. `az account show` says whether you are; if not, `az login` (no browser here: "
                 "`az login --use-device-code`, and give the person the code). The CLI reads the storage key through "
                 f"`az` itself, so nothing secret goes in a file or an `export`: you only need an Azure account that "
                 f"can read the keys of the `{account}` storage account. If `az` is missing: "
                 "`brew install azure-cli`, or https://aka.ms/InstallAzureCLI.")
        n += 1
    L.append(f"{n}. Point the CLI at the {'shared Azure' if azure else 'Studio'} root and check it:")
    L += ["", "   ```sh", f"   cat > {ENV_FILE} <<'EOF'", f"   GOLDEN_DATASETS_ROOT={root_uri}",
          f"   GOLDEN_DATASETS_CATALOG={short_name}", "   EOF", f"   golden-datasets rule show {first_rule}", "   ```", ""]
    if azure:
        L.append("   Pages download once into a local cache (`~/.cache/golden-datasets`); `rule publish` uploads the "
                 "new versions, and the Studio shows them when it serves this root.")
    else:
        L.append("   This root is a folder on the machine that runs the Studio: run Claude Code on that machine. "
                 "`rule publish` writes there, and the Studio shows the new version right away.")
    L.append("")
    return L


def build_prompt(ctx: Ctx, rule: str | None = None, needs_work: bool = False, rv: Review | None = None,
                 target: str = "local", azure_root: str | None = None) -> dict:
    """{text, chars, tokens, page_refs, rules, annotations, scope, target, root, warning}
    (web/src/api/types.ts `PromptResponse`). `target`: Claude works on this root ("local") or the Azure one."""
    if target not in TARGETS:
        raise ValueError(f"target must be one of {TARGETS}")
    rv = rv or current_review(ctx)
    needs_work = needs_work or not rule
    targets = scope_rules(rv, rule, needs_work)
    snap = rv.snap
    meta = info(ctx.catalog)
    root_uri = ctx.root.uri if target == "local" or ctx.root.uri.startswith("azure://") \
        else (azure_root or DEFAULT_AZURE_ROOT)
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
    L += _setup(ctx, target, root_uri, targets[0] if targets else "<rule_id>")

    L.append("## Context")
    L.append("")
    platform = f", {meta['platform']} platform" if meta.get("platform") else ""
    L += table(["", ""], [
        ["Catalog", f"`{ctx.catalog}` ({meta['name']}{platform})"],
        ["Crawl", f"`{ctx.crawl}`, {len(snap.page):,} saved pages (scripts already ran at crawl time)"],
        ["Ruleset", f"v{snap.ruleset_version} (extraction `{snap.ext}`)"],
        ["Storage root", f"`{root_uri}`"],
        ["A saved page", "`golden-datasets pages get <page_stem>` prints its local path and live URL"],
    ])
    L.append("")
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

    if len(targets) > 1:
        L.append(f"## The {len(targets)} rules")
        L.append("")
        rows = []
        for rid in targets:
            r = snap.rules[rid]
            n = sum(1 for a in rule_annotations(rv, rid) if a["open"])
            rows.append([f"`{rid}`", f"v{r['version']}", KIND_NAME[r["kind"]], r.get("property_label") or "—", n])
        L += table(["Rule", "Version", "Kind", "Property", "Open annotations"], rows)
        L.append("")

    questions: dict[str, tuple[str, dict]] = {}
    for rid in targets:
        r = snap.rules[rid]
        st = rv.rule_status(rid)
        fill = snap.fill(rid)
        prop = f", {r['property_label']} (`{r.get('ctdl_property') or 'no CTDL term'}`)" if r.get("property_label") else ""
        L.append(f"## Rule `{rid}` v{r['version']} — {KIND_NAME[r['kind']]}{prop} — status: **{st['status']}**")
        L.append("")
        L += table(["", ""], [
            ["**What**", r.get("what") or "(empty)"],
            ["**How**", r.get("how") or "(empty)"],
            ["**Why**", r.get("why") or "(empty: imported from v2)"],
            ["Depends on", ", ".join(f"`{d}`" for d in r.get("depends_on") or []) or "—"],
            ["Rows", f"{fill['rows']:,}, {fill['found']:,} with a value; {st['reviewed']:,} reviewed"],
        ])
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
        else:
            head = ["#", "Verdict", "Course", "Page", "Extracted", "Expected", "Notes"] if r["kind"] == "field" \
                else ["#", "Verdict", "Course / page", "Page", "Problem", "Notes"]
            L += table(head, [_annotation_row(r, a, i, refs) for i, a in enumerate(open_, 1)])
            L.append("")
            L.append(f"Full css paths, character offsets (DOM textContent) and page paths: "
                     f"`golden-datasets rule annotations {rid} --open`.")
        n_open += len(open_)
        if correct:
            L.append("")
            L.append(f"### Marked correct: must not change ({len(correct)})")
            L.append("")
            if r["kind"] == "field":
                L += table(["Course", "Current value"],
                           [[_who(a), f"\"{short(a['current_value'], 120)}\""] for a in correct])
            else:
                L.append(", ".join(_who(a) for a in correct))
            L.append("")
            L.append(f"Every annotation, these included: `golden-datasets rule annotations {rid}`.")
        if changed:
            L.append("")
            L.append(f"**Marked correct, but the value changed since ({len(changed)}); the expert will look again:** "
                     + ", ".join(a["course_key"] or a["page_stem"] for a in changed))
        sig = _signal_rows(rv, rid)
        if sig:
            L.append("")
            L.append(f"### Signals on this rule in `{snap.ext}`")
            L.append("")
            L += table(["Signal", "Rows", "Examples"], sig)
            L.append("")
            L.append(f"Pages behind a signal: `golden-datasets pages sample --rule {rid} --signal <signal> -n 20`.")
        L.append("")

    if questions:
        L.append("## Questions for the institution (not bugs)")
        L.append("")
        L.append("Only the college can answer these. Don't change a rule for them, but mention them in your report.")
        L.append("")
        rows = []
        for _, (_rid, a) in sorted(questions.items(), key=lambda kv: (kv[1][1]["page_stem"] or "", kv[0])):
            if a["page_stem"]:
                refs.add(a["page_stem"])
            said = f"\"{short(a['note'], 400)}\"" if a["note"] else "(flagged, no note)"
            rows.append([_who(a), f"`{a['page_stem']}`" if a["page_stem"] else "—", a["author"], said])
        L += table(["Course / page", "Page", "From", "Question"], rows)
        L.append("")

    first = targets[0] if targets else "<rule_id>"
    names = " ".join(targets) or "<rule_id>"
    draft = f"drafts/{targets[0]}.json" if len(targets) == 1 else "drafts/needs-work.json"
    L.append("## How to work")
    L.append("")
    L.append("Everything above comes from these commands; run them for more, or when the annotations change.")
    L.append("")
    L += table(["Step", "Command", "What it gives"], [
        ["1. Read", f"`golden-datasets rule show {first}`",
         "definition, what/how/why, examples, versions, status, fill and signal counts (one rule per call); "
         "`golden-datasets rule list`: every rule"],
        ["", f"`golden-datasets rule annotations {first} --open`",
         "every open annotation, with full css paths, character offsets and page paths; without `--open`: every "
         "annotation, including the values marked correct"],
        ["", "`golden-datasets pages get <page_stem>`",
         "makes a saved page available locally and prints `<path><TAB><url>` (a unique part of the stem works, e.g. "
         "`course-geog222`); read it, searching for the expected text"],
        ["", f"`golden-datasets pages sample --rule {first} [--signal <signal>] -n 20`", "more pages where the rule fires"],
        ["", "`golden-datasets sql \"SELECT …\"`",
         "DuckDB over the views `pages`, `occurrences`, `matches`, `signals`, `annotations`, `rules` "
         "(`--format json`: one object per line)"],
        ["2. Draft", f"`golden-datasets rule draft {names} > {draft}`",
         "the current version(s) as an editable draft. Change only `definition`, `what`, `how`, `why` and `examples` "
         "(update an example your fix makes wrong)"],
        ["3. Try", f"`golden-datasets rule try {draft}`",
         "reruns the draft over the whole crawl (writes nothing): per rule fixed / still wrong / newly wrong (values "
         "marked correct that changed), values changed, signal counts before → after. Iterate until every open "
         "annotation is fixed and nothing marked correct changed"],
        ["4. Publish", f"`golden-datasets rule publish {draft} --note \"…\"`",
         "new rule version(s), a new ruleset version and its extraction (unchanged rules are copied); refuses when a "
         "value marked correct changes"],
    ])
    L.append("")
    L.append("Before publishing, fill the draft's text: *what* says what the rule finds, in page terms; *how* says how; "
             "*why* says why this version is better than the last, citing the course codes and the expert's notes. "
             "Add one example per fix (`{\"input\": <the selected text>, \"output\": <the value>}`). Do not commit or "
             "push anything.")
    L.append("")
    L.append("Report back: what changed and why, the final scorecard, and anything you could not fix.")
    text = "\n".join(L) + "\n"
    return {"scope": {"rule": rule if not needs_work else None, "needs_work": needs_work},
            "text": text, "chars": len(text), "tokens": round(len(text) / 4), "page_refs": len(refs),
            "rules": targets, "annotations": n_open, "target": target, "root": root_uri,
            "warning": cli_source()["warning"]}


_HTML = re.compile(r"<\s*(html|body|div|span|script|style|head)\b", re.I)


def has_raw_html(text: str) -> bool:
    return bool(_HTML.search(text))


def cmd_prompt(args) -> int:
    ctx = Ctx.from_args(args)
    if args.rule is None and not args.needs_work:
        args.needs_work = True
    out = build_prompt(ctx, args.rule, args.needs_work, target=args.target, azure_root=args.azure_root)
    if has_raw_html(out["text"]):
        print("golden-datasets: warning: an annotation quotes something that looks like HTML", file=sys.stderr)
    print(out["text"], end="")
    return 0
