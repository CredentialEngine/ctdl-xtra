from __future__ import annotations

import time

from common.polite import PoliteLimiter


def test_zero_interval_does_not_sleep() -> None:
    limiter = PoliteLimiter(concurrency=1, min_interval=0, backoff_base=0, backoff_max=0)
    slept = limiter.wait_turn()
    assert slept == 0


def test_min_interval_spaces_turns() -> None:
    limiter = PoliteLimiter(
        concurrency=1, min_interval=0.05, backoff_base=0, backoff_max=0
    )
    start = time.monotonic()
    limiter.wait_turn()
    limiter.wait_turn()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.04


def test_backoff_doubles(monkeypatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("common.polite.time.sleep", lambda seconds: sleeps.append(seconds))
    limiter = PoliteLimiter(
        concurrency=1, min_interval=0, backoff_base=180, backoff_max=3600
    )
    limiter.backoff_sleep(0)
    limiter.backoff_sleep(1)
    limiter.backoff_sleep(2)
    assert sleeps == [180, 360, 720]
