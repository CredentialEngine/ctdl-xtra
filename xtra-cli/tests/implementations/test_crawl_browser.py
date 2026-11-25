from __future__ import annotations

import logging
import os
import sys
import threading
import types
from typing import Any

import pytest

from implementations import crawl_browser
from implementations.crawl_browser import (
    CHALLENGE_POLL_MS,
    CHALLENGE_WAIT_MS,
    DOM_QUIET_CAP_MS,
    DOM_QUIET_JS,
    DOM_QUIET_MS,
    DOM_QUIET_POLL_MS,
    MAX_CHALLENGE_ROUNDS,
    MUTATION_CLOCK_JS,
    NETWORKIDLE_TIMEOUT_MS,
    SETTLE_AFTER_NAVIGATION_MS,
    VIEWPORT,
    FetchError,
    FetcherStartError,
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
COURSE_HTML = "<html><body><h1>ENGL 101</h1></body></html>"
MAIN_FRAME = "main frame"

# The interstitial AWS WAF serves, trimmed to the parts the detector reads.
AWS_WAF_HTML = (
    "<html><head><script>window.gokuProps = {};</script>"
    '<script src="https://x.token.awswaf.com/x/challenge.js"></script>'
    '</head><body><div id="challenge-container"></div></body></html>'
)
AWS_WAF_HEADERS = {
    "content-type": "text/html",
    "x-amzn-waf-action": "challenge",
}
NAVIGATING = (
    "Page.content: Unable to retrieve content because the page is "
    "navigating and changing the content."
)
INTERRUPTED = (
    f'Page.goto: Navigation to "{URL}" is interrupted by another '
    f'navigation to "{URL}"\nCall log:'
)


class FakePlaywrightError(Exception):
    """Stands in for playwright.sync_api.Error."""


class FakePlaywrightTimeout(FakePlaywrightError):
    """Playwright's TimeoutError is a subclass of its Error, as here."""


class FakeRequest:
    def __init__(self, navigation: bool) -> None:
        self._navigation = navigation

    def is_navigation_request(self) -> bool:
        return self._navigation


class FakeResponse:
    """One response, and the HTML the page holds once it has loaded."""

    def __init__(
        self,
        status: int,
        headers: dict | None,
        *,
        html: str = COURSE_HTML,
        navigation: bool = True,
        frame: str = MAIN_FRAME,
    ) -> None:
        self.status = status
        self.headers = headers
        self.html = html
        self.request = FakeRequest(navigation)
        self.frame = frame


class FakeNavigation:
    """A goto that sees several responses, such as a redirect or a reload.

    The page holds the HTML of the last main-frame document among them.
    """

    def __init__(
        self,
        responses: list[FakeResponse],
        *,
        returns: FakeResponse | None = None,
        raises: Exception | None = None,
    ) -> None:
        self.responses = responses
        self.returns = returns
        self.raises = raises


class FakeClock:
    """Stands in for the time module; only a page's pauses move it."""

    def __init__(self) -> None:
        self.now = 0.0

    def perf_counter(self) -> float:
        return self.now


class FakePage:
    def __init__(self, context: FakeContext) -> None:
        self._context = context
        self.waits: list[str] = []
        # Everything after goto, in order: content reads, readiness waits,
        # and pauses while a challenge runs.
        self.log: list[tuple] = []
        self.functions: list[tuple] = []
        self.handlers: dict[str, list] = {}
        self.timeout: int | None = None
        self.url = "about:blank"
        self.html = COURSE_HTML
        self.main_frame = MAIN_FRAME
        self.cookies_at_open = list(context.jar)
        self.closed = False

    def set_default_timeout(self, timeout: int) -> None:
        self.timeout = timeout

    def on(self, event: str, handler) -> None:
        self.handlers.setdefault(event, []).append(handler)

    def goto(self, url: str, *, wait_until: str, timeout: int):
        self.waits.append(wait_until)
        outcome = self._context.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        if outcome is None:
            return None
        if not isinstance(outcome, FakeNavigation):
            outcome = FakeNavigation([outcome], returns=outcome)
        for response in outcome.responses:
            for handler in self.handlers.get("response", []):
                handler(response)
            if response.frame == self.main_frame:
                self.html = response.html
        self.url = f"{url}?landed"
        if outcome.raises:
            raise outcome.raises
        return outcome.returns

    def content(self) -> str:
        self.log.append(("content",))
        if self._context.contents:
            scripted = self._context.contents.pop(0)
            if isinstance(scripted, Exception):
                raise scripted
            return scripted
        return self.html

    def wait_for_load_state(self, state: str, *, timeout=None) -> None:
        self.log.append((state, timeout))
        if state in self._context.wait_errors:
            raise self._context.wait_errors[state]

    def wait_for_function(
        self, expression: str, *, arg=None, polling=None, timeout=None
    ) -> None:
        self.log.append(("dom quiet", timeout))
        self.functions.append((expression, arg, polling, timeout))
        if "dom quiet" in self._context.wait_errors:
            raise self._context.wait_errors["dom quiet"]

    def wait_for_timeout(self, timeout: float) -> None:
        if self.closed:
            raise FakePlaywrightError("Target page has been closed")
        self.log.append(("pause", timeout))
        self._context.tick(timeout)

    def close(self) -> None:
        self.closed = True
        if self._context.page_close_error:
            raise self._context.page_close_error


class FakeContext:
    def __init__(self) -> None:
        self.options: dict | None = None
        self.init_scripts: list[str | None] = []
        self.outcomes: list = []
        # content() answers, consumed in order across pages; once empty a
        # page answers with the HTML of the document it loaded.
        self.contents: list = []
        # A readiness wait ("networkidle", "load", "dom quiet") that fails.
        self.wait_errors: dict[str, Exception] = {}
        # The cookie jar, and what it becomes after each pause: a challenge
        # script earning its token while the fetcher waits.
        self.jar: list[dict] = []
        self.jar_after_pause: list[list[dict]] = []
        self.cookie_error: Exception | None = None
        self.clock: FakeClock | None = None
        self.pages: list[FakePage] = []
        self.page_close_error: Exception | None = None
        self.closed = False

    def add_init_script(self, script: str | None = None) -> None:
        self.init_scripts.append(script)

    def new_page(self) -> FakePage:
        self.pages.append(FakePage(self))
        return self.pages[-1]

    def cookies(self, urls=None) -> list[dict]:
        if self.cookie_error:
            raise self.cookie_error
        return list(self.jar)

    def storage_state(self) -> dict:
        """What Playwright hands back: the jar, plus local storage."""
        if self.cookie_error:
            raise self.cookie_error
        return {"cookies": list(self.jar), "origins": []}

    def tick(self, ms: float) -> None:
        if self.jar_after_pause:
            self.jar = self.jar_after_pause.pop(0)
        if self.clock:
            self.clock.now += ms / 1000

    def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self, context: FakeContext) -> None:
        self.context = context
        self.closed = False
        # The options of every context opened, first to last.
        self.contexts_opened: list[dict] = []

    def new_context(self, **options) -> FakeContext:
        self.context.options = options
        self.contexts_opened.append(options)
        # One fake stands in for each browser opened again: open once more.
        self.closed = False
        self.context.closed = False
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
        self.starts = 0

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
            playwright.starts += 1
            playwright.stopped = False
            return playwright

    module = types.ModuleType("playwright.sync_api")
    # Through __dict__: a bare ModuleType has no such attributes to assign.
    module.__dict__.update(
        Error=FakePlaywrightError,
        TimeoutError=FakePlaywrightTimeout,
        sync_playwright=Starter,
    )
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


