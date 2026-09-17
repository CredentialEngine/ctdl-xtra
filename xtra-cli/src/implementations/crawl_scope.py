"""Which URLs a crawl may keep, and how links come out of a rendered page.

The crawler downloads and saves. It does not know what a course page is,
which CMS produced it, or which of two catalog years it belongs to. When a
host keeps several years side by side, the operator narrows the run with
--include-regex rather than the crawler guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit

# Extensions a browser would download rather than render.
SKIP_EXTENSIONS = frozenset(
    {
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "zip",
        "jpg", "jpeg", "png", "gif", "svg", "webp", "ico",
        "css", "js", "xml", "mp3", "mp4",
    }
)

HTML_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})

REASON_SCHEME = "scheme"
REASON_OUT_OF_SCOPE = "out_of_scope"
REASON_EXTENSION = "extension"
REASON_INCLUDE_RULE = "include_rule"
REASON_EXCLUDE_RULE = "exclude_rule"
REASON_ROBOTS = "robots"
REASON_DUPLICATE = "duplicate"
REASON_NON_HTML = "non_html"
REASON_REDIRECT_OUT_OF_SCOPE = "redirect_out_of_scope"

# Scope decisions are the bulk of a crawl and would bury the GET lines, so
# they log at DEBUG. Surprises (robots, non-HTML, a redirect off the site)
# stay at INFO because an operator needs to see them without re-running.
QUIET_REASONS = frozenset(
    {
        REASON_OUT_OF_SCOPE,
        REASON_DUPLICATE,
        REASON_EXTENSION,
        REASON_INCLUDE_RULE,
        REASON_EXCLUDE_RULE,
        REASON_SCHEME,
    }
)


def directory_of(path: str) -> str:
    """Directory part of a URL path, always ending in a slash.

    /courses/index.html -> /courses/ , /courses -> / , "" -> /
    """
    if not path:
        return "/"
    if path.endswith("/"):
        return path
    head, _, _ = path.rpartition("/")
    return f"{head}/" if head else "/"


def extension_of(path: str) -> str:
    segment = path.rsplit("/", 1)[-1]
    if "." not in segment:
        return ""
    return segment.rsplit(".", 1)[-1].lower()


def first_path_segment(url: str) -> str:
    """Top folder of a URL path, for the coverage count in crawl.json."""
    path = urlsplit(url).path or "/"
    parts = [part for part in path.split("/") if part]
    return parts[0] if parts else "(root)"


def content_type_is_html(content_type: str) -> bool:
    return content_type.split(";", 1)[0].strip().lower() in HTML_CONTENT_TYPES


@dataclass(frozen=True)
class Scope:
    """Host, path prefix, operator regexes, and robots.txt, as one test."""

    host: str
    path_prefix: str
    include: tuple[re.Pattern[str], ...] = ()
    exclude: tuple[re.Pattern[str], ...] = ()
    robots: object | None = None

    @classmethod
    def from_seed(
        cls,
        seed_url: str,
        *,
        scope_prefix: str | None = None,
        include_regex: tuple[str, ...] = (),
        exclude_regex: tuple[str, ...] = (),
        robots: object | None = None,
    ) -> Scope:
        """Build the scope. The host always comes from --url.

        Without --scope-prefix the prefix is the directory of --url, so
        https://catalog.example.edu/courses/index.html crawls
        https://catalog.example.edu/courses/ and nothing above it.
        """
        seed = urlsplit(seed_url)
        if scope_prefix:
            prefix = urlsplit(scope_prefix).path or "/"
        else:
            prefix = directory_of(seed.path)
        return cls(
            host=(seed.hostname or "").lower(),
            path_prefix=prefix,
            include=tuple(re.compile(pattern) for pattern in include_regex),
            exclude=tuple(re.compile(pattern) for pattern in exclude_regex),
            robots=robots,
        )

    def with_robots(self, robots: object | None) -> Scope:
        return Scope(
            host=self.host,
            path_prefix=self.path_prefix,
            include=self.include,
            exclude=self.exclude,
            robots=robots,
        )

    def rejection(self, url: str) -> str | None:
        """Why this URL is out of the crawl, or None when it is in."""
        parsed = urlsplit(url)
        if (parsed.scheme or "").lower() not in {"http", "https"}:
            return REASON_SCHEME
        if (parsed.hostname or "").lower() != self.host:
            return REASON_OUT_OF_SCOPE
        path = parsed.path or "/"
        if not path.startswith(self.path_prefix):
            return REASON_OUT_OF_SCOPE
        if extension_of(path) in SKIP_EXTENSIONS:
            return REASON_EXTENSION
        if self.include and not any(rule.search(url) for rule in self.include):
            return REASON_INCLUDE_RULE
        if any(rule.search(url) for rule in self.exclude):
            return REASON_EXCLUDE_RULE
        if self.robots is not None and not self.robots.can_fetch("*", url):
            return REASON_ROBOTS
        return None

    def allows(self, url: str) -> bool:
        return self.rejection(url) is None


class _LinkParser(HTMLParser):
    """href of a, area, and link rel=next, plus any base href."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.base: str | None = None
        self.hrefs: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = dict(attrs)
        if tag == "base":
            href = (values.get("href") or "").strip()
            if href and self.base is None:
                self.base = href
            return
        if tag in {"a", "area"}:
            href = (values.get("href") or "").strip()
        elif tag == "link":
            rel = (values.get("rel") or "").lower().split()
            href = (values.get("href") or "").strip() if "next" in rel else ""
        else:
            return
        if href:
            self.hrefs.append(href)


def extract_links(html: str, base_url: str) -> list[str]:
    """Absolute, fragment-free links in document order, first sighting only."""
    parser = _LinkParser()
    parser.feed(html)
    parser.close()
    base = urljoin(base_url, parser.base) if parser.base else base_url
    seen: set[str] = set()
    links: list[str] = []
    for href in parser.hrefs:
        absolute = urldefrag(urljoin(base, href)).url
        if absolute and absolute not in seen:
            seen.add(absolute)
            links.append(absolute)
    return links
