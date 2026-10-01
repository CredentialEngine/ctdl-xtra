from __future__ import annotations

import pytest

from implementations.crawl_crawl4ai import Crawl4aiFetcher
from implementations.crawl_fetchers import (
    IMPLEMENTED_CRAWL_STRATEGIES,
    STRATEGY_GUIDANCE,
    StrategyNotImplementedError,
    StrategyOptionError,
    fetcher_factory_for,
)
from implementations.crawl_firecrawl import FirecrawlFetcher
from implementations.strategies import CRAWL_STRATEGIES


def test_every_implemented_strategy_is_a_registered_one() -> None:
    assert set(IMPLEMENTED_CRAWL_STRATEGIES) <= set(CRAWL_STRATEGIES)


def test_every_implemented_strategy_says_when_to_pick_it() -> None:
    """The flag is only a real choice if the help says what it costs."""
    assert set(STRATEGY_GUIDANCE) == set(IMPLEMENTED_CRAWL_STRATEGIES)
    for name, line in STRATEGY_GUIDANCE.items():
        assert line.strip(), name


def test_choosing_a_strategy_returns_a_factory_and_starts_nothing() -> None:
    """Picking a backend must not open a browser or a socket."""
    for strategy in ("playwright", "crawl4ai"):
        assert callable(fetcher_factory_for(strategy))
    assert callable(fetcher_factory_for("firecrawl", firecrawl_api_key="k"))


def test_the_crawl4ai_strategy_builds_a_crawl4ai_fetcher(monkeypatch) -> None:
    import sys
    import types

    module = types.ModuleType("crawl4ai")
    module.AsyncWebCrawler = lambda config=None: _NoopCrawler()
    module.BrowserConfig = lambda **kwargs: kwargs
    module.CrawlerRunConfig = lambda **kwargs: kwargs
    module.CacheMode = types.SimpleNamespace(BYPASS="bypass")
    monkeypatch.setitem(sys.modules, "crawl4ai", module)

    made = fetcher_factory_for("crawl4ai")()
    assert isinstance(made, Crawl4aiFetcher)
    made.close()


class _NoopCrawler:
    async def start(self):
        return None

    async def close(self):
        return None


def test_the_firecrawl_strategy_builds_a_firecrawl_fetcher() -> None:
    made = fetcher_factory_for("firecrawl", firecrawl_api_key="fc-key")()
    assert isinstance(made, FirecrawlFetcher)


def test_a_self_hosted_firecrawl_endpoint_reaches_the_fetcher() -> None:
    made = fetcher_factory_for(
        "firecrawl",
        firecrawl_api_key="fc-key",
        firecrawl_api_url="http://firecrawl.internal:3002",
    )()
    assert made._endpoint == "http://firecrawl.internal:3002/v1/scrape"


def test_firecrawl_without_a_key_says_which_flag_is_missing() -> None:
    with pytest.raises(StrategyOptionError, match="--firecrawl-api-key"):
        fetcher_factory_for("firecrawl")
    with pytest.raises(StrategyOptionError, match="FIRECRAWL_API_KEY"):
        fetcher_factory_for("firecrawl", firecrawl_api_key="")


@pytest.mark.parametrize("strategy", ["ai-agent", "third-party"])
def test_a_reserved_strategy_fails_closed_and_names_the_working_ones(
    strategy: str,
) -> None:
    with pytest.raises(StrategyNotImplementedError) as caught:
        fetcher_factory_for(strategy)
    message = str(caught.value)
    assert f"--with-{strategy} is not implemented" in message
    assert "--with-playwright" in message
    assert "--with-crawl4ai" in message
    assert "--with-firecrawl" in message


def test_an_unknown_strategy_is_refused_the_same_way() -> None:
    with pytest.raises(StrategyNotImplementedError):
        fetcher_factory_for("crawlee")


def test_the_removed_http_strategy_is_gone() -> None:
    assert "http" not in IMPLEMENTED_CRAWL_STRATEGIES
    with pytest.raises(StrategyNotImplementedError):
        fetcher_factory_for("http")
