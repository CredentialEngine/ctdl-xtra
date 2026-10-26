"""The template registry, its detection order, and what every extractor
promises: copy only text the freeze prints, and fail closed.

src/implementations/extract.py reads a course page's markup only after a
template raises TranscriptionError. Any other exception skips that
fallback, and the page loses its record.
"""

from __future__ import annotations

import pytest
from evidence import find_excerpt
from inventory import allowed_for
from lib_doubles import example_slot
from normalize import normalize_html
from template_texts import TEXTS, as_html, lines
from templates import (
    FAMILIES,
    FAMILY_OF,
    TEMPLATE,
    acalog,
    clean_catalog,
    coursedog,
    detect_template,
)
from transcribe_courses import extract_course
from transcribe_lib import TranscriptionError

TEMPLATE_FAMILIES = {
    "clean_catalog_course_detail": "custom_html",
    "coursedog_rcbc_course_detail": "coursedog",
    "coursedog_mccc_course_detail": "coursedog",
    "coursedog_brookdale_course_detail": "coursedog",
    "acalog_hcc_nbsp_credits": "acalog",
    "acalog_units_glued_hours": "acalog",
    "acalog_bergen_glued_credits": "acalog",
    "acalog_raritan_hours_credits": "acalog",
}

D1 = (
    "D1: Clean Catalog without Prerequisites or Lecture Hours raises "
    "ValueError at clean_catalog.py:129, so the markup fallback is skipped"
)
D2 = (
    "D2: a Clean Catalog CODE: heading with nothing after it raises "
    "StopIteration at clean_catalog.py:36"
)
D3 = (
    "D3: Raritan without an 'Add to Portfolio' line raises a message-less "
    "StopIteration at acalog.py:425"
)
D9 = (
    "D9: a page cut short raises IndexError or ValueError at "
    "clean_catalog.py:111/129/130/141 and coursedog.py:43/73"
)
LEAK_WHEN_CUT = {
    "clean_catalog_course_detail",
    "coursedog_rcbc_course_detail",
    "coursedog_mccc_course_detail",
    "coursedog_brookdale_course_detail",
}


def test_the_registry_holds_the_eight_templates_and_their_families() -> None:
    assert FAMILY_OF == TEMPLATE_FAMILIES
    assert set(TEMPLATE) == set(TEMPLATE_FAMILIES)


def test_no_two_families_claim_the_same_template_id() -> None:
    assert len(TEMPLATE) == sum(len(family.TEMPLATES) for family in FAMILIES)


def test_families_are_tried_clean_catalog_then_coursedog_then_acalog() -> None:
    assert (clean_catalog, coursedog, acalog) == FAMILIES


def test_the_classification_doc_names_every_template(lib_dir) -> None:
    doc = (lib_dir / "CLASSIFICATION.md").read_text(encoding="utf-8")
    assert [tid for tid in TEMPLATE_FAMILIES if f"`{tid}`" not in doc] == []


@pytest.mark.parametrize("template_id", sorted(TEXTS))
def test_each_layout_is_detected_as_its_own_template(template_id: str) -> None:
    assert detect_template(TEXTS[template_id]) == template_id


@pytest.mark.parametrize("template_id", sorted(TEXTS))
def test_each_template_text_is_what_normalize_html_makes_of_a_page(
    template_id: str,
) -> None:
    text = TEXTS[template_id]
    assert normalize_html(as_html(text)) == text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param(
            TEXTS["clean_catalog_course_detail"]
            + lines("Course Description", "Credit Hours"),
            "clean_catalog_course_detail",
            id="clean-catalog-before-coursedog-labels",
        ),
        pytest.param(
            TEXTS["coursedog_rcbc_course_detail"]
            + lines("Course Description", "Credit Hours"),
            "coursedog_rcbc_course_detail",
            id="rcbc-before-brookdale",
        ),
        pytest.param(
            TEXTS["acalog_hcc_nbsp_credits"]
            + TEXTS["acalog_units_glued_hours"]
            + TEXTS["acalog_bergen_glued_credits"]
            + TEXTS["acalog_raritan_hours_credits"],
            "acalog_hcc_nbsp_credits",
            id="hcc-first-among-acalog",
        ),
        pytest.param(
            TEXTS["acalog_units_glued_hours"]
            + TEXTS["acalog_bergen_glued_credits"]
            + TEXTS["acalog_raritan_hours_credits"],
            "acalog_units_glued_hours",
            id="units-before-bergen",
        ),
        pytest.param(
            TEXTS["acalog_bergen_glued_credits"]
            + TEXTS["acalog_raritan_hours_credits"],
            "acalog_bergen_glued_credits",
            id="bergen-before-raritan",
        ),
    ],
)
def test_detection_order_decides_between_overlapping_signatures(
    text: str, expected: str
) -> None:
    assert detect_template(text) == expected


def test_mercer_wins_although_its_page_also_matches_brookdale() -> None:
    text = TEXTS["coursedog_mccc_course_detail"]
    assert "Course Description" in text and "Credit Hours" in text
    assert detect_template(text) == "coursedog_mccc_course_detail"


@pytest.mark.parametrize(
    "text", ["", lines("Welcome to the library", "Hours and directions")]
)
def test_a_page_no_template_knows_is_none(text: str) -> None:
    assert detect_template(text) is None


