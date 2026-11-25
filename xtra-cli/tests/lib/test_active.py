"""The active slot list is the pack's slots.json."""

from __future__ import annotations

from pathlib import Path

import active
import dynamic_slots
from lib_doubles import example_slot


def test_active_slots_and_unique_pages_read_the_pack_slots(pack: Path) -> None:
    course = example_slot()
    link = example_slot(record_id="example-engl101-link")
    dynamic_slots.write_slots([course, link])
    assert active.active_slots() == [course, link]
    assert active.unique_pages() == [course]
