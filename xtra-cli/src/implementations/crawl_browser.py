"""One Playwright browser per worker thread, reused across that thread's pages.

The sync Playwright API is bound to the thread that created it, so a pool of
workers cannot share one browser. Each worker starts its own on first use,
opens a fresh page per URL, and closes everything on its own thread when the
run ends.

A page is taken when it is ready, not when its load event fires. CurriQunet
catalogs fetch every word of their content by XHR after load, so the HTML at
load is an empty shell. And a bot challenge in front of a catalog is waited
out in the browser rather than saved as if it were the page.
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
from implementations.crawl_challenge import (
    UNSOLVABLE_CHALLENGES,
    challenge_kind,
    challenge_tokens,
)
from implementations.crawl_robots import browser_user_agent
from implementations.crawl_scope import REASON_NON_HTML

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 60000
BARRIER_TIMEOUT_SECONDS = 30.0
CLOSE_TIMEOUT_SECONDS = 120.0
VIEWPORT = {"width": 1400, "height": 1800}

# The readiness budget was measured on CurriQunet, CourseLeaf and Acalog.
# The slowest CurriQunet page went network-idle 7.1 s after its load event.
NETWORKIDLE_TIMEOUT_MS = 15000
# At network idle CurriQunet pages had already been quiet for 507-1021 ms.
DOM_QUIET_MS = 500
# Bounds the quiet wait for a page whose DOM never stops changing.
DOM_QUIET_CAP_MS = 3000
# How often the quiet check runs inside the page.
DOM_QUIET_POLL_MS = 100
# content() fails while the page navigates, so it gets a few tries.
CONTENT_ATTEMPTS = 3
# The idle budget for a document that replaced the one being waited on.
SETTLE_AFTER_NAVIGATION_MS = 5000
# The longest a challenge script gets to earn its token; solves took 1.5-7.6 s.
CHALLENGE_WAIT_MS = 30000
# How often the context's cookies are read while a challenge runs.
CHALLENGE_POLL_MS = 250
# A challenge that keeps coming back after it was solved will not let us in.
MAX_CHALLENGE_ROUNDS = 3

# Counts DOM content mutations from the moment each document is created.
# Installed once per context, so a page that has already been quiet for
# DOM_QUIET_MS passes the check on its first poll. Content mutations only:
# attribute churn (carousels, focus rings, class toggles) does not change
# what content() captures, and counting it would keep an animated page from
# ever going quiet.
MUTATION_CLOCK_JS = """
(() => {
  if (window.__xtraMut) return;
  const clock = {n: 0, last: performance.now()};
  window.__xtraMut = clock;
  try {
    new MutationObserver((records) => {
      clock.n += records.length;
      clock.last = performance.now();
    }).observe(document, {subtree: true, childList: true, characterData: true});
  } catch (e) { clock.error = String(e); }
})();
"""

# True when the page has had no content mutation for `q` ms. A page without
# the clock (init script blocked, about:blank) counts as quiet.
DOM_QUIET_JS = (
    "q => !window.__xtraMut || (performance.now() - window.__xtraMut.last) >= q"
)

# What Playwright says when the document it was reading went away under it.
# Only these are worth reading the page again for.
NAVIGATING_MARKERS = (
    "page is navigating",
    "Execution context was destroyed",
    "Cannot find context with specified id",
    "frame was detached",
)

# goto's error when the page navigated again before load, as a challenge
# script does when it reloads the page it was served on.
INTERRUPTED_BY_NAVIGATION = "interrupted by another navigation"


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
    # How the backend decided the page was ready to be taken: what it waited
    # for, whether each wait ended on its own or at its cap, and any
    # challenge it waited out. Written to the sidecar as "render" when set,
    # so a page captured at a cap can be found afterwards.
    render: dict[str, Any] | None = None


@dataclass(frozen=True)
class _Capture:
    """What one page held: its newest document, its HTML, and any challenge."""

    response: Any
    html: str
    final_url: str
    challenge: str | None


def _first_line(error: BaseException) -> str:
    text = str(error).strip()
    return text.splitlines()[0] if text else error.__class__.__name__


def _ms_since(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _is_navigating(error: BaseException) -> bool:
    text = str(error)
    return any(marker in text for marker in NAVIGATING_MARKERS)


def retry_after_seconds(raw: str | None) -> float | None:
    """Retry-After in seconds. The HTTP-date form is ignored on purpose."""
    if not raw:
        return None
    try:
        seconds = float(raw.strip())
    except ValueError:
        return None
    return seconds if seconds > 0 else None


def _navigation_error(error: BaseException) -> FetchError:
    """A download is not worth another try; anything else may be."""
    message = _first_line(error)
    if "ERR_ABORTED" in message:
        return FetchError(message, retryable=False, reason=REASON_NON_HTML)
    return FetchError(message)


def _document_logger(page: Any, documents: list[Any]) -> Callable[[Any], None]:
    """A response handler that keeps the page's own documents, in order.

    goto returns only the document it started with. A challenge that
    reloads the page, or a script that navigates it, shows up here as a
    later document, and the newest one is the page that was read. An
    iframe's document and a redirect hop are not the page.
    """
    from playwright.sync_api import Error as PlaywrightError

    def on_response(response: Any) -> None:
        with suppress(PlaywrightError):
            if (
                response.request.is_navigation_request()
                and response.frame == page.main_frame
                and not 300 <= response.status < 400
            ):
                documents.append(response)

    return on_response


def _result(
    url: str, capture: _Capture, started: float, render: dict[str, Any]
) -> FetchResult:
    headers = capture.response.headers or {}
    return FetchResult(
        requested_url=url,
        final_url=capture.final_url,
        http_status=capture.response.status,
        content_type=headers.get("content-type", ""),
        html=capture.html,
        latency_ms=_ms_since(started),
        retry_after=retry_after_seconds(headers.get("retry-after")),
        render=render,
    )


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
        self._context.add_init_script(script=MUTATION_CLOCK_JS)

    def fetch(self, url: str) -> FetchResult:
        """Render one URL once it is ready, waiting out any bot challenge.

        Every pass opens a fresh page. A pass that meets a challenge keeps
        its page open while the challenge script, which runs in that page,
        earns a token cookie, then closes it, and the next pass asks for the
        URL from a new page that carries the cookie.

        Waiting on the challenge page for its own reload looks simpler but
        reads the wrong document: once the reload starts,
        wait_for_load_state("load") still answers for the old document, and
        content() can return a half-parsed DOM (seen live: 2,845 bytes, cut
        off inside <head>) that would be saved as a real page. A page opened
        after the cookie exists never has a reload in flight to read.

        The challenge page is never returned. Latency covers the whole
        fetch, challenge rounds included, until the HTML is held.
        """
        from playwright.sync_api import Error as PlaywrightError

        started = time.perf_counter()
        tokens = self._tokens(url)
        # What the challenge rounds cost spans the whole fetch; how the page
        # became ready is about the last page alone.
        challenge: dict[str, Any] = {}
        rounds = 0
        while True:
            page, documents = self._open_page()
            render: dict[str, Any] = {}
            try:
                capture = self._capture(page, url, documents, render)
                kind = capture.challenge
                if kind is None:
                    return _result(url, capture, started, render | challenge)
                rounds += 1
                challenge["challenge"] = kind
                challenge["challenge_rounds"] = rounds
                if kind in UNSOLVABLE_CHALLENGES:
                    raise FetchError(
                        f"{kind} interstitial: a headless browser cannot "
                        "solve it",
                        retryable=False,
                    )
                if rounds > MAX_CHALLENGE_ROUNDS:
                    raise FetchError(
                        f"{kind} challenge came back {rounds - 1} times"
                    )
                waited = time.perf_counter()
                tokens = self._wait_for_new_token(page, url, kind, tokens)
                spent = challenge.get("challenge_wait_ms", 0)
                challenge["challenge_wait_ms"] = spent + _ms_since(waited)
            except PlaywrightError as exc:
                raise _navigation_error(exc) from None
            finally:
                with suppress(PlaywrightError):
                    page.close()

    def _open_page(self) -> tuple[Any, list[Any]]:
        page = self._context.new_page()
        page.set_default_timeout(self._timeout_ms)
        documents: list[Any] = []
        page.on("response", _document_logger(page, documents))
        return page, documents

    def _capture(
        self,
        page: Any,
        url: str,
        documents: list[Any],
        render: dict[str, Any],
    ) -> _Capture:
        """Load `url` in `page` and read it once it is ready.

        A challenge found at first look is returned at once, so no readiness
        wait is spent on an interstitial.
        """
        response = self._goto(page, url, documents, render)
        if response is None:
            raise FetchError(
                "navigation produced no response",
                retryable=False,
                reason=REASON_NON_HTML,
            )
        loaded = time.perf_counter()
        kind = self._first_look_challenge(page, response, documents)
        if kind is not None:
            return _Capture(response, "", page.url, kind)
        self._wait_until_ready(page, render)
        html, final_url = self._content(page, render)
        render["ready_ms"] = _ms_since(loaded)
        latest = documents[-1] if documents else response
        kind = challenge_kind(latest.status, latest.headers, html)
        return _Capture(latest, html, final_url, kind)

    def _goto(
        self,
        page: Any,
        url: str,
        documents: list[Any],
        render: dict[str, Any],
    ) -> Any:
        """Navigate, and record which point in loading goto waited for.

        A challenge can reload the page before goto's load wait is over, and
        goto then fails as interrupted. The documents logged by then still
        say what the page was, so the fetch carries on from the newest.
        """
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        try:
            try:
                response = page.goto(
                    url, wait_until="load", timeout=self._timeout_ms
                )
                render["load_event"] = "load"
            except PlaywrightTimeout:
                response = page.goto(
                    url, wait_until="domcontentloaded", timeout=self._timeout_ms
                )
                render["load_event"] = "domcontentloaded"
        except PlaywrightError as exc:
            if INTERRUPTED_BY_NAVIGATION not in str(exc) or not documents:
                raise
            render["load_event"] = "interrupted"
            return documents[-1]
        return response

    @staticmethod
    def _first_look_challenge(
        page: Any, response: Any, documents: list[Any]
    ) -> str | None:
        """A challenge seen before any time is spent waiting on the page.

        Every logged document's headers are read, not only the newest: a
        challenge that already reloaded the page still left its own response
        behind. Without a header, one look at the DOM, not retried, because
        a page that is navigating now is read again after the wait.
        """
        from playwright.sync_api import Error as PlaywrightError

        for document in (response, *documents):
            kind = challenge_kind(document.status, document.headers, "")
            if kind is not None:
                return kind
        try:
            html = page.content()
        except PlaywrightError:
            html = ""
        return challenge_kind(response.status, response.headers, html)

    @staticmethod
    def _wait_until_ready(page: Any, render: dict[str, Any]) -> None:
        """Wait for the network to go idle, then for the DOM to go quiet.

        Neither wait is an error when it runs out: a page that polls forever
        is captured at the cap, and render says so.
        """
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        try:
            page.wait_for_load_state(
                "networkidle", timeout=NETWORKIDLE_TIMEOUT_MS
            )
            render["networkidle"] = True
        except PlaywrightTimeout:
            render["networkidle"] = False
        except PlaywrightError as exc:
            # A closed or crashed page; content() is the call that reports it.
            render["networkidle"] = False
            render["networkidle_error"] = _first_line(exc)
        try:
            page.wait_for_function(
                DOM_QUIET_JS,
                arg=DOM_QUIET_MS,
                polling=DOM_QUIET_POLL_MS,
                timeout=DOM_QUIET_CAP_MS,
            )
            render["dom_quiet"] = True
        except PlaywrightTimeout:
            render["dom_quiet"] = False
        except PlaywrightError as exc:
            # The page navigated mid-poll; content() waits for the new one.
            render["dom_quiet"] = False
            render["dom_quiet_error"] = _first_line(exc)

    @staticmethod
    def _content(page: Any, render: dict[str, Any]) -> tuple[str, str]:
        """The HTML and the URL it came from, read again after a navigation.

        A page that navigates during the readiness wait makes content()
        fail. Letting the new document reach load and go idle, then reading
        again, takes the page it moved to. Any other failure is not retried.
        """
        from playwright.sync_api import Error as PlaywrightError

        attempt = 1
        while True:
            try:
                html = page.content()
            except PlaywrightError as exc:
                if attempt >= CONTENT_ATTEMPTS or not _is_navigating(exc):
                    raise
                attempt += 1
                with suppress(PlaywrightError):
                    page.wait_for_load_state("load")
                with suppress(PlaywrightError):
                    page.wait_for_load_state(
                        "networkidle", timeout=SETTLE_AFTER_NAVIGATION_MS
                    )
                continue
            render["content_attempts"] = attempt
            return html, page.url

    def _tokens(self, url: str) -> dict[str, str]:
        """The challenge tokens this context would send to `url`."""
        from playwright.sync_api import Error as PlaywrightError

        try:
            return challenge_tokens(self._context.cookies(url))
        except PlaywrightError:
            return {}

    def _wait_for_new_token(
        self, page: Any, url: str, kind: str, tokens: dict[str, str]
    ) -> dict[str, str]:
        """Poll the cookies until the challenge running in `page` is solved.

        Only a token that is new, or whose value changed, counts: the
        context can still hold the one the site has just refused. Polls are
        counted rather than timed, so a test's wait is the real one.
        """
        for _ in range(CHALLENGE_WAIT_MS // CHALLENGE_POLL_MS):
            page.wait_for_timeout(CHALLENGE_POLL_MS)
            current = self._tokens(url)
            # A (name, value) pair that was not there before: a new token,
            # or a known one with a new value.
            if current.items() - tokens.items():
                return current
        raise FetchError(
            f"{kind} challenge did not resolve within "
            f"{CHALLENGE_WAIT_MS // 1000} s"
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
