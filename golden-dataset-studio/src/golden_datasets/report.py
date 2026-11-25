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
from .log import FULL_NAMES
from .review import Review, Snapshot, norm

ENDINGS = ("published", "needs_you", "failed")
OUTCOMES = ("published", "held", "not changed", "failed")
MARKS = ("correct", "wrong", "not_on_page", "save_expected")
TOP_FIELDS = {"ending", "reason", "rules", "also_changed", "rows", "together", "inferred", "to_do", "notes"}
LIST_FIELDS = ("rules", "also_changed", "rows", "together", "inferred", "to_do")
MAX_NOTE_LINES = 5
MAX_OPEN_TODOS = 3
MAX_COMMENT = 400
MAX_WHY = 320           # a to-do's `why`: at most two short sentences
MAX_WHY_SENTENCES = 2
MAX_LABEL = 80          # an option's `label`: the action, as its button says it
BY_ANYONE = "anyone"  # the Rules tab's reviewer filter: a link shows the row whoever reviewed it
SUITE_FIELDS = ("rules", "golden", "now_right", "inferred", "got_worse")
VALUES_CHANGED_FIELDS = ("count", "of", "base", "published", "compare_url", "text")

#: What each answer's mark posts, one verdict per course (the Rules tab's own: "Not on the page" is ✕ with the reason
#: `not_on_page`, sme-fixes §6). `save_expected` needs a value per course, so it opens the rows instead.
MARK_EVENTS = {"correct": {"verdict": "correct"}, "wrong": {"verdict": "wrong"},
               "not_on_page": {"verdict": "wrong", "reasons": ["not_on_page"]}}
MARK_NAMES = {"correct": "correct", "wrong": "wrong", "not_on_page": "Not on the page",
              "save_expected": "with their expected values"}

BLOCKS = {"p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "section", "article",
          "header", "footer", "dd", "dt", "dl", "blockquote", "pre", "main", "nav", "aside", "td", "th"}


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
    cls: str = "course"               # the class the run is for (the Studio's addresses name it)

    def row(self, rule: str, course: str, snap: Snapshot | None = None) -> dict | None:
        snap = snap or self.snap
        if snap is None or rule not in snap.rules:
            return None
        key = (id(snap), rule)
        if key not in self._rows:
            self._rows[key] = _rows_by_course(snap, rule)
        return self._rows[key].get(course)

    def text(self, course: str) -> str | None:
        return self.page_text(course) if callable(self.page_text) else None


def _rows_by_course(snap: Snapshot, rule: str) -> dict[str, dict]:
    by: dict[str, dict] = {}
    for r in snap.rows(rule):
        if r.get("record_external_identifier"):
            by.setdefault(r["record_external_identifier"], r)
    return by


def build_known(ctx, run: dict) -> Known:
    """Everything a run's report is checked against and resolved from, read from the catalog now."""
    from .review import LOADER

    ctx.invalidate()
    versions = ctx.ruleset_versions()
    published = _published_by(ctx, run, versions)
    ext, snap, base = _pinned_snapshots(ctx, run.get("ruleset_before"), published, versions)
    known = _known_catalog(ctx, ext, snap, base, LOADER.log(ctx).events())
    _add_run_facts(known, ctx, run, published, versions)
    return known


def _published_by(ctx, run: dict, versions: list[int]) -> list[int]:
    before = run.get("ruleset_before")
    return [v for v in versions if before is not None and v > before
            and ctx.ruleset(v).get("run_id") == run.get("run_id")]


def _pinned_snapshots(ctx, before: int | None, published: list[int], versions: list[int]):
    """The extraction of the version this run published (else the one it started from), and the one it started from."""
    from .review import LOADER

    pinned = published[-1] if published else (before or (versions[-1] if versions else None))
    ext = ctx.extraction_for(pinned) if pinned else None
    snap = LOADER.snapshot(ctx, ext) if ext else None
    base_ext = ctx.extraction_for(before) if before else None
    base = LOADER.snapshot(ctx, base_ext) if base_ext else None
    return ext, snap, base


def _known_catalog(ctx, ext: str | None, snap: Snapshot | None, base: Snapshot | None, events: list) -> Known:
    from .catalogs import info

    rules = dict(snap.rules) if snap else {}
    return Known(catalog=info(ctx.catalog)["short"], folder=ctx.catalog, cls=ctx.cls, rules=rules,
                 names=rule_names({**(base.rules if base else {}), **rules}), courses=_courses_of(snap),
                 notes=_notes_of(events), ext=ext, snap=snap, base=base, events=events,
                 page_text=page_text_reader(ctx, snap) if snap else None)


def _add_run_facts(known: Known, ctx, run: dict, published: list[int], versions: list[int]) -> None:
    before = run.get("ruleset_before")
    known.last_try, known.publishes = _run_files(ctx, run)
    known.run, known.goals = run, list((run.get("scope") or {}).get("rules") or [])
    known.published, known.changed_by_run = published, _changed_rules(ctx, published)
    known.ruleset_before, known.ruleset_after = before, versions[-1] if versions else None
    known.based_on = known.publishes[-1]["base"] if known.publishes else before


def _changed_rules(ctx, published: list[int]) -> dict[str, int]:
    changed: dict[str, int] = {}
    for v in published:
        for rid in ctx.ruleset(v).get("changed_rules") or []:
            changed[rid] = v
    return changed


def _courses_of(snap: Snapshot | None) -> dict[str, dict]:
    courses: dict[str, dict] = {}
    for o in snap.occurrences.values() if snap is not None else []:
        code = o.get("record_external_identifier")
        if code and code not in courses:
            p = snap.page.get(o["page_stem"]) or {}
            courses[code] = {"title": p.get("title"), "url": p.get("url"), "page_stem": o["page_stem"]}
    return courses


def _notes_of(events: list) -> dict[str, dict]:
    return {e["annotation_id"]: _note(e) for e in events if e["type"] in ("verdict", "comment")}


def _note(e: dict) -> dict:
    t = e.get("target") or {}
    return {"author": e["author"], "at": e["at"], "rule": t.get("rule_id"),
            "course": t.get("record_external_identifier"), "kind": e.get("verdict") or "comment",
            "text": e.get("note"), "expected": (e.get("expected") or {}).get("text"), "event": e}


def _run_files(ctx, run: dict) -> tuple[dict | None, list]:
    folder = layout.agent_run_dir(ctx.catalog, ctx.cls, run["run_id"])
    try:
        last_try = ctx.root.read_json(f"{folder}/last-try.json")
    except FileNotFoundError:
        last_try = None
    try:
        publishes = ctx.root.read_json(f"{folder}/published.json")["publishes"]
    except (FileNotFoundError, KeyError):
        publishes = []
    return last_try, publishes


# =====================================================================================================
# Checks
# =====================================================================================================
def check(facts: dict, k: Known) -> list[str]:
    """Every problem with `facts`, one line each (`run done` refuses the report when there is any)."""
    if not isinstance(facts, dict):
        return ["the report must be a JSON object"]
    c = Checker(k)
    lists = c.top_fields(facts)
    c.goal_rules(lists["rules"])
    c.also_changed(lists["also_changed"])
    c.rows(lists["rows"])
    c.together(lists["together"])
    c.inferred(lists["inferred"])
    c.to_dos(lists["to_do"])
    return c.out


