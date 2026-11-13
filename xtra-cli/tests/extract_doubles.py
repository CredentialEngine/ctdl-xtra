"""Pages for the one-property extraction tests, cut from real catalogs.

Each fixture under fixtures/html/extract/course/ is a saved
crawl page trimmed to its head, the site's heading and a few courses. Its
first line names the page it came from.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from implementations.discover_dom import parse, read_fingerprint
from implementations.extract_run import Page

COURSE_FIXTURES = (
    Path(__file__).resolve().parent / "fixtures" / "html" / "extract" / "course"
)

_SOURCE_RE = re.compile(r"<!-- Trimmed from (\S+)")


def fixture_html(name: str) -> str:
    return (COURSE_FIXTURES / f"{name}.html").read_text(encoding="utf-8")


def fixture_url(name: str) -> str:
    """The address the trimmed page was saved from."""
    match = _SOURCE_RE.match(fixture_html(name))
    assert match is not None, f"{name} names no source page"
    return match.group(1)


def fixture_page(
    name: str,
    *,
    platform: str | None = None,
    profile: dict[str, Any] | None = None,
) -> Page:
    """The fixture as a Page. The platform is its own fingerprint unless
    given, so `platform=""` reads it as an unknown site."""
    html = fixture_html(name)
    return Page(
        stem=name,
        url=fixture_url(name),
        soup=parse(html),
        platform=(
            read_fingerprint(parse(html)).platform
            if platform is None
            else platform
        ),
        profile=profile or {},
    )
