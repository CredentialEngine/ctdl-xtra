"""Run a ruleset over every page of a crawl run and write the results.

Outputs, next to the crawl's ``pages/``:

    extractions/<ts>/rules.json  sample.json  pages.jsonl  report.json  records/*.json
    discovery/<ts>/labels.json
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

from . import engine
from .merge import label_id, merge_pages
from .normalize import values_match
from .runs import CrawlRun, PageRef, list_pages, now_ts, page_type_of, split_page
from .store import Store, open_store
from .template import TemplateProperty

WRITE_THREADS = 16
_RULESET: dict = {}
_STORE: Store | None = None


def _init_worker(ruleset: dict, root: Store | Path | str) -> None:
    global _RULESET, _STORE
    _RULESET, _STORE = ruleset, open_store(root)


def _extract_page(page: PageRef) -> dict:
    assert _STORE is not None
    main_html, _ = split_page(_STORE.read_text(page.html_key), _RULESET["content_root"])
    result = engine.run_page(_RULESET, page.url, main_html)
    result.update(
        stem=page.stem,
        page_type=page_type_of(page.url, _RULESET["page_types"]),
        has_main_content=main_html is not None,
    )
    return result


def review_sessions(store: Store, run_key: str) -> list[str]:
    """Review session ids for a run, oldest first."""
    return [
        name
        for name in store.list_dir(f"{run_key}/review-ui")
        if store.exists(f"{run_key}/review-ui/{name}/session.json")
    ]


def baseline_decisions(store: Store, run_key: str) -> dict[str, dict]:
    """Latest decision per key across all of a run's review sessions."""
    merged: dict[str, dict] = {}
    for session_id in review_sessions(store, run_key):
        key = f"{run_key}/review-ui/{session_id}/decisions.json"
        if store.exists(key):
            merged.update(store.read_json(key))
    return merged


def latest_flags(store: Store, run_key: str) -> dict[str, dict]:
    """Open flags of the most recent review session.

    Each session starts from the previous one's flags, so the latest session holds
    the full current set; taking only it means a flag cleared there stays cleared.
    """
    sessions = review_sessions(store, run_key)
    key = f"{run_key}/review-ui/{sessions[-1]}/flags.json" if sessions else None
    return store.read_json(key) if key and store.exists(key) else {}


def check_regressions(
    decisions: dict[str, dict], records: dict[str, dict], label_keys: set[str]
) -> dict:
    """Compare earlier reviewer decisions with fresh extraction results."""
    current = {
        f["field_id"]: f["value"]
        for record in records.values()
        for f in record["source_expected"]["fields"]
    }
    regressions, fixed, still_wrong, checked = [], 0, 0, 0
    for key, decision in decisions.items():
        status = decision["status"]
        if decision["kind"] == "label":
            if status == "accepted":
                checked += 1
                if key not in label_keys:
                    regressions.append(
                        {"key": key, "was": decision["value"], "now": None}
                    )
            continue
        now = current.get(key)
        if status == "accepted":
            checked += 1
            if not values_match(now, decision["value"]):
                regressions.append({"key": key, "was": decision["value"], "now": now})
        elif status in ("rejected", "missing") and decision.get("expected_value"):
            if values_match(now, decision["expected_value"]):
                fixed += 1
            else:
                still_wrong += 1
    return {
        "accepted_checked": checked,
        "regressions": regressions,
        "fixed": fixed,
        "still_wrong": still_wrong,
    }


def _fill_rates(results: list[dict]) -> dict:
    fill: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for result in results:
        for entity in result["entities"]:
            for field in entity["fields"]:
                counts = fill[entity["label_rule_id"]][field["canonical_label"]]
                counts["total"] += 1
                counts[field["presence"]] += 1
    return {
        rule: {label: dict(counts) for label, counts in labels.items()}
        for rule, labels in fill.items()
    }


def run_extraction(
    root: Store | Path | str,
    run: CrawlRun,
    ruleset: dict,
    properties: list[TemplateProperty],
    ts: str | None = None,
    workers: int | None = None,
) -> dict:
    store = open_store(root)
    ts = ts or now_ts()
    pages = list_pages(store, run)
    workers = workers or min(8, os.cpu_count() or 1)

    # Worker processes rebuild their own store from the root string; a ready-made Store
    # object cannot be sent to them, so it is used in this process alone.
    if workers > 1 and isinstance(root, str | Path):
        with ProcessPoolExecutor(
            max_workers=workers, initializer=_init_worker, initargs=(ruleset, str(root))
        ) as pool:
            results = list(pool.map(_extract_page, pages, chunksize=8))
    else:
        _init_worker(ruleset, root)
        results = [_extract_page(page) for page in pages]

    records = merge_pages(results, properties)

    rids_by_url: dict[str, list[str]] = defaultdict(list)
    for rid, record in records.items():
        for url in record["source_urls"]:
            rids_by_url[url].append(rid)

    base = f"{run.key}/extractions/{ts}"
    store.write_json(f"{base}/rules.json", ruleset)
    sample_key = f"{run.key}/review-ui/sample.json"
    if store.exists(sample_key):
        store.write_json(f"{base}/sample.json", store.read_json(sample_key))
    # One small file per record. Written in parallel: each write is a network round trip
    # when the root is Azure, so doing 2,000 of them one after another dominates the run.
    with ThreadPoolExecutor(max_workers=WRITE_THREADS) as writers:
        list(
            writers.map(
                lambda item: store.write_json(
                    f"{base}/records/{item[0]}.json", item[1]
                ),
                records.items(),
            )
        )
    store.write_text(
        f"{base}/pages.jsonl",
        "".join(
            json.dumps(
                {
                    "stem": result["stem"],
                    "url": result["url"],
                    "page_type": result["page_type"],
                    "title": result.get("title"),
                    "labels": result["labels"],
                    "record_ids": sorted(rids_by_url.get(result["url"], [])),
                }
            )
            + "\n"
            for result in results
        ),
    )

    labels = [
        {
            "label": entry["label"],
            "source_url": result["url"],
            "rule_id": entry["rule_id"],
            "stem": result["stem"],
        }
        for result in results
        for entry in result["labels"]
    ]
    store.write_json(f"{run.key}/discovery/{ts}/labels.json", labels)

    label_keys = {label_id(l["source_url"], l["label"], l["rule_id"]) for l in labels}
    regression = check_regressions(
        baseline_decisions(store, run.key), records, label_keys
    )
    report = {
        "extraction_id": ts,
        "ruleset": {"id": ruleset["ruleset_id"], "version": ruleset["version"]},
        "pages_total": len(results),
        "pages_without_main_content": sum(not r["has_main_content"] for r in results),
        "labels_per_rule": dict(Counter(l["rule_id"] for l in labels)),
        "page_types": dict(Counter(r["page_type"] for r in results)),
        "entities": sum(len(r["entities"]) for r in results),
        "records": len(records),
        "uncoded_records": sum(rid.startswith("UNCODED-") for rid in records),
        "records_with_conflicts": sum(bool(r["conflicts"]) for r in records.values()),
        "fill": _fill_rates(results),
        "regression": regression,
    }
    store.write_json(f"{base}/report.json", report)
    return report


def latest_extraction(store: Store, run_key: str) -> str | None:
    names = [
        n
        for n in store.list_dir(f"{run_key}/extractions")
        if store.exists(f"{run_key}/extractions/{n}/report.json")
    ]
    return names[-1] if names else None
