"""Normalized freeze texts for the eight lib course templates.

Each text is what src/lib/normalize.py makes of a course page: one stripped
line per block, no blank lines, a trailing newline. Real Coursedog and
Acalog pages are not in tests/fixtures, so these are written by hand to
the layout each template reads, as src/lib/CLASSIFICATION.md describes it.
A non-breaking space is spelled \xa0, as Acalog prints its code-dash-title
headings. as_html() serves a text as a page, which is how the tests show
that normalize_html can really produce it.
"""

from __future__ import annotations

import html


def lines(*rows: str) -> str:
    """Rows as normalize_html prints them: joined, newline-terminated."""
    return "\n".join(rows) + "\n"


def as_html(text: str) -> str:
    """One <p> per line, so normalize_html gives the same text back."""
    body = "".join(f"<p>{html.escape(row)}</p>" for row in text.splitlines())
    return f"<!DOCTYPE html><html><head><title>t</title></head><body>{body}</body></html>"


CLEAN_CATALOG = lines(
    "Course Catalog Software by Clean Catalog",
    "ENGL101:",
    "Download as PDF",
    "English Composition I",
    "Program",
    "English",
    "Credits",
    "3",
    "Lab/Clinical/Field Study Hours",
    "0",
    "Lecture Hours",
    "3",
    "Develops college-level writing through drafting and revision.",
    "Prerequisites",
    "ENGL099 or placement",
    "Corequisites",
    "ENGL101L",
)

COURSEDOG_RCBC = lines(
    "Courses/",
    "English Composition I",
    "ENG-101",
    "Course Long Title",
    "English Composition I: Academic Writing",
    "Subject code",
    "ENG",
    "Course Number",
    "101",
    "Academic Level",
    "Undergraduate",
    "Description",
    "Develops academic writing. Co-requisite: ENG-091",
    "(Credit Hours) Min",
    "3",
)

COURSEDOG_MCCC = lines(
    "Courses/",
    "Composition I",
    "ENG101",
    "Composition I",
    "Subject Code",
    "ENG",
    "Course Number",
    "101",
    "Course Description",
    "Introduces expository writing and research.",
    "Credit Hours",
    "Min",
    "3",
    "Prerequisite",
    "Course Requirements",
    "Earn a minimum grade of C in the following",
    "ENG021 - Basic Writing",
    "Corequisite",
    "Enroll in the following",
    "ENG111 - Composition Lab",
    "ENG101 is a prerequisite for",
    "ENG102 - Composition II",
)

COURSEDOG_BROOKDALE = lines(
    "Courses/",
    "English Composition: Writing as Process",
    "ENGL121",
    "Course Description",
    "Develops writing as a process of drafting and revision. "
    "(Prerequisite(s): ENGL095 or placement)",
    "Credit Hours",
    "Min",
    "3",
    "General Education Competencies",
    "Written and Oral Communication",
    "School",
    "Humanities",
    "Division",
    "Liberal Arts",
    "Department(s) ~*",
    "English",
)

ACALOG_HCC = lines(
    "Add to Portfolio (opens a new window)",
    "ENG 1010\xa0-\xa0College Composition I Credits: 3",
    "Lecture: 3",
    "Lab: 0",
    "3.0 CEUs",
    "Prerequisite(s): ENG 0930 or placement",
    "Introduces academic writing, argument and research at college level.",
)

ACALOG_UNITS = lines(
    "ENGL 1\xa0-\xa0Reading and Composition4 units",
    "4 hours lecture, 1 hour lab",
    "Prerequisite: ENGL 100 or placement.",
    "Develops critical reading and expository writing across disciplines.",
)

ACALOG_BERGEN = lines(
    "WRT-101 English Composition I3 Credit(s)",
    "3 Lecture Hour(s)",
    "0 Lab Hour(s)",
    "This course develops writing through the study of rhetoric.",
    "General Education Course: Communication",
    "Prerequisite(s): WRT-095 or placement",
)

ACALOG_RARITAN = lines(
    "Add to Portfolio (opens a new window)",
    "ENGL 111\xa0-\xa0English I",
    "(3,0) 3 Credits",
    "General Education Course: Written CommunicationPrerequisite(s): ENGL 070",
    "This course develops expository writing through structured practice.",
)

TEXTS = {
    "clean_catalog_course_detail": CLEAN_CATALOG,
    "coursedog_rcbc_course_detail": COURSEDOG_RCBC,
    "coursedog_mccc_course_detail": COURSEDOG_MCCC,
    "coursedog_brookdale_course_detail": COURSEDOG_BROOKDALE,
    "acalog_hcc_nbsp_credits": ACALOG_HCC,
    "acalog_units_glued_hours": ACALOG_UNITS,
    "acalog_bergen_glued_credits": ACALOG_BERGEN,
    "acalog_raritan_hours_credits": ACALOG_RARITAN,
}
