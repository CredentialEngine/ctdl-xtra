"""ceterms:name, read from a ceterms:Course: the course's title, as printed.

https://credreg.net/ctdl/terms/name, "Name or title of the resource."

The title the page prints, casing and abbreviations kept, without the
ceterms:codedNotation, without the credits.

The title is looked for in this order, first one accepted wins:

1. `profile_title`: the title element the platform's markup names.
2. `title_class`: an element whose class says it is a course title.
3. `heading_beside_code`: a heading next to one that is only a code.
4. `first_heading`: the first heading in the course.
5. `code_line`: in a course block, the first short element that opens
   with the course code ("SOC 200 Understanding Society (CT)").
6. `page_name`: discovery's h1 or <title>, on a one-course page only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import Tag

from implementations.discover_page import title_name
from implementations.discover_rules import (
    COURSE_BLOCK_TITLE_CLASS_RE,
    COURSE_CODE_RE,
    PLATFORM_ACALOG,
    PLATFORM_COURSELEAF,
    PLATFORM_CURRIQUNET,
    PLATFORM_ELUMEN,
    collapse,
)
from implementations.extract_course import code_at_start
from implementations.extract_run import (
    Occurrence,
    Page,
    Reading,
    css_path,
    inside_chrome,
    printed_text,
)

PROPERTY = "ceterms:name"
# The classes it is read from, each a CTDL class the command knows. As we add more classes, we'll need to update the classes here.
#  We probably want to extract this property to a config file, so that we can add more classes without changing the code.
CLASS = ("ceterms:Course",)

STRATEGY_PROFILE_TITLE = "profile_title"
STRATEGY_TITLE_CLASS = "title_class"
STRATEGY_HEADING_BESIDE_CODE = "heading_beside_code"
STRATEGY_FIRST_HEADING = "first_heading"
STRATEGY_CODE_LINE = "code_line"
STRATEGY_PAGE_NAME = "page_name"

REASON_NO_CANDIDATE = "no_candidate"
REASON_EMPTY_TITLE = "empty_title"
REASON_CODE_ONLY = "code_only"
REASON_TOO_LONG = "rejected:too_long"
REASON_SITE_NAME = "rejected:site_name"

# Longer than this is a sentence or a description, not a course's title.
MAX_NAME_LENGTH = 150


@dataclass(frozen=True)
class TitleSelector:
    """Where a platform prints the title, and whether the code is with it."""

    selector: str
    combined: bool


# The title element each platform's own markup names. Vendor markup only,
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

HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")

# Where a block prints its opening line when no class or heading says so.
LINE_TAGS = ("strong", "b", "span", "p", "div", "dt", "td", "a")
FIRST_HEADINGS = ("h1", "h2", "h3", "h4")

# Text only a screen reader gets: an eLumen catalog prints its year as an h1
# no one sees, above the course's real title.
HIDDEN_CLASS_RE = re.compile(
    r"sr-only|visually-?hidden|screen-?reader", re.IGNORECASE
)

# What separates the code from the title: "LAW 604. Natural", "AJ 101:",
# "COMM 79073 - Intro", or just a space.
LEADING_DELIMITER_RE = re.compile(r"^\s*[.:\-–—]?\s*")

# A former number printed before the title: "(was ACOM 7390)".
FORMER_NUMBER_RE = re.compile(r"^\((?:was|formerly)\b[^)]*\)\s*", re.IGNORECASE)

# The credits a heading repeats after the title: "3 Hours.", "1-6 Hours.",
# "1,2 Hour.", "4 units", or a bare "(3.0)". A bare number outside
# parentheses is never taken, so "Calculus 2" keeps its 2, and "Hr" is
# not a unit, so "Orientation to Pharmacy 1-2 Hr." keeps its own text.
_NUMBER = r"\d+(?:\.\d+)?(?:\s*[-–,]\s*\d+(?:\.\d+)?)*"
_UNIT = r"(?:(?:credit|semester|quarter)\s+)?(?:credits?|units?|hours?)"
TRAILING_CREDITS_RE = re.compile(
    rf"(?:(?<=[\s.,])|^)"
    rf"(?:\(\s*{_NUMBER}(?:\s*{_UNIT})?\s*\)|{_NUMBER}\s*{_UNIT})"
    r"\s*\.?\s*$",
    re.IGNORECASE,
)

_EDGE_PUNCTUATION = " .,:-–—"


@dataclass(frozen=True)
class _Candidate:
    text: str
    combined: bool
    strategy: str
    css_path: str
    # True when the element found is the course's own title element, so
    # an empty title there means the course has none, not "look further".
    is_title_element: bool = False


def split_name(text: str, *, combined: bool) -> str:
    """The title in a heading, without its code, credits or former number.

    `combined` says the text may also hold the code and the credits, as
    "LAW 604.  Natural Resources.  3 Hours." does. A title-only element is
    only collapsed. Casing is never changed.
    """
    name = collapse(text)
    if not combined:
        return name
    code = code_at_start(name)
    if code is not None:
        name = LEADING_DELIMITER_RE.sub("", name[len(code) :], count=1)
    name = FORMER_NUMBER_RE.sub("", name, count=1)
    credits = TRAILING_CREDITS_RE.search(name)
    if credits is not None:
        name = name[: credits.start()]
    return name.strip(_EDGE_PUNCTUATION)


def is_code_only(text: str) -> bool:
    """True for "AJ 101:" or "PSYC 1B", a code and nothing else."""
    bare = collapse(text).strip(_EDGE_PUNCTUATION)
    return bool(bare) and code_at_start(bare) == bare


def read(occurrence: Occurrence, page: Page) -> Reading:
    """The course's name, read from inside one occurrence."""
    rejected = ""
    for find in (
        _profile_title,
        _title_class,
        _heading_beside_code,
        _first_heading,
        _code_line,
        _page_name,
    ):
        candidate = find(occurrence, page)
        if candidate is None:
            continue
        value = split_name(candidate.text, combined=candidate.combined)
        if not value:
            if candidate.is_title_element:
                reason = (
                    REASON_CODE_ONLY
                    if is_code_only(candidate.text)
                    else REASON_EMPTY_TITLE
                )
                return _missing(candidate, reason)
            continue
        reason = _rejection(value, page)
        if reason:
            rejected = reason
            continue
        return Reading(
            value=value,
            raw_text=candidate.text,
            strategy=candidate.strategy,
            css_path=candidate.css_path,
        )
    return Reading(
        value=None,
        raw_text=None,
        strategy="",
        css_path=occurrence.css_path,
        reason=rejected or REASON_NO_CANDIDATE,
    )


