"""Rebuilds a crawl's link tree from its saved pages, using the crawler's own rules."""

from __future__ import annotations

import logging
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from common.clock import format_duration, run_id_for_json, utc_timestamp
from common.keys import (
    crawl_key,
    dedupe_key,
    navigation_key,
    page_html_key,
    page_meta_key,
    page_stem,
    state_key,
)
from implementations.crawl_scope import (
    REASON_EXCLUDE_RULE,
    REASON_EXTENSION,
    REASON_INCLUDE_RULE,
    REASON_OUT_OF_SCOPE,
    REASON_ROBOTS,
    REASON_SCHEME,
    Scope,
    extract_link_records,
)

logger = logging.getLogger(__name__)

NAVIGATION_SCHEMA = "xtra-navigation-1"

BUILT_BY_CRAWL = "crawl"
BUILT_BY_REBUILD = "rebuild"

FOUND_BY_START_URL = "start_url"
FOUND_BY_SITEMAP = "sitemap"
FOUND_BY_SITE_INDEX = "site_index"
FOUND_BY_SEED_FILE = "seed_file"
FOUND_BY_LINK = "link"
FOUND_BY_NOT_A_LINK = "not_from_a_link"

NEW = "new"
ALREADY_FOUND = "already_found"
OTHER_WEBSITE = "other_website"
OUTSIDE_SCOPE = "outside_scope"
NOT_A_WEB_PAGE = "not_a_web_page"
FILE = "file"
LEFT_OUT_BY_INCLUDE_REGEX = "left_out_by_include_regex"
LEFT_OUT_BY_EXCLUDE_REGEX = "left_out_by_exclude_regex"
BLOCKED_BY_ROBOTS = "blocked_by_robots"

RESULT_ORDER = (
    NEW,
    ALREADY_FOUND,
    OTHER_WEBSITE,
    OUTSIDE_SCOPE,
    NOT_A_WEB_PAGE,
    FILE,
    LEFT_OUT_BY_INCLUDE_REGEX,
    LEFT_OUT_BY_EXCLUDE_REGEX,
    BLOCKED_BY_ROBOTS,
)

_RESULT_OF_REASON = {
    REASON_SCHEME: NOT_A_WEB_PAGE,
    REASON_EXTENSION: FILE,
    REASON_INCLUDE_RULE: LEFT_OUT_BY_INCLUDE_REGEX,
    REASON_EXCLUDE_RULE: LEFT_OUT_BY_EXCLUDE_REGEX,
    REASON_ROBOTS: BLOCKED_BY_ROBOTS,
}

SAVED = "saved"
FAILED = "failed"
SKIPPED = "skipped"
NOT_VISITED = "not_visited"
STATUS_ORDER = (SAVED, FAILED, SKIPPED, NOT_VISITED)

# The crawl's reasons for skipping a page, in plain words.
SKIP_REASONS = {
    "non_html": "download",
    "redirect_out_of_scope": "sent_to_another_website",
}

# Pages deeper than this are listed at the top, so the JSON never nests too far.
MAX_NESTED_CLICKS = 100

PROGRESS_EVERY = 50

OPERATOR_SOURCES = frozenset({FOUND_BY_START_URL, FOUND_BY_SEED_FILE})


class NavigationError(RuntimeError):
    """There's no crawl to read, or the crawl's own tree would be replaced."""


@dataclass(frozen=True)
class CrawlFacts:
    """What a live crawl knows that a rebuild has to guess."""

    scope: Scope
    canonical: Callable[[str], str]
    declared: dict[str, list[str]]


@dataclass
class _Page:
    url: str
    found_by: str
    clicks: int
    found_on: str | None = None
    link_text: str | None = None
    redirected_to: str | None = None
    links_on_page: int | None = None
    skipped_links: list[dict[str, str]] = field(default_factory=list)
    children: list[str] = field(default_factory=list)


