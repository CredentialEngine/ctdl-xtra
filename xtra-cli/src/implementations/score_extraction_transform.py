"""Turn extraction_report/ files into the records scoring reads.

`xtra catalog extract` writes one file per property of one resource,
under extraction_report/<prefix>/<property key>/{resource_id}.json.
Scoring matches a page's baseline entities against the page's records, in
page order. This builds those records in memory, without writing any:

- every property of one resource_id is one record, its `expected` the
  present values by `ctdl_property`;
- a record's page is the stem of its `source_url`, the name the crawl
  saved the page under;
- a page's records are in page order, found again from the element each
  value was read from (the `css=` in its notes) in the saved page.

The result is a read-only store that `match_extraction_run` reads as it
reads records/.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from common.keys import (
    EXTRACTION_REPORT_DIR,
    page_html_key,
    page_stem,
    record_key,
    records_prefix,
    run_prefix,
)
from implementations.discover_dom import parse

# Where the notes say the value's element is: "... css=<path> reason=...".
_CSS_NOTE = " css="
_REASON_NOTE = " reason="


class ExtractionReportError(Exception):
    """The run has no extraction_report/ files to score."""


class ExtractionRecords:
    """Records built from extraction_report/, read the way records/ is."""

    def __init__(self, records: dict[str, dict[str, Any]], location: str):
        self._records = records
        self._location = location

    def list_keys(self, prefix: str = "") -> list[str]:
        return sorted(key for key in self._records if key.startswith(prefix))

    def get_json(self, key: str) -> dict[str, Any]:
        if key not in self._records:
            raise FileNotFoundError(key)
        return self._records[key]

    def describe_location(self) -> str:
        return self._location


def css_from_notes(notes: str) -> str:
    """The css path in a value's notes, or "" when they hold none."""
    text = f" {notes or ''}"
    start = text.find(_CSS_NOTE)
    if start < 0:
        return ""
    path = text[start + len(_CSS_NOTE) :]
    end = path.find(_REASON_NOTE)
    path = path if end < 0 else path[:end]
    return "" if path == "-" else path.strip()


def extraction_records(
    store: Any, catalog_id: str, run_id: str
) -> ExtractionRecords:
    """The run's extraction_report/ files as records, for scoring."""
    root = f"{run_prefix(catalog_id, run_id)}/{EXTRACTION_REPORT_DIR}/"
    # Only <prefix>/<property key>/{resource_id}.json: anything else under
    # extraction_report/ wasn't written by an extractor.
    keys = [
        key
        for key in store.list_keys(root)
        if key.endswith(".json") and key[len(root) :].count("/") == 2
    ]
    if not keys:
        raise ExtractionReportError(
            f"no {EXTRACTION_REPORT_DIR}/ files for {catalog_id} {run_id}. "
            "Run xtra catalog extract first."
        )

    resources: dict[str, dict[str, Any]] = {}
    for key in keys:
        value = store.get_json(key)
        resource_id = value.get("resource_id")
        if not resource_id or not value.get("source_url"):
            continue
        resource = resources.setdefault(
            resource_id,
            {
                "record_id": resource_id,
                "source_url": value["source_url"],
                "expected": {},
                "_css": "",
            },
        )
        if value.get("value") is not None:
            resource["expected"][value["ctdl_property"]] = value["value"]
        resource["_css"] = resource["_css"] or css_from_notes(
            value.get("notes") or ""
        )

    by_stem: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for resource in resources.values():
        by_stem[page_stem(resource["source_url"])].append(resource)

    records: dict[str, dict[str, Any]] = {}
    for stem, on_page in by_stem.items():
        ordered = _in_page_order(store, catalog_id, run_id, stem, on_page)
        for index, resource in enumerate(ordered, start=1):
            record_id = stem if index == 1 else f"{stem}--resource-{index:03d}"
            resource = {k: v for k, v in resource.items() if k != "_css"}
            records[record_key(catalog_id, run_id, record_id)] = resource
    return ExtractionRecords(
        records,
        f"{store.describe_location()} {EXTRACTION_REPORT_DIR}/ as "
        f"{records_prefix(catalog_id, run_id)}/",
    )


def _in_page_order(
    store: Any,
    catalog_id: str,
    run_id: str,
    stem: str,
    resources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The page's resources in the order the page prints them.

    One resource needs no page. Otherwise each is placed by its value's
    element in the saved page; a resource whose element can't be found,
    or a page that isn't saved, goes after the rest, by resource id.
    """
    by_id = sorted(resources, key=lambda r: r["record_id"])
    if len(by_id) < 2:
        return by_id
    try:
        soup = parse(store.get_text(page_html_key(catalog_id, run_id, stem)))
    except FileNotFoundError:
        return by_id
    position = {id(tag): i for i, tag in enumerate(soup.find_all(True))}
    unplaced = len(position)

    def place(resource: dict[str, Any]) -> int:
        css = resource["_css"]
        try:
            tag = soup.select_one(css) if css else None
        except Exception:  # a hand-edited path; soupsieve's own error type
            tag = None
        return position.get(id(tag), unplaced) if tag is not None else unplaced

    return sorted(by_id, key=place)
