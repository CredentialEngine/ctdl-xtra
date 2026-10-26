"""The catalogs the app can review: crawl runs that have a ruleset.

A ruleset lives at ``review-ui-index/rulesets/<dir>/rules.json`` and names its ``catalog_folder``;
every crawl run with that catalog folder is a catalog the landing page offers.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass

from .extract import latest_extraction, review_sessions
from .review import ReviewSession
from .rulesets import read_rulesets
from .runs import CrawlRun, find_runs
from .store import Store
from .template import load_template


@dataclass(frozen=True)
class Catalog:
    cid: str  # url-safe id, used in /api/c/<cid>/...
    run: CrawlRun
    ruleset_key: str | None
    ruleset: dict | None
    ruleset_error: str | None = None


def cid_of(run: CrawlRun) -> str:
    return re.sub(
        r"[^a-z0-9]+", "-", f"{run.catalog_folder}-{run.run_id}".lower()
    ).strip("-")


def discover(
    store: Store, known_properties: set[str], extra_run: CrawlRun | None = None
) -> list[Catalog]:
    """Every crawl run that has a ruleset in the root, plus ``extra_run`` (from ``--run``)."""
    runs = find_runs(store)
    catalogs: list[Catalog] = []
    for published in read_rulesets(store, known_properties):
        matching = sorted(
            (r for r in runs if r.catalog_folder == published.catalog_folder),
            key=lambda r: r.run_id,
            reverse=True,
        )
        catalogs += [
            Catalog(cid_of(r), r, published.key, published.ruleset, published.error)
            for r in matching
        ]
    catalogs.sort(key=lambda c: c.ruleset_error is not None)  # broken rulesets last
    if extra_run and not any(c.run.key == extra_run.key for c in catalogs):
        catalogs.append(Catalog(cid_of(extra_run), extra_run, None, None))
    return catalogs


class CatalogIndex:
    """The catalogs the app offers, rediscovered from the storage root so that a crawl or
    ruleset published while the app runs appears without a restart. Cached for a few
    seconds, because discovery lists blobs when the root is Azure."""

    def __init__(
        self, store: Store, extra_run: CrawlRun | None = None, ttl: float = 5.0
    ):
        self._store, self._extra, self._ttl = store, extra_run, ttl
        self._lock = threading.Lock()
        self._catalogs: dict[str, Catalog] = {}
        self._loaded_at: float | None = None

    def _refresh(self) -> None:
        known = {p.name for p in load_template(self._store)}
        found = discover(self._store, known, self._extra)
        self._catalogs = {c.cid: c for c in found}
        self._loaded_at = time.monotonic()

    def all(self) -> list[Catalog]:
        with self._lock:
            stale = (
                self._loaded_at is None
                or time.monotonic() - self._loaded_at > self._ttl
            )
            if stale:
                self._refresh()
            return list(self._catalogs.values())

    def get(self, cid: str) -> Catalog | None:
        self.all()
        with self._lock:
            if cid not in self._catalogs:  # maybe published since the last look
                self._refresh()
            return self._catalogs.get(cid)


def summarize(store: Store, catalog: Catalog) -> dict:
    """What the landing page shows for one catalog, and whether it can be opened."""
    run = catalog.run
    pages = sum(n.endswith(".meta.json") for n in store.list_dir(f"{run.key}/pages"))
    extraction_id = latest_extraction(store, run.key)
    report = (
        store.read_json(f"{run.key}/extractions/{extraction_id}/report.json")
        if extraction_id
        else None
    )
    # An extraction made by the first app has no content_root in its frozen rules, so the
    # page pane could not show its pages.
    legacy = bool(
        extraction_id
        and "content_root"
        not in store.read_json(f"{run.key}/extractions/{extraction_id}/rules.json")
    )
    has_sample = bool(
        extraction_id
        and store.exists(f"{run.key}/extractions/{extraction_id}/sample.json")
    )

    hint = None
    if catalog.ruleset_error:
        hint = "The ruleset is invalid; run `review-ui-v2 check-rules` for details."
    elif not report:
        hint = f"Run `review-ui-v2 extract --run {run.key}` first."
    elif legacy:
        hint = (
            "The latest extraction was made by an older version of the app. Run "
            f"`review-ui-v2 extract --run {run.key}`. (The first app picks the newest "
            "extraction when it restarts; pin its current one with --extraction.)"
        )
    elif not has_sample:
        hint = (
            f"Run `review-ui-v2 sample --run {run.key}`, then `review-ui-v2 extract "
            f"--run {run.key}`."
        )

    return {
        "cid": catalog.cid,
        "catalog_folder": run.catalog_folder,
        "run_key": run.key,
        "run_id": run.run_id,
        "seed_url": run.seed_url,
        "pages": pages,
        "ruleset": (
            {
                "id": catalog.ruleset["ruleset_id"],
                "version": catalog.ruleset["version"],
                "rules": len(catalog.ruleset["field_rules"]),
            }
            if catalog.ruleset
            else None
        ),
        "ruleset_error": catalog.ruleset_error,
        "extraction": (
            {
                "id": extraction_id,
                "records": report["records"],
                "ruleset_version": report["ruleset"]["version"],
                # The rules changed after this extraction, so the review would be out of date.
                "legacy": legacy,
                "stale": bool(
                    catalog.ruleset
                    and report["ruleset"]["version"] != catalog.ruleset["version"]
                ),
            }
            if report
            else None
        ),
        "has_sample": has_sample,
        "ready": hint is None,
        "hint": hint,
        "review": _latest_review(store, run.key, extraction_id),
    }


def _latest_review(
    store: Store, run_key: str, extraction_id: str | None
) -> dict | None:
    """Progress of the newest review of the current extraction, without creating one."""
    for review_id in reversed(review_sessions(store, run_key)):
        session = store.read_json(f"{run_key}/review-ui/{review_id}/session.json")
        if session["extraction_id"] == extraction_id:
            return {
                "review_id": review_id,
                "counts": ReviewSession.open(store, run_key, review_id).counts(),
            }
    return None
