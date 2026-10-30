"""Queue the later pages of a list that pages with buttons, not links.

A list is trusted to open by its ?page=N address only once page 2 shows 2.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger(__name__)

PAGE_PARAMETER = "page"

# The row of page buttons. Only an element's class counts, not a stylesheet.
BAR_CLASS = "base-pagination"
BAR_ATTRIBUTE_RE = re.compile(
    r"""class=["']?[^"'>]*\b""" + re.escape(BAR_CLASS) + r"\b"
)

# The button of the page on screen. It is also disabled.
CURRENT_CLASS = "btn-primary"

# What the server renders where the list goes, before the list loads.
LOADING_RE = re.compile(r">\s*Loading results(?:\.\.\.|…)\s*<")

# Keeps a misread number from queueing an endless run; reaching it is logged.
MAX_LIST_PAGES = 1000

PROBLEM_LOADING = "loading"
PROBLEM_NO_CURRENT_PAGE = "no_current_page"
PROBLEM_PAGE_IGNORED = "page_ignored"
PROBLEM_CAPPED = "capped"


@dataclass(frozen=True)
class Bar:
    """What one row of page buttons says: the page on screen, the last."""

    current: int | None
    last: int


@dataclass(frozen=True)
class ListPages:
    """What one saved list page says about the rest of its list."""

    asked: int | None
    current: int | None = None
    last: int | None = None
    urls: tuple[str, ...] = ()
    problem: str | None = None


def _is_number(text: str) -> bool:
    # str.isdigit alone also accepts digits int() refuses, such as "²".
    return text.isascii() and text.isdigit()


class _BarParser(HTMLParser):
    """The numbered buttons inside each element whose class is the bar's."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        # One list per bar: (number, highlighted, disabled) per button.
        self.bars: list[list[tuple[int, bool, bool]]] = []
        self._tag: str | None = None
        self._depth = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = dict(attrs)
        if self._depth:
            # Only the bar's own tag is counted, so a void element cannot
            # throw the count off.
            if tag == self._tag:
                self._depth += 1
            elif tag == "button":
                self._button(values)
            return
        if BAR_CLASS in (values.get("class") or "").split():
            self._tag = tag
            self._depth = 1
            self.bars.append([])

    def handle_endtag(self, tag: str) -> None:
        if self._depth and tag == self._tag:
            self._depth -= 1

    def _button(self, values: dict[str, str | None]) -> None:
        number = (values.get("number") or "").strip()
        # Previous and Next carry no number, and the gap carries "...".
        if not _is_number(number):
            return
        classes = (values.get("class") or "").split()
        self.bars[-1].append(
            (int(number), CURRENT_CLASS in classes, "disabled" in values)
        )


def _current(buttons: list[tuple[int, bool, bool]]) -> int | None:
    """The one page marked as on screen: highlighted, else disabled."""
    for marked in (
        {number for number, highlighted, _ in buttons if highlighted},
        {number for number, _, disabled in buttons if disabled},
    ):
        if marked:
            return marked.pop() if len(marked) == 1 else None
    return None


def read_bar(html: str) -> Bar | None:
    """The page's one row of page buttons; None for no row or for two."""
    if not BAR_ATTRIBUTE_RE.search(html):
        return None
    parser = _BarParser()
    parser.feed(html)
    parser.close()
    bars = [buttons for buttons in parser.bars if buttons]
    if len(bars) != 1:
        return None
    buttons = bars[0]
    return Bar(
        current=_current(buttons),
        last=max(number for number, _, _ in buttons),
    )


def _parameters(url: str) -> list[tuple[str, str]]:
    """The query as written, name and value, neither one decoded."""
    pairs: list[tuple[str, str]] = []
    for piece in urlsplit(url).query.split("&"):
        if piece:
            name, _, value = piece.partition("=")
            pairs.append((name, value))
    return pairs


def asked_page(url: str) -> int | None:
    """The page `url` asks for: 1 when it names none, None when unusable."""
    values = [
        value for name, value in _parameters(url) if name == PAGE_PARAMETER
    ]
    if not values:
        return 1
    if len(values) > 1 or not _is_number(values[0]):
        return None
    return int(values[0])


def _says_something(piece: str) -> bool:
    """False for an empty parameter such as cq=, which a list reads as unset."""
    _, equals, value = piece.partition("=")
    return not equals or bool(value)


def page_url(url: str, number: int) -> str:
    """`url` asking for page `number`, with empty parameters dropped."""
    parts = urlsplit(url)
    kept = [
        piece
        for piece in parts.query.split("&")
        if piece
        and piece.partition("=")[0] != PAGE_PARAMETER
        and _says_something(piece)
    ]
    query = "&".join([f"{PAGE_PARAMETER}={number}", *kept])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def read_list_pages(html: str, url: str) -> ListPages | None:
    """The list pages to queue from one saved page asked for at `url`."""
    bar = read_bar(html)
    if bar is None:
        # A list still loading has no buttons, but its stylesheet names them.
        if BAR_CLASS in html and LOADING_RE.search(html):
            return ListPages(asked=asked_page(url), problem=PROBLEM_LOADING)
        return None
    asked = asked_page(url)
    if asked is None:
        return None
    if bar.current is None:
        return ListPages(
            asked=asked, last=bar.last, problem=PROBLEM_NO_CURRENT_PAGE
        )
    if bar.current != asked:
        return ListPages(
            asked=asked,
            current=bar.current,
            last=bar.last,
            problem=PROBLEM_PAGE_IGNORED,
        )
    if asked == 1:
        # Page 2 alone, to learn whether the list opens by page number.
        numbers = range(2, min(bar.last, 2) + 1)
        capped = False
    else:
        numbers = range(asked + 1, min(bar.last, MAX_LIST_PAGES) + 1)
        capped = bar.last > MAX_LIST_PAGES
    return ListPages(
        asked=asked,
        current=bar.current,
        last=bar.last,
        urls=tuple(page_url(url, number) for number in numbers),
        problem=PROBLEM_CAPPED if capped else None,
    )


def queue_list_pages(
    html: str, url: str, *, enqueue: Callable[[str], bool]
) -> int:
    """Queue the rest of a list through the crawler's enqueue; count new ones."""
    pages = read_list_pages(html, url)
    if pages is None:
        return 0
    queued = sum(enqueue(url) for url in pages.urls)
    if pages.problem == PROBLEM_LOADING:
        logger.warning(
            "LIST %s was saved before its list loaded (Loading "
            "results...), so the pages after it are not known",
            url,
        )
    elif pages.problem == PROBLEM_NO_CURRENT_PAGE:
        logger.warning(
            "LIST %s has page buttons up to %s but none marks the page "
            "on screen, so the rest of the list is not queued",
            url,
            pages.last,
        )
    elif pages.problem == PROBLEM_PAGE_IGNORED:
        logger.warning(
            "LIST %s asked for page %s and the site showed page %s, so "
            "this list does not open by page number and the rest of it "
            "is not queued",
            url,
            pages.asked,
            pages.current,
        )
    elif pages.problem == PROBLEM_CAPPED:
        logger.warning(
            "LIST %s says the list has %s pages; only pages up to %s are "
            "queued",
            url,
            pages.last,
            MAX_LIST_PAGES,
        )
    if not queued:
        return 0
    if pages.asked == 1:
        logger.info(
            "LIST %s is page 1 of %s; queued page 2 to check the list "
            "opens by page number",
            url,
            pages.last,
        )
    else:
        logger.info(
            "LIST %s opened as page %s of %s; queued %s more page(s) of "
            "the list",
            url,
            pages.current,
            pages.last,
            queued,
        )
    return queued
