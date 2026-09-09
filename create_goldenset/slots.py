"""One catalog course page queued for freeze + extract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from page import slug_url


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
