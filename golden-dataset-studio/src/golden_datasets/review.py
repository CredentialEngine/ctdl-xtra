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
Annotations re-attach through `record_external_identifier` + page when the occurrence key changed (a changed locator, D3).
A row's `events` are every verdict and comment on it, whichever ruleset version they were made in: the "Annotated by"
filter of the Rules and Records tabs (`annotations`, `annotated_match`) and the Sample drawer's "Annotated in" stratum.

Human-reviewed (Evals spec §4.3): only a subject matter expert's verdict makes a value human-reviewed (`RowState.human`).
An engineer's ✓ is recorded and shown as engineer-checked, waiting for an expert; their ✕ counts against the rule
like anyone's. An expert's later verdict supersedes an engineer's; an engineer's later verdict never supersedes an
expert's (the expert's ✓ stands beside it, so the value stays human-reviewed after an engineer's ✓).

The file reads top-down: the `Loader` (what the server calls), then `Review`, then `Snapshot`, then the small pieces.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import functools
import gc
import hashlib
import os
import re
import threading
import time
from collections import Counter, OrderedDict, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import facets, layout, model, profiles_rule, strata, telemetry
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
#: The "Annotated by" menu's choices of who (a person's name besides) and of verdict, all counted per rule at once.
FILTER_WHO = (None, NOBODY, WAITING, EXPERTS, ENGINEERS)
FILTER_VERDICTS = (None, *sorted(set(VERDICT_KIND.values())))
#: The history signal a row's state gives it (spec §8).
STATE_HISTORY = {"wrong": ("previously-wrong", "marked wrong"), "still-wrong": ("previously-wrong", "marked wrong"),
                 "fixed": ("previously-wrong", "marked wrong"), "correct": ("previously-correct", "marked correct"),
                 "changed-since-correct": ("changed-since-correct", "the value changed since it was marked correct")}

#: Rule statuses, see Review.rule_status. Cleared when a profile's role changes (Loader.forget_reviews).
STATUS_CACHE: dict[tuple, dict] = {}
# Per (extraction, parent, rule, the rule's live events): what the "Annotated by" dropdown counts on that rule, and the
# rule list's count for each filter asked for (Review.people, Review.annotated_count). Small, so it outlives Reviews: a
# verdict recounts only its own rule. The per-rule caches of a Review keep only a few rules, so walking every rule for
# the dropdown used to rebuild every rule's rows and row states on each call (6-12 s on Marshall).
PEOPLE_CACHE: dict[tuple, dict] = {}
_RULE_LOCKS: dict[tuple, threading.RLock] = {}  # STATUS_CACHE's key → the lock its work is done under
_RULE_LOCKS_LOCK = threading.Lock()
CACHE_LIMIT = 20_000  # entries a per-rule cache holds before it starts again
_HUMAN_COUNTS: dict[tuple, Counter] = {}

#: The garbage collector's thresholds while serving (`tune_gc`). Python's default (700, 10, 10) collects the young
#: objects every 700 allocations: building a big catalog's rows (half a million dicts for the Rules tab) made 3-4
#: thousand collections, a few of them full ones over every loaded snapshot, 2.6-4.4 s of a 13 s request on Marshall.
GC_THRESHOLDS = (50_000, 20, 10)


