import pytest
from conftest import fixture_url

from review_ui.exports import property_terms
from review_ui.golden import (
    NothingToSave,
    golden_dataset,
    golden_key,
    save_golden,
    saved_pages,
)
from review_ui.review import ReviewSession
from review_ui.views import ExtractionView

EID = "2026-02-01T00-00-00Z"
URL = fixture_url("course_admj")
SOURCE_ONLY = {"ctdl_property", "value", "source_url"}


def crawl_of(run):
    return "/".join(run.key.split("/")[-2:])


def key(label, record="ADMJ51", n=0):
    return f"{record}::{label}::{URL}::{n}"


def decide(label, status, record="ADMJ51", **extra):
    return {
        "type": "decision",
        "author": "Jared",
        "kind": "field",
        "key": key(label, record),
        "status": status,
        "canonical_label": label,
        "source_url": URL,
        "record_id": record,
        **extra,
    }


@pytest.fixture
def view(store, run, extraction):
    return ExtractionView(store, run.key, EID)


@pytest.fixture
def review(store, run, extraction):
    return ReviewSession.create(store, run.key, EID)


@pytest.fixture
def terms(store):
    return property_terms(store)


def dataset(view, review, terms, stem="course_admj"):
    return golden_dataset(
        view, review.decisions, stem, review.review_id, review.flags, terms
    )


@pytest.fixture
def golden_store(tmp_path):
    from review_ui.store import LocalStore

    return LocalStore(tmp_path / "xtra-golden-sets-verified")


def save(store, run, view, review, terms, stem="course_admj", golden_store=None):
    return save_golden(
        golden_store or store,
        store,
        run,
        view,
        review.decisions,
        stem,
        review.review_id,
        review.flags,
        terms,
        f"{run.key}/pages/{stem}.html",
    )


def values(records, record=0):
    return {f["ctdl_property"]: f["value"] for f in records[record]["fields"]}


def test_nothing_reviewed_means_nothing_to_save(store, run, view, review, terms):
    records, left_out = dataset(view, review, terms)
    assert records == [] and left_out["not_reviewed"] > 20
    with pytest.raises(NothingToSave, match="Nothing to save"):
        save(store, run, view, review, terms)
    assert not store.exists(golden_key(run, "course_admj"))


def test_accepted_corrected_and_added_values_are_saved_with_only_three_keys(
    view, review, terms
):
    review.apply(decide("Coded Notation", "accepted", value="ADMJ 51"))
    review.apply(decide("Credit Value", "rejected", value="3.0", expected_value="3"))
    review.apply(
        decide("Prerequisite", "missing", expected_value="Completion of ADMJ 50")
    )
    records, _ = dataset(view, review, terms)
    assert len(records) == 1 and list(records[0]) == ["fields"]
    assert values(records) == {
        "ceterms:codedNotation": "ADMJ 51",
        "ceterms:creditValue": "3",  # the reviewer's correction, not the extracted 3.0
        "ceterms:prerequisite": "Completion of ADMJ 50",
    }
    for field in records[0]["fields"]:
        assert set(field) == SOURCE_ONLY and field["source_url"] == URL


def test_unverified_and_unusable_values_are_left_out_and_counted(view, review, terms):
    review.apply(decide("Coded Notation", "accepted", value="ADMJ 51"))  # saved
    review.apply(
        decide("Language", "rejected", value="English")
    )  # rejected, no correction
    review.apply(
        decide("Learning Type", "accepted", value="Course")
    )  # template has no term for it
    review.apply(
        {
            "type": "flag",
            "author": "Jared",
            "scope": "field",
            "target": key("Description"),
            "stem": "course_admj",
            "source_url": URL,
            "flagged": True,
        }
    )  # undecided and waiting for an expert
    records, left_out = dataset(view, review, terms)
    assert values(records) == {"ceterms:codedNotation": "ADMJ 51"}
    assert left_out["rejected_without_correction"] == 1
    assert left_out["no_ctdl_property"] == 1
    assert (
        left_out["flagged"] == 1 and left_out["not_reviewed"] > 1
    )  # flagged is a subset


