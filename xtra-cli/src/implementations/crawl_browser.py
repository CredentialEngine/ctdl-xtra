"""One Playwright browser per worker thread, reused across that thread's pages.

The sync Playwright API is bound to the thread that created it, so a pool of
workers cannot share one browser. Each worker starts its own on first use,
opens a fresh page per URL, and closes everything on its own thread when the
run ends.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ALL_COMPLETED, Future, ThreadPoolExecutor
from concurrent.futures import wait as wait_for_futures
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from common.polite import WorkerPacer
from implementations.crawl_robots import browser_user_agent
from implementations.crawl_scope import REASON_NON_HTML

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 60000
BARRIER_TIMEOUT_SECONDS = 30.0
CLOSE_TIMEOUT_SECONDS = 120.0
VIEWPORT = {"width": 1400, "height": 1800}


class FetchError(RuntimeError):
    """A navigation that never produced a page."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = True,
        reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.reason = reason


@dataclass(frozen=True)
class FetchResult:
    requested_url: str
    final_url: str
    http_status: int | None
    content_type: str
    html: str
    latency_ms: int
    retry_after: float | None = None


def _first_line(error: BaseException) -> str:
    text = str(error).strip()
    return text.splitlines()[0] if text else error.__class__.__name__


def retry_after_seconds(raw: str | None) -> float | None:
    """Retry-After in seconds. The HTTP-date form is ignored on purpose."""
    if not raw:
        return None
    try:
        seconds = float(raw.strip())
    except ValueError:
        return None
    return seconds if seconds > 0 else None


class PlaywrightFetcher:
    """Playwright, a browser, and one context, all owned by one thread."""

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ) -> None:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright

        self._timeout_ms = timeout_ms
        self._playwright = sync_playwright().start()
        try:
            browser = self._playwright.chromium.launch(
                headless=True, channel="chrome"
            )
        except PlaywrightError:
            browser = self._playwright.chromium.launch(headless=True)
        self._browser = browser
        self._context = browser.new_context(
            viewport=VIEWPORT,
            user_agent=user_agent,
            ignore_https_errors=True,
            accept_downloads=False,
        )

    def fetch(self, url: str) -> FetchResult:
        """Render one URL. Latency covers navigation until the HTML is held."""
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        page = self._context.new_page()
        page.set_default_timeout(self._timeout_ms)
        started = time.perf_counter()
        try:
            try:
                response = page.goto(
                    url, wait_until="load", timeout=self._timeout_ms
                )
            except PlaywrightTimeout:
                response = page.goto(
                    url, wait_until="domcontentloaded", timeout=self._timeout_ms
                )
            html = page.content()
            final_url = page.url
        except PlaywrightError as exc:
            message = _first_line(exc)
            if "ERR_ABORTED" in message:
                raise FetchError(
                    message, retryable=False, reason=REASON_NON_HTML
                ) from None
            raise FetchError(message) from None
        finally:
            with suppress(PlaywrightError):
                page.close()

        latency_ms = int((time.perf_counter() - started) * 1000)
        if response is None:
            raise FetchError(
                "navigation produced no response",
                retryable=False,
                reason=REASON_NON_HTML,
            )
        headers = response.headers or {}
        return FetchResult(
            requested_url=url,
            final_url=final_url,
            http_status=response.status,
            content_type=headers.get("content-type", ""),
            html=html,
            latency_ms=latency_ms,
            retry_after=retry_after_seconds(headers.get("retry-after")),
        )

    def close(self) -> None:
        from playwright.sync_api import Error as PlaywrightError

        closers = (
            self._context.close,
            self._browser.close,
            self._playwright.stop,
        )
        for shut in closers:
            with suppress(PlaywrightError):
                shut()


def playwright_fetcher_factory(
    *,
    user_agent: str | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> Callable[[], PlaywrightFetcher]:
    def factory() -> PlaywrightFetcher:
        return PlaywrightFetcher(
            user_agent=user_agent or browser_user_agent(),
            timeout_ms=timeout_ms,
        )

    return factory


@dataclass
class WorkerState:
    """The browser and the pacing clock belonging to one worker thread."""

    fetcher: Any
    pacer: WorkerPacer


class WorkerPool:
    """Runs fetch work on `workers` threads, one browser each.

    Only the main thread touches the frontier and storage. A worker receives
    its own state, fetches, and returns a result.
    """

    def __init__(
        self,
        *,
        workers: int,
        fetcher_factory: Callable[[], Any],
        min_interval: float,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.workers = max(1, int(workers))
        self.min_interval = float(min_interval)
        self._fetcher_factory = fetcher_factory
        self._sleep = sleep
        self._local = threading.local()
        self._executor = ThreadPoolExecutor(
            max_workers=self.workers, thread_name_prefix="xtra-fetch"
        )
        self._closed = False

    def _state(self) -> WorkerState:
        state = getattr(self._local, "state", None)
        if state is None:
            state = WorkerState(
                fetcher=self._fetcher_factory(),
                pacer=WorkerPacer(self.min_interval, sleep=self._sleep),
            )
            self._local.state = state
        return state

    def submit(self, work: Callable[..., Any], *args: Any) -> Future:
        return self._executor.submit(self._run, work, args)

    def _run(self, work: Callable[..., Any], args: tuple[Any, ...]) -> Any:
        return work(self._state(), *args)

    def _close_one(self, barrier: threading.Barrier) -> None:
        state = getattr(self._local, "state", None)
        if state is not None:
            self._local.state = None
            state.fetcher.close()
        # Block so no thread can pick up a second close task while another
        # thread still holds an open browser.
        with suppress(threading.BrokenBarrierError):
            barrier.wait(timeout=BARRIER_TIMEOUT_SECONDS)

    def close(self) -> None:
        """Close every worker's browser, each on the thread that opened it."""
        if self._closed:
            return
        self._closed = True
        barrier = threading.Barrier(self.workers)
        futures = [
            self._executor.submit(self._close_one, barrier)
            for _ in range(self.workers)
        ]
        done, not_done = wait_for_futures(
            futures, timeout=CLOSE_TIMEOUT_SECONDS, return_when=ALL_COMPLETED
        )
        for future in done:
            error = future.exception()
            if error is not None:
                logger.warning("a browser did not close cleanly: %s", error)
        if not_done:
            logger.warning("%s browser(s) did not close in time", len(not_done))
        self._executor.shutdown(wait=not not_done)