class Loader:
    """Caches snapshots and log readers per catalog (the server keeps one for its lifetime).

    Snapshots are big, so only the most recently used ones are kept: at most `MAX_SNAPSHOTS`, and fewer once their
    values add up to more than `budget` (env `GOLDEN_DATASETS_SNAPSHOT_BUDGET`, matched values); the two most recent
    always stay (a Review and its parent). Reviews are dropped with their snapshots, so nothing else keeps an evicted
    snapshot alive.

    Sized from production's traces (2026-11-25): a snapshot.load adds 0.4-1.3 KB of resident memory per row, and the
    server sat at 1.1-1.9 GB of its 6 GiB while 4 snapshots and 600,000 rows were all it kept, so going back to a
    catalog reloaded it (5-12 s each time). Every catalog's current extraction and its parent add up to ~1.55 million
    rows: they now all stay (~3 GB)."""

    MAX_SNAPSHOTS = 12
    KEEP = 2
    DEFAULT_BUDGET = 1_600_000
    SMALL_SHARE = 0.0075  # a snapshot this share of the budget or less is "small" (12,000 rows by default)
    MAX_SMALL = 6       # small snapshots kept, apart from the big ones: at most 12% of the budget together

    def __init__(self, budget: int | None = None):
        self.budget = budget if budget is not None else int(os.environ.get("GOLDEN_DATASETS_SNAPSHOT_BUDGET")
                                                            or self.DEFAULT_BUDGET)
        self._snaps: OrderedDict[tuple, Snapshot] = OrderedDict()  # least recently used first
        self._logs: dict[tuple, AnnotationLog] = {}
        self._reviews: dict[tuple, Review] = {}
        self._lock = threading.RLock()
        self._loading = threading.RLock()  # held while a snapshot loads (see `snapshot`)
        #: bumped when every Review is rebuilt (a role changed): derived caches key on it
        self.generation = 0

    def review(self, ctx: Ctx, ext: str | None = None, with_parent: bool = True) -> Review:
        """The same Review object while the annotation log hasn't grown, so its per-rule work is reused."""
        ext = ext or ctx.latest_extraction()
        snap = self.snapshot(ctx, ext)
        parent = self._parent_of(ctx, snap) if with_parent else None
        log = self.log(ctx)
        events = log.events()
        key = (ctx.root.uri, ctx.catalog, ctx.cls, ctx.crawl, ext, with_parent, log.offset)
        return self._cached_review(key, snap) or self._build_review(ctx, key, snap, parent, events)

    def snapshot(self, ctx: Ctx, ext: str, reported_as: str = "ce.snapshot") -> Snapshot:
        """`reported_as`: the prefix of the request span's attributes about this load (`ce.snapshot.cache`...), so a
        review's parent snapshot (`ce.snapshot.parent`) doesn't overwrite what its own snapshot's load said."""
        key = (ctx.root.uri, ctx.catalog, ctx.crawl, ext, ctx.cls)
        snap = self._cached(key)
        if snap is not None:
            telemetry.set({f"{reported_as}.cache": "hit"})
            return snap
        # One cold load at a time. Loads used to run side by side: people opening WVU together each built their own
        # ~1.3 GB copy, and cold loads of different catalogs all made room for themselves alone, so together they
        # passed the memory limit and the server was OOM-killed (2026-11-12). A request whose extraction is loading
        # waits for it and then finds it cached; cached snapshots don't wait for anything.
        started = time.perf_counter()
        with self._loading:
            waited = round((time.perf_counter() - started) * 1000, 1)
            return self._loaded_meanwhile(key, reported_as, waited) or self._load(ctx, ext, key, reported_as, waited)

    def log(self, ctx: Ctx) -> AnnotationLog:
        key = (ctx.root.uri, ctx.catalog, ctx.cls)
        with self._lock:
            if key not in self._logs:
                self._logs[key] = AnnotationLog(ctx.root, layout.annotations(ctx.catalog, ctx.cls))
            return self._logs[key]

    def forget_reviews(self) -> None:
        """Rebuild every Review on next use (a profile's role changed)."""
        with self._lock:
            self._reviews.clear()
            self.generation += 1
        STATUS_CACHE.clear()
        PEOPLE_CACHE.clear()

    def occupancy(self) -> dict:
        """How full the snapshot cache is (`ce.snapshot.cached.*`), against its budget in rows."""
        with self._lock:
            rows = sum(self.weight(s) for s in self._snaps.values())
            return {"ce.snapshot.cached.count": len(self._snaps), "ce.snapshot.cached.rows": rows,
                    "ce.snapshot.budget.rows": self.budget}

    def cached_extractions(self) -> list[tuple]:
        """(catalog, crawl, extraction) of the snapshots kept now, least recently used first."""
        with self._lock:
            return [k[1:4] for k in self._snaps]

    @classmethod
    def weight(cls, snap: Snapshot) -> int:
        """A snapshot's size, in the rows that dominate it: matched values and occurrences."""
        rows = cls._rows(snap.meta)
        return rows if rows is not None else sum(len(v) for v in snap.matches_by_rule.values()) + len(snap.occurrences)

    # -- reviews ------------------------------------------------------------------------------------------
    def _parent_of(self, ctx: Ctx, snap: Snapshot) -> Snapshot | None:
        parent_ext = snap.meta.get("parent_extraction")
        return self.snapshot(ctx, parent_ext, reported_as="ce.snapshot.parent") if parent_ext else None

    def _cached_review(self, key: tuple, snap: Snapshot) -> Review | None:
        with self._lock:
            review = self._reviews.get(key)
        if review is None or review.snap is not snap:
            return None
        telemetry.set({"ce.review.cache": "hit"})
        return review

    def _build_review(self, ctx: Ctx, key: tuple, snap: Snapshot, parent: Snapshot | None,
                      events: list[dict]) -> Review:
        telemetry.set({"ce.review.cache": "miss", "ce.annotations.events": len(events),
                       "ce.review.parent_extraction": parent.ext if parent is not None else None})
        with telemetry.span("review.build", {"ce.annotations.events": len(events)}):
            review = Review(snap, events, parent, roles(ctx.root))  # roles as profiles.json says now
        with self._lock:
            self._reviews = {k: v for k, v in self._reviews.items() if k[:5] != key[:5]}  # drop older log offsets
            self._reviews[key] = review
        return review

    # -- snapshots ----------------------------------------------------------------------------------------
    def _cached(self, key: tuple) -> Snapshot | None:
        with self._lock:
            snap = self._snaps.get(key)
            if snap is not None:
                self._snaps.move_to_end(key)
            return snap

    def _loaded_meanwhile(self, key: tuple, reported_as: str, waited: float) -> Snapshot | None:
        """The snapshot another request loaded while this one waited, if it did."""
        snap = self._cached(key)
        if snap is not None:
            telemetry.set({f"{reported_as}.cache": "waited", f"{reported_as}.wait.duration_ms": waited})
        return snap

    def _load(self, ctx: Ctx, ext: str, key: tuple, reported_as: str, waited: float) -> Snapshot:
        incoming = self._rows(ctx.extraction_meta(ext)) or 0
        evicted = self._make_room(incoming)
        telemetry.set({f"{reported_as}.cache": "miss", f"{reported_as}.wait.duration_ms": waited})
        load_attrs = {"ce.extraction.id": ext, "ce.catalog.folder": ctx.catalog, "ce.class": ctx.cls,
                      "ce.snapshot.rows": incoming,
                      "ce.snapshot.evicted": evicted, "ce.snapshot.is_parent": reported_as.endswith(".parent")}
        with telemetry.span("snapshot.load", load_attrs):
            snap = _read_snapshot(ctx, ext)
        self._keep(key, snap)
        freeze_loaded()
        return snap

    def _make_room(self, incoming: int) -> int:
        """Evict before loading (its row counts are in extraction.json), so the old and the new aren't held at once.
        Returns how many snapshots went."""
        with self._lock:
            before = len(self._snaps)
            self._evict(incoming=incoming)
            return before - len(self._snaps)

    def _keep(self, key: tuple, snap: Snapshot) -> None:
        with self._lock:
            self._snaps[key] = snap
            self._snaps.move_to_end(key)
            self._evict()

    def _evict(self, incoming: int = 0) -> None:
        """Drop least recently used snapshots (and their Reviews) until the kept ones, plus `incoming` rows about to
        load, fit; the `KEEP` most recent stay whatever their size.

        Small snapshots (at most `SMALL_SHARE` of the budget, such as a class with a few hundred records) are kept
        apart, at most `MAX_SMALL` of them, and don't count against the big ones. Otherwise opening WVU's
        LearningProgram (2,888 rows) evicted WVU's Course pair (418,635 rows each), and with All classes the two
        classes evicted each other on every request: a 4 s reload each time."""
        doomed = self._big_to_drop(incoming) + self._small_to_drop(incoming)
        for key in doomed:
            self._drop(key)
        if doomed:
            release_memory()

    def _big_to_drop(self, incoming: int) -> list[tuple]:
        big_in = int(bool(incoming) and not self._small(incoming))
        large = [k for k, s in self._snaps.items() if not self._small(self.weight(s))]  # least recently used first
        total = (incoming if big_in else 0) + sum(self.weight(self._snaps[k]) for k in large)
        doomed = []
        while len(large) > self.KEEP - big_in and (len(large) > self.MAX_SNAPSHOTS - big_in or total > self.budget):
            key = large.pop(0)
            total -= self.weight(self._snaps[key])
            doomed.append(key)
        return doomed

    def _small_to_drop(self, incoming: int) -> list[tuple]:
        small_in = int(bool(incoming) and self._small(incoming))
        small = [k for k, s in self._snaps.items() if self._small(self.weight(s))]  # least recently used first
        return small[:max(0, len(small) - (self.MAX_SMALL - small_in))]

    def _drop(self, key: tuple) -> None:
        telemetry.count("stats.snapshot.evictions")
        snap = self._snaps.pop(key)
        self._reviews = {rk: rv for rk, rv in self._reviews.items() if rv.snap is not snap and rv.parent is not snap}

    def _small(self, rows: int) -> bool:
        return rows <= self.budget * self.SMALL_SHARE

    @staticmethod
    def _rows(meta: dict) -> int | None:
        files = meta.get("files") or {}
        try:
            return sum(files[f"{t}.parquet"]["rows"] for t in ("matches", "occurrences"))
        except (KeyError, TypeError):
            return None


LOADER = Loader()


def human_reviewed_counts(root, catalogs: list[str], ctx_of=None) -> Counter:
    """rule_id → values a subject matter expert gave a verdict on, summed over these catalogs: the Rules tab's sort
    (property-rules spec §4.8, R9). From the annotation logs only (research B7.4): per (rule, course, page, item), the
    latest live expert verdict that is correct, or wrong with the right text. Cached while no log grows."""
    logs = _annotation_logs(root, catalogs, ctx_of)
    key = (root.uri, tuple((c, log.offset) for c, log in logs))
    if key not in _HUMAN_COUNTS:
        counts = _count_human_values(_latest_expert_verdicts(logs, roles(root)))
        _HUMAN_COUNTS.clear()
        _HUMAN_COUNTS[key] = counts
    return _HUMAN_COUNTS[key]


def _annotation_logs(root, catalogs: list[str], ctx_of) -> list[tuple[str, AnnotationLog]]:
    logs = []
    for catalog in catalogs:
        ctx = ctx_of(catalog) if ctx_of else Ctx(root, catalog)  # the server's contexts keep the manifest a while
        if root.exists(layout.annotations(catalog, ctx.cls)):  # the manifest names a log only from the next publish on
            log = LOADER.log(ctx)
            log.events()
            logs.append((catalog, log))
    return logs


def _latest_expert_verdicts(logs: list[tuple[str, AnnotationLog]], who: dict[str, str]) -> dict[tuple, dict]:
    latest: dict[tuple, dict] = {}
    for catalog, log in logs:
        events = log.events()
        gone = {e["supersedes"] for e in events if e.get("supersedes")} | cleared_by_resets(events)
        for e in sorted(events, key=lambda x: x["at"]):
            if _is_live_expert_verdict(e, gone, who):
                latest[_value_key(catalog, e["target"])] = e
    return latest


def _count_human_values(latest: dict[tuple, dict]) -> Counter:
    counts: Counter = Counter()
    for (_, rule_id, *_), e in latest.items():
        if e["verdict"] == "correct" or (e["verdict"] == "wrong" and (e.get("expected") or {}).get("text")):
            counts[rule_id] += 1
    return counts


