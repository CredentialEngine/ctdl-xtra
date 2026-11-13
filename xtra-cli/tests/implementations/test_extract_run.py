from __future__ import annotations

import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from discovery_doubles import seed_crawl_page

from common.keys import discovery_key, extract_resource_key, run_prefix
from common.object_store import open_store
from implementations.discover import PAGES_FILE, SUMMARY_FILE, sample_file_name
from implementations.extract_run import (
    ExtractionError,
    Extractor,
    Occurrence,
    Page,
    RdfClass,
    Reading,
    css_path,
    inside_chrome,
    page_platform,
    printed_text,
    reading_notes,
    resource_value,
    run_extraction,
    unique_resource_id,
)

FOLDER = "catalog-example-edu"
RUN = "2026-09-17T14:20:01Z"
DISCOVERY = "2026-09-18T10-00-00Z"
PROP = "ex:thing"  # made up: nothing in the shared code is about names


def test_the_page_platform_wins_over_the_site() -> None:
    assert page_platform("acalog", "courseleaf") == "acalog"


def test_a_page_with_no_platform_takes_the_site_platform() -> None:
    assert page_platform("", "courseleaf") == "courseleaf"


def test_no_platform_anywhere_is_empty() -> None:
    assert page_platform("", "") == ""


def test_a_repeated_resource_id_is_numbered_from_its_second_use() -> None:
    seen: dict[str, int] = {}
    ids = [unique_resource_id(i, seen) for i in ("a_X1", "a_X2", "a_X1")]
    assert ids == ["a_X1", "a_X2", "a_X1-2"]
    assert unique_resource_id("a_X1", seen) == "a_X1-3"


def _reading(value: str | None, reason: str = "") -> Reading:
    return Reading(
        value=value,
        raw_text="RAW 101. raw text.",
        strategy="profile_title",
        css_path="div > h1",
        reason=reason,
    )


def _value(reading: Reading) -> dict:
    return resource_value(
        rdf_type="ceterms:Course",
        resource_id="catalog-example-edu_RAW101",
        prop=PROP,
        reading=reading,
        catalog_id=FOLDER,
        source_url="https://catalog.example.edu/x",
        retrieved_at="2026-09-17T14:20:05Z",
        notes="strategy=profile_title",
    )


def test_a_value_is_written_with_its_class_resource_and_page() -> None:
    assert _value(_reading("Thing")) == {
        "type": "ceterms:Course",
        "resource_id": "catalog-example-edu_RAW101",
        "ctdl_property": PROP,
        "value": "Thing",
        "catalog_id": FOLDER,
        "source_url": "https://catalog.example.edu/x",
        "retrieved_at": "2026-09-17T14:20:05Z",
        "notes": "strategy=profile_title",
    }


def test_a_value_not_found_is_written_as_null() -> None:
    written = _value(_reading(None, reason="empty_title"))
    assert written["value"] is None
    assert "presence" not in written


def test_notes_say_how_the_value_was_read_and_why_it_was_not() -> None:
    assert reading_notes(_reading(None, "empty_title"), "courseleaf") == (
        "strategy=profile_title platform=courseleaf css=div > h1 "
        "reason=empty_title"
    )


def test_printed_text_skips_scripts_and_reads_a_break_as_a_space() -> None:
    soup = BeautifulSoup(
        "<h1>Intro<br>to <script>x()</script>Law&nbsp;</h1>", "html.parser"
    )
    assert printed_text(soup.h1) == "Intro to Law"


def test_an_element_inside_the_site_navigation_is_chrome() -> None:
    soup = BeautifulSoup(
        "<nav><ul><li><h2>Menu</h2></li></ul></nav><main><h2>T</h2></main>",
        "html.parser",
    )
    menu, title = soup.find_all("h2")
    assert inside_chrome(menu)
    assert not inside_chrome(title)


def test_a_css_path_finds_the_same_element_again() -> None:
    soup = BeautifulSoup(
        "<html><body><div><p>a</p><p>b</p></div></body></html>", "html.parser"
    )
    second = soup.find_all("p")[1]
    assert soup.select_one(css_path(second)) is second


# --- run_extraction, with a fake extractor ---------------------------------


def _three_occurrences(page: Page) -> list[Occurrence]:
    """Occurrences "1", "2" and "3", told apart by their css path."""
    return [
        Occurrence(element=page.soup, css_path=n, is_whole_page=n == "1")
        for n in ("1", "2", "3")
    ]


def _read_title(occurrence: Occurrence, page: Page) -> Reading:
    title = page.soup.title.get_text() if page.soup.title else ""
    if occurrence.css_path == "2":
        return Reading(None, None, "", "body", reason="no_candidate")
    return Reading(title, title, "fake", "title")


def _id_unless_third(
    occurrence: Occurrence, page: Page, catalog_id: str
) -> str | None:
    if occurrence.css_path == "3":
        return None
    return f"{catalog_id}_{page.stem.upper()}{occurrence.css_path}"


