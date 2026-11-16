from __future__ import annotations

from pathlib import Path

import pytest
from discovery_doubles import seed_crawl_page

from common.keys import (
    extract_resource_key,
    page_stem,
    property_extract_report_key,
    record_key,
    records_prefix,
    run_prefix,
)
from common.object_store import open_store
from implementations.score_extraction_transform import (
    ExtractionReportError,
    css_from_notes,
    extraction_records,
    whole_catalog_extracted,
)

FOLDER = "catalog-example-edu"
RUN = "2026-09-17T14:20:01Z"
URL = "https://catalog.example.edu/courses/law/"
STEM = page_stem(URL)
PAGE = (
    "<html><body><main>"
    "<div><h2>LAW 604. Natural Resources.</h2></div>"
    "<div><h2>LAW 793. Externship.</h2></div>"
    "</main></body></html>"
)
FIRST_H2 = (
    "body:nth-of-type(1) > main:nth-of-type(1) > div:nth-of-type(1) > "
    "h2:nth-of-type(1)"
)
SECOND_H2 = FIRST_H2.replace("div:nth-of-type(1)", "div:nth-of-type(2)")


def _value(
    resource_id: str,
    prop: str,
    value: str | None,
    *,
    css: str = "-",
    url: str = URL,
) -> dict:
    return {
        "type": "ceterms:Course",
        "resource_id": resource_id,
        "ctdl_property": prop,
        "value": value,
        "catalog_id": FOLDER,
        "source_url": url,
        "retrieved_at": None,
        "notes": f"strategy=profile_title platform=courseleaf css={css}",
    }


def _write(store, value: dict) -> None:
    store.put_json(
        extract_resource_key(
            FOLDER, RUN, value["ctdl_property"], value["resource_id"]
        ),
        value,
    )


def _records(store) -> dict:
    built = extraction_records(store, FOLDER, RUN)
    return {key: built.get_json(key) for key in built.list_keys()}


def test_the_css_path_is_read_from_the_notes() -> None:
    notes = f"strategy=s platform=p css={FIRST_H2} reason=empty_title"
    assert css_from_notes(notes) == FIRST_H2
    assert css_from_notes("strategy=s platform=p css=-") == ""
    assert css_from_notes("") == ""


def test_every_property_of_a_resource_is_one_record(tmp_path: Path) -> None:
    store = open_store(str(tmp_path))
    _write(store, _value("c_LAW604", "ceterms:name", "Natural Resources"))
    _write(store, _value("c_LAW604", "ceterms:codedNotation", "LAW 604"))
    assert _records(store) == {
        record_key(FOLDER, RUN, STEM): {
            "record_id": "c_LAW604",
            "source_url": URL,
            "expected": {
                "ceterms:name": "Natural Resources",
                "ceterms:codedNotation": "LAW 604",
            },
        }
    }


def test_a_value_not_found_has_no_expected_key(tmp_path: Path) -> None:
    store = open_store(str(tmp_path))
    _write(store, _value("c_LAW793", "ceterms:name", None))
    (record,) = _records(store).values()
    assert record["expected"] == {}


def test_a_page_records_follow_the_order_the_page_prints(
    tmp_path: Path,
) -> None:
    store = open_store(str(tmp_path))
    seed_crawl_page(store, FOLDER, RUN, STEM, PAGE, URL)
    # Ids that sort the other way round from the page.
    _write(store, _value("c_B", "ceterms:name", "Natural", css=FIRST_H2))
    _write(store, _value("c_A", "ceterms:name", "Externship", css=SECOND_H2))
    records = _records(store)
    assert records[record_key(FOLDER, RUN, STEM)]["record_id"] == "c_B"
    assert (
        records[record_key(FOLDER, RUN, f"{STEM}--resource-002")]["record_id"]
        == "c_A"
    )


