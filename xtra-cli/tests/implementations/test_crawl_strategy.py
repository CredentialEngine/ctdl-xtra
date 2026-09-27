"""What a run records about the backend that fetched its pages."""

from __future__ import annotations

import inspect
import platform
from importlib.metadata import version

from implementations import crawl_strategy
from implementations.crawl_browser import DEFAULT_TIMEOUT_MS, VIEWPORT
from implementations.crawl_strategy import (
    STRATEGY_NOTES,
    StrategyFacts,
    package_version,
    strategy_facts,
)


def test_the_versions_are_read_from_the_installed_packages() -> None:
    """Hardcoding them would let crawl.json drift from what actually ran."""
    facts = strategy_facts("playwright")
    assert isinstance(facts, StrategyFacts)
    assert facts.version == {
        "python": platform.python_version(),
        "playwright": version("playwright"),
    }


def test_crawl4ai_reports_itself_and_the_browser_it_drives() -> None:
    assert set(strategy_facts("crawl4ai").version) == {
        "python",
        "crawl4ai",
        "playwright",
    }


def test_a_package_that_is_not_installed_is_recorded_as_null(
    monkeypatch,
) -> None:
    monkeypatch.setattr(crawl_strategy, "package_version", lambda name: None)
    assert strategy_facts("crawl4ai").version["crawl4ai"] is None


def test_package_version_of_something_nobody_has_installed() -> None:
    assert package_version("a-distribution-nobody-has-installed") is None


def test_the_playwright_settings_are_the_ones_the_fetcher_is_built_with() -> (
    None
):
    settings = strategy_facts("playwright").settings
    assert settings["timeout_ms"] == DEFAULT_TIMEOUT_MS
    assert settings["viewport"] == VIEWPORT
    assert settings["headless"] is True
    assert settings["accept_downloads"] is False
    assert settings["user_agent"].startswith("Mozilla/")


def test_the_crawl4ai_settings_say_its_cache_is_bypassed() -> None:
    assert strategy_facts("crawl4ai").settings["cache_mode"] == "BYPASS"


def test_the_firecrawl_endpoint_is_recorded_and_no_key_can_be() -> None:
    settings = strategy_facts(
        "firecrawl", firecrawl_api_url="https://firecrawl.example/"
    ).settings
    assert settings["endpoint"] == "https://firecrawl.example/v1/scrape"
    assert "api_key" not in inspect.signature(strategy_facts).parameters
    assert not [name for name in settings if "key" in name.lower()]


def test_every_working_backend_says_what_it_only_approximates() -> None:
    for name in ("playwright", "crawl4ai", "firecrawl"):
        notes = strategy_facts(name).notes
        assert notes == STRATEGY_NOTES[name]
        assert all(isinstance(note, str) and note for note in notes)


def test_a_backend_with_no_implementation_reports_nothing_invented() -> None:
    facts = strategy_facts("ai-agent")
    assert facts.version == {"python": platform.python_version()}
    assert facts.settings == {}
    assert facts.notes == ()