def _is_live_expert_verdict(e: dict, gone: set[str], who: dict[str, str]) -> bool:
    return e["type"] == "verdict" and e["annotation_id"] not in gone and e["target"].get("kind") == "match" \
        and role_of(e, who) == "sme"


def _value_key(catalog: str, target: dict) -> tuple:
    """(catalog, rule, course, page, item): what one expert verdict is about."""
    item = norm(target.get("value_seen")) if target.get("item") else None
    return (catalog, target.get("rule_id"), target.get("record_external_identifier") or target.get("occurrence_key"),
            target.get("page_stem"), item)


def _read_snapshot(ctx: Ctx, ext: str) -> Snapshot:
    before = telemetry.rss_mb()
    snap = Snapshot(ctx, ext)  # outside `Loader._lock`: a cold load takes seconds; cached reads go on meanwhile
    telemetry.set(_memory_change(before))
    return snap


class Review:
    """A snapshot (+ optional parent snapshot) and the annotation events."""

    # History signals that move a row up in the Rules tab. `previously-correct` doesn't: rows Jared already
    # confirmed fade back instead (spec §7.2); Compare orders by every history signal (A4.1).
    RULES_TAB_HISTORY = {"previously-wrong", "changed-since-correct", "new-in-version"}

    def __init__(self, snap: Snapshot, events: list[dict], parent: Snapshot | None = None,
                 roles: dict[str, str] | None = None):
        self.snap, self.events, self.parent = snap, events, parent
        self.roles = roles or {}  # name → role (profiles.json), for events without author_role
        self.by_id = {e["annotation_id"]: e for e in events}
        superseded = {e["supersedes"] for e in events if e.get("supersedes") and self._supersedes(e)}
        cleared = cleared_by_resets(events)  # Reset rule (phase1-followups §4.3): back to "not reviewed"
        self.live = [e for e in events if e["annotation_id"] not in superseded and e["annotation_id"] not in cleared]
        self.cleared = [e for e in events if e["annotation_id"] in cleared and e["annotation_id"] not in superseded]
        self._states: dict[str, dict] = _Recent()  # rule_id → row states of snap.rows(rule_id) (events are fixed per Review)
        self._annotations: dict[str, dict] = _Recent()  # rule_id → Review.annotations(...)
        self._facets: dict[str, list[dict]] = _Recent()  # rule_id → facets.dimensions(...), see Review.facet_dims
        self._by_rule = self._live_ids_by_rule()  # rule_id → its live events' ids (the status key)

    def report_sizes(self) -> None:
        """Put the catalog's size on the request's span: records, matched values, pages, rules, annotation events, and
        how full the snapshot cache is. Bubble-up then shows which size a slow request follows."""
        parent = self.parent.sizes()["ce.snapshot.matches"] if self.parent is not None else None
        telemetry.set({**self.snap.sizes(), "ce.snapshot.parent.matches": parent,
                       "ce.annotations.events": len(self.events), "ce.annotations.live": len(self.live),
                       **LOADER.occupancy()})

    # -- rule status (spec §4.3) --------------------------------------------------------------------------
    def rule_status(self, rule_id: str, states: dict[str, RowState] | None = None) -> dict:
        """Cached per (extraction, parent, the rule's own live events) across Reviews: a verdict recomputes only
        its own rule's status (property-rules spec §4.14)."""
        got = STATUS_CACHE.get(self._rule_key(rule_id))
        if got is None:
            got = self._summarize(rule_id, states)[0]
        return dict(got)

    def _summarize(self, rule_id: str, states: dict[str, RowState] | None = None) -> tuple[dict, dict]:
        """A rule's status and its "Annotated by" counts, worked out together from one build of its rows and row
        states. The Rules tab asks for every rule's status while its "Annotated by" menu asks for every rule's counts,
        at the same time: each used to build every rule's rows for itself (only `_Recent.RULES_KEPT` rules stay
        cached), the two sharing one core, so each took twice as long. One request per rule at a time: another that
        wants the same rule waits for it, then finds both cached."""
        key = self._rule_key(rule_id)
        with _rule_lock(key):
            status, people = STATUS_CACHE.get(key), PEOPLE_CACHE.get(key)
            if status is None:
                telemetry.count("stats.rule_status.computed")
                status = _keep(STATUS_CACHE, key, self._rule_status(rule_id, states))
            if people is None:
                telemetry.count("stats.rule_people.computed")
                people = _keep(PEOPLE_CACHE, key, self._count_people(rule_id))
        return status, people

    def _rule_key(self, rule_id: str) -> tuple:
        """STATUS_CACHE's and PEOPLE_CACHE's key: the extraction, its parent and the rule's own live events."""
        return (self.snap.ctx.root.uri, self.snap.ctx.catalog, self.snap.ctx.cls, self.snap.ext,
                self.parent.ext if self.parent is not None else None, rule_id, tuple(self._by_rule.get(rule_id, ())))

    def _rule_status(self, rule_id: str, states: dict[str, RowState] | None = None) -> dict:
        last = self._last_rule_decision(rule_id)
        if states is None:
            states = self.row_states(rule_id, self.snap.rows(rule_id))
        counts = _count_states(states)
        open_missing = len(self.missing_events(rule_id))
        status = _status(last, counts["open_wrong"] or open_missing)
        approved = status == "approved"
        return {"status": status, "reviewed": counts["reviewed"], "total": len(states),
                "open_wrong": counts["open_wrong"], "human_values": counts["human"],
                "open_missing": open_missing, "questions": counts["questions"],
                "approved_by": last["author"] if approved else None,
                "approved_at": last["at"] if approved else None}

    def _last_rule_decision(self, rule_id: str) -> dict | None:
        """The rule's latest approve or reopen of its current version, or reset of any version (a reset ends the
        approval of any version)."""
        version = self.snap.rules[rule_id]["version"]
        last = None
        for e in sorted(self.live, key=lambda x: x["at"]):
            if _decides_rule(e, rule_id, version):
                last = e
        return last

    def missing_events(self, rule_id: str) -> list[dict]:
        """`missing` verdicts on a record locator / page rule (no row: the rule didn't find it), still open."""
        rule = self.snap.rules[rule_id]
        latest = self.verdicts_for(rule_id)["latest"]
        return [e for e in latest.values() if e["verdict"] == "missing" and not self._found_since(rule_id, rule, e)]

    def _found_since(self, rule_id: str, rule: dict, e: dict) -> bool:
        stem = e["target"].get("page_stem")
        if rule["kind"] == "page":
            return rule_id in self.snap.matched_pages.get(stem, set())  # the page is recognised now
        if rule["kind"] == "locator":
            return self._occurrence_covers(rule_id, stem, (e.get("expected") or {}).get("css_path") or "")
        return False

    def _occurrence_covers(self, rule_id: str, stem: str | None, css: str) -> bool:
        return bool(css) and any(o["page_stem"] == stem and _overlaps(css, o["css_path"])
                                 for o in self.snap.occ_by_locator.get(rule_id, []))

    # -- row states -----------------------------------------------------------------------------------------
    def row_states(self, rule_id: str, rows: list[dict], stems: set[str] | None = None) -> dict[str, RowState]:
        """Each row's state. `stems`: `rows` are the rule's rows on these pages (`Snapshot.rows_on`), and nothing
        builds the rule's other rows, here or in the parent; their states are those the whole rule's rows get."""
        if stems is not None:
            return self._row_states(rule_id, rows, stems)
        if rows is self.snap.rows(rule_id):
            states = self._states.get(rule_id)
            if states is None:
                started = time.perf_counter()
                self._states[rule_id] = states = self._row_states(rule_id, rows)
                _count_rebuild("row_states", started, len(rows))
            return states
        return self._row_states(rule_id, rows)

    def _row_states(self, rule_id: str, rows: list[dict], stems: set[str] | None = None) -> dict[str, RowState]:
        rule = self.snap.rules[rule_id]
        annotations = _RowAnnotations(self.verdicts_for(rule_id), {r["key"] for r in rows})
        item_events = self.item_events(rule_id) if _is_list_rule(rule) else {}
        parent_keys, parent_has_rows = self._parent_keys(rule_id, stems)
        states = {}
        for row in rows:
            st = self._row_state(rule, row, annotations)
            if item_events:
                self._attach_items(row, item_events, st)
            st.history = self._history(st, parent_has_rows and row["key"] not in parent_keys)
            states[row["key"]] = st
        return states

    def _row_state(self, rule: dict, row: dict, annotations: _RowAnnotations) -> RowState:
        st = annotations.state_of(row)
        if st.verdict is not None:
            self._judge(st, rule, row, annotations)
        if st.events or st.human:  # most rows have no events: skip the scan (it ran on every row of a cold load)
            st.checked = self._engineer_check(st)
        return st

    def _judge(self, st: RowState, rule: dict, row: dict, annotations: _RowAnnotations) -> None:
        st.state = self._carry(rule, st.verdict, row)
        st.role = self.role(st.verdict)
        expert = st.verdict if st.role == "sme" else annotations.lookup("expert", row)
        if expert is not None and st.state not in OPEN and self._carry(rule, expert, row) in HUMAN_STATES:
            st.human = expert

    def _engineer_check(self, st: RowState) -> dict | None:
        """The engineer's check: still on the row, or the one an expert's Confirm superseded."""
        confirmed = [self.by_id.get(st.human.get("supersedes"))] if st.human and st.human.get("supersedes") else []
        checks = [*confirmed, *st.events]
        return max((x for x in checks if x and x["type"] == "verdict" and x["verdict"] == "correct"
                    and self.role(x) != "sme"), key=lambda x: x["at"], default=None)

    def _attach_items(self, row: dict, item_events: dict[tuple, list[dict]], st: RowState) -> None:
        events = item_events.get((row.get("record_external_identifier") or row["occurrence_key"], row["page_stem"]), [])
        if events:
            self._item_states(row, events, st)

    def _history(self, st: RowState, new_in_version: bool) -> list[dict]:
        history = [_h("new-in-version", f"not in {self.parent.ext}")] if new_in_version else []
        if st.state in STATE_HISTORY:
            history.append(_h(*STATE_HISTORY[st.state]))
        return history

    def _parent_keys(self, rule_id: str, stems: set[str] | None) -> tuple[set[str], bool]:
        """The parent's row keys for this rule, and whether the parent has any row of it."""
        if self.parent is None or rule_id not in self.parent.rules:
            return set(), False
        if stems is None:
            keys = {r["key"] for r in self.parent.rows(rule_id)}
            return keys, bool(keys)
        # a row's key names its page, so the parent's rows on the same pages are the ones that can match
        return {r["key"] for r in self.parent.rows_on(rule_id, stems)}, self.parent.has_rows(rule_id)

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

    def _item_states(self, row: dict, events: list[dict], st: RowState) -> None:
        present = {norm(i["value"]) for i in row.get("items") or []}
        for e in events:
            if e["verdict"] != "missing":
                self._mark_item(st, e, present)
        st.missing_items = _missing_items(events, present)
        st.items = {k: v for k, v in st.items.items() if v.state is not None}

    def _mark_item(self, st: RowState, e: dict, present: set[str]) -> None:
        value = norm(e["target"].get("value_seen"))
        item = st.items.setdefault(value, ItemState())
        item.verdict = e
        if e["verdict"] == "correct":
            item.state = "correct" if value in present else None
            if self.role(e) == "sme" and value in present:
                item.human = e
        elif e["verdict"] == "wrong":
            item.state = "wrong" if value in present else "fixed"

    # -- verdicts on rows ------------------------------------------------------------------------------
    def verdicts_for(self, rule_id: str) -> dict:
        """Latest verdict, latest expert's verdict (`expert`), comments and every verdict or comment (`all`) per
        target of this rule, keyed by occurrence_key / page_stem."""
        latest: dict = {}
        expert: dict = {}
        comments = defaultdict(list)
        every = defaultdict(list)
        for e in self._row_events(rule_id):
            k = self._target_key(e)[1]
            if e["type"] == "verdict":
                latest[k] = e
                if self.role(e) == "sme":
                    expert[k] = e
            else:
                comments[k].append(e)
            every[k].append(e)
        return {"latest": latest, "expert": expert, "comments": comments, "all": every,
                "before_reset": self._before_reset(rule_id)}

    def _row_events(self, rule_id: str) -> list[dict]:
        """The rule's live verdicts and comments on its rows, oldest first. Not whole-rule talk (see `discussion`), nor
        a list item's verdicts (see `item_events`)."""
        return [e for e in sorted(self.live, key=lambda x: x["at"])
                if e["target"].get("rule_id") == rule_id and e["target"]["kind"] not in ("rule", "ruleset")
                and not e["target"].get("item") and e["type"] in ("verdict", "comment")]

    def _before_reset(self, rule_id: str) -> dict[str, dict]:
        before = {}
        for e in sorted(self.cleared, key=lambda x: x["at"]):
            if e["target"].get("rule_id") == rule_id and not e["target"].get("item"):
                before[self._target_key(e)[1]] = e
        return before

    def item_events(self, rule_id: str) -> dict[tuple, list[dict]]:
        """Verdicts on a list rule's items, oldest first, per (record_external_identifier or occurrence, page)."""
        out: dict[tuple, list[dict]] = defaultdict(list)
        for e in sorted(self.live, key=lambda x: x["at"]):
            t = e["target"]
            if e["type"] == "verdict" and t.get("item") and t.get("rule_id") == rule_id:
                out[(t.get("record_external_identifier") or t.get("occurrence_key"), t.get("page_stem"))].append(e)
        return out

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

    def withdrawn(self) -> set[str]:
        """Properties whose column a reset took out of the silver dataset: their rule's latest approve or reset is a
        reset (phase1-followups §4.5). Approving the rule again brings the column back."""
        last: dict[str, str] = {}
        for e in sorted(self.live, key=lambda x: x["at"]):
            if e["type"] in ("approve", "reset") and e["target"].get("kind") == "rule":
                last[e["target"].get("rule_id")] = e["type"]
        return {self.snap.rules[rid].get("property_label") for rid, t in last.items()
                if t == "reset" and rid in self.snap.rules}

    def reviewed_elsewhere(self, rule_id: str, rows: list[dict], states: dict[str, RowState]) -> dict[str, list[str]]:
        """Rows of this rule nobody has reviewed yet (no verdict, no comment) whose record someone reviewed in
        another rule: row key → those rules. A record matches by its course, or by its page (page-rule verdicts)."""
        by_course, by_page = self._other_rules_reviewed(rule_id)
        out = {}
        for r in rows:
            st = states[r["key"]]
            if st.state is not None or st.comments:
                continue
            other = by_course.get(r.get("record_external_identifier") or "", set()) | by_page.get(r["page_stem"], set())
            if other:
                out[r["key"]] = sorted(other)
        return out

    def _other_rules_reviewed(self, rule_id: str) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        """The other rules someone gave a verdict or comment in, per course and per page."""
        by_course: dict[str, set[str]] = defaultdict(set)
        by_page: dict[str, set[str]] = defaultdict(set)
        for e in self.live:
            t = e["target"]
            if e["type"] not in ("verdict", "comment") or not t.get("rule_id") or t["rule_id"] == rule_id:
                continue
            if t.get("record_external_identifier"):
                by_course[t["record_external_identifier"]].add(t["rule_id"])
            elif t.get("page_stem"):
                by_page[t["page_stem"]].add(t["rule_id"])
        return by_course, by_page

    def role(self, e: dict) -> str | None:
        return role_of(e, self.roles)

    def _target_key(self, e: dict) -> tuple:
        t = e["target"]
        if t["kind"] in ("match", "occurrence"):
            return (t.get("rule_id"), t.get("occurrence_key"))
        return (t.get("rule_id"), t.get("page_stem"))

    def _supersedes(self, e: dict) -> bool:
        """Whether `e` takes the verdict it supersedes away: an engineer's verdict doesn't take an expert's (§4.3)."""
        old = self.by_id.get(e["supersedes"])
        return old is None or old["type"] != "verdict" or self.role(old) != "sme" or self.role(e) == "sme"

    def _live_ids_by_rule(self) -> dict[str, list[str]]:
        by_rule: dict[str, list[str]] = defaultdict(list)
        for e in self.live:
            if e["target"].get("rule_id"):
                by_rule[e["target"]["rule_id"]].append(e["annotation_id"])
        return by_rule

    # -- ordering (spec §8) --------------------------------------------------------------------------------
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
        discussed = _discussed_first(rows, states)
        talked = {r["key"] for r in discussed}
        rest = [r for r in rows if r["key"] not in talked]
        flagged, sample = self._flagged_and_sample(rule_id, rest, states, keep, seed)
        return [(r, states[r["key"]]) for r in [*discussed, *_mix(flagged, sample, mix_every)]]

    def _flagged_and_sample(self, rule_id: str, rows: list[dict], states: dict[str, RowState], keep: set[str],
                            seed: str) -> tuple[list[dict], list[dict]]:
        """The rows with signals, by severity then signal count; a spread sample of the rest."""
        _, label, order = self.spread_groups(rule_id)
        shuffle = functools.partial(_shuffle_key, seed)
        severity = {r["key"]: _severity(r, states[r["key"]], keep) for r in rows}
        flagged = sorted((r for r in rows if severity[r["key"]][0] > 0),
                         key=lambda r: (-severity[r["key"]][0], -severity[r["key"]][1], shuffle(r)))
        sample = strata.spread([r for r in rows if severity[r["key"]][0] == 0], label, order, shuffle)
        return flagged, sample

    def spread_groups(self, rule_id: str) -> tuple[str, dict[str, str], list[str]]:
        """strata.groups for this rule's rows: (grouped by, row key → group, group order). Fixed per snapshot."""
        cache = self.snap._spread
        if rule_id not in cache:
            snap = self.snap
            kind = snap.rules[rule_id]["kind"]
            on_page = Counter(o["page_stem"] for o in snap.occurrences.values()) if kind == "page" else None
            cache[rule_id] = strata.groups(kind, snap.rows(rule_id), on_page)
        return cache[rule_id]

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

    # -- "Annotated by" ------------------------------------------------------------------------------------
    def people(self) -> dict:
        """The "Annotated by" dropdown: every profile and everyone who annotated a value, with their role and how many
        property values they annotated, and how many values an engineer checked are waiting for an expert."""
        values: Counter = Counter()
        waiting = experts = engineers = 0
        for rid, r in self.snap.rules.items():
            if r["kind"] != "property":
                continue
            e = self._people_entry(rid)
            values.update(e["values"])
            waiting += e["waiting"]
            experts += e["experts"]
            engineers += e["engineers"]
        names = set(self.roles) | set(values)
        return {"people": sorted(({"name": n, "role": self.roles.get(n) or "engineer", "values": values[n]}
                                  for n in names), key=lambda p: (p["role"] != "sme", -p["values"], p["name"])),
                "waiting": waiting, "experts": experts, "engineers": engineers}

    def annotated_count(self, rule_id: str, by: str | None, verdict: str | None) -> int:
        """How many of the rule's rows pass the "Annotated by" filter (the rule list's counts). Every filter the menu
        offers is counted (`_count_people`): one it doesn't (someone who never annotated the rule) passes no row."""
        return self._people_entry(rule_id)["counts"][(by, verdict)]

    def _people_entry(self, rule_id: str) -> dict:
        """PEOPLE_CACHE's entry for this rule: its counts for the dropdown, filled in on first use."""
        got = PEOPLE_CACHE.get(self._rule_key(rule_id))
        if got is None:
            got = self._summarize(rule_id)[1]
        return got

    def _count_people(self, rule_id: str) -> dict:
        """The rule's "Annotated by" counts: values per person, and rows passing every filter the menu offers (each
        choice of who, everyone who annotated the rule among them, with each verdict), so choosing one in the menu
        doesn't build every rule's rows again (8.5 s on Marshall)."""
        values: Counter = Counter()
        counts: Counter = Counter()
        for a in self.annotations(rule_id).values():
            if not (a["people"] or a["kinds"] or a["waiting"]):  # most rows: nobody has touched them
                counts[(None, None)] += 1
                counts[(NOBODY, None)] += 1
                continue
            values.update(list(a["people"]))
            for by in (*FILTER_WHO, *a["people"]):
                for verdict in FILTER_VERDICTS:
                    counts[(by, verdict)] += annotated_match(a, by, verdict)
        return {"values": values, "waiting": counts[(WAITING, None)], "experts": counts[(EXPERTS, None)],
                "engineers": counts[(ENGINEERS, None)], "counts": counts}

    def annotations(self, rule_id: str) -> dict[str, dict]:
        """The "Annotated by" filter's data, per row key: `people` {name: {"kinds": [correct|wrong|note], "at", "role"}} (their
        latest verdict, and note when they commented; the Studio's own events don't count; first names count as the
        full name), `kinds` (the row's: its verdict, note when discussed) and `waiting` (engineer-checked). Fixed per
        Review."""
        cached = self._annotations.get(rule_id)
        if cached is None:
            rows = self.snap.rows(rule_id)
            states = self.row_states(rule_id, rows)
            self._annotations[rule_id] = cached = {r["key"]: self.annotation(states[r["key"]]) for r in rows}
        return cached

    def annotation(self, st: RowState) -> dict:
        """One row's entry in `annotations`, from its state."""
        people = _latest_per_person(st.events)
        kinds = {VERDICT_KIND[st.state]} if st.state in VERDICT_KIND else set()
        return {"people": {n: {"kinds": [k for k in (p["verdict"], "note" if p["note"] else None) if k],
                               "at": p["at"], "role": self.roles.get(n) or "engineer"} for n, p in people.items()},
                "kinds": sorted(kinds | ({"note"} if st.comments else set())), "waiting": st.engineer_checked}


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
        self.ruleset, self.rules = self._read_rules() if rules is None else (ruleset, rules)
        self.settings = self.ruleset["settings"]
        pages, tables = self._read_tables(tables)
        with telemetry.span("snapshot.index", {"ce.extraction.id": ext}):
            self._index(pages, tables)

    def rows(self, rule_id: str) -> list[dict]:
        rows = self._rows.get(rule_id)
        if rows is None:
            started = time.perf_counter()
            self._rows[rule_id] = rows = self._build_rows(rule_id)
            _count_rebuild("rows", started, len(rows))
        return rows

    def rows_on(self, rule_id: str, stems: set[str]) -> list[dict]:
        """The rule's rows on these pages, as `rows` has them; built for those pages alone when the rule's rows aren't
        cached (the cache keeps only a few rules, and one verdict's golden file needs one page of every rule)."""
        rows = self._rows.get(rule_id)
        if rows is not None:
            return [r for r in rows if r["page_stem"] in stems]
        return self._build_rows(rule_id, stems)

    def has_rows(self, rule_id: str) -> bool:
        """Whether the rule has any row, without building them."""
        rows = self._rows.get(rule_id)
        if rows is not None:
            return bool(rows)
        rule = self.rules[rule_id]
        if rule["kind"] == "property":
            if rule["definition"].get("rule_type") == "none":
                return bool(self.occ_by_locator.get(rule["definition"]["locator"]))
            return any(not m["value_index"] for m in self.matches_by_rule.get(rule_id, []))
        if rule["kind"] == "locator":
            return bool(self.occ_by_locator.get(rule_id))
        return bool(self.labels_by_rule.get(rule_id))

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

    def sizes(self) -> dict:
        """How big this extraction is: the counts a request's latency follows (`ce.catalog.records`...)."""
        if getattr(self, "_sizes", None) is None:
            self._sizes = {"ce.catalog.records": len({o["record_external_identifier"] for o in self.occurrences.values()}),
                           "ce.snapshot.occurrences": len(self.occurrences),
                           "ce.snapshot.matches": sum(map(len, self.matches_by_rule.values())),
                           "ce.snapshot.pages": len(self.page), "ce.rules.count": len(self.rules)}
        return self._sizes

    def unclassified_pages(self) -> list[dict]:
        """Pages no page rule recognised although they name many course codes (for "Add a page this rule missed")."""
        return [{"page_stem": stem, "signals": sigs} for stem, sigs in self.page_signals.items()
                if any(s["signal"] == "unclassified-page-with-codes" for s in sigs)]

    def course_line(self, occ_key: str) -> str:
        """Kept per course: every rule's rows on it share the one string."""
        if occ_key not in self._course_lines:
            self._course_lines[occ_key] = self._course_line(occ_key)
        return self._course_lines[occ_key]

    # -- loading ------------------------------------------------------------------------------------------
    def _read_rules(self) -> tuple[dict, dict]:
        with telemetry.span("snapshot.read_rules", {"ce.ruleset.version": self.ruleset_version}):
            ruleset, rules = self.ctx.ruleset_rules(self.ruleset_version)
            telemetry.set({"ce.rules.count": len(rules)})
        return ruleset, rules

    def _read_tables(self, tables: dict | None) -> tuple[list[dict], dict[str, list[dict]]]:
        with telemetry.span("snapshot.read_tables", {"ce.extraction.id": self.ext}), \
                ThreadPoolExecutor(max_workers=5) as pool:  # five downloads at once on a cold Azure cache
            pending_pages = pool.submit(telemetry.in_this_request(self.ctx.pages))
            if tables is None:
                tables = self._download_tables(pool)
            pages = pending_pages.result()
            rows_per_table = {f"ce.snapshot.{name}.rows": len(rows) for name, rows in tables.items()}
            telemetry.set({"ce.snapshot.pages": len(pages), **rows_per_table})
        return pages, tables

    def _download_tables(self, pool: ThreadPoolExecutor) -> dict[str, list[dict]]:
        read_rows = telemetry.in_this_request(lambda name: self.ctx.table(self.ext, name).to_pylist())
        pending = {name: pool.submit(read_rows, name) for name in layout.EXTRACTION_TABLES}
        return {name: _shared(rows.result()) for name, rows in pending.items()}

    def _index(self, pages: list[dict], tables: dict[str, list[dict]]) -> None:
        """The lookups every request uses (matches by rule and by course, labels, signals, course lines): pure
        Python over every row, so for a big catalog (WVU) as slow as the downloads."""
        self.page = {p["page_stem"]: p for p in pages}
        self.occurrences = {o["occurrence_key"]: o for o in tables["occurrences"]}
        self._index_matches(tables["matches"])
        self.occ_by_locator: dict[str, list[dict]] = defaultdict(list)
        for o in self.occurrences.values():
            self.occ_by_locator[o["locator_rule_id"]].append(o)
        self._index_labels(tables["page_labels"])
        self._index_signals(tables["signals"])
        self.code_rule = {loc: self._code_rule(loc) for loc, r in self.rules.items() if r["kind"] == "locator"}
        self.name_rule = {loc: self._name_rule(loc) for loc in self.code_rule}

    def _index_matches(self, matches: list[dict]) -> None:
        self.matches_by_rule: dict[str, list[dict]] = defaultdict(list)
        self.matches_by_occ: dict[str, dict[str, dict]] = defaultdict(dict)  # a rule's first value on a course
        self.items_by_occ: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))  # all of them
        full_paths: dict[tuple, str] = {}  # one string per (course, value) css path pair, not one per match
        for m in sorted(matches, key=lambda x: (x["rule_id"], x["occurrence_key"], x["value_index"])):
            m = self._placed(m, full_paths)
            self.matches_by_rule[m["rule_id"]].append(m)
            self.matches_by_occ[m["occurrence_key"]].setdefault(m["rule_id"], m)
            self.items_by_occ[m["occurrence_key"]][m["rule_id"]].append(m)

    def _placed(self, match: dict, full_paths: dict[tuple, str]) -> dict:
        """A copy of the match with its record's identifier and its css path from the page's root."""
        m = dict(match)
        o = self.occurrences[m["occurrence_key"]]
        m["record_external_identifier"] = o["record_external_identifier"]
        k = (o["css_path"], m["css_path"])
        if k not in full_paths:
            full_paths[k] = model.full_css_path(*k)
        m["full_css_path"] = full_paths[k]
        return m

    def _index_labels(self, labels: list[dict]) -> None:
        self.labels_by_rule: dict[str, list[dict]] = defaultdict(list)
        self.matched_pages: dict[str, set] = defaultdict(set)
        for lb in labels:
            if lb["matched"]:
                self.labels_by_rule[lb["rule_id"]].append(lb)
                self.matched_pages[lb["page_stem"]].add(lb["rule_id"])

    def _index_signals(self, signals: list[dict]) -> None:
        self.signals_by_target: dict[tuple, list[dict]] = defaultdict(list)
        self.page_signals: dict[str, list[dict]] = defaultdict(list)
        self.signal_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for s in signals:
            self.signal_counts[s["rule_id"] or ""][s["signal"]] += 1
            if s["target_kind"] in ("match", "occurrence"):
                self.signals_by_target[(s["rule_id"], s["occurrence_key"])].append(s)
            else:
                self.page_signals[s["page_stem"]].append(s)

    def _code_rule(self, locator: str) -> str:
        """The rule giving a record's code for its display line ("GEOG 222 - Cartography for …"), else its key rule."""
        code = next((rid for rid, r in sorted(self.rules.items())
                     if _is_property_of(r, locator, "ceterms:codedNotation")
                     and r["definition"].get("rule_type") != "none"), None)
        return code or model.key_rule_for(locator, self.rules)[0]

    def _name_rule(self, locator: str) -> str | None:
        return next((rid for rid, r in sorted(self.rules.items()) if _is_property_of(r, locator, "ceterms:name")), None)

    # -- rows ---------------------------------------------------------------------------------------------
    def _build_rows(self, rule_id: str, stems: set[str] | None = None) -> list[dict]:
        rule = self.rules[rule_id]
        if rule["kind"] == "locator":
            return self._locator_rows(rule_id, stems)
        if rule["kind"] != "property":
            return self._page_rows(rule_id, stems)
        if rule["definition"].get("rule_type") == "none":
            return self._unruled_rows(rule["definition"]["locator"], stems)
        return self._property_rows(rule_id, bool(rule["definition"].get("multiple")), stems)

    def _property_rows(self, rule_id: str, is_list: bool, stems: set[str] | None) -> list[dict]:
        rows = []
        for m in self.matches_by_rule.get(rule_id, []):
            if m["value_index"] or (stems is not None and m["page_stem"] not in stems):
                continue  # a list: one row per course, its items below
            row = self._property_row(rule_id, m)
            if is_list:
                self._add_items(row, rule_id, m)
            rows.append(row)
        return rows

    def _property_row(self, rule_id: str, m: dict) -> dict:
        o = self.occurrences[m["occurrence_key"]]
        return {"key": m["occurrence_key"], "occurrence_key": m["occurrence_key"],
                "record_external_identifier": o["record_external_identifier"], "page_stem": m["page_stem"],
                "value": m["value"], "status": m["status"], "css_path": m["full_css_path"],
                "char_start": m["char_start"], "char_end": m["char_end"], "occurrence_css_path": o["css_path"],
                "context": self.course_line(m["occurrence_key"]),
                "signals": self.signals_by_target.get((rule_id, m["occurrence_key"]), [])}

    def _add_items(self, row: dict, rule_id: str, m: dict) -> None:
        found = [x for x in self.items_by_occ[m["occurrence_key"]][rule_id] if x["status"] == "found"]
        row["items"] = [list_item(x, row["occurrence_css_path"]) for x in found]
        row["value"] = profiles_rule.row_value(found) if found else None

    def _unruled_rows(self, locator: str, stems: set[str] | None) -> list[dict]:
        """A property with no rule yet: a row per course, to annotate (§4.6)."""
        return [self._unruled_row(o) for o in self.occ_by_locator.get(locator, [])
                if stems is None or o["page_stem"] in stems]

    def _unruled_row(self, o: dict) -> dict:
        return {"key": o["occurrence_key"], "occurrence_key": o["occurrence_key"],
                "record_external_identifier": o["record_external_identifier"], "page_stem": o["page_stem"],
                "value": None, "status": "none", "css_path": None, "char_start": None, "char_end": None,
                "occurrence_css_path": o["css_path"], "context": self.course_line(o["occurrence_key"]), "signals": []}

    def _locator_rows(self, rule_id: str, stems: set[str] | None) -> list[dict]:
        return [self._locator_row(rule_id, o) for o in self.occ_by_locator.get(rule_id, [])
                if stems is None or o["page_stem"] in stems]

    def _locator_row(self, rule_id: str, o: dict) -> dict:
        signals = list(self.signals_by_target.get((rule_id, o["occurrence_key"]), []))
        signals += self._page_signals_of(rule_id, o["page_stem"])
        return {"key": o["occurrence_key"], "occurrence_key": o["occurrence_key"],
                "record_external_identifier": o["record_external_identifier"], "page_stem": o["page_stem"],
                "value": self.course_line(o["occurrence_key"]) or None, "status": "found",
                "css_path": o["css_path"], "char_start": None, "char_end": None,
                "occurrence_css_path": o["css_path"], "locator_index": o["locator_index"],
                "context": self.page[o["page_stem"]]["title"], "signals": signals}

    def _page_rows(self, rule_id: str, stems: set[str] | None) -> list[dict]:
        return [self._page_row(rule_id, lb["page_stem"]) for lb in self.labels_by_rule.get(rule_id, [])
                if stems is None or lb["page_stem"] in stems]

    def _page_row(self, rule_id: str, stem: str) -> dict:
        p = self.page[stem]
        return {"key": stem, "occurrence_key": None, "record_external_identifier": None, "page_stem": stem,
                "value": p["title"], "status": "found", "css_path": None, "char_start": None,
                "char_end": None, "occurrence_css_path": None, "context": p["url"],
                "signals": self._page_signals_of(rule_id, stem)}

    def _page_signals_of(self, rule_id: str, stem: str) -> list[dict]:
        return [s for s in self.page_signals.get(stem, []) if s["rule_id"] == rule_id]

    def _course_line(self, occ_key: str) -> str:
        """A course's "GEOG 222 - Cartography"; another class's record: its page's title (mockup w4-class-menu)."""
        o = self.occurrences[occ_key]
        if self.ctx.cls != "course":
            return self.page[o["page_stem"]]["title"] or o["page_stem"]
        ms = self.matches_by_occ[occ_key]
        code = (ms.get(self.code_rule.get(o["locator_rule_id"])) or {}).get("value")
        name = (ms.get(self.name_rule.get(o["locator_rule_id"])) or {}).get("value")
        return " - ".join(x for x in (code, name) if x)


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
    before_reset: dict | None = None  # the verdict a reset took back, on a row nobody has reviewed since (a hint only)
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


