"""The pages of a Coursedog course or program list, read off its buttons.

A Coursedog catalog shows its courses and its programs twenty at a time.
The list arrives by XHR after the load event, and the way to the next
twenty is a row of <button>s, not links, so following links reaches the
first twenty of each list and nothing after them. Brookdale's crawl of
2026-09-23 saved no course and no program page at all, and Commonwealth's
of 2026-10-21, made after the readiness wait, queued 20 of 2,733 courses.

The site keeps the page number in the address, though: it rewrites
/courses to /courses?page=1&cq= once the list is up, and /courses?page=2
opens the second page. So the buttons stand for addresses the site
answers, the way an <a rel=next> would, and they are read that way: the
page on screen, and the last page the row offers. Nothing is clicked and
nothing is fetched here.

What a page number in the address does is still the site's business, so
it is checked before it is trusted:

- the first page of a list queues its second page and nothing else;
- a page asked for page N that shows page N queues every page after it,
  up to the last, all at once, so one page that loads badly cannot end
  the list there;
- a page asked for page N that shows another page means the list ignores
  the address. Nothing more is queued from it, so a list that cannot be
  paged that way costs one page, not hundreds.

Addresses are built from the URL the page was asked for, never from the
one the site rewrote it to, because a resume reads a saved page back
under the URL it was asked for and has to build the same addresses. An
empty parameter is dropped, so /courses and the /courses?page=1&cq= that
a catalog's own pages link to lead to one page 2, not two copies of the
whole list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit

PAGE_PARAMETER = "page"

# Every Coursedog page names its platform, in its asset URLs and footer.
PLATFORM_RE = re.compile("coursedog", re.IGNORECASE)

# The row of page buttons. A print stylesheet on every page names the
# class too, so only an element's class attribute counts.
BAR_CLASS = "base-pagination"
BAR_ATTRIBUTE_RE = re.compile(
    r"""class=["']?[^"'>]*\b""" + re.escape(BAR_CLASS) + r"\b"
)

# The button of the page on screen. It is also disabled, which is what is
# left to go on when a theme drops the colour.
CURRENT_CLASS = "btn-primary"

# What the server renders where a list will go, before its XHR lands.
LOADING_RE = re.compile(r">\s*Loading results(?:\.\.\.|…)\s*<")

# The longest list seen has 195 pages. The cap is there so a misread number
# cannot queue an endless run; reaching it is reported, never silent.
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
    """What one saved page says about the rest of its list.

    `asked` is the page its URL asked for, `current` the page its buttons
    say is on screen, `last` the highest page they offer, and `urls` the
    pages to queue. `problem` says why the list cannot be followed further
    from this page, or that it was cut at MAX_LIST_PAGES.
    """

    asked: int | None
    current: int | None = None
    last: int | None = None
    urls: tuple[str, ...] = ()
    problem: str | None = None


def _is_number(text: str) -> bool:
    # str.isdigit alone also accepts digits int() refuses, such as "²".
    return text.isascii() and text.isdigit()


class _BarParser(HTMLParser):
    """The numbered buttons inside each element whose class is the bar's.

    Nesting is counted on the bar's own tag only, so a void element inside
    it, which never closes, cannot throw the count off.
    """

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
    """The one page the row marks as on screen, or None.

    The highlighted button decides. With none highlighted, the disabled
    numbered button does; the gap is disabled too, but carries no number.
    Two pages marked the same way is no answer.
    """
    for marked in (
        {number for number, highlighted, _ in buttons if highlighted},
        {number for number, _, disabled in buttons if disabled},
    ):
        if marked:
            return marked.pop() if len(marked) == 1 else None
    return None


def read_bar(html: str) -> Bar | None:
    """The one row of page buttons on a page, or None.

    None when there is no row, when it numbers no page, and when there are
    two: which list each row pages cannot be told.
    """
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
    """The page `url` asks for: 1 when it names none.

    None when it names one that is not a number, or names two: no page
    address can be built from such a URL.
    """
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
    """`url` asking for page `number`.

    The page goes first, where the site writes it. Every other parameter
    keeps its place and its spelling, except an empty one, which says
    nothing: /courses and /courses?page=1&cq= lead to the same page 2.
    """
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
    """The pages of a Coursedog list to queue from one of its pages.

    `url` is the URL the page was asked for. None for a page that is not a
    Coursedog list, which is every page of every other catalog, and for a
    list page whose URL names no usable page number.
    """
    if not PLATFORM_RE.search(html):
        return None
    bar = read_bar(html)
    if bar is None:
        if LOADING_RE.search(html):
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
        # One page is enough to learn whether the list opens by number.
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
