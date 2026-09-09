"""Deterministic Course transcription from freeze text. One extractor per catalog template."""

from __future__ import annotations

import re

from slots import Slot
from transcribe_lib import FieldDraft, TranscriptionError


def detect_template(text: str) -> str | None:
    """Pick an extractor from freeze text. College name is not a signal."""
    if "Course Catalog Software by Clean Catalog" in text or re.search(
        r"^[A-Z]{2,5}\d{3}:\s*$", text, re.M
    ):
        if re.search(r"^Credits$", text, re.M):
            return "clean_catalog_course_detail"
    if "Course Long Title" in text or "(Credit Hours) Min" in text:
        return "coursedog_rcbc_course_detail"
    if (
        re.search(r"^Subject Code$", text, re.M)
        and re.search(r"^Course Number$", text, re.M)
        and "Course Description" in text
    ):
        return "coursedog_mccc_course_detail"
    if "Course Description" in text and ("Credit Hours" in text or "Credit Hours Min" in text):
        return "coursedog_brookdale_course_detail"
    if re.search(r"^[A-Z]{2,4}-\d{3} .+?\d+(?:\.\d+)? Credit\(s\)$", text, re.M):
        return "acalog_bergen_glued_credits"
    if re.search(r"\([0-9.]+,[0-9.]+\) \d+(?:\.\d+)? Credits", text) and "\xa0-\xa0" in text:
        return "acalog_raritan_hours_credits"
    return None


def extract_course(slot: Slot, text: str) -> list[FieldDraft]:
    tid = detect_template(text)
    if tid is None and slot.template_id in TEMPLATE:
        tid = slot.template_id
    if tid not in TEMPLATE:
        raise TranscriptionError(
            f"{slot.record_id}: freeze does not match a known course template "
            "(Clean Catalog, Coursedog, or Acalog). No LLM fallback."
        )
    return TEMPLATE[tid](text)


def _f(field_id, label, value, excerpt, loc, *, raw=None, notes=None, occ=None) -> FieldDraft:
    return FieldDraft(
        field_id=field_id,
        canonical_label=label,
        value=value,
        raw_text=raw if raw is not None else (excerpt if isinstance(value, str) else excerpt),
        excerpt=excerpt,
        locator_strategy="text_anchor",
        locator_value=loc,
        occurrence=occ,
        notes=notes,
    )


def _occ(text: str, excerpt: str) -> int | None:
    n = text.count(excerpt)
    if n == 0:
        raise TranscriptionError(f"missing {excerpt[:160]!r}")
    return None if n == 1 else 1


def _line_after(text: str, label: str) -> str | None:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == label:
            for nxt in lines[i + 1 :]:
                if nxt.strip():
                    return nxt
    return None


def _num(txt: str):
    t = txt.strip()
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    if re.fullmatch(r"-?\d+\.\d+", t):
        return float(t)
    raise TranscriptionError(f"not a number: {txt!r}")


def _add(drafts: list[FieldDraft], label: str, value, excerpt: str, loc: str, text: str, **kwargs) -> None:
    drafts.append(
        _f(
            f"src_{len(drafts) + 1:03d}",
            label,
            value,
            excerpt,
            loc,
            occ=kwargs.pop("occ", _occ(text, excerpt)),
            **kwargs,
        )
    )


def _maybe_labeled_number(text: str, label: str) -> tuple[object, str] | None:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() != label:
            continue
        for nxt in lines[i + 1 :]:
            if nxt.strip():
                n_txt = nxt.strip()
                return _num(n_txt), f"{label}\n{n_txt}"
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


_BERGEN_HEAD = re.compile(r"^([A-Z]{2,4}-\d{3}) (.+?)(\d+(?:\.\d+)?) Credit\(s\)$", re.M)


def extract_bergen(text: str) -> list[FieldDraft]:
    m = _BERGEN_HEAD.search(text)
    if not m:
        raise TranscriptionError("no Acalog CODE NameN Credit(s) heading")
    code, name, n_txt = m.group(1), m.group(2), m.group(3)
    heading = m.group(0)
    number = _num(n_txt)
    lines = text.splitlines()
    hi = next(i for i, ln in enumerate(lines) if ln == heading)
    drafts: list[FieldDraft] = []
    _add(
        drafts,
        "course_id",
        code,
        heading,
        "acalog heading code",
        text,
        notes="Code split from glued heading. Code is not the name.",
    )
    _add(
        drafts,
        "course_name",
        name,
        heading,
        "acalog heading name",
        text,
        notes="Name split from glued CODE NameN Credit(s) heading. Digit before Credit(s) is not part of the name.",
    )
    credit_ex = f"{n_txt} Credit(s)"
    _add(
        drafts,
        "course_credits",
        number,
        credit_ex,
        "Credit(s) in heading",
        text,
        raw=credit_ex,
        notes="Single printed credit; not expanded to min/max.",
    )
    for label, field in (("Lab Hour(s)", "course_lab_hours"), ("Lecture Hour(s)", "course_lecture_hours")):
        pat = re.compile(rf"^(\d+(?:\.\d+)?) {re.escape(label)}$", re.M)
        hm = pat.search(text)
        if hm:
            _add(drafts, field, _num(hm.group(1)), hm.group(0), label, text, raw=hm.group(0))
    desc = None
    for nxt in lines[hi + 1 :]:
        if nxt.startswith("This ") or nxt.startswith("The ") or (len(nxt) > 60 and "Hour(s)" not in nxt and "Credit(s)" not in nxt):
            desc = nxt
            break
    if desc:
        _add(drafts, "course_description", desc, desc, "description paragraph", text)
    for nxt in lines[hi + 1 :]:
        if nxt.startswith("General Education Course"):
            _add(drafts, "course_general_education", nxt, nxt, "General Education Course line", text)
            break
    for nxt in lines[hi + 1 :]:
        if nxt.startswith("Prerequisite(s):"):
            prereq = _prereq_value(nxt)
            _add(drafts, "course_prerequisites", prereq, nxt, "Prerequisite(s) line", text, raw=nxt)
            break
        if nxt.startswith("Corequisite(s):"):
            coreq = nxt[len("Corequisite(s):") :].strip()
            _add(drafts, "course_corequisites", coreq, nxt, "Corequisite(s) line", text, raw=nxt)
    return drafts


