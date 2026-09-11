"""Coursedog family. Three page templates: RCBC/Hudson, Mercer, Brookdale.

Detection order inside the family matters: RCBC and Mercer carry distinctive
labels, so they are tested before the generic Brookdale shape, which would
otherwise match all three.
"""

from __future__ import annotations

import re

from transcribe_lib import FieldDraft, TranscriptionError
from templates._shared import _add, _line_after, _num


FAMILY = "coursedog"


def detect(text: str) -> str | None:
    """Return this family's template id, or None. Order is load bearing."""
    if "Course Long Title" in text or "(Credit Hours) Min" in text:
        return "coursedog_rcbc_course_detail"
    if (
        re.search(r"^Subject Code$", text, re.M)
        and re.search(r"^Course Number$", text, re.M)
        and "Course Description" in text
    ):
        return "coursedog_mccc_course_detail"
    if "Course Description" in text and (
        "Credit Hours" in text or "Credit Hours Min" in text
    ):
        return "coursedog_brookdale_course_detail"
    return None


def _coursedog_credits(text: str) -> list[tuple[str, object, str, str]]:
    """Return credit fields. Single value unless Max or a range is printed."""
    lines = text.splitlines()
    out: list[tuple[str, object, str, str]] = []
    if "Credit Hours" in lines:
        i = lines.index("Credit Hours")
        if i + 1 < len(lines) and lines[i + 1].strip() == "Min":
            n_txt = lines[i + 2].strip()
            number = _num(n_txt)
            if i + 3 < len(lines) and lines[i + 3].strip() == "Max":
                max_txt = lines[i + 4].strip()
                min_ex = f"Credit Hours\nMin\n{n_txt}"
                max_ex = f"Max\n{max_txt}"
                out.append(("course_credits_min", number, min_ex, "Credit Hours Min"))
                out.append(("course_credits_max", _num(max_txt), max_ex, "Credit Hours Max"))
                return out
            credits_ex = f"Credit Hours\nMin\n{n_txt}"
            out.append(
                (
                    "course_credits",
                    number,
                    credits_ex,
                    "Credit Hours Min (no Max printed)",
                )
            )
            return out
    if "(Credit Hours) Min" in lines:
        i = lines.index("(Credit Hours) Min")
        n_txt = lines[i + 1].strip()
        nxt_label = lines[i + 2].strip() if i + 2 < len(lines) else ""
        if nxt_label == "(Credit Hours) Max" or nxt_label == "Max":
            max_txt = lines[i + 3].strip()
            out.append(("course_credits_min", _num(n_txt), f"(Credit Hours) Min\n{n_txt}", "Min bound"))
            out.append(("course_credits_max", _num(max_txt), f"{nxt_label}\n{max_txt}", "Max bound"))
            return out
        out.append(("course_credits", _num(n_txt), f"(Credit Hours) Min\n{n_txt}", "Credit Hours Min only"))
        return out
    if "Credit Hours Min" in lines:
        i = lines.index("Credit Hours Min")
        n_txt = lines[i + 1].strip()
        if i + 2 < len(lines) and lines[i + 2].strip() == "Credit Hours Max":
            max_txt = lines[i + 3].strip()
            out.append(("course_credits_min", _num(n_txt), f"Credit Hours Min\n{n_txt}", "Min bound"))
            out.append(("course_credits_max", _num(max_txt), f"Credit Hours Max\n{max_txt}", "Max bound"))
            return out
        out.append(("course_credits", _num(n_txt), f"Credit Hours Min\n{n_txt}", "Credit Hours Min only"))
        return out
    raise TranscriptionError("no Coursedog credit hours block")


def _after_courses_slash(text: str) -> tuple[str, str]:
    lines = text.splitlines()
    try:
        i = lines.index("Courses/")
    except ValueError as exc:
        raise TranscriptionError("no Courses/ breadcrumb") from exc
    name = lines[i + 1].strip()
    code = lines[i + 2].strip()
    if code == "Download as PDF":
        raise TranscriptionError("expected course code after title")
    return name, code


def extract_brookdale(text: str) -> list[FieldDraft]:
    name, code = _after_courses_slash(text)
    desc = _line_after(text, "Course Description")
    if not desc:
        raise TranscriptionError("no Course Description")
    drafts: list[FieldDraft] = []
    _add(drafts, "course_id", code, code, "course code line", text)
    _add(drafts, "course_name", name, name, "course title", text, notes="Name is the printed title, not the code.")
    _add(drafts, "course_description", desc, desc, "Course Description", text)
    for label, value, excerpt, loc in _coursedog_credits(text):
        notes = "Page prints Min only. Single value, not an invented max." if label == "course_credits" else "Printed bound."
        _add(drafts, label, value, excerpt, loc, text, raw=excerpt, notes=notes)
    ge = _line_after(text, "General Education Competencies")
    if ge and ge not in {"School", "Credit Hours"}:
        _add(drafts, "course_general_education", ge, f"General Education Competencies\n{ge}", "GE competencies", text, raw=ge)
    school = _line_after(text, "School")
    if school:
        _add(drafts, "course_school", school, f"School\n{school}", "School field", text, raw=school)
    division = _line_after(text, "Division")
    if division:
        _add(drafts, "course_division", division, f"Division\n{division}", "Division field", text, raw=division)
    dept = _line_after(text, "Department(s) ~*") or _line_after(text, "Department")
    if dept:
        label = "Department(s) ~*" if _line_after(text, "Department(s) ~*") else "Department"
        _add(drafts, "course_department", dept, f"{label}\n{dept}", "Department field", text, raw=dept)
    m = re.search(
        r"\((Prerequisite(?:\(s\))?(?: or Corequisite)?:)\s*(.+)\)\s*$",
        desc,
    )
    if m:
        prereq = m.group(2)
        excerpt = m.group(0)
        _add(
            drafts,
            "course_prerequisites",
            prereq,
            excerpt,
            "parenthetical requirement in description",
            text,
            raw=excerpt,
            notes="Printed in the description, not a separate Prerequisites field.",
        )
    return drafts


