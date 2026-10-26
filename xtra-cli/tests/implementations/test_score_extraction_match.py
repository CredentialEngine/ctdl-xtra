from __future__ import annotations

from pathlib import Path

import pytest

from common.keys import baseline_record_key, extract_report_key, record_key
from common.object_store import open_store
from implementations.score_extraction_match import (
    MODE_EXACT,
    MODE_PARTIAL,
    PARTIAL_THRESHOLD,
    ExtractionMatchError,
    baseline_entities,
    extracted_values,
    format_table,
    is_exact,
    match_entity,
    match_extraction_run,
    match_page,
    normalize,
    similarity,
)

FOLDER = "avc-elumenapp-com-catalog-2026-27-welcome"
RUN = "2026-10-12T20:59:13Z"
STEM = "avc-elumenapp-com-catalog-2026-27-course-acct199-02f732419a"
URL = "https://avc.elumenapp.com/catalog/2026-27/course/acct199"
DESCRIPTION = (
    "Work Experience Education is supervised employment designed to "
    "provide students a realistic learning experience through work."
)


def baseline_field(prop: str, value: object) -> dict:
    return {"ctdl_property": prop, "value": value, "source_url": URL}


def baseline_acct199() -> list[dict]:
    return [
        baseline_field("ceterms:identifier", "ACCT199"),
        baseline_field("ceterms:name", "Work Experience Education"),
        baseline_field("ceterms:description", DESCRIPTION),
        baseline_field("ceterms:subjectWebpage", URL),
        baseline_field("ceterms:lifeCycleStatusType", "Active"),
        baseline_field("ceterms:inLanguage", "English"),
        baseline_field("ceterms:codedNotation", "ACCT 199"),
        baseline_field("ceterms:creditMinValue", "1.0"),
        baseline_field("ceterms:creditMaxValue", "8.0"),
        baseline_field("ceterms:creditUnitType", "Units"),
    ]


def prop(name: str, value: object) -> dict:
    return {"property": name, "value": value}


def record_of(*properties: dict, record_id: str = STEM) -> dict:
    return {
        "record_id": record_id,
        "source_url": URL,
        "expected": {p["property"]: p["value"] for p in properties},
    }


def outcomes_of(result: dict) -> dict[str, str]:
    return {f["ctdl_property"]: f["outcome"] for f in result["fields"]}


def exact_acct199_record() -> dict:
    return record_of(
        prop("ceterms:identifier", "ACCT199"),
        prop("ceterms:name", "Work Experience Education"),
        prop("ceterms:description", DESCRIPTION),
        prop("ceterms:lifeCycleStatusType", "Active"),
        prop("ceterms:inLanguage", "English"),
        prop("ceterms:codedNotation", "ACCT 199"),
        prop("ceterms:creditMinValue", "1.0"),
        prop("ceterms:creditMaxValue", "8.0"),
        prop("ceterms:creditUnitType", "Units"),
    )


def test_a_record_holding_every_baseline_value_matches_exactly() -> None:
    result = match_entity(
        baseline_acct199(), exact_acct199_record(), MODE_EXACT
    )

    assert set(outcomes_of(result).values()) == {"match"}
    assert len(result["fields"]) == 10
    assert "score" not in result


def test_a_property_the_extractor_never_emitted_is_missing() -> None:
    record = record_of(prop("ceterms:name", "Work Experience Education"))

    result = match_entity(baseline_acct199(), record, MODE_EXACT)

    outcomes = outcomes_of(result)
    assert outcomes["ceterms:name"] == "match"
    assert outcomes["ceterms:identifier"] == "missing"
    assert outcomes["ceterms:inLanguage"] == "missing"
    missing = [f for f in result["fields"] if f["outcome"] == "missing"]
    assert missing[0]["similarity"] is None


def test_exact_means_identical_so_case_and_spacing_are_mismatches() -> None:
    record = record_of(prop("ceterms:name", "  work   experience education. "))

    result = match_entity(
        [baseline_field("ceterms:name", "Work Experience Education")],
        record,
        MODE_EXACT,
    )

    field = result["fields"][0]
    assert field["outcome"] == "mismatch"
    assert field["similarity"] == 1.0


