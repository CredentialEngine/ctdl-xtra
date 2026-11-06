"""Locate crawl runs and read their pages.

Runs are found by looking for ``crawl.json`` rather than by path depth, because
crawl output nesting is not consistent between catalogs.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import lxml.html

from .store import Store, open_store

# Rules and the page pane see a page's own content (the ruleset's ``content_root``)
# inside this wrapper element, so ``css_path`` has one anchor on every platform.
ROOT_ID = "xtra-root"


@dataclass(frozen=True)
class CrawlRun:
    key: str  # posix path of the run directory relative to the storage root
    catalog_folder: str
    run_id: str
    seed_url: str


@dataclass(frozen=True)
class PageRef:
    stem: str
    url: str
    retrieved_at: str
    html_key: str


@dataclass(frozen=True)
class PageAssets:
    base_href: str | None
    stylesheets: tuple[str, ...]
    inline_styles: tuple[str, ...] = ()


def now_ts() -> str:
    """Timestamp in the folder-name format used throughout the buckets."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")


def find_runs(root: Store | Path | str) -> list[CrawlRun]:
    """Every crawl run under ``root`` (a folder, an azure:// URI, or a Store)."""
    store = open_store(root)
    runs: list[CrawlRun] = []
    for key in store.find_files("crawl.json"):
        meta = store.read_json(f"{key}/crawl.json" if key else "crawl.json")
        runs.append(
            CrawlRun(
                key=key,
                catalog_folder=meta.get("catalog_folder", ""),
                run_id=meta.get("run_id", ""),
                seed_url=meta.get("seed_url", ""),
            )
        )
    return runs


def list_pages(store: Store, run: CrawlRun) -> list[PageRef]:
    """A run's pages. One small metadata read per page, done concurrently because each
    read is a network round trip when the store is Azure."""
    names = [n for n in store.list_dir(f"{run.key}/pages") if n.endswith(".meta.json")]

    def one(name: str) -> PageRef:
        stem = name[: -len(".meta.json")]
        meta = store.read_json(f"{run.key}/pages/{name}")
        return PageRef(
            stem=stem,
            url=meta.get("final_url") or meta["requested_url"],
            retrieved_at=meta.get("retrieved_at", ""),
            html_key=f"{run.key}/pages/{stem}.html",
        )

    with ThreadPoolExecutor(max_workers=16) as pool:
        return list(pool.map(one, names))


def split_page(html: str, content_root: str) -> tuple[str | None, PageAssets]:
    """Cut the page's own content (CSS selector ``content_root``) out of a saved page,
    plus its style assets.

    lxml is ~8x faster than BeautifulSoup on multi-MB pages, so it is used only to
    find the fragment; rules run on the fragment.
    """
    doc = lxml.html.fromstring(html)
    mains = doc.cssselect(content_root)
    main_html = (
        lxml.html.tostring(mains[0], encoding="unicode", with_tail=False)
        if mains
        else None
    )
    base = doc.xpath("//base/@href")
    sheets = doc.xpath('//link[@rel="stylesheet"]/@href')
    styles = tuple(s.text_content() for s in doc.xpath("//head/style"))
    return main_html, PageAssets(base[0] if base else None, tuple(sheets), styles)


def page_type_of(url: str, page_types: list[dict]) -> str:
    """Page type for sampling and display: the first ruleset ``page_types`` entry whose
    ``url_regex`` matches the URL, else ``info``."""
    for entry in page_types:
        if re.search(entry["url_regex"], url):
            return entry["type"]
    return "info"
