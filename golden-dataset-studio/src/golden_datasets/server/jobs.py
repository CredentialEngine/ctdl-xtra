"""Scores as durable jobs (Evals spec §4): `score.json` is written `running`, the scorer runs in a thread of the server,
and the file says `done` or `failed`. One score runs per catalog at a time; on start, a score a restart left
`running` becomes `interrupted`.

A loop checks every 30 s, and once on start: for each catalog, a new extract output (copied, then scored against the
latest golden dataset) and `scores/pending.json` (when due, the latest extract output against the human-reviewed
values; then the file is deleted).
"""

from __future__ import annotations

import threading
import traceback

from .. import scores
from ..context import Ctx
from ..errors import UserError

EVERY = 30.0  # seconds


class ScoreJobs:
    def __init__(self):
        self._busy: dict[str, str] = {}  # catalog → the score running
        self._lock = threading.Lock()

    def busy(self, catalog: str) -> str | None:
        return self._busy.get(catalog)

    def start(self, ctx: Ctx, golden: str | None, output: str | None = None, by: str = "", reason: str = "",
              wait: bool = False) -> dict:
        """The score of this pair: the existing one, or a new one started in a thread (`running`). Raises UserError
        while another score of the catalog runs."""
        with self._lock:
            if ctx.catalog in self._busy:
                raise UserError(f"{self._busy[ctx.catalog]} is still running")
            self._busy[ctx.catalog] = "a score"
        try:
            p = scores.prepare(ctx, golden, output, log=print)
            doc = scores.existing(ctx, p)
            if doc:
                self._busy.pop(ctx.catalog, None)
                return doc
            doc = scores.begin(ctx, p, by, reason)
            self._busy[ctx.catalog] = doc["id"]
        except BaseException:
            self._busy.pop(ctx.catalog, None)
            raise

        def run() -> None:
            try:
                scores.finish(ctx, doc, p)
            finally:
                self._busy.pop(ctx.catalog, None)

        t = threading.Thread(target=run, name=f"score-{ctx.catalog}-{doc['id']}", daemon=True)
        t.start()
        if wait:
            t.join()
        return doc

    def after_publish(self, ctx: Ctx, by: str) -> dict | None:
        """Approving a column publishes it, then scores the latest extract output against the latest golden dataset
        (Evals spec §4.1). None when there is nothing to score."""
        return self._quietly(ctx, None, by, "a column was published")

    def _quietly(self, ctx: Ctx, golden: str | None, by: str, reason: str) -> dict | None:
        try:
            return self.start(ctx, golden, by=by, reason=reason)
        except UserError as e:
            print(f"score ({ctx.catalog}, {reason}): {e}")
            return None

    # -- the loop -------------------------------------------------------------------------------------------
    def tick(self, studio) -> None:
        """One pass over the catalogs: a new extract output, then a pending score that is due."""
        for catalog in (studio.ctx(c) for c in _catalogs(studio)):
            try:
                catalog.invalidate()
                entry, new = scores.see_output(catalog)
                if new and scores.latest_golden(catalog):
                    self._quietly(catalog, None, "the Studio", f"a new extract output, {entry['id']}")
                due = scores.pending(catalog)
                if due and entry and not self.busy(catalog.catalog):
                    scores.done_pending(catalog)
                    self._quietly(catalog, scores.HUMAN_REVIEWED, "the Studio", due.get("reason") or "reviews")
                elif due and not entry:
                    scores.done_pending(catalog)  # no extract output to score
            except UserError as e:
                print(f"scores ({catalog.catalog}): {e}")
            except Exception:  # noqa: BLE001 - the loop keeps going
                traceback.print_exc()

    def recover(self, studio) -> None:
        for c in _catalogs(studio):
            try:
                ctx = studio.ctx(c)
                ctx.invalidate()
                gone = scores.interrupt_running(ctx)
                if gone:
                    print(f"scores ({c}): interrupted by the restart: {', '.join(gone)}")
            except UserError:
                pass

    def loop(self, studio, stop: threading.Event) -> None:
        self.recover(studio)
        while not stop.is_set():
            self.tick(studio)
            stop.wait(EVERY)


def _catalogs(studio) -> list[str]:
    from ..manifest import load

    return [c["catalog"] for c in load(studio.root)[0].get("catalogs", []) if c.get("current_crawl")]
