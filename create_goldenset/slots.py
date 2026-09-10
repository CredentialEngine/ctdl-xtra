"""v4 candidate sampling slots. Discovery plan, not signed gold."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from html_text import slug_url

_REPO = Path(__file__).absolute().parent.parent
_SRC = (_REPO / "golden_sets" / "sources" / "html").absolute()


@dataclass(frozen=True)
class Slot:
    record_id: str
    entity_type: str
    requested_url: str
    institution_name: str
    source_family: str
    template_id: str
    template_version: str
    page_id: str
    copy_html: Path | None
    retrieved_at: str | None
    multi_entity_bundle: bool = False
    notes: str = ""

    @property
    def stem(self) -> str:
        return slug_url(self.requested_url)


def _html(stem: str) -> Path:
    return _SRC / f"{stem}.html" / f"{stem}.html"


# Copied freezes keep the original golden-set retrieval day as midnight UTC.
_COPY_TS = {
    "catalog-atlanticcape-edu-english-engl101": "2026-08-23T00:00:00Z",
    "catalog-atlanticcape-edu-aviation-flight-instructor": "2026-08-23T00:00:00Z",
    "catalog-brookdalecc-edu-programs-HOSPM": "2026-08-23T00:00:00Z",
    "catalog-mccc-edu-programs-ARCH-AS": "2026-08-23T00:00:00Z",
    "catalog-mccc-edu-programs-BUS-STUD-ENTR-AAS": "2026-08-23T00:00:00Z",
    "catalog-raritanval-edu-preview-program-php-catoid-15-poid-1917-returnto-1319": "2026-08-28T00:00:00Z",
    "catalog-raritanval-edu-preview-program-php-catoid-15-poid-1858-returnto-1319": "2026-08-28T00:00:00Z",
}

CLEAN = "clean_catalog_detail"
CD_COURSE = "coursedog_course_detail"
CD_PROG = "coursedog_program_detail"
AC_COURSE = "acalog_preview_course_nopop"
AC_PROG = "acalog_preview_program"

SLOTS: list[Slot] = [
    Slot(
        "atlanticcape-engl101-course",
        "Course",
        "https://catalog.atlanticcape.edu/english/engl101",
        "Atlantic Cape Community College",
        "custom_html",
        CLEAN,
        "1",
        "atlanticcape-engl101",
        _html("catalog-atlanticcape-edu-english-engl101"),
        _COPY_TS["catalog-atlanticcape-edu-english-engl101"],
    ),
    Slot(
        "atlanticcape-flti-learning-program",
        "LearningProgram",
        "https://catalog.atlanticcape.edu/aviation/flight-instructor",
        "Atlantic Cape Community College",
        "custom_html",
        CLEAN,
        "1",
        "atlanticcape-flti",
        _html("catalog-atlanticcape-edu-aviation-flight-instructor"),
        _COPY_TS["catalog-atlanticcape-edu-aviation-flight-instructor"],
        multi_entity_bundle=True,
        notes="FLTI page is the declared multi-entity competency bundle: 1 program + 4 outcomes.",
    ),
    Slot(
        "atlanticcape-flti-comp-private-pilot",
        "Competency",
        "https://catalog.atlanticcape.edu/aviation/flight-instructor",
        "Atlantic Cape Community College",
        "custom_html",
        CLEAN,
        "1",
        "atlanticcape-flti",
        _html("catalog-atlanticcape-edu-aviation-flight-instructor"),
        _COPY_TS["catalog-atlanticcape-edu-aviation-flight-instructor"],
        multi_entity_bundle=True,
    ),
    Slot(
        "atlanticcape-flti-comp-instrument",
        "Competency",
        "https://catalog.atlanticcape.edu/aviation/flight-instructor",
        "Atlantic Cape Community College",
        "custom_html",
        CLEAN,
        "1",
        "atlanticcape-flti",
        _html("catalog-atlanticcape-edu-aviation-flight-instructor"),
        _COPY_TS["catalog-atlanticcape-edu-aviation-flight-instructor"],
        multi_entity_bundle=True,
    ),
    Slot(
        "atlanticcape-flti-comp-commercial",
        "Competency",
        "https://catalog.atlanticcape.edu/aviation/flight-instructor",
        "Atlantic Cape Community College",
        "custom_html",
        CLEAN,
        "1",
        "atlanticcape-flti",
        _html("catalog-atlanticcape-edu-aviation-flight-instructor"),
        _COPY_TS["catalog-atlanticcape-edu-aviation-flight-instructor"],
        multi_entity_bundle=True,
    ),
    Slot(
        "atlanticcape-flti-comp-cfi",
        "Competency",
        "https://catalog.atlanticcape.edu/aviation/flight-instructor",
        "Atlantic Cape Community College",
        "custom_html",
        CLEAN,
        "1",
        "atlanticcape-flti",
        _html("catalog-atlanticcape-edu-aviation-flight-instructor"),
        _COPY_TS["catalog-atlanticcape-edu-aviation-flight-instructor"],
        multi_entity_bundle=True,
    ),
    Slot(
        "brookdale-engl121-course",
        "Course",
        "https://catalog.brookdalecc.edu/courses/ENGL121",
        "Brookdale Community College",
        "coursedog",
        CD_COURSE,
        "1",
        "brookdale-engl121",
        None,
        None,
    ),
    Slot(
        "brookdale-engl122-course",
        "Course",
        "https://catalog.brookdalecc.edu/courses/ENGL122",
        "Brookdale Community College",
        "coursedog",
        CD_COURSE,
        "1",
        "brookdale-engl122",
        None,
        None,
    ),
    Slot(
        "brookdale-hospm-learning-program",
        "LearningProgram",
        "https://catalog.brookdalecc.edu/programs/HOSPM",
        "Brookdale Community College",
        "coursedog",
        CD_PROG,
        "1",
        "brookdale-hospm",
        _html("catalog-brookdalecc-edu-programs-HOSPM"),
        _COPY_TS["catalog-brookdalecc-edu-programs-HOSPM"],
    ),
    Slot(
        "brookdale-hospm-credential",
        "Credential",
        "https://catalog.brookdalecc.edu/programs/HOSPM",
        "Brookdale Community College",
        "coursedog",
        CD_PROG,
        "1",
        "brookdale-hospm",
        _html("catalog-brookdalecc-edu-programs-HOSPM"),
        _COPY_TS["catalog-brookdalecc-edu-programs-HOSPM"],
    ),
    Slot(
        "brookdale-hospm-link-results-in-credential",
        "Link",
        "https://catalog.brookdalecc.edu/programs/HOSPM",
        "Brookdale Community College",
        "coursedog",
        CD_PROG,
        "1",
        "brookdale-hospm",
        _html("catalog-brookdalecc-edu-programs-HOSPM"),
        _COPY_TS["catalog-brookdalecc-edu-programs-HOSPM"],
    ),
    Slot(
        "mccc-eng101-course",
        "Course",
        "https://catalog.mccc.edu/courses/ENG101",
        "Mercer County Community College",
        "coursedog",
        CD_COURSE,
        "1",
        "mccc-eng101",
        None,
        None,
    ),
    Slot(
        "mccc-arch-learning-program",
        "LearningProgram",
        "https://catalog.mccc.edu/programs/ARCH-AS",
        "Mercer County Community College",
        "coursedog",
        CD_PROG,
        "1",
        "mccc-arch",
        _html("catalog-mccc-edu-programs-ARCH-AS"),
        _COPY_TS["catalog-mccc-edu-programs-ARCH-AS"],
    ),
    Slot(
        "mccc-arch-credential",
        "Credential",
        "https://catalog.mccc.edu/programs/ARCH-AS",
        "Mercer County Community College",
        "coursedog",
        CD_PROG,
        "1",
        "mccc-arch",
        _html("catalog-mccc-edu-programs-ARCH-AS"),
        _COPY_TS["catalog-mccc-edu-programs-ARCH-AS"],
    ),
    Slot(
        "mccc-arch-competency-framework",
        "CompetencyFramework",
        "https://catalog.mccc.edu/programs/ARCH-AS",
        "Mercer County Community College",
        "coursedog",
        CD_PROG,
        "1",
        "mccc-arch",
        _html("catalog-mccc-edu-programs-ARCH-AS"),
        _COPY_TS["catalog-mccc-edu-programs-ARCH-AS"],
        notes="Framework title only (PROGRAM OUTCOMES). Outcome statements are out of pack scope.",
    ),
    Slot(
        "mccc-bus-stud-entr-competency-framework",
        "CompetencyFramework",
        "https://catalog.mccc.edu/programs/BUS-STUD-ENTR-AAS",
        "Mercer County Community College",
        "coursedog",
        CD_PROG,
        "1",
        "mccc-bus-stud-entr",
        _html("catalog-mccc-edu-programs-BUS-STUD-ENTR-AAS"),
        _COPY_TS["catalog-mccc-edu-programs-BUS-STUD-ENTR-AAS"],
        notes="Framework title only (PROGRAM OUTCOMES).",
    ),
    Slot(
        "mccc-cmptr-da-cert-competency-framework",
        "CompetencyFramework",
        "https://catalog.mccc.edu/programs/CMPTR.DA.CERT",
        "Mercer County Community College",
        "coursedog",
        CD_PROG,
        "1",
        "mccc-cmptr-da-cert",
        None,
        None,
        notes="Framework title only (PROGRAM OUTCOMES).",
    ),
    Slot(
        "rcbc-eng101-course",
        "Course",
        "https://catalog.rcbc.edu/courses/ENG101",
        "Rowan College at Burlington County",
        "coursedog",
        CD_COURSE,
        "1",
        "rcbc-eng101",
        None,
        None,
    ),
    Slot(
        "rcbc-eng102-course",
        "Course",
        "https://catalog.rcbc.edu/courses/ENG102",
        "Rowan College at Burlington County",
        "coursedog",
        CD_COURSE,
        "1",
        "rcbc-eng102",
        None,
        None,
    ),
    Slot(
        "raritan-medical-assistant-learning-program",
        "LearningProgram",
        "https://catalog.raritanval.edu/preview_program.php?catoid=15&poid=1917&returnto=1319",
        "Raritan Valley Community College",
        "acalog",
        AC_PROG,
        "1",
        "raritan-medical-assistant",
        _html("catalog-raritanval-edu-preview-program-php-catoid-15-poid-1917-returnto-1319"),
        _COPY_TS["catalog-raritanval-edu-preview-program-php-catoid-15-poid-1917-returnto-1319"],
    ),
    Slot(
        "raritan-medical-assistant-credential",
        "Credential",
        "https://catalog.raritanval.edu/preview_program.php?catoid=15&poid=1917&returnto=1319",
        "Raritan Valley Community College",
        "acalog",
        AC_PROG,
        "1",
        "raritan-medical-assistant",
        _html("catalog-raritanval-edu-preview-program-php-catoid-15-poid-1917-returnto-1319"),
        _COPY_TS["catalog-raritanval-edu-preview-program-php-catoid-15-poid-1917-returnto-1319"],
    ),
    Slot(
        "raritan-medical-assistant-link-results-in-credential",
        "Link",
        "https://catalog.raritanval.edu/preview_program.php?catoid=15&poid=1917&returnto=1319",
        "Raritan Valley Community College",
        "acalog",
        AC_PROG,
        "1",
        "raritan-medical-assistant",
        _html("catalog-raritanval-edu-preview-program-php-catoid-15-poid-1917-returnto-1319"),
        _COPY_TS["catalog-raritanval-edu-preview-program-php-catoid-15-poid-1917-returnto-1319"],
    ),
    Slot(
        "raritan-automotive-learning-program",
        "LearningProgram",
        "https://catalog.raritanval.edu/preview_program.php?catoid=15&poid=1858&returnto=1319",
        "Raritan Valley Community College",
        "acalog",
        AC_PROG,
        "1",
        "raritan-automotive",
        _html("catalog-raritanval-edu-preview-program-php-catoid-15-poid-1858-returnto-1319"),
        _COPY_TS["catalog-raritanval-edu-preview-program-php-catoid-15-poid-1858-returnto-1319"],
    ),
    Slot(
        "raritan-automotive-credential",
        "Credential",
        "https://catalog.raritanval.edu/preview_program.php?catoid=15&poid=1858&returnto=1319",
        "Raritan Valley Community College",
        "acalog",
        AC_PROG,
        "1",
        "raritan-automotive",
        _html("catalog-raritanval-edu-preview-program-php-catoid-15-poid-1858-returnto-1319"),
        _COPY_TS["catalog-raritanval-edu-preview-program-php-catoid-15-poid-1858-returnto-1319"],
    ),
    Slot(
        "raritan-automotive-link-results-in-credential",
        "Link",
        "https://catalog.raritanval.edu/preview_program.php?catoid=15&poid=1858&returnto=1319",
        "Raritan Valley Community College",
        "acalog",
        AC_PROG,
        "1",
        "raritan-automotive",
        _html("catalog-raritanval-edu-preview-program-php-catoid-15-poid-1858-returnto-1319"),
        _COPY_TS["catalog-raritanval-edu-preview-program-php-catoid-15-poid-1858-returnto-1319"],
    ),
    Slot(
        "bergen-eng-101-course",
        "Course",
        "https://catalog.bergen.edu/preview_course_nopop.php?catoid=13&coid=19370",
        "Bergen Community College",
        "acalog",
        AC_COURSE,
        "1",
        "bergen-eng-101",
        None,
        None,
    ),
    Slot(
        "bergen-eng-201-course",
        "Course",
        "https://catalog.bergen.edu/preview_course_nopop.php?catoid=13&coid=19371",
        "Bergen Community College",
        "acalog",
        AC_COURSE,
        "1",
        "bergen-eng-201",
        None,
        None,
    ),
    Slot(
        "bergen-acc-100-course",
        "Course",
        "https://catalog.bergen.edu/preview_course_nopop.php?catoid=13&coid=18422",
        "Bergen Community College",
        "acalog",
        AC_COURSE,
        "1",
        "bergen-acc-100",
        None,
        None,
    ),
    Slot(
        "bergen-bio-101-course",
        "Course",
        "https://catalog.bergen.edu/preview_course_nopop.php?catoid=13&coid=18500",
        "Bergen Community College",
        "acalog",
        AC_COURSE,
        "1",
        "bergen-bio-101",
        None,
        None,
    ),
    Slot(
        "bergen-mat-160-course",
        "Course",
        "https://catalog.bergen.edu/preview_course_nopop.php?catoid=13&coid=19015",
        "Bergen Community College",
        "acalog",
        AC_COURSE,
        "1",
        "bergen-mat-160",
        None,
        None,
    ),
]


def unique_pages() -> list[Slot]:
    seen: set[str] = set()
    out: list[Slot] = []
    for slot in SLOTS:
        if slot.stem in seen:
            continue
        seen.add(slot.stem)
        out.append(slot)
    return out
