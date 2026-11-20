"""ceterms:lifeCycleStatusType, read from a ceterms:Course: where the course
is in its life cycle.

https://credreg.net/ctdl/terms/lifeCycleStatusType, "Type of state of the
resource in terms of its stage in a life cycle; select from an enumeration
of such types." The enumeration is ceterms:LifeCycleStatus, and the value
is the concept's label (Schema-Development,
Split/concepts/lifeCycle_*.jsonld):

- Active: "active, current, ongoing, offered, operational, or available."
- Ceased: "permanently no longer active, ..."
- Ceasing: "in the process of becoming no longer active, ..."
- Developing: "under development and may or may not become active, ..."
- Suspended: "temporarily not active, ..."

A catalog lists the courses it offers, so a course it lists is Active
unless the course itself says otherwise. That is the Golden Dataset
Studio's rule on every reviewed catalog, "A published current catalog lists
active courses", and every golden value is Active.

What the course says otherwise is looked for in this order, first one
found wins:

1. `status_label`: a label naming the status, "Status: Inactive".
2. `title_marker`: a status marked in the course's opening line,
   "ENGL 101 - Composition (Inactive)", "[DELETED]", "DISCONTINUED".
3. `course_statement`: a sentence about the course, "This course is no
   longer offered", "This course will be discontinued after Spring 2027".
4. `listed_in_catalog`: none of these, so Active.
"""

from __future__ import annotations

import re

from implementations.discover_rules import collapse
from implementations.extract.ceterms.ceterms_description import shown_text
from implementations.extract_course import CODE_NEAR_START
from implementations.extract_run import Occurrence, Page, Reading

PROPERTY = "ceterms:lifeCycleStatusType"
# The classes it is read from, each a CTDL class the command knows.
CLASS = ("ceterms:Course",)

ACTIVE = "Active"
CEASED = "Ceased"
CEASING = "Ceasing"
DEVELOPING = "Developing"
SUSPENDED = "Suspended"

STRATEGY_STATUS_LABEL = "status_label"
STRATEGY_TITLE_MARKER = "title_marker"
STRATEGY_COURSE_STATEMENT = "course_statement"
STRATEGY_LISTED_IN_CATALOG = "listed_in_catalog"

# What a catalog prints for each status, the first match naming it. Ceasing
# and Suspended come before Ceased, so "phasing out" and "temporarily
# inactive" are not taken for a course that is gone.
STATUS_WORDS: tuple[tuple[str, str], ...] = (
    (r"phas(?:ed|ing)\s+out|teach[- ]?out|sunsett?ing", CEASING),
    (
        r"suspended|on\s+hold|paused|not\s+currently\s+offered"
        r"|temporarily\s+(?:inactive|unavailable|not\s+offered)",
        SUSPENDED,
    ),
    (
        r"inactiv(?:e|ated)|deactivated|discontinued|deleted|retired"
        r"|withdrawn|cancell?ed|archived|obsolete"
        r"|no\s+longer\s+(?:be\s+)?(?:offered|active|available)",
        CEASED,
    ),
    (
        r"pending(?:\s+approval)?|proposed|(?:under|in)\s+development"
        r"|under\s+review",
        DEVELOPING,
    ),
    # A label's "Active"; never a section's "Open", which is enrollment.
    (r"active|current", ACTIVE),
)
_ANY_STATUS = "|".join(f"(?:{words})" for words, _ in STATUS_WORDS)

# "Status: Inactive", "Course Status - Discontinued". The word before
# "Status" says whose status it is.
STATUS_LABEL_RE = re.compile(
    rf"\b(?:(?P<whose>[a-z]+)\s+)?status\s*[:\-–—]\s*"
    rf"(?P<status>{_ANY_STATUS})\b",
    re.IGNORECASE,
)
# A status that belongs to something other than the course: a section's
# seats, a student's enrollment or grade. "Enrollment Status: Pending" says
# nothing about whether the course is offered.
NOT_THE_COURSES = frozenset(
    {
        "admission",
        "application",
        "class",
        "enrollment",
        "enrolment",
        "grade",
        "grading",
        "payment",
        "registration",
        "seat",
        "seats",
        "section",
        "student",
        "waitlist",
    }
)

