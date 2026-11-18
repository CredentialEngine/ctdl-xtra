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
    WHITESPACE_RE,
    course_in_query,
)
from implementations.extract_platform import (
    COURSE_BLOCK_SELECTORS,
    COURSE_CODE_PARTS,
)
from implementations.extract_run import (
    CtdlClass,
    Occurrence,
    Page,
    class_text,
    css_path,
    inside_chrome,
    printed_text,
)

# A block has to print a course code this close to its start. A course's
# block opens with its heading; a description panel that happens to be
# called "course-description" doesn't, and taking it as the course would
# leave the heading outside it.
CODE_NEAR_START = 160

# A section letter joined to the number by a hyphen is part of the code:
# "NUR 741-A" is a course of its own, apart from "NUR 741A" and "NUR 741".
CODE_SECTION_RE = re.compile(r"-[A-Z]{1,2}\b")

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
            if COURSE_BLOCK_CLASS_RE.search(class_text(tag))
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


def code_identifier(code: str) -> str:
    """The code without its whitespace: "ABA 610" is ABA610.

    Only whitespace goes. A hyphen or a letter can be what tells two
    courses apart: NUR 741-A and NUR 741A are different courses.
    """
    return WHITESPACE_RE.sub("", code)


def address_identifier(occurrence: Occurrence, page: Page) -> str | None:
    """What the page's address calls the course, on a one-course page:
    /portal/training?cmd=catalog&course=109497 is 109497.

    A block on a page of many courses shares the page's address, so the
    address names none of them.
    """
    if not occurrence.is_whole_page:
        return None
    return course_in_query(page.url)


def course_identifier(occurrence: Occurrence, page: Page) -> str | None:
    """The code the course prints, without its whitespace; else, on a
    one-course page that prints none, what its address calls it. None
    when the course can't be known by either."""
    code = course_code(occurrence, page)
    if code is not None:
        return code_identifier(code)
    return address_identifier(occurrence, page)


def course_resource_id(
    occurrence: Occurrence, page: Page, catalog_id: str
) -> str | None:
    """`{catalog_id}_{identifier}`: catalog-example-edu_ABA610,
    catalog-example-edu_NUR741-A, catalog-example-edu_109497. None when
    the course can't be known by a code or its address.
    """
    identifier = course_identifier(occurrence, page)
    if identifier is None:
        return None
    return f"{catalog_id}_{identifier}"


COURSE = CtdlClass(
    term="ceterms:Course",
    page_label=LABEL_COURSE,
    occurrences=course_occurrences,
    resource_id=course_resource_id,
)
