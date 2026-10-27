"""Background jobs for the Evals tab: an xtra run or an eval, one at a time per catalog.

A job runs in a thread of the server process. Its log is kept in memory (the UI polls the tail) and written to
`<cache>/jobs/<id>.log`. Cancelling terminates the xtra-cli subprocess it is waiting on.
"""

from __future__ import annotations

import itertools
import subprocess
import threading
import time
import traceback
from collections.abc import Callable

from ..errors import UserError
from ..storage import cache_home

MAX_LINES = 2000


class Job:
    def __init__(self, jid: str, catalog: str, kind: str, label: str):
        self.id, self.catalog, self.kind, self.label = jid, catalog, kind, label
        self.status = "running"  # running · done · failed · cancelled
        self.lines: list[str] = []
        self.result: dict | None = None
        self.error: str | None = None
        self.started = time.time()
        self.finished: float | None = None
        self.proc: subprocess.Popen | None = None
        self.cancelled = False
        self.file = cache_home() / "jobs" / f"{jid}.log"
        self.file.parent.mkdir(parents=True, exist_ok=True)

    def log(self, line: str) -> None:
        self.lines.append(line)
        del self.lines[:-MAX_LINES]
        with self.file.open("a") as f:
            f.write(line + "\n")

    def doc(self, tail: int = 200) -> dict:
        return {"id": self.id, "catalog": self.catalog, "kind": self.kind, "label": self.label, "status": self.status,
                "error": self.error, "result": self.result, "started": self.started, "finished": self.finished,
                "log": self.lines[-tail:]}


class Jobs:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._n = itertools.count(1)

    def running(self, catalog: str) -> Job | None:
        return next((j for j in self._jobs.values() if j.catalog == catalog and j.status == "running"), None)

    def start(self, catalog: str, kind: str, label: str, work: Callable[[Job], dict]) -> Job:
        with self._lock:
            busy = self.running(catalog)
            if busy:
                raise UserError(f"{busy.label} is still running")
            job = Job(f"job-{time.strftime('%Y%m%d-%H%M%S')}-{next(self._n)}", catalog, kind, label)
            self._jobs[job.id] = job

        def run() -> None:
            try:
                job.result = work(job)
                job.status = "cancelled" if job.cancelled else "done"
            except Exception as e:  # noqa: BLE001 - every failure ends up in the job's log
                job.status = "cancelled" if job.cancelled else "failed"
                job.error = str(e)
                if not isinstance(e, UserError):
                    job.log(traceback.format_exc())
            finally:
                job.finished = time.time()

        threading.Thread(target=run, name=job.id, daemon=True).start()
        return job

    def get(self, jid: str) -> Job | None:
        return self._jobs.get(jid)

    def recent(self, catalog: str, n: int = 10) -> list[Job]:
        return sorted((j for j in self._jobs.values() if j.catalog == catalog), key=lambda j: -j.started)[:n]

    def cancel(self, jid: str) -> Job | None:
        job = self._jobs.get(jid)
        if job and job.status == "running":
            job.cancelled = True
            if job.proc and job.proc.poll() is None:
                job.proc.terminate()
        return job
