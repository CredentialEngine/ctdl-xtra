"""A run's report, version 2 (docs/qrspi/one-rule-runs/03-spec.md §2, contract in 05-api-contract.md §3).

Claude writes `report.json`: short titles, reasons and outcomes, and everything else by **reference** (a course, a
course's value in a rule, a note, a passage of a course's saved page, a set of courses). `run done --report` checks
every reference and every quote (`check`), appends Claude's row comments to the annotation log, then resolves the
references into data (`resolve` → `report.resolved.json`, which the Studio renders with its own components) and
writes the same report as Markdown (`markdown` → `summary.md`, for Slack and older Studios).

    check(facts, known) -> list of problems (empty = fine)
    resolve(facts, known) -> report.resolved.json
    markdown(resolved, studio_url) -> summary.md

`Known` reads the catalog once: the rules (with their Studio names), the courses, every annotation's text, the run's
extractions (the version it published, else the one it started from, and the one it started from), the saved pages,
the run's last try and what it published. No text written here contains a middle dot.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import quote as urlquote
from urllib.parse import urlencode

from . import layout
from .review import Review, Snapshot, norm

ENDINGS = ("published", "needs_you", "failed")
OUTCOMES = ("published", "held", "not changed", "failed")
MARKS = ("correct", "wrong", "not_on_page", "save_expected")
TOP_FIELDS = {"ending", "reason", "rules", "also_changed", "rows", "together", "inferred", "to_do", "notes"}
MAX_NOTE_LINES = 5
MAX_OPEN_TODOS = 3
MAX_COMMENT = 400
BY_ANYONE = "anyone"  # the Rules tab's reviewer filter: a link shows the row whoever reviewed it


def rule_names(rules: dict[str, dict]) -> dict[str, str]:
    """rule id → the name the Studio shows (the property label; a page rule's or locator's title)."""
    from .server.routes_review import rule_title

    return {rid: rule_title(r, rules)[0] for rid, r in rules.items()}


def words(items: list[str]) -> str:
    """"A", "A and B", "A, B and C"."""
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def plain(s: str) -> str:
    """Quotes and passages compared as people read them: curly quotes and dashes plain, whitespace collapsed."""
    s = unicodedata.normalize("NFKC", s or "")
    s = s.translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-",
                                   "—": "-", " ": " "}))
    return " ".join(s.split())


def found(quote: str, text: str | None) -> bool:
    """`quote` appears in `text`; `…` (or `...`) joins pieces that must appear in this order."""
    if text is None:
        return False
    hay, at = plain(text), 0
    for piece in re.split(r"\s*(?:…|\.\.\.)\s*", quote or ""):
        p = plain(piece)
        if not p:
            continue
        i = hay.find(p, at)
        if i < 0:
            return False
        at = i + len(p)
    return bool(plain(quote).strip(" .…"))


def context_lines(quote: str, text: str) -> tuple[str | None, str | None]:
    """The line before and the line after the passage, for context."""
    lines = [ln for ln in (text or "").split("\n") if ln.strip()]
    pieces = [plain(p) for p in re.split(r"\s*(?:…|\.\.\.)\s*", quote) if plain(p)]
    if not pieces:
        return None, None
    first = next((i for i, ln in enumerate(lines) if pieces[0][:60] in plain(ln)), None)
    last = next((i for i, ln in enumerate(lines) if pieces[-1][-60:] in plain(ln)), first)
    if first is None:
        return None, None
    return (plain(lines[first - 1]) if first > 0 else None,
            plain(lines[last + 1]) if last is not None and last + 1 < len(lines) else None)


# =====================================================================================================
# What references are checked against
# =====================================================================================================
@dataclass
class Known:
    catalog: str                      # the short name the Studio's addresses use (avc)
    folder: str
    rules: dict[str, dict]            # the pinned version's rules
    names: dict[str, str]
    courses: dict[str, dict]          # code → {title, url, page_stem}
    notes: dict[str, dict]            # annotation id → {author, at, rule, course, kind, text}
    run: dict = field(default_factory=dict)
    goals: list[str] = field(default_factory=list)
    published: list[int] = field(default_factory=list)          # versions this run published
    changed_by_run: dict[str, int] = field(default_factory=dict)  # rule → the version this run changed it in
    ruleset_before: int | None = None
    ruleset_after: int | None = None
    based_on: int | None = None
    ext: str | None = None            # the extraction rows are read from (and `&ext=` pins)
    snap: Snapshot | None = None      # that extraction
    base: Snapshot | None = None      # the extraction of the version the run started from
    events: list = field(default_factory=list)
    last_try: dict | None = None
    publishes: list = field(default_factory=list)
    page_text: object = None          # course → the saved page's text (or None)
    _rows: dict = field(default_factory=dict)

    def row(self, rule: str, course: str, snap: Snapshot | None = None) -> dict | None:
        snap = snap or self.snap
        if snap is None or rule not in snap.rules:
            return None
        key = (id(snap), rule)
        if key not in self._rows:
            by: dict[str, dict] = {}
            for r in snap.rows(rule):
                if r.get("course_key"):
                    by.setdefault(r["course_key"], r)
            self._rows[key] = by
        return self._rows[key].get(course)

    def text(self, course: str) -> str | None:
        return self.page_text(course) if callable(self.page_text) else None


BLOCKS = {"p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "section", "article",
          "header", "footer", "dd", "dt", "dl", "blockquote", "pre", "main", "nav", "aside", "td", "th"}


def page_text(html: bytes) -> str:
    """A saved page's visible text (its body), one line per block, as people read it on the page."""
    from . import engine

    doc = engine.parse(html)
    body = doc.find("body")
    root = body if body is not None else doc
    for el in root.iter():
        if isinstance(el.tag, str) and el.tag.lower() in BLOCKS:
            el.tail = "\n" + (el.tail or "")
            if len(el) == 0 or el.text:
                el.text = "\n" + (el.text or "")
    return "\n".join(line.strip() for line in engine.text_of(root)[0].split("\n") if line.strip())