class _Tree:
    def __init__(
        self,
        *,
        scope: Scope,
        canonical: Callable[[str], str],
        crawl_seen: set[str] | None,
    ) -> None:
        self.scope = scope
        self.seed_scope = Scope(
            host=scope.host, path_prefix=scope.path_prefix, robots=scope.robots
        )
        self.canonical = canonical
        # Rebuilds only: a link the crawl never queued was blocked by robots.txt.
        self.crawl_seen = crawl_seen
        self.pages: dict[str, _Page] = {}
        self.roots: list[str] = []
        self.found: set[str] = set()
        # Each skipped link is listed once, on the first page that has it.
        self.listed_skips: set[str] = set()
        self.link_totals: Counter = Counter()
        self.robots_guessed = 0

    def _root(self, url: str, found_by: str) -> _Page:
        page = _Page(url=url, found_by=found_by, clicks=0)
        key = dedupe_key(url)
        self.pages[key] = page
        self.found.add(key)
        self.roots.append(key)
        return page

    def declare(self, url: str, found_by: str) -> None:
        url = self.canonical(url)
        scope = self.seed_scope if found_by in OPERATOR_SOURCES else self.scope
        if scope.rejection(url) is not None:
            return
        key = dedupe_key(url)
        if key in self.found:
            return
        if self.crawl_seen is not None and key not in self.crawl_seen:
            return
        self._root(url, found_by)

    def judge(self, url: str) -> str:
        url = self.canonical(url)
        reason = self.scope.rejection(url)
        if reason == REASON_OUT_OF_SCOPE:
            host = (urlsplit(url).hostname or "").lower()
            return OTHER_WEBSITE if host != self.scope.host else OUTSIDE_SCOPE
        if reason is not None:
            return _RESULT_OF_REASON.get(reason, reason)
        key = dedupe_key(url)
        if key in self.found:
            return ALREADY_FOUND
        if self.crawl_seen is not None and key not in self.crawl_seen:
            self.robots_guessed += 1
            return BLOCKED_BY_ROBOTS
        return NEW

    def _record(self, page: _Page, url: str, text: str) -> str:
        """Adds the link's page to the tree, or notes why it was skipped."""
        result = self.judge(url)
        if result == NEW:
            url = self.canonical(url)
            key = dedupe_key(url)
            self.pages[key] = _Page(
                url=url,
                found_by=FOUND_BY_LINK,
                clicks=page.clicks + 1,
                found_on=page.url,
                link_text=text,
            )
            self.found.add(key)
            page.children.append(key)
        elif result != ALREADY_FOUND and url not in self.listed_skips:
            self.listed_skips.add(url)
            page.skipped_links.append(
                {"link_text": text, "url": url, "result": result}
            )
        return result

    def page(self, saved_url: str) -> _Page:
        page = self.pages.get(dedupe_key(self.canonical(saved_url)))
        if page is None:
            page = self._root(self.canonical(saved_url), FOUND_BY_NOT_A_LINK)
        return page

    def follow(self, saved_url: str, final_url: str, html: str) -> None:
        """Goes through a saved page's links in the same order the crawler did."""
        page = self.page(saved_url)
        self.found.add(dedupe_key(self.canonical(final_url)))
        if final_url != saved_url:
            page.redirected_to = final_url

        records = extract_link_records(html, final_url)
        for record in records:
            result = self._record(page, record.url, record.text)
            self.link_totals[result] += 1
        page.links_on_page = len(records)


def _as_pairs(counts: dict[str, int]) -> str:
    return " ".join(f"{name}={n}" for name, n in counts.items()) or "none"


def _ordered(counts: Counter, order: tuple[str, ...]) -> dict[str, int]:
    known = {name: counts[name] for name in order if counts.get(name)}
    rest = {name: n for name, n in counts.items() if name not in order and n}
    return {**known, **rest}


def _alias_canonical(typed_seed: str, host: str) -> Callable[[str], str]:
    """Swaps the host typed in --url for the one that answered, as the crawler does."""
    typed = (urlsplit(typed_seed).hostname or "").lower()
    if not typed or typed == host:
        return lambda url: url

    def canonical(url: str) -> str:
        parsed = urlsplit(url)
        if (parsed.hostname or "").lower() != typed:
            return url
        netloc = host if parsed.port is None else f"{host}:{parsed.port}"
        return urlunsplit(parsed._replace(netloc=netloc))

    return canonical