def extract_mccc(text: str) -> list[FieldDraft]:
    name, code = _after_courses_slash(text)
    if name == code:
        raise TranscriptionError("Mercer title/code collapsed")
    desc = _line_after(text, "Course Description")
    if not desc:
        raise TranscriptionError("no Course Description")
    drafts: list[FieldDraft] = []
    heading_ex = f"{name}\n{code}\n{name}"
    if heading_ex in text:
        _add(drafts, "course_id", code, heading_ex, "course heading code", text, raw=code, notes="Code split from title/code/title block.")
    else:
        _add(drafts, "course_id", code, code, "course code line", text)
    _add(drafts, "course_name", name, name, "course title", text, notes="Name is the printed title, not the code.")
    subj = _line_after(text, "Subject Code")
    if subj:
        _add(drafts, "course_subject_code", subj, f"Subject Code\n{subj}", "Subject Code", text, raw=subj)
    num = _line_after(text, "Course Number")
    if num:
        _add(drafts, "course_number", num, f"Course Number\n{num}", "Course Number", text, raw=num)
    _add(drafts, "course_description", desc, desc, "Course Description", text)
    for label, value, excerpt, loc in _coursedog_credits(text):
        notes = "Page prints Min only. Single value, not an invented max." if label == "course_credits" else "Printed bound."
        _add(drafts, label, value, excerpt, loc, text, raw=excerpt, notes=notes)
    pre, pre_ex = _mccc_this_course_requirement(text, code, "Prerequisite")
    if pre:
        _add(
            drafts,
            "course_prerequisites",
            pre,
            pre_ex,
            "this-course Prerequisite block",
            text,
            raw=pre_ex,
            notes="Related-course lists ('is a prerequisite for') are not this course's prerequisites.",
        )
    co, co_ex = _mccc_this_course_requirement(text, code, "Corequisite")
    if co:
        _add(drafts, "course_corequisites", co, co_ex, "this-course Corequisite block", text, raw=co_ex)
    return drafts


def _mccc_this_course_requirement(text: str, code: str, heading: str) -> tuple[str | None, str | None]:
    """Capture this course's own reqs. Ignore 'CODE is a prerequisite for' lists."""
    lines = text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == "Course Description")
    except StopIteration:
        return None, None
    stop_prefixes = (f"{code} is a ",)
    courses: list[str] = []
    header = None
    in_block = False
    for ln in lines[start + 1 :]:
        if any(ln.startswith(p) for p in stop_prefixes):
            break
        if ln.strip() == heading:
            in_block = True
            continue
        if ln.strip() in {"Corequisite", "Prerequisite"} and ln.strip() != heading:
            in_block = False
            continue
        if not in_block:
            continue
        if ln.strip() in {"Course Requirements", "Courses", "Collapse All"}:
            continue
        if ln.startswith("Earn a minimum") or ln.startswith("Enroll in the following"):
            header = ln
            continue
        if re.match(r"^[A-Z]{2,6}\d{3} - ", ln):
            courses.append(ln)
            continue
        if courses or header:
            break
    if not header or not courses:
        return None, None
    excerpt = "\n".join([header, *courses])
    if excerpt not in text:
        return None, None
    return excerpt, excerpt


def extract_rcbc(text: str) -> list[FieldDraft]:
    name, code = _after_courses_slash(text)
    desc = _line_after(text, "Description") or _line_after(text, "Course Description")
    if not desc:
        raise TranscriptionError("no Description")
    drafts: list[FieldDraft] = []
    _add(drafts, "course_id", code, code, "course code line", text)
    _add(drafts, "course_name", name, name, "course title", text, notes="Name is the printed title, not the code.")
    long_title = _line_after(text, "Course Long Title")
    if long_title:
        _add(drafts, "course_long_title", long_title, f"Course Long Title\n{long_title}", "Course Long Title", text, raw=long_title)
    subj = _line_after(text, "Subject code") or _line_after(text, "Subject Code")
    if subj:
        label = "Subject code" if _line_after(text, "Subject code") else "Subject Code"
        _add(drafts, "course_subject_code", subj, f"{label}\n{subj}", label, text, raw=subj)
    num = _line_after(text, "Course Number")
    if num:
        _add(drafts, "course_number", num, f"Course Number\n{num}", "Course Number", text, raw=num)
    level = _line_after(text, "Academic Level")
    if level:
        _add(drafts, "course_academic_level", level, f"Academic Level\n{level}", "Academic Level", text, raw=level)
    _add(drafts, "course_description", desc, desc, "Description field", text)
    for label, value, excerpt, loc in _coursedog_credits(text):
        notes = "Page prints Min only. Single value, not an invented max." if label == "course_credits" else "Printed bound."
        _add(drafts, label, value, excerpt, loc, text, raw=excerpt, notes=notes)
    m = re.search(r"(Co-requisite:\s*[A-Z]{2,5}-\d{3})", desc)
    if m:
        excerpt = m.group(1)
        val = excerpt.split(":", 1)[1].strip()
        _add(drafts, "course_corequisites", val, excerpt, "Co-requisite in description", text, raw=excerpt)
    return drafts


TEMPLATES = {
    "coursedog_rcbc_course_detail": extract_rcbc,
    "coursedog_mccc_course_detail": extract_mccc,
    "coursedog_brookdale_course_detail": extract_brookdale,
}
