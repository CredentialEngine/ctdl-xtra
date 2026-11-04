"""The read model shared by the server, `rule list/show/annotations`, the prompt and Compare.

`Snapshot` = one extraction loaded in memory (rules of its ruleset, occurrences, matches, signals, page labels).
`Review` = a snapshot + the annotation log: each row's verdict carried forward to the current version, history
signals (spec §8, computed when read, never stored), rule status (spec §4.3) and the row order of the Rules tab.

Rows, per rule kind (spec §7.2):
- property rule: one per match (a course the record locator found), key = occurrence_key;
- record locator: one per occurrence, key = occurrence_key;
- page rule: one per page the rule recognised, key = page_stem.

How an old verdict applies to the current row (spec §4.3 "old verdicts carry forward through the comparison"):
- seen on this rule version, or the value is unchanged since → it applies as given;
- `wrong` and the value changed: **fixed** when it now equals the expected text, else **still wrong**;
- `correct` and the value changed: **changed since correct** (needs a fresh look; not counted as wrong).
Annotations re-attach through `course_key` + page when the occurrence key changed (a changed locator, D3).
A row's `events` are every verdict and comment on it, whichever ruleset version they were made in: the "Annotated by"
filter of the Rules and Records tabs (`annotations`, `annotated_match`) and the Sample drawer's "Annotated in" stratum.

Human-reviewed (Evals spec §4.3): only a subject matter expert's verdict makes a value human-reviewed (`RowState.human`).
An engineer's ✓ is recorded and shown as engineer-checked, waiting for an expert; their ✕ counts against the rule
like anyone's. An expert's later verdict supersedes an engineer's; an engineer's later verdict never supersedes an
expert's (the expert's ✓ stands beside it, so the value stays human-reviewed after an engineer's ✓).
"""

from __future__ import annotations

import hashlib
import re
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from . import facets, layout, model, strata
from .context import Ctx
from .log import FULL_NAMES, AnnotationLog
from .profiles import role_of, roles
from .signals import SEVERITY_RANK

OPEN = {"wrong", "still-wrong", "missing"}
#: Row states where a person confirmed the value itself: marked it correct (and it hasn't changed since), or marked
#: it wrong and selected the right text, which the value now is. From an expert, that makes the value human-reviewed.
HUMAN_STATES = ("correct", "fixed")
#: The "Annotated by" filter's verdict switch: ✓ correct · ✕ wrong · note (a comment or a question for the institution).
VERDICT_KIND = {"correct": "correct", "fixed": "correct", "wrong": "wrong", "still-wrong": "wrong", "missing": "wrong",
                "question": "note"}
#: "Annotated by" choices besides a person's name: nobody yet, an engineer's check waiting for an expert, any subject
#: matter expert, any engineer.
NOBODY, WAITING, EXPERTS, ENGINEERS = "nobody", "waiting", "experts", "engineers"


#: Rule statuses, see Review.rule_status. Cleared when a profile's role changes (Loader.forget_reviews).
STATUS_CACHE: dict[tuple, dict] = {}


def norm(v: str | None) -> str:
    return re.sub(r"\s+", " ", v or "").strip()


class _Recent(dict):
    """A per-rule cache that keeps the `RULES_KEPT` most recently used rules. Opening the Rules tab works out every
    rule's status, so these used to hold every rule's rows and row states for the life of the snapshot: on WVU, ~1M
    row dicts in the extraction and as many in its parent."""

    RULES_KEPT = 8

    def __init__(self) -> None:
        super().__init__()
        # Request threads share a Review: unlocked, two of them could pop the same key (KeyError) or evict it twice.
        self._lock = threading.Lock()

    def __getitem__(self, key):
        with self._lock:
            value = super().pop(key)
            super().__setitem__(key, value)  # most recent last
            return value

    def get(self, key, default=None):
        """The value, marked most recent, or `default`. Callers use this instead of `in` then `[]`: another thread could
        evict the rule between the two."""
        with self._lock:
            if not super().__contains__(key):
                return default
            value = super().pop(key)
            super().__setitem__(key, value)
            return value

    def __setitem__(self, key, value) -> None:
        with self._lock:
            super().pop(key, None)
            super().__setitem__(key, value)
            while len(self) > self.RULES_KEPT:
                super().__delitem__(next(iter(self)))


def _shared(rows: list[dict]) -> list[dict]:
    """A table's rows with one string object per distinct value. `to_pylist` makes a new str per cell, so WVU's
    419k matches carried 419k copies of a few dozen rule ids, of each occurrence key and css path, and so on."""
    seen: dict[str, str] = {}
    for row in rows:
        for k, v in row.items():
            if type(v) is str:
                row[k] = seen.setdefault(v, v)
    return rows


