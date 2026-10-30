"""Field ids, occurrence counting, labelled lines and number parsing."""

from __future__ import annotations

import pytest
from template_texts import lines
from templates._shared import (
    _add,
    _f,
    _line_after,
    _maybe_labeled_number,
    _num,
    _occ,
    _prereq_value,
)
from transcribe_lib import TranscriptionError


def test_a_draft_quotes_its_excerpt_unless_given_raw_text() -> None:
    draft = _f("src_001", "course_id", "ENG 101", "ENG 101 - Comp", "h1")
    assert draft.raw_text == "ENG 101 - Comp"
    assert draft.locator_strategy == "text_anchor"
    assert draft.locator_value == "h1"
    assert _f("src_001", "x", 1, "e", "l", raw="r").raw_text == "r"


@pytest.mark.parametrize(
    ("text", "occurrence"),
    [("one Credits", None), ("Credits and Credits", 1)],
)
def test_occurrence_is_set_only_when_the_excerpt_repeats(
    text: str, occurrence: int | None
) -> None:
    assert _occ(text, "Credits") == occurrence


def test_an_excerpt_missing_from_the_text_raises() -> None:
    with pytest.raises(TranscriptionError, match="missing 'Credits'"):
        _occ("no such label", "Credits")


def test_line_after_skips_blank_lines_and_returns_the_line_as_printed() -> None:
    assert _line_after("Program\n\n  English  \n", "Program") == "  English  "
    assert _line_after(lines("Program"), "Program") is None
    assert _line_after(lines("Programs", "English"), "Program") is None


@pytest.mark.parametrize(
    ("printed", "number"),
    [("3", 3), (" 4 ", 4), ("-2", -2), ("3.5", 3.5), ("0", 0)],
)
def test_num_reads_a_printed_integer_or_decimal(
    printed: str, number: float
) -> None:
    value = _num(printed)
    assert value == number
    assert type(value) is type(number)


@pytest.mark.parametrize("printed", ["", "TBA", "1,000", "3.", ".5", "3-4"])
def test_num_refuses_anything_else(printed: str) -> None:
    with pytest.raises(TranscriptionError, match="not a number"):
        _num(printed)


def test_add_numbers_fields_in_order_and_counts_occurrences() -> None:
    text = lines("Credits", "3", "Credits", "3")
    drafts = []
    _add(drafts, "course_id", "ENG", "Credits", "label", text, notes="n")
    _add(drafts, "course_name", "Comp", "Credits\n3", "label", text, raw="r")
    assert [d.field_id for d in drafts] == ["src_001", "src_002"]
    assert [d.occurrence for d in drafts] == [1, 1]
    assert drafts[0].notes == "n"
    assert drafts[1].raw_text == "r"


def test_add_fails_closed_when_the_excerpt_is_not_printed() -> None:
    with pytest.raises(TranscriptionError):
        _add([], "course_id", "ENG", "absent", "label", lines("Credits"))


def test_a_labelled_number_comes_with_its_label_as_the_excerpt() -> None:
    assert _maybe_labeled_number(lines("Credits", "4"), "Credits") == (
        4,
        "Credits\n4",
    )
    assert _maybe_labeled_number(lines("Credits"), "Credits") is None
    assert _maybe_labeled_number(lines("Lecture Hours", "3"), "Credits") is None
    with pytest.raises(TranscriptionError):
        _maybe_labeled_number(lines("Credits", "TBA"), "Credits")


@pytest.mark.parametrize(
    ("block", "value"),
    [
        ("Prerequisite(s): ENG 101", "ENG 101"),
        ("  Prerequisite(s):   ENG 101  ", "ENG 101"),
        (
            "Prerequisite(s): and Corequisite(s): ENG 102",
            "Prerequisite(s): and Corequisite(s): ENG 102",
        ),
        ("Corequisite(s): ENG 102", "Corequisite(s): ENG 102"),
    ],
)
def test_prereq_value_drops_the_label_unless_it_glues_onto_corequisite(
    block: str, value: str
) -> None:
    assert _prereq_value(block) == value
