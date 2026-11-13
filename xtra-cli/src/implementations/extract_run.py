"""What every one-property extraction shares.

An extractor reads one CTDL property from one occurrence of a class on a
page: `ceterms:name` from one course block. A property declares the classes
it is read from, and each class says how one of its resources is
identified. Everything around that is here and written once: which pages
each class is read from, which resource each occurrence is, the file each
value is written to, and the run report. Nothing here knows which property
it is extracting.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from common.keys import (
    discovery_key,
    extract_property_prefix,
    extract_resource_key,
    page_html_key,
    page_meta_key,
    property_extract_report_key,
)
from implementations.discover import (
    PAGES_FILE,
    SUMMARY_FILE,
    git_commit,
    sample_file_name,
)
from implementations.discover_dom import is_chrome, parse
from implementations.discover_rules import collapse

logger = logging.getLogger(__name__)

REPORT_SCHEMA = "xtra-extraction-report-1"
REASON_PAGE_MISSING = "page_missing"
REASON_NO_RESOURCE_ID = "no_resource_id"

# How many misses the report quotes. The counts cover the rest.
NOT_FOUND_EXAMPLES = 50

# Text a browser never shows, so a value never comes from it.
_UNPRINTED = frozenset({"script", "style", "template", "noscript"})


class ExtractionError(Exception):
    """The extraction cannot run at all, as opposed to a page reading badly."""


@dataclass(frozen=True)
class Page:
    """One saved page, with what discovery said about it."""

    stem: str
    url: str
    soup: BeautifulSoup
    platform: str
    profile: dict[str, Any]
    retrieved_at: str | None = None

    @property
    def site_name(self) -> str:
        meta = self.soup.find("meta", attrs={"property": "og:site_name"})
        content = meta.get("content") if isinstance(meta, Tag) else ""
        return collapse(content or "")


@dataclass(frozen=True)
class Occurrence:
    """One thing of the class the page prints: one course, one block."""

    element: Tag
    css_path: str
    is_whole_page: bool


@dataclass(frozen=True)
class Reading:
    """What an extractor read from one occurrence, and how.

    `value` is None when nothing was found, and `reason` then says why.
    """

    value: Any
    raw_text: str | None
    strategy: str
    css_path: str
    reason: str = ""


@dataclass(frozen=True)
class RdfClass:
    """A class a property can be read from: which pages hold it, where
    each one is on a page, and how one is identified.

    `resource_id` is None when the occurrence can't be identified; the
    value is then not written, only counted.
    """

    rdf_type: str
    page_label: str
    occurrences: Callable[[Page], list[Occurrence]]
    resource_id: Callable[[Occurrence, Page, str], str | None]


@dataclass(frozen=True)
class Extractor:
    """One property, read from every class it declares."""

    prop: str
    classes: tuple[RdfClass, ...]
    read: Callable[[Occurrence, Page], Reading]


@dataclass
class _Tally:
    """The run report's counts, gathered as the pages are read."""

    pages_considered: int = 0
    pages_read: int = 0
    occurrences: int = 0
    found: int = 0
    not_found: int = 0
    files_cleared: int = 0
    resources_written: int = 0
    no_resource_id: int = 0
    repeated_resource_ids: int = 0
    by_strategy: dict[str, int] = field(default_factory=dict)
    by_class: dict[str, dict[str, int]] = field(default_factory=dict)
    by_platform: dict[str, dict[str, int]] = field(default_factory=dict)
    not_found_by_reason: dict[str, int] = field(default_factory=dict)
    not_found_examples: list[dict[str, Any]] = field(default_factory=list)
    no_resource_id_examples: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    # How many times each resource id has been written in this run, so a
    # repeat gets "-2", "-3" in the order the pages are read.
    seen_ids: dict[str, int] = field(default_factory=dict)


def page_platform(own: str, site: str) -> str:
    """The page's own fingerprint, else the site's, else none."""
    return own or site or ""


