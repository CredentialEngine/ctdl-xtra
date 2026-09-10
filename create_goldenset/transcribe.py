"""Copy source fields from normalized freeze text. Never invent values."""

from __future__ import annotations

import re

from record import locator
from active import active_slots
from slots import Slot
from transcribe_lib import FieldDraft, TranscriptionError


def transcribe_slot(slot: Slot, text: str) -> list[FieldDraft]:
    from config import SLOTS_NAME

    if SLOTS_NAME in {"courses_30", "dynamic"}:
        from transcribe_courses import extract_course

        drafts = extract_course(slot, text)
    else:
        fn = EXTRACTORS[slot.record_id]
        drafts = fn(text)
    if not drafts:
        raise TranscriptionError(f"{slot.record_id}: no fields transcribed")
    for d in drafts:
        if d.excerpt not in text:
            raise TranscriptionError(f"{slot.record_id}: excerpt missing {d.excerpt[:160]!r}")
    return drafts


def entities_for_page(slot: Slot, text: str) -> list[dict]:
    same = [s for s in active_slots() if s.stem == slot.stem]
    return [
        {
            "provisional_id": s.record_id,
            "entity_type": s.entity_type,
            "locator": locator("whole_document", s.record_id),
        }
        for s in same
    ]


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


def _line_after(text: str, label: str) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == label:
            for nxt in lines[i + 1 :]:
                if nxt.strip():
                    return nxt
    raise TranscriptionError(f"no line after {label!r}")


def atlanticcape_engl101(text: str) -> list[FieldDraft]:
    lines = text.splitlines()
    prereq_i = lines.index("Prerequisites")
    desc = lines[prereq_i - 1]
    prereq = lines[prereq_i + 1]
    credits_ex = "Credits\n3"
    return [
        _f("src_001", "course_id", "ENGL101", "ENGL101:", "h1 code", notes="Split from ENGL101: / Composition I heading. Code is not the name."),
        _f("src_002", "course_name", "Composition I", "Composition I", "h1 name"),
        _f("src_003", "course_description", desc, desc, "description paragraph"),
        _f("src_004", "course_credits", 3, credits_ex, "Credits field", raw=credits_ex, notes="Lossless parse of printed 3. Not expanded to min/max."),
        _f("src_005", "course_prerequisites", prereq, prereq, "Prerequisites field"),
    ]


def atlanticcape_flti_lp(text: str) -> list[FieldDraft]:
    name = "Flight Instructor"
    desc = next(
        ln for ln in text.splitlines() if ln.startswith("The Flight Instructor Certificate provides")
    )
    return [
        _f("src_001", "learning_program_name", name, name, "program heading", occ=_occ(text, name)),
        _f("src_002", "learning_program_description", desc, desc, "program description"),
    ]


def _comp(text: str, value: str) -> list[FieldDraft]:
    return [_f("src_001", "competency_text", value, value, "Upon completion list item", occ=_occ(text, value))]


def atlanticcape_flti_private(text: str) -> list[FieldDraft]:
    return _comp(text, "Obtain\u00a0the FAA Private Pilot Certificate;")


def atlanticcape_flti_instrument(text: str) -> list[FieldDraft]:
    return _comp(text, "Obtain the FAA Instrument Rating;")


def atlanticcape_flti_commercial(text: str) -> list[FieldDraft]:
    return _comp(text, "Obtain the FAA Commercial Pilot Certificate;")


def atlanticcape_flti_cfi(text: str) -> list[FieldDraft]:
    return _comp(text, "Obtain the FAA Flight Instructor Certificate.")


def brookdale_hospm_lp(text: str) -> list[FieldDraft]:
    title = "Hospitality Management Program, A.S."
    title_ex = "Program Title\nHospitality Management Program, A.S."
    code_ex = "Program Code\nHOSPM"
    desc = _line_after(text, "Program Description")
    return [
        _f("src_001", "learning_program_id", "HOSPM", code_ex, "Program Code", raw="HOSPM"),
        _f("src_002", "learning_program_name", title, title_ex, "Program Title", raw=title),
        _f("src_003", "learning_program_description", desc, desc, "Program Description"),
    ]


def brookdale_hospm_cred(text: str) -> list[FieldDraft]:
    title = "Hospitality Management Program, A.S."
    title_ex = "Program Title\nHospitality Management Program, A.S."
    desc = _line_after(text, "Program Description")
    return [
        _f("src_001", "credential_name", title, title_ex, "Program Title / award", raw=title),
        _f("src_002", "credential_description", desc, desc, "Program Description"),
    ]


def brookdale_hospm_link(text: str) -> list[FieldDraft]:
    title = "Hospitality Management Program, A.S."
    title_ex = "Program Title\nHospitality Management Program, A.S."
    return [_f("src_001", "relationship_heading", title, title_ex, "Program Title names program and A.S.", raw=title)]