def test_is_exact_compares_printed_values_only() -> None:
    assert is_exact("ACCT199", "ACCT199")
    assert is_exact("8", 8)
    assert not is_exact("ACCT 199", "ACCT199")
    assert not is_exact("Units", "units")
    assert not is_exact("1.0", 1)


def test_a_printed_number_is_the_same_number_as_text() -> None:
    assert similarity("1.0", 1) == 1.0
    assert similarity("8.0", "8") == 1.0
    assert similarity("1.0", 2) == 0.0


def test_a_code_is_close_with_or_without_its_space() -> None:
    assert similarity("ACCT 199", "ACCT199") == 1.0


def test_partial_sets_exact_matches_aside_and_judges_the_rest() -> None:
    long = DESCRIPTION + " The goal is to teach students skills."
    record = record_of(
        prop("ceterms:name", "Work Experience Education"),
        prop("ceterms:description", DESCRIPTION),
    )

    result = match_entity(
        [
            baseline_field("ceterms:name", "Work Experience Education"),
            baseline_field("ceterms:description", long),
        ],
        record,
        MODE_PARTIAL,
    )

    assert result["excluded_exact"] == 1
    assert outcomes_of(result) == {"ceterms:description": "partial"}
    assert result["fields"][0]["similarity"] >= PARTIAL_THRESHOLD


def test_a_different_value_is_wrong_in_partial_not_missing() -> None:
    record = record_of(prop("ceterms:name", "Introduction to Welding"))

    result = match_entity(
        [baseline_field("ceterms:name", "Work Experience Education")],
        record,
        MODE_PARTIAL,
    )

    assert outcomes_of(result) == {"ceterms:name": "wrong"}


def test_the_partial_threshold_is_eighty_percent() -> None:
    assert PARTIAL_THRESHOLD == 0.8
    baseline = "a" * 10
    at = record_of(prop("ceterms:name", "a" * 8 + "bb"))
    below = record_of(prop("ceterms:name", "a" * 7 + "bbb"))
    fields = [baseline_field("ceterms:name", baseline)]

    assert outcomes_of(match_entity(fields, at, MODE_PARTIAL)) == {
        "ceterms:name": "partial"
    }
    assert outcomes_of(match_entity(fields, below, MODE_PARTIAL)) == {
        "ceterms:name": "wrong"
    }


def test_a_single_printed_credit_satisfies_min_and_max() -> None:
    record = record_of(prop("ceterms:creditValue", [{"ceterms:value": 3}]))

    result = match_entity(
        [
            baseline_field("ceterms:creditMinValue", 3),
            baseline_field("ceterms:creditMaxValue", 3),
        ],
        record,
        MODE_EXACT,
    )

    assert set(outcomes_of(result).values()) == {"match"}


def test_a_flat_credit_value_satisfies_min_max_and_itself() -> None:
    record = record_of(prop("ceterms:creditValue", 5.0))

    result = match_entity(
        [
            baseline_field("ceterms:creditMinValue", "5.0"),
            baseline_field("ceterms:creditMaxValue", "5.0"),
            baseline_field("ceterms:creditValue", "5.0"),
        ],
        record,
        MODE_EXACT,
    )

    assert set(outcomes_of(result).values()) == {"match"}


def test_a_record_without_expected_is_all_missing() -> None:
    record = {
        "record_id": STEM,
        "source_url": URL,
        "ctdl_expected": {
            "properties": [prop("ceterms:name", "Work Experience Education")]
        },
    }

    result = match_entity(
        [baseline_field("ceterms:name", "Work Experience Education")],
        record,
        MODE_EXACT,
    )

    assert outcomes_of(result) == {"ceterms:name": "missing"}


def test_a_list_value_answers_several_baseline_values() -> None:
    record = record_of(prop("ceterms:requires", ["MAT-048", "MAT-160"]))

    result = match_entity(
        [
            baseline_field("ceterms:requires", "MAT-048"),
            baseline_field("ceterms:requires", "MAT-160"),
        ],
        record,
        MODE_EXACT,
    )

    assert set(outcomes_of(result).values()) == {"match"}


def test_a_credit_range_fills_min_and_max_separately() -> None:
    record = record_of(
        prop(
            "ceterms:creditValue",
            [{"ceterms:minValue": 1, "ceterms:maxValue": 8}],
        )
    )

    pool = extracted_values(record)

    assert pool["ceterms:creditMinValue"] == [1]
    assert pool["ceterms:creditMaxValue"] == [8]


