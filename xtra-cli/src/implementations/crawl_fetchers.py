"""Which backend does the fetching. One strategy name, one factory.

Everything else about a crawl is the same whichever backend runs it: the
frontier, the scope rules, robots.txt, the retry ladder, the pacing, the
checkpoints, the log lines, and everything discovery reads afterwards. A
strategy only decides how one URL turns into one FetchResult, which is why
adding one is a class and an entry here rather than a second crawler.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from implementations.crawl_browser import playwright_fetcher_factory
from implementations.crawl_crawl4ai import crawl4ai_fetcher_factory
from implementations.crawl_firecrawl import (
    DEFAULT_API_URL as DEFAULT_FIRECRAWL_API_URL,
)
from implementations.crawl_firecrawl import firecrawl_fetcher_factory
from implementations.strategies import unimplemented_message

STRATEGY_PLAYWRIGHT = "playwright"
STRATEGY_CRAWL4AI = "crawl4ai"
STRATEGY_FIRECRAWL = "firecrawl"

IMPLEMENTED_CRAWL_STRATEGIES = (
    STRATEGY_PLAYWRIGHT,
    STRATEGY_CRAWL4AI,
    STRATEGY_FIRECRAWL,
)

# What each one costs and what it buys, in one line, for --help and a README
# that has to answer "which do I pick" without a benchmark.
STRATEGY_GUIDANCE = {
    STRATEGY_PLAYWRIGHT: (
        "Renders JavaScript in a real browser. Slowest and heaviest, works "
        "on every catalog. The default choice when you do not know."
    ),
    STRATEGY_CRAWL4AI: (
        "An open-source crawler, no key and no bill. Brings stealth "
        "handling and hooks for clicking through a page before the HTML is "
        'taken. Optional extra: pip install -e ".[crawl4ai]"'
    ),
    STRATEGY_FIRECRAWL: (
        "A hosted crawler. Costs money per page and sends every URL to a "
        "third party. Worth it when a site blocks the browser we drive."
    ),
}


class StrategyNotImplementedError(RuntimeError):
    """A registered strategy with no backend behind it yet."""


class StrategyOptionError(ValueError):
    """A strategy was chosen without something it needs to run."""


def fetcher_factory_for(
    strategy: str,
    *,
    firecrawl_api_key: str | None = None,
    firecrawl_api_url: str = DEFAULT_FIRECRAWL_API_URL,
) -> Callable[[], Any]:
    """The factory a WorkerPool should build its per-thread fetchers from."""
    if strategy == STRATEGY_PLAYWRIGHT:
        return playwright_fetcher_factory()
    if strategy == STRATEGY_CRAWL4AI:
        return crawl4ai_fetcher_factory()
    if strategy == STRATEGY_FIRECRAWL:
        if not firecrawl_api_key:
            raise StrategyOptionError(
                "--with-firecrawl needs an API key. Pass "
                "--firecrawl-api-key or set FIRECRAWL_API_KEY."
            )
        return firecrawl_fetcher_factory(
            api_key=firecrawl_api_key, api_url=firecrawl_api_url
        )
    raise StrategyNotImplementedError(
        unimplemented_message(
            "crawl",
            strategy,
            implemented="playwright, --with-crawl4ai, or --with-firecrawl",
        )
    )
