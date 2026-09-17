"""Fetch a page with urllib. No browser.

A catalog that renders on the server does not need one, and a browser costs
roughly a second and a few hundred megabytes per page. This is the cheap
strategy: it returns exactly what the server sent, which for a catalog that
renders in the client is an empty shell. That is the whole trade, and it is
why the strategy is a flag rather than a guess.
"""

from __future__ import annotations

import http.client
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from implementations.crawl_browser import (
    FetchError,
    FetchResult,
    retry_after_seconds,
)
from implementations.crawl_robots import browser_user_agent

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 60
# A catalog page is HTML. Anything this large is a mistake we stop reading.
MAX_BODY_BYTES = 32 * 1024 * 1024
ACCEPT = "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1"


def _decode(body: bytes, headers: Any) -> str:
    """Text of the response, trusting the server's charset when it gave one."""
    charset = "utf-8"
    if headers is not None:
        charset = headers.get_content_charset() or "utf-8"
    return body.decode(charset, errors="replace")


def _header(headers: Any, name: str, default: str = "") -> str:
    if headers is None:
        return default
    return headers.get(name, default) or default


class HttpFetcher:
    """One worker's HTTP client. Holds no connection, so closing is a no-op.

    `open_url` is resolved at call time rather than bound as a default, so a
    test that forgets to inject a fake still trips the no-network guard
    instead of quietly reaching a real college.
    """

    def __init__(
        self,
        *,
        user_agent: str,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        open_url: Callable[..., Any] | None = None,
    ) -> None:
        self._user_agent = user_agent
        self._timeout = timeout
        self._open_url = open_url

    def fetch(self, url: str) -> FetchResult:
        opener = self._open_url or urllib.request.urlopen
        request = urllib.request.Request(
            url, headers={"User-Agent": self._user_agent, "Accept": ACCEPT}
        )
        started = time.perf_counter()
        try:
            with opener(request, timeout=self._timeout) as response:
                status = int(getattr(response, "status", 200) or 200)
                headers = response.headers
                body = response.read(MAX_BODY_BYTES)
                final_url = response.geturl() or url
        except urllib.error.HTTPError as exc:
            # The server answered. A status is an answer, not a failure, so
            # it goes back as a result and the caller decides about retrying.
            return self._result(
                url,
                exc.url or url,
                int(exc.code),
                exc.headers,
                exc.read(),
                started,
            )
        except (OSError, http.client.HTTPException, ValueError) as exc:
            raise FetchError(str(exc) or exc.__class__.__name__) from exc

        return self._result(url, final_url, status, headers, body, started)

    def _result(
        self,
        url: str,
        final_url: str,
        status: int,
        headers: Any,
        body: bytes,
        started: float,
    ) -> FetchResult:
        return FetchResult(
            requested_url=url,
            final_url=final_url,
            http_status=status,
            content_type=_header(headers, "Content-Type"),
            html=_decode(body, headers),
            latency_ms=int((time.perf_counter() - started) * 1000),
            retry_after=retry_after_seconds(_header(headers, "Retry-After") or None),
        )

    def close(self) -> None:
        """Nothing is held open. Present so every fetcher looks the same."""


def http_fetcher_factory(
    *,
    user_agent: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> Callable[[], HttpFetcher]:
    def factory() -> HttpFetcher:
        return HttpFetcher(
            user_agent=user_agent or browser_user_agent(), timeout=timeout
        )

    return factory
