from __future__ import annotations

import pytest

from common.polite import WorkerPacer, backoff_delay


def test_backoff_doubles_from_the_minimum_and_stops_at_the_maximum() -> None:
    waits = [
        backoff_delay(retry, min_interval=1, max_interval=5)
        for retry in range(1, 6)
    ]
    assert waits == [1, 2, 4, 5, 5]


def test_backoff_uses_production_defaults() -> None:
    waits = [
        backoff_delay(retry, min_interval=180, max_interval=3600)
        for retry in range(1, 6)
    ]
    assert waits == [180, 360, 720, 1440, 2880]


def test_retry_after_lengthens_one_wait_but_never_past_the_maximum() -> None:
    assert backoff_delay(1, min_interval=1, max_interval=5, retry_after=3) == 3
    assert backoff_delay(1, min_interval=1, max_interval=5, retry_after=900) == 5
    # A Retry-After shorter than the backoff does not shorten it.
    assert backoff_delay(3, min_interval=1, max_interval=5, retry_after=1) == 4


def test_backoff_counts_the_first_retry_as_one() -> None:
    with pytest.raises(ValueError, match="retry is 1"):
        backoff_delay(0, min_interval=1, max_interval=5)


def test_the_first_fetch_of_a_worker_never_waits() -> None:
    slept: list[float] = []
    pacer = WorkerPacer(180, sleep=slept.append, monotonic=lambda: 100.0)
    assert pacer.wait() == 0
    assert slept == []


def test_a_worker_waits_out_its_own_interval_before_the_next_fetch() -> None:
    slept: list[float] = []
    clock = [100.0]
    pacer = WorkerPacer(
        180, sleep=slept.append, monotonic=lambda: clock[0]
    )
    pacer.wait()
    pacer.record_fetch()
    clock[0] = 150.0
    assert pacer.wait() == pytest.approx(130.0)
    assert slept == [pytest.approx(130.0)]

    pacer.record_fetch()
    clock[0] = 400.0
    assert pacer.wait() == 0


def test_a_zero_interval_never_sleeps() -> None:
    slept: list[float] = []
    pacer = WorkerPacer(0, sleep=slept.append, monotonic=lambda: 0.0)
    pacer.record_fetch()
    assert pacer.wait() == 0
    assert slept == []


def test_a_negative_interval_is_rejected() -> None:
    with pytest.raises(ValueError, match="min_interval"):
        WorkerPacer(-1)