class Snapshot:
    """One extraction, in memory. Immutable, so it is cached for the life of the process."""

    def __init__(self, ctx: Ctx, ext: str, tables: dict | None = None, ruleset: dict | None = None,
                 rules: dict | None = None, meta: dict | None = None):
        """An extraction on storage (`ext`), or an unwritten one (`tables` + `ruleset` + `rules`, e.g. a draft)."""
        self.ctx, self.ext = ctx, ext
        self.meta = meta if meta is not None else ctx.extraction_meta(ext)
        self._rows: dict[str, list[dict]] = _Recent()
        self._course_lines: dict[str, str] = {}  # occurrence_key → course_line(...)
        self._spread: dict[str, tuple] = {}  # rule_id → strata.groups(...), see Review.spread_groups
        self.ruleset_version = self.meta.get("ruleset_version")
        if rules is None:
            self.ruleset, self.rules = ctx.ruleset_rules(self.ruleset_version)
        else:
            self.ruleset, self.rules = ruleset, rules
        self.settings = self.ruleset["settings"]
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=5) as pool:  # five downloads at once on a cold Azure cache
            pages_f = pool.submit(ctx.pages)
            if tables is None:
                futures = {name: pool.submit(lambda n=name: ctx.table(ext, n).to_pylist())
                           for name in layout.EXTRACTION_TABLES}
                tables = {name: _shared(f.result()) for name, f in futures.items()}
            pages = pages_f.result()
        self.page = {p["page_stem"]: p for p in pages}
        self.occurrences = {o["occurrence_key"]: o for o in tables["occurrences"]}
        self.matches_by_rule: dict[str, list[dict]] = defaultdict(list)
        self.matches_by_occ: dict[str, dict[str, dict]] = defaultdict(dict)  # a rule's first value on a course
        self.items_by_occ: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))  # all of them
        full_paths: dict[tuple, str] = {}  # one string per (course, value) css path pair, not one per match
        for m in sorted(tables["matches"], key=lambda x: (x["rule_id"], x["occurrence_key"], x["value_index"])):
            m = dict(m)
            o = self.occurrences[m["occurrence_key"]]
            m["course_key"] = o["course_key"]
            k = (o["css_path"], m["css_path"])
            if k not in full_paths:
                full_paths[k] = model.full_css_path(*k)
            m["full_css_path"] = full_paths[k]
            self.matches_by_rule[m["rule_id"]].append(m)
            self.matches_by_occ[m["occurrence_key"]].setdefault(m["rule_id"], m)
            self.items_by_occ[m["occurrence_key"]][m["rule_id"]].append(m)
        self.occ_by_locator: dict[str, list[dict]] = defaultdict(list)
        for o in self.occurrences.values():
            self.occ_by_locator[o["locator_rule_id"]].append(o)
        self.labels_by_rule: dict[str, list[dict]] = defaultdict(list)
        self.matched_pages: dict[str, set] = defaultdict(set)
        for lb in tables["page_labels"]:
            if lb["matched"]:
                self.labels_by_rule[lb["rule_id"]].append(lb)
                self.matched_pages[lb["page_stem"]].add(lb["rule_id"])
        self.signals_by_target: dict[tuple, list[dict]] = defaultdict(list)
        self.page_signals: dict[str, list[dict]] = defaultdict(list)
        self.signal_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for s in tables["signals"]:
            rid = s["rule_id"] or ""
            self.signal_counts[rid][s["signal"]] += 1
            if s["target_kind"] == "match":
                self.signals_by_target[(s["rule_id"], s["occurrence_key"])].append(s)
            elif s["target_kind"] == "occurrence":
                self.signals_by_target[(s["rule_id"], s["occurrence_key"])].append(s)
            else:
                self.page_signals[s["page_stem"]].append(s)
        # A course's display line: "GEOG 222 - Cartography for …" from the code + name rules of its locator.
        self.code_rule = {loc: model.code_rule_for(loc, self.rules, self.settings)
                          for loc, r in self.rules.items() if r["kind"] == "locator"}
        self.name_rule = {}
        for loc in self.code_rule:
            self.name_rule[loc] = next((rid for rid, r in sorted(self.rules.items()) if r["kind"] == "property"
                                        and r["definition"]["locator"] == loc
                                        and r.get("ctdl_property") == "ceterms:name"), None)

    # -- rows ---------------------------------------------------------------------------------------------
    def course_line(self, occ_key: str) -> str:
        """Kept per course: every rule's rows on it share the one string."""
        if occ_key not in self._course_lines:
            self._course_lines[occ_key] = self._course_line(occ_key)
        return self._course_lines[occ_key]

    def _course_line(self, occ_key: str) -> str:
        o = self.occurrences[occ_key]
        ms = self.matches_by_occ[occ_key]
        code = (ms.get(self.code_rule.get(o["locator_rule_id"])) or {}).get("value")
        name = (ms.get(self.name_rule.get(o["locator_rule_id"])) or {}).get("value")
        return " - ".join(x for x in (code, name) if x)

    def rows(self, rule_id: str) -> list[dict]:
        rows = self._rows.get(rule_id)
        if rows is None:
            self._rows[rule_id] = rows = self._build_rows(rule_id)
        return rows

    def _build_rows(self, rule_id: str) -> list[dict]:
        rule = self.rules[rule_id]
        out = []
        if rule["kind"] == "property":
            if rule["definition"].get("rule_type") == "none":  # no rule yet: a row per course, to annotate (§4.6)
                for o in self.occ_by_locator.get(rule["definition"]["locator"], []):
                    out.append({"key": o["occurrence_key"], "occurrence_key": o["occurrence_key"],
                                "course_key": o["course_key"], "page_stem": o["page_stem"], "value": None,
                                "status": "none", "css_path": None, "char_start": None, "char_end": None,
                                "occurrence_css_path": o["css_path"],
                                "context": self.course_line(o["occurrence_key"]), "signals": []})
                return out
            is_list = bool(rule["definition"].get("multiple"))
            for m in self.matches_by_rule.get(rule_id, []):
                if m["value_index"]:
                    continue  # a list: one row per course, its items below
                o = self.occurrences[m["occurrence_key"]]
                row = {"key": m["occurrence_key"], "occurrence_key": m["occurrence_key"],
                       "course_key": o["course_key"], "page_stem": m["page_stem"], "value": m["value"],
                       "status": m["status"], "css_path": m["full_css_path"], "char_start": m["char_start"],
                       "char_end": m["char_end"], "occurrence_css_path": o["css_path"],
                       "context": self.course_line(m["occurrence_key"]),
                       "signals": self.signals_by_target.get((rule_id, m["occurrence_key"]), [])}
                if is_list:
                    found = [x for x in self.items_by_occ[m["occurrence_key"]][rule_id] if x["status"] == "found"]
                    row["items"] = [{"value_index": x["value_index"], "value": x["value"],
                                     "css_path": x["full_css_path"], "char_start": x["char_start"],
                                     "char_end": x["char_end"]} for x in found]
                    row["value"] = "\n".join(x["value"] for x in found) if found else None
                out.append(row)
        elif rule["kind"] == "locator":
            for o in self.occ_by_locator.get(rule_id, []):
                sig = list(self.signals_by_target.get((rule_id, o["occurrence_key"]), []))
                sig += [s for s in self.page_signals.get(o["page_stem"], []) if s["rule_id"] == rule_id]
                out.append({"key": o["occurrence_key"], "occurrence_key": o["occurrence_key"],
                            "course_key": o["course_key"], "page_stem": o["page_stem"],
                            "value": self.course_line(o["occurrence_key"]) or None, "status": "found",
                            "css_path": o["css_path"], "char_start": None, "char_end": None,
                            "occurrence_css_path": o["css_path"], "locator_index": o["locator_index"],
                            "context": self.page[o["page_stem"]]["title"], "signals": sig})
        else:
            stems = [lb["page_stem"] for lb in self.labels_by_rule.get(rule_id, [])]
            for stem in stems:
                p = self.page[stem]
                out.append({"key": stem, "occurrence_key": None, "course_key": None, "page_stem": stem,
                            "value": p["title"], "status": "found", "css_path": None, "char_start": None,
                            "char_end": None, "occurrence_css_path": None, "context": p["url"],
                            "signals": [s for s in self.page_signals.get(stem, []) if s["rule_id"] == rule_id]})
        return out

    def unclassified_pages(self) -> list[dict]:
        """Pages no page rule recognised although they name many course codes (for "Add a page this rule missed")."""
        return [{"page_stem": stem, "signals": sigs} for stem, sigs in self.page_signals.items()
                if any(s["signal"] == "unclassified-page-with-codes" for s in sigs)]

    def fill(self, rule_id: str) -> dict:
        rule = self.rules[rule_id]
        if rule["kind"] != "property":
            n = len(self.rows(rule_id))
            return {"rows": n, "found": n}
        if rule["definition"].get("rule_type") == "none":
            return {"rows": len(self.occ_by_locator.get(rule["definition"]["locator"], [])), "found": 0}
        ms = [m for m in self.matches_by_rule.get(rule_id, []) if not m["value_index"]]
        return {"rows": len(ms), "found": sum(1 for m in ms if m["status"] == "found")}

    def values(self, rule_id: str) -> int:
        """Values a rule found: a list rule's items each count."""
        return sum(1 for m in self.matches_by_rule.get(rule_id, []) if m["status"] == "found")


