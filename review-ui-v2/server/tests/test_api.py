import io
import json
import zipfile

import pytest
from conftest import SAMPLE_STEMS, fixture_url
from fastapi.testclient import TestClient

from review_ui.api import create_app

URL = fixture_url("course_admj")
P = "/api/c/cat-2026-01-01t00-00-00z"  # the fake run: catalog "cat", run id 2026-01-01T00:00:00Z


@pytest.fixture
def client(crawl_root, run, extraction):
    return TestClient(create_app(crawl_root, run))


def crawl_of(run):
    return "/".join(run.key.split("/")[-2:])


def test_state_describes_the_sample_and_the_review(client):
    state = client.get(f"{P}/state").json()
    assert [p["stem"] for p in state["pages"]] == SAMPLE_STEMS
    course = state["pages"][0]
    assert course["title"] == "ADMJ - Administration of Justice · 3 courses" and course[
        "labels"
    ] == ["Course"]
    assert state["review"]["counts"]["total"] == sum(
        len(p["keys"]) for p in state["pages"]
    )
    assert "Keywords" in {p["name"] for p in state["properties"]}
    assert "wrong_format" in state["reasons"] and "Program" in state["label_vocabulary"]


def test_serving_again_resumes_the_existing_review(crawl_root, run, extraction):
    first = (
        TestClient(create_app(crawl_root, run))
        .get(f"{P}/state")
        .json()["review"]["session"]["review_id"]
    )
    second = (
        TestClient(create_app(crawl_root, run))
        .get(f"{P}/state")
        .json()["review"]["session"]["review_id"]
    )
    assert first == second
    third = (
        TestClient(create_app(crawl_root, run, new_review=True))
        .get(f"{P}/state")
        .json()["review"]["session"]["review_id"]
    )
    assert third != first


def test_page_endpoint_returns_labels_and_records(client):
    page = client.get(f"{P}/pages/course_admj").json()
    assert page["records"][0]["record_id"] == "ADMJ51"
    assert client.get(f"{P}/pages/nope").status_code == 404


def test_page_content_is_safe_and_self_contained(client):
    html = client.get(f"{P}/pages/course_admj/content").text
    assert (
        html.count("<script") == 1 and "addEventListener" in html
    )  # only our own script
    assert 'id="content-body"' in html and "leftsidemenu" not in html
    assert f'<base href="{fixture_url("course_admj")}"' in html  # no <base> on the page
    assert ".course-title{font-weight:bold}" in html  # the page's own style is kept
    assert "onclick" not in html


def test_page_source_returns_the_main_content_markup(client):
    assert (
        'id="content-body"'
        in client.get(f"{P}/pages/course_admj/source").json()["html"]
    )


def event(**extra):
    return {
        "type": "decision",
        "author": "Seth",
        "kind": "field",
        "key": f"ADMJ51::Language::{URL}::0",
        "status": "accepted",
        "canonical_label": "Language",
        "source_url": URL,
        "value": "English",
        **extra,
    }


def test_events_are_validated_and_saved(client, store, run):
    assert client.post(f"{P}/events", json=event(status="bogus")).status_code == 422
    saved = client.post(f"{P}/events", json=event()).json()
    assert saved["counts"]["accepted"] == 1
    review = client.get(f"{P}/state").json()["review"]
    assert list(review["decisions"]) == [f"ADMJ51::Language::{URL}::0"]
    assert store.exists(
        f"{run.key}/review-ui/{review['session']['review_id']}/events.jsonl"
    )


def test_new_review_carries_accepted_values_and_old_one_can_be_reopened(client):
    client.post(f"{P}/events", json=event())
    old = client.get(f"{P}/state").json()["review"]["session"]["review_id"]
    new_state = client.post(f"{P}/reviews").json()
    assert new_state["review"]["session"]["review_id"] != old
    assert len(new_state["review"]["decisions"]) == 1
    assert (
        client.post(f"{P}/reviews/{old}/open").json()["review"]["session"]["review_id"]
        == old
    )
    assert client.post(f"{P}/reviews/nope/open").status_code == 404


