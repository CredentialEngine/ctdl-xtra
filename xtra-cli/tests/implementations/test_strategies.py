from __future__ import annotations

from implementations.strategies import (
    CRAWL_STRATEGIES,
    DOWNLOAD_STRATEGIES,
    EXTRACT_STRATEGIES,
    TRANSFORM_STRATEGIES,
    unimplemented_message,
)


def test_crawl_strategies_include_playwright_and_future_backends() -> None:
    assert "playwright" in CRAWL_STRATEGIES
    assert "ai-agent" in CRAWL_STRATEGIES
    assert "third-party" in CRAWL_STRATEGIES


def test_extract_and_transform_share_ai_agent_extension_point() -> None:
    assert EXTRACT_STRATEGIES == ("template", "ai-agent")
    assert TRANSFORM_STRATEGIES == ("ctdl", "ai-agent")
    assert DOWNLOAD_STRATEGIES == CRAWL_STRATEGIES


def test_unimplemented_message_points_at_working_flag() -> None:
    message = unimplemented_message(
        "crawl", "ai-agent", implemented="playwright"
    )
    assert "--with-ai-agent" in message
    assert "--with-playwright" in message
    assert "not implemented" in message
