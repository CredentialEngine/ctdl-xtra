"""Display copies and the one fixed text that positions are counted against (section 8.3).

The display copy is the stored page with scripts removed. Its text is every text node under
<body>, in reading order, joined with nothing between. The viewer loads the same display copy in
a browser and counts the same way, so positions written here and highlights drawn there cannot
disagree.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Comment, Doctype, NavigableString, Tag

_REMOVED_ELEMENTS = ("script", "noscript", "template", "iframe", "object", "embed", "frame", "base")
_KEPT_LINK_RELS = {"stylesheet"}


def make_display_copy(raw_html: str, base_address: str) -> str:
    """The stored page, minus scripts, pointing its stylesheets and images at the live site."""
    soup = BeautifulSoup(raw_html, "html5lib")
    for el in soup.find_all(_REMOVED_ELEMENTS):
        el.decompose()
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    for style in (soup.body.find_all("style") if soup.body else []):
        style.decompose()
    for link in soup.find_all("link"):
        rels = {r.lower() for r in (link.get("rel") or [])}
        if not rels & _KEPT_LINK_RELS:
            link.decompose()
    for el in soup.find_all(True):
        for name in list(el.attrs):
            value = el.attrs[name]
            if name.lower().startswith("on"):
                del el.attrs[name]
            elif name.lower() in ("href", "src", "action") and isinstance(value, str):
                if value.strip().lower().startswith("javascript:"):
                    del el.attrs[name]
    if soup.head is not None:
        # Relative addresses (stylesheets, images, links) resolve against the live site (D13).
        base = soup.new_tag("base", href=base_address, target="_blank")
        soup.head.insert(0, base)
    for item in list(soup.contents):
        if isinstance(item, Doctype):
            item.extract()
    return "<!doctype html>\n" + soup.decode(formatter="minimal")


@dataclass
class DisplayDocument:
    """A parsed display copy: its text, and where every element sits in that text."""

    html: str
    soup: BeautifulSoup
    text: str
    _spans: dict[int, tuple[int, int]]

    @property
    def text_sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def span(self, element: Tag) -> tuple[int, int]:
        """Start and end of an element's text within the document text."""
        return self._spans[id(element)]

    def element_text(self, element: Tag) -> str:
        start, end = self.span(element)
        return self.text[start:end]


def load_display_copy(display_html: str) -> DisplayDocument:
    # Parse the display copy itself, not the stored page, so that this reading and the
    # browser's reading start from the same characters.
    soup = BeautifulSoup(display_html, "html5lib")
    spans: dict[int, tuple[int, int]] = {}
    parts: list[str] = []
    position = 0

    def walk(node: Tag) -> None:
        nonlocal position
        start = position
        for child in node.children:
            if isinstance(child, Tag):
                walk(child)
            elif isinstance(child, NavigableString) and not isinstance(child, (Comment, Doctype)):
                parts.append(str(child))
                position += len(child)
        spans[id(node)] = (start, position)

    if soup.body is not None:
        walk(soup.body)
    return DisplayDocument(display_html, soup, "".join(parts), spans)


def normalise_text(text: str) -> str:
    """How a quote becomes a record value: non-breaking spaces become spaces, runs of white
    space become one space, and the ends are trimmed. The quote itself is stored untouched."""
    return re.sub(r"\s+", " ", text.replace(" ", " ")).strip()


def was_normalised(quote: str) -> bool:
    return normalise_text(quote) != quote


def context(text: str, start: int, end: int, width: int = 32) -> tuple[str, str]:
    """A little text before and after a segment, kept with the quote so it can be re-found."""
    return text[max(0, start - width) : start], text[end : end + width]
