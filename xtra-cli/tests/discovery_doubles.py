"""Hand-built page profiles, for the rules that only make sense in bulk.

Chrome, rarity, and proportional sampling are properties of a whole run, so
these tests describe a run directly instead of inventing hundreds of pages
of HTML to imply one.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from implementations.discover_page import PageProfile


def make_profile(
    stem: str,
    *,
    url: str | None = None,
    page_type: str = "Course",
    labels: Iterable[str] | None = None,
    field_labels: Iterable[str] = (),
    markers: Mapping[str, str] | None = None,
    duplicate_of: str | None = None,
    course_block_count: int = 1,
    text_sha256: str = "",
) -> PageProfile:
    resolved_labels = (
        list(labels)
        if labels is not None
        else ([page_type] if page_type else [])
    )
    return PageProfile(
        url=url or f"https://catalog.example.edu/{stem}",
        final_url=url or f"https://catalog.example.edu/{stem}",
        stem=stem,
        bytes=1000,
        http_status=200,
        title=stem,
        h1=stem,
        visible_chars=1000,
        text_sha256=text_sha256 or f"sha-{stem}",
        url_template=f"/{stem}",
        course_code_count=1,
        course_block_count=course_block_count,
        field_labels=sorted(field_labels),
        headings=[],
        markers=dict(markers or {}),
        labels=resolved_labels,
        page_type=page_type,
        rules_fired={},
        duplicate_of=duplicate_of,
    )


def seed_crawl_page(
    store,
    folder: str,
    run_id: str,
    stem: str,
    html: str,
    url: str,
    *,
    retrieved_at: str = "2026-09-17T14:20:05Z",
) -> None:
    """Write one saved page and its sidecar, the way the crawler would."""
    from common.keys import page_html_key, page_meta_key

    store.put_text(page_html_key(folder, run_id, stem), html, "text/html")
    store.put_json(
        page_meta_key(folder, run_id, stem),
        {
            "requested_url": url,
            "final_url": url,
            "http_status": 200,
            "content_type": "text/html; charset=utf-8",
            "bytes": len(html.encode("utf-8")),
            "latency_ms": 12,
            "retrieved_at": retrieved_at,
            "attempts": 1,
            "sha256": "0" * 64,
            "stem": stem,
        },
    )


def seed_crawl_manifest(store, folder: str, run_id: str, **overrides) -> dict:
    """Write the crawl.json a finished crawl run would have left behind."""
    from common.keys import crawl_key

    document = {
        "schema": "xtra-crawl-2",
        "catalog_folder": folder,
        "run_id": run_id,
        "strategy": "playwright",
        "seed_url": "https://catalog.example.edu/",
        "resolved_seed_url": "https://catalog.example.edu/",
        "effective_min_interval_in_seconds": 10.0,
        "status": "complete",
        "pages_saved": 10,
    }
    document.update(overrides)
    store.put_json(crawl_key(folder, run_id), document)
    return document
