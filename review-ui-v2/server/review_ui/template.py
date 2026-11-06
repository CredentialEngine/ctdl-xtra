"""CTDL Course template properties.

The "Property" column of the Learning Opportunity BU Template is the canonical
field name; "Term" is the CTDL property it maps to.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from .store import Store

# Beside the crawls in the storage root, so the deployed app needs no files of its own.
TEMPLATE_KEY = "review-ui-index/templates/course.properties.json"


class ConfigMissing(RuntimeError):
    """Shared configuration (the field template) is not in the storage root."""


REQUIRED_SECTION = "Required Properties"


@dataclass(frozen=True)
class TemplateProperty:
    name: str
    term: str | None
    section: str
    required: bool
    multiple: bool


def build_properties(csv_path: Path | str) -> list[dict]:
    """Read the template CSV into an ordered list of property dicts."""
    properties: list[dict] = []
    section = ""
    with open(csv_path, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        next(reader)  # header row
        for row in reader:
            row = row + [""] * (8 - len(row))
            name, term = row[0].strip(), row[1].strip()
            if name and not any(cell.strip() for cell in row[1:]):
                section = name  # section header rows have only the first cell
                continue
            if not name:
                continue
            properties.append(
                {
                    "name": name,
                    "term": term or None,
                    "section": section,
                    "required": section == REQUIRED_SECTION,
                    "multiple": row[6].strip().lower() == "multiple",
                }
            )
    return properties


def load_properties(path: Path | str) -> list[TemplateProperty]:
    raw = json.loads(Path(path).read_text("utf-8"))
    return [TemplateProperty(**item) for item in raw]


def load_template(store: Store) -> list[TemplateProperty]:
    """The field template published in the storage root."""
    try:
        raw = store.read_json(TEMPLATE_KEY)
    except FileNotFoundError as exc:
        raise ConfigMissing(
            f"The field template is missing: {store.location(TEMPLATE_KEY)}. "
            "Publish it with `review-ui-v2 template publish <file>`."
        ) from exc
    return [TemplateProperty(**item) for item in raw]