class Checker:
    def __init__(self, k: Known):
        self.k = k
        self.out: list[str] = []

    def add(self, msg: str) -> None:
        self.out.append(msg)

    # --- the report's own fields ---
    def top_fields(self, facts: dict) -> dict[str, list]:
        for f in sorted(set(facts) - TOP_FIELDS):
            self.add(f"{f}: not a report field (fields: {', '.join(sorted(TOP_FIELDS))})")
        ending = facts.get("ending")
        if ending not in ENDINGS:
            self.add(f"ending: must be one of {', '.join(ENDINGS)}")
        lists = self.lists_of(facts)
        self.ending_needs(ending, facts, lists)
        self.notes(facts.get("notes"))
        return lists

    def lists_of(self, facts: dict) -> dict[str, list]:
        lists = {f: facts.get(f) or [] for f in LIST_FIELDS}
        for f, v in lists.items():
            if not isinstance(v, list):
                self.add(f"{f}: must be a list")
                lists[f] = []
        return lists

    def ending_needs(self, ending, facts: dict, lists: dict[str, list]) -> None:
        if ending == "needs_you" and not lists["to_do"]:
            self.add("to_do: a needs_you report needs at least one decision for people")
        if ending == "failed" and not _text(facts.get("reason")):
            self.add("reason: a failed report says what broke, in one line")
        if ending == "published" and not self.k.published:
            self.add(f"ending: published, but this run published no ruleset (the latest is v{self.k.ruleset_after})")

    def notes(self, notes) -> None:
        if notes is not None and (not isinstance(notes, str) or len(notes.strip().splitlines()) > MAX_NOTE_LINES):
            self.add(f"notes: text of at most {MAX_NOTE_LINES} lines")

    # --- rules to improve: one entry per rule, its outcome checked against what the run published ---
    def goal_rules(self, items: list) -> None:
        seen = set()
        for i, r in enumerate(items):
            w = f"rules[{i}]"
            if self.fields(w, r, {"rule", "outcome", "now", "why"}, ("rule", "outcome")) \
                    and self.rule(f"{w}.rule", r.get("rule")):
                seen.add(r["rule"])
                self.goal_rule(w, r)
        for rid in self.k.goals:
            if rid not in seen and rid in self.k.rules:
                self.add(f"rules: no entry for {self.k.names[rid]} ({rid}), a rule to improve")

    def goal_rule(self, w: str, r: dict) -> None:
        k, rid = self.k, r["rule"]
        if k.goals and rid not in k.goals:
            self.add(f"{w}.rule: {k.names[rid]} isn't a rule to improve in this run; list it under also_changed")
        if r.get("outcome") not in OUTCOMES:
            self.add(f"{w}.outcome: one of {', '.join(OUTCOMES)}")
        elif r["outcome"] == "published" and rid not in k.changed_by_run:
            self.add(f"{w}.outcome: published, but no version this run published changed {k.names[rid]}")
        elif r["outcome"] != "published" and rid in k.changed_by_run:
            self.add(f"{w}.outcome: {k.names[rid]} was changed in v{k.changed_by_run[rid]}: say published")

    # --- also_changed: exactly the other rules this run changed ---
    def also_changed(self, items: list) -> None:
        listed = set()
        for i, a in enumerate(items):
            w = f"also_changed[{i}]"
            if self.fields(w, a, {"rule", "because", "why"}, ("rule", "why")) \
                    and self.rule(f"{w}.rule", a.get("rule")):
                listed.add(a["rule"])
                self.also_changed_rule(w, a)
        first = (self.k.run.get("scope") or {}).get("kind") == "first_rules"  # writes every rule: nothing to list
        for rid, v in sorted(self.k.changed_by_run.items()):
            if not first and rid not in self.k.goals and rid not in listed:
                self.add(f"also_changed: {self.k.names.get(rid, rid)} ({rid}) was changed in v{v} and isn't listed")

    def also_changed_rule(self, w: str, a: dict) -> None:
        k = self.k
        if not _text(a.get("why")):
            self.add(f"{w}.why: one line on why")
        b = a.get("because")
        if b is not None and not (isinstance(b, dict) and len(b) == 1 and next(iter(b)) in ("reads", "read_by")
                                  and next(iter(b.values())) in k.rules):
            self.add(f"{w}.because: {{reads: <rule>}} or {{read_by: <rule>}}")
        if a["rule"] not in k.changed_by_run:
            self.add(f"{w}: {k.names[a['rule']]} wasn't changed in any version this run published")
        if a["rule"] in k.goals:
            self.add(f"{w}: {k.names[a['rule']]} is a rule to improve; it goes under rules")

    # --- rows, together ---
    def rows(self, items: list) -> None:
        for i, r in enumerate(items):
            w = f"rows[{i}]"
            if self.fields(w, r, {"rule", "course", "comment"}, ("rule", "course", "comment")):
                self.row_comment(w, r)

    def row_comment(self, w: str, r: dict) -> None:
        if self.rule(f"{w}.rule", r.get("rule"), property_only=True) and self.course(f"{w}.course", r.get("course")) \
                and self.k.row(r["rule"], r["course"]) is None:
            self.add(f"{w}: {r['course']} has no row in {self.k.names[r['rule']]}")
        if not _text(r.get("comment")) or len(r.get("comment", "")) > MAX_COMMENT:
            self.add(f"{w}.comment: one sentence (at most {MAX_COMMENT} characters)")

    def together(self, items: list) -> None:
        for i, t in enumerate(items):
            w = f"together[{i}]"
            if self.fields(w, t, {"rules", "because"}, ("rules", "because")):
                self.together_item(w, t)

    def together_item(self, w: str, t: dict) -> None:
        rs = t.get("rules")
        if not isinstance(rs, list) or len(rs) < 2:
            self.add(f"{w}.rules: two or more rule ids")
        else:
            for j, rid in enumerate(rs):
                self.rule(f"{w}.rules[{j}]", rid)
        if isinstance(t.get("because"), dict):
            self.quote(f"{w}.because", t["because"])

    # --- values Claude worked out ---
    def inferred(self, items: list) -> None:
        tried = (self.k.last_try or {}).get("inferred_values") or {}
        for i, x in enumerate(items):
            w = f"inferred[{i}]"
            if self.fields(w, x, {"rule", "course", "annotation", "value", "evidence", "left_out"},
                           ("rule", "course", "annotation", "value")) \
                    and self.rule(f"{w}.rule", x.get("rule"), property_only=True) \
                    and self.course(f"{w}.course", x.get("course")):
                self.inferred_item(w, x, tried)

    def inferred_item(self, w: str, x: dict, tried: dict) -> None:
        rid, course = x["rule"], x["course"]
        n = self.k.notes.get(x.get("annotation"))
        if n is None or n["rule"] != rid or n["course"] != course:
            self.add(f"{w}.annotation: {x.get('annotation')!r} is not an annotation on {course} in {self.k.names[rid]}")
        self.inferred_value(w, x, tried)
        for j, e in enumerate(x.get("evidence") or []):
            if self.fields(f"{w}.evidence[{j}]", e, {"quote", "from"}, ("quote", "from")):
                self.quote(f"{w}.evidence[{j}]", e)
        for j, p in enumerate(x.get("left_out") or []):
            if isinstance(p, dict) and "quote" in p and len(p) == 1:
                self.passage(f"{w}.left_out[{j}].quote", p["quote"], course)
            else:
                self.ref(f"{w}.left_out[{j}]", p)

    def inferred_value(self, w: str, x: dict, tried: dict) -> None:
        if not isinstance(x.get("value"), str):
            self.add(f"{w}.value: the value, as text (\"\" for empty)")
        elif x["rule"] in self.k.changed_by_run:
            self.published_value(w, x)
        else:
            self.tried_value(w, x, tried.get(x["rule"], {}))

    def published_value(self, w: str, x: dict) -> None:
        rid, course = x["rule"], x["course"]
        row = self.k.row(rid, course)
        if norm(x["value"]) != norm((row or {}).get("value")):
            self.add(f"{w}.value: the published {self.k.names[rid]} of {course} is "
                     f"{(row or {}).get('value')!r}, not {x['value']!r}")

    def tried_value(self, w: str, x: dict, have: dict) -> None:
        course = x["course"]
        if course not in have:
            self.add(f"{w}: {course}'s {self.k.names[x['rule']]} isn't in your last try; add it to inferred.json and run "
                     "`rule try` again")
        elif norm(have[course]) != norm(x["value"]):
            self.add(f"{w}.value: your last try gives {have[course]!r}, not {x['value']!r}")

    # --- decisions for people ---
    def to_dos(self, items: list) -> None:
        for i, t in enumerate(items):
            w = f"to_do[{i}]"
            if self.fields(w, t, {"ask", "why", "rule", "about", "evidence", "options", "effect"}, ("ask", "why")):
                self.to_do_words(w, t)
                self.to_do_parts(w, t)

    def to_do_words(self, w: str, t: dict) -> None:
        if not _text(t.get("ask")):
            self.add(f"{w}.ask: a question someone who knows the catalog can answer from the evidence")
        if "why" in t and (not _text(t.get("why")) or sentences(t["why"]) > MAX_WHY_SENTENCES
                           or len(t["why"]) > MAX_WHY):
            self.add(f"{w}.why: at most {MAX_WHY_SENTENCES} short sentences ({MAX_WHY} characters) of plain context, "
                     "naming the courses and rules")

    def to_do_parts(self, w: str, t: dict) -> None:
        if t.get("rule") is not None:
            self.rule(f"{w}.rule", t["rule"])
        for j, r in enumerate(t.get("about") or []):
            self.ref(f"{w}.about[{j}]", r)
        for j, e in enumerate(t.get("evidence") or []):
            self.to_do_evidence(f"{w}.evidence[{j}]", e)
        for j, o in enumerate(t.get("options") or []):
            self.option(f"{w}.options[{j}]", o)
        for j, e in enumerate(t.get("effect") or []):
            if self.fields(f"{w}.effect[{j}]", e, {"rule", "after"}, ("rule", "after")):
                self.rule(f"{w}.effect[{j}].rule", e.get("rule"))

    def to_do_evidence(self, ew: str, e) -> None:
        if isinstance(e, dict) and "set" in e:
            self.fields(ew, e, {"set", "label"})
            self.ref(f"{ew}.set", e["set"])
        elif self.fields(ew, e, {"quote", "from"}, ("quote", "from")):
            self.quote(ew, e)

    def option(self, ow: str, o) -> None:
        if not self.fields(ow, o, {"answer", "label", "do", "then"}, ("answer", "label")):
            return
        if not _text(o.get("answer")):
            self.add(f"{ow}.answer: a word or two (yes, no)")
        if "label" in o and (not _text(o.get("label")) or len(o["label"]) > MAX_LABEL):
            self.add(f"{ow}.label: the action, in a few words (at most {MAX_LABEL} characters), e.g. "
                     "\"mark the 13 courses Not on the page\"")
        if o.get("do") is not None:
            self.option_do(ow, o["do"])
        if o.get("then") is not None:
            self.option_then(ow, o["then"])

    def option_do(self, ow: str, do) -> None:
        if not self.fields(f"{ow}.do", do, {"mark", "courses", "rule"}, ("mark", "courses")):
            return
        if do.get("mark") not in MARKS:
            self.add(f"{ow}.do.mark: one of {', '.join(MARKS)}")
        if do.get("rule") is not None:
            self.rule(f"{ow}.do.rule", do["rule"], property_only=True)
        self.ref(f"{ow}.do.courses", {"courses": do.get("courses")})

    def option_then(self, ow: str, then) -> None:
        pub = then.get("publish") if isinstance(then, dict) else None
        if not isinstance(pub, list) or set(then) != {"publish"}:
            self.add(f"{ow}.then: {{publish: [rule ids]}}")
            return
        for x in pub:
            self.rule(f"{ow}.then.publish", x)

    # --- the building blocks: rules, courses, fields, references, quotes ---
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
        check_ref = {"course": self.course, "value": self.value_ref, "note": self.note_ref,
                     "page": self.page_ref, "courses": self.courses_ref}.get(kind)
        if check_ref is None:
            self.add(f"{where}: {kind!r} is not a kind of reference (course, value, note, page, courses)")
            return
        check_ref(where, v)

    def value_ref(self, where: str, v) -> None:
        if isinstance(v, dict) and self.rule(f"{where}.value.rule", v.get("rule")):
            self.course(f"{where}.value.course", v.get("course"))

    def note_ref(self, where: str, v) -> None:
        if v not in self.k.notes:
            self.add(f"{where}: {v!r} is not an annotation or comment on this catalog")

    def page_ref(self, where: str, v) -> None:
        if isinstance(v, dict) and self.course(f"{where}.page.course", v.get("course")):
            self.passage(f"{where}.page.quote", v.get("quote"), v["course"])

    def courses_ref(self, where: str, v) -> None:
        if isinstance(v, list):
            for i, c in enumerate(v):
                self.course(f"{where}.courses[{i}]", c)
        elif isinstance(v, dict):
            self.rule(f"{where}.courses.rule", v.get("rule"))
            if v.get("verdict") not in ("correct", "wrong"):
                self.add(f"{where}.courses.verdict: correct or wrong")
        else:
            self.add(f"{where}.courses: a list of course codes, or {{rule, verdict}}")

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
        check_quote = {"note": self.quote_in_note, "page": self.quote_on_page, "value": self.quote_in_value}.get(kind)
        if check_quote is None:
            self.add(f"{where}.from: {kind!r} is not a source (note, page, value)")
            return
        check_quote(where, q, v)

    def quote_in_note(self, where: str, q: str, v) -> None:
        n = self.k.notes.get(v)
        if n is None:
            self.add(f"{where}.from: {v!r} is not an annotation or comment on this catalog")
        elif not found(q, " ".join(x for x in (n["text"], n["expected"]) if x)):
            self.add(f"{where}.quote: not in {v}: {q!r}")

    def quote_on_page(self, where: str, q: str, v) -> None:
        course = v.get("course") if isinstance(v, dict) else v
        if self.course(f"{where}.from.page", course):
            self.passage(f"{where}.quote", q, course)

    def quote_in_value(self, where: str, q: str, v) -> None:
        if isinstance(v, dict) and self.rule(f"{where}.from.value.rule", v.get("rule")) \
                and self.course(f"{where}.from.value.course", v.get("course")):
            row = self.k.row(v["rule"], v["course"])
            if not found(q, (row or {}).get("value")):
                self.add(f"{where}.quote: not in {v['course']}'s {self.k.names.get(v['rule'])} value: {q!r}")