class _RowAnnotations:
    """One rule's verdicts and comments (`Review.verdicts_for`) by row key, and again by (course, page) for rows whose
    occurrence key changed since (a changed locator, D3): comments and earlier verdicts re-attach the same way, so an
    older ruleset's annotations stay on the row. Looked up once per row: the Rules tab does it for every row."""

    def __init__(self, found: dict, row_keys: set[str]):
        self.found = found
        talk, every = _events_off_rows(found["all"], row_keys)
        self.moved = {"latest": _last_per_course_page(found["latest"]),
                      "expert": _last_per_course_page(found["expert"]),
                      "before_reset": _last_per_course_page(found["before_reset"]),
                      "comments": talk, "all": every}

    def state_of(self, row: dict) -> RowState:
        """The row's state as its annotations start it: comments, events, verdict, or what a reset took back."""
        key = row["key"]
        place = (row["record_external_identifier"], row["page_stem"]) if row.get("record_external_identifier") else None
        found, moved = self.found, self.moved if place else _NOWHERE
        st = RowState(comments=found["comments"].get(key, []), events=found["all"].get(key, []))
        if place:
            st.comments = st.comments + moved["comments"].get(place, [])
            st.events = sorted(st.events + moved["all"].get(place, []), key=lambda x: x["at"])
        st.verdict = found["latest"].get(key)
        if st.verdict is None:
            st.verdict = moved["latest"].get(place)
            st.reattached = st.verdict is not None
        if st.verdict is None:  # what a reset took back, on this row or re-attached by course and page
            st.before_reset = found["before_reset"].get(key) or moved["before_reset"].get(place)
        return st

    def lookup(self, kind: str, row: dict) -> dict | None:
        """The row's own `kind` verdict, else one re-attached by its course and page."""
        own = self.found[kind].get(row["key"])
        if own is not None or not row.get("record_external_identifier"):
            return own
        return self.moved[kind].get((row["record_external_identifier"], row["page_stem"]))