def printed_text(tag: Tag) -> str:
    """The text a reader sees in this element, whitespace collapsed.

    Scripts and styles are left out. A <br> is a space, so a title
    broken over two lines doesn't run its words together.
    """
    parts: list[str] = []
    for node in tag.descendants:
        if isinstance(node, Tag):
            if node.name == "br":
                parts.append(" ")
            continue
        if not isinstance(node, NavigableString) or isinstance(node, Comment):
            continue
        if any(parent.name in _UNPRINTED for parent in node.parents):
            continue
        parts.append(str(node))
    return collapse("".join(parts))


def inside_chrome(tag: Tag) -> bool:
    """True when the element, or anything around it, is site furniture."""
    return is_chrome(tag) or any(
        is_chrome(parent) for parent in tag.parents if isinstance(parent, Tag)
    )


def css_path(tag: Tag) -> str:
    """A selector that finds this one element again in the saved page."""
    steps: list[str] = []
    node: Tag | None = tag
    while isinstance(node, Tag) and node.name not in ("[document]", "html"):
        parent = node.parent
        siblings = (
            [s for s in parent.find_all(node.name, recursive=False)]
            if isinstance(parent, Tag)
            else [node]
        )
        position = next(
            (i for i, s in enumerate(siblings, start=1) if s is node), 1
        )
        steps.append(f"{node.name}:nth-of-type({position})")
        node = parent
    return " > ".join(reversed(steps))


def unique_resource_id(resource_id: str, seen: dict[str, int]) -> str:
    """The id, or the id with "-2", "-3" for its second and later use."""
    count = seen.get(resource_id, 0) + 1
    seen[resource_id] = count
    return resource_id if count == 1 else f"{resource_id}-{count}"


def resource_value(
    *,
    rdf_type: str,
    resource_id: str,
    prop: str,
    reading: Reading,
    catalog_id: str,
    source_url: str,
    retrieved_at: str | None,
    notes: str,
) -> dict[str, Any]:
    """The file one property of one resource is written as.

    A value not found is still written, as null, so the file says the
    property was looked for on that resource; its notes say why.
    """
    return {
        "type": rdf_type,
        "resource_id": resource_id,
        "ctdl_property": prop,
        "value": reading.value,
        "catalog_id": catalog_id,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "notes": notes,
    }


def reading_notes(reading: Reading, platform: str) -> str:
    """How the value was read, for a reviewer looking at the file."""
    notes = (
        f"strategy={reading.strategy or '-'} platform={platform or '-'} "
        f"css={reading.css_path or '-'}"
    )
    return f"{notes} reason={reading.reason}" if reading.reason else notes


def read_profiles(
    source: Any, catalog_id: str, run_id: str, discovery_run_id: str
) -> list[dict[str, Any]]:
    """Discovery's pages.jsonl, one profile per saved page."""
    key = discovery_key(catalog_id, run_id, discovery_run_id, PAGES_FILE)
    try:
        text = source.get_text(key)
    except FileNotFoundError as exc:
        raise ExtractionError(
            f"discovery run {discovery_run_id} has no {PAGES_FILE}. "
            "Run xtra catalog discover again."
        ) from exc
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def site_platform(
    source: Any, catalog_id: str, run_id: str, discovery_run_id: str
) -> str:
    """The platform most of the site's pages fingerprint as, or ""."""
    key = discovery_key(catalog_id, run_id, discovery_run_id, SUMMARY_FILE)
    try:
        summary = source.get_json(key)
    except (FileNotFoundError, ValueError):
        return ""
    platform = summary.get("platform") if isinstance(summary, dict) else None
    return (platform or {}).get("name") or ""


def _golden_stems(
    source: Any,
    catalog_id: str,
    run_id: str,
    discovery_run_id: str,
    label: str,
) -> set[str]:
    sample = source.get_json(
        discovery_key(
            catalog_id, run_id, discovery_run_id, sample_file_name(label)
        )
    )
    return {page["stem"] for page in sample.get("pages") or []}


