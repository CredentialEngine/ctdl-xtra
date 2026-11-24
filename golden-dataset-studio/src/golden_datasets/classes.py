"""The CTDL classes the Studio builds golden datasets for (LearningProgram spec, approved items 1–6).

Course was the first and LearningProgram the second; more follow. Each class has:
- a slug, used in paths, URLs and `--class` (`course`, `learningprogram`);
- its display name, the CTDL class name with no space (`Course`, `LearningProgram`);
- its rule id prefix (`course-`, `learningprogram-`);
- its tab in the sheet "xTRA: Learning Opportunity BU Template" (`<Name> Properties`), synced into
  `properties/<slug>.csv`;
- its xtra `entity_type`, and the CTDL type xtra's extraction files carry (`ceterms:Course`);
- its required properties (the sheet has no Required column yet: asks-jared-jeanne.md, ask 9);
- the prefix of a generated External Identifier, `{type}-{normalized name}` (issue #368; ask 3).

Adding a class is adding an entry here and a tab to the sheet.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .errors import UserError

#: The CTDL-required properties every class starts from: External Identifier, Learning Type (the Studio's own
#: constant column, no path), Name, Description, Subject Webpage, Life Cycle Status and Language.
REQUIRED = ("ceterms:identifier", "", "ceterms:name", "ceterms:description", "ceterms:subjectWebpage",
            "ceterms:lifeCycleStatusType", "ceterms:inLanguage")
ENV = "GOLDEN_DATASETS_CLASS"


@dataclass(frozen=True)
class CtdlClass:
    slug: str            # course
    name: str            # Course
    rule_prefix: str     # course-
    sheet_tab: str       # Course Properties
    entity_type: str     # Course (xtra's records/)
    ctdl_type: str       # ceterms:Course (xtra's extraction_report/ files)
    id_prefix: str       # course (a generated External Identifier: course-<normalized name>)
    required: tuple[str, ...] = REQUIRED


CLASSES: dict[str, CtdlClass] = {c.slug: c for c in (
    CtdlClass("course", "Course", "course-", "Course Properties", "Course", "ceterms:Course", "course"),
    CtdlClass("learningprogram", "LearningProgram", "learningprogram-", "Learning Program Properties",
              "LearningProgram", "ceterms:LearningProgram", "program"),
)}
SLUGS = tuple(CLASSES)


def get(slug: str | CtdlClass) -> CtdlClass:
    """A class by its slug (or its name, any case: `LearningProgram`)."""
    if isinstance(slug, CtdlClass):
        return slug
    key = (slug or "").strip().lower().replace(" ", "")
    if key not in CLASSES:
        raise UserError(f"{slug!r}: not a class (classes: {', '.join(SLUGS)})")
    return CLASSES[key]


def of_rule(rule_id: str) -> CtdlClass | None:
    """The class whose prefix a rule id carries, or None (page rules and locators may carry none)."""
    return next((c for c in CLASSES.values() if rule_id.startswith(c.rule_prefix)), None)


def from_env() -> str | None:
    return os.environ.get(ENV) or None