@dataclass
class RowState:
    state: str | None = None          # correct | wrong | fixed | still-wrong | changed-since-correct | question | missing
    verdict: dict | None = None       # the event it comes from
    reattached: bool = False
    comments: list = field(default_factory=list)
    events: list = field(default_factory=list)   # every live verdict and comment on the row, oldest first
    history: list = field(default_factory=list)  # history signals: [{"signal", "severity", "detail"}]
    role: str | None = None           # the verdict's author's role (sme | engineer)
    human: dict | None = None         # the expert's verdict that makes the value human-reviewed
    checked: dict | None = None       # the latest engineer's ✓ on the row (the check an expert confirms)
    items: dict = field(default_factory=dict)          # a list's item value (normalized) → ItemState
    missing_items: list = field(default_factory=list)  # items marked missing that the rule still doesn't find

    @property
    def engineer_checked(self) -> bool:
        """Confirmed by someone who isn't an expert: waiting for an expert, still approved by its rule."""
        return self.state in HUMAN_STATES and self.human is None and self.role != "sme"


@dataclass
class ItemState:
    """One item of a list row (property-rules spec §4.4): verdicts attach to (rule, occurrence, value text)."""
    state: str | None = None     # correct | wrong | fixed (marked wrong, now gone from the list)
    verdict: dict | None = None
    human: dict | None = None    # the expert's ✓ that makes the item human-reviewed


