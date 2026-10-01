"""What a run records about the backend that fetched its pages."""

from __future__ import annotations

import inspect
import json
import platform
from importlib.metadata import version

from implementations import crawl_strategy
from implementations.crawl_browser import (
    CHALLENGE_WAIT_MS,
    CONTENT_ATTEMPTS,
    DEFAULT_TIMEOUT_MS,
    DOM_QUIET_CAP_MS,
    DOM_QUIET_MS,
    MAX_CHALLENGE_ROUNDS,
    MUTATION_CLOCK_JS,
    NETWORKIDLE_TIMEOUT_MS,
    VIEWPORT,
)
from implementations.crawl_challenge import CHALLENGE_TOKEN_COOKIES
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


def test_the_playwright_settings_record_how_long_a_page_is_waited_for() -> None:
    settings = strategy_facts("playwright").settings
    assert settings["ready_wait"] == {
        "networkidle_timeout_ms": NETWORKIDLE_TIMEOUT_MS,
        "dom_quiet_ms": DOM_QUIET_MS,
        "dom_quiet_cap_ms": DOM_QUIET_CAP_MS,
        "dom_quiet_mutations": ["childList", "characterData"],
        "content_attempts": CONTENT_ATTEMPTS,
    }


def test_the_recorded_mutations_are_the_ones_the_page_clock_watches() -> None:
    """A setting the browser script does not honour would be a false record."""
    mutations = strategy_facts("playwright").settings["ready_wait"][
        "dom_quiet_mutations"
    ]
    for mutation in mutations:
        assert f"{mutation}: true" in MUTATION_CLOCK_JS


def test_the_playwright_settings_record_which_challenges_are_waited_out() -> (
    None
):
    settings = strategy_facts("playwright").settings
    assert settings["challenge_wait"] == {
        "detects": ["aws-waf", "aws-waf-captcha", "cloudflare"],
        "wait_ms": CHALLENGE_WAIT_MS,
        "max_rounds": MAX_CHALLENGE_ROUNDS,
        "token_cookies": list(CHALLENGE_TOKEN_COOKIES),
    }


def test_the_playwright_settings_can_be_written_to_crawl_json() -> None:
    settings = strategy_facts("playwright").settings
    assert json.loads(json.dumps(settings)) == settings


def test_the_playwright_notes_say_when_the_html_is_taken() -> None:
    taken = STRATEGY_NOTES["playwright"][0]
    assert "DOMContentLoaded" in taken
    assert f"up to {NETWORKIDLE_TIMEOUT_MS // 1000} s" in taken
    assert f"{DOM_QUIET_MS} ms without a content change" in taken
    assert f"up to {DOM_QUIET_CAP_MS // 1000} s" in taken
    assert "captured at the cap" in taken


def test_the_playwright_notes_say_a_challenge_is_never_saved() -> None:
    notes = STRATEGY_NOTES["playwright"]
    challenge = [note for note in notes if "challenge" in note]
    assert len(challenge) == 1
    assert "never saved" in challenge[0]
    assert "once per host" in challenge[0]


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