def test_the_page_address_stands_in_for_subject_webpage() -> None:
    result = match_entity(
        [baseline_field("ceterms:subjectWebpage", URL)],
        record_of(),
        MODE_EXACT,
    )

    assert outcomes_of(result) == {"ceterms:subjectWebpage": "match"}


def test_prerequisites_are_read_from_their_nested_name() -> None:
    record = record_of(
        prop("ceterms:requires", [{"ceterms:name": "MAT-048 or MAT-160"}])
    )

    result = match_entity(
        [baseline_field("ceterms:requires", "MAT-048 or MAT-160")],
        record,
        MODE_EXACT,
    )

    assert outcomes_of(result) == {"ceterms:requires": "match"}


def test_one_extracted_value_answers_only_one_baseline_value() -> None:
    record = record_of(prop("ceterms:requires", [{"ceterms:name": "MAT-048"}]))

    result = match_entity(
        [
            baseline_field("ceterms:requires", "MAT-048"),
            baseline_field("ceterms:requires", "MAT-160"),
            baseline_field("ceterms:requires", "ENG-101"),
        ],
        record,
        MODE_EXACT,
    )

    outcomes = [f["outcome"] for f in result["fields"]]
    assert outcomes == ["match", "missing", "missing"]


def test_the_exact_candidate_wins_a_repeated_property() -> None:
    record = record_of(prop("ceterms:identifier", ["OTHER", "ACCT199"]))

    result = match_entity(
        [baseline_field("ceterms:identifier", "ACCT199")], record, MODE_EXACT
    )

    assert outcomes_of(result) == {"ceterms:identifier": "match"}


def test_properties_the_baseline_lacks_are_listed_and_cost_nothing() -> None:
    record = record_of(
        prop("ceterms:name", "Work Experience Education"),
        prop("ceterms:requires", [{"ceterms:name": "MAT-048"}]),
    )

    result = match_entity(
        [baseline_field("ceterms:name", "Work Experience Education")],
        record,
        MODE_EXACT,
    )

    assert outcomes_of(result) == {"ceterms:name": "match"}
    assert "ceterms:requires" in result["unscored_extras"]


def test_an_entity_with_no_record_is_all_missing() -> None:
    page = match_page([baseline_acct199()], [], MODE_EXACT)

    entity = page["entities"][0]
    assert {f["outcome"] for f in entity["fields"]} == {"missing"}
    assert entity["record_id"] is None


def test_baseline_entities_pair_with_records_in_order() -> None:
    main = record_of(prop("ceterms:name", "Main"), record_id=STEM)
    extra = record_of(
        prop("ceterms:name", "Second"), record_id=f"{STEM}--competencyframework"
    )

    page = match_page(
        [
            [baseline_field("ceterms:name", "Main")],
            [baseline_field("ceterms:name", "Second")],
            [baseline_field("ceterms:name", "Third")],
        ],
        [main, extra],
        MODE_EXACT,
    )

    assert [e["fields"][0]["outcome"] for e in page["entities"]] == [
        "match",
        "match",
        "missing",
    ]
    assert page["entities"][1]["record_id"] == f"{STEM}--competencyframework"


@pytest.mark.parametrize(
    "payload",
    [
        [],
        "text",
        [{"fields": []}],
        [{"nofields": 1}],
        [{"fields": [{"value": "x"}]}],
        [{"fields": [{"ctdl_property": "ceterms:name"}]}],
    ],
)
def test_a_malformed_baseline_file_is_refused(payload: object) -> None:
    with pytest.raises(ValueError):
        baseline_entities(payload)


def test_a_single_entity_object_is_accepted() -> None:
    field = baseline_field("ceterms:name", "x")
    assert baseline_entities({"fields": [field]}) == [[field]]


def test_normalize_folds_width_case_and_trailing_punctuation() -> None:
    assert normalize("ＡＣＣＴ  199.") == "acct 199"