_NOWHERE: dict[str, dict] = {"latest": {}, "expert": {}, "before_reset": {}, "comments": {}, "all": {}}


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
                telemetry.count("stats.rule_cache.evictions")


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


def cleared_by_resets(events: list[dict]) -> set[str]:
    """The verdicts resets took back: a `reset` on a rule clears its rule's verdicts appended before it (any rule
    version: verdicts carry forward across versions). The log's order, not `at`: a verdict saved in the same second
    after the reset stays."""
    pending: dict[str, set[str]] = defaultdict(set)
    out: set[str] = set()
    for e in events:
        rid = e["target"].get("rule_id")
        if e["type"] == "reset":
            out |= pending.pop(rid, set())
        elif reset_clears(e):
            pending[rid].add(e["annotation_id"])
    return out


def reset_clears(e: dict) -> bool:
    """A verdict Reset rule takes back (phase1-followups spec §4.3): one that makes a value human. ✓; ✕ with an answer
    or "not on the page"; an added item or object (`missing` with an answer). Comments, questions and ✕ or `missing`
    with no answer stay."""
    if e["type"] != "verdict":
        return False
    x = e.get("expected") or {}
    answered = bool(x.get("text") or x.get("segments") or x.get("objects"))
    return e["verdict"] == "correct" or (e["verdict"] == "wrong" and (answered or "not_on_page" in (e.get("reasons") or []))) \
        or (e["verdict"] == "missing" and answered)


