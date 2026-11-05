"""A run's report (docs/qrspi/report-links/03-spec.md): Claude writes `report.json` (facts, by id), and this checks it
and writes the Markdown people read, with every link built here from the Studio address the run was started from.

    check(facts, known) -> list of problems (empty = fine)
    render(facts, known, run, last_try) -> Markdown

`Known` is what the ids are checked against: the latest ruleset's rules (with their Studio names), the catalog's
course codes, and each rule's live annotations. Links open the Studio's own screens:

    rule        <studio>#/c/<catalog>/rules/<rule>
    course      …/rules/<rule>?row=<course>&by=anyone
    annotation  …/rules/<rule>?row=<course>&by=anyone&note=<annotation id>
    compare     <studio>#/c/<catalog>/compare?a=<before>&b=<after>
    report      <studio>#/c/<catalog>/rules?run=<run id>
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote, urlencode

ENDINGS = ("published", "needs_you", "failed")
RESULTS = ("published", "not published", "not tried")
TOP_FIELDS = {"ending", "summary", "reason", "to_do", "rules", "notes"}
TODO_FIELDS = {"rule", "course", "notes", "do", "value", "then"}
RULE_FIELDS = {"rule", "asked", "tried", "result", "why"}
MAX_NOTE_LINES = 5
BY_ANYONE = "anyone"  # the Rules tab's reviewer filter; a link shows the row whoever reviewed it


@dataclass
class Known:
    catalog: str                                   # the short name the Studio's addresses use (avc)
    rules: dict[str, str]                          # rule id → Studio name
    courses: set[str]
    notes: dict[str, dict[str, dict]] = field(default_factory=dict)  # rule id → annotation id → {author, course, …}
    ruleset_before: int | None = None
    ruleset_after: int | None = None


def known_from(ctx, rv, run: dict | None) -> Known:
    """Everything the ids are checked against, read from the catalog's latest ruleset and its annotations."""
    from .catalogs import info
    from .loop import rule_annotations
    from .server.routes_review import rule_title

    snap = rv.snap
    rules = {rid: rule_title(r, snap.rules)[0] for rid, r in snap.rules.items()}
    courses = {r["course_key"] for rid, r0 in snap.rules.items() if r0["kind"] == "locator"
               for r in snap.rows(rid) if r.get("course_key")}
    notes: dict[str, dict[str, dict]] = {}
    for rid in snap.rules:
        got: dict[str, dict] = {}
        for a in rule_annotations(rv, rid, page_questions=False):
            got[a["annotation_id"]] = {"author": a["author"], "course": a["course_key"], "kind": a["verdict"] or "comment"}
            for c in a["comments"]:
                if c.get("annotation_id"):
                    got[c["annotation_id"]] = {"author": c["author"], "course": a["course_key"], "kind": "comment"}
        notes[rid] = got
    return Known(catalog=info(ctx.catalog)["short"], rules=rules, courses=courses, notes=notes,
                 ruleset_before=(run or {}).get("ruleset_before"), ruleset_after=snap.ruleset_version)


