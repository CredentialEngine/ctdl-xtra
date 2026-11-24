"""Each catalog platform's own markup: the one place extraction knows it.

Discovery fingerprints a page's platform (`page.platform`). Where that
platform's markup names an element, an extractor looks there first, and
falls back to what any catalog prints when there is no platform or no such
element. Vendor markup only, seen on more than one catalog of the platform;
never a catalog's own theme. Adding a platform is adding its entries here.
"""

from __future__ import annotations

from dataclasses import dataclass

from implementations.discover_rules import (
    PLATFORM_ACALOG,
    PLATFORM_COURSELEAF,
    PLATFORM_CURRIQUNET,
    PLATFORM_ELUMEN,
)

# --- ceterms:Course ----------------------------------------------------------

# The element each platform writes around one course, where the class
# words alone don't say it.
COURSE_BLOCK_SELECTORS: dict[str, str] = {
    PLATFORM_COURSELEAF: "div.courseblock",
    PLATFORM_CURRIQUNET: ".course-summary-wrapper",
}

# Where a platform prints a course's code as a subject and a number of
# their own: CurriQunet's "ENGL" "-" "6". The parts are read as printed,
# because a code like "ENGL 6" is one the code pattern refuses on its own.
COURSE_CODE_PARTS: dict[str, tuple[str, str]] = {
    PLATFORM_CURRIQUNET: (".course-subject", ".course-number"),
}

# --- ceterms:name ------------------------------------------------------------


@dataclass(frozen=True)
class TitleSelector:
    """Where a platform prints the title, and whether the code is with it."""

    selector: str
    combined: bool


# The title element each platform's own markup names, in the order to try
# them.
TITLE_SELECTORS: dict[str, tuple[TitleSelector, ...]] = {
    # "COMM 79073 - (was ACOM 7390) Introduction to Applied ..."
    PLATFORM_ACALOG: (TitleSelector("#course_preview_title", True),),
    # "LAW 604.  Natural Resources.  3 Hours." in the classic theme. The
    # detail theme prints the title in .detail-title beside a code-only
    # .detail-code, or in .detail-code after the code.
    PLATFORM_COURSELEAF: (
        TitleSelector(".courseblocktitle", True),
        TitleSelector(".detail-title", True),
        TitleSelector(".detail-code", True),
    ),
    # The code and " - " are spans of their own beside the title; the
    # credits are too ("(3.0)"), or are inside it ("(3.00 units)").
    PLATFORM_CURRIQUNET: (TitleSelector(".course-title", True),),
    # <header class="header"><h2>title</h2><h3>AJ 101:</h3></header>, or
    # <header class="header-course"><p class="header-course-name">title</p>
    # <h1>APPR B48G</h1></header>.
    PLATFORM_ELUMEN: (
        TitleSelector("header.header h2", False),
        TitleSelector(".header-course-name", False),
    ),
}

# --- ceterms:description -----------------------------------------------------

# The description element each platform's own markup names, in the order
# to try them.
DESCRIPTION_SELECTORS: dict[str, tuple[str, ...]] = {
    # <p class="courseblockdesc"> in the classic theme; the detail theme
    # prints the description as the block's first .courseblockextra, or
    # the prerequisite there when the course has no description.
    PLATFORM_COURSELEAF: (".courseblockdesc", ".courseblockextra"),
    PLATFORM_CURRIQUNET: (".course-catalog-description",),
    # <div class="introtext" style="white-space: pre-wrap">.
    PLATFORM_ELUMEN: (".introtext",),
}