def _prereq_value(block: str) -> str:
    """Keep Prerequisite(s): when the printed remainder is the glued 'and Corequisite' label."""
    block = block.strip()
    prefix = "Prerequisite(s):"
    if not block.startswith(prefix):
        return block
    rest = block[len(prefix) :].strip()
    if rest.lower().startswith("and corequisite"):
        return block
    return rest


_RARITAN_TITLE = re.compile(r"^([A-Z]{2,5} \d{3})\xa0-\xa0(.+)$")
_RARITAN_HOURS = re.compile(r"^\((\d+(?:\.\d+)?),(\d+(?:\.\d+)?)\) (\d+(?:\.\d+)?) Credits$")
_RARITAN_INLINE_HOURS = re.compile(
    r"^(.*?)\s+\((\d+(?:\.\d+)?),(\d+(?:\.\d+)?)\) (\d+(?:\.\d+)?) Credits$"
)


def extract_raritan(text: str) -> list[FieldDraft]:
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("Add to Portfolio"))
    title_line = lines[start + 1]
    tm = _RARITAN_TITLE.match(title_line)
    if not tm:
        raise TranscriptionError(f"no Raritan CODE - title heading: {title_line!r}")
    code = tm.group(1)
    rest = tm.group(2)
    inline = _RARITAN_INLINE_HOURS.match(rest)
    if inline:
        name = inline.group(1).strip()
        lecture, lab, credits = inline.group(2), inline.group(3), inline.group(4)
        hours_ex = f"({lecture},{lab}) {credits} Credits"
    else:
        name = rest.strip()
        hours_line = lines[start + 2]
        hm = _RARITAN_HOURS.match(hours_line)
        if not hm:
            raise TranscriptionError(f"no Raritan hours line: {hours_line!r}")
        lecture, lab, credits = hm.group(1), hm.group(2), hm.group(3)
        hours_ex = hours_line
    drafts: list[FieldDraft] = []
    _add(
        drafts,
        "course_id",
        code,
        title_line,
        "acalog heading code",
        text,
        notes="Code split from NBSP-dashed heading. Code is not the name.",
    )
    _add(
        drafts,
        "course_name",
        name,
        title_line,
        "acalog heading name",
        text,
        notes="Name split from heading; hours/credits are not the name.",
    )
    _add(
        drafts,
        "course_credits",
        _num(credits),
        hours_ex,
        "Credits in (lecture,lab) Credits line",
        text,
        raw=hours_ex,
        notes="Single printed credit; not expanded to min/max.",
    )
    _add(drafts, "course_lecture_hours", _num(lecture), hours_ex, "lecture hours in (lecture,lab)", text, raw=hours_ex)
    _add(drafts, "course_lab_hours", _num(lab), hours_ex, "lab hours in (lecture,lab)", text, raw=hours_ex)
    ge_line = next((ln for ln in lines[start + 1 :] if ln.startswith("General Education Course:")), None)
    if ge_line:
        cut = ge_line.find("Prerequisite")
        ge_ex = ge_line[:cut] if cut > 0 else ge_line
        ge_val = ge_ex.split(":", 1)[1].strip() if ":" in ge_ex else ge_ex
        _add(drafts, "course_general_education", ge_val, ge_ex, "General Education Course prefix", text, raw=ge_ex)
    desc = None
    for ln in lines[start + 1 :]:
        if ln.startswith("This ") or ln.startswith("English Composition I is") or ln.startswith("Introduction to"):
            desc = ln
            break
    pstart = text.find("Prerequisite(s):")
    if pstart >= 0 and desc:
        pend = text.find(desc, pstart)
        if pend > pstart:
            prereq_ex = text[pstart:pend].rstrip("\n")
            prereq_val = _prereq_value(prereq_ex)
            _add(
                drafts,
                "course_prerequisites",
                prereq_val,
                prereq_ex,
                "Prerequisite(s) block",
                text,
                raw=prereq_ex,
                notes="Freeze glues GE and Prerequisite(s). Keep Prerequisite(s): when the page then prints and Corequisite.",
            )
    if desc:
        _add(drafts, "course_description", desc, desc, "description paragraph", text)
    return drafts


TEMPLATE = {
    "clean_catalog_course_detail": extract_clean_catalog,
    "coursedog_brookdale_course_detail": extract_brookdale,
    "coursedog_mccc_course_detail": extract_mccc,
    "coursedog_rcbc_course_detail": extract_rcbc,
    "acalog_bergen_glued_credits": extract_bergen,
    "acalog_raritan_hours_credits": extract_raritan,
}
