"""`ceterms:Course`, the class: which pages hold courses, and where each is.

https://credreg.net/ctdl/terms/Course. A page prints one course or many.
Each course is an occurrence, and every property whose class is
`ceterms:Course` is read from inside its occurrence, so a value can't leak
from the course next to it or from the site around the page.
"""

from __future__ import annotations

import re

from bs4 import Tag

from implementations.discover_dom import find_main
from implementations.discover_rules import (
    COURSE_BLOCK_CLASS_RE,
    COURSE_CODE_RE,
    LABEL_COURSE,
    PLATFORM_COURSELEAF,
    PLATFORM_CURRIQUNET,
)
from implementations.extract_run import (
    Occurrence,
    Page,
    RdfClass,
    css_path,
    inside_chrome,
    printed_text,
)

# The element each platform writes around one course, where the class
# words alone don't say it. Vendor markup only, seen on more than one
# catalog of the platform; never a catalog's own theme.
COURSE_BLOCK_SELECTORS: dict[str, str] = {
    PLATFORM_COURSELEAF: "div.courseblock",
    PLATFORM_CURRIQUNET: ".course-summary-wrapper",
}

# A block has to print a course code this close to its start. A course's
# block opens with its heading; a description panel that happens to be
# called "course-description" doesn't, and taking it as the course would
# leave the heading outside it.
CODE_NEAR_START = 160

# A section letter joined to the number by a hyphen is part of the code:
# "NUR 741-A" is a course of its own, apart from "NUR 741A" and "NUR 741".
CODE_SECTION_RE = re.compile(r"-[A-Z]{1,2}\b")

WHITESPACE_RE = re.compile(r"\s+")

# Where a platform prints a course's code as a subject and a number of
# their own: CurriQunet's "ENGL" "-" "6". Vendor markup only. The parts
# are read as printed, because a code like "ENGL 6" is one the code
# pattern refuses on its own.
COURSE_CODE_PARTS: dict[str, tuple[str, str]] = {
    PLATFORM_CURRIQUNET: (".course-subject", ".course-number"),
}

# Where a one-course page prints its code: a heading opening with it
# ("COMM 79073 - Intro…", eLumen's "AJ 101:"). A paragraph's first code
# is as likely a prerequisite.
PAGE_CODE_TAGS = ("h1", "h2", "h3")

# Where a course block prints its opening line.
BLOCK_CODE_TAGS = ("h1", "h2", "h3", "h4", "strong", "b", "span", "p", "div")


def course_occurrences(page: Page) -> list[Occurrence]:
    """One occurrence per course block, or the page's content as one.

    The content is the page's main element, else its body. Blocks are
    found by the platform's own block markup, else by the class words
    discovery already reads (`courseblock`, `acalog-course`, ...).
    """
    soup = page.soup
    root = find_main(soup) or soup.body or soup
    blocks = _blocks(root, page.platform)
    if not blocks:
        return [
            Occurrence(
                element=root,
                css_path=css_path(root),
                is_whole_page=True,
            )
        ]
    return [
        Occurrence(
            element=block,
            css_path=css_path(block),
            is_whole_page=False,
        )
        for block in blocks
    ]


def _blocks(root: Tag, platform: str) -> list[Tag]:
    """The page's course blocks, never one inside another.

    A platform's own block markup is taken as it is. A block found only by
    its class words has to open with a code, because the same words name
    description panels too; the platform's markup needs no such check, and
    must not get one: CurriQunet prints codes like "PARA 51" that the code
    pattern refuses, so as not to read "GOAL 1" as a course.
    """
    selector = COURSE_BLOCK_SELECTORS.get(platform)
    if selector:
        candidates = root.select(selector)
    else:
        candidates = [
            tag
            for tag in root.find_all(True)
            if COURSE_BLOCK_CLASS_RE.search(" ".join(tag.get("class") or []))
            and _opens_with_code(tag)
        ]
    outermost: list[Tag] = []
    taken: set[int] = set()
    for tag in candidates:
        if any(id(parent) in taken for parent in tag.parents):
            continue
        if inside_chrome(tag):
            continue
        outermost.append(tag)
        taken.add(id(tag))
    return outermost


def _opens_with_code(tag: Tag) -> bool:
    return (
        COURSE_CODE_RE.search(printed_text(tag)[:CODE_NEAR_START]) is not None
    )


def code_at_start(text: str) -> str | None:
    """The course code the text opens with, as printed, or None.

    "NUR 741-A Health Care Practicum" opens with "NUR 741-A".
    """
    match = COURSE_CODE_RE.match(text)
    if match is None:
        return None
    section = CODE_SECTION_RE.match(text, match.end())
    return text[: (section or match).end()]


def course_code(occurrence: Occurrence, page: Page) -> str | None:
    """The course's code as printed ("ABA 610"), or None.

    The platform's own code markup first. Otherwise the first element
    that opens with a code: in a block, its opening line; on a one-course
    page, a heading.
    """
    parts = COURSE_CODE_PARTS.get(page.platform, ())
    texts = [
        printed_text(tag)
        for tag in (occurrence.element.select_one(p) for p in parts)
        if tag is not None
    ]
    if parts and len(texts) == len(parts) and all(texts):
        return " ".join(texts)
    tags = PAGE_CODE_TAGS if occurrence.is_whole_page else BLOCK_CODE_TAGS
    for tag in occurrence.element.find_all(tags):
        if inside_chrome(tag):
            continue
        code = code_at_start(printed_text(tag))
        if code is not None:
            return code
    return None


def course_resource_id(
    occurrence: Occurrence, page: Page, catalog_id: str
) -> str | None:
    """`{catalog_id}_{code}`, the code without its spaces:
    catalog-example-edu_ABA610, catalog-example-edu_NUR741-A.

    Only whitespace goes. A hyphen or a letter can be what tells two
    courses apart: NUR 741-A and NUR 741A are different courses. None when
    the course prints no code it can be known by.
    """
    code = course_code(occurrence, page)
    if code is None:
        return None
    return f"{catalog_id}_{WHITESPACE_RE.sub('', code)}"


COURSE = RdfClass(
    rdf_type="ceterms:Course",
    page_label=LABEL_COURSE,
    occurrences=course_occurrences,
    resource_id=course_resource_id,
)
