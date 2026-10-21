"""The Slot that describes one page of work."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest
from html_text import slug_url
from lib_doubles import example_slot
from slots import Slot


def test_slot_keeps_the_field_order_positional_callers_rely_on() -> None:
    """src/implementations/extract.py and lib/college_capture.py build a
    Slot positionally, so a reordered field would shift silently."""
    assert [f.name for f in fields(Slot)] == [
        "record_id",
        "entity_type",
        "requested_url",
        "institution_name",
        "source_family",
        "template_id",
        "template_version",
        "page_id",
        "copy_html",
        "retrieved_at",
        "multi_entity_bundle",
        "notes",
    ]


def test_a_slot_cannot_be_changed_in_place() -> None:
    slot = example_slot()
    with pytest.raises(FrozenInstanceError):
        slot.record_id = "other"  # type: ignore[misc]


def test_the_stem_is_the_slug_of_the_requested_url() -> None:
    slot = example_slot()
    assert slot.stem == slug_url(slot.requested_url)
    assert slot.stem == "catalog-example-edu-english-engl101"


def test_bundle_flag_and_notes_default_to_off_and_empty() -> None:
    slot = Slot(
        "r",
        "Course",
        "https://x.example.edu/a",
        "X",
        "f",
        "t",
        "1",
        "p",
        None,
        None,
    )
    assert slot.multi_entity_bundle is False
    assert slot.notes == ""
