"""Acalog family. Two page templates: Bergen glued credits, Raritan hours.

Bergen prints CODE-NNN Title{n} Credit(s) on one heading line. Raritan prints
a non-breaking-space dash heading and a (lecture,lab) N Credits line.
"""

from __future__ import annotations

import re

from transcribe_lib import FieldDraft, TranscriptionError
from templates._shared import _add, _num, _prereq_value


FAMILY = "acalog"


_BERGEN_HEAD = re.compile(r"^([A-Z]{2,4}-\d{3}) (.+?)(\d+(?:\.\d+)?) Credit\(s\)$", re.M)

_RARITAN_TITLE = re.compile(r"^([A-Z]{2,5} \d{3})\xa0-\xa0(.+)$")
_RARITAN_HOURS = re.compile(r"^\((\d+(?:\.\d+)?),(\d+(?:\.\d+)?)\) (\d+(?:\.\d+)?) Credits$")
_RARITAN_INLINE_HOURS = re.compile(
    r"^(.*?)\s+\((\d+(?:\.\d+)?),(\d+(?:\.\d+)?)\) (\d+(?:\.\d+)?) Credits$"
)

_HCC_HEAD_GLUED = re.compile(
    r"^([A-Z]{2,5} \d{4})\xa0-\xa0(.+?) Credits: (\d+(?:\.\d+)?)$",
    re.M,
)
_HCC_HEAD = re.compile(r"^([A-Z]{2,5} \d{4})\xa0-\xa0(.+)$", re.M)
_HCC_CREDITS_LINE = re.compile(r"^Credits: (\d+(?:\.\d+)?)$", re.M)
_HCC_LECTURE = re.compile(r"^Lecture: (\d+(?:\.\d+)?)$", re.M)
_HCC_LAB = re.compile(r"^Lab: (\d+(?:\.\d+)?)$", re.M)
_HCC_CEU = re.compile(r"^(\d+(?:\.\d+)?) CEUs$", re.M)
_HCC_PREREQ = re.compile(r"^Prerequisite\(s\): (.+)$", re.M)
_UNITS_HEAD = re.compile(
    r"^([A-Z]{1,6} \d{1,4})\xa0-\xa0(.+?)(\d+(?:\.\d+)?) units?$",
    re.M,
)
_LECTURE_LAB = re.compile(
    r"^(\d+(?:\.\d+)?) hours? lecture(?:, (\d+(?:\.\d+)?) hours? lab)?$",
    re.M,
)
_LAB_ONLY = re.compile(r"^(\d+(?:\.\d+)?) hours? lab$", re.M)


def detect(text: str) -> str | None:
    """Return this family's template id, or None."""
    if _HCC_HEAD_GLUED.search(text) or (
        _HCC_HEAD.search(text) and _HCC_CREDITS_LINE.search(text)
    ):
        return "acalog_hcc_nbsp_credits"
    if _UNITS_HEAD.search(text) and (
        _LECTURE_LAB.search(text) or _LAB_ONLY.search(text)
    ):
        return "acalog_units_glued_hours"
    if _BERGEN_HEAD.search(text):
        return "acalog_bergen_glued_credits"
    if re.search(r"\([0-9.]+,[0-9.]+\) \d+(?:\.\d+)? Credits", text) and "\xa0-\xa0" in text:
        return "acalog_raritan_hours_credits"
    return None