def _count_states(states: dict[str, RowState]) -> dict[str, int]:
    rows = states.values()
    return {"open_wrong": sum(1 for s in rows if s.state in OPEN)
            + sum(1 for s in rows for i in s.items.values() if i.state == "wrong")
            + sum(1 for s in rows for e in s.missing_items if e["verdict"] == "missing"),  # a correction's ✕ counts
            "reviewed": sum(1 for s in rows if s.state is not None or s.items),
            "questions": sum(1 for s in rows if s.state == "question"),
            "human": sum(1 for s in rows if s.human) + sum(1 for s in rows for i in s.items.values() if i.human)}


def _status(last: dict | None, open_work: int) -> str:
    if last is not None and last["type"] == "approve":
        return "approved"
    return "needs work" if open_work else "in review"


def _decides_rule(e: dict, rule_id: str, version) -> bool:
    t = e["target"]
    return t.get("kind") == "rule" and t.get("rule_id") == rule_id and (e["type"] == "reset" or (
        e["type"] in ("approve", "reopen") and t.get("rule_version_seen") == version))


def _missing_items(events: list[dict], present: set[str]) -> list[dict]:
    """Items someone added that the rule still doesn't give: an added object, or a found one's correction (✕ with the
    corrected object, phase1-followups spec §3.2). The answer stands until the rule gives it."""
    missing: dict[str, dict] = {}
    for e in events:
        if e["verdict"] == "missing" or (e["verdict"] == "wrong" and (e.get("expected") or {}).get("objects")):
            missing[norm((e.get("expected") or {}).get("text"))] = e
        elif e["verdict"] == "correct":
            missing.pop(norm(e["target"].get("value_seen")), None)
    return [e for text, e in missing.items() if text and text not in present]


