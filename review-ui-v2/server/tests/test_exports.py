import pytest
from conftest import fixture_url

from review_ui.exports import (
    feedback_markdown,
    flagged_markdown,
    golden_for_page,
    labels_for_page,
    property_terms,
)
from review_ui.review import ReviewSession
from review_ui.views import ExtractionView

EID = "2026-02-01T00-00-00Z"
URL = fixture_url("course_admj")


def key(label, n=0):
    return f"ADMJ51::{label}::{URL}::{n}"


def d(label, status, **extra):
    return {
        "type": "decision",
        "author": "Jared",
        "kind": "field",
        "key": key(label),
        "status": status,
        "canonical_label": label,
        "source_url": URL,
        "record_id": "ADMJ51",
        "rule_id": extra.pop("rule_id", None),
        **extra,
    }


@pytest.fixture
def view(store, run, extraction):
    return ExtractionView(store, run.key, EID)


@pytest.fixture
def review(store, run, extraction):
    return ReviewSession.create(store, run.key, EID)


def golden(view, review):
    records = golden_for_page(view, review.decisions, "course_admj", review.review_id)
    assert [r["record_id"] for r in records] == ["ADMJ51", "ADMJ52", "ADMJ53"]
    record = records[0]
    return record, {
        f["canonical_label"]: f for f in record["source_expected"]["fields"]
    }


def test_golden_uses_the_reviewers_corrections(view, review):
    review.apply(d("Credit Value", "rejected", value="3.0", expected_value="3"))
    review.apply(d("Coded Notation", "accepted", value="ADMJ 51"))
    review.apply(d("Keywords", "missing", key="added-1", expected_value="auto body"))
    record, fields = golden(view, review)
    assert (
        fields["Credit Value"]["value"],
        fields["Credit Value"]["review_status"],
    ) == ("3", "corrected")
    assert fields["Coded Notation"]["review_status"] == "accepted"
    assert (fields["Keywords"]["value"], fields["Keywords"]["review_status"]) == (
        "auto body",
        "added",
    )
    assert fields["Language"]["review_status"] == "pending"
    assert record["catalogue_type"] == "COURSES" and record["entity_type"] == "Course"
    assert "field_id" not in fields["Language"]


def test_rejected_field_without_a_correction_is_left_out_and_counted(view, review):
    review.apply(d("Credit Value", "rejected", value="3.0"))
    record, fields = golden(view, review)
    assert "Credit Value" not in fields
    assert record["verification"]["unresolved_fields"] == 1


def test_rejected_as_should_be_absent_becomes_an_absent_field(view, review):
    review.apply(
        d("Language", "rejected", value="English", reasons=["should_be_absent"])
    )
    _, fields = golden(view, review)
    assert (fields["Language"]["presence"], fields["Language"]["value"]) == (
        "absent",
        None,
    )


def test_labels_drop_rejected_and_include_added(view, review):
    label_key = f"label::{URL}::Course::label-course-page"
    review.apply(
        {
            "type": "decision",
            "author": "S",
            "kind": "label",
            "key": label_key,
            "status": "rejected",
            "canonical_label": "Course",
            "source_url": URL,
        }
    )
    review.apply(
        {
            "type": "decision",
            "author": "S",
            "kind": "label",
            "key": f"label::{URL}::Credential::manual",
            "status": "missing",
            "canonical_label": "Credential",
            "source_url": URL,
            "expected_value": "Credential",
        }
    )
    labels = labels_for_page(view, review.decisions, "course_admj")
    assert [(l["label"], l["review_status"]) for l in labels] == [
        ("Credential", "added")
    ]
    assert all("source_url" in l for l in labels)


def test_unreviewed_labels_are_listed_as_pending(view, review):
    (label,) = labels_for_page(view, review.decisions, "course_admj")
    assert (label["label"], label["review_status"]) == ("Course", "pending")