@pytest.mark.parametrize("template_id", sorted(TEXTS))
def test_every_field_is_copied_from_the_text_and_locatable(
    template_id: str,
) -> None:
    text = TEXTS[template_id]
    drafts = TEMPLATE[template_id](text)
    labels = [draft.canonical_label for draft in drafts]
    assert [draft.field_id for draft in drafts] == [
        f"src_{n:03d}" for n in range(1, len(drafts) + 1)
    ]
    assert len(labels) == len(set(labels))
    assert {"course_id", "course_name"} <= set(labels)
    assert set(labels) <= allowed_for("Course")
    assert not (
        "course_credits" in labels
        and {"course_credits_min", "course_credits_max"} & set(labels)
    )
    for draft in drafts:
        assert draft.locator_strategy == "text_anchor"
        if isinstance(draft.value, str):
            assert draft.value in text
        start, end = find_excerpt(text, draft.excerpt, draft.occurrence)
        assert text[start:end] == draft.excerpt


FAILS_CLOSED = [
    pytest.param(
        lines(
            "Course Catalog Software by Clean Catalog",
            "English Composition I",
            "Credits",
            "3",
        ),
        id="clean-catalog-footer-without-a-code-heading",
    ),
    pytest.param(
        lines(
            "ENGL101:",
            "Composition I",
            "Credits",
            "TBA",
            "Lecture Hours",
            "3",
            "An introduction to college writing.",
        ),
        id="clean-catalog-credits-not-a-number",
    ),
    pytest.param(
        lines(
            "English Composition",
            "ENGL121",
            "Course Description",
            "Develops writing.",
            "Credit Hours",
            "Min",
            "3",
        ),
        id="coursedog-without-the-courses-breadcrumb",
    ),
    pytest.param(
        lines(
            "Courses/",
            "English Composition",
            "Download as PDF",
            "Course Description",
            "Develops writing.",
            "Credit Hours",
            "Min",
            "3",
        ),
        id="coursedog-without-a-code-after-the-title",
    ),
    pytest.param(
        lines(
            "Courses/",
            "English Composition",
            "ENGL121",
            "Credit Hours",
            "Min",
            "3",
            "Course Description",
        ),
        id="brookdale-without-a-description",
    ),
    pytest.param(
        lines(
            "Courses/",
            "English Composition",
            "ENGL121",
            "Course Description",
            "Develops writing.",
            "Credit Hours (see schedule)",
        ),
        id="brookdale-without-a-credit-block",
    ),
    pytest.param(
        lines(
            "Courses/",
            "English Composition",
            "ENGL121",
            "Course Description",
            "Develops writing.",
            "Credit Hours",
            "Min",
            "TBA",
        ),
        id="coursedog-credits-not-a-number",
    ),
    pytest.param(
        lines(
            "Courses/",
            "ENG101",
            "ENG101",
            "Subject Code",
            "ENG",
            "Course Number",
            "101",
            "Course Description",
            "Develops writing.",
            "Credit Hours",
            "Min",
            "3",
        ),
        id="mercer-title-is-the-code",
    ),
    pytest.param(
        lines(
            "Courses/",
            "English Composition I",
            "ENG-101",
            "Course Long Title",
            "English Composition I: Academic Writing",
            "(Credit Hours) Min",
            "3",
        ),
        id="rcbc-without-a-description",
    ),
    pytest.param(
        lines(
            "Add to Portfolio (opens a new window)",
            "English I",
            "(3,0) 3 Credits",
            "ENGL 111\xa0-\xa0English I",
        ),
        id="raritan-title-without-a-code",
    ),
    pytest.param(
        lines(
            "Add to Portfolio (opens a new window)",
            "ENGL 111\xa0-\xa0English I",
            "Credits vary by term",
            "Note: (3,0) 3 Credits when offered in fall",
        ),
        id="raritan-without-an-hours-line",
    ),
    pytest.param(
        lines(
            "ENGL101:",
            "Composition I",
            "Credits",
            "3",
            "An introduction to college writing.",
        ),
        id="D1-clean-catalog-without-lecture-hours-or-prerequisites",
        marks=pytest.mark.xfail(strict=True, raises=ValueError, reason=D1),
    ),
    pytest.param(
        lines("Credits", "3", "ENGL101:"),
        id="D2-clean-catalog-code-heading-on-the-last-line",
        marks=pytest.mark.xfail(strict=True, raises=StopIteration, reason=D2),
    ),
    pytest.param(
        lines(
            "ENGL 111\xa0-\xa0English I",
            "(3,0) 3 Credits",
            "This course develops expository writing.",
        ),
        id="D3-raritan-without-add-to-portfolio",
        marks=pytest.mark.xfail(strict=True, raises=StopIteration, reason=D3),
    ),
]


@pytest.mark.parametrize("text", FAILS_CLOSED)
def test_a_page_a_template_cannot_read_raises_transcription_error(
    text: str,
) -> None:
    with pytest.raises(TranscriptionError):
        extract_course(example_slot(template_id=""), text)


def leaks_when_cut(text: str) -> list[str]:
    """Each line count after which extract_course raises anything else."""
    rows = text.splitlines()
    slot = example_slot(template_id="")
    leaks = []
    for count in range(len(rows) + 1):
        try:
            extract_course(slot, lines(*rows[:count]) if count else "")
        except TranscriptionError:
            continue
        except Exception as exc:
            leaks.append(f"first {count} lines: {type(exc).__name__}: {exc}")
    return leaks


@pytest.mark.parametrize(
    "template_id",
    [
        pytest.param(
            template_id,
            marks=pytest.mark.xfail(
                strict=True, raises=AssertionError, reason=D9
            ),
        )
        if template_id in LEAK_WHEN_CUT
        else template_id
        for template_id in sorted(TEXTS)
    ],
)
def test_a_page_cut_short_at_any_line_still_fails_closed(
    template_id: str,
) -> None:
    assert leaks_when_cut(TEXTS[template_id]) == []
