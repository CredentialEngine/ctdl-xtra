"""A log line every so many items, saying how far a long loop has got."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from common.clock import format_duration


class Progress:
    """One INFO line every `every` items and one at the last, with time left."""

    def __init__(
        self,
        logger: logging.Logger,
        phase: str,
        total: int,
        *,
        every: int,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.logger = logger
        self.phase = phase
        self.total = total
        self.every = every
        self.monotonic = monotonic
        self.started = monotonic()

    def step(self, done: int) -> None:
        if done % self.every and done != self.total:
            return
        elapsed = self.monotonic() - self.started
        eta = elapsed / done * (self.total - done)
        self.logger.info(
            "%s %s/%s (%s%%) elapsed=%s eta=%s",
            self.phase,
            done,
            self.total,
            done * 100 // self.total,
            format_duration(elapsed),
            format_duration(eta),
        )
