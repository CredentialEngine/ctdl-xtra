"""The five catalogs in scope (spec §1.1): display name, platform, logo, and where their v2 inputs are."""

from __future__ import annotations

from .errors import UserError

CATALOGS = {
    "avc-elumenapp-com-catalog-2026-27-welcome": {
        "short": "avc", "course_code_pattern": r"\b[A-Z]{2,5} ?\d{3}[A-Z]?\b",
        "name": "AVC", "institution": "Antelope Valley College", "platform": "eLumen",
        "logo": "avc.png"},
    "ccsf-curricunet-com-catalog": {
        "short": "ccsf", "course_code_pattern": r"\b[A-Z]{2,5} \d{1,3}[A-Z]{0,2}\b",
        "name": "CCSF", "institution": "City College of San Francisco", "platform": "CurricUNET",
        "logo": "ccsf.svg"},
    "catalog-marshall-edu": {
        "short": "marshall", "course_code_pattern": r"\b[A-Z]{2,4} \d{3}[A-Z]?\b",
        "name": "Marshall", "institution": "Marshall University", "platform": "CourseLeaf",
        "logo": "marshall.svg"},
    "catalog-ualr-edu": {
        "short": "ualr", "course_code_pattern": r"\b[A-Z]{2,5} \d{4,5}\b",
        "name": "UALR", "institution": "University of Arkansas at Little Rock", "platform": "Acalog",
        "logo": "ualr.svg"},
    "catalog-wvu-edu": {
        "short": "wvu", "course_code_pattern": r"\b[A-Z]{2,4} \d{3}[A-Z]?\b",
        "name": "WVU", "institution": "West Virginia University", "platform": "CourseLeaf",
        "logo": "wvu.png"},
}

#: Catalogs added from the picker that the Studio knows more about than their crawl says: a short name for the score
#: tables and the address, and the classes the catalog has none of (`not_sources`: the home page says "Not a
#: LearningProgram source"). Unlike CATALOGS, these are only shown once they're in the manifest.
KNOWN = {
    "training-uark-edu-portal-training": {
        "short": "uark", "name": "UARK", "institution": "University of Arkansas Professional and Workforce Development",
        "platform": "", "logo": None, "not_sources": ("learningprogram",)},
}


def resolve(name: str | None) -> str:
    """Folder name for a catalog given its folder name or short name."""
    if not name:
        raise UserError("--catalog is required")
    if name in CATALOGS:
        return name
    if name in KNOWN:
        return name
    for folder, meta in (CATALOGS | KNOWN).items():
        if meta["short"] == name.lower():
            return folder
    return name  # an unknown catalog folder is allowed (it just has no logo or display name)


def info(catalog: str) -> dict:
    return CATALOGS.get(catalog) or KNOWN.get(catalog) or {"short": catalog, "name": catalog, "institution": catalog,
                                                           "platform": "", "logo": None}
