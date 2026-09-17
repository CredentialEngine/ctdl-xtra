"""Fetch a page through Firecrawl's scrape endpoint.

A hosted crawler renders the page and absorbs the blocking that a college
site sometimes does to a browser we drive ourselves. It costs money per page
and it sends every URL to a third party, so it is never the default.

Only the HTTP shape is coded here, with no SDK, so this adds no dependency.
The endpoint, the payload format, and the response keys are all overridable,
because a hosted API changes on its own schedule and a crawl should not need
a new release to follow it.
"""

from __future__ import annotations

import http.client
import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from implementations.crawl_browser import FetchError, FetchResult
from implementations.crawl_robots import browser_user_agent

logger = logging.getLogger(__name__)

DEFAULT_API_URL = "https://api.firecrawl.dev"
SCRAPE_PATH = "/v1/scrape"
DEFAULT_TIMEOUT_SECONDS = 120
# We save the page as it was served, so markdown is not what we want.
DEFAULT_FORMAT = "rawHtml"


class FirecrawlFetcher:
    """One worker's Firecrawl client.

    The API key never reaches a log line or a stored document: it is held
    here, put in one header, and nowhere else.
    """

    def __init__(
        self,
        *,
        api_key: str,
        api_url: str = DEFAULT_API_URL,
        user_agent: str,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        scrape_format: str = DEFAULT_FORMAT,
        open_url: Callable[..., Any] | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Firecrawl needs an API key")
        self._api_key = api_key
        self._endpoint = f"{api_url.rstrip('/')}{SCRAPE_PATH}"
        self._user_agent = user_agent
        self._timeout = timeout
        self._format = scrape_format
        self._open_url = open_url

    def fetch(self, url: str) -> FetchResult:
        opener = self._open_url or urllib.request.urlopen
        body = json.dumps(
            {
                "url": url,
                "formats": [self._format],
                "onlyMainContent": False,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": self._user_agent,
            },
        )
        started = time.perf_counter()
        try:
            with opener(request, timeout=self._timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise self._api_error(int(exc.code)) from None
        except (OSError, http.client.HTTPException) as exc:
            raise FetchError(str(exc) or exc.__class__.__name__) from exc
        except ValueError as exc:
            raise FetchError(f"Firecrawl sent something that is not JSON: {exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        return self._read(url, payload, latency_ms)

    def _api_error(self, status: int) -> FetchError:
        """A fault in the API is not a fault in the page.

        A rejected key retried six times a page would burn a whole crawl and
        a whole budget, so only the statuses worth waiting out are retried.
        """
        retryable = status == 429 or status >= 500
        detail = "rate limited or unavailable" if retryable else "rejected the request"
        return FetchError(
            f"Firecrawl {detail} (HTTP {status})", retryable=retryable
        )

    def _read(
        self, url: str, payload: dict[str, Any], latency_ms: int
    ) -> FetchResult:
        if payload.get("success") is False:
            raise FetchError(
                f"Firecrawl could not scrape the page: {payload.get('error')}",
                retryable=False,
            )
        document = payload.get("data")
        if not isinstance(document, dict):
            document = payload
        html = document.get(self._format) or document.get("html") or ""
        metadata = document.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        status = metadata.get("statusCode")
        return FetchResult(
            requested_url=url,
            final_url=metadata.get("sourceURL") or metadata.get("url") or url,
            http_status=int(status) if isinstance(status, int) else 200,
            content_type=metadata.get("contentType") or "text/html",
            html=html,
            latency_ms=latency_ms,
        )

    def close(self) -> None:
        """Nothing is held open. Present so every fetcher looks the same."""


def firecrawl_fetcher_factory(
    *,
    api_key: str,
    api_url: str = DEFAULT_API_URL,
    user_agent: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> Callable[[], FirecrawlFetcher]:
    def factory() -> FirecrawlFetcher:
        return FirecrawlFetcher(
            api_key=api_key,
            api_url=api_url,
            user_agent=user_agent or browser_user_agent(),
            timeout=timeout,
        )

    return factory
