from conftest import SAMPLE_STEMS, fixture_url

from review_ui.views import ExtractionView


def test_page_view_lists_labels_and_only_this_pages_fields(store, run, extraction):
    view = ExtractionView(store, run.key, extraction["extraction_id"])
    page = view.page("course_admj")
    assert [l["label"] for l in page["labels"]] == ["Course"]
    assert (
        page["labels"][0]["key"]
        == f"label::{fixture_url('course_admj')}::Course::label-course-page"
    )
    assert [r["record_id"] for r in page["records"]] == ["ADMJ51", "ADMJ52", "ADMJ53"]
    assert {f["source_url"] for f in page["records"][0]["fields"]} == {
        fixture_url("course_admj")
    }


def test_info_page_has_nothing_to_review(store, run, extraction):
    view = ExtractionView(store, run.key, extraction["extraction_id"])
    assert view.item_keys(["index_courses"]) == []


def test_item_keys_cover_labels_and_every_field(store, run, extraction):
    view = ExtractionView(store, run.key, extraction["extraction_id"])
    keys = view.item_keys(SAMPLE_STEMS)
    assert sum(k.startswith("label::") for k in keys) == 2
    assert len(keys) == len(set(keys)) and len(keys) > 20


def test_sample_and_report_are_readable(store, run, extraction):
    view = ExtractionView(store, run.key, extraction["extraction_id"])
    assert [p["stem"] for p in view.sample()] == SAMPLE_STEMS
    assert view.report()["records"] == extraction["records"]
    assert view.ruleset()["version"] == 2