# A status set off in the opening line: "(Inactive)", "[Deleted]",
# "*Discontinued*", or one in capitals, "INACTIVE". Capitals alone have to
# be the whole word, so a title's "Retired Persons" is not taken.
_MARKED = (
    r"INACTIVE|DEACTIVATED|DISCONTINUED|DELETED|RETIRED|ARCHIVED|SUSPENDED"
)
TITLE_MARKER_RE = re.compile(
    rf"[(\[*]\s*(?P<status>(?i:{_ANY_STATUS}))\s*[)\]*]"
    rf"|(?<![A-Za-z])(?P<capitals>{_MARKED})(?![A-Za-z])"
)

# "This course is no longer offered", "The course has been discontinued",
# "This course will be discontinued", "This course is temporarily
# suspended".
COURSE_STATEMENT_RE = re.compile(
    r"\b(?:this|the)\s+course\s+"
    r"(?P<verb>is\s+being|is|has\s+been|was|will(?:\s+be)?)\s+"
    r"(?:(?P<adverb>permanently|temporarily)\s+)?"
    rf"(?P<status>{_ANY_STATUS})\b",
    re.IGNORECASE,
)


def status_of(words: str) -> str | None:
    """The ceterms:LifeCycleStatus label the printed words name, or None."""
    for pattern, status in STATUS_WORDS:
        if re.fullmatch(pattern, collapse(words), re.IGNORECASE):
            return status
    return None


def read(occurrence: Occurrence, page: Page) -> Reading:
    """The course's life cycle status: what it prints, else Active."""
    text = shown_text(occurrence.element)
    for find in (_status_label, _title_marker, _course_statement):
        found = find(text)
        if found is not None:
            status, raw_text, strategy = found
            return Reading(
                value=status,
                raw_text=raw_text,
                strategy=strategy,
                css_path=occurrence.css_path,
            )
    return Reading(
        value=ACTIVE,
        raw_text=None,
        strategy=STRATEGY_LISTED_IN_CATALOG,
        css_path=occurrence.css_path,
    )


def _status_label(text: str) -> tuple[str, str, str] | None:
    match = next(
        (
            m
            for m in STATUS_LABEL_RE.finditer(text)
            if (m.group("whose") or "").lower() not in NOT_THE_COURSES
        ),
        None,
    )
    if match is None:
        return None
    status = status_of(match.group("status"))
    if status is None:
        return None
    return status, collapse(match.group(0)), STRATEGY_STATUS_LABEL


def _title_marker(text: str) -> tuple[str, str, str] | None:
    """A status marked in the first line, the one that names the course."""
    opening = text.split("\n\n", 1)[0][:CODE_NEAR_START]
    match = TITLE_MARKER_RE.search(opening)
    if match is None:
        return None
    status = status_of(match.group("status") or match.group("capitals"))
    if status is None:
        return None
    return status, collapse(match.group(0)), STRATEGY_TITLE_MARKER


def _course_statement(text: str) -> tuple[str, str, str] | None:
    match = COURSE_STATEMENT_RE.search(text)
    if match is None:
        return None
    status = status_of(match.group("status"))
    if status is None:
        return None
    verb = match.group("verb").lower()
    adverb = (match.group("adverb") or "").lower()
    if status == DEVELOPING and verb != "is":
        # "This course was proposed by the faculty" is its history.
        return None
    if status == CEASED and adverb == "temporarily":
        status = SUSPENDED
    elif status == CEASED and (verb.startswith("will") or "being" in verb):
        # Not gone yet, going.
        status = CEASING
    return status, collapse(match.group(0)), STRATEGY_COURSE_STATEMENT
