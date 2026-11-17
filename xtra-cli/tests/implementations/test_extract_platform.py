from __future__ import annotations

import pytest

from implementations.discover_rules import PLATFORM_NAMES, PLATFORM_WEAK
from implementations.extract_platform import (
    COURSE_BLOCK_SELECTORS,
    COURSE_CODE_PARTS,
    DESCRIPTION_SELECTORS,
    TITLE_SELECTORS,
)


@pytest.mark.parametrize(
    "table",
    [
        COURSE_BLOCK_SELECTORS,
        COURSE_CODE_PARTS,
        TITLE_SELECTORS,
        DESCRIPTION_SELECTORS,
    ],
    ids=["course blocks", "code parts", "titles", "descriptions"],
)
def test_markup_is_only_for_known_strong_platforms(table: dict) -> None:
    """A weak platform (a CMS any catalog may sit on) has no markup of its
    own to read."""
    for platform in table:
        assert platform in PLATFORM_NAMES
        assert platform not in PLATFORM_WEAK