# =====================================================================================================
# Resolving references into data (report.resolved.json)
# =====================================================================================================
def resolve(facts: dict, k: Known) -> dict:
    """Every reference replaced by its data: the report the Studio renders (05-api-contract.md §3)."""
    resolution = _Resolution(facts, k)
    return {**resolution.header(), **resolution.body()}


class _Resolution:
    """One report's facts resolved against what is known: the header, the decisions, the rule sections."""

    def __init__(self, facts: dict, k: Known):
        self.facts, self.k, self.names = facts, k, k.names
        self.resolver = Resolver(k)
        self.comments = {(r["rule"], r["course"]): r["comment"].strip() for r in facts.get("rows") or []}
        self.inferred_by = {(x["rule"], x["course"]): x for x in facts.get("inferred") or []}

    def header(self) -> dict:
        facts, k = self.facts, self.k
        first_base, compare = self.compare()
        return {"version": 2, "run_id": k.run.get("run_id"), "catalog": k.folder, "catalog_short": k.catalog,
                "ending": facts["ending"], "outcome": outcome(facts, k),
                "reason": " ".join(str(facts.get("reason")).split()) if facts.get("reason") else None,
                "ruleset": {"started_on": k.ruleset_before, "based_on": k.based_on, "published": k.published,
                            "latest": k.ruleset_after, "ext": k.ext,
                            "compare": {"a": first_base, "b": k.published[-1], "url": compare} if compare else None},
                "facts": self.fact_lines(), "suite": self.suite()}

    def body(self) -> dict:
        k, notes = self.k, self.facts.get("notes")
        return {"inferred": self.inferred_values(), "to_do": self.decisions(), "rules": self.goal_sections(),
                "also_changed": self.also_changed_sections(), "together": self.together(),
                "notes": notes.strip() if isinstance(notes, str) and notes.strip() else None,
                "links": {"report": _h(f"{urlquote(k.catalog)}/{k.cls}/rules", {"run": k.run.get("run_id")}),
                          "compare": self.compare()[1]},
                "revert": self.revert()}

    def compare(self) -> tuple[int | None, str | None]:
        """Compare from what this run's first publish was built on: after a rebase, the versions between are other
        runs'."""
        k, pubs = self.k, self.k.published
        first_base = (k.publishes[0].get("base") if k.publishes else None) or k.ruleset_before
        return first_base, self.resolver.compare_url(first_base, pubs[-1]) if pubs and first_base else None

    # --- facts ---
    def fact_lines(self) -> list[dict]:
        k = self.k
        suite = (k.last_try or {}).get("suite")
        out = []
        if k.goals:
            out.append({"label": "Rules to improve", "text": self.names_of(k.goals)})
        also = [a["rule"] for a in self.facts.get("also_changed") or []]
        if also:
            out.append({"label": "Also changed", "text": self.names_of(also)})
        if suite:
            from .suite import checked_fact
            out.append({"label": "Checked", "text": checked_fact(suite)})
        out.append({"label": "Ruleset", "text": self.ruleset_text()})
        return out

    def ruleset_text(self) -> str:
        k, pubs, before = self.k, self.k.published, self.k.ruleset_before
        if not pubs:
            return f"v{before}, unchanged" if before else "none yet"
        if k.based_on is not None and before is not None and k.based_on != before:
            return f"Based on v{k.based_on}; started on v{before}."
        return f"v{before} to v{pubs[-1]}" if before else f"v{pubs[-1]}"

    def suite(self) -> dict | None:
        suite = (self.k.last_try or {}).get("suite")
        return {x: suite[x] for x in SUITE_FIELDS} if suite else None

    # --- values Claude worked out ---
    def inferred_values(self) -> list[dict]:
        return [self.inferred_value(x) for x in self.facts.get("inferred") or []]

    def inferred_value(self, x: dict) -> dict:
        return {"rule": x["rule"], "rule_name": self.names.get(x["rule"], x["rule"]), "course": x["course"],
                "value": x["value"], "published": x["rule"] in self.k.changed_by_run,
                "evidence": [{"quote": e["quote"], "source": self.resolver.source(e["from"], e["quote"])}
                             for e in x.get("evidence") or []],
                "row": self.card(x["rule"], x["course"])}

    def card(self, rid: str, course: str) -> dict:
        x = self.inferred_by.get((rid, course))
        return self.resolver.card(rid, course, self.comments.get((rid, course)), self.inferred_of(rid, course),
                                  self.left_out_of(x) if x else None)

    def inferred_of(self, rid: str, course: str) -> dict | None:
        x = self.inferred_by.get((rid, course))
        if x is None:
            return None
        return {"value": x["value"], "annotation": x["annotation"],
                "saves": "correct" if rid in self.k.changed_by_run else "expected"}

    def left_out_of(self, x: dict) -> list[dict]:
        out = []
        for p in x.get("left_out") or []:
            q = p["quote"] if "quote" in p else p["page"]["quote"]
            course = x["course"] if "quote" in p else p["page"]["course"]
            before, after = context_lines(q, self.k.text(course) or "")
            out.append({"text": plain(q), "before": before, "after": after})
        return out

    # --- decisions (pass 7): what to decide and why first, then the answers (each one an action the Studio can
    # take: one verdict per course), then the evidence, every row card introduced in words ---
    def decisions(self) -> list[dict]:
        return [self.decision(i, t) for i, t in enumerate(self.facts.get("to_do") or [])]

    def decision(self, i: int, t: dict) -> dict:
        subject = self.subject_of(t)
        shown: set = set()
        about = self.about_cards(t, subject, shown)
        evidence = [self.evidence_item(e, subject, shown) for e in t.get("evidence") or []]
        effects = t.get("effect") or []
        return {"ask": t["ask"].strip(), "why": " ".join(str(t.get("why") or "").split()) or None,
                "open": i < MAX_OPEN_TODOS, "rule": subject,
                "rule_name": self.names.get(subject, subject) if subject else None, "about": about,
                "evidence": evidence, "options": self.options(t, subject),
                "effect": [{"rule": e["rule"], "rule_name": self.names.get(e["rule"], e["rule"]),
                            "text": _effect_text(self.names.get(e["rule"], e["rule"]), e["after"])}
                           for e in effects]}

    def subject_of(self, t: dict) -> str | None:
        return t.get("rule") or next((e["rule"] for e in t.get("effect") or []), None) or \
            next((o["do"].get("rule") for o in t.get("options") or [] if o.get("do") and o["do"].get("rule")), None) \
            or (self.k.goals[0] if self.k.goals else None)

    def about_cards(self, t: dict, subject: str | None, shown: set) -> list[dict]:
        about = []
        for ref in t.get("about") or []:
            for card in self.cards_of(ref, subject):
                if (card["rule"], card["course"]) not in shown:
                    shown.add((card["rule"], card["course"]))
                    about.append(card | {"lead": _lead_of(card)})
        return about

    def cards_of(self, ref: dict, subject: str | None) -> list[dict]:
        kind, v = next(iter(ref.items()))
        if kind == "course" and subject:
            return [self.card(subject, v)]
        if kind == "value":
            return [self.card(v["rule"], v["course"])]
        if kind == "courses":
            rid, codes = self.resolver.courses_of(v, subject)
            return [self.card(rid, c) for c in codes[:3]]
        return []

    def evidence_item(self, e: dict, subject: str | None, shown: set) -> dict:
        if "set" not in e:
            return {"kind": "quote", "quote": e["quote"], "source": self.resolver.source(e["from"], e["quote"])}
        return self.course_set(e, subject, shown)

    def course_set(self, e: dict, subject: str | None, shown: set) -> dict:
        kind, v = next(iter(e["set"].items()))
        rid, codes = self.resolver.courses_of(v, subject) if kind == "courses" else (subject, [v])
        verdict = v.get("verdict") if isinstance(v, dict) else None
        briefs = [self.resolver.course_brief(rid, c) for c in codes]
        label = _set_label(e, verdict, briefs)
        first = next((c for c in codes if (rid, c) not in shown), None)
        rows = self.set_rows(rid, first, len(codes), label, shown)
        others = [b for b in briefs if b["course"] != first]
        return {"kind": "set", "label": label, "rule": rid, "count": len(codes), "rows": rows, "courses": others,
                "others_lead": _others_lead(others, label),
                "link": self.resolver.rules_link(rid, by=BY_ANYONE, verdict=verdict) if verdict else None}

    def set_rows(self, rid: str, first: str | None, n: int, label: str, shown: set) -> list[dict]:
        if not first:
            return []
        shown.add((rid, first))
        lead = f"Here is one of the {n} courses {label}:" if n > 1 else f"Here is the course {label}:"
        return [self.card(rid, first) | {"lead": lead}]

    def options(self, t: dict, subject: str | None) -> list[dict]:
        effects = t.get("effect") or []
        opts = t.get("options") or []
        owner = _effect_owner(opts, effects)
        return [self.option(o, subject, effects if j == owner else []) for j, o in enumerate(opts)]

    def option(self, o: dict, subject: str | None, effects: list[dict]) -> dict:
        answer = o["answer"].strip()
        do = o.get("do")
        marking = self.marking(do, subject) if do else _NO_MARKING
        pub = (o.get("then") or {}).get("publish") or []
        again = list(dict.fromkeys([*self.k.goals, *pub])) if (pub or do) else []
        needs = list(dict.fromkeys([*pub, *[e["rule"] for e in effects]]))
        label = (o.get("label") or "").strip() or marking["said"]
        effect = [_effect_text(self.names.get(e["rule"], e["rule"]), e["after"]) for e in effects]
        return {"answer": answer, "label": label,
                "button": f"{answer[:1].upper()}{answer[1:]}: {label}" if label else answer.capitalize(),
                "text": self.option_text(answer, marking, pub), "link": marking["link"], "do": marking["do"],
                "done": marking["done"], "then": self.then(pub, again), "effect": " ".join(effect) or None,
                "no_rule_yet": [f"{self.names.get(r, r)} has no rule yet; the next run writes one."
                                for r in needs if not self.resolver.has_rule(r)]}

    def option_text(self, answer: str, marking: dict, pub: list[str]) -> str:
        bits = [marking["said"] + "."] if marking["do"] else []
        if pub:
            bits.append(f"The next run publishes {self.names_of(pub)}" + (" together." if len(pub) > 1 else "."))
        text = " ".join(bits)
        return f"If {answer}, {text[0].lower() + text[1:]}" if text else f"If {answer}."

    def then(self, pub: list[str], again: list[str]) -> dict:
        return {"publish": [{"rule": r, "name": self.names.get(r, r), "has_rule": self.resolver.has_rule(r)}
                            for r in pub],
                "run_again": [{"rule": r, "name": self.names.get(r, r)} for r in again],
                "text": f"Then run again with {self.names_of(again)}." if again else None}

    def marking(self, do: dict, subject: str | None) -> dict:
        """What an answer's `do` marks: its words, a link to the rows, and the verdict per course it posts."""
        rid = do.get("rule") or (do["courses"].get("rule") if isinstance(do["courses"], dict) else subject)
        marked_rule, codes = self.resolver.courses_of(do["courses"], rid)
        marked_rule = marked_rule or rid
        rule_name = self.names.get(marked_rule, marked_rule)
        mark = do["mark"]
        return {"said": _mark_words(do, len(codes), codes, rule_name), "link": self.mark_link(do, marked_rule, codes),
                "done": _done_text(mark, codes),
                "do": {"mark": mark, "rule": marked_rule, "rule_name": rule_name, "words": MARK_NAMES[mark],
                       "event": MARK_EVENTS.get(mark), "count": len(codes),
                       "courses": [self.resolver.course_brief(marked_rule, c) for c in codes]}}

    def mark_link(self, do: dict, rule: str, codes: list[str]) -> str | None:
        if isinstance(do["courses"], dict):
            return self.resolver.rules_link(do["courses"]["rule"], by=BY_ANYONE, verdict=do["courses"]["verdict"])
        if len(codes) == 1:
            return self.resolver.rules_link(rule, row=codes[0], by=BY_ANYONE)
        return None

    # --- rule sections ---
    def goal_sections(self) -> list[dict]:
        by_goal = {r["rule"]: r for r in self.facts.get("rules") or []}
        return [self.section(rid, True, by_goal.get(rid, {})) for rid in (self.k.goals or list(by_goal))]

    def also_changed_sections(self) -> list[dict]:
        return [self.section(a["rule"], False, a) for a in self.facts.get("also_changed") or []]

    def section(self, rid: str, goal: bool, item: dict) -> dict:
        values_changed = self.resolver.values_changed(rid)
        rows = self.section_rows(rid, goal, values_changed)
        return {"rule": rid, "name": self.names.get(rid, rid), "goal": goal,
                "outcome": item.get("outcome") or ("published" if rid in self.k.changed_by_run else "not changed"),
                "now": item.get("now"), "why": item.get("why"), "because": self.because(item.get("because")),
                "values_changed": {x: values_changed[x] for x in VALUES_CHANGED_FIELDS} if values_changed
                else values_changed,
                "rows": rows}

    def section_rows(self, rid: str, goal: bool, values_changed: dict | None) -> list[dict]:
        rows = [self.card(rid, c) for (r, c) in self.comments if r == rid]
        if goal or rows:
            return rows
        changed = (values_changed or {}).get("courses") or []
        if changed:
            return [self.card(rid, c) for c in changed[:3] if self.k.row(rid, c)]
        held = self.correct_course(rid)
        return [self.card(rid, held)] if held else []

    def correct_course(self, rid: str) -> str | None:
        snap = self.k.snap
        rows = snap.rows(rid) if snap and rid in snap.rules else []
        return next((row["record_external_identifier"] for row in rows if row.get("record_external_identifier")
                     and _is_correct(self.resolver.state(rid, row))), None)

    def because(self, b: dict | None) -> dict | None:
        if not b:
            return None
        kind, other = next(iter(b.items()))
        return {kind: other, "name": self.names.get(other, other)}

    def together(self) -> list[dict]:
        return [self.together_item(t) for t in self.facts.get("together") or []]

    def together_item(self, t: dict) -> dict:
        b = t["because"]
        return {"rules": t["rules"], "names": [self.names.get(r, r) for r in t["rules"]], "quote": b["quote"],
                "source": self.resolver.source(b["from"], b["quote"])}

    def revert(self) -> dict | None:
        from .publishing import revert_text

        k, pubs = self.k, self.k.published
        if not pubs:
            return None
        changed = sorted(k.changed_by_run, key=lambda r: (r not in k.goals, r))
        return {"version": pubs[-1],
                "text": revert_text({"version": pubs[-1], "next_version": (k.ruleset_after or pubs[-1]) + 1,
                                     "parent": k.based_on or k.ruleset_before,
                                     "rules": [{"rule": r} for r in changed]}, self.names)}

    def names_of(self, rids: list[str]) -> str:
        return words([self.names.get(r, r) for r in rids])


