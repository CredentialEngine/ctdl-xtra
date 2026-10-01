from __future__ import annotations

import json
import urllib.error

import pytest

from implementations.crawl_browser import FetchError
from implementations.crawl_firecrawl import (
    FirecrawlFetcher,
    firecrawl_fetcher_factory,
)

URL = "https://catalog.example.edu/courses/engl101"
KEY = "fc-secret-key-value"
HTML = "<html><body><h1>ENGL 101</h1></body></html>"

OK = {
    "success": True,
    "data": {
        "rawHtml": HTML,
        "metadata": {
            "statusCode": 200,
            "sourceURL": URL,
            "contentType": "text/html; charset=utf-8",
        },
    },
}


class FakeResponse:
    def __init__(self, payload) -> None:
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None


def answering(payload, seen=None):
    def open_url(request, timeout=None):
        if seen is not None:
            seen["url"] = request.full_url
            seen["method"] = request.get_method()
            seen["auth"] = request.get_header("Authorization")
            seen["body"] = json.loads(request.data.decode("utf-8"))
            seen["timeout"] = timeout
        return FakeResponse(payload)

    return open_url


def fetcher(open_url, **overrides) -> FirecrawlFetcher:
    options = {"api_key": KEY, "user_agent": "xtra-test", "open_url": open_url}
    options.update(overrides)
    return FirecrawlFetcher(**options)


def test_a_scraped_page_comes_back_as_html() -> None:
    result = fetcher(answering(OK)).fetch(URL)
    assert result.requested_url == URL
    assert result.final_url == URL
    assert result.http_status == 200
    assert result.content_type.startswith("text/html")
    assert "ENGL 101" in result.html
    assert result.latency_ms >= 0


def test_the_request_asks_for_raw_html_at_the_scrape_endpoint() -> None:
    seen: dict = {}
    fetcher(answering(OK, seen)).fetch(URL)
    assert seen["url"] == "https://api.firecrawl.dev/v1/scrape"
    assert seen["method"] == "POST"
    assert seen["body"]["url"] == URL
    assert seen["body"]["formats"] == ["rawHtml"]
    assert seen["body"]["onlyMainContent"] is False


def test_a_self_hosted_endpoint_is_used_when_given() -> None:
    seen: dict = {}
    fetcher(
        answering(OK, seen), api_url="http://firecrawl.internal:3002/"
    ).fetch(URL)
    assert seen["url"] == "http://firecrawl.internal:3002/v1/scrape"


def test_the_key_travels_in_one_header_and_nowhere_else(caplog) -> None:
    seen: dict = {}
    with caplog.at_level("DEBUG"):
        fetcher(answering(OK, seen)).fetch(URL)
    assert seen["auth"] == f"Bearer {KEY}"
    assert KEY not in json.dumps(seen["body"])
    assert KEY not in caplog.text


def test_the_page_status_comes_from_the_metadata_not_the_api_call() -> None:
    payload = {
        "success": True,
        "data": {
            "rawHtml": "",
            "metadata": {"statusCode": 404, "sourceURL": URL},
        },
    }
    assert fetcher(answering(payload)).fetch(URL).http_status == 404


def test_a_redirect_the_service_followed_is_reported() -> None:
    landed = "https://catalog.example.edu/courses/engl101/"
    payload = {
        "success": True,
        "data": {
            "rawHtml": HTML,
            "metadata": {"statusCode": 200, "sourceURL": landed},
        },
    }
    assert fetcher(answering(payload)).fetch(URL).final_url == landed


def test_a_response_without_the_data_envelope_still_reads() -> None:
    payload = {"rawHtml": HTML, "metadata": {"statusCode": 200}}
    assert "ENGL 101" in fetcher(answering(payload)).fetch(URL).html


def test_a_refused_scrape_is_not_retried() -> None:
    payload = {"success": False, "error": "url is not reachable"}
    with pytest.raises(FetchError) as caught:
        fetcher(answering(payload)).fetch(URL)
    assert caught.value.retryable is False
    assert "not reachable" in str(caught.value)


def test_rate_limiting_is_waited_out() -> None:
    def open_url(request, timeout=None):
        raise urllib.error.HTTPError(URL, 429, "Too Many Requests", None, None)

    with pytest.raises(FetchError) as caught:
        fetcher(open_url).fetch(URL)
    assert caught.value.retryable is True


def test_a_rejected_key_fails_fast_instead_of_burning_the_budget() -> None:
    """Six retries a page on a bad key would spend a whole crawl's money."""

    def open_url(request, timeout=None):
        raise urllib.error.HTTPError(URL, 401, "Unauthorized", None, None)

    with pytest.raises(FetchError) as caught:
        fetcher(open_url).fetch(URL)
    assert caught.value.retryable is False
    assert "401" in str(caught.value)


def test_a_network_fault_is_worth_another_try() -> None:
    def open_url(request, timeout=None):
        raise TimeoutError("timed out")

    with pytest.raises(FetchError) as caught:
        fetcher(open_url).fetch(URL)
    assert caught.value.retryable is True


def test_a_reply_that_is_not_json_says_so() -> None:
    class NotJson:
        def read(self):
            return b"<html>gateway error</html>"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

    with pytest.raises(FetchError, match="not JSON"):
        fetcher(lambda request, timeout=None: NotJson()).fetch(URL)


def test_a_fetcher_without_a_key_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="API key"):
        FirecrawlFetcher(api_key="", user_agent="xtra-test")


def test_closing_is_safe_because_nothing_is_held_open() -> None:
    made = fetcher(answering(OK))
    made.close()
    made.close()


def test_the_factory_builds_one_fetcher_per_call() -> None:
    factory = firecrawl_fetcher_factory(api_key=KEY, user_agent="xtra-test")
    assert factory() is not factory()


def test_a_forgotten_fake_hits_the_no_network_guard() -> None:
    with pytest.raises(AssertionError, match="tried to open"):
        FirecrawlFetcher(api_key=KEY, user_agent="xtra-test").fetch(URL)