def test_the_fetcher_starts_chromium_and_opens_one_context(browser) -> None:
    PlaywrightFetcher(user_agent="xtra-test")
    assert browser.chromium.launches == [{"headless": True}]
    assert browser.context.options == {
        "viewport": VIEWPORT,
        "user_agent": "xtra-test",
        "ignore_https_errors": True,
        "accept_downloads": False,
    }


def test_the_fetcher_starts_chrome_when_asked(browser) -> None:
    PlaywrightFetcher(user_agent="xtra-test", browser="chrome")
    assert browser.chromium.launches == [
        {"headless": True, "channel": "chrome"}
    ]


def test_chrome_asked_for_and_not_installed_stops_the_run(browser) -> None:
    """Never quietly a Chromium run: the run asked for Chrome."""
    browser.chromium.chrome_installed = False
    with pytest.raises(FetcherStartError, match="'chrome' is not found"):
        PlaywrightFetcher(user_agent="xtra-test", browser="chrome")
    assert browser.chromium.launches == [
        {"headless": True, "channel": "chrome"}
    ]


def test_an_unknown_browser_is_refused(browser) -> None:
    with pytest.raises(ValueError, match="browser is one of"):
        PlaywrightFetcher(user_agent="xtra-test", browser="firefox")


def test_the_factory_passes_the_browser_on(browser) -> None:
    playwright_fetcher_factory(browser="chrome")()
    assert browser.chromium.launches == [
        {"headless": True, "channel": "chrome"}
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


def _fetch() -> FetchResult:
    return PlaywrightFetcher(user_agent="xtra-test").fetch(URL)


def rendered(result: FetchResult) -> dict[str, Any]:
    """The render record, which the browser fetcher always writes."""
    assert result.render is not None
    return result.render


def _token(value: str, name: str = "aws-waf-token") -> dict:
    return {"name": name, "value": value, "domain": "catalog.example.edu"}


def _waf_challenge(headers: dict | None = None) -> FakeResponse:
    return FakeResponse(
        202,
        AWS_WAF_HEADERS if headers is None else headers,
        html=AWS_WAF_HTML,
    )


def _real_page() -> FakeResponse:
    return FakeResponse(200, {"content-type": "text/html; charset=utf-8"})


def test_the_context_installs_the_mutation_clock(browser) -> None:
    """Once per context, so it runs in every document from its first node."""
    PlaywrightFetcher(user_agent="xtra-test")
    assert browser.context.init_scripts == [MUTATION_CLOCK_JS]


def test_the_mutation_clock_counts_content_changes_and_not_attributes() -> None:
    """A carousel toggling classes would otherwise never let a page go quiet."""
    assert "childList: true" in MUTATION_CLOCK_JS
    assert "characterData: true" in MUTATION_CLOCK_JS
    assert "attributes" not in MUTATION_CLOCK_JS


def test_a_page_is_read_after_network_idle_and_a_quiet_dom(browser) -> None:
    browser.context.outcomes.append(_real_page())
    result = _fetch()
    page = browser.context.pages[0]
    assert page.waits == ["load"]
    # The first read only looks for a challenge; the page is read again
    # once both waits are over.
    assert page.log == [
        ("content",),
        ("networkidle", NETWORKIDLE_TIMEOUT_MS),
        ("dom quiet", DOM_QUIET_CAP_MS),
        ("content",),
    ]
    assert page.functions == [
        (DOM_QUIET_JS, DOM_QUIET_MS, DOM_QUIET_POLL_MS, DOM_QUIET_CAP_MS)
    ]
    assert result.html == COURSE_HTML
    assert rendered(result)["load_event"] == "load"
    assert rendered(result)["networkidle"] is True
    assert rendered(result)["dom_quiet"] is True
    assert rendered(result)["content_attempts"] == 1
    assert rendered(result)["ready_ms"] >= 0
    assert "challenge" not in rendered(result)
    assert page.closed


def test_a_page_that_never_goes_network_idle_is_taken_at_the_cap(
    browser,
) -> None:
    browser.context.outcomes.append(_real_page())
    browser.context.wait_errors["networkidle"] = FakePlaywrightTimeout(
        "Timeout 15000ms exceeded."
    )
    result = _fetch()
    assert result.http_status == 200
    assert result.html == COURSE_HTML
    assert rendered(result)["networkidle"] is False
    assert rendered(result)["dom_quiet"] is True


@pytest.mark.parametrize(
    ("error", "recorded"),
    [
        (FakePlaywrightTimeout("Timeout 3000ms exceeded."), None),
        (
            FakePlaywrightError(
                "Execution context was destroyed, most likely because of a "
                "navigation"
            ),
            "Execution context was destroyed, most likely because of a "
            "navigation",
        ),
    ],
)
def test_a_dom_that_does_not_go_quiet_is_still_taken(
    browser, error, recorded
) -> None:
    """At the cap, or when a navigation cut the check short."""
    browser.context.outcomes.append(_real_page())
    browser.context.wait_errors["dom quiet"] = error
    result = _fetch()
    assert result.html == COURSE_HTML
    assert rendered(result)["dom_quiet"] is False
    assert rendered(result).get("dom_quiet_error") == recorded


def test_content_read_mid_navigation_is_read_again_once_it_settles(
    browser,
) -> None:
    browser.context.outcomes.append(_real_page())
    browser.context.contents = [COURSE_HTML, FakePlaywrightError(NAVIGATING)]
    result = _fetch()
    page = browser.context.pages[0]
    assert page.log[3:] == [
        ("content",),
        ("load", None),
        ("networkidle", SETTLE_AFTER_NAVIGATION_MS),
        ("content",),
    ]
    assert result.html == COURSE_HTML
    assert rendered(result)["content_attempts"] == 2


def test_content_that_fails_for_another_reason_is_not_read_again(
    browser,
) -> None:
    browser.context.outcomes.append(_real_page())
    browser.context.contents = [
        COURSE_HTML,
        FakePlaywrightError("Target crashed\nCall log:"),
    ]
    with pytest.raises(FetchError) as raised:
        _fetch()
    page = browser.context.pages[0]
    assert str(raised.value) == "Target crashed"
    assert raised.value.retryable is True
    assert page.log.count(("content",)) == 2
    assert page.closed


def test_content_that_keeps_navigating_gives_up_after_its_attempts(
    browser,
) -> None:
    browser.context.outcomes.append(_real_page())
    browser.context.contents = [COURSE_HTML] + [
        FakePlaywrightError(NAVIGATING)
    ] * 3
    with pytest.raises(FetchError, match="page is navigating") as raised:
        _fetch()
    assert raised.value.retryable is True
    assert browser.context.pages[0].log.count(("content",)) == 4


def test_status_and_headers_come_from_the_newest_document(browser) -> None:
    """A script that navigated the page leaves the document that was read."""
    first = FakeResponse(200, {"content-type": "text/html"})
    newest = FakeResponse(
        410,
        {"content-type": "text/html; charset=utf-8", "retry-after": "30"},
        html="<html><body>Gone</body></html>",
    )
    browser.context.outcomes.append(
        FakeNavigation([first, newest], returns=first)
    )
    result = _fetch()
    assert result.http_status == 410
    assert result.content_type == "text/html; charset=utf-8"
    assert result.retry_after == 30.0
    assert "Gone" in result.html


def test_redirects_iframes_and_subresources_are_not_the_page(browser) -> None:
    document = FakeResponse(200, {"content-type": "text/html"})
    browser.context.outcomes.append(
        FakeNavigation(
            [
                document,
                FakeResponse(500, {"content-type": "text/html"}, frame="ad"),
                FakeResponse(
                    404, {"content-type": "image/png"}, navigation=False
                ),
                FakeResponse(302, {"location": "/elsewhere"}),
            ],
            returns=document,
        )
    )
    result = _fetch()
    assert result.http_status == 200
    assert result.content_type == "text/html"


def test_a_waf_challenge_is_waited_out_and_the_real_page_returned(
    browser,
) -> None:
    browser.context.outcomes += [_waf_challenge(), _real_page()]
    browser.context.jar_after_pause = [[], [_token("fresh")]]
    result = _fetch()
    challenge_page, real_page = browser.context.pages
    # The header said challenge, so the interstitial was never waited on
    # or read: its page only paused, still open, until the token arrived.
    assert challenge_page.log == [("pause", CHALLENGE_POLL_MS)] * 2
    assert challenge_page.closed
    assert real_page.cookies_at_open == [_token("fresh")]
    assert real_page.closed
    assert result.http_status == 200
    assert result.html == COURSE_HTML
    assert "gokuProps" not in result.html
    assert rendered(result)["challenge"] == "aws-waf"
    assert rendered(result)["challenge_rounds"] == 1
    assert rendered(result)["challenge_wait_ms"] >= 0
    assert rendered(result)["networkidle"] is True


def test_a_challenge_known_only_by_its_markers_is_waited_out_too(
    browser,
) -> None:
    browser.context.outcomes += [
        _waf_challenge({"content-type": "text/html"}),
        _real_page(),
    ]
    browser.context.jar_after_pause = [[_token("fresh")]]
    result = _fetch()
    challenge_page = browser.context.pages[0]
    assert challenge_page.log == [("content",), ("pause", CHALLENGE_POLL_MS)]
    assert result.http_status == 200
    assert result.html == COURSE_HTML
    assert rendered(result)["challenge"] == "aws-waf"


def test_a_cloudflare_challenge_is_solved_by_its_clearance_cookie(
    browser,
) -> None:
    browser.context.outcomes += [
        FakeResponse(403, {"cf-mitigated": "challenge"}, html=""),
        _real_page(),
    ]
    browser.context.jar_after_pause = [[_token("ok", name="cf_clearance")]]
    result = _fetch()
    assert result.http_status == 200
    assert rendered(result)["challenge"] == "cloudflare"


def test_a_challenge_that_shows_up_during_the_wait_is_never_saved(
    browser,
) -> None:
    """The first look missed it, so the HTML read after the wait catches it."""
    browser.context.outcomes += [_real_page(), _real_page()]
    browser.context.contents = [
        FakePlaywrightError(NAVIGATING),
        AWS_WAF_HTML,
    ]
    browser.context.jar_after_pause = [[_token("fresh")]]
    result = _fetch()
    assert len(browser.context.pages) == 2
    assert result.html == COURSE_HTML
    assert rendered(result)["challenge"] == "aws-waf"


def test_a_challenge_that_never_earns_a_token_can_be_retried(browser) -> None:
    browser.context.outcomes.append(_waf_challenge())
    with pytest.raises(FetchError) as raised:
        _fetch()
    page = browser.context.pages[0]
    assert str(raised.value) == "aws-waf challenge did not resolve within 30 s"
    assert raised.value.retryable is True
    assert raised.value.reason is None
    assert page.log == [("pause", CHALLENGE_POLL_MS)] * (
        CHALLENGE_WAIT_MS // CHALLENGE_POLL_MS
    )
    assert page.closed
    assert len(browser.context.pages) == 1


def test_a_captcha_fails_for_good_and_is_not_a_skip(browser) -> None:
    """A person has to solve it, so retrying only spends the run's budget."""
    browser.context.outcomes.append(
        FakeResponse(405, {"x-amzn-waf-action": "captcha"})
    )
    with pytest.raises(FetchError, match="cannot solve it") as raised:
        _fetch()
    page = browser.context.pages[0]
    assert raised.value.retryable is False
    assert raised.value.reason is None
    assert page.log == []
    assert page.closed


def test_a_challenge_that_keeps_coming_back_gives_up(browser) -> None:
    browser.context.outcomes += [_waf_challenge()] * (MAX_CHALLENGE_ROUNDS + 1)
    browser.context.jar_after_pause = [
        [_token(f"token-{n}")] for n in range(MAX_CHALLENGE_ROUNDS)
    ]
    with pytest.raises(FetchError) as raised:
        _fetch()
    assert str(raised.value) == (
        f"aws-waf challenge came back {MAX_CHALLENGE_ROUNDS} times"
    )
    assert raised.value.retryable is True
    assert len(browser.context.pages) == MAX_CHALLENGE_ROUNDS + 1
    assert all(page.closed for page in browser.context.pages)


def test_a_stale_token_does_not_count_until_its_value_changes(
    browser,
) -> None:
    browser.context.jar = [_token("refused")]
    browser.context.outcomes += [_waf_challenge(), _real_page()]
    browser.context.jar_after_pause = [
        [_token("refused")],
        [_token("refused")],
        [_token("fresh")],
    ]
    result = _fetch()
    challenge_page = browser.context.pages[0]
    assert challenge_page.log == [("pause", CHALLENGE_POLL_MS)] * 3
    assert result.http_status == 200


def test_latency_covers_the_whole_fetch_with_its_challenge_rounds(
    browser, monkeypatch
) -> None:
    clock = FakeClock()
    monkeypatch.setattr(crawl_browser, "time", clock)
    browser.context.clock = clock
    browser.context.outcomes += [_waf_challenge(), _real_page()]
    browser.context.jar_after_pause = [[], [_token("fresh")]]
    result = _fetch()
    assert rendered(result)["challenge_wait_ms"] == 2 * CHALLENGE_POLL_MS
    assert result.latency_ms == 2 * CHALLENGE_POLL_MS
    assert rendered(result)["ready_ms"] == 0


def test_a_goto_cut_short_by_a_challenge_reload_waits_the_challenge_out(
    browser,
) -> None:
    browser.context.outcomes += [
        FakeNavigation(
            [_waf_challenge()], raises=FakePlaywrightError(INTERRUPTED)
        ),
        _real_page(),
    ]
    browser.context.jar_after_pause = [[_token("fresh")]]
    result = _fetch()
    assert browser.context.pages[0].waits == ["load"]
    assert result.http_status == 200
    assert rendered(result)["challenge"] == "aws-waf"
    assert rendered(result)["load_event"] == "load"


def test_a_goto_cut_short_by_a_reload_reads_the_page_it_reloaded_to(
    browser,
) -> None:
    reloaded = FakeResponse(200, {"content-type": "text/html"})
    browser.context.outcomes.append(
        FakeNavigation([reloaded], raises=FakePlaywrightError(INTERRUPTED))
    )
    result = _fetch()
    assert result.http_status == 200
    assert result.html == COURSE_HTML
    assert rendered(result)["load_event"] == "interrupted"
    assert rendered(result)["networkidle"] is True


def test_a_goto_cut_short_before_any_document_is_a_retryable_error(
    browser,
) -> None:
    browser.context.outcomes.append(
        FakeNavigation([], raises=FakePlaywrightError(INTERRUPTED))
    )
    with pytest.raises(FetchError, match="interrupted") as raised:
        _fetch()
    assert raised.value.retryable is True
    assert browser.context.pages[0].closed


def test_cookies_that_cannot_be_read_count_as_no_token(browser) -> None:
    browser.context.cookie_error = FakePlaywrightError("Target closed")
    browser.context.outcomes.append(_real_page())
    assert _fetch().http_status == 200


def test_a_browser_that_will_not_start_is_told_apart_from_a_crash() -> None:
    def no_browser():
        raise OSError("Executable doesn't exist")

    pool = WorkerPool(workers=1, fetcher_factory=no_browser, min_interval=0)
    try:
        error = pool.submit(lambda state: None).exception(timeout=10)
    finally:
        pool.close()
    assert isinstance(error, FetcherStartError)
    assert "browser could not start" in str(error)
    assert "Executable doesn't exist" in str(error)


def test_a_crash_while_fetching_is_not_a_start_failure() -> None:
    class Fetcher:
        def close(self) -> None:
            return None

    def crash(state):
        raise RuntimeError("page crashed")

    pool = WorkerPool(workers=1, fetcher_factory=Fetcher, min_interval=0)
    try:
        error = pool.submit(crash).exception(timeout=10)
    finally:
        pool.close()
    assert isinstance(error, RuntimeError)
    assert not isinstance(error, FetcherStartError)


# --- closed between pages, cookies kept -------------------------------------


def test_the_browser_is_closed_after_each_page(browser) -> None:
    browser.context.outcomes.append(FakeResponse(200, {}))
    fetcher = PlaywrightFetcher(user_agent="xtra-test")
    assert browser.playwright.starts == 1
    fetcher.fetch(URL)
    assert browser.context.closed
    assert browser.browser.closed
    assert browser.playwright.stopped


def test_the_next_page_opens_a_browser_again_with_the_cookies_kept(
    browser,
) -> None:
    browser.context.outcomes.extend([FakeResponse(200, {}), _real_page()])
    browser.context.jar = [_token("earned")]
    fetcher = PlaywrightFetcher(user_agent="xtra-test")
    fetcher.fetch(URL)
    fetcher.fetch(URL)
    assert browser.playwright.starts == 2
    assert browser.chromium.launches == [{"headless": True}] * 2
    first, second = browser.browser.contexts_opened
    assert "storage_state" not in first
    assert second["storage_state"] == {
        "cookies": [_token("earned")],
        "origins": [],
    }
    # Everything else about the context is the same as the first time.
    assert {k: v for k, v in second.items() if k != "storage_state"} == first
    assert browser.context.init_scripts == [MUTATION_CLOCK_JS] * 2
    assert browser.browser.closed


def test_a_token_a_challenge_earned_reaches_the_next_browser(browser) -> None:
    """Without it, every page would meet the challenge again."""
    browser.context.outcomes.extend(
        [_waf_challenge(), _real_page(), _real_page()]
    )
    browser.context.jar_after_pause = [[_token("fresh")]]
    fetcher = PlaywrightFetcher(user_agent="xtra-test")
    fetcher.fetch(URL)
    fetcher.fetch(URL)
    last = browser.browser.contexts_opened[-1]
    assert last["storage_state"]["cookies"] == [_token("fresh")]


def test_cookies_that_cannot_be_read_keep_the_ones_read_before(
    browser,
) -> None:
    browser.context.outcomes.extend(
        [FakeResponse(200, {}), FakeResponse(200, {}), FakeResponse(200, {})]
    )
    browser.context.jar = [_token("first")]
    fetcher = PlaywrightFetcher(user_agent="xtra-test")
    fetcher.fetch(URL)
    browser.context.cookie_error = FakePlaywrightError("Target closed")
    fetcher.fetch(URL)
    browser.context.cookie_error = None
    fetcher.fetch(URL)
    last = browser.browser.contexts_opened[-1]
    assert last["storage_state"]["cookies"] == [_token("first")]


def test_a_failed_fetch_still_closes_the_browser(browser) -> None:
    browser.context.outcomes.append(
        FakePlaywrightError("net::ERR_CONNECTION_RESET")
    )
    fetcher = PlaywrightFetcher(user_agent="xtra-test")
    with pytest.raises(FetchError):
        fetcher.fetch(URL)
    assert browser.browser.closed
    assert browser.playwright.stopped


def test_keep_open_holds_one_browser_for_every_page(browser) -> None:
    browser.context.outcomes.extend([FakeResponse(200, {}), _real_page()])
    fetcher = PlaywrightFetcher(user_agent="xtra-test", keep_open=True)
    fetcher.fetch(URL)
    fetcher.fetch(URL)
    assert browser.playwright.starts == 1
    assert len(browser.chromium.launches) == 1
    assert not browser.browser.closed
    fetcher.close()
    assert browser.browser.closed
    assert browser.playwright.stopped


def test_a_browser_that_will_not_open_again_stops_the_run(browser) -> None:
    browser.context.outcomes.append(FakeResponse(200, {}))
    fetcher = PlaywrightFetcher(user_agent="xtra-test")
    fetcher.fetch(URL)

    def no_browser(**options):
        raise FakePlaywrightError("Executable doesn't exist at chrome.exe")

    browser.chromium.launch = no_browser
    with pytest.raises(FetcherStartError, match="could not start"):
        fetcher.fetch(URL)
    # Nothing half-open is left behind.
    assert browser.playwright.stopped


def test_closing_a_fetcher_that_is_already_closed_is_harmless(browser) -> None:
    browser.context.outcomes.append(FakeResponse(200, {}))
    fetcher = PlaywrightFetcher(user_agent="xtra-test")
    fetcher.fetch(URL)
    fetcher.close()
    fetcher.close()


def test_the_factory_passes_keep_open_on(browser) -> None:
    browser.context.outcomes.extend([FakeResponse(200, {}), _real_page()])
    fetcher = playwright_fetcher_factory(keep_open=True)()
    fetcher.fetch(URL)
    fetcher.fetch(URL)
    assert browser.playwright.starts == 1


def test_a_browser_that_will_not_start_is_reported_once() -> None:
    def factory():
        raise FetcherStartError("the browser could not start: no chrome.exe")

    pool = WorkerPool(workers=1, fetcher_factory=factory, min_interval=0)
    try:
        future = pool.submit(lambda state: None)
        error = future.exception(timeout=10)
    finally:
        pool.close()
    assert isinstance(error, FetcherStartError)
    assert str(error) == "the browser could not start: no chrome.exe"


# --- each worker its own pacing clock ---------------------------------------


def test_each_worker_gets_its_own_pacing_clock() -> None:
    pool = WorkerPool(
        workers=3,
        fetcher_factory=_CountingFetcher,
        min_interval=10,
        sleep=lambda seconds: None,
        monotonic=lambda: 0.0,
    )
    started = threading.Barrier(3)

    def take_a_turn(state):
        started.wait(timeout=10)
        return state.pacer, state.pacer.wait()

    try:
        futures = [pool.submit(take_a_turn) for _ in range(3)]
        results = [future.result(timeout=10) for future in futures]
    finally:
        pool.close()
    assert len({id(pacer) for pacer, _ in results}) == 3
    # Each worker's first GET waits for nothing.
    assert [wait for _, wait in results] == [0, 0, 0]