_NO_MARKING = {"said": "", "link": None, "done": None, "do": None}


class Resolver:
    def __init__(self, k: Known):
        self.k = k
        self.review = Review(k.snap, k.events) if k.snap is not None else None
        self._states: dict[str, dict] = {}

    def card(self, rid: str, course: str, comment: str | None = None, inferred: dict | None = None,
             left_out: list | None = None) -> dict:
        """A course as its Rules tab row card, as it was when the run ended."""
        row = self.k.row(rid, course)
        st = self.state(rid, row) if row else None
        return {**self.card_head(rid, course, row), "value_before": self.value_before(rid, course, row),
                "inferred": inferred, "left_out": left_out or [], "comment": comment,
                "verdict": brief(st.verdict) if st and st.verdict else None,
                "state": st.state if st else None, "history": self.history(st), "links": self.row_links(rid, course)}

    def card_head(self, rid: str, course: str, row: dict | None) -> dict:
        k, row = self.k, row or {}
        r, c = k.rules.get(rid) or {}, k.courses.get(course, {})
        return {"rule": rid, "rule_name": k.names.get(rid, rid), "legend": r.get("property_label") or k.names.get(rid, rid),
                "kind": r.get("kind"), "course": course, "title": c.get("title"),
                "page_stem": row.get("page_stem") or c.get("page_stem"), "url": c.get("url"),
                "key": row.get("key"), "occurrence_key": row.get("occurrence_key"),
                "value": row.get("value"), "status": row.get("status")}

    def value_before(self, rid: str, course: str, row: dict | None) -> dict | None:
        k = self.k
        before = k.row(rid, course, k.base) if k.base is not None else None
        changed = k.base is not None and before is not None and norm(before.get("value")) != norm((row or {}).get("value"))
        return {"version": k.ruleset_before, "value": before.get("value")} if changed else None

    def row_links(self, rid: str, course: str) -> dict:
        links = {"rules": self.rules_link(rid, row=course, by=BY_ANYONE, ext=self.k.ext)}
        links["wrong"] = links["rules"] + "&mark=wrong"
        return links

    def history(self, st) -> list[dict]:
        out = []
        for e in (st.events if st else []):
            b = brief(e)
            out.append({"kind": e["type"], **{k: b[k] for k in ("annotation_id", "verdict", "author", "author_role",
                                                                 "at", "note", "expected", "run_id",
                                                                 "ruleset_version", "run_at")},
                        "after_run": False})
        return out

    def course_brief(self, rid: str, course: str) -> dict:
        """A course in a table (the rest of a set, the courses an answer marks): enough to show it and to post a
        verdict on it that supersedes its current one."""
        k = self.k
        row = k.row(rid, course)
        st = self.state(rid, row) if row else None
        v = st.verdict if st and st.verdict else None
        return {"course": course, "rule": rid, "title": k.courses.get(course, {}).get("title"),
                "value": (row or {}).get("value"), "status": (row or {}).get("status"),
                "occurrence_key": (row or {}).get("occurrence_key"),
                "page_stem": (row or {}).get("page_stem") or k.courses.get(course, {}).get("page_stem"),
                "verdict": v["verdict"] if v else None, "state": st.state if st else None,
                "current": brief(v) if v else None,
                "links": {"rules": self.rules_link(rid, row=course, by=BY_ANYONE, ext=k.ext)}}

    def courses_of(self, ref, rule: str | None) -> tuple[str | None, list[str]]:
        """A set of courses: (its rule, the course codes)."""
        if not isinstance(ref, dict):
            return rule, list(ref)
        rid, want = ref["rule"], ref["verdict"]
        states = ("correct", "changed-since-correct") if want == "correct" else ("wrong", "still-wrong")
        got = []
        for row in (self.k.snap.rows(rid) if self.k.snap and rid in self.k.snap.rules else []):
            st = self.state(rid, row)
            if st and st.state in states and row.get("record_external_identifier"):
                got.append(row["record_external_identifier"])
        return rid, sorted(set(got))

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

    def has_rule(self, rid: str) -> bool:
        """The rule exists in the pinned version and finds values (`rule_type: none` is a property with no rule yet)."""
        r = self.k.rules.get(rid)
        return bool(r) and (r.get("definition") or {}).get("rule_type") != "none"

    def state(self, rid: str, row: dict):
        if self.review is None:
            return None
        if rid not in self._states:
            self._states[rid] = self.review.row_states(rid, self.k.snap.rows(rid))
        return self._states[rid].get(row["key"])

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

    def note_source(self, aid: str) -> dict:
        n = self.k.notes[aid]
        return {"kind": "note", "annotation_id": aid, "author": full(n["author"]), "at": n["at"], "rule": n["rule"],
                "course": n["course"]}

    def rules_link(self, rid: str, **p) -> str:
        return _h(f"{urlquote(self.k.catalog)}/{self.k.cls}/rules/{urlquote(rid)}", p)

    def compare_url(self, a, b, rid: str | None = None) -> str | None:
        if not a or not b:
            return None
        return _h(f"{urlquote(self.k.catalog)}/{self.k.cls}/compare", {"a": a, "b": b, "rule": rid})