def test_feedback_groups_problems_by_rule_with_notes_and_html(store, run, view, review):
    review.apply(
        d(
            "Credit Value",
            "rejected",
            value="3.0",
            expected_value="3",
            reasons=["wrong_format"],
            rule_id="course-credit-value",
        )
    )
    review.apply(
        {
            "type": "note",
            "author": "Jared",
            "scope": "field",
            "target": key("Credit Value"),
            "text": "whole number",
        }
    )
    review.apply(
        {
            "type": "note",
            "author": "Jared",
            "scope": "general",
            "target": None,
            "text": "general thought",
        }
    )
    review.apply(
        {
            "type": "note",
            "author": "Jared",
            "scope": "rule",
            "target": "course-description",
            "text": "split prereqs",
        }
    )
    review.apply(
        {
            "type": "note",
            "author": "Jared",
            "scope": "property",
            "target": "Credit Value",
            "text": "no decimals",
        }
    )
    review.apply(
        d(
            "Keywords",
            "missing",
            key="added-1",
            expected_value="auto body",
            reasons=["missed"],
        )
    )
    text = feedback_markdown(store, run, view, review.state(), {URL: "course_admj"})
    assert "### `course-credit-value`: Credit Value" in text
    assert "extracted: `3.0`" in text and "expected: `3`" in text
    assert "wrong_format" in text and "whole number" in text
    assert '<span class="course-unit-range">(3.0)</span>' in text
    assert "general thought" in text and "no decimals" in text
    assert "`course-description` (Description), Jared: split prereqs" in text
    assert "No rule found these (missed)" in text and "auto body" in text


def test_feedback_for_a_clean_review_says_so(store, run, view, review):
    text = feedback_markdown(store, run, view, review.state(), {})
    assert "Nothing rejected or missed." in text


# -- flag for review ---------------------------------------------------------
def fl(target, scope="field", flagged=True, **extra):
    return {
        "type": "flag",
        "author": "Jared",
        "scope": scope,
        "target": target,
        "stem": "course_admj",
        "source_url": URL,
        "flagged": flagged,
        "canonical_label": extra.pop("canonical_label", "Credit Value"),
        "record_id": "ADMJ51",
        **extra,
    }


def test_golden_marks_flagged_fields_and_pages_without_changing_their_status(
    view, review
):
    review.apply(d("Credit Value", "accepted", value="3.0"))
    review.apply(fl(key("Credit Value"), note="ask Registrar"))
    review.apply(fl("page::course_admj", scope="page", note="whole page unsure"))
    records = golden_for_page(
        view, review.decisions, "course_admj", review.review_id, review.flags
    )
    fields = {f["canonical_label"]: f for f in records[0]["source_expected"]["fields"]}
    assert fields["Credit Value"]["review_status"] == "accepted"
    assert (fields["Credit Value"]["flagged"], fields["Credit Value"]["flag_note"]) == (
        True,
        "ask Registrar",
    )
    assert "flagged" not in fields["Language"]
    assert records[0]["verification"]["page_flagged"] is True
    assert records[0]["verification"]["page_flag_note"] == "whole page unsure"


def test_golden_without_flags_is_unchanged(view, review):
    records = golden_for_page(view, review.decisions, "course_admj", review.review_id)
    assert "page_flagged" not in records[0]["verification"]
    assert all("flagged" not in f for f in records[0]["source_expected"]["fields"])


def test_labels_mark_a_flagged_label(view, review):
    review.apply(
        fl(
            f"label::{URL}::Course::label-course-page",
            scope="label",
            note="is it a Program too?",
        )
    )
    (label,) = labels_for_page(view, review.decisions, "course_admj", review.flags)
    assert (label["flagged"], label["flag_note"]) == (True, "is it a Program too?")


def test_flagged_document_lists_pages_then_items_with_the_extracted_value(
    store, run, view, review
):
    review.apply(fl("page::course_admj", scope="page", note="ask the dean"))
    review.apply(fl(key("Credit Value"), note="units or hours?"))
    review.apply(fl(key("Coded Notation"), canonical_label="Coded Notation"))
    text = flagged_markdown(view, review.flags, run, review.review_id)
    assert "# Flagged for review: cat" in text
    assert "1 page(s), 2 flagged item(s)" in text
    assert "### ADMJ - Administration of Justice" in text
    assert "**whole page flagged** by Jared: ask the dean" in text
    assert (
        "**Credit Value** (property · record ADMJ51) flagged by Jared: units or hours?"
        in text
    )
    assert "extracted: `3.0`" in text and "extracted: `ADMJ 51`" in text


