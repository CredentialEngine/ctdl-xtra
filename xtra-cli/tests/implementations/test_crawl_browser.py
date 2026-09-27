from __future__ import annotations

import logging
import os
import sys
import threading
import types

import pytest

from implementations import crawl_browser
from implementations.crawl_browser import (
    VIEWPORT,
    FetchError,
    FetchResult,
    PlaywrightFetcher,
    WorkerPool,
    playwright_fetcher_factory,
    retry_after_seconds,
)
from implementations.crawl_scope import REASON_NON_HTML

# Taken at import, before conftest swaps __init__ for its real-browser guard.
_REAL_INIT = PlaywrightFetcher.__init__
URL = "https://catalog.example.edu/english/engl101"


class FakePlaywrightError(Exception):
    """Stands in for playwright.sync_api.Error."""


class FakePlaywrightTimeout(FakePlaywrightError):
    """Playwright's TimeoutError is a subclass of its Error, as here."""


class FakeResponse:
    def __init__(self, status: int, headers: dict | None) -> None:
        self.status = status
        self.headers = headers


class FakePage:
    def __init__(self, context: FakeContext) -> None:
        self._context = context
        self.waits: list[str] = []
        self.timeout: int | None = None
        self.url = "about:blank"
        self.closed = False

    def set_default_timeout(self, timeout: int) -> None:
        self.timeout = timeout

    def goto(self, url: str, *, wait_until: str, timeout: int):
        self.waits.append(wait_until)
        outcome = self._context.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        self.url = f"{url}?landed"
        return outcome

    def content(self) -> str:
        return "<html><body><h1>ENGL 101</h1></body></html>"

    def close(self) -> None:
        self.closed = True
        if self._context.page_close_error:
            raise self._context.page_close_error


class FakeContext:
    def __init__(self) -> None:
        self.options: dict | None = None
        self.outcomes: list = []
        self.pages: list[FakePage] = []
        self.page_close_error: Exception | None = None
        self.closed = False

    def new_page(self) -> FakePage:
        self.pages.append(FakePage(self))
        return self.pages[-1]

    def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self, context: FakeContext) -> None:
        self.context = context
        self.closed = False

    def new_context(self, **options) -> FakeContext:
        self.context.options = options
        return self.context

    def close(self) -> None:
        self.closed = True


class FakeChromium:
    def __init__(self, browser: FakeBrowser) -> None:
        self.browser = browser
        self.chrome_installed = True
        self.launches: list[dict] = []

    def launch(self, **options) -> FakeBrowser:
        self.launches.append(options)
        if options.get("channel") == "chrome" and not self.chrome_installed:
            raise FakePlaywrightError(
                "Chromium distribution 'chrome' is not found"
            )
        return self.browser


class FakePlaywright:
    def __init__(self, chromium: FakeChromium) -> None:
        self.chromium = chromium
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


@pytest.fixture
def browser(monkeypatch) -> types.SimpleNamespace:
    """A fake playwright.sync_api, so PlaywrightFetcher runs with no browser.

    conftest replaces PlaywrightFetcher.__init__ to stop a real browser from
    starting. The fake module is that guarantee here, so the real __init__
    is put back for these tests only.
    """
    context = FakeContext()
    chromium = FakeChromium(FakeBrowser(context))
    playwright = FakePlaywright(chromium)

    class Starter:
        def start(self) -> FakePlaywright:
            return playwright

    module = types.ModuleType("playwright.sync_api")
    module.Error = FakePlaywrightError
    module.TimeoutError = FakePlaywrightTimeout
    module.sync_playwright = Starter
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    monkeypatch.setattr(PlaywrightFetcher, "__init__", _REAL_INIT)
    return types.SimpleNamespace(
        playwright=playwright,
        chromium=chromium,
        browser=chromium.browser,
        context=context,
    )


def test_retry_after_reads_seconds_and_ignores_the_date_form() -> None:
    assert retry_after_seconds("30") == 30.0
    assert retry_after_seconds(" 2.5 ") == 2.5
    assert retry_after_seconds("Wed, 21 Oct 2026 07:28:00 GMT") is None
    assert retry_after_seconds("0") is None
    assert retry_after_seconds(None) is None


def test_a_fetch_error_says_whether_it_is_worth_another_try() -> None:
    assert FetchError("timeout").retryable is True
    blocked = FetchError("download", retryable=False, reason="non_html")
    assert blocked.retryable is False
    assert blocked.reason == "non_html"


