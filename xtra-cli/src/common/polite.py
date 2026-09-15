"""Polite fetch pacing for long-running catalog crawls."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PoliteLimiter:
    """Serial-by-default limiter with a minimum gap and exponential backoff.

    Production crawls refresh thousands of catalogs. Default concurrency is 1
    and the default gap is 3 minutes so we do not trip bot detectors.
    """

    concurrency: int = 1
    min_interval: float = 180.0
    backoff_base: float = 180.0
    backoff_max: float = 3600.0

    def __post_init__(self) -> None:
        if self.concurrency < 1:
            raise ValueError("concurrency must be >= 1")
        if self.min_interval < 0 or self.backoff_base < 0 or self.backoff_max < 0:
            raise ValueError("intervals must be >= 0")
        self._sema = threading.Semaphore(self.concurrency)
        self._lock = threading.Lock()
        self._next_mono = 0.0

    def _arm_interval(self) -> float:
        with self._lock:
            now = time.monotonic()
            sleep_for = max(0.0, self._next_mono - now)
            start = max(now, self._next_mono)
            self._next_mono = start + self.min_interval
        if sleep_for:
            logger.info("polite crawl: waiting %.1fs before next page", sleep_for)
            time.sleep(sleep_for)
        return sleep_for

    def wait_turn(self) -> float:
        """Block until a fetch slot and the minimum interval have elapsed."""
        with self.occupy() as slept:
            return slept

    @contextmanager
    def occupy(self) -> Iterator[float]:
        """Hold a concurrency slot for one page fetch, after the polite gap."""
        self._sema.acquire()
        try:
            yield self._arm_interval()
        finally:
            self._sema.release()

    def backoff_sleep(self, attempt: int) -> float:
        """Sleep  base * 2**attempt  seconds, capped at backoff_max."""
        delay = min(self.backoff_max, self.backoff_base * (2**attempt))
        if delay > 0:
            logger.warning(
                "polite crawl: backoff %.1fs after failed fetch (attempt %s)",
                delay,
                attempt + 1,
            )
            time.sleep(delay)
        return delay