class Review:
    """A snapshot (+ optional parent snapshot) and the annotation events."""

    def __init__(self, snap: Snapshot, events: list[dict], parent: Snapshot | None = None,
                 roles: dict[str, str] | None = None):
        self.snap, self.events, self.parent = snap, events, parent
        self.roles = roles or {}  # name → role (profiles.json), for events without author_role
        self.by_id = by_id = {e["annotation_id"]: e for e in events}

        def supersedes(e: dict) -> bool:  # an engineer's verdict doesn't take an expert's away (§4.3)
            old = by_id.get(e["supersedes"])
            return old is None or old["type"] != "verdict" or self.role(old) != "sme" or self.role(e) == "sme"
        superseded = {e["supersedes"] for e in events if e.get("supersedes") and supersedes(e)}
        self.live = [e for e in events if e["annotation_id"] not in superseded]
        self._states: dict[str, dict] = _Recent()  # rule_id → row states of snap.rows(rule_id) (events are fixed per Review)
        self._annotations: dict[str, dict] = _Recent()  # rule_id → Review.annotations(...)
        self._facets: dict[str, list[dict]] = _Recent()  # rule_id → facets.dimensions(...), see Review.facet_dims
        self._by_rule: dict[str, list[str]] = defaultdict(list)  # rule_id → its live events' ids (the status key)
        for e in self.live:
            if e["target"].get("rule_id"):
                self._by_rule[e["target"]["rule_id"]].append(e["annotation_id"])

    # -- verdicts on rows ------------------------------------------------------------------------------
    def _target_key(self, e: dict) -> tuple:
        t = e["target"]
        if t["kind"] in ("match", "occurrence"):
            return (t.get("rule_id"), t.get("occurrence_key"))
        return (t.get("rule_id"), t.get("page_stem"))

    def discussion(self) -> dict:
        """Comments on a whole rule or on the ruleset (the Rules tab sidebar), oldest first:
        {"ruleset": [event, …], "rules": {rule_id: [event, …]}}."""
        talk = sorted((e for e in self.live if e["type"] == "comment" and e["target"]["kind"] in ("rule", "ruleset")),
                      key=lambda e: e["at"])
        rules: dict[str, list[dict]] = defaultdict(list)
        for e in talk:
            if e["target"]["kind"] == "rule":
                rules[e["target"]["rule_id"]].append(e)
        return {"ruleset": [e for e in talk if e["target"]["kind"] == "ruleset"], "rules": dict(rules)}

    def role(self, e: dict) -> str | None:
        return role_of(e, self.roles)

    def verdicts_for(self, rule_id: str) -> dict:
        """Latest verdict, latest expert's verdict (`expert`), comments and every verdict or comment (`all`) per
        target of this rule, keyed by occurrence_key / page_stem."""
        latest: dict = {}
        expert: dict = {}
        comments = defaultdict(list)
        every = defaultdict(list)
        for e in sorted(self.live, key=lambda x: x["at"]):
            t = e["target"]
            if t.get("rule_id") != rule_id or t["kind"] in ("rule", "ruleset"):  # whole-rule talk: see discussion()
                continue
            k = self._target_key(e)[1]
            if t.get("item"):  # a list item's verdict: see item_events
                continue
            if e["type"] == "verdict":
                latest[k] = e
                if self.role(e) == "sme":
                    expert[k] = e
            elif e["type"] == "comment":
                comments[k].append(e)
            else:
                continue
            every[k].append(e)
        return {"latest": latest, "expert": expert, "comments": comments, "all": every}

    def item_events(self, rule_id: str) -> dict[tuple, list[dict]]:
        """Verdicts on a list rule's items, oldest first, per (course_key or occurrence, page)."""
        out: dict[tuple, list[dict]] = defaultdict(list)
        for e in sorted(self.live, key=lambda x: x["at"]):
            t = e["target"]
            if e["type"] == "verdict" and t.get("item") and t.get("rule_id") == rule_id:
                out[(t.get("course_key") or t.get("occurrence_key"), t.get("page_stem"))].append(e)
        return out

    def _item_states(self, rule_id: str, row: dict, events: list[dict], st: RowState) -> None:
        present = {norm(i["value"]) for i in row.get("items") or []}
        for e in events:
            if e["verdict"] == "missing":
                continue
            v = norm(e["target"].get("value_seen"))
            item = st.items.setdefault(v, ItemState())
            item.verdict = e
            if e["verdict"] == "correct":
                item.state = "correct" if v in present else None
                if self.role(e) == "sme" and v in present:
                    item.human = e
            elif e["verdict"] == "wrong":
                item.state = "wrong" if v in present else "fixed"
        missing: dict[str, dict] = {}
        for e in events:
            if e["verdict"] == "missing":
                missing[norm((e.get("expected") or {}).get("text"))] = e
            elif e["verdict"] == "correct":
                missing.pop(norm(e["target"].get("value_seen")), None)
        st.missing_items = [e for text, e in missing.items() if text and text not in present]
        st.items = {k: v for k, v in st.items.items() if v.state is not None}

    def reviewed_elsewhere(self, rule_id: str, rows: list[dict], states: dict[str, RowState]) -> dict[str, list[str]]:
        """Rows of this rule nobody has reviewed yet (no verdict, no comment) whose record someone reviewed in
        another rule: row key → those rules. A record matches by its course, or by its page (page-rule verdicts)."""
        by_course: dict[str, set[str]] = defaultdict(set)
        by_page: dict[str, set[str]] = defaultdict(set)
        for e in self.live:
            t = e["target"]
            if e["type"] not in ("verdict", "comment") or not t.get("rule_id") or t["rule_id"] == rule_id:
                continue
            if t.get("course_key"):
                by_course[t["course_key"]].add(t["rule_id"])
            elif t.get("page_stem"):
                by_page[t["page_stem"]].add(t["rule_id"])
        out = {}
        for r in rows:
            st = states[r["key"]]
            if st.state is not None or st.comments:
                continue
            other = by_course.get(r.get("course_key") or "", set()) | by_page.get(r["page_stem"], set())
            if other:
                out[r["key"]] = sorted(other)
        return out

    def row_states(self, rule_id: str, rows: list[dict]) -> dict[str, RowState]:
        if rows is self.snap.rows(rule_id):
            states = self._states.get(rule_id)
            if states is None:
                self._states[rule_id] = states = self._row_states(rule_id, rows)
            return states
        return self._row_states(rule_id, rows)

    def _row_states(self, rule_id: str, rows: list[dict]) -> dict[str, RowState]:
        rule = self.snap.rules[rule_id]
        v = self.verdicts_for(rule_id)
        latest, expert, comments, every = v["latest"], v["expert"], v["comments"], v["all"]
        by_course_page, expert_by_course_page = {}, {}
        for found, into in ((latest, by_course_page), (expert, expert_by_course_page)):
            for e in found.values():
                t = e["target"]
                if t.get("course_key"):
                    into[(t["course_key"], t.get("page_stem"))] = e
        # comments and earlier verdicts re-attach the same way, so an older ruleset's annotations stay on the row
        talk_by_course_page: dict[tuple, list] = defaultdict(list)
        every_by_course_page: dict[tuple, list] = defaultdict(list)
        keys = {r["key"] for r in rows}
        for k, es in every.items():
            if k in keys:
                continue
            for e in es:
                t = e["target"]
                if t.get("course_key"):
                    cp = (t["course_key"], t.get("page_stem"))
                    every_by_course_page[cp].append(e)
                    if e["type"] == "comment":
                        talk_by_course_page[cp].append(e)
        item_events = self.item_events(rule_id) if rule["kind"] == "property" \
            and rule["definition"].get("multiple") else {}
        parent_values = {}
        if self.parent is not None and rule_id in self.parent.rules:
            parent_values = {r["key"]: r["value"] for r in self.parent.rows(rule_id)}
        out = {}
        for row in rows:
            st = RowState()
            e = latest.get(row["key"])
            if e is None and row.get("course_key"):
                e = by_course_page.get((row["course_key"], row["page_stem"]))
                st.reattached = e is not None
            st.comments = comments.get(row["key"], [])
            st.events = every.get(row["key"], [])
            if row.get("course_key"):
                cp = (row["course_key"], row["page_stem"])
                st.comments = st.comments + talk_by_course_page.get(cp, [])
                st.events = sorted(st.events + every_by_course_page.get(cp, []), key=lambda x: x["at"])
            if e is not None:
                st.verdict = e
                st.state = self._carry(rule, e, row)
                st.role = self.role(e)
                x = e if st.role == "sme" else expert.get(row["key"]) or (
                    expert_by_course_page.get((row["course_key"], row["page_stem"])) if row.get("course_key") else None)
                if x is not None and st.state not in OPEN and self._carry(rule, x, row) in HUMAN_STATES:
                    st.human = x
            # the engineer's check: still on the row, or the one an expert's Confirm superseded
            checks = [*([self.by_id.get(st.human.get("supersedes"))] if st.human and st.human.get("supersedes") else []),
                      *st.events]
            st.checked = max((x for x in checks if x and x["type"] == "verdict" and x["verdict"] == "correct"
                              and self.role(x) != "sme"), key=lambda x: x["at"], default=None)
            if item_events:
                es = item_events.get((row.get("course_key") or row["occurrence_key"], row["page_stem"]), [])
                if es:
                    self._item_states(rule_id, row, es, st)
            if self.parent is not None:
                if row["key"] not in parent_values and parent_values:
                    st.history.append(_h("new-in-version", f"not in {self.parent.ext}"))
            if st.state in ("wrong", "still-wrong", "fixed"):
                st.history.append(_h("previously-wrong", "marked wrong"))
            elif st.state == "correct":
                st.history.append(_h("previously-correct", "marked correct"))
            elif st.state == "changed-since-correct":
                st.history.append(_h("changed-since-correct", "the value changed since it was marked correct"))
            out[row["key"]] = st
        return out

    def _carry(self, rule: dict, e: dict, row: dict) -> str:
        verdict = e["verdict"]
        if verdict == "question":
            return "question"
        t = e["target"]
        same_version = t.get("rule_version_seen") == rule["version"]
        if rule["kind"] != "property":
            return verdict  # page / locator verdicts: their rows exist only where the rule still finds them
        unchanged = norm(t.get("value_seen")) == norm(row["value"])
        if same_version or unchanged:
            return verdict
        if verdict == "wrong":
            expected = (e.get("expected") or {}).get("text")
            return "fixed" if expected is not None and norm(expected) == norm(row["value"]) else "still-wrong"
        return "changed-since-correct"

    def missing_events(self, rule_id: str) -> list[dict]:
        """`missing` verdicts on a record locator / page rule (no row: the rule didn't find it), still open."""
        rule = self.snap.rules[rule_id]
        out = []
        latest = self.verdicts_for(rule_id)["latest"]
        for e in latest.values():
            if e["verdict"] != "missing":
                continue
            t = e["target"]
            if rule["kind"] == "page" and rule_id in self.snap.matched_pages.get(t.get("page_stem"), set()):
                continue  # the page is recognised now
            if rule["kind"] == "locator":
                css = (e.get("expected") or {}).get("css_path") or ""
                stem = t.get("page_stem")
                if css and any(o["page_stem"] == stem and _overlaps(css, o["css_path"])
                               for o in self.snap.occ_by_locator.get(rule_id, [])):
                    continue  # an occurrence covers it now
            out.append(e)
        return out

    # -- rule status (spec §4.3) --------------------------------------------------------------------------
    def rule_status(self, rule_id: str, states: dict[str, RowState] | None = None) -> dict:
        """Cached per (extraction, parent, the rule's own live events) across Reviews: a verdict recomputes only
        its own rule's status (property-rules spec §4.14)."""
        key = (self.snap.ctx.root.uri, self.snap.ctx.catalog, self.snap.ext,
               self.parent.ext if self.parent is not None else None, rule_id, tuple(self._by_rule.get(rule_id, ())))
        got = STATUS_CACHE.get(key)
        if got is None:
            got = STATUS_CACHE[key] = self._rule_status(rule_id, states)
            if len(STATUS_CACHE) > 20_000:
                STATUS_CACHE.clear()
        return dict(got)

    def _rule_status(self, rule_id: str, states: dict[str, RowState] | None = None) -> dict:
        rule = self.snap.rules[rule_id]
        last = None
        for e in sorted(self.live, key=lambda x: x["at"]):
            t = e["target"]
            if e["type"] in ("approve", "reopen") and t.get("kind") == "rule" and t.get("rule_id") == rule_id \
                    and t.get("rule_version_seen") == rule["version"]:
                last = e
        if states is None:
            states = self.row_states(rule_id, self.snap.rows(rule_id))
        open_rows = sum(1 for s in states.values() if s.state in OPEN) \
            + sum(1 for s in states.values() for i in s.items.values() if i.state == "wrong") \
            + sum(len(s.missing_items) for s in states.values())
        open_missing = len(self.missing_events(rule_id))
        reviewed = sum(1 for s in states.values() if s.state is not None or s.items)
        if last is not None and last["type"] == "approve":
            status = "approved"
        elif open_rows or open_missing:
            status = "needs work"
        else:
            status = "in review"
        questions = sum(1 for s in states.values() if s.state == "question")
        return {"status": status, "reviewed": reviewed, "total": len(states), "open_wrong": open_rows,
                "open_missing": open_missing, "questions": questions,
                "approved_by": last["author"] if status == "approved" else None,
                "approved_at": last["at"] if status == "approved" else None}

    # -- ordering (spec §8) --------------------------------------------------------------------------------
    # History signals that move a row up in the Rules tab. `previously-correct` doesn't: rows Jared already
    # confirmed fade back instead (spec §7.2); Compare orders by every history signal (A4.1).
    RULES_TAB_HISTORY = {"previously-wrong", "changed-since-correct", "new-in-version"}

    def ordered(self, rule_id: str, seed: str = "golden-datasets", mix_every: int = 5,
                history: set[str] | None = None) -> list[tuple[dict, RowState]]:
        """Review order of the Rules tab:
        1. discussed: rows with a comment or an "unsure" verdict that nobody has marked correct, newest first, so
           teammates see what others asked about;
        2. rows with signals, by severity then signal count, with every `mix_every`-th row taken from
        3. a spread sample of the rest (strata.py: length buckets, distinct values or shapes, pages, subjects)."""
        rows = self.snap.rows(rule_id)
        states = self.row_states(rule_id, rows)
        keep = self.RULES_TAB_HISTORY if history is None else history
        _, label, order = self.spread_groups(rule_id)

        def sev(row) -> tuple[int, int]:
            sig = row["signals"] + [h for h in states[row["key"]].history if h["signal"] in keep]
            if not sig:
                return (0, 0)
            return (max(SEVERITY_RANK[s["severity"]] for s in sig), len(sig))

        def rnd(row) -> str:
            return hashlib.sha1(f"{seed}:{row['key']}".encode()).hexdigest()

        def last_talk(row) -> str:
            st = states[row["key"]]
            ats = [c["at"] for c in st.comments] + ([st.verdict["at"]] if st.state == "question" else [])
            return max(ats, default="")

        discussed = [r for r in rows if states[r["key"]].state != "correct"
                     and (states[r["key"]].comments or states[r["key"]].state == "question")]
        talked = {r["key"] for r in discussed}
        discussed.sort(key=last_talk, reverse=True)
        rest = [r for r in rows if r["key"] not in talked]
        flagged = sorted((r for r in rest if sev(r)[0] > 0), key=lambda r: (-sev(r)[0], -sev(r)[1], rnd(r)))
        sample = strata.spread([r for r in rest if sev(r)[0] == 0], label, order, rnd)
        out, si = list(discussed), 0
        for i, r in enumerate(flagged):
            if i and i % (mix_every - 1) == 0 and si < len(sample):
                out.append(sample[si])
                si += 1
            out.append(r)
        out.extend(sample[si:])
        return [(r, states[r["key"]]) for r in out]

    def facet_dims(self, rule_id: str) -> list[dict]:
        """facets.dimensions over this rule's rows, review states included. Fixed per Review."""
        dims = self._facets.get(rule_id)
        if dims is None:
            snap = self.snap
            kind = snap.rules[rule_id]["kind"]
            rows = snap.rows(rule_id)
            states = self.row_states(rule_id, rows)
            on_page = Counter(o["page_stem"] for o in snap.occurrences.values()) if kind != "property" else None
            ruleset_of = {e["extraction"]: e["ruleset_version"] for e in snap.ctx.extractions()}
            items = [facets.item(r, snap.page[r["page_stem"]]["url"], state=states[r["key"]].state,
                                 **self._annotated(states[r["key"]], ruleset_of),
                                 **({"on_page": on_page.get(r["page_stem"], 0)} if on_page is not None else {}))
                     for r in rows]
            self._facets[rule_id] = dims = facets.dimensions(kind, items)
        return dims

    @staticmethod
    def _annotated(st: RowState, ruleset_of: dict[str, int]) -> dict:
        """The ruleset versions people marked or commented on the row in (the Studio's own events don't count)."""
        es = [e for e in st.events if not e["author"].startswith("golden-datasets")]
        return {"annotated_in": sorted({ruleset_of.get(e["target"].get("extraction_seen")) for e in es},
                                       key=lambda v: (v is None, v or 0))}

    def annotations(self, rule_id: str) -> dict[str, dict]:
        """The "Annotated by" filter's data, per row key: `people` {name: {"kinds": [correct|wrong|note], "at", "role"}} (their
        latest verdict, and note when they commented; the Studio's own events don't count; first names count as the
        full name), `kinds` (the row's: its verdict, note when discussed) and `waiting` (engineer-checked). Fixed per
        Review."""
        cached = self._annotations.get(rule_id)
        if cached is None:
            rows = self.snap.rows(rule_id)
            states = self.row_states(rule_id, rows)
            out = {}
            for r in rows:
                st = states[r["key"]]
                people: dict[str, dict] = {}
                for e in st.events:  # oldest first: the latest verdict wins
                    if e["author"].startswith("golden-datasets"):
                        continue
                    p = people.setdefault(FULL_NAMES.get(e["author"], e["author"]), {"verdict": None, "note": False})
                    if e["type"] == "verdict" and e["verdict"] != "question":
                        p["verdict"] = VERDICT_KIND.get(e["verdict"])
                    else:
                        p["note"] = True
                    p["at"] = e["at"]
                kinds = {VERDICT_KIND[st.state]} if st.state in VERDICT_KIND else set()
                out[r["key"]] = {
                    "people": {n: {"kinds": [k for k in (p["verdict"], "note" if p["note"] else None) if k],
                                   "at": p["at"], "role": self.roles.get(n) or "engineer"} for n, p in people.items()},
                    "kinds": sorted(kinds | ({"note"} if st.comments else set())), "waiting": st.engineer_checked}
            self._annotations[rule_id] = cached = out
        return cached

    def people(self) -> dict:
        """The "Annotated by" dropdown: every profile and everyone who annotated a value, with their role and how many
        property values they annotated, and how many values an engineer checked are waiting for an expert."""
        values: Counter = Counter()
        waiting = experts = engineers = 0
        for rid, r in self.snap.rules.items():
            if r["kind"] != "property":
                continue
            for a in self.annotations(rid).values():
                values.update(list(a["people"]))
                waiting += a["waiting"]
                experts += annotated_match(a, EXPERTS, None)
                engineers += annotated_match(a, ENGINEERS, None)
        names = set(self.roles) | set(values)
        return {"people": sorted(({"name": n, "role": self.roles.get(n) or "engineer", "values": values[n]}
                                  for n in names), key=lambda p: (p["role"] != "sme", -p["values"], p["name"])),
                "waiting": waiting, "experts": experts, "engineers": engineers}

    def spread_groups(self, rule_id: str) -> tuple[str, dict[str, str], list[str]]:
        """strata.groups for this rule's rows: (grouped by, row key → group, group order). Fixed per snapshot."""
        cache = self.snap._spread
        if rule_id not in cache:
            snap = self.snap
            kind = snap.rules[rule_id]["kind"]
            on_page = Counter(o["page_stem"] for o in snap.occurrences.values()) if kind == "page" else None
            cache[rule_id] = strata.groups(kind, snap.rows(rule_id), on_page)
        return cache[rule_id]


