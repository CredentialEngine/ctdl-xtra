"""What a slow request competed for (telemetry.Resources, the gc hook) and how big its catalog is (Snapshot.sizes):
the attributes that let a trace show whether time went to CPU, to other requests, to memory or to the catalog's size."""

from __future__ import annotations

import contextvars

from test_golden_versions import CAT, studio  # noqa: F401  (studio: the fixture)
from test_telemetry import _server_spans, no_otel_env, traced  # noqa: F401  (fixtures)

from golden_datasets import telemetry
from golden_datasets.context import Ctx
from golden_datasets.review import LOADER, _Recent


def _counting(monkeypatch) -> dict:
    """Telemetry on, with this test's own request counters."""
    monkeypatch.setattr(telemetry, "_enabled", True)
    counters: dict = {}
    telemetry._counters.set(counters)
    return counters


def test_a_request_says_how_much_cpu_and_memory_it_took_and_who_it_shared_them_with(traced):  # noqa: F811
    c, exporter = traced
    assert c.get("/api/profiles").status_code == 200
    a = _server_spans(exporter)[-1].attributes
    assert a["ce.process.cpu.duration_ms"] >= 0 and a["ce.process.cpu.utilization"] >= 0
    assert a["ce.http.inflight"] == 1 and a["ce.http.inflight.max"] == 1  # alone
    assert a["ce.process.memory.peak_mb"] > 0


def test_inflight_max_counts_requests_that_started_later():
    first = telemetry.Resources.start()
    second = telemetry.Resources.start()
    assert (first.inflight, second.inflight) == (1, 2)
    second_attrs = second.end()
    third = telemetry.Resources.start()  # starts after the second ended: two at once again, not three
    first_attrs = first.end()
    third.close()
    assert second_attrs["ce.http.inflight.max"] == 2
    assert first_attrs["ce.http.inflight"] == 1 and first_attrs["ce.http.inflight.max"] == 2
    assert telemetry.Resources._active == []


def test_a_garbage_collection_counts_on_the_request_that_triggered_it(monkeypatch):
    def run():
        counters = _counting(monkeypatch)
        telemetry._on_gc("start", {"generation": 2})
        telemetry._on_gc("stop", {"generation": 2})
        return counters
    counters = contextvars.copy_context().run(run)
    assert counters["stats.gc.collections"] == 1 and counters["stats.gc.gen2"] == 1
    assert counters["stats.gc.duration_ms"] >= 0


def test_a_rule_pushed_out_of_the_per_rule_cache_is_counted(monkeypatch):
    def run():
        counters = _counting(monkeypatch)
        recent = _Recent()
        for i in range(_Recent.RULES_KEPT + 3):
            recent[f"rule-{i}"] = i
        return counters
    assert contextvars.copy_context().run(run)["stats.rule_cache.evictions"] == 3


def test_a_catalogs_size_is_counted_once_per_snapshot(studio):  # noqa: F811
    _, ctx, _ = studio
    rv = LOADER.review(Ctx(ctx.root, CAT))
    sizes = rv.snap.sizes()
    assert sizes["ce.catalog.records"] > 0 and sizes["ce.snapshot.pages"] > 0 and sizes["ce.rules.count"] > 0
    assert sizes["ce.snapshot.matches"] >= sizes["ce.catalog.records"] - 1
    assert sizes["ce.snapshot.occurrences"] >= sizes["ce.catalog.records"]
    assert rv.snap.sizes() is sizes  # worked out once
    occupancy = LOADER.occupancy()
    assert occupancy["ce.snapshot.cached.count"] >= 1 and occupancy["ce.snapshot.budget.rows"] == LOADER.budget