def _retrieved_at(
    source: Any, catalog_id: str, run_id: str, stem: str
) -> str | None:
    try:
        meta = source.get_json(page_meta_key(catalog_id, run_id, stem))
    except (FileNotFoundError, ValueError):
        return None
    return meta.get("retrieved_at") if isinstance(meta, dict) else None


def run_extraction(
    source: Any,
    target: Any,
    extractor: Extractor,
    *,
    catalog_id: str,
    run_id: str,
    discovery_run_id: str,
    only_golden_sample: bool = False,
    limit: int | None = None,
    version: str = "",
) -> dict[str, Any]:
    """Read one property from every page discovery gave one of its classes
    to.

    Discovery and pages are read from `source`; the values and the report
    are written to `target`, one file per resource under
    extraction_report/<prefix>/<property key>/. That folder is emptied
    first, so it holds this run's files and nothing older. Returns the
    report.
    """
    all_profiles = read_profiles(source, catalog_id, run_id, discovery_run_id)
    site = site_platform(source, catalog_id, run_id, discovery_run_id)
    tally = _Tally()
    tally.files_cleared = _clear_property(
        target, catalog_id, run_id, extractor.prop
    )
    for rdf_class in extractor.classes:
        profiles = [
            profile
            for profile in all_profiles
            if rdf_class.page_label in (profile.get("labels") or [])
        ]
        if only_golden_sample:
            wanted = _golden_stems(
                source,
                catalog_id,
                run_id,
                discovery_run_id,
                rdf_class.page_label,
            )
            profiles = [p for p in profiles if p["stem"] in wanted]
        if limit is not None:
            profiles = profiles[:limit]
        logger.info(
            "READ %s pages labelled %s in discovery %s",
            len(profiles),
            rdf_class.page_label,
            discovery_run_id,
        )
        tally.pages_considered += len(profiles)
        for profile in profiles:
            _extract_page(
                source,
                target,
                extractor,
                rdf_class,
                profile,
                site=site,
                catalog_id=catalog_id,
                run_id=run_id,
                tally=tally,
            )

    report = _report(
        tally,
        extractor,
        catalog_id=catalog_id,
        run_id=run_id,
        discovery_run_id=discovery_run_id,
        only_golden_sample=only_golden_sample,
        limit=limit,
        version=version,
    )
    key = property_extract_report_key(catalog_id, run_id, extractor.prop)
    target.put_json(key, report)
    logger.info(
        "DONE %s found, %s not found, in %s occurrences on %s pages",
        tally.found,
        tally.not_found,
        tally.occurrences,
        tally.pages_read,
    )
    return {**report, "report_key": key}


def _clear_property(
    target: Any, catalog_id: str, run_id: str, prop: str
) -> int:
    """Delete the files an earlier run wrote for this property.

    Only this property's folder: other properties, records/ and the rest
    of the run are left alone. Ids can change between runs (a fix to how
    codes are read, a narrower --limit, another discovery run), and a file
    left over would be scored as a resource the page still prints.
    """
    keys = target.list_keys(extract_property_prefix(catalog_id, run_id, prop))
    if keys:
        target.delete(keys)
        logger.info("CLEAR %s files from an earlier run of %s", len(keys), prop)
    return len(keys)


