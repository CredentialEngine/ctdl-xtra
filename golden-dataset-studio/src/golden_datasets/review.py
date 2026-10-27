"""The read model shared by the server, `rule list/show/annotations`, the prompt and Compare.

`Snapshot` = one extraction loaded in memory (rules of its ruleset, occurrences, matches, signals, page labels).
`Review` = a snapshot + the annotation log: each row's verdict carried forward to the current version, history
signals (spec §8, computed when read, never stored), rule status (spec §4.3) and the row order of the Rules tab.

Rows, per rule kind (spec §7.2):
- field rule: one per match (a course the record locator found), key = occurrence_key;
- record locator: one per occurrence, key = occurrence_key;
- page rule: one per page the rule recognised, key = page_stem.

How an old verdict applies to the current row (spec §4.3 "old verdicts carry forward through the comparison"):
- seen on this rule version, or the value is unchanged since → it applies as given;
- `wrong` and the value changed: **fixed** when it now equals the expected text, else **still wrong**;
- `correct` and the value changed: **changed since correct** (needs a fresh look; not counted as wrong).
Annotations re-attach through `course_key` + page when the occurrence key changed (a changed locator, D3).
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field

from . import layout, model
from .context import Ctx
from .log import AnnotationLog
from .signals import SEVERITY_RANK

OPEN = {"wrong", "still-wrong", "missing"}


def norm(v: str | None) -> str:
    return re.sub(r"\s+", " ", v or "").strip()


class Snapshot:
    """One extraction, in memory. Immutable, so it is cached for the life of the process."""

    def __init__(self, ctx: Ctx, ext: str, tables: dict | None = None, ruleset: dict | None = None,
                 rules: dict | None = None, meta: dict | None = None):
        """An extraction on storage (`ext`), or an unwritten one (`tables` + `ruleset` + `rules`, e.g. a draft)."""
        self.ctx, self.ext = ctx, ext
        self.meta = meta if meta is not None else ctx.extraction_meta(ext)
        self._rows: dict[str, list[dict]] = {}
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
                tables = {name: f.result() for name, f in futures.items()}
            pages = pages_f.result()
        self.page = {p["page_stem"]: p for p in pages}
        self.occurrences = {o["occurrence_key"]: o for o in tables["occurrences"]}
        self.matches_by_rule: dict[str, list[dict]] = defaultdict(list)
        self.matches_by_occ: dict[str, dict[str, dict]] = defaultdict(dict)
        for m in tables["matches"]:
            m = dict(m)
            o = self.occurrences[m["occurrence_key"]]
            m["course_key"] = o["course_key"]
            m["full_css_path"] = model.full_css_path(o["css_path"], m["css_path"])
            self.matches_by_rule[m["rule_id"]].append(m)
            self.matches_by_occ[m["occurrence_key"]][m["rule_id"]] = m
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
            self.name_rule[loc] = next((rid for rid, r in sorted(self.rules.items()) if r["kind"] == "field"
                                        and r["definition"]["locator"] == loc
                                        and r.get("ctdl_property") == "ceterms:name"), None)

    # -- rows ---------------------------------------------------------------------------------------------
    def course_line(self, occ_key: str) -> str:
        o = self.occurrences[occ_key]
        ms = self.matches_by_occ[occ_key]
        code = (ms.get(self.code_rule.get(o["locator_rule_id"])) or {}).get("value")
        name = (ms.get(self.name_rule.get(o["locator_rule_id"])) or {}).get("value")
        return " - ".join(x for x in (code, name) if x)

    def rows(self, rule_id: str) -> list[dict]:
        if rule_id not in self._rows:
            self._rows[rule_id] = self._build_rows(rule_id)
        return self._rows[rule_id]

    def _build_rows(self, rule_id: str) -> list[dict]:
        rule = self.rules[rule_id]
        out = []
        if rule["kind"] == "field":
            for m in self.matches_by_rule.get(rule_id, []):
                o = self.occurrences[m["occurrence_key"]]
                out.append({"key": m["occurrence_key"], "occurrence_key": m["occurrence_key"],
                            "course_key": o["course_key"], "page_stem": m["page_stem"], "value": m["value"],
                            "status": m["status"], "css_path": m["full_css_path"], "char_start": m["char_start"],
                            "char_end": m["char_end"], "occurrence_css_path": o["css_path"],
                            "context": self.course_line(m["occurrence_key"]),
                            "signals": self.signals_by_target.get((rule_id, m["occurrence_key"]), [])})
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
        if rule["kind"] != "field":
            n = len(self.rows(rule_id))
            return {"rows": n, "found": n}
        ms = self.matches_by_rule.get(rule_id, [])
        return {"rows": len(ms), "found": sum(1 for m in ms if m["status"] == "found")}


@dataclass
class RowState:
    state: str | None = None          # correct | wrong | fixed | still-wrong | changed-since-correct | question | missing
    verdict: dict | None = None       # the event it comes from
    reattached: bool = False
    comments: list = field(default_factory=list)
    history: list = field(default_factory=list)  # history signals: [{"signal", "severity", "detail"}]


class Review:
    """A snapshot (+ optional parent snapshot) and the annotation events."""

    def __init__(self, snap: Snapshot, events: list[dict], parent: Snapshot | None = None):
        self.snap, self.events, self.parent = snap, events, parent
        superseded = {e["supersedes"] for e in events if e.get("supersedes")}
        self.live = [e for e in events if e["annotation_id"] not in superseded]

    # -- verdicts on rows ------------------------------------------------------------------------------
    def _target_key(self, e: dict) -> tuple:
        t = e["target"]
        if t["kind"] in ("match", "occurrence"):
            return (t.get("rule_id"), t.get("occurrence_key"))
        return (t.get("rule_id"), t.get("page_stem"))

    def verdicts_for(self, rule_id: str) -> dict:
        """Latest verdict and comments per target of this rule, keyed by occurrence_key / page_stem."""
        latest: dict = {}
        comments = defaultdict(list)
        for e in sorted(self.live, key=lambda x: x["at"]):
            t = e["target"]
            if t.get("rule_id") != rule_id:
                continue
            k = self._target_key(e)[1]
            if e["type"] == "verdict":
                latest[k] = e
            elif e["type"] == "comment":
                comments[k].append(e)
        return {"latest": latest, "comments": comments}

    def row_states(self, rule_id: str, rows: list[dict]) -> dict[str, RowState]:
        rule = self.snap.rules[rule_id]
        v = self.verdicts_for(rule_id)
        latest, comments = v["latest"], v["comments"]
        by_course_page = {}
        for e in latest.values():
            t = e["target"]
            if t.get("course_key"):
                by_course_page[(t["course_key"], t.get("page_stem"))] = e
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
            if e is not None:
                st.verdict = e
                st.state = self._carry(rule, e, row)
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
        if rule["kind"] != "field":
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
        rule = self.snap.rules[rule_id]
        last = None
        for e in sorted(self.live, key=lambda x: x["at"]):
            t = e["target"]
            if e["type"] in ("approve", "reopen") and t.get("kind") == "rule" and t.get("rule_id") == rule_id \
                    and t.get("rule_version_seen") == rule["version"]:
                last = e
        if states is None:
            states = self.row_states(rule_id, self.snap.rows(rule_id))
        open_rows = sum(1 for s in states.values() if s.state in OPEN)
        open_missing = len(self.missing_events(rule_id))
        reviewed = sum(1 for s in states.values() if s.state is not None)
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

    def ordered(self, rule_id: str, seed: str = "golden-datasets", boring_every: int = 10,
                history: set[str] | None = None) -> list[tuple[dict, RowState]]:
        """Severity, then signal count, then a seeded random sample of rows without signals; one such "boring"
        row is mixed in every `boring_every` rows, so a reviewer always sees some."""
        rows = self.snap.rows(rule_id)
        states = self.row_states(rule_id, rows)
        keep = self.RULES_TAB_HISTORY if history is None else history

        def sev(row) -> tuple[int, int]:
            sig = row["signals"] + [h for h in states[row["key"]].history if h["signal"] in keep]
            if not sig:
                return (0, 0)
            return (max(SEVERITY_RANK[s["severity"]] for s in sig), len(sig))

        def rnd(row) -> str:
            return hashlib.sha1(f"{seed}:{row['key']}".encode()).hexdigest()

        flagged = sorted((r for r in rows if sev(r)[0] > 0), key=lambda r: (-sev(r)[0], -sev(r)[1], rnd(r)))
        boring = sorted((r for r in rows if sev(r)[0] == 0), key=rnd)
        out, bi = [], 0
        for i, r in enumerate(flagged):
            if i and i % (boring_every - 1) == 0 and bi < len(boring):
                out.append(boring[bi])
                bi += 1
            out.append(r)
        out.extend(boring[bi:])
        return [(r, states[r["key"]]) for r in out]


def _overlaps(a: str, b: str) -> bool:
    """One css path is the other or inside it."""
    return a == b or a.startswith(b + " > ") or b.startswith(a + " > ")


def _h(signal: str, detail: str) -> dict:
    from .signals import CATALOG

    return {"signal": signal, "severity": CATALOG[signal][1], "detail": detail, "history": True}


class Loader:
    """Caches snapshots and log readers per catalog (the server keeps one for its lifetime)."""

    def __init__(self):
        self._snaps: dict[tuple, Snapshot] = {}
        self._logs: dict[tuple, AnnotationLog] = {}

    def snapshot(self, ctx: Ctx, ext: str) -> Snapshot:
        key = (ctx.root.uri, ctx.catalog, ctx.crawl, ext)
        if key not in self._snaps:
            self._snaps[key] = Snapshot(ctx, ext)
        return self._snaps[key]

    def log(self, ctx: Ctx) -> AnnotationLog:
        key = (ctx.root.uri, ctx.catalog)
        if key not in self._logs:
            self._logs[key] = AnnotationLog(ctx.root, layout.annotations(ctx.catalog))
        return self._logs[key]

    def review(self, ctx: Ctx, ext: str | None = None, with_parent: bool = True) -> Review:
        ext = ext or ctx.latest_extraction()
        snap = self.snapshot(ctx, ext)
        parent = None
        if with_parent and snap.meta.get("parent_extraction"):
            parent = self.snapshot(ctx, snap.meta["parent_extraction"])
        return Review(snap, self.log(ctx).events(), parent)


LOADER = Loader()
