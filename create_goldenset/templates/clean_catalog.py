"""Clean Catalog (custom_html family). One template.

Signature: the Clean Catalog footer or a bare CODE: heading, together with
a line that is exactly "Credits".
"""

from __future__ import annotations

import re

from transcribe_lib import FieldDraft, TranscriptionError
from templates._shared import (
    _add,
    _line_after,
    _maybe_labeled_number,
    _num,
)


FAMILY = "custom_html"


def detect(text: str) -> str | None:
    """Return this family's template id, or None."""
    heading = "Course Catalog Software by Clean Catalog" in text or re.search(
        r"^[A-Z]{2,5}\\d{3}:\\s*$", text, re.M
    )
    if heading and re.search(r"^Credits$", text, re.M):
        return "clean_catalog_course_detail"
    return None


def extract_clean_catalog(text: str) -> list[FieldDraft]:
    m = re.search(r"^([A-Z]{2,5}\d{3}):\s*$", text, re.M)
    if not m:
        raise TranscriptionError("no CODE: heading")
    code = m.group(1)
    code_ex = m.group(0)
    lines = text.splitlines()
    i = next(idx for idx, ln in enumerate(lines) if ln.strip() == f"{code}:")
    name = next(ln for ln in lines[i + 1 :] if ln.strip() and ln.strip() != "Download as PDF")
    drafts: list[FieldDraft] = []
    _add(drafts, "course_id", code, code_ex, "h1 code", text, notes="Split from CODE: / name heading. Code is not the name.")
    _add(drafts, "course_name", name, name, "h1 name", text, notes="Name is the printed title, not the code.")
    program = _line_after(text, "Program")
    if program:
        _add(drafts, "course_program", program, f"Program\n{program}", "Program field", text, raw=program)
    cred = _maybe_labeled_number(text, "Credits")
    if cred:
        number, excerpt = cred
        _add(
            drafts,
            "course_credits",
            number,
            excerpt,
            "Credits field",
            text,
            raw=excerpt,
            notes="Lossless parse of a single printed credit. Not expanded to min/max.",
        )
    lab = _maybe_labeled_number(text, "Lab/Clinical/Field Study Hours")
    if lab:
        number, excerpt = lab
        _add(drafts, "course_lab_hours", number, excerpt, "Lab/Clinical/Field Study Hours", text, raw=excerpt)
    lecture = _maybe_labeled_number(text, "Lecture Hours")
    if lecture:
        number, excerpt = lecture
        _add(drafts, "course_lecture_hours", number, excerpt, "Lecture Hours", text, raw=excerpt)
    if "Prerequisites" in lines:
        prereq_i = lines.index("Prerequisites")
        desc = lines[prereq_i - 1]
        prereq = lines[prereq_i + 1]
        _add(drafts, "course_description", desc, desc, "description paragraph", text)
        _add(drafts, "course_prerequisites", prereq, prereq, "Prerequisites field", text)
    else:
        li = lines.index("Lecture Hours")
        desc = lines[li + 2]
        _add(drafts, "course_description", desc, desc, "description paragraph", text)
    if "Corequisites" in lines:
        ci = lines.index("Corequisites")
        coreq = lines[ci + 1]
        if coreq.strip() and coreq.strip() not in {"User account menu", "Staff Login"}:
            _add(drafts, "course_corequisites", coreq, coreq, "Corequisites field", text)
    return drafts


TEMPLATES = {"clean_catalog_course_detail": extract_clean_catalog}
