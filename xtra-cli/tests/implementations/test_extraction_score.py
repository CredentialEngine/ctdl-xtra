from __future__ import annotations

from pathlib import Path

import pytest

from common.keys import extract_report_key, golden_record_key, record_key
from common.object_store import open_store
from implementations.extraction_score import (
    ExtractionScoreError,
    extracted_values,
    format_table,
    golden_entities,
    normalize,
    score_entity,
    score_extraction_run,
    score_page,
    value_score,
)

FOLDER = "avc-elumenapp-com-catalog-2026-27-welcome"
RUN = "2026-10-12T20:59:13Z"
STEM = "avc-elumenapp-com-catalog-2026-27-course-acct199-02f732419a"
URL = "https://avc.elumenapp.com/catalog/2026-27/course/acct199"
DESCRIPTION = (
    "Work Experience Education is supervised employment designed to "
    "provide students a realistic learning experience through work."
)


def golden_field(prop: str, value: object) -> dict:
    return {"ctdl_property": prop, "value": value, "source_url": URL}


def golden_acct199() -> list[dict]:
    return [
        golden_field("ceterms:identifier", "ACCT199"),
        golden_field("ceterms:name", "Work Experience Education"),
        golden_field("ceterms:description", DESCRIPTION),
        golden_field("ceterms:subjectWebpage", URL),
        golden_field("ceterms:lifeCycleStatusType", "Active"),
        golden_field("ceterms:inLanguage", "English"),
        golden_field("ceterms:codedNotation", "ACCT 199"),
        golden_field("ceterms:creditMinValue", "1.0"),
        golden_field("ceterms:creditMaxValue", "8.0"),
        golden_field("ceterms:creditUnitType", "Units"),
    ]


def prop(name: str, value: object) -> dict:
    return {"property": name, "value": value}


def record_of(*properties: dict, record_id: str = STEM) -> dict:
    return {
        "record_id": record_id,
        "source_url": URL,
        "ctdl_expected": {"properties": list(properties)},
    }


def outcomes_of(result: dict) -> dict[str, str]:
    return {f["ctdl_property"]: f["outcome"] for f in result["fields"]}


def test_a_record_holding_every_golden_value_scores_one() -> None:
    record = record_of(
        prop("ceterms:identifier", "ACCT199"),
        prop("ceterms:name", "Work Experience Education"),
        prop("ceterms:description", DESCRIPTION),
        prop("ceterms:lifeCycleStatusType", "Active"),
        prop("ceterms:inLanguage", "English"),
        prop("ceterms:codedNotation", "ACCT 199"),
        prop("ceterms:creditMinValue", 1),
        prop("ceterms:creditMaxValue", 8),
        prop("ceterms:creditUnitType", "Units"),
    )

    result = score_entity(golden_acct199(), record)

    assert result["score"] == 1.0
    assert result["by_outcome"]["match"] == 10


def test_a_property_the_extractor_never_emitted_counts_as_missing() -> None:
    record = record_of(prop("ceterms:name", "Work Experience Education"))

    result = score_entity(golden_acct199(), record)

    outcomes = outcomes_of(result)
    assert outcomes["ceterms:name"] == "match"
    assert outcomes["ceterms:identifier"] == "missing"
    assert outcomes["ceterms:inLanguage"] == "missing"
    # Only the name matches, and the page address fills subjectWebpage.
    assert result["score"] == 0.2


def test_case_and_whitespace_differences_still_match() -> None:
    record = record_of(prop("ceterms:name", "  work   experience education. "))

    result = score_entity(
        [golden_field("ceterms:name", "Work Experience Education")], record
    )

    assert result["score"] == 1.0


def test_a_printed_number_matches_the_same_number_as_text() -> None:
    assert value_score("1.0", 1) == 1.0
    assert value_score("8.0", "8") == 1.0
    assert value_score("1.0", 2) == 0.0


def test_a_code_matches_with_or_without_its_space() -> None:
    assert value_score("ACCT 199", "ACCT199") == 1.0


def test_a_description_missing_a_sentence_is_partial() -> None:
    long = DESCRIPTION + " The goal is to teach students skills and attitudes."
    record = record_of(prop("ceterms:description", DESCRIPTION))

    result = score_entity([golden_field("ceterms:description", long)], record)

    field = result["fields"][0]
    assert field["outcome"] == "partial"
    assert 0.6 <= field["score"] < 0.95