def page_text_reader(ctx, snap: Snapshot):
    """course → its saved page's visible text, read once per course."""
    cache: dict[str, str | None] = {}

    def read(course: str) -> str | None:
        if course not in cache:
            stem = next((o["page_stem"] for o in snap.occurrences.values() if o.get("course_key") == course), None)
            try:
                cache[course] = page_text(ctx.page_path(stem).read_bytes()) if stem else None
            except (FileNotFoundError, OSError):
                cache[course] = None
        return cache[course]
    return read


def build_known(ctx, run: dict) -> Known:
    """Everything a run's report is checked against and resolved from, read from the catalog now."""
    from .catalogs import info
    from .review import LOADER

    ctx.invalidate()
    versions = ctx.ruleset_versions()
    before = run.get("ruleset_before")
    published = [v for v in versions if before is not None and v > before
                 and ctx.ruleset(v).get("run_id") == run.get("run_id")]
    changed: dict[str, int] = {}
    for v in published:
        for rid in ctx.ruleset(v).get("changed_rules") or []:
            changed[rid] = v
    pinned = published[-1] if published else (before or (versions[-1] if versions else None))
    ext = ctx.extraction_for(pinned) if pinned else None
    snap = LOADER.snapshot(ctx, ext) if ext else None
    base_ext = ctx.extraction_for(before) if before else None
    base = LOADER.snapshot(ctx, base_ext) if base_ext else None
    events = LOADER.log(ctx).events()
    rules = dict(snap.rules) if snap else {}
    courses = {}
    if snap is not None:
        for o in snap.occurrences.values():
            if o.get("course_key") and o["course_key"] not in courses:
                p = snap.page.get(o["page_stem"]) or {}
                courses[o["course_key"]] = {"title": p.get("title"), "url": p.get("url"), "page_stem": o["page_stem"]}
    notes = {}
    for e in events:
        if e["type"] not in ("verdict", "comment"):
            continue
        t = e.get("target") or {}
        notes[e["annotation_id"]] = {"author": e["author"], "at": e["at"], "rule": t.get("rule_id"),
                                     "course": t.get("course_key"), "kind": e.get("verdict") or "comment",
                                     "text": e.get("note"), "expected": (e.get("expected") or {}).get("text"),
                                     "event": e}
    d = layout.agent_run_dir(ctx.catalog, run["run_id"])
    try:
        last_try = ctx.root.read_json(f"{d}/last-try.json")
    except FileNotFoundError:
        last_try = None
    try:
        publishes = ctx.root.read_json(f"{d}/published.json")["publishes"]
    except (FileNotFoundError, KeyError):
        publishes = []
    based_on = publishes[-1]["base"] if publishes else before
    scope = run.get("scope") or {}
    return Known(catalog=info(ctx.catalog)["short"], folder=ctx.catalog, rules=rules,
                 names=rule_names({**(base.rules if base else {}), **rules}), courses=courses, notes=notes, run=run,
                 goals=list(scope.get("rules") or []), published=published, changed_by_run=changed,
                 ruleset_before=before, ruleset_after=versions[-1] if versions else None, based_on=based_on,
                 ext=ext, snap=snap, base=base, events=events, last_try=last_try, publishes=publishes,
                 page_text=page_text_reader(ctx, snap) if snap else None)


