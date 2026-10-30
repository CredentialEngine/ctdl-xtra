"""slots.json: the queue of pages a pack is built from."""

from __future__ import annotations

import json
from pathlib import Path

import dynamic_slots
import pytest
from dynamic_slots import (
    load_slots,
    slot_from_dict,
    slots_path,
    unique_pages,
    write_slots,
)
from lib_doubles import example_slot

MINIMAL = {
    "record_id": "x-course",
    "requested_url": "https://x.example.edu/a",
    "institution_name": "X",
    "source_family": "acalog",
    "template_id": "acalog_hcc_nbsp_credits",
}


def test_slots_live_in_the_pack(pack: Path) -> None:
    assert slots_path() == pack / "slots.json"


def test_a_minimal_row_fills_in_the_defaults() -> None:
    slot = slot_from_dict(MINIMAL)
    assert slot.entity_type == "Course"
    assert slot.template_version == "1"
    assert slot.page_id == "x-course"
    assert slot.copy_html is None
    assert slot.retrieved_at is None
    assert slot.multi_entity_bundle is False
    assert slot.notes == ""


def test_row_values_are_coerced_to_the_slot_field_types() -> None:
    slot = slot_from_dict(
        {
            **MINIMAL,
            "template_version": 2,
            "copy_html": "fixtures/x.html",
            "multi_entity_bundle": 1,
            "notes": None,
        }
    )
    assert slot.template_version == "2"
    assert slot.copy_html == Path("fixtures/x.html")
    assert slot.multi_entity_bundle is True
    assert slot.notes == ""


def test_slots_round_trip_through_the_file(pack: Path) -> None:
    slots = [
        example_slot(),
        example_slot(
            record_id="upr-esp101-course",
            requested_url="https://catalog.example.edu/espanol/esp101",
            institution_name="Universidad – Río Piedras",
            copy_html=Path("x/y.html"),
            multi_entity_bundle=True,
            notes="bundle",
        ),
    ]
    path = write_slots(slots, extra={"discovery": [{"family": "custom_html"}]})
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert payload["schema"] == "xtra-slots-1"
    assert payload["discovery"] == [{"family": "custom_html"}]
    assert "Universidad – Río Piedras" in text
    assert load_slots() == slots


def test_a_bare_list_of_rows_also_loads(pack: Path) -> None:
    (pack / "slots.json").write_text(json.dumps([MINIMAL]), encoding="utf-8")
    assert [slot.record_id for slot in load_slots()] == ["x-course"]


def test_a_missing_slots_file_says_to_discover_first(pack: Path) -> None:
    with pytest.raises(FileNotFoundError, match="slots.json; run"):
        load_slots()


def test_unique_pages_keeps_the_first_slot_on_each_page(pack: Path) -> None:
    first = example_slot()
    same_page = example_slot(record_id="example-engl101-link")
    other = example_slot(
        record_id="example-math101-course",
        requested_url="https://catalog.example.edu/math/math101",
    )
    write_slots([first, same_page, other])
    assert unique_pages() == [first, other]


def test_writing_slots_creates_the_pack_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(dynamic_slots, "PACK", tmp_path / "new" / "pack")
    assert write_slots([]).is_file()
