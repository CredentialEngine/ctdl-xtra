"""What the site itself declares: robots.txt rules and sitemap URLs.

Both are fetched with urllib rather than a browser. They are small text
documents, a browser adds nothing, and robots.txt has to be read before the
first page is rendered.
"""

from __future__ import annotations

import gzip
import http.client
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

from implementations.engine import load_engine

logger = logging.getLogger(__name__)

ROBOTS_TIMEOUT_SECONDS = 30
MAX_SITEMAP_DOCUMENTS = 50
_GZIP_MAGIC = b"\x1f\x8b"


class SiteFetchError(RuntimeError):
    """robots.txt or a sitemap could not be fetched at all."""


def browser_user_agent() -> str:
    """The UA string shared with the Playwright context, from lib/config."""
    load_engine()
    from config import BROWSER_USER_AGENT

    return BROWSER_USER_AGENT


def fetch_url(
    url: str, *, timeout: int = ROBOTS_TIMEOUT_SECONDS
) -> tuple[int, bytes]:
    """GET one small document. Returns (status, body); 4xx and 5xx included."""
    request = urllib.request.Request(
        url, headers={"User-Agent": browser_user_agent()}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(getattr(response, "status", 200) or 200), response.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read()
    except (OSError, http.client.HTTPException, ValueError) as exc:
        raise SiteFetchError(str(exc)) from exc


def resolve_final_url(
    url: str,
    *,
    timeout: int = ROBOTS_TIMEOUT_SECONDS,
) -> str:
    """Where this URL actually answers, after redirects.

    A college that has been renamed often serves its whole catalog from the
    new host and redirects the old one. Resolving the entry point first means
    the crawl is scoped to the host that answers, instead of fetching every
    page and then throwing it away as off-site.
    """
    request = urllib.request.Request(
        url, headers={"User-Agent": browser_user_agent()}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.geturl() or url
    except urllib.error.HTTPError as exc:
        return exc.url or url
    except (OSError, http.client.HTTPException, ValueError) as exc:
        logger.warning("ENTRY %s could not be resolved (%s)", url, exc)
        return url


def robots_url(seed_url: str) -> str:
    parsed = urlsplit(seed_url)
    return f"{parsed.scheme or 'https'}://{parsed.netloc}/robots.txt"


def default_sitemap_url(seed_url: str) -> str:
    parsed = urlsplit(seed_url)
    return f"{parsed.scheme or 'https'}://{parsed.netloc}/sitemap.xml"


def no_rules() -> RobotFileParser:
    """A parser that allows everything, for a site with no usable rules."""
    parser = RobotFileParser()
    parser.parse([])
    return parser


@dataclass(frozen=True)
class SiteRules:
    robots: RobotFileParser
    robots_status: int | None
    crawl_delay: float | None = None
    sitemap_urls: tuple[str, ...] = field(default_factory=tuple)


def read_robots(
    seed_url: str,
    *,
    fetch: Callable[[str], tuple[int, bytes]] = fetch_url,
) -> SiteRules:
    """Rules for user-agent *, plus any sitemaps robots.txt points at.

    A 4xx means the site published no rules. A 5xx or a network error means
    we could not tell, which is also no rules, but it is warned about and
    recorded so an incomplete crawl can be explained later.
    """
    url = robots_url(seed_url)
    try:
        status, body = fetch(url)
    except SiteFetchError as exc:
        logger.warning(
            "ROBOTS %s unreachable (%s), crawling with no rules", url, exc
        )
        return SiteRules(robots=no_rules(), robots_status=None)

    if status >= 500:
        logger.warning(
            "ROBOTS %s returned HTTP %s, crawling with no rules", url, status
        )
        return SiteRules(robots=no_rules(), robots_status=status)
    if status >= 400:
        logger.info(
            "ROBOTS %s returned HTTP %s, no rules published", url, status
        )
        return SiteRules(robots=no_rules(), robots_status=status)

    parser = RobotFileParser()
    parser.parse(body.decode("utf-8", errors="replace").splitlines())
    delay = parser.crawl_delay("*")
    sitemaps = tuple(parser.site_maps() or ())
    logger.info(
        "ROBOTS %s -> %s crawl_delay=%s sitemaps=%s",
        url,
        status,
        delay,
        len(sitemaps),
    )
    return SiteRules(
        robots=parser,
        robots_status=status,
        crawl_delay=float(delay) if delay is not None else None,
        sitemap_urls=sitemaps,
    )


def _decompress(url: str, body: bytes) -> bytes:
    if body.startswith(_GZIP_MAGIC) or url.lower().endswith(".gz"):
        return gzip.decompress(body)
    return body


def _local_name(tag: str) -> str:
    return tag.rpartition("}")[2]


def parse_sitemap(body: bytes) -> tuple[str, list[str]]:
    """Return (document kind, every loc value) for one sitemap document."""
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return "", []
    locations = [
        element.text.strip()
        for element in root.iter()
        if _local_name(element.tag) == "loc" and element.text
    ]
    return _local_name(root.tag), locations


def collect_sitemap_urls(
    sitemap_urls: list[str],
    *,
    fetch: Callable[[str], tuple[int, bytes]] = fetch_url,
    max_documents: int = MAX_SITEMAP_DOCUMENTS,
) -> list[str]:
    """Every page URL a site's sitemaps declare, following index documents.

    Gzip is unwrapped, a sitemap index is followed one document at a time,
    and a document already read is never read again, so a self-referencing
    index cannot loop.
    """
    pending = list(sitemap_urls)
    read: set[str] = set()
    pages: list[str] = []
    seen_pages: set[str] = set()
    while pending and len(read) < max_documents:
        url = pending.pop(0)
        if url in read:
            continue
        read.add(url)
        try:
            status, body = fetch(url)
        except SiteFetchError as exc:
            logger.warning("SITEMAP %s unreachable (%s)", url, exc)
            continue
        if status >= 400:
            logger.info("SITEMAP %s returned HTTP %s", url, status)
            continue
        try:
            body = _decompress(url, body)
        except (OSError, EOFError) as exc:
            logger.warning("SITEMAP %s is not readable gzip (%s)", url, exc)
            continue
        kind, locations = parse_sitemap(body)
        logger.info(
            "SITEMAP %s -> %s %s entries",
            url,
            kind or "unknown",
            len(locations),
        )
        for location in locations:
            if kind == "sitemapindex":
                pending.append(location)
            elif location not in seen_pages:
                seen_pages.add(location)
                pages.append(location)
    return pages