# =====================================================================================================
# Checks
# =====================================================================================================
def _text(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


class Checker:
    def __init__(self, k: Known):
        self.k = k
        self.out: list[str] = []

    def add(self, msg: str) -> None:
        self.out.append(msg)

    def rule(self, where: str, rid, property_only: bool = False) -> bool:
        if rid not in self.k.rules:
            self.add(f"{where}: {rid!r} is not a rule of this catalog's ruleset")
            return False
        if property_only and self.k.rules[rid]["kind"] != "property":
            self.add(f"{where}: {rid} is a {self.k.rules[rid]['kind']} rule; rows are property rules' courses")
            return False
        return True

    def course(self, where: str, code) -> bool:
        if code not in self.k.courses:
            self.add(f"{where}: {code!r} is not a course of this catalog")
            return False
        return True

    def fields(self, where: str, item, allowed: set[str], need: tuple[str, ...] = ()) -> bool:
        if not isinstance(item, dict):
            self.add(f"{where}: must be an object")
            return False
        for f in sorted(set(item) - allowed):
            self.add(f"{where}.{f}: not a field here (fields: {', '.join(sorted(allowed))})")
        for f in need:
            if f not in item:
                self.add(f"{where}.{f}: missing")
        return True

    def ref(self, where: str, r) -> None:
        """One reference: {course} | {value: {course, rule}} | {note} | {page: {course, quote}} | {courses: …}."""
        if not isinstance(r, dict) or len(r) != 1:
            self.add(f"{where}: a reference is one of {{course}}, {{value}}, {{note}}, {{page}}, {{courses}}")
            return
        kind, v = next(iter(r.items()))
        if kind == "course":
            self.course(where, v)
        elif kind == "value":
            if not isinstance(v, dict) or not self.rule(f"{where}.value.rule", v.get("rule")) \
                    or not self.course(f"{where}.value.course", v.get("course")):
                return
        elif kind == "note":
            if v not in self.k.notes:
                self.add(f"{where}: {v!r} is not an annotation or comment on this catalog")
        elif kind == "page":
            if not isinstance(v, dict) or not self.course(f"{where}.page.course", v.get("course")):
                return
            self.passage(f"{where}.page.quote", v.get("quote"), v["course"])
        elif kind == "courses":
            if isinstance(v, list):
                for i, c in enumerate(v):
                    self.course(f"{where}.courses[{i}]", c)
            elif isinstance(v, dict):
                self.rule(f"{where}.courses.rule", v.get("rule"))
                if v.get("verdict") not in ("correct", "wrong"):
                    self.add(f"{where}.courses.verdict: correct or wrong")
            else:
                self.add(f"{where}.courses: a list of course codes, or {{rule, verdict}}")
        else:
            self.add(f"{where}: {kind!r} is not a kind of reference (course, value, note, page, courses)")

    def passage(self, where: str, q, course: str) -> None:
        if not _text(q):
            self.add(f"{where}: the passage's words, copied from the page")
        elif not found(q, self.k.text(course)):
            self.add(f"{where}: not found on {course}'s saved page: {q!r}")

    def quote(self, where: str, item: dict) -> None:
        """{quote, from}: the words must be in their source."""
        q, src = item.get("quote"), item.get("from")
        if not _text(q):
            self.add(f"{where}.quote: the words, copied exactly")
            return
        if not isinstance(src, dict) or len(src) != 1:
            self.add(f"{where}.from: {{note: <id>}}, {{page: <course>}} or {{value: {{course, rule}}}}")
            return
        kind, v = next(iter(src.items()))
        if kind == "note":
            n = self.k.notes.get(v)
            if n is None:
                self.add(f"{where}.from: {v!r} is not an annotation or comment on this catalog")
            elif not found(q, " ".join(x for x in (n["text"], n["expected"]) if x)):
                self.add(f"{where}.quote: not in {v}: {q!r}")
        elif kind == "page":
            course = v.get("course") if isinstance(v, dict) else v
            if self.course(f"{where}.from.page", course):
                self.passage(f"{where}.quote", q, course)
        elif kind == "value":
            if isinstance(v, dict) and self.rule(f"{where}.from.value.rule", v.get("rule")) \
                    and self.course(f"{where}.from.value.course", v.get("course")):
                row = self.k.row(v["rule"], v["course"])
                if not found(q, (row or {}).get("value")):
                    self.add(f"{where}.quote: not in {v['course']}'s {self.k.names.get(v['rule'])} value: {q!r}")
        else:
            self.add(f"{where}.from: {kind!r} is not a source (note, page, value)")


def check(facts: dict, k: Known) -> list[str]:
    """Every problem with `facts`, one line each (`run done` refuses the report when there is any)."""
    if not isinstance(facts, dict):
        return ["the report must be a JSON object"]
    c = Checker(k)
    for f in sorted(set(facts) - TOP_FIELDS):
        c.add(f"{f}: not a report field (fields: {', '.join(sorted(TOP_FIELDS))})")
    ending = facts.get("ending")
    if ending not in ENDINGS:
        c.add(f"ending: must be one of {', '.join(ENDINGS)}")
    lists = {f: facts.get(f) or [] for f in ("rules", "also_changed", "rows", "together", "inferred", "to_do")}
    for f, v in lists.items():
        if not isinstance(v, list):
            c.add(f"{f}: must be a list")
            lists[f] = []
    if ending == "needs_you" and not lists["to_do"]:
        c.add("to_do: a needs_you report needs at least one decision for people")
    if ending == "failed" and not _text(facts.get("reason")):
        c.add("reason: a failed report says what broke, in one line")
    if ending == "published" and not k.published:
        c.add(f"ending: published, but this run published no ruleset (the latest is v{k.ruleset_after})")
    notes = facts.get("notes")
    if notes is not None and (not isinstance(notes, str) or len(notes.strip().splitlines()) > MAX_NOTE_LINES):
        c.add(f"notes: text of at most {MAX_NOTE_LINES} lines")

    # goals: one entry per rule to improve, outcome checked against what the run published
    seen = set()
    for i, r in enumerate(lists["rules"]):
        w = f"rules[{i}]"
        if not c.fields(w, r, {"rule", "outcome", "now", "why"}, ("rule", "outcome")) or not c.rule(f"{w}.rule", r.get("rule")):
            continue
        rid = r["rule"]
        seen.add(rid)
        if k.goals and rid not in k.goals:
            c.add(f"{w}.rule: {k.names[rid]} isn't a rule to improve in this run; list it under also_changed")
        if r.get("outcome") not in OUTCOMES:
            c.add(f"{w}.outcome: one of {', '.join(OUTCOMES)}")
        elif r["outcome"] == "published" and rid not in k.changed_by_run:
            c.add(f"{w}.outcome: published, but no version this run published changed {k.names[rid]}")
        elif r["outcome"] != "published" and rid in k.changed_by_run:
            c.add(f"{w}.outcome: {k.names[rid]} was changed in v{k.changed_by_run[rid]}: say published")
    for rid in k.goals:
        if rid not in seen and rid in k.rules:
            c.add(f"rules: no entry for {k.names[rid]} ({rid}), a rule to improve")

    # also_changed must be exactly the other rules this run changed
    listed = set()
    for i, a in enumerate(lists["also_changed"]):
        w = f"also_changed[{i}]"
        if not c.fields(w, a, {"rule", "because", "why"}, ("rule", "why")) or not c.rule(f"{w}.rule", a.get("rule")):
            continue
        listed.add(a["rule"])
        if not _text(a.get("why")):
            c.add(f"{w}.why: one line on why")
        b = a.get("because")
        if b is not None and not (isinstance(b, dict) and len(b) == 1 and next(iter(b)) in ("reads", "read_by")
                                  and next(iter(b.values())) in k.rules):
            c.add(f"{w}.because: {{reads: <rule>}} or {{read_by: <rule>}}")
        if a["rule"] not in k.changed_by_run:
            c.add(f"{w}: {k.names[a['rule']]} wasn't changed in any version this run published")
        if a["rule"] in k.goals:
            c.add(f"{w}: {k.names[a['rule']]} is a rule to improve; it goes under rules")
    first = (k.run.get("scope") or {}).get("kind") == "first_rules"  # writes every rule: nothing to list
    for rid, v in sorted(k.changed_by_run.items()):
        if not first and rid not in k.goals and rid not in listed:
            c.add(f"also_changed: {k.names.get(rid, rid)} ({rid}) was changed in v{v} and isn't listed")

    for i, r in enumerate(lists["rows"]):
        w = f"rows[{i}]"
        if not c.fields(w, r, {"rule", "course", "comment"}, ("rule", "course", "comment")):
            continue
        if c.rule(f"{w}.rule", r.get("rule"), property_only=True) and c.course(f"{w}.course", r.get("course")) \
                and k.row(r["rule"], r["course"]) is None:
            c.add(f"{w}: {r['course']} has no row in {k.names[r['rule']]}")
        if not _text(r.get("comment")) or len(r.get("comment", "")) > MAX_COMMENT:
            c.add(f"{w}.comment: one sentence (at most {MAX_COMMENT} characters)")

    for i, t in enumerate(lists["together"]):
        w = f"together[{i}]"
        if not c.fields(w, t, {"rules", "because"}, ("rules", "because")):
            continue
        rs = t.get("rules")
        if not isinstance(rs, list) or len(rs) < 2:
            c.add(f"{w}.rules: two or more rule ids")
        else:
            for j, rid in enumerate(rs):
                c.rule(f"{w}.rules[{j}]", rid)
        if isinstance(t.get("because"), dict):
            c.quote(f"{w}.because", t["because"])

    tried = (k.last_try or {}).get("inferred_values") or {}
    for i, x in enumerate(lists["inferred"]):
        w = f"inferred[{i}]"
        if not c.fields(w, x, {"rule", "course", "annotation", "value", "evidence", "left_out"},
                        ("rule", "course", "annotation", "value")):
            continue
        if not c.rule(f"{w}.rule", x.get("rule"), property_only=True) or not c.course(f"{w}.course", x.get("course")):
            continue
        rid, course = x["rule"], x["course"]
        n = k.notes.get(x.get("annotation"))
        if n is None or n["rule"] != rid or n["course"] != course:
            c.add(f"{w}.annotation: {x.get('annotation')!r} is not an annotation on {course} in {k.names[rid]}")
        if not isinstance(x.get("value"), str):
            c.add(f"{w}.value: the value, as text (\"\" for empty)")
        elif rid in k.changed_by_run:
            row = k.row(rid, course)
            if norm(x["value"]) != norm((row or {}).get("value")):
                c.add(f"{w}.value: the published {k.names[rid]} of {course} is "
                      f"{(row or {}).get('value')!r}, not {x['value']!r}")
        else:
            have = tried.get(rid, {})
            if course not in have:
                c.add(f"{w}: {course}'s {k.names[rid]} isn't in your last try; add it to inferred.json and run "
                      "`rule try` again")
            elif norm(have[course]) != norm(x["value"]):
                c.add(f"{w}.value: your last try gives {have[course]!r}, not {x['value']!r}")
        for j, e in enumerate(x.get("evidence") or []):
            if c.fields(f"{w}.evidence[{j}]", e, {"quote", "from"}, ("quote", "from")):
                c.quote(f"{w}.evidence[{j}]", e)
        for j, p in enumerate(x.get("left_out") or []):
            if isinstance(p, dict) and "quote" in p and len(p) == 1:
                c.passage(f"{w}.left_out[{j}].quote", p["quote"], course)
            else:
                c.ref(f"{w}.left_out[{j}]", p)

    for i, t in enumerate(lists["to_do"]):
        w = f"to_do[{i}]"
        if not c.fields(w, t, {"ask", "rule", "about", "evidence", "options", "effect"}, ("ask",)):
            continue
        if not _text(t.get("ask")):
            c.add(f"{w}.ask: a question someone who knows the catalog can answer from the evidence")
        if t.get("rule") is not None:
            c.rule(f"{w}.rule", t["rule"])
        for j, r in enumerate(t.get("about") or []):
            c.ref(f"{w}.about[{j}]", r)
        for j, e in enumerate(t.get("evidence") or []):
            ew = f"{w}.evidence[{j}]"
            if isinstance(e, dict) and "set" in e:
                c.fields(ew, e, {"set", "label"})
                c.ref(f"{ew}.set", e["set"])
            elif c.fields(ew, e, {"quote", "from"}, ("quote", "from")):
                c.quote(ew, e)
        for j, o in enumerate(t.get("options") or []):
            ow = f"{w}.options[{j}]"
            if not c.fields(ow, o, {"answer", "do", "then"}, ("answer",)):
                continue
            if not _text(o.get("answer")):
                c.add(f"{ow}.answer: a word or two (yes, no)")
            do = o.get("do")
            if do is not None and c.fields(f"{ow}.do", do, {"mark", "courses", "rule"}, ("mark", "courses")):
                if do.get("mark") not in MARKS:
                    c.add(f"{ow}.do.mark: one of {', '.join(MARKS)}")
                if do.get("rule") is not None:
                    c.rule(f"{ow}.do.rule", do["rule"])
                c.ref(f"{ow}.do.courses", {"courses": do.get("courses")})
            then = o.get("then")
            if then is not None:
                pub = then.get("publish") if isinstance(then, dict) else None
                if not isinstance(pub, list) or set(then) != {"publish"}:
                    c.add(f"{ow}.then: {{publish: [rule ids]}}")
                else:
                    for x in pub:
                        c.rule(f"{ow}.then.publish", x)
        for j, e in enumerate(t.get("effect") or []):
            if c.fields(f"{w}.effect[{j}]", e, {"rule", "after"}, ("rule", "after")):
                c.rule(f"{w}.effect[{j}].rule", e.get("rule"))
    return c.out


# =====================================================================================================
# Resolving references into data (report.resolved.json)
# =====================================================================================================
def _h(path: str, params: dict | None = None) -> str:
    q = urlencode({a: b for a, b in (params or {}).items() if b not in (None, "")})
    return f"#/c/{path}" + (f"?{q}" if q else "")


class Resolver:
    def __init__(self, k: Known):
        self.k = k
        self.review = Review(k.snap, k.events) if k.snap is not None else None
        self._states: dict[str, dict] = {}

    def rules_link(self, rid: str, **p) -> str:
        return _h(f"{urlquote(self.k.catalog)}/rules/{urlquote(rid)}", p)

    def compare_url(self, a, b, rid: str | None = None) -> str | None:
        if not a or not b:
            return None
        return _h(f"{urlquote(self.k.catalog)}/compare", {"a": a, "b": b, "rule": rid})

    def state(self, rid: str, row: dict):
        if self.review is None:
            return None
        if rid not in self._states:
            self._states[rid] = self.review.row_states(rid, self.k.snap.rows(rid))
        return self._states[rid].get(row["key"])

    def note_source(self, aid: str) -> dict:
        n = self.k.notes[aid]
        return {"kind": "note", "annotation_id": aid, "author": n["author"], "at": n["at"], "rule": n["rule"],
                "course": n["course"]}

    def source(self, src: dict, q: str) -> dict:
        kind, v = next(iter(src.items()))
        if kind == "note":
            return self.note_source(v)
        if kind == "page":
            course = v.get("course") if isinstance(v, dict) else v
            before, after = context_lines(q, self.k.text(course) or "")
            return {"kind": "page", "course": course, "title": self.k.courses[course]["title"],
                    "before": before, "after": after}
        return {"kind": "value", "rule": v["rule"], "course": v["course"]}

    def history(self, st) -> list[dict]:
        from .server.routes_review import _event_brief

        out = []
        for e in (st.events if st else []):
            b = _event_brief(e)
            out.append({"kind": e["type"], **{k: b[k] for k in ("annotation_id", "verdict", "author", "author_role",
                                                                 "at", "note", "expected", "run_id",
                                                                 "ruleset_version", "run_at")},
                        "after_run": False})
        return out

    def card(self, rid: str, course: str, comment: str | None = None, inferred: dict | None = None,
             left_out: list | None = None) -> dict:
        """A course as its Rules tab row card, as it was when the run ended."""
        from .server.routes_review import _event_brief

        k = self.k
        row = k.row(rid, course)
        r = k.rules.get(rid) or {}
        c = k.courses.get(course, {})
        before = k.row(rid, course, k.base) if k.base is not None else None
        value = (row or {}).get("value")
        changed = k.base is not None and before is not None and norm(before.get("value")) != norm(value)
        st = self.state(rid, row) if row else None
        links = {"rules": self.rules_link(rid, row=course, by=BY_ANYONE, ext=k.ext)}
        links["wrong"] = links["rules"] + "&mark=wrong"
        return {"rule": rid, "rule_name": k.names.get(rid, rid), "legend": r.get("property_label") or k.names.get(rid, rid),
                "kind": r.get("kind"), "course": course, "title": c.get("title"),
                "page_stem": (row or {}).get("page_stem") or c.get("page_stem"), "url": c.get("url"),
                "key": (row or {}).get("key"), "occurrence_key": (row or {}).get("occurrence_key"),
                "value": value, "status": (row or {}).get("status"),
                "value_before": {"version": k.ruleset_before, "value": before.get("value")} if changed else None,
                "inferred": inferred, "left_out": left_out or [], "comment": comment,
                "verdict": _event_brief(st.verdict) if st and st.verdict else None,
                "state": st.state if st else None, "history": self.history(st), "links": links}

    def course_brief(self, rid: str, course: str) -> dict:
        row = self.k.row(rid, course)
        st = self.state(rid, row) if row else None
        return {"course": course, "title": self.k.courses.get(course, {}).get("title"),
                "value": (row or {}).get("value"), "verdict": st.verdict["verdict"] if st and st.verdict else None}

    def courses_of(self, ref, rule: str | None) -> tuple[str | None, list[str]]:
        """A set of courses: (its rule, the course codes)."""
        if isinstance(ref, dict):
            rid, want = ref["rule"], ref["verdict"]
            states = ("correct", "changed-since-correct") if want == "correct" else ("wrong", "still-wrong")
            got = []
            for row in (self.k.snap.rows(rid) if self.k.snap and rid in self.k.snap.rules else []):
                st = self.state(rid, row)
                if st and st.state in states and row.get("course_key"):
                    got.append(row["course_key"])
            return rid, sorted(set(got))
        return rule, list(ref)

    def values_changed(self, rid: str) -> dict | None:
        k = self.k
        for p in reversed(k.publishes):
            vc = (p.get("values_changed") or {}).get(rid)
            if vc is not None:
                return {"count": vc["count"], "of": vc["of"], "base": p["base"], "published": p["version"],
                        "compare_url": self.compare_url(p["base"], p["version"], rid),
                        "text": f"{vc['count']:,} of {vc['of']:,} courses", "courses": vc.get("courses", [])}
        vc = ((k.last_try or {}).get("values_changed") or {}).get(rid)
        if vc is not None:
            return {"count": vc["count"], "of": vc["of"], "base": (k.last_try or {}).get("base_ruleset"),
                    "published": None, "compare_url": None, "text": f"{vc['count']:,} of {vc['of']:,} courses",
                    "courses": vc.get("courses", [])}
        return None


def _effect_text(name: str, after) -> str:
    if after == "" or after is None:
        return f"{name} becomes empty."
    if isinstance(after, dict) and after.get("source") == "page_url":
        return f"{name} reads the page's address."
    if isinstance(after, str):
        return f"{name} becomes \"{after}\"."
    return f"{name} changes."


def _mark_words(do: dict, n: int, names: list[str], rule_name: str) -> str:
    who = names[0] if n == 1 else f"the {n} courses"
    return {"correct": f"mark {who} correct for {rule_name}", "wrong": f"mark {who} wrong for {rule_name}",
            "not_on_page": f"mark {who} \"Not on the page\" for {rule_name}",
            "save_expected": f"save {who}'s expected {rule_name}"}[do["mark"]]


def outcome(facts: dict, k: Known) -> str:
    """The band's sentence."""
    names = k.names
    if facts["ending"] == "published":
        goals = [r for r in k.goals if r in k.changed_by_run] or sorted(k.changed_by_run)
        v = k.published[-1] if k.published else k.ruleset_after
        return f"Claude published {words([names.get(r, r) for r in goals])} in v{v}."
    if facts["ending"] == "needs_you":
        n = len(facts.get("to_do") or [])
        held = [r["rule"] for r in facts.get("rules") or [] if r.get("outcome") == "held"] or k.goals
        what = f" {words([names.get(r, r) for r in held])}" if held else ""
        return f"{n} decision{'' if n == 1 else 's'} before Claude can publish{what}."
    return f"Claude couldn't finish: {' '.join(str(facts.get('reason', '')).split())}"


def resolve(facts: dict, k: Known) -> dict:
    """Every reference replaced by its data: the report the Studio renders (05-api-contract.md §3)."""
    R = Resolver(k)
    names = k.names
    run = k.run
    comments = {(r["rule"], r["course"]): r["comment"].strip() for r in facts.get("rows") or []}
    inferred_by = {(x["rule"], x["course"]): x for x in facts.get("inferred") or []}

    def inferred_of(rid: str, course: str) -> dict | None:
        x = inferred_by.get((rid, course))
        if x is None:
            return None
        return {"value": x["value"], "annotation": x["annotation"],
                "saves": "correct" if rid in k.changed_by_run else "expected"}

    def left_out_of(x: dict) -> list[dict]:
        out = []
        for p in x.get("left_out") or []:
            q = p["quote"] if "quote" in p else p["page"]["quote"]
            course = x["course"] if "quote" in p else p["page"]["course"]
            before, after = context_lines(q, k.text(course) or "")
            out.append({"text": plain(q), "before": before, "after": after})
        return out

    def card(rid: str, course: str) -> dict:
        x = inferred_by.get((rid, course))
        return R.card(rid, course, comments.get((rid, course)), inferred_of(rid, course),
                      left_out_of(x) if x else None)

    def quote_item(e: dict) -> dict:
        return {"kind": "quote", "quote": e["quote"], "source": R.source(e["from"], e["quote"])}

    # facts
    s = (k.last_try or {}).get("suite")
    pubs = k.published
    facts_out = []
    if k.goals:
        facts_out.append({"label": "Rules to improve", "text": words([names.get(r, r) for r in k.goals])})
    also = [a["rule"] for a in facts.get("also_changed") or []]
    if also:
        facts_out.append({"label": "Also changed", "text": words([names.get(r, r) for r in also])})
    if s:
        from .suite import checked_fact
        facts_out.append({"label": "Checked", "text": checked_fact(s)})
    before = k.ruleset_before
    if pubs:
        if k.based_on is not None and before is not None and k.based_on != before:
            rs_text = f"Based on v{k.based_on}; started on v{before}."
        else:
            rs_text = f"v{before} to v{pubs[-1]}" if before else f"v{pubs[-1]}"
    else:
        rs_text = f"v{before}, unchanged" if before else "none yet"
    facts_out.append({"label": "Ruleset", "text": rs_text})
    # Compare from what this run's first publish was built on: after a rebase, the versions between are other runs'
    first_base = (k.publishes[0].get("base") if k.publishes else None) or before
    compare = R.compare_url(first_base, pubs[-1]) if pubs and first_base else None

    # values Claude worked out
    inferred = []
    for x in facts.get("inferred") or []:
        inferred.append({"rule": x["rule"], "rule_name": names.get(x["rule"], x["rule"]), "course": x["course"],
                         "value": x["value"], "published": x["rule"] in k.changed_by_run,
                         "evidence": [{"quote": e["quote"], "source": R.source(e["from"], e["quote"])}
                                      for e in x.get("evidence") or []],
                         "row": card(x["rule"], x["course"])})

    # decisions
    to_do = []
    for i, t in enumerate(facts.get("to_do") or []):
        subject = t.get("rule") or next((e["rule"] for e in t.get("effect") or []), None) or \
            next((o["do"].get("rule") for o in t.get("options") or [] if o.get("do") and o["do"].get("rule")), None) \
            or (k.goals[0] if k.goals else None)
        about = []
        for ref in t.get("about") or []:
            kind, v = next(iter(ref.items()))
            if kind == "course" and subject:
                about.append(card(subject, v))
            elif kind == "value":
                about.append(card(v["rule"], v["course"]))
            elif kind == "courses":
                rid, codes = R.courses_of(v, subject)
                about += [card(rid, c) for c in codes[:3]]
        evidence = []
        for e in t.get("evidence") or []:
            if "set" in e:
                kind, v = next(iter(e["set"].items()))
                rid, codes = R.courses_of(v, subject) if kind == "courses" else (subject, [v])
                verdict = v.get("verdict") if isinstance(v, dict) else None
                evidence.append({"kind": "set", "label": e.get("label") or (f"marked {verdict}" if verdict else "courses"),
                                 "rule": rid, "count": len(codes), "rows": [card(rid, c) for c in codes[:1]],
                                 "courses": [R.course_brief(rid, c) for c in codes[1:]],
                                 "link": R.rules_link(rid, by=BY_ANYONE, verdict=verdict) if verdict else None})
            else:
                evidence.append(quote_item(e))
        options = []
        for o in t.get("options") or []:
            bits = []
            do = o.get("do")
            link = None
            if do:
                rid = do.get("rule") or (do["courses"].get("rule") if isinstance(do["courses"], dict) else subject)
                rid2, codes = R.courses_of(do["courses"], rid)
                bits.append(_mark_words(do, len(codes), codes, names.get(rid2 or rid, rid2 or rid)) + ".")
                if isinstance(do["courses"], dict):
                    link = R.rules_link(do["courses"]["rule"], by=BY_ANYONE, verdict=do["courses"]["verdict"])
                elif len(codes) == 1:
                    link = R.rules_link(rid2 or rid, row=codes[0], by=BY_ANYONE)
            pub = (o.get("then") or {}).get("publish") or []
            if pub:
                bits.append(f"The next run publishes {words([names.get(r, r) for r in pub])}"
                            + (" together." if len(pub) > 1 else "."))
            text = " ".join(bits)
            answer = o["answer"].strip()
            text = f"If {answer}, {text[0].lower() + text[1:]}" if text else f"If {answer}."
            options.append({"answer": answer, "text": text, "link": link})
        to_do.append({"ask": t["ask"].strip(), "open": i < MAX_OPEN_TODOS, "rule": subject,
                      "rule_name": names.get(subject, subject) if subject else None, "about": about,
                      "evidence": evidence, "options": options,
                      "effect": [{"rule": e["rule"], "rule_name": names.get(e["rule"], e["rule"]),
                                  "text": _effect_text(names.get(e["rule"], e["rule"]), e["after"])}
                                 for e in t.get("effect") or []]})

    # rule sections
    def section(rid: str, goal: bool, item: dict) -> dict:
        rows = [card(rid, c) for (r, c) in comments if r == rid]
        vc = R.values_changed(rid)
        if not goal and not rows:
            changed = (vc or {}).get("courses") or []
            if changed:
                rows = [card(rid, c) for c in changed[:3] if k.row(rid, c)]
            else:
                held = next((row["course_key"] for row in (k.snap.rows(rid) if k.snap and rid in k.snap.rules else [])
                             if row.get("course_key") and (R.state(rid, row) or None)
                             and R.state(rid, row).state == "correct"), None)
                rows = [card(rid, held)] if held else []
        b = item.get("because")
        because = None
        if b:
            kind, other = next(iter(b.items()))
            because = {kind: other, "name": names.get(other, other)}
        if vc:
            vc = {x: vc[x] for x in ("count", "of", "base", "published", "compare_url", "text")}
        return {"rule": rid, "name": names.get(rid, rid), "goal": goal,
                "outcome": item.get("outcome") or ("published" if rid in k.changed_by_run else "not changed"),
                "now": item.get("now"), "why": item.get("why"), "because": because, "values_changed": vc,
                "rows": rows}

    by_goal = {r["rule"]: r for r in facts.get("rules") or []}
    rules = [section(rid, True, by_goal.get(rid, {})) for rid in (k.goals or list(by_goal))]
    also_changed = [section(a["rule"], False, a) for a in facts.get("also_changed") or []]
    together = []
    for t in facts.get("together") or []:
        b = t["because"]
        together.append({"rules": t["rules"], "names": [names.get(r, r) for r in t["rules"]], "quote": b["quote"],
                         "source": R.source(b["from"], b["quote"])})
    revert = None
    if pubs:
        from .publishing import revert_text

        changed = sorted(k.changed_by_run, key=lambda r: (r not in k.goals, r))
        revert = {"version": pubs[-1],
                  "text": revert_text({"version": pubs[-1], "next_version": (k.ruleset_after or pubs[-1]) + 1,
                                       "parent": k.based_on or before, "rules": [{"rule": r} for r in changed]}, names)}
    notes = facts.get("notes")
    return {"version": 2, "run_id": run.get("run_id"), "catalog": k.folder, "catalog_short": k.catalog,
            "ending": facts["ending"], "outcome": outcome(facts, k),
            "reason": " ".join(str(facts.get("reason")).split()) if facts.get("reason") else None,
            "ruleset": {"started_on": before, "based_on": k.based_on, "published": pubs, "latest": k.ruleset_after,
                        "ext": k.ext, "compare": {"a": first_base, "b": pubs[-1], "url": compare} if compare else None},
            "facts": facts_out,
            "suite": {x: s[x] for x in ("rules", "golden", "now_right", "inferred", "got_worse")} if s else None,
            "inferred": inferred, "to_do": to_do, "rules": rules, "also_changed": also_changed, "together": together,
            "notes": notes.strip() if isinstance(notes, str) and notes.strip() else None,
            "links": {"report": _h(f"{urlquote(k.catalog)}/rules", {"run": run.get("run_id")}), "compare": compare},
            "revert": revert}


def row_keys(resolved: dict) -> list[tuple[str, str]]:
    """Every (rule, course) the report shows as a row card, in order, once."""
    seen: dict[tuple, None] = {}

    def add(c: dict) -> None:
        seen.setdefault((c["rule"], c["course"]), None)
    for x in resolved.get("inferred") or []:
        add(x["row"])
    for t in resolved.get("to_do") or []:
        for c in t["about"]:
            add(c)
        for e in t["evidence"]:
            for c in e.get("rows") or []:
                add(c)
    for s in (resolved.get("rules") or []) + (resolved.get("also_changed") or []):
        for c in s["rows"]:
            add(c)
    return list(seen)


# =====================================================================================================
# summary.md
# =====================================================================================================
def _md(label: str, url: str | None) -> str:
    return f"[{label.replace('[', '(').replace(']', ')')}]({url})" if url else label


def markdown(r: dict, studio_url: str | None) -> str:
    """The resolved report as Markdown, for Slack and for older Studios: folds become lists, the row's ✓ a link to
    the row."""
    base = (studio_url or "").split("#")[0] or None

    def url(h: str | None) -> str | None:
        return f"{base}{h}" if base and h else None

    def card_line(c: dict) -> str:
        value = "empty" if c["value"] in (None, "") else f"`{' '.join(str(c['value']).split())[:200]}`"
        line = f"- {_md(c['course'], url(c['links']['rules']))}"
        if c.get("title"):
            line += f" ({c['title']})"
        line += f": {value}"
        if c.get("value_before"):
            vb = c["value_before"]
            line += f", was `{' '.join(str(vb['value'] or '').split())[:120]}` in v{vb['version']}"
        if c.get("inferred"):
            inf = c["inferred"]["value"]
            line += f". Claude worked out {'empty' if inf == '' else f'`{inf}`'}: {_md('save it', url(c['links']['rules']))}"
        if c.get("comment"):
            line += f". Claude: {c['comment']}"
        return line

    out = [f"**{r['outcome']}**", ""]
    out += [f"- {f['label']}: {f['text']}" for f in r["facts"]]
    if r["ruleset"].get("compare"):
        cmp_ = r["ruleset"]["compare"]
        label = f"Compare v{cmp_['a']} and v{cmp_['b']}"
        out.append(f"- {_md(label, url(cmp_['url']))}")
    out.append("")
    if r["inferred"]:
        out += ["## Values Claude worked out", ""]
        for x in r["inferred"]:
            out.append(card_line(x["row"]))
            out += [f"  - {e['source'].get('author') or e['source'].get('course')}: \"{e['quote']}\""
                    for e in x["evidence"]]
        out.append("")
    if r["to_do"]:
        out += ["## What you need to decide", ""]
        for t in r["to_do"]:
            out += [f"### {t['ask']}", ""]
            out += [card_line(c) for c in t["about"]]
            for e in t["evidence"]:
                if e["kind"] == "quote":
                    out.append(f"- {e['source'].get('author') or e['source'].get('course')}: \"{e['quote']}\"")
                else:
                    codes = [c["course"] for c in e["rows"]] + [c["course"] for c in e["courses"]]
                    out.append(f"- {_md(e['label'].capitalize(), url(e.get('link')))} ({e['count']}): {', '.join(codes)}")
            out += [f"- {o['text']}" for o in t["options"]]
            out += [f"- {e['text']}" for e in t["effect"]]
            out.append("")
    for s in r["rules"] + r["also_changed"]:
        out += [f"## {'' if s['goal'] else 'Also changed: '}{s['name']}", ""]
        bits = [x for x in (s.get("now"), s.get("why")) if x]
        if bits:
            out += [" ".join(b.strip().rstrip(".") + "." for b in bits), ""]
        vc = s.get("values_changed")
        if vc:
            label = f"Compare v{vc['base']} and v{vc['published']}"
            cmp_ = f" {_md(label, url(vc['compare_url']))}" if vc.get("compare_url") else ""
            out += [f"Values changed: {vc['text']}.{cmp_}", ""]
        out += [card_line(c) for c in s["rows"]]
        if s["rows"]:
            out.append("")
    if r["together"]:
        out += ["## Rules that go together", ""]
        out += [f"- {words(t['names'])}: \"{t['quote']}\"" for t in r["together"]]
        out.append("")
    if r.get("notes"):
        out += ["## Notes", "", r["notes"], ""]
    if url(r["links"]["report"]):
        out.append(_md("This report", url(r["links"]["report"])))
    return "\n".join(out).rstrip() + "\n"


# =====================================================================================================
# The last try, kept for the report
# =====================================================================================================
def last_try_doc(ev: dict, base_ruleset: int | None, published: int | None) -> dict:
    """What `rule try` / `rule publish` keep for the report: the whole suite, values changed per rule, the inferred
    values the draft produces, and per rule the annotated courses by outcome."""
    cards = []
    for c in ev["cards"]:
        by: dict[str, list[str]] = {"fixed": [], "still_wrong": [], "newly_wrong": []}
        for r in c["annotated_rows"]:
            key = {"fixed": "fixed", "still wrong": "still_wrong", "newly wrong": "newly_wrong"}.get(r["outcome"])
            if key:
                by[key].append(r.get("course_key") or r["page_stem"])
        cards.append({"rule_id": c["rule_id"], **{k: sorted(set(v)) for k, v in by.items()}})
    s = ev.get("suite") or {}
    return {"base_ruleset": base_ruleset, "published": published, "totals": ev["totals"], "cards": cards,
            "suite": {k: s[k] for k in ("rules", "golden", "now_right", "inferred", "got_worse", "regressions")}
            | {"line": (ev.get("suite_lines") or [""])[0]} if s else None,
            "values_changed": s.get("changed") or {}, "inferred": ev.get("inferred") or [],
            "inferred_values": ev.get("inferred_values") or {}}
