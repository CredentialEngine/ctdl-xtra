"""Polite fetch pacing for long-running catalog crawls.

Pacing is per worker, not global: each worker thread waits out its own
minimum interval, and retries back off from that same minimum up to the
maximum. Crawling a catalog is a rare, one-time job, so the defaults are
slow on purpose.
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable

# Waits are the minimum plus a random 0-25% of it: 180 s becomes 180-225 s.
PACING_JITTER_FRACTION = 0.25


def jittered(
    seconds: float,
    *,
    jitter_fraction: float,
    ceiling: float | None = None,
    uniform: Callable[[float, float], float] = random.uniform,
) -> float:
    """Return `seconds` plus a random 0 to `jitter_fraction` of it.

    Jitter only adds, so the result is never less than `seconds`.
    `ceiling` caps the total, but never below `seconds`: a wait already
    at or above the ceiling comes back unchanged, with no jitter.
        jittered(180, jitter_fraction=0.25)               -> 180 to 225
    """
    if jitter_fraction <= 0 or seconds <= 0:
        return float(seconds)
    delay = seconds + uniform(0.0, seconds * jitter_fraction)
    if ceiling is not None:
        delay = min(delay, max(seconds, ceiling))
    return float(delay)


def backoff_delay(
    retry: int,
    *,
    min_interval: float,
    max_interval: float,
    retry_after: float | None = None,
    jitter_fraction: float = 0.0,
    uniform: Callable[[float, float], float] = random.uniform,
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
    return jittered(
        delay,
        jitter_fraction=jitter_fraction,
        ceiling=max_interval,
        uniform=uniform,
    )


class WorkerPacer:
    """Minimum gap between the GETs of one worker thread.

    One instance per thread, so it needs no lock. Time sources are injected
    so tests can assert the waits without spending them.
    """

    def __init__(
        self,
        min_interval: float,
        *,
        jitter_fraction: float = 0.0,
        max_interval: float | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        if min_interval < 0:
            raise ValueError("min_interval must be >= 0")
        if jitter_fraction < 0:
            raise ValueError("jitter_fraction must be >= 0")
        self.min_interval = float(min_interval)
        self.jitter_fraction = float(jitter_fraction)
        self.max_interval = max_interval
        self._sleep = sleep
        self._monotonic = monotonic
        self._uniform = uniform
        self._lock = threading.Lock()
        self._next_at: float | None = None

    def _gap(self) -> float:
        return jittered(
            self.min_interval,
            jitter_fraction=self.jitter_fraction,
            ceiling=self.max_interval,
            uniform=self._uniform,
        )

    def wait(self, at_least: float = 0.0) -> float:
        with self._lock:
            now = self._monotonic()
            sleep_for = float(at_least)
            if self._next_at is not None:
                sleep_for = max(sleep_for, self._next_at - now)
            sleep_for = max(sleep_for, 0.0)
            self._next_at = now + sleep_for + self._gap()
        if sleep_for > 0:
            self._sleep(sleep_for)
        return sleep_for

    def record_fetch(self) -> None:
        with self._lock:
            after = self._monotonic() + self._gap()
            if self._next_at is None or after > self._next_at:
                self._next_at = after
