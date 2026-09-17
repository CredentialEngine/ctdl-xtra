"""Every regex, keyword list, and threshold discovery uses.

Discovery is deterministic: no model decides what a page is. When a page is
labelled wrong, the fix is a rule in this file and a fixture next to the
others that proves it. Nothing else in the discovery code carries a literal
pattern or a cut-off, so tuning is one file to read and one file to review.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

# --- thresholds -------------------------------------------------------------

# A label printed on nearly every page is the site's furniture, not a field.
CHROME_SHARE = 0.90
# Within one page type, a label or marker this uncommon is worth looking at.
RARE_LABEL_SHARE = 0.05
RARE_MARKER_SHARE = 0.20
# A pattern covering this little of its page type is a special case.
RARE_PATTERN_SHARE = 0.05

EMPTY_PAGE_CHARS = 500
# How far a credits value may sit from the course code it belongs to.
COURSE_BLOCK_WINDOW = 400
# "Near the top" for deciding the page is about one course.
COURSE_CODE_HEAD_CHARS = 300
MAX_FIELD_LABEL_CHARS = 40
MARKER_EVIDENCE_CHARS = 80
PATTERN_ID_LENGTH = 8
MIN_OUTCOME_ITEMS = 2
MIN_PROGRAM_TERMS = 2

DEFAULT_SAMPLE_SIZE = 30
DEFAULT_SAMPLE_LABEL = "Course"

# --- labels -----------------------------------------------------------------

LABEL_COURSE = "Course"
LABEL_LEARNING_OPPORTUNITY = "LearningOpportunity"
LABEL_COMPETENCY = "Competency"
PAGE_TYPE_MULTIPLE = "Multiple"
PAGE_TYPE_UNKNOWN = "Unknown"

# --- course codes and credits ------------------------------------------------

COURSE_CODE_RE = re.compile(r"\b[A-Z]{2,5}[ -]?\d{3,4}[A-Z]?\b")

# The leading boundary matters: without it "accredited" reads as a
# credit value and every page looks like it prints credits.
_CREDIT_WORDS = r"\b(?:credits?|units?|hours?|hrs?|cr)\.?"
_NUMBER = r"\d+(?:\.\d+)?"
_RANGE = rf"{_NUMBER}(?:\s*(?:-|to)\s*{_NUMBER})?"

CREDIT_VALUE_RE = re.compile(
    rf"(?:{_RANGE}\s*{_CREDIT_WORDS}|{_CREDIT_WORDS}\s*[:=-]?\s*{_RANGE})",
    re.IGNORECASE,
)

# 3-2-4 or 3/2/4 printed next to a course: lecture, lab, credit.
LECTURE_LAB_CREDIT_RE = re.compile(r"\b\d{1,2}\s*[-/]\s*\d{1,2}\s*[-/]\s*\d{1,2}\b")

# No boundary after "hours": the normalizer the extractors share glues a
# term to its value, so a definition list reads as "Lab Hours3".
LAB_CLINICAL_HOURS_RE = re.compile(
    r"\b(?:lab(?:oratory)?|clinical|field\s+study|practicum|externship|studio)"
    r"\s*(?:/\s*\w+\s*)?hours?",
    re.IGNORECASE,
)

PRINTED_ZERO_HOURS_RE = re.compile(
    rf"(?:\b0(?:\.0)?\s*{_CREDIT_WORDS}|{_CREDIT_WORDS}\s*[:=-]?\s*0(?:\.0)?\b)",
    re.IGNORECASE,
)

CEU_RE = re.compile(r"\bC\.?E\.?U\.?s?\b|\bcontinuing\s+education\s+units?\b")

# --- relationships between courses ------------------------------------------

PREREQUISITE_RE = re.compile(r"\bpre[\s-]?requisites?\b", re.IGNORECASE)
COREQUISITE_RE = re.compile(r"\bco[\s-]?requisites?\b", re.IGNORECASE)
PREREQ_COREQ_COMBINED_RE = re.compile(
    r"\bpre[\s-]?requisites?\s*(?:/|&|\band\b|\bor\b)\s*co[\s-]?requisites?\b",
    re.IGNORECASE,
)
RECOMMENDED_RE = re.compile(
    r"\brecommended\b(?:\s+(?:pre[\s-]?requisites?|preparation|background))?",
    re.IGNORECASE,
)

# --- outcomes, programs, policies --------------------------------------------

OUTCOMES_HEADING_RE = re.compile(
    r"\b(?:learning\s+)?(?:outcomes?|objectives?|competenc(?:y|ies)|"
    r"goals?\s+and\s+objectives?)\b",
    re.IGNORECASE,
)

PROGRAM_TERM_RES = {
    # Dotted forms only. Case-insensitively, a bare A.S. without its
    # dots is the word "as", which appears on every page ever written.
    "degree": re.compile(
        r"\bdegrees?\b|\bassociate\s+(?:of|in|degree)\b"
        r"|\bbachelor(?:'s)?\b"
        r"|\bA\.A\.S\.|\bA\.A\.|\bA\.S\.|\bB\.A\.|\bB\.S\."
        r"|\bB\.F\.A\.|\bAAS\b",
        re.IGNORECASE,
    ),
    "certificate": re.compile(r"\bcertificates?\b|\bdiploma\b", re.IGNORECASE),
    "program_requirements": re.compile(
        r"\bprogram\s+requirements?\b|\bdegree\s+requirements?\b"
        r"|\brequirements?\s+for\s+(?:the\s+)?(?:degree|certificate|major)\b",
        re.IGNORECASE,
    ),
    "total_credits": re.compile(
        r"\btotal\s+(?:program\s+|degree\s+|required\s+)?"
        r"(?:credits?|credit\s+hours?)\b",
        re.IGNORECASE,
    ),
    "plan_of_study": re.compile(
        r"\bplan\s+of\s+study\b|\bcurriculum\s+(?:plan|map|guide)\b"
        r"|\bprogram\s+map\b|\bsuggested\s+sequence\b|\bcourse\s+sequence\b",
        re.IGNORECASE,
    ),
    "term_sequence": re.compile(
        r"\b(?:first|second|third|fourth|1st|2nd|3rd|4th)\s+"
        r"(?:semester|term|year)\b"
        r"|\b(?:fall|spring|summer|winter)\s+(?:semester|term)\b",
        re.IGNORECASE,
    ),
}

# "Degrees" and "Certificates" are what a navigation menu is called, so they
# appear on every page of a catalog and say nothing about the page under
# them. The terms below are printed by a credential page and by nothing
# else, so one of them has to be present before a page counts as one.
PROGRAM_CONTENT_TERMS = frozenset(
    {"program_requirements", "total_credits", "plan_of_study", "term_sequence"}
)

PROGRAM_URL_RE = re.compile(
    r"program|degree|certificate|major|preview_program", re.IGNORECASE
)


def has_program_content(terms: list[str]) -> bool:
    """True when the page prints something only a credential page prints."""
    return any(term in PROGRAM_CONTENT_TERMS for term in terms)

POLICY_OR_DEFINITION_RE = re.compile(
    r"\bcourse\s+numbering\b|\bnumbering\s+system\b"
    r"|\bhow\s+to\s+read\s+(?:a\s+|the\s+)?course\b"
    r"|\bkey\s+to\s+course\s+descriptions?\b"
    r"|\bcourse\s+description\s+(?:key|legend|format|guide)\b"
    r"|\bdefinition\s+of\s+(?:a\s+)?credit\s+hours?\b"
    r"|\bcredit\s+hour\s+(?:definition|policy)\b"
    r"|\bexplanation\s+of\s+course\b",
    re.IGNORECASE,
)

ARCHIVED_RE = re.compile(
    r"\barchived?\s+catalog\b|\bcatalog\s+archive\b"
    r"|\bthis\s+(?:is|was)\s+an\s+archived?\b"
    r"|\bno\s+longer\s+(?:current|in\s+effect)\b"
    r"|\bprevious\s+(?:catalog|edition)\b"
    r"|\bfor\s+(?:reference|historical)\s+purposes\s+only\b",
    re.IGNORECASE,
)

CATALOG_YEAR_RE = re.compile(r"\b(20\d{2})\s*(?:-|/|to)\s*(20\d{2}|\d{2})\b")

# 404 has to be error-shaped. On its own it matched the area code in a phone
# number, which marked a real program page empty and dropped it from the
# sample population.
EMPTY_OR_ERROR_RE = re.compile(
    r"\b(?:page|file|document)\s+not\s+found\b"
    r"|\b404\s+(?:error|not\s+found)\b|\berror\s+404\b|\bHTTP\s+404\b"
    r"|\ban\s+error\s+(?:has\s+)?occurred\b|\baccess\s+denied\b"
    r"|\bplease\s+log\s*in\b|\bsign\s+in\s+to\s+continue\b"
    r"|\byou\s+do\s+not\s+have\s+permission\b",
    re.IGNORECASE,
)

TAB_ROLE_RE = re.compile(r"\btab\b", re.IGNORECASE)
TAB_CLASS_RE = re.compile(r"\btabs?\b|\btab-(?:nav|list|pane)\b", re.IGNORECASE)

# --- shared text helpers ------------------------------------------------------

DIGIT_RUN_RE = re.compile(r"\d+")
WHITESPACE_RE = re.compile(r"\s+")
_TRIM_PUNCTUATION = " \t:;,.-_*|/\\"

MARKER_NAMES = (
    "lecture_lab_credit_numbers",
    "lab_clinical_field_study_hours",
    "printed_zero_hours",
    "ceu",
    "prerequisite",
    "corequisite",
    "prerequisite_corequisite_combined",
    "recommended",
    "learning_outcomes",
    "program_markers",
    "tabs_present",
    "archived",
    "catalog_year",
    "policy_or_definition_page",
    "multi_course_page",
    "empty_or_error_page",
)

# One line per marker on what it costs an extractor that ignores it.
MARKER_MEANING = {
    "lecture_lab_credit_numbers": (
        "Three numbers in a row are lecture, lab, and credit hours. Read as "
        "one value they become a wrong credit count."
    ),
    "lab_clinical_field_study_hours": (
        "Contact hours are printed beside credits. An extractor that takes "
        "the first number on the line reports contact hours as credits."
    ),
    "printed_zero_hours": (
        "A printed 0 is a real value, not a missing one. Treating it as "
        "absent loses the distinction between zero-credit and unstated."
    ),
    "ceu": (
        "Continuing education units are not academic credits and must not "
        "be mapped to the same field."
    ),
    "prerequisite": "A prerequisite list to parse into course references.",
    "corequisite": "A corequisite list, which is a different relation.",
    "prerequisite_corequisite_combined": (
        "One heading covers both relations, so splitting on the heading "
        "alone assigns corequisites to the prerequisite field."
    ),
    "recommended": (
        "A recommendation is not a requirement and must not become one."
    ),
    "learning_outcomes": (
        "A competency list lives here, which is a separate entity from the "
        "course that carries it."
    ),
    "program_markers": (
        "The page describes a credential, not a course, so course fields "
        "will be empty or borrowed from a listing."
    ),
    "tabs_present": (
        "Content sits in hidden tab panels. Text taken from the visible tab "
        "alone silently drops the rest."
    ),
    "archived": (
        "The page is a past catalog. Mixing it with the current one "
        "produces two versions of the same course."
    ),
    "catalog_year": (
        "The year range this page belongs to, which pins every value on it "
        "to a time frame."
    ),
    "policy_or_definition_page": (
        "The page explains how to read courses. It contains course codes "
        "but describes none of them."
    ),
    "multi_course_page": (
        "Several courses share the page, so one record per page is wrong."
    ),
    "empty_or_error_page": (
        "Nothing was captured. Extracting produces an empty record that "
        "looks like a real one."
    ),
}


def url_template(url: str) -> str:
    """Path and query with every run of digits replaced by {n}."""
    parsed = urlsplit(url)
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return DIGIT_RUN_RE.sub("{n}", f"{path}{query}")


def collapse(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def normalize_field_label(text: str) -> str | None:
    """Turn a label as printed into the form the vocabulary counts.

    Lowercase, collapsed spaces, no trailing colon or punctuation, digits
    replaced by #. Anything too long to be a key, or carrying a course code,
    is not a label: those are sentences and course titles.
    """
    raw = collapse(text)
    if not raw:
        return None
    trimmed = raw.strip(_TRIM_PUNCTUATION)
    if not trimmed or len(trimmed) > MAX_FIELD_LABEL_CHARS:
        return None
    if COURSE_CODE_RE.search(trimmed):
        return None
    label = DIGIT_RUN_RE.sub("#", trimmed).lower()
    return label or None


def evidence(text: str, match: re.Match[str] | None = None) -> str:
    """A short quote showing why a marker fired."""
    if match is not None:
        start = max(0, match.start() - 20)
        text = text[start : match.end() + 40]
    return collapse(text)[:MARKER_EVIDENCE_CHARS]


def catalog_year_value(text: str) -> str | None:
    """The catalog year range as printed, written out in full."""
    match = CATALOG_YEAR_RE.search(text or "")
    if not match:
        return None
    start, end = match.group(1), match.group(2)
    if len(end) == 2:
        end = f"{start[:2]}{end}"
    return f"{start}-{end}"


def course_codes(text: str) -> list[str]:
    return COURSE_CODE_RE.findall(text)


def course_block_count(text: str) -> int:
    """Course codes that have a credits, units, or hours value nearby.

    A code on its own is a cross-reference; a code with a credits value is
    the course itself being described.
    """
    blocks = 0
    for match in COURSE_CODE_RE.finditer(text):
        window = text[match.end() : match.end() + COURSE_BLOCK_WINDOW]
        if CREDIT_VALUE_RE.search(window):
            blocks += 1
    return blocks


def near_course_code(text: str, match: re.Match[str]) -> bool:
    """True when a course code sits within one block window of the match."""
    start = max(0, match.start() - COURSE_BLOCK_WINDOW)
    window = text[start : match.end() + COURSE_BLOCK_WINDOW]
    return bool(COURSE_CODE_RE.search(window))


def program_terms(text: str) -> list[str]:
    """Which program vocabulary terms the page uses, by name."""
    return sorted(
        name for name, rule in PROGRAM_TERM_RES.items() if rule.search(text)
    )