class _CountingFetcher:
    made = 0

    def __init__(self) -> None:
        type(self).made += 1
        self.thread = threading.current_thread().name
        self.closed = False

    def fetch(self, url: str) -> FetchResult:
        return FetchResult(url, url, 200, "text/html", "<html></html>", 1)

    def close(self) -> None:
        self.closed = True


def test_every_worker_thread_gets_its_own_browser_and_closes_it() -> None:
    made: list[_CountingFetcher] = []
    ready = threading.Barrier(3)

    def factory() -> _CountingFetcher:
        fetcher = _CountingFetcher()
        made.append(fetcher)
        return fetcher

    def work(state, url):
        ready.wait(timeout=10)
        return state.fetcher.fetch(url).requested_url

    pool = WorkerPool(workers=3, fetcher_factory=factory, min_interval=0)
    futures = [pool.submit(work, f"https://x.edu/{n}") for n in range(3)]
    assert sorted(future.result(timeout=10) for future in futures) == [
        "https://x.edu/0",
        "https://x.edu/1",
        "https://x.edu/2",
    ]
    assert len(made) == 3
    assert len({fetcher.thread for fetcher in made}) == 3

    pool.close()
    assert all(fetcher.closed for fetcher in made)


def test_a_worker_reuses_its_browser_across_pages() -> None:
    made: list[_CountingFetcher] = []

    def factory() -> _CountingFetcher:
        fetcher = _CountingFetcher()
        made.append(fetcher)
        return fetcher

    pool = WorkerPool(workers=1, fetcher_factory=factory, min_interval=0)
    for n in range(4):
        pool.submit(
            lambda state, url: state.fetcher.fetch(url), f"https://x.edu/{n}"
        ).result(timeout=10)
    pool.close()
    assert len(made) == 1
    assert made[0].closed


def test_closing_twice_is_harmless() -> None:
    pool = WorkerPool(
        workers=1, fetcher_factory=_CountingFetcher, min_interval=0
    )
    pool.close()
    pool.close()


def test_closing_a_pool_that_never_fetched_does_not_hang() -> None:
    pool = WorkerPool(
        workers=4, fetcher_factory=_CountingFetcher, min_interval=0
    )
    pool.close()


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("XTRA_BROWSER_TESTS"),
    reason="set XTRA_BROWSER_TESTS=1 to open a real browser",
)
def test_playwright_fetcher_renders_a_local_file(tmp_path) -> None:
    """The only test that starts a browser, and it never touches the network."""
    from implementations.crawl_browser import PlaywrightFetcher

    page = tmp_path / "page.html"
    page.write_text(
        "<html><body><h1>ENGL 101</h1></body></html>", encoding="utf-8"
    )
    fetcher = PlaywrightFetcher(user_agent="xtra-test")
    try:
        result = fetcher.fetch(page.as_uri())
    finally:
        fetcher.close()
    assert "ENGL 101" in result.html
    assert result.latency_ms >= 0


def test_the_fetcher_asks_for_chrome_and_opens_one_context(browser) -> None:
    PlaywrightFetcher(user_agent="xtra-test")
    assert browser.chromium.launches == [
        {"headless": True, "channel": "chrome"}
    ]
    assert browser.context.options == {
        "viewport": VIEWPORT,
        "user_agent": "xtra-test",
        "ignore_https_errors": True,
        "accept_downloads": False,
    }


def test_the_fetcher_falls_back_to_bundled_chromium_without_chrome(
    browser,
) -> None:
    browser.chromium.chrome_installed = False
    PlaywrightFetcher(user_agent="xtra-test")
    assert browser.chromium.launches == [
        {"headless": True, "channel": "chrome"},
        {"headless": True},
    ]


def test_fetch_returns_the_rendered_page_with_its_headers(browser) -> None:
    browser.context.outcomes.append(
        FakeResponse(429, {"content-type": "text/html", "retry-after": "120"})
    )
    result = PlaywrightFetcher(user_agent="xtra-test", timeout_ms=5000).fetch(
        URL
    )
    page = browser.context.pages[0]
    assert result.requested_url == URL
    assert result.final_url == f"{URL}?landed"
    assert result.http_status == 429
    assert result.content_type == "text/html"
    assert result.retry_after == 120.0
    assert "ENGL 101" in result.html
    assert result.latency_ms >= 0
    assert page.waits == ["load"]
    assert page.timeout == 5000
    assert page.closed


