"""The snapshot cache is bounded: least recently used extractions go once the kept ones' values pass the budget or
there are more than `MAX_SNAPSHOTS`; the two most recent always stay; a Review goes with its snapshot; room is made
before a big extraction loads."""

from __future__ import annotations

import pytest

from golden_datasets import review
from golden_datasets.review import Loader

ROWS = {"a": 300, "b": 300, "c": 300, "d": 10, "e": 10, "f": 10, "big": 900}


class FakeCtx:
    root = type("R", (), {"uri": "mem://"})()
    catalog, crawl = "cat", "k"

    def extraction_meta(self, ext):
        return {"files": {"matches.parquet": {"rows": ROWS[ext]}, "occurrences.parquet": {"rows": 0}}}


@pytest.fixture
def loads(monkeypatch):
    loaded = []

    class FakeSnapshot:
        def __init__(self, ctx, ext):
            loaded.append((ext, len(LOADER._snaps)))  # how many were kept while this one loaded
            self.ext, self.meta = ext, ctx.extraction_meta(ext)

    monkeypatch.setattr(review, "Snapshot", FakeSnapshot)
    LOADER = Loader(budget=650)
    return LOADER, loaded


def kept(loader):
    return [k[2] for k in loader.cached_extractions()]


def test_the_least_recently_used_snapshots_go_past_the_budget(loads):
    loader, _ = loads
    ctx = FakeCtx()
    loader.snapshot(ctx, "a"), loader.snapshot(ctx, "b")
    loader.snapshot(ctx, "a")  # a used again: b is now the oldest
    loader.snapshot(ctx, "c")
    assert kept(loader) == ["a", "c"]


def test_at_most_max_snapshots_however_small(loads):
    loader, _ = loads
    ctx = FakeCtx()
    for ext in "def":
        loader.snapshot(ctx, ext)
    loader.snapshot(ctx, "a"), loader.snapshot(ctx, "d")
    assert kept(loader) == ["e", "f", "a", "d"]
    loader.snapshot(ctx, "b")
    assert kept(loader) == ["f", "a", "d", "b"]  # e (oldest) went: 4 at most


def test_room_is_made_before_a_big_one_loads_and_the_most_recent_stays(loads):
    loader, loaded = loads
    ctx = FakeCtx()
    loader.snapshot(ctx, "a"), loader.snapshot(ctx, "b")
    loader.snapshot(ctx, "big")  # over the budget on its own: it stays, with the one before it dropped first
    assert loaded[-1] == ("big", 1) and kept(loader) == ["b", "big"]
    assert loader.snapshot(ctx, "big") is loader.snapshot(ctx, "big")  # cached: no reload
    assert [x for x, _ in loaded].count("big") == 1


def test_a_review_goes_with_its_snapshot(loads):
    loader, _ = loads
    ctx = FakeCtx()
    snap = loader.snapshot(ctx, "a")
    rv = type("Rv", (), {"snap": snap, "parent": None})()
    loader._reviews[("mem://", "cat", "k", "a", True, 0)] = rv
    loader.snapshot(ctx, "b"), loader.snapshot(ctx, "c")
    assert "a" not in kept(loader) and not loader._reviews


def test_per_rule_caches_keep_only_the_most_recent_rules():
    c = review._Recent()
    for i in range(review._Recent.RULES_KEPT):
        c[f"r{i}"] = i
    assert c["r0"] == 0  # used: now the most recent
    c["new"] = 99
    assert "r1" not in c and "r0" in c and "new" in c and len(c) == review._Recent.RULES_KEPT


def test_a_tables_repeated_strings_are_one_object():
    rows = review._shared([{"rule_id": "".join(["course-", "name"]), "n": 1},
                           {"rule_id": "".join(["course-", "name"]), "n": 2}])
    assert rows[0]["rule_id"] is rows[1]["rule_id"] and rows[1]["n"] == 2


def test_concurrent_requests_load_an_extraction_once_and_one_extraction_at_a_time(monkeypatch):
    """Two people opening WVU at once used to build two ~1.3 GB copies, and cold loads of different catalogs ran
    side by side; together they got the server OOM-killed (2026-11-12)."""
    import threading
    import time

    loading, peak, loaded = [0], [0], []
    guard = threading.Lock()

    class SlowSnapshot:
        def __init__(self, ctx, ext):
            with guard:
                loading[0] += 1
                peak[0] = max(peak[0], loading[0])
                loaded.append(ext)
            time.sleep(0.05)
            with guard:
                loading[0] -= 1
            self.ext, self.meta = ext, ctx.extraction_meta(ext)

    monkeypatch.setattr(review, "Snapshot", SlowSnapshot)
    loader, ctx = Loader(budget=10_000), FakeCtx()
    got: list = []
    threads = [threading.Thread(target=lambda e=e: got.append(loader.snapshot(ctx, e))) for e in "aaaabbcd" * 2]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(loaded) == ["a", "b", "c", "d"]  # each extraction built once
    assert peak[0] == 1  # never two at once
    assert len({id(s) for s in got if s.ext == "a"}) == 1  # everyone got the same copy
