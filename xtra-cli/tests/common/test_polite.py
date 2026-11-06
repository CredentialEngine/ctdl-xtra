from __future__ import annotations

import random
from concurrent.futures import ThreadPoolExecutor

import pytest

from common.polite import WorkerPacer, backoff_delay, jittered


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
    assert (
        backoff_delay(1, min_interval=1, max_interval=5, retry_after=900) == 5
    )
    # A Retry-After shorter than the backoff does not shorten it.
    assert backoff_delay(3, min_interval=1, max_interval=5, retry_after=1) == 4


def test_backoff_counts_the_first_retry_as_one() -> None:
    with pytest.raises(ValueError, match="retry is 1"):
        backoff_delay(0, min_interval=1, max_interval=5)


class Clock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def pacer_on(clock: Clock, min_interval: float = 180, **options) -> WorkerPacer:
    return WorkerPacer(
        min_interval,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        **options,
    )


def test_the_first_get_of_a_crawl_never_waits() -> None:
    clock = Clock(100.0)
    assert pacer_on(clock).wait() == 0
    assert clock.slept == []


def test_one_worker_waits_a_gap_after_its_last_get_finished() -> None:
    clock = Clock(100.0)
    pacer = pacer_on(clock)
    pacer.wait()
    clock.now = 110.0
    pacer.record_fetch()
    clock.now = 150.0
    assert pacer.wait() == pytest.approx(140.0)
    assert clock.now == pytest.approx(290.0)


def test_a_slow_page_never_shortens_the_pause_the_site_gets() -> None:
    """The gap runs from the end of the GET, not from its start."""
    clock = Clock()
    pacer = pacer_on(clock)
    pacer.wait()
    clock.now = 50.0
    pacer.record_fetch()
    assert pacer.wait() == pytest.approx(180.0)
    assert clock.now == pytest.approx(230.0)


def test_callers_of_one_pacer_take_turns() -> None:
    """Three calls at once are handed turns at 0, 180 and 360 seconds."""
    pacer = WorkerPacer(180, sleep=lambda seconds: None, monotonic=lambda: 0.0)
    assert [pacer.wait() for _ in range(3)] == [0, 180, 360]


def test_turns_are_handed_out_once_each_under_real_threads() -> None:
    clock = Clock()
    pacer = WorkerPacer(
        180, sleep=lambda seconds: None, monotonic=clock.monotonic
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        waits = sorted(pool.map(lambda _: pacer.wait(), range(8)))
    assert waits == [180.0 * n for n in range(8)]


def test_a_retry_waits_its_backoff_or_its_turn_whichever_is_longer() -> None:
    clock = Clock()
    pacer = pacer_on(clock)
    pacer.wait()
    pacer.record_fetch()
    assert pacer.wait(360) == 360
    pacer.record_fetch()
    other = pacer.wait()
    assert other == 180
    assert pacer.wait(10) == 180


def test_a_zero_interval_never_sleeps() -> None:
    clock = Clock()
    pacer = pacer_on(clock, 0)
    for _ in range(3):
        pacer.wait()
        pacer.record_fetch()
    assert clock.slept == []


def test_a_negative_interval_is_rejected() -> None:
    with pytest.raises(ValueError, match="min_interval"):
        WorkerPacer(-1)


def test_there_is_no_clock_shared_by_the_whole_site() -> None:
    """Each worker keeps its own; workers wait for IP rotation."""
    from common import polite

    assert not hasattr(polite, "SitePacer")


def highest(low: float, high: float) -> float:
    return high


def lowest(low: float, high: float) -> float:
    return low


def test_jitter_adds_up_to_its_fraction_and_never_takes_away() -> None:
    assert jittered(180, jitter_fraction=0.25, uniform=lowest) == 180
    assert jittered(180, jitter_fraction=0.25, uniform=highest) == 225


def test_no_jitter_is_the_exact_wait() -> None:
    assert jittered(180, jitter_fraction=0, uniform=highest) == 180
    assert jittered(0, jitter_fraction=0.25, uniform=highest) == 0


def test_jitter_never_passes_the_ceiling_or_cuts_below_the_wait() -> None:
    assert jittered(4, jitter_fraction=0.5, ceiling=5, uniform=highest) == 5
    # A wait already at the ceiling stays there.
    assert jittered(5, jitter_fraction=0.5, ceiling=5, uniform=highest) == 5


def test_real_jitter_stays_in_range_and_is_not_one_fixed_beat() -> None:
    draws = random.Random(7)
    waits = [
        jittered(10, jitter_fraction=0.25, uniform=draws.uniform)
        for _ in range(200)
    ]
    assert all(10 <= wait <= 12.5 for wait in waits)
    assert len(set(waits)) > 100


def test_backoff_jitter_is_added_after_the_doubling_and_capped() -> None:
    waits = [
        backoff_delay(
            retry,
            min_interval=1,
            max_interval=5,
            jitter_fraction=0.25,
            uniform=highest,
        )
        for retry in range(1, 6)
    ]
    assert waits == [1.25, 2.5, 5, 5, 5]


def test_backoff_jitter_never_cuts_a_retry_after_short() -> None:
    wait = backoff_delay(
        1,
        min_interval=1,
        max_interval=60,
        retry_after=30,
        jitter_fraction=0.25,
        uniform=lowest,
    )
    assert wait == 30


def test_a_pacer_with_jitter_waits_the_minimum_plus_its_draw() -> None:
    clock = Clock(100.0)
    pacer = pacer_on(clock, jitter_fraction=0.25, uniform=highest)
    pacer.record_fetch()
    assert pacer.wait() == 225
    assert clock.slept == [225]


def test_a_pacer_draws_a_new_gap_for_every_turn() -> None:
    draws = iter([0.0, 0.0, 40.0, 40.0, 10.0, 10.0, 0.0])
    clock = Clock()
    pacer = pacer_on(
        clock, jitter_fraction=0.25, uniform=lambda low, high: next(draws)
    )
    for _ in range(3):
        pacer.wait()
        pacer.record_fetch()
    pacer.wait()
    assert clock.slept == [180, 220, 190]


def test_a_pacer_with_negative_jitter_is_refused() -> None:
    with pytest.raises(ValueError, match="jitter_fraction"):
        WorkerPacer(180, jitter_fraction=-0.1)