FAKE_COURSE = RdfClass(
    rdf_type="ceterms:Course",
    page_label="Course",
    occurrences=_three_occurrences,
    resource_id=_id_unless_third,
)
FAKE = Extractor(prop=PROP, classes=(FAKE_COURSE,), read=_read_title)


def _seed(store, profiles: list[dict], *, sample: list[str] | None = None):
    for profile in profiles:
        if profile.pop("_missing", False):
            continue
        seed_crawl_page(
            store,
            FOLDER,
            RUN,
            profile["stem"],
            f"<html><head><title>{profile['stem']}</title></head></html>",
            profile["url"],
        )
    store.put_text(
        discovery_key(FOLDER, RUN, DISCOVERY, PAGES_FILE),
        "\n".join(json.dumps(p) for p in profiles),
        "application/x-ndjson",
    )
    store.put_json(
        discovery_key(FOLDER, RUN, DISCOVERY, SUMMARY_FILE),
        {"platform": {"name": "courseleaf"}},
    )
    if sample is not None:
        store.put_json(
            discovery_key(FOLDER, RUN, DISCOVERY, sample_file_name("Course")),
            {"pages": [{"stem": stem} for stem in sample]},
        )


def _profile(stem: str, labels: list[str], **extra) -> dict:
    return {
        "stem": stem,
        "url": f"https://catalog.example.edu/{stem}",
        "labels": labels,
        "platform": "",
        **extra,
    }


def _run(store, extractor: Extractor = FAKE, **options) -> dict:
    return run_extraction(
        store,
        store,
        extractor,
        catalog_id=FOLDER,
        run_id=RUN,
        discovery_run_id=DISCOVERY,
        version="test",
        **options,
    )


def _written(store, resource_id: str) -> dict:
    return store.get_json(extract_resource_key(FOLDER, RUN, PROP, resource_id))


def test_values_go_under_extraction_report_by_property() -> None:
    assert extract_resource_key(FOLDER, RUN, PROP, "x_A1") == (
        f"{run_prefix(FOLDER, RUN)}/extraction_report/ex/ex_thing/x_A1.json"
    )


def test_only_pages_labelled_with_the_class_are_read(tmp_path: Path) -> None:
    store = open_store(str(tmp_path))
    _seed(
        store,
        [
            _profile("a", ["Course"]),
            _profile("b", ["Credential"]),
        ],
    )
    report = _run(store)
    assert report["pages_read"] == 1
    assert _written(store, f"{FOLDER}_A1")["value"] == "a"
    assert not store.exists(
        extract_resource_key(FOLDER, RUN, PROP, f"{FOLDER}_B1")
    )


def test_each_identified_resource_is_written_found_or_not(
    tmp_path: Path,
) -> None:
    store = open_store(str(tmp_path))
    _seed(store, [_profile("a", ["Course"])])
    report = _run(store)
    assert report["occurrences"] == 3
    assert report["resources_written"] == 2
    assert report["found"] == 1
    assert report["not_found"] == 1
    assert report["not_found_by_reason"] == {"no_candidate": 1}
    assert _written(store, f"{FOLDER}_A1")["value"] == "a"
    assert _written(store, f"{FOLDER}_A2")["value"] is None


def test_a_resource_with_no_id_is_counted_not_written(tmp_path: Path) -> None:
    store = open_store(str(tmp_path))
    _seed(store, [_profile("a", ["Course"])])
    report = _run(store)
    assert report["no_resource_id"] == 1
    (example,) = report["no_resource_id_examples"]
    assert example["url"] == "https://catalog.example.edu/a"
    assert not store.exists(
        extract_resource_key(FOLDER, RUN, PROP, f"{FOLDER}_A3")
    )


def test_a_repeated_resource_id_gets_a_suffix(tmp_path: Path) -> None:
    store = open_store(str(tmp_path))
    _seed(store, [_profile("a", ["Course"]), _profile("b", ["Course"])])
    same_id = RdfClass(
        "ceterms:Course",
        "Course",
        lambda page: [Occurrence(page.soup, "body", True)],
        lambda occurrence, page, catalog_id: f"{catalog_id}_SAME1",
    )
    report = _run(store, Extractor(PROP, (same_id,), _read_title))
    assert report["repeated_resource_ids"] == 1
    assert _written(store, f"{FOLDER}_SAME1")["value"] == "a"
    assert _written(store, f"{FOLDER}_SAME1-2")["value"] == "b"
    assert _written(store, f"{FOLDER}_SAME1-2")["resource_id"] == (
        f"{FOLDER}_SAME1-2"
    )


def test_the_site_platform_stands_in_for_a_page_without_one(
    tmp_path: Path,
) -> None:
    store = open_store(str(tmp_path))
    _seed(store, [_profile("a", ["Course"])])
    assert set(_run(store)["by_platform"]) == {"courseleaf"}


