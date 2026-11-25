"""The dispatcher src/implementations/extract.py calls for course pages."""

from __future__ import annotations

import pytest
import templates
import transcribe_courses
from lib_doubles import example_slot
from template_texts import CLEAN_CATALOG, lines
from templates.clean_catalog import extract_clean_catalog
from transcribe_courses import detect_template, extract_course
from transcribe_lib import TranscriptionError


def test_the_detected_template_reads_the_page_whatever_the_slot_says() -> None:
    slot = example_slot(template_id="acalog_bergen_glued_credits")
    assert extract_course(slot, CLEAN_CATALOG) == extract_clean_catalog(
        CLEAN_CATALOG
    )


def test_an_undetected_page_falls_back_to_the_slot_template_and_warns(
    capsys: pytest.CaptureFixture[str],
) -> None:
    text = lines(
        "ENGL101:",
        "Composition I",
        "Lecture Hours",
        "3",
        "An introduction to college writing.",
    )
    assert detect_template(text) is None
    drafts = extract_course(example_slot(), text)
    assert [d.canonical_label for d in drafts] == [
        "course_id",
        "course_name",
        "course_lecture_hours",
        "course_description",
    ]
    assert capsys.readouterr().err == (
        "warning: detect_template=None for example-engl101-course; "
        "using slot.template_id='clean_catalog_course_detail'\n"
    )


@pytest.mark.parametrize("template_id", ["", "markup_v1", "acalog"])
def test_a_page_no_template_reads_fails_closed_without_an_llm(
    template_id: str,
) -> None:
    with pytest.raises(TranscriptionError, match="No LLM fallback"):
        extract_course(
            example_slot(template_id=template_id), lines("Library hours")
        )


def test_every_name_the_module_lists_is_importable_from_it() -> None:
    missing = [
        name
        for name in transcribe_courses.__all__
        if not hasattr(transcribe_courses, name)
    ]
    assert missing == []
    assert transcribe_courses.TEMPLATE is templates.TEMPLATE
    assert transcribe_courses.FAMILY_OF is templates.FAMILY_OF