class Stores:
    """A records store and a baseline store, side by side on disk."""

    def __init__(self, tmp_path: Path) -> None:
        self.records = open_store(str(tmp_path / "records"))
        self.baseline = open_store(str(tmp_path / "baseline"))

    def put_record(self, record: dict) -> None:
        self.records.put_json(
            record_key(FOLDER, RUN, record["record_id"]), record
        )

    def put_baseline(self, stem: str, payload: object) -> None:
        self.baseline.put_json(baseline_record_key(FOLDER, RUN, stem), payload)

    def put_skipped(self, *stems: str) -> None:
        self.records.put_json(
            extract_report_key(FOLDER, RUN),
            {
                "skipped": [
                    {"stem": s, "reason": "multi_course_page"} for s in stems
                ]
            },
        )

    def match(self, mode: str = MODE_EXACT) -> dict:
        return match_extraction_run(
            self.records, self.baseline, FOLDER, RUN, mode
        )


@pytest.fixture
def stores(tmp_path: Path) -> Stores:
    return Stores(tmp_path)


def test_an_exact_run_counts_outcomes_and_the_exact_rate(
    stores: Stores,
) -> None:
    stores.put_baseline(STEM, [{"fields": baseline_acct199()}])
    stores.put_record(
        record_of(prop("ceterms:name", "Work Experience Education"))
    )

    report = stores.match()

    assert report["mode"] == "exact"
    assert report["pages_scored"] == 1
    assert report["fields_total"] == 10
    # The name matches, and the page address fills subjectWebpage.
    assert report["outcomes"] == {"match": 2, "mismatch": 0, "missing": 8}
    assert report["exact_match_rate"] == 0.2
    assert report["by_property"]["ceterms:name"]["match"] == 1
    assert report["by_property"]["ceterms:inLanguage"]["missing"] == 1


def test_a_report_never_carries_an_average(stores: Stores) -> None:
    stores.put_baseline(STEM, [{"fields": baseline_acct199()}])
    stores.put_record(exact_acct199_record())

    for mode in (MODE_EXACT, MODE_PARTIAL):
        report = stores.match(mode)
        assert "overall" not in report
        assert all("score" not in page for page in report["pages"])
        assert all(
            "score" not in stats for stats in report["by_property"].values()
        )


def test_the_outliers_list_every_non_match_worst_first(
    stores: Stores,
) -> None:
    stores.put_baseline(
        STEM,
        [
            {
                "fields": [
                    baseline_field("ceterms:name", "Work Experience"),
                    baseline_field("ceterms:description", "Describes work."),
                    baseline_field("ceterms:inLanguage", "English"),
                    baseline_field("ceterms:codedNotation", "ACCT 199"),
                ]
            }
        ],
    )
    stores.put_record(
        record_of(
            prop("ceterms:name", "Work Experience"),
            prop("ceterms:description", "Describes working."),
            prop("ceterms:codedNotation", "Welding"),
        )
    )

    outliers = stores.match()["outliers"]

    assert [o["ctdl_property"] for o in outliers] == [
        "ceterms:inLanguage",
        "ceterms:codedNotation",
        "ceterms:description",
    ]
    assert [o["outcome"] for o in outliers] == [
        "missing",
        "mismatch",
        "mismatch",
    ]
    assert outliers[0]["stem"] == STEM
    assert outliers[2]["baseline_value"] == "Describes work."
    assert outliers[2]["extracted_value"] == "Describes working."


def test_a_partial_run_leaves_the_exact_matches_out(stores: Stores) -> None:
    stores.put_baseline(
        STEM,
        [
            {
                "fields": [
                    baseline_field("ceterms:name", "Work Experience"),
                    baseline_field("ceterms:description", "Describes work."),
                ]
            }
        ],
    )
    stores.put_record(
        record_of(
            prop("ceterms:name", "Work Experience"),
            prop("ceterms:description", "Describes working."),
        )
    )

    report = stores.match(MODE_PARTIAL)

    assert report["mode"] == "partial"
    assert report["partial_threshold"] == PARTIAL_THRESHOLD
    assert report["excluded_exact"] == 1
    assert report["fields_total"] == 1
    assert report["outcomes"] == {"partial": 1, "wrong": 0, "missing": 0}
    assert "exact_match_rate" not in report
    assert "ceterms:name" not in report["by_property"]


