"""Scores as durable jobs (Evals spec §4): `score.json` is written `running`, the scorer runs in a thread of the server,
and the file says `done` or `failed`. One score runs per catalog at a time; on start, a score a restart left
`running` becomes `interrupted`.

A loop checks every 30 s, and once on start: for each catalog and class, a new extract output (scored against the
latest golden dataset, every property: trigger `new-output`), a latest golden dataset the latest extract output has
no score against yet (one published from the CLI: the properties it changed, trigger `golden-published`), and
`scores-pending.json` (when due, the latest extract output against the human-reviewed values, for the properties
reviewed: `golden-published`; then the file is deleted). A score of a class runs one at a time per catalog and class.
"""

from __future__ import annotations

import multiprocessing
import os
import threading
import traceback

from .. import scores, telemetry
from ..context import Ctx
from ..errors import UserError

EVERY = 30.0  # seconds
#: "1": each score runs in a process of its own (the deployed Studio). A score is a minute of Python work: in a thread
#: of the server it held up every request meanwhile, and the memory it used stayed with the server after it ended.
ENV_PROCESS = "GOLDEN_DATASETS_SCORE_PROCESS"


def in_process() -> bool:
    return os.environ.get(ENV_PROCESS) == "1"


class ScoreJobs:
    def __init__(self):
        self._busy: dict[tuple[str, str], str] = {}  # (catalog, class) → the score running
        self._lock = threading.Lock()

    def busy(self, catalog: str, cls: str = "course") -> str | None:
        return self._busy.get((catalog, cls))

    def start(self, ctx: Ctx, golden: str | None, output: str | None = None, by: str = "", reason: str = "",
              wait: bool = False, trigger: str = "manual", properties: list[str] | None = None) -> dict:
        """The score of this pair: the existing one, or a new one started in a thread (`running`). Raises UserError
        while another score of the catalog and class runs."""
        key = (ctx.catalog, ctx.cls)
        self._claim(key)
        try:
            p, doc = self._begin_unless_scored(ctx, key, golden, output, by, reason, trigger, properties)
        except BaseException:
            self._busy.pop(key, None)
            raise
        if p is not None:
            self._run_in_thread(ctx, key, doc, p, by, reason, wait)
        return doc

    def after_publish(self, ctx: Ctx, by: str, columns: list[str] | None = None) -> dict | None:
        """Approving (or resetting) a column publishes it, then scores the latest extract output against the latest
        golden dataset, for that column (Evals spec §4.1). None when there is nothing to score."""
        return self._quietly(ctx, None, by, "a column was published", "golden-published", columns)

    def _claim(self, key: tuple[str, str]) -> None:
        with self._lock:
            if key in self._busy:
                raise UserError(f"{self._busy[key]} is still running")
            self._busy[key] = "a score"

    def _begin_unless_scored(self, ctx: Ctx, key: tuple[str, str], golden: str | None, output: str | None, by: str,
                             reason: str, trigger: str, properties: list[str] | None) -> tuple:
        """(prepared, the new score), or (None, the existing score of the pair)."""
        p = scores.prepare(ctx, golden, output, log=print)
        doc = scores.existing(ctx, p)
        if doc:
            self._busy.pop(key, None)
            return None, doc
        doc = scores.begin(ctx, p, by, reason, trigger, properties)
        self._busy[key] = doc["id"]
        return p, doc

    def _run_in_thread(self, ctx: Ctx, key: tuple[str, str], doc: dict, p, by: str, reason: str, wait: bool) -> None:
        carried = telemetry.carry()  # the score's trace links to the request (or loop pass) that started it
        telemetry.set({"ce.score.id": doc["id"], "ce.score.reason": reason})
        thread = threading.Thread(target=self._run, args=(ctx, key, doc, p, by, reason, carried),
                                  name=f"score-{ctx.catalog}-{doc['id']}", daemon=True)
        thread.start()
        if wait:
            thread.join()

    def _run(self, ctx: Ctx, key: tuple[str, str], doc: dict, p, by: str, reason: str, carried: dict) -> None:
        attrs = {"ce.catalog.folder": ctx.catalog, "ce.class": ctx.cls, "ce.crawl.id": ctx.crawl, "ce.score.id": doc["id"],
                 "ce.score.reason": reason, "ce.score.by": by, "ce.score.process": in_process()}
        try:
            with telemetry.job("score.run", attrs, carried=carried):
                if in_process():
                    finish_in_process(ctx, doc, p)
                else:
                    scores.finish(ctx, doc, p)
                telemetry.set({"ce.score.status": doc.get("status"), "ce.error.detail": doc.get("error")})
        finally:
            self._busy.pop(key, None)

    def _quietly(self, ctx: Ctx, golden: str | None, by: str, reason: str, trigger: str = "manual",
                 properties: list[str] | None = None) -> dict | None:
        try:
            return self.start(ctx, golden, by=by, reason=reason, trigger=trigger, properties=properties)
        except UserError as e:
            print(f"score ({ctx.catalog}, {reason}): {e}")
            return None

    # -- the loop -------------------------------------------------------------------------------------------
    def loop(self, studio, stop: threading.Event) -> None:
        self.recover(studio)
        while not stop.is_set():
            self.tick(studio)
            stop.wait(EVERY)

    def recover(self, studio) -> None:
        for c, cls in _catalogs(studio):
            try:
                ctx = studio.ctx(c, cls)
                ctx.invalidate()
                gone = scores.interrupt_running(ctx)
                if gone:
                    print(f"scores ({c}): interrupted by the restart: {', '.join(gone)}")
            except UserError:
                pass

    def tick(self, studio) -> None:
        """One pass over the catalogs and their classes: a new extract output, then a pending score that is due."""
        for folder, cls in _catalogs(studio):
            catalog = studio.ctx(folder, cls)
            try:
                self._check(catalog, folder, cls)
            except UserError as e:
                print(f"scores ({folder}, {cls}): {e}")
            except Exception:  # noqa: BLE001 - the loop keeps going
                traceback.print_exc()

    def _check(self, catalog: Ctx, folder: str, cls: str) -> None:
        catalog.invalidate()
        entry, _ = scores.see_output(catalog)
        latest = scores.latest_golden(catalog)
        if entry and latest and not self.busy(folder, cls):
            self._score_what_is_new(catalog, entry, latest)
        self._score_pending(catalog, entry, folder, cls)

    def _score_what_is_new(self, catalog: Ctx, entry: dict, latest: str) -> None:
        if not scores.scored_output(catalog, entry["id"]):  # an output this class hasn't scored yet: every property
            self._quietly(catalog, None, "the Studio", f"a new extract output, {entry['id']}", "new-output")
        elif not scores.scored_against(catalog, entry["id"], latest):
            # a golden dataset published outside the Studio's approve (`golden-datasets golden publish`)
            self._quietly(catalog, None, "the Studio", f"a new golden dataset, {latest}", "golden-published",
                          scores.changed_columns(catalog, latest))

    def _score_pending(self, catalog: Ctx, entry: dict | None, folder: str, cls: str) -> None:
        due = scores.pending(catalog)
        if due and entry and not self.busy(folder, cls):
            scores.done_pending(catalog)
            self._quietly(catalog, scores.HUMAN_REVIEWED, "the Studio", due.get("reason") or "reviews",
                          "golden-published", due.get("columns"))
        elif due and not entry:
            scores.done_pending(catalog)  # no extract output to score


