from __future__ import annotations

from pathlib import Path

import pytest

from implementations.discover_page import (
    field_labels_of,
    page_type_of,
    parse_structure,
    profile_page,
)

# What each hand-written fixture is meant to demonstrate. When a rule in
# discover_rules changes, this table is the thing that has to still hold.
EXPECTED = {
    "course-single.html": {
        "page_type": "Course",
        "labels": ["Course"],
        "markers": {"catalog_year", "prerequisite"},
        "field_labels": {"credits", "department", "prerequisite"},
    },
    "course-prereq-coreq-combined.html": {
        "page_type": "Course",
        "labels": ["Course"],
        "markers": {
            "catalog_year",
            "prerequisite",
            "corequisite",
            "prerequisite_corequisite_combined",
        },
        "field_labels": {"credits", "department"},
    },
    "course-lecture-lab-credit.html": {
        "page_type": "Course",
        "labels": ["Course"],
        "markers": {
            "catalog_year",
            "lecture_lab_credit_numbers",
            "lab_clinical_field_study_hours",
            "printed_zero_hours",
        },
        "field_labels": {"credits", "lab hours", "clinical hours"},
    },
    "course-with-outcomes.html": {
        "page_type": "Multiple",
        "labels": ["Course", "Competency"],
        "markers": {"catalog_year", "learning_outcomes"},
        "field_labels": {"credits", "department"},
    },
    "program.html": {
        "page_type": "LearningOpportunity",
        "labels": ["LearningOpportunity"],
        "markers": {"catalog_year", "program_markers"},
        "field_labels": set(),
    },
    "outcomes-only.html": {
        "page_type": "Competency",
        "labels": ["Competency"],
        "markers": {"catalog_year", "learning_outcomes"},
        "field_labels": set(),
    },
    "multi-course.html": {
        "page_type": "Course",
        "labels": ["Course"],
        "markers": {"catalog_year", "multi_course_page"},
        "field_labels": set(),
    },
    "policy-course-numbering.html": {
        "page_type": "Unknown",
        "labels": [],
        "markers": {"catalog_year", "policy_or_definition_page"},
        "field_labels": set(),
    },
    "error-page.html": {
        "page_type": "Unknown",
        "labels": [],
        "markers": {"empty_or_error_page"},
        "field_labels": set(),
    },
    "course-title-in-h2.html": {
        "page_type": "Course",
        "labels": ["Course"],
        "markers": {"catalog_year"},
        "field_labels": {"credits", "department"},
    },
}


def profile_fixture(fixture_html_dir: Path, name: str):
    return profile_page(
        url=f"https://catalog.example.edu/{Path(name).stem}",
        html=(fixture_html_dir / name).read_text(encoding="utf-8"),
        stem=Path(name).stem,
    )


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_each_fixture_profiles_as_intended(
    fixture_html_dir: Path, name: str
) -> None:
    expected = EXPECTED[name]
    profile = profile_fixture(fixture_html_dir, name)
    assert profile.page_type == expected["page_type"]
    assert profile.labels == expected["labels"]
    assert set(profile.markers) == expected["markers"]
    assert set(profile.field_labels) == expected["field_labels"]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_every_marker_carries_its_evidence(
    fixture_html_dir: Path, name: str
) -> None:
    profile = profile_fixture(fixture_html_dir, name)
    for marker, quote in profile.markers.items():
        assert quote, f"{marker} fired with no evidence"
        assert len(quote) <= 80


def test_a_course_title_in_a_heading_never_becomes_a_field_label(
    fixture_html_dir: Path,
) -> None:
    """Headings carry course titles, so they stay out of the vocabulary."""
    profile = profile_fixture(fixture_html_dir, "course-title-in-h2.html")
    assert "ACCT 101 Principles of Accounting" in profile.headings
    for label in profile.field_labels:
        assert "acct" not in label
        assert "principles of accounting" not in label


def test_a_heading_is_never_a_label_even_without_a_course_code() -> None:
    html = "<h2>Description of the Course Content</h2><dt>Credits</dt>"
    structure = parse_structure(html)
    labels = field_labels_of(structure, "")
    assert labels == ["credits"]
    assert structure.headings == ["Description of the Course Content"]