def test_fetch_retries_a_slow_load_at_domcontentloaded(browser) -> None:
    browser.context.outcomes += [
        FakePlaywrightTimeout("Timeout 60000ms exceeded."),
        FakeResponse(200, None),
    ]
    result = PlaywrightFetcher(user_agent="xtra-test").fetch(URL)
    assert browser.context.pages[0].waits == ["load", "domcontentloaded"]
    assert result.http_status == 200
    assert result.content_type == ""
    assert result.retry_after is None


@pytest.mark.parametrize(
    ("error", "message", "retryable", "reason"),
    [
        (
            FakePlaywrightError(f"net::ERR_ABORTED at {URL}.pdf\nCall log:"),
            f"net::ERR_ABORTED at {URL}.pdf",
            False,
            REASON_NON_HTML,
        ),
        (
            FakePlaywrightError("net::ERR_CONNECTION_RESET"),
            "net::ERR_CONNECTION_RESET",
            True,
            None,
        ),
        (FakePlaywrightError(""), "FakePlaywrightError", True, None),
    ],
)
def test_a_failed_navigation_becomes_a_fetch_error(
    browser, error, message, retryable, reason
) -> None:
    """A download is not worth another try; a dropped connection is."""
    browser.context.outcomes.append(error)
    with pytest.raises(FetchError) as raised:
        PlaywrightFetcher(user_agent="xtra-test").fetch(URL)
    assert str(raised.value) == message
    assert raised.value.retryable is retryable
    assert raised.value.reason == reason
    assert browser.context.pages[0].closed


def test_a_navigation_with_no_response_is_not_retried(browser) -> None:
    browser.context.outcomes.append(None)
    with pytest.raises(FetchError, match="no response") as raised:
        PlaywrightFetcher(user_agent="xtra-test").fetch(URL)
    assert raised.value.retryable is False
    assert raised.value.reason == REASON_NON_HTML


def test_a_page_that_fails_to_close_does_not_lose_the_result(browser) -> None:
    browser.context.outcomes.append(FakeResponse(200, {}))
    browser.context.page_close_error = FakePlaywrightError("Target closed")
    result = PlaywrightFetcher(user_agent="xtra-test").fetch(URL)
    assert result.http_status == 200


def test_close_shuts_everything_even_when_one_step_fails(browser) -> None:
    fetcher = PlaywrightFetcher(user_agent="xtra-test")

    def refuse() -> None:
        raise FakePlaywrightError("Target page, context or browser is closed")

    browser.context.close = refuse
    fetcher.close()
    assert browser.browser.closed
    assert browser.playwright.stopped


def test_the_factory_builds_fetchers_with_the_shared_user_agent(
    browser, monkeypatch
) -> None:
    monkeypatch.setattr(crawl_browser, "browser_user_agent", lambda: "xtra-ua")
    browser.context.outcomes.append(FakeResponse(200, {}))
    playwright_fetcher_factory(timeout_ms=1234)().fetch(URL)
    assert browser.context.options["user_agent"] == "xtra-ua"
    assert browser.context.pages[0].timeout == 1234


def test_closing_the_pool_logs_a_browser_that_fails_to_close(caplog) -> None:
    class BrokenFetcher:
        def close(self) -> None:
            raise RuntimeError("browser process already gone")

    pool = WorkerPool(workers=1, fetcher_factory=BrokenFetcher, min_interval=0)
    pool.submit(lambda state: None).result(timeout=10)
    with caplog.at_level(logging.WARNING, logger=crawl_browser.logger.name):
        pool.close()
    assert "did not close cleanly: browser process already gone" in caplog.text


def test_closing_the_pool_gives_up_on_a_browser_that_hangs(
    monkeypatch, caplog
) -> None:
    release = threading.Event()

    class HangingFetcher:
        def close(self) -> None:
            release.wait(timeout=10)

    monkeypatch.setattr(crawl_browser, "CLOSE_TIMEOUT_SECONDS", 0.05)
    pool = WorkerPool(workers=1, fetcher_factory=HangingFetcher, min_interval=0)
    pool.submit(lambda state: None).result(timeout=10)
    try:
        with caplog.at_level(logging.WARNING, logger=crawl_browser.logger.name):
            pool.close()
    finally:
        release.set()
    assert "1 browser(s) did not close in time" in caplog.text
