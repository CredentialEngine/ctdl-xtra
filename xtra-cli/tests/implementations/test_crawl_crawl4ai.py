from __future__ import annotations

import os
import sys
import types

import pytest

from implementations.crawl_browser import FetchError
from implementations.crawl_crawl4ai import (
    Crawl4aiFetcher,
    crawl4ai_fetcher_factory,
)

URL = "https://catalog.example.edu/courses/engl101"
HTML = "<html><body><h1>ENGL 101</h1></body></html>"


class FakeResult:
    def __init__(
        self,
        *,
        html=HTML,
        success=True,
        status_code=200,
        error_message="",
        redirected_url=None,
        response_headers=None,
    ) -> None:
        self.html = html
        self.success = success
        self.status_code = status_code
        self.error_message = error_message
        self.redirected_url = redirected_url
        self.url = URL
        self.response_headers = response_headers


class FakeCrawler:
    """Stands in for AsyncWebCrawler. Its methods are awaited, so async."""

    def __init__(self, config=None) -> None:
        self.config = config
        self.started = False
        self.closed = False
        self.asked: list[str] = []
        self.result = FakeResult()
        self.raises: Exception | None = None

    async def start(self):
        self.started = True

    async def close(self):
        self.closed = True

    async def arun(self, url, config=None):
        self.asked.append(url)
        if self.raises is not None:
            raise self.raises
        return self.result


def fake_module(monkeypatch) -> types.ModuleType:
    """Install a stand-in crawl4ai so the tests never need the real one."""
    module = types.ModuleType("crawl4ai")
    made: list[FakeCrawler] = []

    def build(config=None):
        crawler = FakeCrawler(config)
        made.append(crawler)
        return crawler

    module.AsyncWebCrawler = build
    module.BrowserConfig = lambda **kwargs: dict(kwargs)
    module.CrawlerRunConfig = lambda **kwargs: dict(kwargs)
    module.CacheMode = types.SimpleNamespace(BYPASS="bypass")
    module.made = made
    monkeypatch.setitem(sys.modules, "crawl4ai", module)
    return module


def fetcher(monkeypatch, **overrides) -> tuple[Crawl4aiFetcher, FakeCrawler]:
    module = fake_module(monkeypatch)
    made = Crawl4aiFetcher(user_agent="xtra-test", **overrides)
    return made, module.made[0]


def test_a_page_comes_back_with_its_status_type_and_timing(monkeypatch) -> None:
    made, crawler = fetcher(monkeypatch)
    crawler.result = FakeResult(
        response_headers={"Content-Type": "text/html; charset=utf-8"}
    )
    result = made.fetch(URL)
    assert crawler.started is True
    assert crawler.asked == [URL]
    assert result.requested_url == URL
    assert result.http_status == 200
    assert result.content_type.startswith("text/html")
    assert "ENGL 101" in result.html
    assert result.latency_ms >= 0


def test_the_browser_runs_headless_with_our_user_agent(monkeypatch) -> None:
    made, crawler = fetcher(monkeypatch)
    assert crawler.config["headless"] is True
    assert crawler.config["user_agent"] == "xtra-test"
    made.close()


def test_the_library_cache_is_always_bypassed(monkeypatch) -> None:
    """A cached hit would report a status and a latency that never happened."""
    made, _ = fetcher(monkeypatch)
    made.fetch(URL)
    assert made._run_config["cache_mode"] == "bypass"


def test_the_timeout_reaches_the_run_config(monkeypatch) -> None:
    made, _ = fetcher(monkeypatch, timeout_ms=12345)
    assert made._run_config["page_timeout"] == 12345


def test_a_redirect_the_crawler_followed_is_reported(monkeypatch) -> None:
    landed = "https://catalog.example.edu/courses/engl101/"
    made, crawler = fetcher(monkeypatch)
    crawler.result = FakeResult(redirected_url=landed)
    assert made.fetch(URL).final_url == landed


def test_the_page_status_is_carried_through(monkeypatch) -> None:
    made, crawler = fetcher(monkeypatch)
    crawler.result = FakeResult(status_code=503, html="")
    assert made.fetch(URL).http_status == 503


def test_a_missing_status_is_not_guessed_as_a_failure(monkeypatch) -> None:
    made, crawler = fetcher(monkeypatch)
    crawler.result = FakeResult(status_code=None)
    assert made.fetch(URL).http_status == 200


def test_a_retry_after_header_is_passed_to_the_backoff(monkeypatch) -> None:
    made, crawler = fetcher(monkeypatch)
    crawler.result = FakeResult(response_headers={"retry-after": "45"})
    assert made.fetch(URL).retry_after == 45.0


def test_an_unsuccessful_crawl_says_why(monkeypatch) -> None:
    made, crawler = fetcher(monkeypatch)
    crawler.result = FakeResult(
        success=False, error_message="net::ERR_CONNECTION_RESET", html=""
    )
    with pytest.raises(FetchError, match="ERR_CONNECTION_RESET"):
        made.fetch(URL)


def test_an_unsuccessful_crawl_with_no_message_still_raises(monkeypatch) -> None:
    made, crawler = fetcher(monkeypatch)
    crawler.result = FakeResult(success=False, error_message="", html="")
    with pytest.raises(FetchError, match="could not fetch"):
        made.fetch(URL)


def test_a_library_fault_is_worth_another_try(monkeypatch) -> None:
    made, crawler = fetcher(monkeypatch)
    crawler.raises = RuntimeError("browser crashed")
    with pytest.raises(FetchError) as caught:
        made.fetch(URL)
    assert caught.value.retryable is True


def test_closing_shuts_the_crawler_and_its_loop(monkeypatch) -> None:
    made, crawler = fetcher(monkeypatch)
    made.close()
    assert crawler.closed is True
    assert made._loop.is_closed()


def test_a_failed_close_never_fails_the_run(monkeypatch, caplog) -> None:
    made, crawler = fetcher(monkeypatch)

    async def boom():
        raise RuntimeError("already gone")

    crawler.close = boom
    with caplog.at_level("WARNING"):
        made.close()
    assert "did not close cleanly" in caplog.text
    assert made._loop.is_closed()


def test_the_factory_builds_one_fetcher_per_call(monkeypatch) -> None:
    fake_module(monkeypatch)
    factory = crawl4ai_fetcher_factory(user_agent="xtra-test")
    first, second = factory(), factory()
    assert first is not second
    first.close()
    second.close()


def test_a_missing_package_names_the_install_command(monkeypatch) -> None:
    """The extra is optional, so the error has to say how to get it."""
    monkeypatch.setitem(sys.modules, "crawl4ai", None)
    with pytest.raises(FetchError) as caught:
        Crawl4aiFetcher(user_agent="xtra-test")
    assert 'pip install -e ".[crawl4ai]"' in str(caught.value)
    assert caught.value.retryable is False


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("XTRA_BROWSER_TESTS"),
    reason="set XTRA_BROWSER_TESTS=1 to drive the real crawl4ai",
)
def test_the_real_library_renders_a_local_file(tmp_path) -> None:
    """The only test that uses the installed package, and it stays offline."""
    pytest.importorskip("crawl4ai")
    page = tmp_path / "page.html"
    page.write_text("<html><body><h1>ENGL 101</h1></body></html>", encoding="utf-8")
    made = Crawl4aiFetcher(user_agent="xtra-test")
    try:
        result = made.fetch(page.as_uri())
    finally:
        made.close()
    assert "ENGL 101" in result.html
