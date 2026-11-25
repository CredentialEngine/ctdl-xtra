"""`_Recent`, the per-rule cache, is shared by request threads (sme-fixes spec §4, Q9.1). Unlocked, two threads that
add a rule at once both evict the same oldest one, and the second gets `KeyError` (`GET /annotators` failed with
`KeyError: 'course-keyword'`)."""

from __future__ import annotations

import contextlib
import sys
import threading

from golden_datasets import review


class _Unlocked(review._Recent):
    """`_Recent` as it was before the lock."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = contextlib.nullcontext()


def _hammer(cache: review._Recent, threads: int = 8, rounds: int = 4000) -> list[BaseException]:
    """Threads that use and add rules at once, as the Rules tab's requests do. Returns what they raised."""
    keys = [f"r{i}" for i in range(cache.RULES_KEPT + 4)]
    errors: list[BaseException] = []
    start = threading.Barrier(threads)

    def work(n: int) -> None:
        start.wait()
        try:
            for i in range(rounds):
                if errors:
                    return
                k = keys[(n * 7 + i) % len(keys)]
                cache[k] = i
                try:
                    cache[keys[(n + i) % len(keys)]]
                except KeyError:
                    pass  # not cached (or evicted by now): a miss, which callers handle by building it
        except BaseException as e:  # noqa: BLE001 - report anything the cache raised
            errors.append(e)

    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)  # switch threads as often as possible, so the race shows within a few rounds
    try:
        ts = [threading.Thread(target=work, args=(n,)) for n in range(threads)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
    finally:
        sys.setswitchinterval(old)
    return errors


def test_without_the_lock_threads_break_the_cache():
    seen: list[BaseException] = []
    for _ in range(50):  # a race: every try breaks it, with KeyError or "dictionary changed size during iteration"
        seen += _hammer(_Unlocked())
        if any(isinstance(e, KeyError) for e in seen):
            break
    assert seen and all(isinstance(e, (KeyError, RuntimeError)) for e in seen)
    assert any(isinstance(e, KeyError) for e in seen)


def test_with_the_lock_threads_share_the_cache():
    for _ in range(3):
        cache = review._Recent()
        assert _hammer(cache) == []
        assert len(cache) == review._Recent.RULES_KEPT
