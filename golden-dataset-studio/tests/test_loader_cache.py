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
