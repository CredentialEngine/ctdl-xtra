from __future__ import annotations

from implementations.strategies import (
    CRAWL_STRATEGIES,
    EXTRACT_STRATEGIES,
    TRANSFORM_STRATEGIES,
    unimplemented_message,
)


def test_crawl_strategies_include_the_backends_and_the_placeholders() -> None:
    for working in ("playwright", "crawl4ai", "firecrawl"):
        assert working in CRAWL_STRATEGIES
    for reserved in ("ai-agent", "third-party"):
        assert reserved in CRAWL_STRATEGIES


def test_extract_and_transform_share_ai_agent_extension_point() -> None:
    assert EXTRACT_STRATEGIES == ("template", "ai-agent")
    assert TRANSFORM_STRATEGIES == ("ctdl", "ai-agent")


def test_there_is_no_separate_download_verb() -> None:
    """Crawl saves pages and resumes, so page download was removed."""
    from implementations import strategies

    assert not hasattr(strategies, "DOWNLOAD_STRATEGIES")


def test_unimplemented_message_points_at_working_flag() -> None:
    message = unimplemented_message(
        "crawl", "ai-agent", implemented="playwright"
    )
    assert "--with-ai-agent" in message
    assert "--with-playwright" in message
    assert "not implemented" in message