def mccc_arch_lp(text: str) -> list[FieldDraft]:
    heading = "ARCH.AS - Architecture"
    desc = _line_after(text, "Description")
    return [
        _f("src_001", "learning_program_id", "ARCH.AS", heading, "program heading code", raw="ARCH.AS", occ=_occ(text, heading)),
        _f(
            "src_002",
            "learning_program_name",
            "Architecture",
            heading,
            "program heading name",
            occ=_occ(text, heading),
            notes="Split from explicit CODE - Name heading. Code is not the name.",
        ),
        _f("src_003", "learning_program_description", desc, desc, "Description first paragraph"),
    ]


def mccc_arch_cred(text: str) -> list[FieldDraft]:
    name = "Associate in Science - Architecture"
    return [_f("src_001", "credential_name", name, name, "degree heading")]


def mccc_cf(text: str) -> list[FieldDraft]:
    name = "PROGRAM OUTCOMES"
    return [
        _f(
            "src_001",
            "competency_framework_name",
            name,
            name,
            "PROGRAM OUTCOMES heading",
            occ=_occ(text, name),
            notes="Heading only. Outcome bullets are out of pack scope.",
        )
    ]


def raritan_lp(text: str, heading: str) -> list[FieldDraft]:
    desc = None
    lines = text.splitlines()
    i = lines.index(heading)
    for nxt in lines[i + 1 :]:
        if nxt.startswith("The ") or nxt.startswith("This "):
            desc = nxt
            break
    if not desc:
        raise TranscriptionError(f"no description after {heading!r}")
    return [
        _f("src_001", "learning_program_name", heading, heading, "acalog h1", occ=_occ(text, heading)),
        _f("src_002", "learning_program_description", desc, desc, "first program paragraph"),
    ]


def raritan_cred(text: str, heading: str) -> list[FieldDraft]:
    fields = raritan_lp(text, heading)
    return [
        _f("src_001", "credential_name", heading, heading, "acalog h1", occ=_occ(text, heading)),
        _f("src_002", "credential_description", fields[1].value, fields[1].excerpt, "first award/program paragraph"),
    ]


def raritan_link(text: str, heading: str) -> list[FieldDraft]:
    return [
        _f(
            "src_001",
            "relationship_heading",
            heading,
            heading,
            "acalog h1 names program and award",
            occ=_occ(text, heading),
        )
    ]


def brookdale_course(text: str, code: str) -> list[FieldDraft]:
    lines = text.splitlines()
    try:
        i = lines.index(code)
    except ValueError as exc:
        raise TranscriptionError(f"code line missing {code}") from exc
    # Prefer the line immediately before the code if it is the long title.
    name = lines[i - 1]
    if name in {"Download as PDF", "Courses/"}:
        name = lines[i + 2] if lines[i + 1] == "Download as PDF" else lines[i + 1]
    desc = _line_after(text, "Course Description")
    # Credit Hours / Min / 3
    ch = lines.index("Credit Hours")
    if lines[ch + 1].strip() != "Min":
        raise TranscriptionError("expected Credit Hours / Min / N")
    n_txt = lines[ch + 2].strip()
    number = float(n_txt) if "." in n_txt else int(n_txt)
    credits_ex = f"Credit Hours\nMin\n{n_txt}"
    return [
        _f("src_001", "course_id", code, code, "course code line", occ=_occ(text, code)),
        _f("src_002", "course_name", name, name, "course title", occ=_occ(text, name), notes="Name is the printed title, not the code."),
        _f("src_003", "course_description", desc, desc, "Course Description"),
        _f(
            "src_004",
            "course_credits",
            number,
            credits_ex,
            "Credit Hours Min",
            raw=credits_ex,
            notes="Page prints Min only. Single value, not an invented max.",
        ),
    ]


def rcbc_course(text: str, code: str, name: str) -> list[FieldDraft]:
    desc = _line_after(text, "Description")
    lines = text.splitlines()
    i = lines.index("(Credit Hours) Min")
    n_txt = lines[i + 1].strip()
    number = float(n_txt) if "." in n_txt else int(n_txt)
    credits_ex = f"(Credit Hours) Min\n{n_txt}"
    return [
        _f("src_001", "course_id", code, code, "course code line", occ=_occ(text, code)),
        _f("src_002", "course_name", name, name, "Course Long Title", occ=_occ(text, name), notes="Name is the printed title, not the code."),
        _f("src_003", "course_description", desc, desc, "Description field"),
        _f(
            "src_004",
            "course_credits",
            number,
            credits_ex,
            "Credit Hours Min",
            raw=credits_ex,
            notes="Page prints Min only. Single value, not an invented max.",
        ),
    ]


def mccc_eng101(text: str) -> list[FieldDraft]:
    name = "English Composition I"
    desc = _line_after(text, "Course Description")
    lines = text.splitlines()
    i = lines.index("Credit Hours Min")
    n_txt = lines[i + 1].strip()
    number = float(n_txt) if "." in n_txt else int(n_txt)
    credits_ex = f"Credit Hours Min\n{n_txt}"
    return [
        _f(
            "src_001",
            "course_id",
            "ENG101",
            "English Composition I\nENG101\nEnglish Composition I",
            "course heading code",
            raw="ENG101",
        ),
        _f("src_002", "course_name", name, name, "course title", occ=_occ(text, name), notes="Name is the printed title, not the code."),
        _f("src_003", "course_description", desc, desc, "Course Description"),
        _f(
            "src_004",
            "course_credits",
            number,
            credits_ex,
            "Credit Hours Min",
            raw=credits_ex,
            notes="Page prints Min only. Single value, not an invented max.",
        ),
    ]