def outcome(facts: dict, k: Known) -> str:
    """The band's sentence."""
    if facts["ending"] == "published":
        return _published_outcome(facts, k)
    if facts["ending"] == "needs_you":
        held = [r["rule"] for r in facts.get("rules") or [] if r.get("outcome") == "held"] or k.goals
        what = f" {words([k.names.get(r, r) for r in held])}" if held else ""
        return f"{_decisions(len(facts.get('to_do') or []))} before Claude can publish{what}."
    return f"Claude couldn't finish: {' '.join(str(facts.get('reason', '')).split())}"


def _published_outcome(facts: dict, k: Known) -> str:
    names = k.names
    goals = [r for r in k.goals if r in k.changed_by_run] or sorted(k.changed_by_run)
    v = k.published[-1] if k.published else k.ruleset_after
    out = f"Claude published {words([names.get(r, r) for r in goals])} in v{v}."
    held = held_rules(facts)
    if held:  # a partial publish: say what still waits, so the sentence isn't read as "all done"
        n = len(facts.get("to_do") or [])
        need = _decisions(n) if n else "you"
        out += f" {words([names.get(r, r) for r in held])} {'needs' if len(held) == 1 else 'need'} {need} first."
    return out


def _decisions(n: int) -> str:
    return f"{n} decision{'' if n == 1 else 's'}"


