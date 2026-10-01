"""What actually ran, in enough detail to compare two runs.

A run that records only "playwright" cannot be reproduced later: the
browser, the crawler library, and the Python that drove them all move under
us. So a crawl records the versions it had installed, the settings the
backend was handed, and the places where a backend honours one of those
settings only approximately.

Versions are read from package metadata rather than written down here, so
they cannot drift from what is installed, and asking which version crawl4ai
is does not import crawl4ai or the dependency tree behind it.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version
from typing import Any

from implementations.crawl_browser import (
    CHALLENGE_WAIT_MS,
    CONTENT_ATTEMPTS,
    DEFAULT_TIMEOUT_MS,
    DOM_QUIET_CAP_MS,
    DOM_QUIET_MS,
    MAX_CHALLENGE_ROUNDS,
    NETWORKIDLE_TIMEOUT_MS,
    VIEWPORT,
)
from implementations.crawl_challenge import (
    CHALLENGE_AWS_WAF,
    CHALLENGE_AWS_WAF_CAPTCHA,
    CHALLENGE_CLOUDFLARE,
    CHALLENGE_TOKEN_COOKIES,
)
from implementations.crawl_crawl4ai import (
    DEFAULT_TIMEOUT_MS as CRAWL4AI_TIMEOUT_MS,
)
from implementations.crawl_fetchers import (
    STRATEGY_CRAWL4AI,
    STRATEGY_FIRECRAWL,
    STRATEGY_PLAYWRIGHT,
)
from implementations.crawl_firecrawl import (
    DEFAULT_API_URL,
    DEFAULT_FORMAT,
    DEFAULT_TIMEOUT_SECONDS,
    SCRAPE_PATH,
)
from implementations.crawl_robots import browser_user_agent

# The distributions each backend runs on. firecrawl has none: it is called
# over stdlib HTTP with no SDK.
STRATEGY_PACKAGES = {
    STRATEGY_PLAYWRIGHT: ("playwright",),
    STRATEGY_CRAWL4AI: ("crawl4ai", "playwright"),
    STRATEGY_FIRECRAWL: (),
}

# Only the approximations belong here. A setting a backend honours exactly
# is already in strategy_settings and needs no explaining.
STRATEGY_NOTES = {
    STRATEGY_PLAYWRIGHT: (
        # The 500 ms between requests is Playwright's own definition of
        # network idle, not a setting of this crawler.
        (
            "The HTML is taken after the load event (or DOMContentLoaded "
            "when load times out), then once the network has gone idle, "
            f"waited for up to {NETWORKIDLE_TIMEOUT_MS // 1000} s, then once "
            f"the DOM has gone {DOM_QUIET_MS} ms without a content change, "
            f"waited for up to {DOM_QUIET_CAP_MS // 1000} s. A page that "
            "never goes network-idle is captured at the cap, and a page "
            "that pauses more than 500 ms between its own requests can be "
            "captured before the later ones."
        ),
        (
            "A bot-challenge interstitial is waited out in the same browser "
            "context and never saved. Every new browser context (each "
            "worker, each run) is challenged once per host, so the first "
            "page a worker fetches from a protected host takes longer."
        ),
        (
            "A navigation the browser turns into a download is recorded as "
            "a skip with reason non_html, because no page was rendered."
        ),
    ),
    STRATEGY_CRAWL4AI: (
        (
            "Crawl4AI waits and retries inside one fetch of its own, so "
            "attempts in the sidecar counts this crawl's attempts and not "
            "the requests the library made."
        ),
        (
            "The HTTP status comes from the library's result and falls "
            "back to 200 when it reports none, so a 200 here is not proof "
            "the site sent one."
        ),
    ),
    STRATEGY_FIRECRAWL: (
        (
            "The service decides how long to render and may answer from "
            "its own cache, so retrieved_at is when the API answered "
            "rather than when the page was rendered."
        ),
        (
            "The status and the final URL come from the service's metadata "
            "and fall back to 200 and the requested URL when it sends "
            "neither."
        ),
    ),
}


def package_version(name: str) -> str | None:
    """The installed version of one distribution, or None when absent."""
    try:
        return installed_version(name)
    except PackageNotFoundError:
        return None


@dataclass(frozen=True)
class StrategyFacts:
    """Versions, settings, and caveats for the backend one run used."""

    version: dict[str, str | None]
    settings: dict[str, Any]
    notes: tuple[str, ...]


def _versions(strategy: str) -> dict[str, str | None]:
    versions: dict[str, str | None] = {"python": platform.python_version()}
    for name in STRATEGY_PACKAGES.get(strategy, ()):
        versions[name] = package_version(name)
    return versions


def _settings(
    strategy: str, *, firecrawl_api_url: str, user_agent: str
) -> dict[str, Any]:
    if strategy == STRATEGY_PLAYWRIGHT:
        return {
            "headless": True,
            "browser_channel": "chrome, falling back to chromium",
            "viewport": dict(VIEWPORT),
            "wait_until": "load, then domcontentloaded when load times out",
            "ready_wait": {
                "networkidle_timeout_ms": NETWORKIDLE_TIMEOUT_MS,
                "dom_quiet_ms": DOM_QUIET_MS,
                "dom_quiet_cap_ms": DOM_QUIET_CAP_MS,
                "dom_quiet_mutations": ["childList", "characterData"],
                "content_attempts": CONTENT_ATTEMPTS,
            },
            "challenge_wait": {
                "detects": [
                    CHALLENGE_AWS_WAF,
                    CHALLENGE_AWS_WAF_CAPTCHA,
                    CHALLENGE_CLOUDFLARE,
                ],
                "wait_ms": CHALLENGE_WAIT_MS,
                "max_rounds": MAX_CHALLENGE_ROUNDS,
                "token_cookies": list(CHALLENGE_TOKEN_COOKIES),
            },
            "timeout_ms": DEFAULT_TIMEOUT_MS,
            "ignore_https_errors": True,
            "accept_downloads": False,
            "user_agent": user_agent,
        }
    if strategy == STRATEGY_CRAWL4AI:
        return {
            "headless": True,
            "cache_mode": "BYPASS",
            "page_timeout_ms": CRAWL4AI_TIMEOUT_MS,
            "verbose": False,
            "user_agent": user_agent,
        }
    if strategy == STRATEGY_FIRECRAWL:
        return {
            "endpoint": f"{firecrawl_api_url.rstrip('/')}{SCRAPE_PATH}",
            "formats": [DEFAULT_FORMAT],
            "only_main_content": False,
            "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
            "user_agent": user_agent,
        }
    return {}


def strategy_facts(
    strategy: str,
    *,
    firecrawl_api_url: str = DEFAULT_API_URL,
    user_agent: str | None = None,
) -> StrategyFacts:
    """What a run can say about the backend it is about to use.

    An API key is never part of this. The endpoint a key would be sent to
    is, because that is what identifies which service answered.
    """
    return StrategyFacts(
        version=_versions(strategy),
        settings=_settings(
            strategy,
            firecrawl_api_url=firecrawl_api_url,
            user_agent=user_agent or browser_user_agent(),
        ),
        notes=STRATEGY_NOTES.get(strategy, ()),
    )