def annotated_match(a: dict, by: str | None, verdict: str | None) -> bool:
    """Whether a row (its `Review.annotations` entry) passes the "Annotated by" filter: `by` is a person (their own
    verdict counts for `verdict`), EXPERTS or ENGINEERS (any of that role's verdicts count), NOBODY or WAITING (the
    row's verdict counts), or None (anyone)."""
    if by == NOBODY:
        return not a["people"] and not verdict
    if by == WAITING:
        ok, kinds = a["waiting"], a["kinds"]
    elif by in (EXPERTS, ENGINEERS):
        role = "sme" if by == EXPERTS else "engineer"
        mine = [p for p in a["people"].values() if p.get("role") == role]
        ok, kinds = bool(mine), [k for p in mine for k in p["kinds"]]
    elif by:
        ok, kinds = by in a["people"], a["people"].get(by, {}).get("kinds", [])
    else:
        ok, kinds = True, a["kinds"]
    return ok and (not verdict or verdict in kinds)


def _overlaps(a: str, b: str) -> bool:
    """One css path is the other or inside it."""
    return a == b or a.startswith(b + " > ") or b.startswith(a + " > ")


def _h(signal: str, detail: str) -> dict:
    from .signals import CATALOG

    return {"signal": signal, "severity": CATALOG[signal][1], "detail": detail, "history": True}


