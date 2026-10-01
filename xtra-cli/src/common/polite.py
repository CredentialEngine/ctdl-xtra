"""Polite fetch pacing for long-running catalog crawls.

Pacing is per worker, not global: each worker thread waits out its own
minimum interval, and retries back off from that same minimum up to the
maximum. Crawling a catalog is a rare, one-time job, so the defaults are
slow on purpose.
"""

from __future__ import annotations

import time
from collections.abc import Callable


def backoff_delay(
    retry: int,
    *,
    min_interval: float,
    max_interval: float,
    retry_after: float | None = None,
) -> float:
    """Seconds to wait before retry `retry`, counting the first retry as 1.

    min 1 and max 5 over five retries gives 1, 2, 4, 5, 5. A Retry-After
    header can lengthen one wait but never past the maximum.
    """
    if retry < 1:
        raise ValueError("retry is 1 for the first retry")
    delay = min(max_interval, min_interval * (2 ** (retry - 1)))
    if retry_after is not None and retry_after > delay:
        delay = min(max_interval, retry_after)
    return float(delay)


class WorkerPacer:
    """Minimum gap between the GETs of one worker thread.

    One instance per thread, so it needs no lock. Time sources are injected
    so tests can assert the waits without spending them.
    """

    def __init__(
        self,
        min_interval: float,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if min_interval < 0:
            raise ValueError("min_interval must be >= 0")
        self.min_interval = float(min_interval)
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_fetch: float | None = None

    def wait(self) -> float:
        """Block until this worker may GET again. Returns seconds slept."""
        if self._last_fetch is None or self.min_interval <= 0:
            return 0.0
        sleep_for = self._last_fetch + self.min_interval - self._monotonic()
        if sleep_for <= 0:
            return 0.0
        self._sleep(sleep_for)
        return sleep_for

    def record_fetch(self) -> None:
        """Mark that this worker has just issued a GET."""
        self._last_fetch = self._monotonic()
