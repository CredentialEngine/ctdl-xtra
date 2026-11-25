"""FieldDraft, TranscriptionError and the text-anchor helpers."""

from __future__ import annotations

from dataclasses import fields

import pytest
from template_texts import lines
from transcribe_lib import (
    FieldDraft,
    TranscriptionError,
    after_heading,
    first_occurrence_ok,
    line_after_label,
    must_find,
)


def test_field_draft_keeps_the_field_order_and_defaults_src_relies_on() -> None:
    assert [f.name for f in fields(FieldDraft)] == [
        "field_id",
        "canonical_label",
        "value",
        "raw_text",
        "excerpt",
        "locator_strategy",
        "locator_value",
        "occurrence",
        "notes",
    ]
    draft = FieldDraft(
        "src_001", "course_id", "ENGL101", None, "ENGL101", "text_anchor", "h1"
    )
    assert draft.occurrence is None
    assert draft.notes is None


def test_transcription_error_is_a_value_error() -> None:
    assert issubclass(TranscriptionError, ValueError)


def test_must_find_returns_an_excerpt_the_text_prints() -> None:
    assert must_find("ENGL101: Composition", "ENGL101", where="h1") == (
        "ENGL101"
    )
    with pytest.raises(TranscriptionError, match="^h1: excerpt not in freeze"):
        must_find("ENGL101: Composition", "MATH101", where="h1")


@pytest.mark.parametrize(
    ("text", "occurrence"),
    [("Credits once", None), ("Credits and Credits", 1)],
)
def test_first_occurrence_ok_asks_for_an_occurrence_only_on_repeats(
    text: str, occurrence: int | None
) -> None:
    assert first_occurrence_ok(text, "Credits") == occurrence


def test_first_occurrence_ok_refuses_an_absent_excerpt() -> None:
    with pytest.raises(TranscriptionError):
        first_occurrence_ok("nothing here", "Credits")


def test_line_after_label_takes_only_the_very_next_line() -> None:
    assert line_after_label(lines(" Credits ", " 3 "), "Credits") == "3"
    assert line_after_label("Credits\n\n3\n", "Credits") is None
    assert line_after_label(lines("Credits"), "Credits") is None
    assert line_after_label(lines("Credit", "3"), "Credits") is None


def test_after_heading_can_skip_blank_lines_or_return_them() -> None:
    text = "Description\n\n Writing course. \n"
    assert after_heading(text, "Description") == "Writing course."
    assert after_heading(text, "Description", skip_empty=False) == ""
    assert after_heading(lines("Description"), "Description") is None
    assert after_heading(lines("Other", "x"), "Description") is None