class Loader:
    """Caches snapshots and log readers per catalog (the server keeps one for its lifetime).

    Snapshots are big (WVU's latest extraction is ~1.3 GB of Python objects), so only the most recently used ones are
    kept: at most `MAX_SNAPSHOTS`, and fewer once their values add up to more than `budget` (env
    `GOLDEN_DATASETS_SNAPSHOT_BUDGET`, matched values); the two most recent always stay (a Review and its parent).
    Reviews are dropped with their snapshots, so nothing else keeps an evicted snapshot alive."""

    MAX_SNAPSHOTS = 4
    KEEP = 2
    DEFAULT_BUDGET = 600_000

    def __init__(self, budget: int | None = None):
        import os
        import threading
        from collections import OrderedDict

        self.budget = budget if budget is not None else int(os.environ.get("GOLDEN_DATASETS_SNAPSHOT_BUDGET")
                                                            or self.DEFAULT_BUDGET)
        self._snaps: OrderedDict[tuple, Snapshot] = OrderedDict()  # least recently used first
        self._logs: dict[tuple, AnnotationLog] = {}
        self._reviews: dict[tuple, Review] = {}
        self._lock = threading.RLock()
        #: bumped when every Review is rebuilt (a role changed): derived caches key on it
        self.generation = 0

    @staticmethod
    def _rows(meta: dict) -> int | None:
        files = meta.get("files") or {}
        try:
            return sum(files[f"{t}.parquet"]["rows"] for t in ("matches", "occurrences"))
        except (KeyError, TypeError):
            return None

    @classmethod
    def weight(cls, snap: Snapshot) -> int:
        """A snapshot's size, in the rows that dominate it: matched values and occurrences."""
        rows = cls._rows(snap.meta)
        return rows if rows is not None else sum(len(v) for v in snap.matches_by_rule.values()) + len(snap.occurrences)

    def snapshot(self, ctx: Ctx, ext: str) -> Snapshot:
        key = (ctx.root.uri, ctx.catalog, ctx.crawl, ext)
        with self._lock:
            snap = self._snaps.get(key)
            if snap is not None:
                self._snaps.move_to_end(key)
                return snap
        # make room first (its row counts are in extraction.json), so the old and the new aren't held at once
        incoming = self._rows(ctx.extraction_meta(ext)) or 0
        with self._lock:
            self._evict(incoming=incoming)
        snap = Snapshot(ctx, ext)  # outside the lock: a cold load takes seconds
        with self._lock:
            snap = self._snaps.setdefault(key, snap)
            self._snaps.move_to_end(key)
            self._evict()
        return snap

    def _evict(self, incoming: int = 0) -> None:
        """Drop least recently used snapshots (and their Reviews) until the kept ones, plus `incoming` rows about to
        load, fit; the `KEEP` most recent stay whatever their size."""
        slots = self.MAX_SNAPSHOTS - (1 if incoming else 0)
        keep = self.KEEP - (1 if incoming else 0)
        total = incoming + sum(self.weight(s) for s in self._snaps.values())
        while len(self._snaps) > keep and (len(self._snaps) > slots or total > self.budget):
            _, snap = self._snaps.popitem(last=False)
            total -= self.weight(snap)
            self._reviews = {k: rv for k, rv in self._reviews.items()
                             if rv.snap is not snap and rv.parent is not snap}

    def cached_extractions(self) -> list[tuple]:
        """(catalog, crawl, extraction) of the snapshots kept now, least recently used first."""
        with self._lock:
            return [k[1:] for k in self._snaps]

    def log(self, ctx: Ctx) -> AnnotationLog:
        key = (ctx.root.uri, ctx.catalog)
        with self._lock:
            if key not in self._logs:
                self._logs[key] = AnnotationLog(ctx.root, layout.annotations(ctx.catalog))
            return self._logs[key]

    def review(self, ctx: Ctx, ext: str | None = None, with_parent: bool = True) -> Review:
        """The same Review object while the annotation log hasn't grown, so its per-rule work is reused."""
        ext = ext or ctx.latest_extraction()
        snap = self.snapshot(ctx, ext)
        parent = None
        if with_parent and snap.meta.get("parent_extraction"):
            parent = self.snapshot(ctx, snap.meta["parent_extraction"])
        log = self.log(ctx)
        events = log.events()
        key = (ctx.root.uri, ctx.catalog, ctx.crawl, ext, with_parent, log.offset)
        with self._lock:
            rv = self._reviews.get(key)
            if rv is not None and rv.snap is snap:
                return rv
        rv = Review(snap, events, parent, roles(ctx.root))  # roles as profiles.json says now
        with self._lock:
            self._reviews = {k: v for k, v in self._reviews.items() if k[:5] != key[:5]}  # drop older log offsets
            self._reviews[key] = rv
        return rv

    def forget_reviews(self) -> None:
        """Rebuild every Review on next use (a profile's role changed)."""
        with self._lock:
            self._reviews.clear()
            self.generation += 1
        STATUS_CACHE.clear()


