from __future__ import annotations

import gzip

import pytest

from implementations.crawl_robots import (
    SiteFetchError,
    browser_user_agent,
    collect_sitemap_urls,
    default_sitemap_url,
    no_rules,
    parse_sitemap,
    read_robots,
    resolve_final_url,
    robots_url,
)

SEED = "https://catalog.example.edu/"
NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'

URLSET = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset {NS}>
  <url><loc>https://catalog.example.edu/courses/engl101</loc></url>
  <url><loc>https://catalog.example.edu/courses/math101</loc></url>
  <url><loc>https://other.edu/elsewhere</loc></url>
</urlset>
""".encode()

INDEX = f"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex {NS}>
  <sitemap><loc>https://catalog.example.edu/sitemap-1.xml.gz</loc></sitemap>
</sitemapindex>
""".encode()


def test_robots_and_sitemap_urls_are_derived_from_the_seed() -> None:
    assert robots_url(SEED) == "https://catalog.example.edu/robots.txt"
    assert default_sitemap_url("https://catalog.example.edu/courses/a") == (
        "https://catalog.example.edu/sitemap.xml"
    )


def test_the_user_agent_comes_from_the_shared_config() -> None:
    assert "Mozilla/5.0" in browser_user_agent()


def test_rules_crawl_delay_and_sitemaps_are_read() -> None:
    body = (
        b"User-agent: *\n"
        b"Disallow: /private/\n"
        b"Crawl-delay: 7\n"
        b"Sitemap: https://catalog.example.edu/sitemap-news.xml\n"
    )
    rules = read_robots(SEED, fetch=lambda url: (200, body))
    assert rules.robots_status == 200
    assert rules.crawl_delay == 7.0
    assert rules.sitemap_urls == ("https://catalog.example.edu/sitemap-news.xml",)
    assert not rules.robots.can_fetch("*", "https://catalog.example.edu/private/x")
    assert rules.robots.can_fetch("*", "https://catalog.example.edu/courses/x")


@pytest.mark.parametrize("status", [403, 404, 410])
def test_a_4xx_robots_means_no_rules(status: int) -> None:
    rules = read_robots(SEED, fetch=lambda url: (status, b"denied"))
    assert rules.robots_status == status
    assert rules.crawl_delay is None
    assert rules.robots.can_fetch("*", "https://catalog.example.edu/anything")


def test_a_5xx_robots_means_no_rules_and_a_warning(caplog) -> None:
    with caplog.at_level("WARNING"):
        rules = read_robots(SEED, fetch=lambda url: (503, b""))
    assert rules.robots_status == 503
    assert rules.robots.can_fetch("*", "https://catalog.example.edu/anything")
    assert "no rules" in caplog.text


def test_an_unreachable_robots_means_no_rules_and_a_warning(caplog) -> None:
    def boom(url: str):
        raise SiteFetchError("connection refused")

    with caplog.at_level("WARNING"):
        rules = read_robots(SEED, fetch=boom)
    assert rules.robots_status is None
    assert rules.robots.can_fetch("*", "https://catalog.example.edu/anything")
    assert "unreachable" in caplog.text


def test_no_rules_allows_everything() -> None:
    assert no_rules().can_fetch("*", "https://catalog.example.edu/anything")


def test_parse_sitemap_reads_a_urlset_and_an_index() -> None:
    assert parse_sitemap(URLSET)[0] == "urlset"
    assert len(parse_sitemap(URLSET)[1]) == 3
    assert parse_sitemap(INDEX)[0] == "sitemapindex"
    assert parse_sitemap(b"not xml") == ("", [])


def test_a_sitemap_index_is_followed_and_gzip_is_unwrapped() -> None:
    documents = {
        "https://catalog.example.edu/sitemap.xml": INDEX,
        "https://catalog.example.edu/sitemap-1.xml.gz": gzip.compress(URLSET),
    }
    pages = collect_sitemap_urls(
        ["https://catalog.example.edu/sitemap.xml"],
        fetch=lambda url: (200, documents[url]),
    )
    assert pages == [
        "https://catalog.example.edu/courses/engl101",
        "https://catalog.example.edu/courses/math101",
        "https://other.edu/elsewhere",
    ]


def test_a_missing_sitemap_yields_nothing() -> None:
    assert collect_sitemap_urls(["https://x.edu/sitemap.xml"],
                               fetch=lambda url: (404, b"")) == []


def test_an_unreachable_sitemap_is_warned_about_not_raised(caplog) -> None:
    def boom(url: str):
        raise SiteFetchError("timed out")

    with caplog.at_level("WARNING"):
        assert collect_sitemap_urls(["https://x.edu/sitemap.xml"], fetch=boom) == []
    assert "unreachable" in caplog.text


def test_a_self_referencing_index_cannot_loop() -> None:
    self_index = f"""<?xml version="1.0"?>
    <sitemapindex {NS}>
      <sitemap><loc>https://x.edu/sitemap.xml</loc></sitemap>
    </sitemapindex>
    """.encode()
    calls: list[str] = []

    def fetch(url: str):
        calls.append(url)
        return 200, self_index

    assert collect_sitemap_urls(["https://x.edu/sitemap.xml"], fetch=fetch) == []
    assert calls == ["https://x.edu/sitemap.xml"]


class _FakeResponse:
    def __init__(self, url: str) -> None:
        self._url = url

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


def test_resolve_final_url_reports_where_a_seed_answers(monkeypatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: _FakeResponse("https://catalog.new.edu/"),
    )
    assert resolve_final_url(SEED) == "https://catalog.new.edu/"


def test_resolve_final_url_falls_back_to_the_url_it_was_given(monkeypatch) -> None:
    """A site that refuses urllib is still crawled from the typed URL."""

    def boom(request, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert resolve_final_url(SEED) == SEED
