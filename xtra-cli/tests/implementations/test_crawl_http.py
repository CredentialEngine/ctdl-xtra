from __future__ import annotations

import email.message
import urllib.error

import pytest

from implementations.crawl_browser import FetchError
from implementations.crawl_http import HttpFetcher, http_fetcher_factory

URL = "https://catalog.example.edu/courses/engl101"
BODY = b"<html><body><h1>ENGL 101</h1></body></html>"


def headers(**fields: str) -> email.message.Message:
    message = email.message.Message()
    for name, value in fields.items():
        message[name.replace("_", "-")] = value
    return message


class FakeResponse:
    def __init__(self, *, status=200, body=BODY, header_fields=None, url=URL):
        self.status = status
        self.headers = headers(**(header_fields or {"Content_Type": "text/html"}))
        self._body = body
        self._url = url

    def read(self, limit=None):
        return self._body

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None


def fetcher(open_url) -> HttpFetcher:
    return HttpFetcher(user_agent="xtra-test", open_url=open_url)


def test_a_page_comes_back_with_its_status_type_and_timing() -> None:
    result = fetcher(lambda request, timeout=None: FakeResponse()).fetch(URL)
    assert result.requested_url == URL
    assert result.final_url == URL
    assert result.http_status == 200
    assert result.content_type == "text/html"
    assert "ENGL 101" in result.html
    assert result.latency_ms >= 0


def test_the_request_carries_the_user_agent_and_asks_for_html() -> None:
    seen = {}

    def open_url(request, timeout=None):
        seen["agent"] = request.get_header("User-agent")
        seen["accept"] = request.get_header("Accept")
        seen["timeout"] = timeout
        return FakeResponse()

    HttpFetcher(user_agent="xtra-test", timeout=17, open_url=open_url).fetch(URL)
    assert seen["agent"] == "xtra-test"
    assert "text/html" in seen["accept"]
    assert seen["timeout"] == 17


def test_a_redirect_is_reported_as_the_url_that_answered() -> None:
    landed = "https://catalog.example.edu/courses/engl101/"
    result = fetcher(
        lambda request, timeout=None: FakeResponse(url=landed)
    ).fetch(URL)
    assert result.requested_url == URL
    assert result.final_url == landed


def test_an_http_error_is_an_answer_not_a_failure() -> None:
    """404 and 503 are the site talking, so the retry ladder decides."""

    def open_url(request, timeout=None):
        raise urllib.error.HTTPError(
            URL, 503, "Service Unavailable", headers(Retry_After="30"), None
        )

    result = fetcher(open_url).fetch(URL)
    assert result.http_status == 503
    assert result.retry_after == 30.0


def test_a_network_fault_is_worth_another_try() -> None:
    def open_url(request, timeout=None):
        raise TimeoutError("timed out")

    with pytest.raises(FetchError) as caught:
        fetcher(open_url).fetch(URL)
    assert caught.value.retryable is True


def test_the_server_charset_is_honoured() -> None:
    body = "<h1>Introducción</h1>".encode("latin-1")
    result = fetcher(
        lambda request, timeout=None: FakeResponse(
            body=body, header_fields={"Content_Type": "text/html; charset=latin-1"}
        )
    ).fetch(URL)
    assert "Introducción" in result.html


def test_bad_bytes_never_stop_a_crawl() -> None:
    result = fetcher(
        lambda request, timeout=None: FakeResponse(body=b"<h1>\xff\xfe</h1>")
    ).fetch(URL)
    assert "<h1>" in result.html


def test_a_non_html_content_type_is_passed_through_for_the_caller_to_skip() -> None:
    result = fetcher(
        lambda request, timeout=None: FakeResponse(
            body=b"%PDF-1.4", header_fields={"Content_Type": "application/pdf"}
        )
    ).fetch(URL)
    assert result.content_type == "application/pdf"


def test_closing_is_safe_because_nothing_is_held_open() -> None:
    made = fetcher(lambda request, timeout=None: FakeResponse())
    made.close()
    made.close()


def test_the_factory_builds_one_fetcher_per_call() -> None:
    factory = http_fetcher_factory(user_agent="xtra-test")
    assert factory() is not factory()


def test_the_factory_defaults_to_the_shared_user_agent() -> None:
    assert "Mozilla/5.0" in http_fetcher_factory()()._user_agent


def test_a_forgotten_fake_hits_the_no_network_guard() -> None:
    """The real urlopen is resolved per call, so the guard still applies."""
    with pytest.raises(AssertionError, match="tried to open"):
        HttpFetcher(user_agent="xtra-test").fetch(URL)