def held_rules(facts: dict) -> list[str]:
    """The rules to improve that Claude held back for a decision."""
    return [r["rule"] for r in facts.get("rules") or [] if r.get("outcome") == "held"]


def _lead_of(card: dict) -> str:
    """A row card's lead sentence in a decision: who marked it what."""
    v = card.get("verdict") or {}
    if v.get("verdict") in ("correct", "wrong"):
        return f"Here is the row {v['author']} marked {v['verdict']}:"
    return "Here is the row this question is about:"


def _set_label(e: dict, verdict: str | None, briefs: list[dict]) -> str:
    if not verdict:
        return e.get("label") or "courses"
    who = _who({(b["current"] or {}).get("author") for b in briefs})
    return f"{who.strip()} marked {verdict}".strip() if who else f"marked {verdict}"


def _others_lead(others: list[dict], label: str) -> str | None:
    if not others:
        return None
    return f"The other {len(others)} courses {label}:" if len(others) > 1 else f"The other course {label}:"


def _effect_owner(opts: list[dict], effects: list[dict]) -> int | None:
    """The answer a to-do's effects belong to: the one that publishes an effect's rule, else the first."""
    effect_rules = {e["rule"] for e in effects}
    return next((j for j, o in enumerate(opts) if effect_rules & set((o.get("then") or {}).get("publish") or [])),
                0 if opts else None)