def finish_in_process(ctx: Ctx, doc: dict, p) -> None:
    """Run `scores.finish` in a spawned process and wait for it; a process that dies (killed, out of memory) leaves
    the score `failed`, saying so."""
    proc = multiprocessing.get_context("spawn").Process(
        target=_child, name=f"score-{ctx.catalog}-{doc['id']}",
        args=(ctx.root.uri, ctx.catalog, ctx.crawl, ctx.cls, doc, p.golden, p.output, (p.records.root.uri, p.records.base),
              p.pair))
    proc.start()
    proc.join()
    telemetry.set({"process.exit.code": proc.exitcode})
    if proc.exitcode != 0:
        _fail_if_still_running(ctx, doc, proc.exitcode)


def _child(root_uri: str, catalog: str, crawl: str, cls: str, doc: dict, golden, output: dict, records: tuple,
           pair: str) -> None:
    """A score's own process: the same `scores.finish`, from what the server prepared."""
    from ..context import Ctx as _Ctx
    from ..storage import open_root

    ctx = _Ctx(open_root(root_uri), catalog, crawl, cls=cls)
    store = scores.RecordsStore(open_root(records[0]), records[1], catalog, crawl, cls)
    scores.finish(ctx, doc, scores.Prepared(golden, output, store, pair))


def _fail_if_still_running(ctx: Ctx, doc: dict, exitcode: int | None) -> None:
    try:
        now = scores.read(ctx, doc["id"])
    except Exception:  # noqa: BLE001 - the score file is what we are fixing
        now = None
    if not now or now.get("status") == "running":
        doc["status"], doc["error"] = "failed", f"the score's process ended with exit code {exitcode}"
        doc["finished_at"] = scores._now()
        scores._write(ctx, doc)


def _catalogs(studio) -> list[tuple[str, str]]:
    """(catalog, class) for each catalog with a crawl and each class it has rules for."""
    from ..manifest import has_rules, load

    out = []
    for c in load(studio.root)[0].get("catalogs", []):
        if c.get("current_crawl"):
            out += [(c["catalog"], cls) for cls in sorted(c.get("classes") or {}) if has_rules(c, cls)]
    return out