def test_values_are_grouped_by_the_record_they_belong_to(view, review, terms):
    for record in ("ADMJ51", "ADMJ52", "ADMJ53"):
        review.apply(decide("Coded Notation", "accepted", record=record, value=record))
    records, _ = dataset(view, review, terms)
    assert [len(r["fields"]) for r in records] == [1, 1, 1] and len(records) == 3


def test_the_source_html_is_saved_beside_the_json_in_a_folder_named_for_the_page(
    store, run, view, review, terms
):
    review.apply(decide("Coded Notation", "accepted", value="ADMJ 51"))
    result = save(store, run, view, review, terms)
    folder = f"{crawl_of(run)}/course_admj"
    assert store.list_dir(folder) == ["course_admj.html", "course_admj.json"]
    assert result["html_key"] == f"{folder}/course_admj.html"
    assert store.read_text(result["html_key"]) == store.read_text(
        f"{run.key}/pages/course_admj.html"
    )


def test_saving_writes_one_folder_per_page_under_golden_data(
    store, run, view, review, terms
):
    review.apply(decide("Coded Notation", "accepted", value="ADMJ 51"))
    result = save(store, run, view, review, terms)
    assert result["key"] == f"{crawl_of(run)}/course_admj/course_admj.json"
    assert (result["values"], result["records"], result["datasets"]) == (1, 1, 1)
    assert store.read_json(result["key"]) == [
        {
            "fields": [
                {
                    "ctdl_property": "ceterms:codedNotation",
                    "value": "ADMJ 51",
                    "source_url": URL,
                }
            ]
        }
    ]
    assert saved_pages(store, run) == ["course_admj"]


def test_saving_again_replaces_the_earlier_save(store, run, view, review, terms):
    review.apply(decide("Credit Value", "accepted", value="3.0"))
    save(store, run, view, review, terms)
    review.apply(decide("Credit Value", "rejected", value="3.0", expected_value="4"))
    result = save(store, run, view, review, terms)
    assert result["datasets"] == 1  # still one page
    assert store.read_json(result["key"])[0]["fields"][0]["value"] == "4"


def test_a_value_accepted_as_absent_is_not_saved_but_counted(view, review, terms):
    program = fixture_url("program_vmd")
    review.apply(
        {
            "type": "decision",
            "author": "Jared",
            "kind": "field",
            "key": f"VMD100::Description::{program}::0",
            "status": "accepted",
            "canonical_label": "Description",
            "source_url": program,
            "record_id": "VMD100",
            "value": None,
        }
    )
    review.apply(
        {
            "type": "decision",
            "author": "Jared",
            "kind": "field",
            "key": f"VMD100::Coded Notation::{program}::0",
            "status": "accepted",
            "canonical_label": "Coded Notation",
            "source_url": program,
            "record_id": "VMD100",
            "value": "VMD 100",
        }
    )
    records, left_out = golden_dataset(
        view, review.decisions, "program_vmd", review.review_id, review.flags, terms
    )
    assert values(records) == {"ceterms:codedNotation": "VMD 100"}
    assert left_out["absent"] == 1


def test_golden_sets_go_to_their_own_storage_not_the_crawl_folder(
    store, run, view, review, terms, golden_store
):
    review.apply(decide("Coded Notation", "accepted", value="ADMJ 51"))
    result = save(store, run, view, review, terms, golden_store=golden_store)
    crawl = "/".join(run.key.split("/")[-2:])
    assert result["key"] == f"{crawl}/course_admj/course_admj.json"
    assert golden_store.list_dir(f"{crawl}/course_admj") == [
        "course_admj.html",
        "course_admj.json",
    ]
    assert golden_store.read_text(result["html_key"]) == store.read_text(
        f"{run.key}/pages/course_admj.html"
    )
    assert not any("golden" in name for name in store.list_dir(run.key))
    assert saved_pages(golden_store, run) == ["course_admj"] and result["datasets"] == 1
    assert not store.exists(
        "review-ui-index/golden-data-index.json"
    )  # no index any more
