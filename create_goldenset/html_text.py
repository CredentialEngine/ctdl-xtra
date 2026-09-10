"""URL slugs and HTML cleanup used by freeze/normalize.

Kept here so golden_set_v4 does not import generate_goldenset.
"""

from __future__ import annotations

import re

NON_SLUG = re.compile(r"[^a-zA-Z0-9]+")

SCRIPT_STYLE = re.compile(
    r"<(script|style|noscript)\b[^>]*>.*?</\1>",
    re.I | re.S,
)


def slug_url(url: str) -> str:
    keep = NON_SLUG.sub("-", url.replace("https://", "").replace("http://", ""))
    return keep.strip("-")[:120]
