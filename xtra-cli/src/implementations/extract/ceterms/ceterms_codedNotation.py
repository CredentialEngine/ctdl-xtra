"""ceterms:codedNotation, read from a ceterms:Course: the code the course
is printed with.

https://credreg.net/ctdl/terms/codedNotation, "Set of alpha-numeric symbols
as defined by the body responsible for this resource that uniquely
identifies this resource and supports its discovery and use."

The code as the catalog prints it, its whitespace collapsed to one space:
"ABA 610", "AJ 101:" is AJ 101, "NUR&nbsp;741-A" is NUR 741-A, and a
subject and number printed apart, "F SC" and "33A", are F SC 33A. A hyphen
or a letter stays; it can be what tells two courses apart.

It is found the way the identifier is (`course_code`), so the two always
agree: ceterms:identifier is this code without its spaces. A course whose
page address is its only name has no code printed, so it has no coded
notation.
"""

from __future__ import annotations

from implementations.discover_rules import collapse
from implementations.extract_course import course_code
from implementations.extract_run import (
    REASON_NO_CANDIDATE,
    Occurrence,
    Page,
    Reading,
)

PROPERTY = "ceterms:codedNotation"
# The classes it is read from, each a CTDL class the command knows.
CLASS = ("ceterms:Course",)

STRATEGY_COURSE_CODE = "course_code"


def read(occurrence: Occurrence, page: Page) -> Reading:
    """The course's code, read from inside one occurrence."""
    code = course_code(occurrence, page)
    if code is None:
        return Reading(
            value=None,
            raw_text=None,
            strategy="",
            css_path=occurrence.css_path,
            reason=REASON_NO_CANDIDATE,
        )
    return Reading(
        value=collapse(code),
        raw_text=code,
        strategy=STRATEGY_COURSE_CODE,
        css_path=occurrence.css_path,
    )