def test_downloads(client):
    client.post(f"{P}/events", json=event())
    golden = client.get(f"{P}/export/golden/course_admj.json")
    assert "attachment" in golden.headers["content-disposition"]
    assert golden.json()[0]["record_id"] == "ADMJ51"
    assert (
        client.get(f"{P}/export/labels/course_admj.json").json()[0]["source_url"] == URL
    )
    assert {l["source_url"] for l in client.get(f"{P}/export/labels.json").json()} == {
        fixture_url("course_admj"),
        fixture_url("course_mixed"),
    }
    with zipfile.ZipFile(
        io.BytesIO(client.get(f"{P}/export/golden.zip").content)
    ) as archive:
        assert sorted(archive.namelist()) == sorted(
            f"golden/{s}.json" for s in SAMPLE_STEMS
        )
        assert json.loads(archive.read("golden/index_courses.json")) == []
    feedback = client.get(f"{P}/export/feedback.md")
    assert feedback.text.startswith("# Review feedback")


# -- flag for review ---------------------------------------------------------
NAME_FIELD = f"ADMJ51::Learning Opportunity Name::{URL}::0"


def flag_event(target=NAME_FIELD, scope="field", flagged=True, **extra):
    return {
        "type": "flag",
        "author": "Jared",
        "scope": scope,
        "target": target,
        "stem": "course_admj",
        "source_url": URL,
        "flagged": flagged,
        "canonical_label": "Learning Opportunity Name",
        "record_id": "ADMJ51",
        **extra,
    }


def test_flags_are_saved_and_come_back_in_the_state(client, store, run):
    assert (
        client.post(
            f"{P}/events", json=flag_event(note="ask the registrar")
        ).status_code
        == 200
    )
    state = client.get(f"{P}/state").json()
    assert state["review"]["flags"][NAME_FIELD]["note"] == "ask the registrar"
    assert state["review"]["counts"]["flagged_items"] == 1
    assert "page" in state["flag_scopes"]
    review_id = state["review"]["session"]["review_id"]
    assert store.exists(f"{run.key}/review-ui/{review_id}/flags.json")


def test_a_bad_flag_is_rejected(client):
    assert client.post(f"{P}/events", json=flag_event(flagged="yes")).status_code == 422


def test_flag_can_be_cleared(client):
    client.post(f"{P}/events", json=flag_event())
    client.post(f"{P}/events", json=flag_event(flagged=False))
    assert client.get(f"{P}/state").json()["review"]["flags"] == {}


def test_flags_carry_into_a_new_review(client):
    client.post(f"{P}/events", json=flag_event(note="still unsure"))
    old = client.get(f"{P}/state").json()["review"]["session"]["review_id"]
    new_state = client.post(f"{P}/reviews").json()
    assert new_state["review"]["session"]["review_id"] != old
    assert new_state["review"]["flags"][NAME_FIELD]["note"] == "still unsure"


def test_flag_downloads(client):
    client.post(f"{P}/events", json=flag_event(note="units or hours?"))
    client.post(f"{P}/events", json=flag_event("page::course_admj", scope="page"))
    flagged = client.get(f"{P}/export/flagged.md")
    assert "attachment" in flagged.headers["content-disposition"]
    assert "units or hours?" in flagged.text and "whole page flagged" in flagged.text
    golden = client.get(f"{P}/export/golden/course_admj.json").json()
    fields = {f["canonical_label"]: f for f in golden[0]["source_expected"]["fields"]}
    assert fields["Learning Opportunity Name"]["flagged"] is True
    assert golden[0]["verification"]["page_flagged"] is True
    assert "units or hours?" in client.get(f"{P}/export/feedback.md").text


def test_downloaded_golden_files_include_the_ctdl_property_of_added_values(client):
    added = {
        "type": "decision",
        "author": "Jared",
        "kind": "field",
        "status": "missing",
        "key": f"ADMJ51::Prerequisite::{URL}::added::x",
        "canonical_label": "Prerequisite",
        "source_url": URL,
        "record_id": "ADMJ51",
        "expected_value": "Completion of ADMJ 50",
    }
    assert client.post(f"{P}/events", json=added).status_code == 200
    page = client.get(f"{P}/export/golden/course_admj.json").json()
    (field,) = [
        f for f in page[0]["source_expected"]["fields"] if f["review_status"] == "added"
    ]
    assert field["ctdl_property"] == "ceterms:prerequisite"
    with zipfile.ZipFile(
        io.BytesIO(client.get(f"{P}/export/golden.zip").content)
    ) as archive:
        fields = json.loads(archive.read("golden/course_admj.json"))[0][
            "source_expected"
        ]["fields"]
    assert all("ctdl_property" in f for f in fields)