def _skip_reason(crawl_doc: dict) -> str | None:
    """The skip reason, but only when the crawl skipped pages for one reason."""
    counts = crawl_doc.get("skipped_by_reason") or {}
    present = [name for name in SKIP_REASONS if counts.get(name)]
    return SKIP_REASONS[present[0]] if len(present) == 1 else None


def _entry(page: _Page, status: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {"url": page.url}
    if page.found_by != FOUND_BY_LINK:
        entry["found_by"] = page.found_by
    if page.found_on is not None:
        entry["found_on"] = page.found_on
        entry["link_text"] = page.link_text
    entry.update(status)
    if page.redirected_to is not None:
        entry["redirected_to"] = page.redirected_to
    if page.links_on_page is not None:
        entry["links_on_page"] = page.links_on_page
    if page.skipped_links:
        entry["skipped_links"] = page.skipped_links
    return entry


def _nest(
    tree: _Tree, statuses: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    top: list[dict[str, Any]] = []
    stack: list[tuple[str, list[dict[str, Any]]]] = [
        (key, top) for key in reversed(tree.roots)
    ]
    while stack:
        key, siblings = stack.pop()
        page = tree.pages[key]
        entry = _entry(page, statuses[key])
        siblings.append(entry)
        if not page.children:
            continue
        if page.clicks >= MAX_NESTED_CLICKS:
            stack.extend((child, top) for child in reversed(page.children))
            continue
        children: list[dict[str, Any]] = []
        entry["pages_found_here"] = children
        stack.extend((child, children) for child in reversed(page.children))
    return top


def build_navigation(
    source: Any,
    target: Any,
    catalog_folder: str,
    run_id: str,
    *,
    facts: CrawlFacts | None = None,
    now: Callable[[], str] = utc_timestamp,
) -> dict[str, Any]:
    """Writes navigation.json and returns it. Without facts, it's a rebuild."""
    started = time.monotonic()
    if facts is None and target.exists(navigation_key(catalog_folder, run_id)):
        earlier = target.get_json(navigation_key(catalog_folder, run_id))
        if earlier.get("built_by") == BUILT_BY_CRAWL:
            raise NavigationError(
                "navigation.json was built by the crawl itself, which is more "
                "exact than a rebuild, so it's left alone. Delete it first if "
                "you want to rebuild it anyway."
            )
    try:
        state = source.get_json(state_key(catalog_folder, run_id))
    except FileNotFoundError as exc:
        raise NavigationError(
            f"no state.json for {catalog_folder} run {run_id}, so there is no "
            "crawl to build a tree from"
        ) from exc
    try:
        crawl_doc = source.get_json(crawl_key(catalog_folder, run_id))
    except FileNotFoundError:
        crawl_doc = {}
    saved_urls = list(state.get("saved") or ())
    logger.info(
        "NAVIGATION building the link tree for %s run %s from %s saved pages",
        catalog_folder,
        run_id_for_json(run_id),
        len(saved_urls),
    )

    if facts is not None:
        tree = _Tree(
            scope=facts.scope, canonical=facts.canonical, crawl_seen=None
        )
        declared = facts.declared
    else:
        seed = (
            crawl_doc.get("resolved_seed_url")
            or crawl_doc.get("seed_url")
            or (state.get("saved") or [""])[0]
        )
        scope = Scope.from_seed(
            seed,
            scope_prefix=crawl_doc.get("scope_prefix"),
            include_regex=tuple(crawl_doc.get("include_regex") or ()),
            exclude_regex=tuple(crawl_doc.get("exclude_regex") or ()),
        )
        canonical = _alias_canonical(
            crawl_doc.get("seed_url") or seed, scope.host
        )
        tree = _Tree(
            scope=scope,
            canonical=canonical,
            crawl_seen=set(state.get("seen") or ()),
        )
        declared = {FOUND_BY_START_URL: [seed]}

    for found_by, urls in declared.items():
        for url in urls:
            tree.declare(url, found_by)

    unreadable = 0
    for number, saved_url in enumerate(saved_urls, start=1):
        stem = page_stem(saved_url)
        try:
            meta = source.get_json(page_meta_key(catalog_folder, run_id, stem))
            html = source.get_text(page_html_key(catalog_folder, run_id, stem))
        except FileNotFoundError:
            unreadable += 1
            tree.page(saved_url)
            logger.warning(
                "NAVIGATION could not read the saved page %s, so its links "
                "are left out",
                saved_url,
            )
        else:
            tree.follow(saved_url, meta.get("final_url") or saved_url, html)
        if number % PROGRESS_EVERY == 0 and number < len(saved_urls):
            logger.info(
                "NAVIGATION read %s of %s saved pages, %s pages in the tree "
                "so far (%s)",
                number,
                len(saved_urls),
                len(tree.pages),
                format_duration(time.monotonic() - started),
            )

    failed = {
        dedupe_key(tree.canonical(record["url"])): record
        for record in state.get("failed") or ()
        if record.get("url")
    }
    waiting = {
        dedupe_key(tree.canonical(url)) for url in state.get("frontier") or ()
    }
    saved = {dedupe_key(tree.canonical(url)) for url in saved_urls}
    for record in failed.values():
        tree.page(record["url"])
    for url in state.get("frontier") or ():
        tree.page(url)

    skip_reason = _skip_reason(crawl_doc)
    statuses: dict[str, dict[str, Any]] = {}
    for key in tree.pages:
        if key in saved:
            statuses[key] = {"status": SAVED}
        elif key in failed:
            statuses[key] = {
                "status": FAILED,
                "error": failed[key].get("error") or "failed",
            }
        elif key in waiting:
            statuses[key] = {"status": NOT_VISITED}
        elif skip_reason:
            statuses[key] = {"status": SKIPPED, "reason": skip_reason}
        else:
            statuses[key] = {"status": SKIPPED}

    notes: list[str] = []
    if tree.robots_guessed:
        notes.append(
            "robots.txt was not saved with this crawl, so the "
            f"{tree.robots_guessed} links marked {BLOCKED_BY_ROBOTS} are links "
            "the crawl never added to its to-visit list."
        )
    if facts is None and crawl_doc.get("sitemap_urls_found"):
        notes.append(
            f"The crawl also read {crawl_doc['sitemap_urls_found']} pages from "
            "the sitemap. A rebuild can't tell those from pages found by a "
            "link, so a sitemap page that an earlier page links to is shown "
            "under that page."
        )
    unlinked = sum(
        1
        for key in tree.roots
        if tree.pages[key].found_by == FOUND_BY_NOT_A_LINK
    )
    if unlinked:
        notes.append(
            f"{unlinked} pages were not found through a link on any saved "
            "page. They came from the sitemap, the site index or the seed "
            "file, and this file can't tell which."
        )
    if (
        any(s["status"] == SKIPPED for s in statuses.values())
        and not skip_reason
    ):
        notes.append(
            "The crawl kept only counts of why pages were skipped when "
            "opened, so their reason is left out."
        )
    if unreadable:
        notes.append(
            f"{unreadable} saved pages could not be read, so their links are "
            "missing."
        )

    by_status = Counter(entry["status"] for entry in statuses.values())
    navigation = {
        "schema": NAVIGATION_SCHEMA,
        "catalog_folder": catalog_folder,
        "run_id": run_id_for_json(run_id),
        "built_by": BUILT_BY_CRAWL if facts is not None else BUILT_BY_REBUILD,
        "built_at": now(),
        "crawl_status": crawl_doc.get("status"),
        "totals": {
            "pages_by_status": _ordered(by_status, STATUS_ORDER),
            "links_by_result": _ordered(tree.link_totals, RESULT_ORDER),
        },
        "notes": notes,
        "tree": _nest(tree, statuses),
    }
    target.put_json(navigation_key(catalog_folder, run_id), navigation)

    for note in notes:
        logger.info("NAVIGATION note: %s", note)
    totals = navigation["totals"]
    logger.info(
        "NAVIGATION done in %s: %s pages (%s), %s links (%s)",
        format_duration(time.monotonic() - started),
        sum(by_status.values()),
        _as_pairs(totals["pages_by_status"]),
        sum(tree.link_totals.values()),
        _as_pairs(totals["links_by_result"]),
    )
    return navigation