def test_a_different_value_is_wrong_not_missing() -> None:
    record = record_of(prop("ceterms:name", "Introduction to Welding"))

    result = score_entity(
        [golden_field("ceterms:name", "Work Experience Education")], record
    )

    assert outcomes_of(result) == {"ceterms:name": "wrong"}


def test_a_single_printed_credit_satisfies_min_and_max() -> None:
    record = record_of(prop("ceterms:creditValue", [{"ceterms:value": 3}]))

    result = score_entity(
        [
            golden_field("ceterms:creditMinValue", "3.0"),
            golden_field("ceterms:creditMaxValue", "3.0"),
        ],
        record,
    )

    assert result["score"] == 1.0


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
    result = score_entity(
        [golden_field("ceterms:subjectWebpage", URL)], record_of()
    )

    assert result["score"] == 1.0


def test_prerequisites_are_read_from_their_nested_name() -> None:
    record = record_of(
        prop("ceterms:requires", [{"ceterms:name": "MAT-048 or MAT-160"}])
    )

    result = score_entity(
        [golden_field("ceterms:requires", "MAT-048 or MAT-160")], record
    )

    assert result["score"] == 1.0


def test_one_extracted_value_satisfies_only_one_golden_value() -> None:
    record = record_of(prop("ceterms:requires", [{"ceterms:name": "MAT-048"}]))

    result = score_entity(
        [
            golden_field("ceterms:requires", "MAT-048"),
            golden_field("ceterms:requires", "MAT-160"),
            golden_field("ceterms:requires", "ENG-101"),
        ],
        record,
    )

    assert result["by_outcome"]["match"] == 1
    assert result["by_outcome"]["missing"] == 2


def test_the_best_candidate_wins_a_repeated_property() -> None:
    record = record_of(
        prop("ceterms:identifier", "OTHER"),
        prop("ceterms:identifier", "ACCT199"),
    )

    result = score_entity(
        [golden_field("ceterms:identifier", "ACCT199")], record
    )

    assert result["score"] == 1.0


def test_properties_the_golden_set_lacks_are_listed_and_cost_nothing() -> None:
    record = record_of(
        prop("ceterms:name", "Work Experience Education"),
        prop("ceterms:requires", [{"ceterms:name": "MAT-048"}]),
    )

    result = score_entity(
        [golden_field("ceterms:name", "Work Experience Education")], record
    )

    assert result["score"] == 1.0
    assert "ceterms:requires" in result["unscored_extras"]


def test_an_entity_with_no_record_scores_all_missing() -> None:
    page = score_page([golden_acct199()], [])

    assert page["score"] == 0.0
    assert page["entities"][0]["by_outcome"]["missing"] == 10
    assert page["entities"][0]["record_id"] is None


def test_golden_entities_pair_with_records_in_order() -> None:
    main = record_of(prop("ceterms:name", "Main"), record_id=STEM)
    extra = record_of(
        prop("ceterms:name", "Second"), record_id=f"{STEM}--competencyframework"
    )

    page = score_page(
        [
            [golden_field("ceterms:name", "Main")],
            [golden_field("ceterms:name", "Second")],
            [golden_field("ceterms:name", "Third")],
        ],
        [main, extra],
    )

    assert [e["score"] for e in page["entities"]] == [1.0, 1.0, 0.0]
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
def test_a_malformed_golden_file_is_refused(payload: object) -> None:
    with pytest.raises(ValueError):
        golden_entities(payload)


def test_a_single_entity_object_is_accepted() -> None:
    assert golden_entities({"fields": [golden_field("ceterms:name", "x")]}) == [
        [golden_field("ceterms:name", "x")]
    ]


def test_normalize_folds_width_case_and_trailing_punctuation() -> None:
    assert normalize("ＡＣＣＴ  199.") == "acct 199"