LOADER = Loader()


_HUMAN_COUNTS: dict[tuple, Counter] = {}


def human_reviewed_counts(root, catalogs: list[str], ctx_of=None) -> Counter:
    """rule_id → values a subject matter expert gave a verdict on, summed over these catalogs: the Rules tab's sort
    (property-rules spec §4.8, R9). From the annotation logs only (research B7.4): per (rule, course, page, item), the
    latest live expert verdict that is correct, or wrong with the right text. Cached while no log grows."""
    from .context import Ctx

    logs = []
    for catalog in catalogs:
        ctx = ctx_of(catalog) if ctx_of else Ctx(root, catalog)  # the server's contexts keep the manifest a while
        if root.exists(layout.annotations(catalog)):  # the manifest names a log only from the next publish on
            log = LOADER.log(ctx)
            log.events()
            logs.append((catalog, log))
    key = (root.uri, tuple((c, log.offset) for c, log in logs))
    if key in _HUMAN_COUNTS:
        return _HUMAN_COUNTS[key]
    who = roles(root)
    latest: dict[tuple, dict] = {}
    for catalog, log in logs:
        events = log.events()
        superseded = {e["supersedes"] for e in events if e.get("supersedes")}
        for e in sorted(events, key=lambda x: x["at"]):
            t = e["target"]
            if e["type"] != "verdict" or e["annotation_id"] in superseded or t.get("kind") != "match" \
                    or role_of(e, who) != "sme":
                continue
            item = norm(t.get("value_seen")) if t.get("item") else None
            latest[(catalog, t.get("rule_id"), t.get("course_key") or t.get("occurrence_key"), t.get("page_stem"),
                    item)] = e
    out: Counter = Counter()
    for (_, rid, *_), e in latest.items():
        if e["verdict"] == "correct" or (e["verdict"] == "wrong" and (e.get("expected") or {}).get("text")):
            out[rid] += 1
    _HUMAN_COUNTS.clear()
    _HUMAN_COUNTS[key] = out
    return out
