"""30 Course-only sampling slots. HTML proof. Mix of NJ colleges."""

from __future__ import annotations

from pathlib import Path

from html_text import slug_url
from slots import Slot

_REPO = Path(__file__).absolute().parent.parent
_SRC = (_REPO / "golden_sets" / "sources" / "html").absolute()
_V4 = (_REPO / "handoff" / "golden_set_v4" / "snapshots").absolute()


def _html(stem: str) -> Path | None:
    nested = _SRC / f"{stem}.html" / f"{stem}.html"
    v4 = _V4 / f"{stem}.html"
    if nested.is_file():
        return nested
    if v4.is_file():
        return v4
    return None


def _slot(
    record_id: str,
    url: str,
    institution: str,
    family: str,
    template_id: str,
    page_id: str,
    retrieved_at: str | None = None,
) -> Slot:
    stem = slug_url(url)
    return Slot(
        record_id,
        "Course",
        url,
        institution,
        family,
        template_id,
        "1",
        page_id,
        _html(stem),
        retrieved_at,
    )


CLEAN = "clean_catalog_course_detail"
CD_B = "coursedog_brookdale_course_detail"
CD_M = "coursedog_mccc_course_detail"
CD_R = "coursedog_rcbc_course_detail"
AC_B = "acalog_bergen_glued_credits"
AC_R = "acalog_raritan_hours_credits"

ACCC = "Atlantic Cape Community College"
BCC = "Brookdale Community College"
MCCC = "Mercer County Community College"
RCBC = "Rowan College at Burlington County"
BERGEN = "Bergen Community College"
RVCC = "Raritan Valley Community College"
HCCC = "Hudson County Community College"

SLOTS: list[Slot] = [
    _slot("atlanticcape-engl101-course", "https://catalog.atlanticcape.edu/english/engl101", ACCC, "custom_html", CLEAN, "atlanticcape-engl101", "2026-08-23T00:00:00Z"),
    _slot("atlanticcape-engl102-course", "https://catalog.atlanticcape.edu/english/engl102", ACCC, "custom_html", CLEAN, "atlanticcape-engl102"),
    _slot("atlanticcape-psyc101-course", "https://catalog.atlanticcape.edu/psychology/psyc101", ACCC, "custom_html", CLEAN, "atlanticcape-psyc101"),
    _slot("atlanticcape-math122-course", "https://catalog.atlanticcape.edu/mathematics/math122", ACCC, "custom_html", CLEAN, "atlanticcape-math122"),
    _slot("atlanticcape-biol103-course", "https://catalog.atlanticcape.edu/biology/biol103", ACCC, "custom_html", CLEAN, "atlanticcape-biol103"),
    _slot("brookdale-engl121-course", "https://catalog.brookdalecc.edu/courses/ENGL121", BCC, "coursedog", CD_B, "brookdale-engl121"),
    _slot("brookdale-engl122-course", "https://catalog.brookdalecc.edu/courses/ENGL122", BCC, "coursedog", CD_B, "brookdale-engl122"),
    _slot("brookdale-hosp105-course", "https://catalog.brookdalecc.edu/courses/HOSP105", BCC, "coursedog", CD_B, "brookdale-hosp105"),
    _slot("brookdale-math131-course", "https://catalog.brookdalecc.edu/courses/MATH131", BCC, "coursedog", CD_B, "brookdale-math131"),
    _slot("brookdale-psyc106-course", "https://catalog.brookdalecc.edu/courses/PSYC106", BCC, "coursedog", CD_B, "brookdale-psyc106"),
    _slot("mccc-eng101-course", "https://catalog.mccc.edu/courses/ENG101", MCCC, "coursedog", CD_M, "mccc-eng101"),
    _slot("mccc-eng102-course", "https://catalog.mccc.edu/courses/ENG102", MCCC, "coursedog", CD_M, "mccc-eng102"),
    _slot("mccc-arc102-course", "https://catalog.mccc.edu/courses/ARC102", MCCC, "coursedog", CD_M, "mccc-arc102"),
    _slot("mccc-bus107-course", "https://catalog.mccc.edu/courses/BUS107", MCCC, "coursedog", CD_M, "mccc-bus107"),
    _slot("mccc-mat146-course", "https://catalog.mccc.edu/courses/MAT146", MCCC, "coursedog", CD_M, "mccc-mat146"),
    _slot("rcbc-eng101-course", "https://catalog.rcbc.edu/courses/ENG101", RCBC, "coursedog", CD_R, "rcbc-eng101"),
    _slot("rcbc-eng102-course", "https://catalog.rcbc.edu/courses/ENG102", RCBC, "coursedog", CD_R, "rcbc-eng102"),
    _slot("rcbc-psy101-course", "https://catalog.rcbc.edu/courses/PSY101", RCBC, "coursedog", CD_R, "rcbc-psy101"),
    _slot("rcbc-mth107-course", "https://catalog.rcbc.edu/courses/MTH107", RCBC, "coursedog", CD_R, "rcbc-mth107"),
    _slot("rcbc-spe101-course", "https://catalog.rcbc.edu/courses/SPE101", RCBC, "coursedog", CD_R, "rcbc-spe101"),
    _slot("bergen-eng-101-course", "https://catalog.bergen.edu/preview_course_nopop.php?catoid=13&coid=19370", BERGEN, "acalog", AC_B, "bergen-eng-101"),
    _slot("bergen-eng-201-course", "https://catalog.bergen.edu/preview_course_nopop.php?catoid=13&coid=19371", BERGEN, "acalog", AC_B, "bergen-eng-201"),
    _slot("bergen-acc-100-course", "https://catalog.bergen.edu/preview_course_nopop.php?catoid=13&coid=18422", BERGEN, "acalog", AC_B, "bergen-acc-100"),
    _slot("bergen-bio-101-course", "https://catalog.bergen.edu/preview_course_nopop.php?catoid=13&coid=18500", BERGEN, "acalog", AC_B, "bergen-bio-101"),
    _slot("bergen-mat-160-course", "https://catalog.bergen.edu/preview_course_nopop.php?catoid=13&coid=19015", BERGEN, "acalog", AC_B, "bergen-mat-160"),
    _slot("raritan-biol-124-course", "https://catalog.raritanval.edu/preview_course_nopop.php?catoid=15&coid=14054", RVCC, "acalog", AC_R, "raritan-biol-124"),
    _slot("hccc-eng101-course", "https://catalog.hccc.edu/courses/ENG101", HCCC, "coursedog", CD_R, "hccc-eng101"),
    _slot("hccc-eng102-course", "https://catalog.hccc.edu/courses/ENG102", HCCC, "coursedog", CD_R, "hccc-eng102"),
    _slot("hccc-psy101-course", "https://catalog.hccc.edu/courses/PSY101", HCCC, "coursedog", CD_R, "hccc-psy101"),
    _slot("hccc-mat110-course", "https://catalog.hccc.edu/courses/MAT110", HCCC, "coursedog", CD_R, "hccc-mat110"),
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
