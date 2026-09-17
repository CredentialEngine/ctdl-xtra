"""Fetch a page through Crawl4AI, an open-source crawler that needs no key.

It drives a browser like the playwright strategy does, but brings its own
stealth handling, its own retry and wait logic, and hooks for running
JavaScript on the page before the HTML is taken. That last part is the
reason to have it: a catalog that hides its course list behind a Next button
cannot be reached by fetching alone.

It is an optional extra, `pip install -e ".[crawl4ai]"`, and the import is
deferred to the moment a crawl actually asks for it. The package pulls a
large tree, including LLM clients this project never calls, so nothing here
lands in a default install and nothing here talks to a model.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from implementations.crawl_browser import (
    FetchError,
    FetchResult,
    retry_after_seconds,
)
from implementations.crawl_robots import browser_user_agent

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 60000
INSTALL_HINT = (
    "--with-crawl4ai needs the crawl4ai package. "
    'Install it with: pip install -e ".[crawl4ai]"'
)


def _import_crawl4ai() -> Any:
    try:
        import crawl4ai
    except ImportError as exc:
        raise FetchError(f"{INSTALL_HINT} ({exc})", retryable=False) from exc
    return crawl4ai


def _header(headers: Any, name: str) -> str:
    """Header lookup that survives whichever case the library hands back."""
    if not isinstance(headers, dict):
        return ""
    for key, value in headers.items():
        if str(key).lower() == name:
            return str(value)
    return ""


class Crawl4aiFetcher:
    """One worker's crawler, with its own event loop.

    The loop belongs to the thread that made it, the same way the browser in
    the playwright strategy does, so workers never share either.
    """

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ) -> None:
        crawl4ai = _import_crawl4ai()
        self._loop = asyncio.new_event_loop()
        self._crawler = crawl4ai.AsyncWebCrawler(
            config=crawl4ai.BrowserConfig(
                headless=True, user_agent=user_agent, verbose=False
            )
        )
        # Never let the library cache. The crawl decides what it already has
        # from storage, and a cached hit would report a status and a latency
        # that never happened on this run.
        self._run_config = crawl4ai.CrawlerRunConfig(
            cache_mode=crawl4ai.CacheMode.BYPASS,
            page_timeout=timeout_ms,
            verbose=False,
        )
        self._loop.run_until_complete(self._crawler.start())

    def fetch(self, url: str) -> FetchResult:
        started = time.perf_counter()
        try:
            result = self._loop.run_until_complete(
                self._crawler.arun(url=url, config=self._run_config)
            )
        except Exception as exc:  # third party, so any error means retry
            raise FetchError(str(exc) or exc.__class__.__name__) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        if not getattr(result, "success", True):
            raise FetchError(
                getattr(result, "error_message", "")
                or "crawl4ai could not fetch the page"
            )

        headers = getattr(result, "response_headers", None)
        status = getattr(result, "status_code", None)
        final_url = (
            getattr(result, "redirected_url", None)
            or getattr(result, "url", None)
            or url
        )
        return FetchResult(
            requested_url=url,
            final_url=final_url,
            http_status=int(status) if isinstance(status, int) else 200,
            content_type=_header(headers, "content-type") or "text/html",
            html=getattr(result, "html", "") or "",
            latency_ms=latency_ms,
            retry_after=retry_after_seconds(_header(headers, "retry-after") or None),
        )

    def close(self) -> None:
        """Shut the crawler and its loop down on the thread that owns them."""
        try:
            self._loop.run_until_complete(self._crawler.close())
        except Exception as exc:  # noqa: BLE001 - a failed close must not fail a run
            logger.warning("crawl4ai did not close cleanly: %s", exc)
        finally:
            self._loop.close()


def crawl4ai_fetcher_factory(
    *,
    user_agent: str | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> Callable[[], Crawl4aiFetcher]:
    def factory() -> Crawl4aiFetcher:
        return Crawl4aiFetcher(
            user_agent=user_agent or browser_user_agent(), timeout_ms=timeout_ms
        )

    return factory