def extract_hcc(text: str) -> list[FieldDraft]:
    """Acalog pages that print CODE NBSP-dash name and Credits: (not college-name based)."""
    glued = _HCC_HEAD_GLUED.search(text)
    credits_line = _HCC_CREDITS_LINE.search(text)
    if glued:
        code, name, n_txt = glued.group(1), glued.group(2).strip(), glued.group(3)
        heading = glued.group(0)
        credit_excerpt = heading
    else:
        head = _HCC_HEAD.search(text)
        if not head or not credits_line:
            raise TranscriptionError("no Acalog CODE NBSP-dash heading with Credits:")
        code, name = head.group(1), head.group(2).strip()
        heading = head.group(0)
        n_txt = credits_line.group(1)
        credit_excerpt = credits_line.group(0)
    drafts: list[FieldDraft] = []
    _add(
        drafts,
        "course_id",
        code,
        heading,
        "acalog heading code",
        text,
        notes="Code split from NBSP-dashed heading. Code is not the name.",
    )
    _add(
        drafts,
        "course_name",
        name,
        heading,
        "acalog heading name",
        text,
        notes="Name split from heading. Credits: is not part of the name.",
    )
    _add(
        drafts,
        "course_credits",
        _num(n_txt),
        credit_excerpt,
        "Credits: line",
        text,
        raw=credit_excerpt,
        notes="Single printed credit; not expanded to min/max.",
    )
    lines = text.splitlines()
    hi = next(i for i, ln in enumerate(lines) if ln == heading)
    skip_prefixes = (
        "Lecture:",
        "Lab:",
        "Credits:",
        "Prerequisite(s):",
        "Corequisite(s):",
        "Add to ",
        "Share this",
        "Print ",
        "Help ",
        "Facebook ",
        "Tweet ",
    )
    for nxt in lines[hi + 1 :]:
        if nxt.endswith(" CEUs"):
            continue
        if nxt.startswith(skip_prefixes):
            continue
        if len(nxt) < 40:
            continue
        _add(drafts, "course_description", nxt, nxt, "description paragraph", text)
        break
    lecture = _HCC_LECTURE.search(text)
    if lecture:
        _add(
            drafts,
            "course_lecture_hours",
            _num(lecture.group(1)),
            lecture.group(0),
            "Lecture:",
            text,
            raw=lecture.group(0),
        )
    lab = _HCC_LAB.search(text)
    if lab:
        _add(
            drafts,
            "course_lab_hours",
            _num(lab.group(1)),
            lab.group(0),
            "Lab:",
            text,
            raw=lab.group(0),
        )
    ceu = _HCC_CEU.search(text)
    if ceu:
        _add(
            drafts,
            "course_ceu_credits",
            _num(ceu.group(1)),
            ceu.group(0),
            "CEUs",
            text,
            raw=ceu.group(0),
        )
    prereq = _HCC_PREREQ.search(text)
    if prereq:
        _add(
            drafts,
            "course_prerequisites",
            prereq.group(1),
            prereq.group(0),
            "Prerequisite(s) line",
            text,
            raw=prereq.group(0),
        )
    return drafts


def extract_units(text: str) -> list[FieldDraft]:
    """Acalog pages that glue N unit(s) onto the NBSP-dash heading and print hours lecture/lab."""
    m = _UNITS_HEAD.search(text)
    if not m:
        raise TranscriptionError("no Acalog CODE NBSP-dash nameN unit(s) heading")
    code, name, n_txt = m.group(1), m.group(2).strip(), m.group(3)
    heading = m.group(0)
    drafts: list[FieldDraft] = []
    _add(
        drafts,
        "course_id",
        code,
        heading,
        "acalog heading code",
        text,
        notes="Code split from NBSP-dashed heading. Code is not the name.",
    )
    _add(
        drafts,
        "course_name",
        name,
        heading,
        "acalog heading name",
        text,
        notes="Name split from glued nameN unit(s) heading. The digit before unit(s) is not part of the name.",
    )
    unit_ex = f"{n_txt} unit" if n_txt == "1" and heading.endswith("1 unit") else f"{n_txt} units"
    if unit_ex not in heading:
        unit_ex = f"{n_txt} units" if heading.endswith("units") else f"{n_txt} unit"
    _add(
        drafts,
        "course_credits",
        _num(n_txt),
        heading,
        "units in heading",
        text,
        raw=unit_ex,
        notes="Page prints unit(s), not the word Credits. Single printed value; not expanded to min/max.",
    )
    lecture_lab = _LECTURE_LAB.search(text)
    lab_only = _LAB_ONLY.search(text)
    if lecture_lab:
        _add(
            drafts,
            "course_lecture_hours",
            _num(lecture_lab.group(1)),
            lecture_lab.group(0),
            "hours lecture",
            text,
            raw=lecture_lab.group(0),
        )
        if lecture_lab.group(2):
            _add(
                drafts,
                "course_lab_hours",
                _num(lecture_lab.group(2)),
                lecture_lab.group(0),
                "hours lab",
                text,
                raw=lecture_lab.group(0),
            )
    elif lab_only:
        _add(
            drafts,
            "course_lab_hours",
            _num(lab_only.group(1)),
            lab_only.group(0),
            "hours lab",
            text,
            raw=lab_only.group(0),
        )
    lines = text.splitlines()
    hi = next(i for i, ln in enumerate(lines) if ln == heading)
    skip_prefixes = (
        "Add to ",
        "Share this",
        "Facebook ",
        "Tweet ",
        "Print ",
        "Help ",
        "Note:",
        "Recommended Preparation:",
        "Credit,",
        "Transfer ",
        "Prerequisite",
        "Corequisite",
    )
    for nxt in lines[hi + 1 :]:
        if nxt.startswith(skip_prefixes):
            continue
        if _LECTURE_LAB.match(nxt) or _LAB_ONLY.match(nxt):
            continue
        if len(nxt) < 40:
            continue
        _add(drafts, "course_description", nxt, nxt, "description paragraph", text)
        break
    return drafts


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


TEMPLATES = {
    "acalog_hcc_nbsp_credits": extract_hcc,
    "acalog_units_glued_hours": extract_units,
    "acalog_bergen_glued_credits": extract_bergen,
    "acalog_raritan_hours_credits": extract_raritan,
}
