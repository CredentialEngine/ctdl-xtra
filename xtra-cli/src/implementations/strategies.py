"""Strategy names for crawl / extract / transform.

"""

from __future__ import annotations

CRAWL_STRATEGIES = ("playwright", "ai-agent", "third-party")
EXTRACT_STRATEGIES = ("template", "ai-agent")
TRANSFORM_STRATEGIES = ("ctdl", "ai-agent")
DOWNLOAD_STRATEGIES = ("playwright", "ai-agent", "third-party")


def unimplemented_message(verb: str, strategy: str, *, implemented: str) -> str:
    return (
        f"{verb} --with-{strategy} is not implemented yet. "
        f"Use --with-{implemented}. Additional strategies can be added as "
        f"src/xtra/<noun>/{verb}.py backends without changing the command shape."
    )