def _events_off_rows(every: dict[str, list[dict]], row_keys: set[str]) -> tuple[dict, dict]:
    """Comments, and every verdict or comment, on keys no current row has, by (course, page)."""
    talk: dict[tuple, list] = defaultdict(list)
    events: dict[tuple, list] = defaultdict(list)
    for key, es in every.items():
        if key in row_keys:
            continue
        for e in es:
            if e["target"].get("record_external_identifier"):
                events[_course_page(e["target"])].append(e)
                if e["type"] == "comment":
                    talk[_course_page(e["target"])].append(e)
    return talk, events


def _last_per_course_page(by_key: dict[str, dict]) -> dict[tuple, dict]:
    return {_course_page(e["target"]): e for e in by_key.values() if e["target"].get("record_external_identifier")}


def _course_page(target: dict) -> tuple:
    return (target["record_external_identifier"], target.get("page_stem"))


def _latest_per_person(events: list[dict]) -> dict[str, dict]:
    """Each person's latest verdict kind on a row and whether they commented (the Studio's own events don't count;
    first names count as the full name)."""
    people: dict[str, dict] = {}
    for e in events:  # oldest first: the latest verdict wins
        if e["author"].startswith("golden-datasets"):
            continue
        p = people.setdefault(FULL_NAMES.get(e["author"], e["author"]), {"verdict": None, "note": False})
        if e["type"] == "verdict" and e["verdict"] != "question":
            p["verdict"] = VERDICT_KIND.get(e["verdict"])
        else:
            p["note"] = True
        p["at"] = e["at"]
    return people