def test_a_page_extract_skipped_is_all_missing(stores: Stores) -> None:
    stores.put_baseline(STEM, [{"fields": baseline_acct199()}])
    stores.put_skipped(STEM)

    report = stores.match()

    assert report["pages_skipped"] == 1
    assert report["outcomes"]["missing"] == 10
    assert report["pages"][0]["status"] == "skipped"


def test_a_page_extract_never_considered_is_not_counted(
    stores: Stores,
) -> None:
    other = "other-page-0000000000"
    stores.put_baseline(
        STEM, [{"fields": [baseline_field("ceterms:name", "A")]}]
    )
    stores.put_baseline(
        other, [{"fields": [baseline_field("ceterms:name", "B")]}]
    )
    stores.put_record(record_of(prop("ceterms:name", "A")))

    report = stores.match()

    assert report["fields_total"] == 1
    assert report["out_of_scope"] == [other]
    assert report["pages_out_of_scope"] == 1


def test_a_malformed_baseline_file_is_reported_and_skipped(
    stores: Stores,
) -> None:
    other = "other-page-0000000000"
    stores.put_baseline(
        STEM, [{"fields": [baseline_field("ceterms:name", "A")]}]
    )
    stores.put_baseline(other, [{"fields": []}])
    stores.put_record(record_of(prop("ceterms:name", "A")))

    report = stores.match()

    assert report["fields_total"] == 1
    assert [m["stem"] for m in report["malformed"]] == [other]


def test_pages_list_the_one_with_most_non_exact_fields_first(
    stores: Stores,
) -> None:
    other = "other-page-0000000000"
    stores.put_baseline(
        STEM, [{"fields": [baseline_field("ceterms:name", "A")]}]
    )
    stores.put_baseline(
        other,
        [
            {
                "fields": [
                    baseline_field("ceterms:name", "B"),
                    baseline_field("ceterms:inLanguage", "English"),
                ]
            }
        ],
    )
    stores.put_record(record_of(prop("ceterms:name", "A")))
    stores.put_record(record_of(prop("ceterms:name", "B"), record_id=other))

    pages = stores.match()["pages"]

    assert [p["stem"] for p in pages] == [other, STEM]
    assert pages[0]["not_exact"] == 1


def test_an_extra_entity_record_belongs_to_its_page(stores: Stores) -> None:
    stores.put_baseline(
        STEM,
        [
            {"fields": [baseline_field("ceterms:name", "Main")]},
            {"fields": [baseline_field("ceterms:name", "Second")]},
        ],
    )
    stores.put_record(record_of(prop("ceterms:name", "Main")))
    stores.put_record(
        record_of(
            prop("ceterms:name", "Second"),
            record_id=f"{STEM}--competencyframework",
        )
    )

    assert stores.match()["exact_match_rate"] == 1.0


def test_a_run_with_no_baseline_files_is_an_error(stores: Stores) -> None:
    stores.put_record(record_of(prop("ceterms:name", "A")))

    with pytest.raises(ExtractionMatchError, match="no baseline files"):
        stores.match()


def test_a_baseline_file_filed_under_the_wrong_name_is_ignored(
    stores: Stores,
) -> None:
    stores.baseline.put_json(
        baseline_record_key(FOLDER, RUN, STEM).replace(
            f"/{STEM}.json", "/notes.json"
        ),
        [{"fields": [baseline_field("ceterms:name", "A")]}],
    )

    with pytest.raises(ExtractionMatchError):
        stores.match()


def test_the_exact_table_shows_counts_the_rate_and_the_outliers(
    stores: Stores,
) -> None:
    stores.put_baseline(STEM, [{"fields": baseline_acct199()}])
    stores.put_record(
        record_of(prop("ceterms:name", "Work Experience Education"))
    )

    table = format_table(stores.match())

    assert "Extraction match (exact)" in table
    assert "exact match rate 0.2000" in table
    assert "ceterms:inLanguage" in table
    assert "Outliers, worst first (8 of 8)" in table
    assert STEM in table


def test_the_partial_table_names_the_threshold(stores: Stores) -> None:
    stores.put_baseline(STEM, [{"fields": baseline_acct199()}])
    stores.put_record(exact_acct199_record())

    table = format_table(stores.match(MODE_PARTIAL))

    assert "Extraction match (partial)" in table
    assert "partial at 0.8 similarity" in table