class Stores:
    """A records store and a golden store, side by side on disk."""

    def __init__(self, tmp_path: Path) -> None:
        self.records = open_store(str(tmp_path / "records"))
        self.golden = open_store(str(tmp_path / "golden"))

    def put_record(self, record: dict) -> None:
        self.records.put_json(
            record_key(FOLDER, RUN, record["record_id"]), record
        )

    def put_golden(self, stem: str, payload: object) -> None:
        self.golden.put_json(golden_record_key(FOLDER, RUN, stem), payload)

    def put_skipped(self, *stems: str) -> None:
        self.records.put_json(
            extract_report_key(FOLDER, RUN),
            {
                "skipped": [
                    {"stem": s, "reason": "multi_course_page"} for s in stems
                ]
            },
        )

    def score(self) -> dict:
        return score_extraction_run(self.records, self.golden, FOLDER, RUN)


@pytest.fixture
def stores(tmp_path: Path) -> Stores:
    return Stores(tmp_path)


def test_a_run_scores_each_golden_page_against_its_record(
    stores: Stores,
) -> None:
    stores.put_golden(STEM, [{"fields": golden_acct199()}])
    stores.put_record(
        record_of(prop("ceterms:name", "Work Experience Education"))
    )

    report = stores.score()

    assert report["pages_scored"] == 1
    assert report["overall"] == 0.2
    assert report["by_property"]["ceterms:name"]["match"] == 1
    assert report["by_property"]["ceterms:inLanguage"]["missing"] == 1


def test_a_page_extract_skipped_scores_zero(stores: Stores) -> None:
    stores.put_golden(STEM, [{"fields": golden_acct199()}])
    stores.put_skipped(STEM)

    report = stores.score()

    assert report["pages_skipped"] == 1
    assert report["overall"] == 0.0
    assert report["pages"][0]["status"] == "skipped"


def test_a_page_extract_never_considered_is_left_out_of_the_mean(
    stores: Stores,
) -> None:
    other = "other-page-0000000000"
    stores.put_golden(STEM, [{"fields": [golden_field("ceterms:name", "A")]}])
    stores.put_golden(other, [{"fields": [golden_field("ceterms:name", "B")]}])
    stores.put_record(record_of(prop("ceterms:name", "A")))

    report = stores.score()

    assert report["overall"] == 1.0
    assert report["out_of_scope"] == [other]
    assert report["pages_out_of_scope"] == 1


def test_a_malformed_golden_file_is_reported_and_skipped(
    stores: Stores,
) -> None:
    other = "other-page-0000000000"
    stores.put_golden(STEM, [{"fields": [golden_field("ceterms:name", "A")]}])
    stores.put_golden(other, [{"fields": []}])
    stores.put_record(record_of(prop("ceterms:name", "A")))

    report = stores.score()

    assert report["overall"] == 1.0
    assert [m["stem"] for m in report["malformed"]] == [other]


def test_an_extra_entity_record_belongs_to_its_page(stores: Stores) -> None:
    stores.put_golden(
        STEM,
        [
            {"fields": [golden_field("ceterms:name", "Main")]},
            {"fields": [golden_field("ceterms:name", "Second")]},
        ],
    )
    stores.put_record(record_of(prop("ceterms:name", "Main")))
    stores.put_record(
        record_of(
            prop("ceterms:name", "Second"),
            record_id=f"{STEM}--competencyframework",
        )
    )

    assert stores.score()["overall"] == 1.0


def test_a_run_with_no_golden_files_is_an_error(stores: Stores) -> None:
    stores.put_record(record_of(prop("ceterms:name", "A")))

    with pytest.raises(ExtractionScoreError, match="no golden files"):
        stores.score()


def test_a_golden_file_filed_under_the_wrong_name_is_not_a_golden_set(
    stores: Stores,
) -> None:
    stores.golden.put_json(
        golden_record_key(FOLDER, RUN, STEM).replace(
            f"/{STEM}.json", "/notes.json"
        ),
        [{"fields": [golden_field("ceterms:name", "A")]}],
    )

    with pytest.raises(ExtractionScoreError):
        stores.score()


def test_the_table_names_the_overall_score_and_each_property(
    stores: Stores,
) -> None:
    stores.put_golden(STEM, [{"fields": golden_acct199()}])
    stores.put_record(
        record_of(prop("ceterms:name", "Work Experience Education"))
    )

    table = format_table(stores.score())

    assert "Extraction score: 0.2000" in table
    assert "ceterms:inLanguage" in table
    assert STEM in table