def _discussed_first(rows: list[dict], states: dict[str, RowState]) -> list[dict]:
    """Rows with a comment or an "unsure" verdict that nobody has marked correct, newest talk first."""
    discussed = [r for r in rows if states[r["key"]].state != "correct"
                 and (states[r["key"]].comments or states[r["key"]].state == "question")]
    return sorted(discussed, key=lambda r: _last_talk(states[r["key"]]), reverse=True)


def _last_talk(st: RowState) -> str:
    ats = [c["at"] for c in st.comments] + ([st.verdict["at"]] if st.state == "question" else [])
    return max(ats, default="")


def _severity(row: dict, st: RowState, keep: set[str]) -> tuple[int, int]:
    signals = row["signals"] + [h for h in st.history if h["signal"] in keep]
    if not signals:
        return (0, 0)
    return (max(SEVERITY_RANK[s["severity"]] for s in signals), len(signals))


def _mix(flagged: list[dict], sample: list[dict], mix_every: int) -> list[dict]:
    """The flagged rows with every `mix_every`-th row taken from the sample, then the rest of the sample."""
    out, taken = [], 0
    for i, row in enumerate(flagged):
        if i and i % (mix_every - 1) == 0 and taken < len(sample):
            out.append(sample[taken])
            taken += 1
        out.append(row)
    return out + sample[taken:]


def _shuffle_key(seed: str, row: dict) -> str:
    return hashlib.sha1(f"{seed}:{row['key']}".encode()).hexdigest()


def _is_list_rule(rule: dict) -> bool:
    return rule["kind"] == "property" and bool(rule["definition"].get("multiple"))


def _is_property_of(rule: dict, locator: str, ctdl_property: str) -> bool:
    return rule["kind"] == "property" and rule["definition"].get("locator") == locator \
        and rule.get("ctdl_property") == ctdl_property


def list_item(match: dict, occurrence_css_path: str) -> dict:
    return {"value_index": match["value_index"], "value": match["value"], "css_path": match["full_css_path"],
            "char_start": match["char_start"], "char_end": match["char_end"],
            **profiles_rule.row_item(match, occurrence_css_path)}


def _rule_lock(key: tuple) -> threading.RLock:
    with _RULE_LOCKS_LOCK:
        if len(_RULE_LOCKS) > CACHE_LIMIT:
            _RULE_LOCKS.clear()  # a lock someone holds stays alive with them; a new one is made for the next asker
        return _RULE_LOCKS.setdefault(key, threading.RLock())


def _keep(cache: dict, key: tuple, value: dict) -> dict:
    if len(cache) > CACHE_LIMIT:
        cache.clear()
    cache[key] = value
    return value


def _count_rebuild(what: str, started: float, rows: int) -> None:
    """Counts a per-rule cache miss on the request's span: `ce.stats.<what>.builds`, `.rows` and `.duration_ms`. Only
    `_Recent.RULES_KEPT` rules stay cached, so a page that walks every rule (the Rules tab) rebuilds most of them; on
    WVU that is the request's time. Counters, not a span per rule: the Rules tab would make hundreds."""
    elapsed_ms = (time.perf_counter() - started) * 1000
    telemetry.count(f"stats.{what}.builds")
    telemetry.count(f"stats.{what}.rows", rows)
    telemetry.count(f"stats.{what}.duration_ms", elapsed_ms)


def _shared(rows: list[dict]) -> list[dict]:
    """A table's rows with one string object per distinct value. `to_pylist` makes a new str per cell, so WVU's
    419k matches carried 419k copies of a few dozen rule ids, of each occurrence key and css path, and so on."""
    seen: dict[str, str] = {}
    for row in rows:
        for k, v in row.items():
            if type(v) is str:
                row[k] = seen.setdefault(v, v)
    return rows


def _overlaps(a: str, b: str) -> bool:
    """One css path is the other or inside it."""
    return a == b or a.startswith(b + " > ") or b.startswith(a + " > ")


def _h(signal: str, detail: str) -> dict:
    from .signals import CATALOG

    return {"signal": signal, "severity": CATALOG[signal][1], "detail": detail, "history": True}


def norm(v: str | None) -> str:
    return re.sub(r"\s+", " ", v or "").strip()


def release_memory() -> None:
    """Free what an evicted snapshot held and give it back to the OS. glibc keeps freed heap for reuse, so without
    this the server's memory only grew: it sat at 2.9 of its 3 GiB with nobody using it, and opening WVU on top got it
    OOM-killed. A no-op where there is no glibc (macOS)."""
    with telemetry.span("memory.release"):
        before = telemetry.rss_mb()
        gc.unfreeze()  # the evicted snapshot's objects back where a collection sees them (see `freeze_loaded`)
        gc.collect()
        gc.freeze()
        try:
            ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6").malloc_trim(0)
        except (OSError, AttributeError):
            pass
        telemetry.set(_memory_change(before))
    telemetry.count("stats.snapshot.releases")


def tune_gc() -> None:
    """Collect less often while serving (`GC_THRESHOLDS`); the server calls it once when it starts."""
    gc.set_threshold(*GC_THRESHOLDS)


def freeze_loaded() -> None:
    """Move every object alive now (the snapshots just loaded) out of the collector's sight: a full collection no
    longer walks millions of snapshot rows that never become garbage. Refcounting still frees them; an eviction's
    `release_memory` unfreezes, collects and freezes again, so cycles in an evicted snapshot are collected too."""
    gc.freeze()


def _memory_change(before: int | None) -> dict:
    """Resident memory before and after some work, for its span (`ce.process.memory.rss_*_mb`)."""
    after = telemetry.rss_mb()
    if before is None or after is None:
        return {}
    return {"ce.process.memory.rss_before_mb": before, "ce.process.memory.rss_after_mb": after,
            "ce.process.memory.rss_delta_mb": after - before}
