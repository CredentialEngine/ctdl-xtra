"""Catalog URL harvest. Playwright is the live strategy; HTML harvest is for tests."""

from __future__ import annotations

from typing import Any, Callable

from implementations.engine import load_engine

load_engine()

from catalog import college_slug, detect_family, institution_from_html, is_course_detail_url
from discover import (
    acalog_course_urls,
    clean_course_urls,
    coursedog_course_urls,
    harvest_with_playwright,
    make_slot,
    normalize_course_url,
)


def catalog_id_from_url(url: str, override: str | None = None) -> str:
    if override:
        return override.strip()
    return college_slug(url)


def slot_to_dict(slot: Any) -> dict[str, Any]:
    return {
        "record_id": slot.record_id,
        "entity_type": slot.entity_type,
        "requested_url": slot.requested_url,
        "institution_name": slot.institution_name,
        "source_family": slot.source_family,
        "template_id": slot.template_id,
        "template_version": slot.template_version,
        "page_id": slot.page_id,
        "copy_html": None,
        "retrieved_at": slot.retrieved_at,
        "multi_entity_bundle": slot.multi_entity_bundle,
        "notes": slot.notes,
        "stem": slot.stem,
    }


def harvest_from_html(
    html: str,
    seed_url: str,
    *,
    limit: int | None,
    institution: str | None = None,
) -> dict[str, Any]:
    family = detect_family(html, seed_url)
    inst = institution or institution_from_html(
        html, college_slug(seed_url).replace("-", " ").title()
    )
    if is_course_detail_url(seed_url, family):
        urls = [normalize_course_url(seed_url)]
    elif family == "acalog":
        urls = acalog_course_urls(html, seed_url)
    elif family == "coursedog":
        urls = coursedog_course_urls(html, seed_url)
    else:
        urls = clean_course_urls(html, seed_url)
    urls = list(dict.fromkeys(urls))
    if limit is not None:
        urls = urls[:limit]
    slots = [
        make_slot(url, institution=inst, family=family, template_id=family)
        for url in urls
    ]
    return {
        "seed_url": seed_url,
        "family": family,
        "institution_name": inst,
        "discovered": len(urls),
        "kept": len(slots),
        "slots": slots,
    }


def harvest_playwright(
    seed_url: str,
    *,
    limit: int | None,
    fetch_all: bool,
    institution: str | None,
    between_pages: Callable[[], None] | None = None,
) -> dict[str, Any]:
    want = limit or 30
    report = harvest_with_playwright(
        seed_url,
        want=want,
        fetch_all=fetch_all,
        between_pages=between_pages,
    )
    slots = list(report["slots"])
    if institution:
        slots = [
            make_slot(
                slot.requested_url,
                institution=institution,
                family=slot.source_family,
                template_id=slot.template_id,
            )
            for slot in slots
        ]
        report["institution_name"] = institution
    if not fetch_all and limit is not None:
        slots = slots[:limit]
    report["slots"] = slots
    report["kept"] = len(slots)
    return report
