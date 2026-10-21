"""Locating an excerpt in normalized text. Offsets are found, never
guessed, and an ambiguous excerpt needs an explicit occurrence."""

from __future__ import annotations

import pytest
from evidence import EvidenceError, find_excerpt, hydrate_evidence
from normalize import sha256_text

TEXT = "Credits\n3\nLecture Hours\n3\n"


def test_a_single_excerpt_gives_its_offsets() -> None:
    assert find_excerpt(TEXT, "Lecture Hours") == (10, 23)


@pytest.mark.parametrize(("occurrence", "start"), [(1, 8), (2, 24)])
def test_a_repeated_excerpt_is_picked_by_its_one_based_occurrence(
    occurrence: int, start: int
) -> None:
    assert find_excerpt(TEXT, "3", occurrence) == (start, start + 1)


def test_overlapping_matches_each_count() -> None:
    assert find_excerpt("aaa", "aa", 2) == (1, 3)


@pytest.mark.parametrize(
    ("excerpt", "occurrence", "message"),
    [
        ("", None, "empty excerpt"),
        ("Lab Hours", None, "excerpt not found"),
        ("3", None, "excerpt occurs 2 times; set occurrence"),
        ("3", 0, "occurrence 0 out of range"),
        ("3", 3, "occurrence 3 out of range"),
    ],
)
def test_an_excerpt_that_cannot_be_placed_exactly_is_refused(
    excerpt: str, occurrence: int | None, message: str
) -> None:
    with pytest.raises(EvidenceError, match=message):
        find_excerpt(TEXT, excerpt, occurrence)


def test_evidence_error_is_a_value_error() -> None:
    assert issubclass(EvidenceError, ValueError)


def test_hydrated_evidence_carries_offsets_hashes_and_its_locator() -> None:
    evidence = hydrate_evidence(
        evidence_id="ev_001",
        excerpt="3",
        snapshot_sha256="a" * 64,
        normalized_text_sha256="b" * 64,
        locator_strategy="text_anchor",
        locator_value="Credits field",
        occurrence=2,
        normalized=TEXT,
    )
    assert evidence == {
        "evidence_id": "ev_001",
        "snapshot_sha256": "a" * 64,
        "normalized_text_sha256": "b" * 64,
        "locator": {
            "strategy": "text_anchor",
            "value": "Credits field",
            "occurrence": 2,
            "page_number": None,
            "bbox": None,
        },
        "occurrence": 2,
        "char_start": 24,
        "char_end": 25,
        "excerpt": "3",
        "excerpt_sha256": sha256_text("3"),
    }
    assert TEXT[evidence["char_start"] : evidence["char_end"]] == "3"
