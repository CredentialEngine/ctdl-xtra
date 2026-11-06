"""Saving a page's golden dataset into the verified-golden-sets storage.

The golden sets go to their own storage root (``--golden-root`` / ``REVIEW_UI_GOLDEN_ROOT``,
e.g. the ``xtra-golden-sets-verified`` container), not into the crawl's folder. If none is
set they go to the crawl's own root. One folder per page, named like its source HTML file:

    <catalog>/<crawl folder>/<page>/<page>.json    the verified values for a page
    <catalog>/<crawl folder>/<page>/<page>.html    the page's source HTML, saved beside them

A golden dataset is what a person has *verified*, so only accepted values, values the
reviewer corrected, and values the reviewer added are saved. Values still waiting for a
decision (including ones flagged for an expert), rejections with no correction, absences,
and values whose property has no CTDL term are left out; the result says how many.

Each saved value has exactly three keys: ``ctdl_property``, ``value`` and ``source_url``.
A department page lists many courses, so values are grouped by the record they belong to:

    [ {"fields": [ {"ctdl_property": ..., "value": ..., "source_url": ...}, ... ]}, ... ]
"""

from __future__ import annotations

from collections import Counter

from .exports import golden_for_page
from .runs import CrawlRun
from .store import Store
from .views import ExtractionView

VERIFIED = ("accepted", "corrected", "added")


class NothingToSave(ValueError):
    """The page has no verified value to save yet."""


def golden_folder(run: CrawlRun, stem: str) -> str:
    """One folder per page, named like the page's source HTML file (without ``.html``).
    The crawl is identified by its last two path segments, which are the catalog folder and
    the run folder both in the bucket and in a local mirror of it."""
    crawl = "/".join(run.key.split("/")[-2:])
    return f"{crawl}/{stem}"


def golden_key(run: CrawlRun, stem: str) -> str:
    return f"{golden_folder(run, stem)}/{stem}.json"


def golden_html_key(run: CrawlRun, stem: str) -> str:
    return f"{golden_folder(run, stem)}/{stem}.html"


def saved_pages(golden_store: Store, run: CrawlRun) -> list[str]:
    """Stems of the pages that have a saved golden dataset (one folder each)."""
    crawl = "/".join(run.key.split("/")[-2:])
    return sorted(golden_store.list_dir(crawl))


def golden_dataset(
    view: ExtractionView,
    decisions: dict,
    stem: str,
    review_id: str,
    flags: dict | None,
    terms: dict[str, str | None],
) -> tuple[list[dict], dict]:
    """The page's verified values (three keys each, grouped by record) and what was left out."""
    left_out: Counter[str] = Counter()
    records: list[dict] = []
    for record in golden_for_page(view, decisions, stem, review_id, flags, terms):
        left_out["rejected_without_correction"] += record["verification"][
            "unresolved_fields"
        ]
        fields = []
        for field in record["source_expected"]["fields"]:
            if field["review_status"] not in VERIFIED:
                left_out["not_reviewed"] += 1
                left_out["flagged"] += bool(
                    field.get("flagged")
                )  # a subset of not_reviewed
            elif field["presence"] != "present" or field["value"] is None:
                left_out["absent"] += 1
            elif not field.get("ctdl_property"):
                left_out["no_ctdl_property"] += 1
            else:
                fields.append(
                    {
                        "ctdl_property": field["ctdl_property"],
                        "value": field["value"],
                        "source_url": field["source_url"],
                    }
                )
        if fields:
            records.append({"fields": fields})
    return records, {k: v for k, v in left_out.items() if v}


def save_golden(
    golden_store: Store,
    source_store: Store,
    run: CrawlRun,
    view: ExtractionView,
    decisions: dict,
    stem: str,
    review_id: str,
    flags: dict | None,
    terms: dict[str, str | None],
    html_key: str,
) -> dict:
    """Write the page's golden dataset and a copy of its source HTML (read from
    ``source_store``) into the page's folder in ``golden_store``, replacing an earlier save."""
    records, left_out = golden_dataset(view, decisions, stem, review_id, flags, terms)
    values = sum(len(r["fields"]) for r in records)
    if not values:
        raise NothingToSave(
            "Nothing to save yet: accept, correct or add at least one value on this page "
            "(values with no CTDL property are never saved)."
        )
    key = golden_key(run, stem)
    html_out = golden_html_key(run, stem)
    golden_store.write_text(html_out, source_store.read_text(html_key))  # as crawled
    golden_store.write_json(key, records)
    return {
        "key": key,
        "html_key": html_out,
        "location": golden_store.location(golden_folder(run, stem)),
        "values": values,
        "records": len(records),
        "left_out": left_out,
        "datasets": len(saved_pages(golden_store, run)),
    }