def _done_text(mark: str, codes: list[str]) -> str | None:
    what = MARK_NAMES[mark]
    if mark not in MARK_EVENTS:
        return None
    return f"{codes[0]} marked {what}" if len(codes) == 1 else f"{len(codes)} courses marked {what}"


def _is_correct(state) -> bool:
    return bool(state) and state.state == "correct"


def _effect_text(name: str, after) -> str:
    if after == "" or after is None:
        return f"{name} becomes empty."
    if isinstance(after, dict) and after.get("source") == "page_url":
        return f"{name} reads the page's address."
    if isinstance(after, str):
        return f"{name} becomes \"{after}\"."
    return f"{name} changes."


def _who(authors: set) -> str:
    """" Jared Diener" when one person made every verdict of a set, else ""."""
    named = {a for a in authors if a}
    return f" {next(iter(named))}" if len(named) == 1 else ""


def _mark_words(do: dict, n: int, names: list[str], rule_name: str) -> str:
    who = names[0] if n == 1 else f"the {n} courses"
    return {"correct": f"mark {who} correct for {rule_name}", "wrong": f"mark {who} wrong for {rule_name}",
            "not_on_page": f"mark {who} \"Not on the page\" for {rule_name}",
            "save_expected": f"save {who}'s expected {rule_name}"}[do["mark"]]


def row_keys(resolved: dict) -> list[tuple[str, str]]:
    """Every (rule, course) the report shows as a row card, in order, once."""
    cards = [x["row"] for x in resolved.get("inferred") or []]
    for t in resolved.get("to_do") or []:
        cards += _decision_cards(t)
    for s in (resolved.get("rules") or []) + (resolved.get("also_changed") or []):
        cards += s["rows"]
    return list(dict.fromkeys((c["rule"], c["course"]) for c in cards))


def _decision_cards(t: dict) -> list[dict]:
    cards = list(t["about"])
    for e in t["evidence"]:
        cards += e.get("rows") or []
        cards += [c for c in e.get("courses") or [] if c.get("rule")]
    for o in t.get("options") or []:
        cards += (o.get("do") or {}).get("courses") or []
    return cards


# =====================================================================================================
# summary.md
# =====================================================================================================
def markdown(r: dict, studio_url: str | None) -> str:
    """The resolved report as Markdown, for Slack and for older Studios: folds become lists, the row's ✓ a link to
    the row."""
    summary = _Markdown(r, studio_url)
    summary.write_header()
    summary.write_inferred()
    summary.write_decisions()
    summary.write_sections()
    summary.write_together()
    summary.write_footer()
    return "\n".join(summary.out).rstrip() + "\n"