def _missing(candidate: _Candidate, reason: str) -> Reading:
    return Reading(
        value=None,
        raw_text=candidate.text,
        strategy=candidate.strategy,
        css_path=candidate.css_path,
        reason=reason,
    )


def _rejection(value: str, page: Page) -> str:
    if len(value) > MAX_NAME_LENGTH:
        return REASON_TOO_LONG
    site = page.site_name
    if site and value.casefold() == site.casefold():
        return REASON_SITE_NAME
    return ""


def _shown(tag: Tag) -> bool:
    """Neither site furniture nor text only a screen reader gets."""
    if inside_chrome(tag):
        return False
    return not any(
        HIDDEN_CLASS_RE.search(" ".join(node.get("class") or []))
        for node in (tag, *tag.parents)
        if isinstance(node, Tag)
    )


def _candidate(
    tag: Tag, strategy: str, *, combined: bool, is_title_element: bool
) -> _Candidate:
    return _Candidate(
        text=printed_text(tag),
        combined=combined,
        strategy=strategy,
        css_path=css_path(tag),
        is_title_element=is_title_element,
    )


def _profile_title(occurrence: Occurrence, page: Page) -> _Candidate | None:
    """The first title element the platform names that holds a title.

    An element holding only the code gives way to the next selector,
    where the detail theme prints the title. When every one holds only
    the code, the first is the answer, and the course has no title.
    """
    code_only: _Candidate | None = None
    for title in TITLE_SELECTORS.get(page.platform, ()):
        for tag in occurrence.element.select(title.selector):
            if not _shown(tag):
                continue
            candidate = _candidate(
                tag,
                STRATEGY_PROFILE_TITLE,
                combined=title.combined,
                is_title_element=True,
            )
            if not is_code_only(candidate.text):
                return candidate
            code_only = code_only or candidate
            break
    return code_only