def test_without_the_saved_page_a_page_records_go_by_resource_id(
    tmp_path: Path,
) -> None:
    store = open_store(str(tmp_path))
    _write(store, _value("c_B", "ceterms:name", "Natural", css=FIRST_H2))
    _write(store, _value("c_A", "ceterms:name", "Externship", css=SECOND_H2))
    records = _records(store)
    assert records[record_key(FOLDER, RUN, STEM)]["record_id"] == "c_A"


def test_resources_of_other_pages_are_other_records(tmp_path: Path) -> None:
    store = open_store(str(tmp_path))
    other = "https://catalog.example.edu/courses/bio/"
    _write(store, _value("c_LAW604", "ceterms:name", "Natural Resources"))
    _write(store, _value("c_BIO101", "ceterms:name", "Biology", url=other))
    assert sorted(_records(store)) == sorted(
        [
            record_key(FOLDER, RUN, STEM),
            record_key(FOLDER, RUN, page_stem(other)),
        ]
    )


def test_files_outside_the_extractor_layout_are_ignored(tmp_path: Path) -> None:
    store = open_store(str(tmp_path))
    _write(store, _value("c_LAW604", "ceterms:name", "Natural Resources"))
    root = f"{run_prefix(FOLDER, RUN)}/extraction_report"
    store.put_text(f"{root}/ceterms_name/stub.json", "")
    store.put_json(f"{root}/old-record.json", {"record_id": "old"})
    assert len(_records(store)) == 1


def test_the_records_read_like_records(tmp_path: Path) -> None:
    store = open_store(str(tmp_path))
    _write(store, _value("c_LAW604", "ceterms:name", "Natural Resources"))
    built = extraction_records(store, FOLDER, RUN)
    assert built.list_keys(records_prefix(FOLDER, RUN)) == [
        record_key(FOLDER, RUN, STEM)
    ]
    assert built.list_keys("elsewhere/") == []
    with pytest.raises(FileNotFoundError):
        built.get_json("elsewhere/x.json")
    assert "extraction_report/" in built.describe_location()


def test_a_run_without_extraction_report_files_says_so(tmp_path: Path) -> None:
    with pytest.raises(ExtractionReportError, match="xtra catalog extract"):
        extraction_records(open_store(str(tmp_path)), FOLDER, RUN)


def _property_report(store, prop: str = "ceterms:name", **fields) -> None:
    _write(store, _value("c_LAW604", prop, "x"))
    store.put_json(
        property_extract_report_key(FOLDER, RUN, prop),
        {"only_golden_sample": False, "limit": None, **fields},
    )


def test_a_run_that_read_every_page_extracted_the_whole_catalog(
    tmp_path: Path,
) -> None:
    store = open_store(str(tmp_path))
    _property_report(store)
    _property_report(store, "ceterms:description")
    assert whole_catalog_extracted(store, FOLDER, RUN)


@pytest.mark.parametrize("fields", [{"only_golden_sample": True}, {"limit": 5}])
def test_a_narrowed_run_did_not_extract_the_whole_catalog(
    tmp_path: Path, fields: dict
) -> None:
    store = open_store(str(tmp_path))
    _property_report(store, "ceterms:description")
    _property_report(store, **fields)
    assert not whole_catalog_extracted(store, FOLDER, RUN)


def test_a_report_that_does_not_say_whether_it_was_limited_is_not_trusted(
    tmp_path: Path,
) -> None:
    """Reports written before they recorded the limit."""
    store = open_store(str(tmp_path))
    _write(store, _value("c_LAW604", "ceterms:name", "x"))
    store.put_json(
        property_extract_report_key(FOLDER, RUN, "ceterms:name"),
        {"only_golden_sample": False},
    )
    assert not whole_catalog_extracted(store, FOLDER, RUN)


def test_without_a_property_extraction_report_it_cannot_say(
    tmp_path: Path,
) -> None:
    store = open_store(str(tmp_path))
    _write(store, _value("c_LAW604", "ceterms:name", "x"))
    assert not whole_catalog_extracted(store, FOLDER, RUN)
