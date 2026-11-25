"""ceterms:identifier, read from a ceterms:Course: what the course is known
by.

https://credreg.net/ctdl/terms/identifier, "Alphanumeric token that
identifies an entity and conforms to a specific identification scheme."

The code the course prints, with its whitespace removed: "ABA 610" is
ABA610, "AJ 101:" is AJ101, "NUR 741-A" is NUR741-A. Only whitespace goes;
a hyphen or a letter can be what tells two courses apart.

A one-course page that prints no code may be named by its address instead:
a training portal's /portal/training?cmd=catalog&course=109497 is 109497.

It is the identifier the course's resource id is made from, found the same
way (`course_identifier`), so the two always agree.
"""

from __future__ import annotations

from implementations.extract_course import (
    address_identifier,
    code_identifier,
    course_code,
)
from implementations.extract_run import (
    REASON_NO_CANDIDATE,
    Occurrence,
    Page,
    Reading,
)

PROPERTY = "ceterms:identifier"
# The classes it is read from, each a CTDL class the command knows.
CLASS = ("ceterms:Course",)

STRATEGY_COURSE_CODE = "course_code"
STRATEGY_PAGE_ADDRESS = "page_address"


def read(occurrence: Occurrence, page: Page) -> Reading:
    """The course's identifier, read from inside one occurrence: its code,
    else its page's address."""
    code = course_code(occurrence, page)
    if code is not None:
        return Reading(
            value=code_identifier(code),
            raw_text=code,
            strategy=STRATEGY_COURSE_CODE,
            css_path=occurrence.css_path,
        )
    named = address_identifier(occurrence, page)
    if named is not None:
        return Reading(
            value=named,
            raw_text=page.url,
            strategy=STRATEGY_PAGE_ADDRESS,
            css_path=occurrence.css_path,
        )
    return Reading(
        value=None,
        raw_text=None,
        strategy="",
        css_path=occurrence.css_path,
        reason=REASON_NO_CANDIDATE,
    )