def test_a_bold_run_is_a_label_only_when_something_follows_it() -> None:
    """`<strong>Credits</strong> 3` is a label. A bold title is not."""
    html = (
        "<p><strong>Credits</strong> 3</p>"
        "<p><strong>Prerequisite:</strong></p>"
        "<p><strong>Introduction to Welding</strong></p>"
    )
    labels = field_labels_of(parse_structure(html), "")
    assert labels == ["credits", "prerequisite"]


def test_a_short_line_ending_in_a_colon_is_a_label() -> None:
    text = "Credits:\n3\nThis sentence is far too long to be a key and ends:\n"
    labels = field_labels_of(parse_structure(""), text)
    assert labels == ["credits"]


def test_digits_in_a_label_collapse_so_terms_group() -> None:
    html = "<dt>Semester 1</dt><dt>Semester 2</dt>"
    assert field_labels_of(parse_structure(html), "") == ["semester #"]


def test_outcomes_need_a_heading_and_two_items() -> None:
    one_item = "<h3>Learning Outcomes</h3><ul><li>Only one.</li></ul>"
    assert not parse_structure(one_item).outcomes_evidence
    two_items = (
        "<h3>Learning Outcomes</h3><ul><li>One.</li><li>Two.</li></ul>"
    )
    assert parse_structure(two_items).outcomes_evidence


def test_a_list_under_an_unrelated_heading_is_not_an_outcome_list() -> None:
    html = (
        "<h3>Learning Outcomes</h3><h3>Course Fees</h3>"
        "<ul><li>One.</li><li>Two.</li></ul>"
    )
    assert not parse_structure(html).outcomes_evidence


def test_tabs_are_noticed_by_role_or_by_class() -> None:
    assert parse_structure('<div role="tab">A</div>').tabs_evidence
    assert parse_structure('<ul class="nav tabs">x</ul>').tabs_evidence
    assert not parse_structure('<div class="tabular-data">x</div>').tabs_evidence


def test_script_and_style_text_is_not_page_content() -> None:
    html = "<style>.x{}</style><script>var credits = 3;</script><dt>Credits</dt>"
    assert field_labels_of(parse_structure(html), "") == ["credits"]


def test_page_type_names_the_single_label_or_says_how_many() -> None:
    assert page_type_of([]) == "Unknown"
    assert page_type_of(["Course"]) == "Course"
    assert page_type_of(["Course", "Competency"]) == "Multiple"


def test_the_same_page_always_profiles_the_same_way(
    fixture_html_dir: Path,
) -> None:
    first = profile_fixture(fixture_html_dir, "course-single.html")
    second = profile_fixture(fixture_html_dir, "course-single.html")
    assert first.as_dict() == second.as_dict()


def test_a_repeated_course_code_still_counts_as_one_course(
    fixture_html_dir: Path,
) -> None:
    profile = profile_fixture(fixture_html_dir, "course-single.html")
    assert profile.course_code_count == 1
    assert profile.course_block_count == 1


def test_rules_fired_records_why_each_label_applied(
    fixture_html_dir: Path,
) -> None:
    profile = profile_fixture(fixture_html_dir, "course-with-outcomes.html")
    assert set(profile.rules_fired) == {"Course", "Competency"}
    assert "course block" in profile.rules_fired["Course"]


def test_the_profile_records_the_url_template_with_digits_removed() -> None:
    profile = profile_page(
        url="https://catalog.example.edu/content.php?catoid=13&navoid=664",
        html="<h1>x</h1>",
        stem="stem",
    )
    assert profile.url_template == "/content.php?catoid={n}&navoid={n}"


def test_nothing_normalized_is_written_into_the_profile(
    fixture_html_dir: Path,
) -> None:
    """Normalized text is read in memory; only its hash is kept."""
    profile = profile_fixture(fixture_html_dir, "course-single.html")
    payload = profile.as_dict()
    assert len(payload["text_sha256"]) == 64
    assert "text" not in payload
    assert "normalized" not in payload
