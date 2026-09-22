"""URL slugs and HTML cleanup used by freeze/normalize.

Kept here so v4 capture does not import the older generator package.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

NON_SLUG = re.compile(r"[^a-zA-Z0-9]+")

SCRIPT_STYLE = re.compile(
    r"<(script|style|noscript)\b[^>]*>.*?</\1>",
    re.I | re.S,
)


def slug_url(url: str) -> str:
    keep = NON_SLUG.sub("-", url.replace("https://", "").replace("http://", ""))
    return keep.strip("-")[:120]


def pack_join(pack, rel: str):
    """Resolve a POSIX pack-relative path (from portable_path) on any OS.

    Do not use ``pack / rel`` when rel contains slashes: on Windows that can
    become one filename component, so pack check would miss the freeze.
    """
    posix = PurePosixPath((rel or "").replace("\\", "/"))
    if not posix.parts:
        return pack
    return pack.joinpath(*posix.parts)