def _title_class(occurrence: Occurrence, page: Page) -> _Candidate | None:
    """The innermost element whose class names a course title.

    CurriQunet nests `span.course-title` inside `b.course-title-units-row`;
    the inner one is the title alone.
    """
    matched = [
        tag
        for tag in occurrence.element.find_all(True)
        if COURSE_BLOCK_TITLE_CLASS_RE.search(" ".join(tag.get("class") or []))
        and _shown(tag)
    ]
    ids = {id(tag) for tag in matched}
    for tag in matched:
        if any(id(inner) in ids for inner in tag.find_all(True)):
            continue
        if printed_text(tag):
            return _candidate(
                tag,
                STRATEGY_TITLE_CLASS,
                combined=True,
                is_title_element=True,
            )
    return None


def _heading_beside_code(
    occurrence: Occurrence, page: Page
) -> _Candidate | None:
    """eLumen's shape: <h2>title</h2><h3>AJ 101:</h3>, side by side."""
    for heading in occurrence.element.find_all(HEADINGS):
        if not _shown(heading) or not is_code_only(printed_text(heading)):
            continue
        parent = heading.parent
        if not isinstance(parent, Tag):
            continue
        for sibling in parent.find_all(HEADINGS, recursive=False):
            text = printed_text(sibling)
            if sibling is heading or not text or is_code_only(text):
                continue
            return _candidate(
                sibling,
                STRATEGY_HEADING_BESIDE_CODE,
                combined=False,
                is_title_element=False,
            )
    return None


def _first_heading(occurrence: Occurrence, page: Page) -> _Candidate | None:
    for heading in occurrence.element.find_all(FIRST_HEADINGS):
        text = printed_text(heading)
        if not text or is_code_only(text) or not _shown(heading):
            continue
        return _candidate(
            heading,
            STRATEGY_FIRST_HEADING,
            combined=True,
            is_title_element=False,
        )
    return None


def _code_line(occurrence: Occurrence, page: Page) -> _Candidate | None:
    """The first short element in a block that opens with a course code.

    One CourseLeaf theme prints "SOC 200 Understanding Society
    (CT)" in a span no class calls a title. The outermost element opening
    with the code also holds the description, so it is too long and the
    one inside it is taken. Never on a whole page: there the first code
    is as likely a prerequisite as the course itself.
    """
    if occurrence.is_whole_page:
        return None
    line = _opening_line(occurrence.element.find_all(LINE_TAGS))
    if line is None:
        return None
    # Narrow to the innermost element still opening with the code: the
    # line's container also holds the credits in a sibling span, and the
    # two print with no space between them in the text.
    while (inner := _opening_line(line.find_all(LINE_TAGS))) is not None:
        line = inner
    return _candidate(
        line, STRATEGY_CODE_LINE, combined=True, is_title_element=False
    )


def _opening_line(tags: list[Tag]) -> Tag | None:
    for tag in tags:
        text = printed_text(tag)
        if len(text) > MAX_NAME_LENGTH or COURSE_CODE_RE.match(text) is None:
            continue
        if is_code_only(text) or not _shown(tag):
            continue
        return tag
    return None


def _page_name(occurrence: Occurrence, page: Page) -> _Candidate | None:
    """What discovery says the page calls itself, on a one-course page."""
    if not occurrence.is_whole_page:
        return None
    h1 = page.profile.get("h1") or ""
    text = h1 or title_name(page.profile.get("title") or "")
    if not text:
        return None
    return _Candidate(
        text=text,
        combined=True,
        strategy=STRATEGY_PAGE_NAME,
        css_path="h1" if h1 else "title",
    )