# -- saving a golden dataset -----------------------------------------------------
def accept(label, value, record="ADMJ51"):
    return {
        "type": "decision",
        "author": "Jared",
        "kind": "field",
        "key": f"{record}::{label}::{URL}::0",
        "status": "accepted",
        "canonical_label": label,
        "source_url": URL,
        "record_id": record,
        "value": value,
    }


def test_the_save_button_writes_the_pages_golden_dataset_next_to_the_crawl(
    client, store, run
):
    client.post(f"{P}/events", json=accept("Coded Notation", "ADMJ 51"))
    client.post(
        f"{P}/events", json=accept("Learning Opportunity Name", "Juvenile Procedures")
    )
    reply = client.post(f"{P}/golden/course_admj")
    assert reply.status_code == 200
    body = reply.json()
    assert (body["values"], body["records"], body["datasets"]) == (2, 1, 1)
    assert body["key"] == f"{crawl_of(run)}/course_admj/course_admj.json"
    saved = store.read_json(body["key"])
    assert {f["ctdl_property"]: f["value"] for f in saved[0]["fields"]} == {
        "ceterms:codedNotation": "ADMJ 51",
        "ceterms:name": "Juvenile Procedures",
    }
    assert all(
        set(f) == {"ctdl_property", "value", "source_url"} for f in saved[0]["fields"]
    )
    assert (
        body["left_out"]["not_reviewed"] > 0
    )  # the rest of the page is still undecided


def test_the_save_button_can_write_to_a_separate_golden_storage(
    crawl_root, run, extraction, tmp_path
):
    golden_root = tmp_path / "xtra-golden-sets-verified"
    client = TestClient(create_app(crawl_root, run, golden_root=golden_root))
    client.post(f"{P}/events", json=accept("Coded Notation", "ADMJ 51"))
    body = client.post(f"{P}/golden/course_admj").json()
    saved = golden_root / f"{crawl_of(run)}/course_admj"
    assert sorted(p.name for p in saved.iterdir()) == [
        "course_admj.html",
        "course_admj.json",
    ]
    assert str(saved) in body["location"]
    assert not list(
        (crawl_root / run.key).rglob("course_admj.json")
    )  # nothing in the crawl
    state = client.get(f"{P}/state").json()
    assert state["golden"] == ["course_admj"]


def test_saving_with_nothing_verified_is_refused_with_a_reason(client, store, run):
    reply = client.post(f"{P}/golden/course_admj")
    assert reply.status_code == 422 and "Nothing to save" in reply.json()["detail"]
    assert not store.exists(f"{crawl_of(run)}/course_admj/course_admj.json")


def test_saving_an_unknown_page_is_a_404(client):
    assert client.post(f"{P}/golden/nope").status_code == 404


def test_the_state_lists_the_pages_with_a_saved_dataset(client):
    assert client.get(f"{P}/state").json()["golden"] == []
    client.post(f"{P}/events", json=accept("Coded Notation", "ADMJ 51"))
    client.post(f"{P}/golden/course_admj")
    assert client.get(f"{P}/state").json()["golden"] == ["course_admj"]


# -- running as a container --------------------------------------------------------
def test_healthz_answers_without_touching_storage(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_the_web_app_folder_can_be_set_by_the_environment(
    monkeypatch, tmp_path, crawl_root, run, extraction
):
    import importlib

    from review_ui import api as api_module

    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "index.html").write_text("<title>from the image</title>")
    monkeypatch.setenv("REVIEW_UI_WEB_DIST", str(tmp_path / "dist"))
    reloaded = importlib.reload(api_module)
    try:
        page = TestClient(reloaded.create_app(crawl_root, run)).get("/")
        assert page.status_code == 200 and "from the image" in page.text
    finally:
        monkeypatch.delenv("REVIEW_UI_WEB_DIST")
        importlib.reload(api_module)
