"""Strategy names for crawl / extract / transform.

Review: keep the same --with-<strategy> pattern so new backends can be
added later. Crawl has three: playwright renders in a browser, http
does not render at all, firecrawl hands the page to a hosted service.
ai-agent and third-party stay registered and fail closed.
"""

from __future__ import annotations

CRAWL_STRATEGIES = (
    "playwright",
    "http",
    "firecrawl",
    "ai-agent",
    "third-party",
)
EXTRACT_STRATEGIES = ("template", "ai-agent")
TRANSFORM_STRATEGIES = ("ctdl", "ai-agent")


def unimplemented_message(verb: str, strategy: str, *, implemented: str) -> str:
    return (
        f"{verb} --with-{strategy} is not implemented yet. "
        f"Use --with-{implemented}. Additional strategies can be added as "
        f"src/xtra/<noun>/{verb}.py backends without changing the command shape."
    )