def test_flagged_document_when_nothing_is_flagged(run, view, review):
    assert "Nothing is flagged." in flagged_markdown(
        view, review.flags, run, review.review_id
    )


def test_feedback_lists_flags_separately_from_problems(store, run, view, review):
    review.apply(fl(key("Credit Value"), note="units or hours?"))
    review.apply(fl("page::course_admj", scope="page"))
    text = feedback_markdown(store, run, view, review.state(), {URL: "course_admj"})
    assert "## Flagged for review (waiting on subject matter experts)" in text
    assert "1 page(s) and 1 item(s) flagged for an expert" in text
    assert "units or hours?" in text
    assert "Nothing rejected or missed." in text  # a flag is not a problem


def test_feedback_has_no_flag_section_without_flags(store, run, view, review):
    text = feedback_markdown(store, run, view, review.state(), {})
    assert "Flagged for review" not in text and "flagged for an expert" not in text


# -- ctdl_property in the golden dataset -------------------------------------
def test_a_value_the_reviewer_added_gets_its_ctdl_property_from_the_template(
    view, review
):
    review.apply(
        d(
            "Prerequisite",
            "missing",
            key="added-1",
            expected_value="Completion of ADMJ 50",
        )
    )
    review.apply(
        d("Coded Notation", "missing", key="added-2", expected_value="ADMJ 51")
    )
    fields = golden_for_page(view, review.decisions, "course_admj", review.review_id)[
        0
    ]["source_expected"]["fields"]
    added = {f["canonical_label"]: f for f in fields if f["review_status"] == "added"}
    assert {k: v["ctdl_property"] for k, v in added.items()} == {
        "Prerequisite": "ceterms:prerequisite",
        "Coded Notation": "ceterms:codedNotation",
    }
    assert added["Prerequisite"] == {
        "canonical_label": "Prerequisite",
        "ctdl_property": "ceterms:prerequisite",
        "value": "Completion of ADMJ 50",
        "presence": "present",
        "rule_id": None,
        "source_url": URL,
        "review_status": "added",
    }
    # the value the rules extracted for the same property is still listed beside it
    assert sorted(
        f["review_status"] for f in fields if f["canonical_label"] == "Coded Notation"
    ) == [
        "added",
        "pending",
    ]


def test_every_golden_field_carries_a_ctdl_property_unless_the_template_has_none(
    view, review
):
    _, fields = golden(view, review)
    assert fields["Coded Notation"]["ctdl_property"] == "ceterms:codedNotation"
    assert fields["Credit Value"]["ctdl_property"] == "ceterms:creditValue"
    assert (
        fields["Learning Type"]["ctdl_property"] is None
    )  # the template has no term for it


def test_a_rules_own_ctdl_property_wins_and_the_template_fills_gaps(view, review):
    terms = {"Learning Type": "ceterms:fromTemplate", "Credit Value": "ceterms:ignored"}
    (record,) = golden_for_page(
        view, review.decisions, "course_admj", review.review_id, terms=terms
    )[:1]
    fields = {f["canonical_label"]: f for f in record["source_expected"]["fields"]}
    assert fields["Learning Type"]["ctdl_property"] == "ceterms:fromTemplate"
    assert fields["Credit Value"]["ctdl_property"] == "ceterms:creditValue"


def test_a_corrected_value_keeps_its_ctdl_property(view, review):
    review.apply(d("Credit Value", "rejected", value="3.0", expected_value="3"))
    _, fields = golden(view, review)
    assert (
        fields["Credit Value"]["review_status"],
        fields["Credit Value"]["ctdl_property"],
    ) == (
        "corrected",
        "ceterms:creditValue",
    )


def test_property_terms_reads_the_published_template_and_tolerates_its_absence(
    store, tmp_path
):
    assert property_terms(store)["Keywords"] == "ceterms:keyword"
    from review_ui.store import LocalStore

    assert property_terms(LocalStore(tmp_path / "empty")) == {}