def acalog_course(text: str) -> list[FieldDraft]:
    pat = re.compile(r"^([A-Z]{2,4}-\d{3}) (.+?)(\d+) Credit\(s\)$", re.M)
    m = pat.search(text)
    if not m:
        raise TranscriptionError("no Acalog CODE NameN Credit(s) heading")
    code, name, n_txt = m.group(1), m.group(2), m.group(3)
    heading = m.group(0)
    number = float(n_txt) if "." in n_txt else int(n_txt)
    # description: first long line after heading that looks like a sentence
    lines = text.splitlines()
    hi = next(i for i, ln in enumerate(lines) if ln == heading)
    desc = None
    for nxt in lines[hi + 1 :]:
        if nxt.startswith("This ") or nxt.startswith("The ") or (len(nxt) > 60 and "Hour(s)" not in nxt):
            desc = nxt
            break
    prereq = None
    for nxt in lines[hi + 1 :]:
        if nxt.startswith("Prerequisite(s):"):
            prereq = nxt[len("Prerequisite(s):") :].strip()
            prereq_ex = nxt
            break
    drafts = [
        _f("src_001", "course_id", code, heading, "acalog heading code+name+credits", notes="Code split from glued heading. Code is not the name."),
        _f("src_002", "course_name", name, heading, "acalog heading name", notes="Name split from glued CODE NameN Credit(s) heading."),
        _f(
            "src_003",
            "course_credits",
            number,
            f"{n_txt} Credit(s)",
            "Credit(s) in heading",
            raw=f"{n_txt} Credit(s)",
            notes="Single printed credit; not expanded to min/max.",
            occ=_occ(text, f"{n_txt} Credit(s)"),
        ),
    ]
    if desc:
        drafts.append(_f(f"src_{len(drafts)+1:03d}", "course_description", desc, desc, "description paragraph"))
    if prereq:
        drafts.append(
            _f(
                f"src_{len(drafts)+1:03d}",
                "course_prerequisites",
                prereq,
                prereq_ex,
                "Prerequisite(s) line",
                raw=prereq_ex,
            )
        )
    return drafts


MEDICAL = "Medical Assistant, Certificate"
AUTO = "Automotive Technology, Associate of Applied Science"

EXTRACTORS = {
    "atlanticcape-engl101-course": atlanticcape_engl101,
    "atlanticcape-flti-learning-program": atlanticcape_flti_lp,
    "atlanticcape-flti-comp-private-pilot": atlanticcape_flti_private,
    "atlanticcape-flti-comp-instrument": atlanticcape_flti_instrument,
    "atlanticcape-flti-comp-commercial": atlanticcape_flti_commercial,
    "atlanticcape-flti-comp-cfi": atlanticcape_flti_cfi,
    "brookdale-engl121-course": lambda t: brookdale_course(t, "ENGL121"),
    "brookdale-engl122-course": lambda t: brookdale_course(t, "ENGL122"),
    "brookdale-hospm-learning-program": brookdale_hospm_lp,
    "brookdale-hospm-credential": brookdale_hospm_cred,
    "brookdale-hospm-link-results-in-credential": brookdale_hospm_link,
    "mccc-eng101-course": mccc_eng101,
    "mccc-arch-learning-program": mccc_arch_lp,
    "mccc-arch-credential": mccc_arch_cred,
    "mccc-arch-competency-framework": mccc_cf,
    "mccc-bus-stud-entr-competency-framework": mccc_cf,
    "mccc-cmptr-da-cert-competency-framework": mccc_cf,
    "rcbc-eng101-course": lambda t: rcbc_course(t, "ENG-101", "College Composition I"),
    "rcbc-eng102-course": lambda t: rcbc_course(t, "ENG-102", "College Composition II"),
    "raritan-medical-assistant-learning-program": lambda t: raritan_lp(t, MEDICAL),
    "raritan-medical-assistant-credential": lambda t: raritan_cred(t, MEDICAL),
    "raritan-medical-assistant-link-results-in-credential": lambda t: raritan_link(t, MEDICAL),
    "raritan-automotive-learning-program": lambda t: raritan_lp(t, AUTO),
    "raritan-automotive-credential": lambda t: raritan_cred(t, AUTO),
    "raritan-automotive-link-results-in-credential": lambda t: raritan_link(t, AUTO),
    "bergen-eng-101-course": acalog_course,
    "bergen-eng-201-course": acalog_course,
    "bergen-acc-100-course": acalog_course,
    "bergen-bio-101-course": acalog_course,
    "bergen-mat-160-course": acalog_course,
}
