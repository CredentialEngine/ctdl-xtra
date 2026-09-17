from __future__ import annotations

import os
import threading

import pytest

from implementations.crawl_browser import (
    FetchError,
    FetchResult,
    WorkerPool,
    retry_after_seconds,
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
    pool = WorkerPool(workers=1, fetcher_factory=_CountingFetcher, min_interval=0)
    pool.close()
    pool.close()


def test_closing_a_pool_that_never_fetched_does_not_hang() -> None:
    pool = WorkerPool(workers=4, fetcher_factory=_CountingFetcher, min_interval=0)
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
    page.write_text("<html><body><h1>ENGL 101</h1></body></html>", encoding="utf-8")
    fetcher = PlaywrightFetcher(user_agent="xtra-test")
    try:
        result = fetcher.fetch(page.as_uri())
    finally:
        fetcher.close()
    assert "ENGL 101" in result.html
    assert result.latency_ms >= 0
