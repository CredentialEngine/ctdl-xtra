"""Stand-ins for the browser and for robots.txt, shared by the crawl tests.

No test opens a browser or a socket. A fake fetcher stands in for one
worker's Playwright instance, and a fake url_fetch stands in for robots.txt
and sitemap reads.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from implementations.crawl_browser import FetchError, FetchResult


@dataclass
class FakePage:
    """One canned answer from the fake browser."""

    html: str = "<html><body>ok</body></html>"
    status: int = 200
    content_type: str = "text/html; charset=utf-8"
    final_url: str | None = None
    retry_after: float | None = None
    raises: str | None = None
    retryable: bool = True
    reason: str | None = None


class FakeFetcher:
    """Stands in for one worker's browser.

    `pages` maps a URL to a FakePage, or to a list of them that is consumed
    one entry per attempt, so a test can say "429 twice, then 200".
    """

    def __init__(
        self,
        pages: dict[str, Any],
        *,
        calls: list[str] | None = None,
        before: Callable[[str], None] | None = None,
    ) -> None:
        self.pages = pages
        self.calls = calls if calls is not None else []
        self.before = before
        self.closed = False

    def fetch(self, url: str) -> FetchResult:
        if self.before is not None:
            self.before(url)
        self.calls.append(url)
        page = self.pages.get(url)
        if isinstance(page, list):
            page = page.pop(0) if page else FakePage(status=404, html="")
        if page is None:
            page = FakePage(status=404, html="")
        if page.raises:
            raise FetchError(
                page.raises, retryable=page.retryable, reason=page.reason
            )
        return FetchResult(
            requested_url=url,
            final_url=page.final_url or url,
            http_status=page.status,
            content_type=page.content_type,
            html=page.html,
            latency_ms=7,
            retry_after=page.retry_after,
        )

    def close(self) -> None:
        self.closed = True


def fetcher_factory(
    pages: dict[str, Any],
    *,
    calls: list[str] | None = None,
    before: Callable[[str], None] | None = None,
    made: list[FakeFetcher] | None = None,
) -> Callable[[], FakeFetcher]:
    """A new fake browser per worker thread, sharing one page map."""

    def factory() -> FakeFetcher:
        fetcher = FakeFetcher(pages, calls=calls, before=before)
        if made is not None:
            made.append(fetcher)
        return fetcher

    return factory


def no_site_documents(url: str) -> tuple[int, bytes]:
    """robots.txt and sitemap.xml both missing."""
    return 404, b""


def site_documents(documents: dict[str, bytes]) -> Callable[[str], tuple[int, bytes]]:
    """Serve canned robots.txt and sitemap bodies; anything else is a 404."""

    def fetch(url: str) -> tuple[int, bytes]:
        body = documents.get(url)
        return (200, body) if body is not None else (404, b"")

    return fetch
