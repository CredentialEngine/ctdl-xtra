"""Deterministic HTML → normalized text. Offsets are into this text."""

from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser

from page import SCRIPT_STYLE


class _VisibleText(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "iframe"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag in {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip and data:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw.splitlines()]
        return "\n".join(line for line in lines if line) + "\n"


def normalize_html(html: str) -> str:
    cleaned = SCRIPT_STYLE.sub("", html)
    parser = _VisibleText()
    parser.feed(cleaned)
    parser.close()
    return parser.text()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))