class _Markdown:
    def __init__(self, r: dict, studio_url: str | None):
        self.r = r
        self.base = (studio_url or "").split("#")[0] or None
        self.out: list[str] = []
        self.shown: set = {(x["row"]["rule"], x["row"]["course"]) for x in r["inferred"]}

    def write_header(self) -> None:
        r = self.r
        self.out += [f"**{r['outcome']}**", ""]
        self.out += [f"- {f['label']}: {f['text']}" for f in r["facts"]]
        compare = r["ruleset"].get("compare")
        if compare:
            label = f"Compare v{compare['a']} and v{compare['b']}"
            self.out.append(f"- {_md(label, self.url(compare['url']))}")
        self.out.append("")

    def write_inferred(self) -> None:
        if not self.r["inferred"]:
            return
        self.out += ["## Values Claude worked out", ""]
        for x in self.r["inferred"]:
            self.out.append(self.card_line(x["row"]))
            self.out += [f"  - {_source_name(e)}: \"{e['quote']}\"" for e in x["evidence"]]
        self.out.append("")

    def write_decisions(self) -> None:
        if not self.r["to_do"]:
            return
        self.out += ["## What you need to decide", ""]
        for t in self.r["to_do"]:
            self.write_decision(t)

    def write_decision(self, t: dict) -> None:
        """What to decide and why, then the answers, then the evidence (pass 7)."""
        self.out += [f"### {t['ask']}", ""]
        if t.get("why"):
            self.out += [t["why"], ""]
        self.out += [self.option_line(o) for o in t["options"]]
        if not any(o.get("effect") for o in t["options"]):
            self.out += [f"- {e['text']}" for e in t["effect"]]
        self.out.append("")
        for c in t["about"]:
            self.out += self.card_once(c, c.get("lead"))
        for e in t["evidence"]:
            self.write_evidence(e)
        self.out.append("")

    def option_line(self, o: dict) -> str:
        if not o.get("button"):  # a report resolved before pass 7
            return f"- {o['text']}"
        line = f"- **{o['button']}**"
        rest = [x for x in (o.get("effect"), *(o.get("no_rule_yet") or []), (o.get("then") or {}).get("text")) if x]
        if rest:
            line += ". " + " ".join(rest)
        if o.get("link"):
            line += f" {_md('Open in Rules', self.url(o['link']))}"
        return line

    def write_evidence(self, e: dict) -> None:
        if e["kind"] == "quote":
            self.out.append(f"- {_source_name(e)}: \"{e['quote']}\"")
            return
        for c in e["rows"]:
            self.out += self.card_once(c, c.get("lead"))
        if e["courses"]:
            self.out.append(e.get("others_lead") or f"The other {len(e['courses'])}:")
            self.out += [self.course_line(c) for c in e["courses"]]

    def course_line(self, c: dict) -> str:
        mark = {"correct": "marked correct", "wrong": "marked wrong"}.get(c.get("verdict"), "not marked")
        title = f" ({c['title']})" if c.get("title") else ""
        link = (c.get("links") or {}).get("rules")
        return f"- {_md(c['course'], self.url(link))}{title}: {mark}"

    def write_sections(self) -> None:
        for s in self.r["rules"] + self.r["also_changed"]:
            self.out += [f"## {'' if s['goal'] else 'Also changed: '}{s['name']}", ""]
            bits = [x for x in (s.get("now"), s.get("why")) if x]
            if bits:
                self.out += [" ".join(b.strip().rstrip(".") + "." for b in bits), ""]
            if s.get("values_changed"):
                self.out += [self.values_changed_line(s["values_changed"]), ""]
            for c in s["rows"]:
                self.out += self.card_once(c)
            if s["rows"]:
                self.out.append("")

    def values_changed_line(self, vc: dict) -> str:
        label = f"Compare v{vc['base']} and v{vc['published']}"
        compare = f" {_md(label, self.url(vc['compare_url']))}" if vc.get("compare_url") else ""
        return f"Values changed: {vc['text']}.{compare}"

    def write_together(self) -> None:
        if self.r["together"]:
            self.out += ["## Rules that go together", ""]
            self.out += [f"- {words(t['names'])}: \"{t['quote']}\"" for t in self.r["together"]]
            self.out.append("")

    def write_footer(self) -> None:
        if self.r.get("notes"):
            self.out += ["## Notes", "", self.r["notes"], ""]
        if self.url(self.r["links"]["report"]):
            self.out.append(_md("This report", self.url(self.r["links"]["report"])))

    def card_once(self, c: dict, lead: str | None = None) -> list[str]:
        """A row once per report; later mentions point back to it."""
        if (c["rule"], c["course"]) in self.shown:
            return [f"- {c['course']}'s row is shown above."]
        self.shown.add((c["rule"], c["course"]))
        return ([lead] if lead else []) + [self.card_line(c)]

    def card_line(self, c: dict) -> str:
        value = "empty" if c["value"] in (None, "") else f"`{' '.join(str(c['value']).split())[:200]}`"
        line = f"- {_md(c['course'], self.url(c['links']['rules']))}"
        if c.get("title"):
            line += f" ({c['title']})"
        line += f": {value}"
        if c.get("value_before"):
            vb = c["value_before"]
            line += f", was `{' '.join(str(vb['value'] or '').split())[:120]}` in v{vb['version']}"
        if c.get("inferred"):
            inf = c["inferred"]["value"]
            line += f". Claude worked out {'empty' if inf == '' else f'`{inf}`'}: {_md('save it', self.url(c['links']['rules']))}"
        if c.get("comment"):
            line += f". Claude: {c['comment']}"
        return line

    def url(self, h: str | None) -> str | None:
        return f"{self.base}{h}" if self.base and h else None


def _source_name(e: dict) -> str:
    return e["source"].get("author") or e["source"].get("course")


# =====================================================================================================
# The last try, kept for the report
# =====================================================================================================
def last_try_doc(ev: dict, base_ruleset: int | None, published: int | None) -> dict:
    """What `rule try` / `rule publish` keep for the report: the whole suite, values changed per rule, the inferred
    values the draft produces, and per rule the annotated courses by outcome."""
    cards = [_courses_by_outcome(c) for c in ev["cards"]]
    s = ev.get("suite") or {}
    return {"base_ruleset": base_ruleset, "published": published, "totals": ev["totals"], "cards": cards,
            "suite": {k: s[k] for k in ("rules", "golden", "now_right", "inferred", "got_worse", "regressions")}
            | {"line": (ev.get("suite_lines") or [""])[0]} if s else None,
            "values_changed": s.get("changed") or {}, "inferred": ev.get("inferred") or [],
            "inferred_values": ev.get("inferred_values") or {}}


def _courses_by_outcome(card: dict) -> dict:
    by: dict[str, list[str]] = {"fixed": [], "still_wrong": [], "newly_wrong": []}
    for r in card["annotated_rows"]:
        key = {"fixed": "fixed", "still wrong": "still_wrong", "newly wrong": "newly_wrong"}.get(r["outcome"])
        if key:
            by[key].append(r.get("record_external_identifier") or r["page_stem"])
    return {"rule_id": card["rule_id"], **{k: sorted(set(v)) for k, v in by.items()}}


# =====================================================================================================
# Names, words and text
# =====================================================================================================
def rule_names(rules: dict[str, dict]) -> dict[str, str]:
    """rule id → the name the Studio shows (the property label; a page rule's or locator's title)."""
    from .server.routes_review import rule_title

    return {rid: rule_title(r, rules)[0] for rid, r in rules.items()}


def full(name: str | None) -> str | None:
    """A reviewer's full name ("Jared" wrote the first events): the report names people one way everywhere."""
    return FULL_NAMES.get(name, name) if name else name


def brief(e: dict | None) -> dict | None:
    """An event as the report shows it (`_event_brief`), its author's full name."""
    from .server.routes_review import _event_brief

    b = _event_brief(e)
    return b and {**b, "author": full(b["author"])}


def words(items: list[str]) -> str:
    """"A", "A and B", "A, B and C"."""
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def sentences(s: str) -> int:
    """How many sentences: runs of text ending in . ! or ? (a last one without a stop counts too). Dots inside
    words (ceterms:inCatalog, 1.0, avc.edu) don't end a sentence."""
    return len([x for x in re.split(r"(?<=[.!?])\s+", (s or "").strip()) if x.strip()])


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
            stem = next((o["page_stem"] for o in snap.occurrences.values() if o.get("record_external_identifier") == course), None)
            try:
                cache[course] = page_text(ctx.page_path(stem).read_bytes()) if stem else None
            except (FileNotFoundError, OSError):
                cache[course] = None
        return cache[course]
    return read


def _text(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _h(path: str, params: dict | None = None) -> str:
    q = urlencode({a: b for a, b in (params or {}).items() if b not in (None, "")})
    return f"#/c/{path}" + (f"?{q}" if q else "")


def _md(label: str, url: str | None) -> str:
    return f"[{label.replace('[', '(').replace(']', ')')}]({url})" if url else label