def test_a_missing_page_is_skipped_and_named(tmp_path: Path) -> None:
    store = open_store(str(tmp_path))
    _seed(store, [_profile("gone", ["Course"], _missing=True)])
    report = _run(store)
    assert report["skipped"] == [
        {
            "stem": "gone",
            "url": "https://catalog.example.edu/gone",
            "reason": "page_missing",
        }
    ]


def test_the_golden_sample_and_the_limit_narrow_the_pages(
    tmp_path: Path,
) -> None:
    store = open_store(str(tmp_path))
    _seed(
        store,
        [_profile(stem, ["Course"]) for stem in ("a", "b", "c")],
        sample=["b", "c"],
    )
    assert _run(store, only_golden_sample=True)["pages_read"] == 2
    assert _run(store, only_golden_sample=True, limit=1)["pages_read"] == 1


def test_the_report_says_whether_the_pages_were_limited(
    tmp_path: Path,
) -> None:
    """Scoring counts a baseline page extract never wrote as missing only
    when extract read every page it was given."""
    store = open_store(str(tmp_path))
    _seed(store, [_profile(stem, ["Course"]) for stem in ("a", "b")])
    assert _run(store)["limit"] is None
    assert _run(store, limit=1)["limit"] == 1


def test_the_report_is_written_beside_extraction_report(tmp_path: Path) -> None:
    store = open_store(str(tmp_path))
    _seed(store, [_profile("a", ["Course"])])
    report = _run(store)
    assert report["report_key"] == (
        f"{run_prefix(FOLDER, RUN)}/extraction-ex_thing-report.json"
    )
    saved = store.get_json(report["report_key"])
    assert saved["schema"] == "xtra-extraction-report-1"
    assert saved["property"] == PROP
    assert saved["class"] == ["ceterms:Course"]
    assert saved["by_class"] == {
        "ceterms:Course": {"occurrences": 3, "found": 1}
    }
    assert saved["resources_written"] == 2


def test_running_again_writes_the_same_files(tmp_path: Path) -> None:
    store = open_store(str(tmp_path))
    _seed(store, [_profile("a", ["Course"])])
    _run(store)
    first = _written(store, f"{FOLDER}_A1")
    _run(store)
    assert _written(store, f"{FOLDER}_A1") == first
    assert not store.exists(
        extract_resource_key(FOLDER, RUN, PROP, f"{FOLDER}_A1-2")
    )


def test_a_discovery_run_without_pages_jsonl_cannot_be_read(
    tmp_path: Path,
) -> None:
    store = open_store(str(tmp_path))
    with pytest.raises(ExtractionError, match="pages.jsonl"):
        _run(store)


def test_each_class_reads_its_own_pages(tmp_path: Path) -> None:
    store = open_store(str(tmp_path))
    _seed(store, [_profile("a", ["Course"]), _profile("p", ["Program"])])
    program = RdfClass(
        "ceterms:LearningProgram",
        "Program",
        lambda page: [Occurrence(page.soup, "body", True)],
        lambda occurrence, page, catalog_id: f"{catalog_id}_PROGRAM",
    )
    report = _run(store, Extractor(PROP, (FAKE_COURSE, program), _read_title))
    assert report["pages_read"] == 2
    assert set(report["by_class"]) == {
        "ceterms:Course",
        "ceterms:LearningProgram",
    }
    assert _written(store, f"{FOLDER}_PROGRAM")["type"] == (
        "ceterms:LearningProgram"
    )


def test_a_run_clears_what_an_earlier_run_wrote_for_its_property(
    tmp_path: Path,
) -> None:
    """A file no run writes any more would be scored as a resource."""
    store = open_store(str(tmp_path))
    _seed(store, [_profile("a", ["Course"])])
    stale = extract_resource_key(FOLDER, RUN, PROP, f"{FOLDER}_GONE1")
    store.put_json(stale, {"resource_id": f"{FOLDER}_GONE1"})
    report = _run(store)
    assert not store.exists(stale)
    assert report["files_cleared"] == 1
    assert _written(store, f"{FOLDER}_A1")["value"] == "a"


def test_clearing_leaves_other_properties_and_the_run_alone(
    tmp_path: Path,
) -> None:
    store = open_store(str(tmp_path))
    _seed(store, [_profile("a", ["Course"])])
    other = extract_resource_key(FOLDER, RUN, "ex:other", f"{FOLDER}_A1")
    beside = f"{run_prefix(FOLDER, RUN)}/extraction_report/note.json"
    for key in (other, beside):
        store.put_json(key, {})
    _run(store)
    assert store.exists(other)
    assert store.exists(beside)


def test_a_run_that_cannot_read_discovery_clears_nothing(
    tmp_path: Path,
) -> None:
    store = open_store(str(tmp_path))
    kept = extract_resource_key(FOLDER, RUN, PROP, f"{FOLDER}_A1")
    store.put_json(kept, {})
    with pytest.raises(ExtractionError):
        _run(store)
    assert store.exists(kept)