def _extract_page(
    source: Any,
    target: Any,
    extractor: Extractor,
    rdf_class: RdfClass,
    profile: dict[str, Any],
    *,
    site: str,
    catalog_id: str,
    run_id: str,
    tally: _Tally,
) -> None:
    stem = profile["stem"]
    url = profile.get("url") or ""
    try:
        html = source.get_text(page_html_key(catalog_id, run_id, stem))
    except FileNotFoundError:
        tally.skipped.append(
            {"stem": stem, "url": url, "reason": REASON_PAGE_MISSING}
        )
        return
    tally.pages_read += 1
    page = Page(
        stem=stem,
        url=url,
        soup=parse(html),
        platform=page_platform(profile.get("platform") or "", site),
        profile=profile,
        retrieved_at=_retrieved_at(source, catalog_id, run_id, stem),
    )
    platform_counts = tally.by_platform.setdefault(
        page.platform or "-", {"occurrences": 0, "found": 0}
    )
    class_counts = tally.by_class.setdefault(
        rdf_class.rdf_type, {"occurrences": 0, "found": 0}
    )
    for occurrence in rdf_class.occurrences(page):
        tally.occurrences += 1
        platform_counts["occurrences"] += 1
        class_counts["occurrences"] += 1
        resource_id = rdf_class.resource_id(occurrence, page, catalog_id)
        if resource_id is None:
            tally.no_resource_id += 1
            if len(tally.no_resource_id_examples) < NOT_FOUND_EXAMPLES:
                tally.no_resource_id_examples.append(
                    {
                        "class": rdf_class.rdf_type,
                        "url": url,
                        "css": occurrence.css_path,
                        "reason": REASON_NO_RESOURCE_ID,
                    }
                )
            continue
        unique_id = unique_resource_id(resource_id, tally.seen_ids)
        if unique_id != resource_id:
            tally.repeated_resource_ids += 1

        reading = extractor.read(occurrence, page)
        target.put_json(
            extract_resource_key(catalog_id, run_id, extractor.prop, unique_id),
            resource_value(
                rdf_type=rdf_class.rdf_type,
                resource_id=unique_id,
                prop=extractor.prop,
                reading=reading,
                catalog_id=catalog_id,
                source_url=url,
                retrieved_at=page.retrieved_at,
                notes=reading_notes(reading, page.platform),
            ),
        )
        tally.resources_written += 1
        if reading.value is not None:
            tally.found += 1
            platform_counts["found"] += 1
            class_counts["found"] += 1
            tally.by_strategy[reading.strategy] = (
                tally.by_strategy.get(reading.strategy, 0) + 1
            )
        else:
            tally.not_found += 1
            tally.not_found_by_reason[reading.reason] = (
                tally.not_found_by_reason.get(reading.reason, 0) + 1
            )
            if len(tally.not_found_examples) < NOT_FOUND_EXAMPLES:
                tally.not_found_examples.append(
                    {
                        "resource_id": unique_id,
                        "class": rdf_class.rdf_type,
                        "url": url,
                        "reason": reading.reason,
                        "raw_text": reading.raw_text,
                    }
                )
        logger.debug(
            "EXTRACT %s %s %r", unique_id, reading.strategy, reading.value
        )


def _report(
    tally: _Tally,
    extractor: Extractor,
    *,
    catalog_id: str,
    run_id: str,
    discovery_run_id: str,
    only_golden_sample: bool,
    limit: int | None,
    version: str,
) -> dict[str, Any]:
    return {
        "schema": REPORT_SCHEMA,
        "property": extractor.prop,
        "class": [c.rdf_type for c in extractor.classes],
        "catalog_folder": catalog_id,
        "run_id": run_id,
        "discovery_run_id": discovery_run_id,
        "only_golden_sample": only_golden_sample,
        "limit": limit,
        "pages_considered": tally.pages_considered,
        "pages_read": tally.pages_read,
        "occurrences": tally.occurrences,
        "found": tally.found,
        "not_found": tally.not_found,
        "files_cleared": tally.files_cleared,
        "resources_written": tally.resources_written,
        "no_resource_id": tally.no_resource_id,
        "repeated_resource_ids": tally.repeated_resource_ids,
        "by_strategy": dict(sorted(tally.by_strategy.items())),
        "by_class": dict(sorted(tally.by_class.items())),
        "by_platform": dict(sorted(tally.by_platform.items())),
        "not_found_by_reason": dict(sorted(tally.not_found_by_reason.items())),
        "not_found_examples": tally.not_found_examples,
        "no_resource_id_examples": tally.no_resource_id_examples,
        "skipped": tally.skipped,
        "git_commit": git_commit(),
        "xtra_version": version,
    }