# =====================================================================================================
# Checks
# =====================================================================================================
def _text(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def check(facts: dict, k: Known) -> list[str]:
    """Every problem with `facts`, one line each (`run done` refuses the report when there is any)."""
    if not isinstance(facts, dict):
        return ["the report must be a JSON object"]
    out: list[str] = []
    for f in sorted(set(facts) - TOP_FIELDS):
        out.append(f"{f}: not a report field (fields: {', '.join(sorted(TOP_FIELDS))})")
    ending = facts.get("ending")
    if ending not in ENDINGS:
        out.append(f"ending: must be one of {', '.join(ENDINGS)}")
    to_do, rules = facts.get("to_do") or [], facts.get("rules") or []
    if not isinstance(to_do, list) or not isinstance(rules, list):
        return out + ["to_do and rules must be lists"]
    if ending == "needs_you" and not to_do:
        out.append("to_do: a needs_you report needs at least one thing for people to do")
    if ending == "failed" and not _text(facts.get("reason")):
        out.append("reason: a failed report says what broke, in one line")
    if ending == "published" and not (k.ruleset_after and (k.ruleset_before is None or k.ruleset_after > k.ruleset_before)):
        out.append(f"ending: published, but the latest ruleset is still v{k.ruleset_after} (the run started on it)")
    notes = facts.get("notes")
    if notes is not None and (not isinstance(notes, str) or len(notes.strip().splitlines()) > MAX_NOTE_LINES):
        out.append(f"notes: text of at most {MAX_NOTE_LINES} lines")

    def ids(where: str, item: dict, fields: set[str], need: str, list_field: str) -> None:
        for f in sorted(set(item) - fields):
            out.append(f"{where}.{f}: not a field here (fields: {', '.join(sorted(fields))})")
        rid = item.get("rule")
        if rid not in k.rules:
            out.append(f"{where}.rule: {rid!r} is not a rule of the latest ruleset")
            return
        course = item.get("course")
        if course is not None and course not in k.courses:
            out.append(f"{where}.course: {course!r} is not a course of this catalog")
        for a in item.get(list_field) or []:
            if a not in k.notes.get(rid, {}):
                out.append(f"{where}.{list_field}: {a} is not an annotation on {rid}")
        if not _text(item.get(need)):
            out.append(f"{where}.{need}: say it in a few words")

    for i, t in enumerate(to_do):
        if not isinstance(t, dict):
            out.append(f"to_do[{i}]: must be an object")
            continue
        ids(f"to_do[{i}]", t, TODO_FIELDS, "do", "notes")
    for i, r in enumerate(rules):
        if not isinstance(r, dict):
            out.append(f"rules[{i}]: must be an object")
            continue
        ids(f"rules[{i}]", r, RULE_FIELDS, "tried", "asked")
        if r.get("result") not in RESULTS:
            out.append(f"rules[{i}].result: must be one of {', '.join(RESULTS)}")
    return out


# =====================================================================================================
# Rendering
# =====================================================================================================
def headline(facts: dict, k: Known) -> str:
    """The run's one-line outcome, shown first everywhere."""
    if facts["ending"] == "published":
        return f"Claude published ruleset v{k.ruleset_after}"
    if facts["ending"] == "needs_you":
        n = len(facts.get("to_do") or [])
        return f"{n} thing{'' if n == 1 else 's'} to fix before Claude can publish"
    return f"Claude couldn't finish: {' '.join(str(facts.get('reason', '')).split())}"


class Links:
    def __init__(self, studio: str | None, k: Known, run_id: str | None):
        self.base = (studio or "").split("#")[0] or None
        self.k = k
        self.run_id = run_id

    def _h(self, path: str, params: dict | None = None) -> str | None:
        if not self.base:
            return None
        q = urlencode({a: b for a, b in (params or {}).items() if b not in (None, "")})
        return f"{self.base}#/c/{quote(self.k.catalog)}/{path}" + (f"?{q}" if q else "")

    def rule(self, rid: str) -> str | None:
        return self._h(f"rules/{quote(rid)}")

    def row(self, rid: str, course: str | None, note: str | None = None) -> str | None:
        if not course:
            return self.rule(rid) if not note else self._h(f"rules/{quote(rid)}", {"by": BY_ANYONE, "note": note})
        return self._h(f"rules/{quote(rid)}", {"row": course, "by": BY_ANYONE, "note": note})

    def compare(self, a: int, b: int) -> str | None:
        return self._h("compare", {"a": a, "b": b})

    def report(self) -> str | None:
        return self._h("rules", {"run": self.run_id}) if self.run_id else None


def _md_escape(s: str) -> str:
    return s.replace("[", "\\[").replace("]", "\\]")


def link(label: str, url: str | None) -> str:
    return f"[{_md_escape(label)}]({url})" if url else label


def cell(s: str) -> str:
    """Text safe inside a Markdown table cell: one line, no bare `|`."""
    return " ".join(s.split()).replace("|", "\\|")


TOKEN = re.compile(r"`?\b([A-Za-z][A-Za-z0-9-]*[A-Za-z0-9](?:@[a-z0-9-]+)?)\b`?")


def linkify(text: str, k: Known, L: Links, rule: str | None) -> str:
    """Course codes and rule ids in Claude's text, linked: a course to its row in `rule` (or `ACCT199@<rule>`), a
    rule id to the rule under its Studio name. Words that are neither stay as written."""
    def sub(m: re.Match) -> str:
        word = m.group(1)
        code, _, other = word.partition("@")
        if other and other in k.rules and code in k.courses:
            return link(f"{code} ({k.rules[other]})", L.row(other, code))
        if word in k.rules:
            return link(k.rules[word], L.rule(word))
        if word in k.courses:
            return link(word, L.row(rule, word) if rule else None)
        return m.group(0)
    return TOKEN.sub(sub, text)


def _note_links(rid: str, ids: list[str], course: str | None, k: Known, L: Links) -> str:
    meta = k.notes.get(rid, {})
    seen: dict[str, int] = {}
    parts = []
    for a in ids:
        m = meta.get(a, {})
        who = (m.get("author") or "a reviewer").split()[0] if m.get("author") else "a reviewer"  # first name
        seen[who] = seen.get(who, 0) + 1
        label = f"{who}'s {'comment' if m.get('kind') == 'comment' else 'note'}"
        if sum(1 for x in ids if ((meta.get(x, {}).get("author") or "a reviewer").split() or ["a"])[0] == who) > 1:
            label += f" {seen[who]}"
        parts.append(link(label, L.row(rid, course or m.get("course"), a)))
    return ", ".join(parts)


def _try_section(last_try: dict | None, k: Known, L: Links) -> list[str]:
    if not last_try:
        return []
    t = last_try["totals"]
    published = last_try.get("published")
    head = "What publishing changed" if published else "Claude's last try (not published)"
    would = "were marked correct and changed" if published else "were marked correct and would change"
    lines = [f"## {head}", "",
             f"{t['fixed']} now right · {t['still_wrong']} still wrong · {t['newly_wrong']} {would} · "
             f"{t['unchanged']} unchanged", ""]
    for c in last_try.get("cards", []):
        rid = c["rule_id"]
        name = link(k.rules.get(rid, rid), L.rule(rid)) if rid in k.rules else rid
        bits = []
        for what, label in (("still_wrong", "still wrong"), ("newly_wrong", would), ("fixed", "now right")):
            courses = c.get(what) or []
            if courses:
                bits.append(f"{label}: " + ", ".join(link(x, L.row(rid, x)) if rid in k.rules else x for x in courses))
        if bits:
            lines.append(f"- {name}: " + "; ".join(bits))
    return lines + ([""] if lines[-1] != "" else [])


def render(facts: dict, k: Known, run: dict | None, last_try: dict | None = None) -> str:
    """The report people read (Markdown), always in the same order; empty sections are left out."""
    run = run or {}
    L = Links(run.get("studio_url"), k, run.get("run_id"))
    before, after = k.ruleset_before, k.ruleset_after
    if facts["ending"] == "published" and before:
        rs = f"ruleset v{before} → v{after} · {link('Compare', L.compare(before, after))}"
    else:
        rs = f"ruleset v{after} unchanged"
    out = [f"**{headline(facts, k)}** · {k.catalog.upper()} · {rs}", ""]
    if _text(facts.get("summary")):
        out += [linkify(facts["summary"].strip(), k, L, None), ""]
    to_do = facts.get("to_do") or []
    if to_do:
        out += ["## What you need to do", ""]
        for i, t in enumerate(to_do, 1):
            rid, course = t["rule"], t.get("course")
            where = link(k.rules[rid], L.rule(rid)) + (f" · {link(course, L.row(rid, course))}" if course else "")
            line = f"{i}. **{where}**: {linkify(t['do'].strip(), k, L, rid)}"
            if t.get("notes"):
                line += f" ({_note_links(rid, t['notes'], course, k, L)})"
            out.append(line)
            if _text(t.get("then")):
                out.append(f"   - *Then:* {linkify(t['then'].strip(), k, L, rid)}")
            if _text(t.get("value")):  # the value to save: its own line, or a block (last: a blank line ends the item)
                v = t["value"].strip()
                out += ([f"   - *Value to save:* `{v}`"] if "\n" not in v and "`" not in v
                        else ["   - *Value to save:*", "", "     ```", *[f"     {x}" for x in v.splitlines()], "     ```", ""])
        out.append("")
    rules = facts.get("rules") or []
    if rules:
        out += ["## Rule by rule", "", "| Rule | Asked | Claude tried | Result |", "|---|---|---|---|"]
        for r in rules:
            rid = r["rule"]
            result = r["result"].capitalize() + (f": {linkify(r['why'].strip(), k, L, rid)}" if _text(r.get("why")) else "")
            out.append("| " + " | ".join(cell(x) for x in (
                link(k.rules[rid], L.rule(rid)), _note_links(rid, r.get("asked") or [], None, k, L) or "—",
                linkify(r["tried"].strip(), k, L, rid), result)) + " |")
        out.append("")
    out += _try_section(last_try, k, L)
    if _text(facts.get("notes")):
        out += ["## Notes", "", linkify(facts["notes"].strip(), k, L, None), ""]
    if L.report():
        out.append(link("This report", L.report()))
    return "\n".join(out).rstrip() + "\n"


def last_try_doc(ev: dict, base_ruleset: int | None, published: int | None) -> dict:
    """What `rule try` / `rule publish` keep for the report: totals and, per rule, the courses by outcome."""
    cards = []
    for c in ev["cards"]:
        by: dict[str, list[str]] = {"fixed": [], "still_wrong": [], "newly_wrong": []}
        for r in c["annotated_rows"]:
            key = {"fixed": "fixed", "still wrong": "still_wrong", "newly wrong": "newly_wrong"}.get(r["outcome"])
            if key:
                by[key].append(r.get("course_key") or r["page_stem"])
        cards.append({"rule_id": c["rule_id"], **{k: sorted(set(v)) for k, v in by.items()}})
    return {"base_ruleset": base_ruleset, "published": published, "totals": ev["totals"], "cards": cards}
