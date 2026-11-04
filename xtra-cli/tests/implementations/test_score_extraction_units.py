"""Units, every outcome, found and right (sme-fixes spec §8).

ACCT199's "Units and Hours" card is the worked example: the golden answer
is four duration objects, and three rules are scored against it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from common.keys import baseline_record_key, record_key
from common.object_store import open_store
from implementations.score_extraction_match import (
    MODE_EXACT,
    MODE_PARTIAL,
    REPORT_SCHEMA,
    extracted_claims,
    format_table,
    match_entity,
    match_extraction_run,
)

FOLDER = "avc-elumenapp-com-catalog-2026-27-welcome"
RUN = "2026-10-12T20:59:13Z"
STEM = "avc-elumenapp-com-catalog-2026-27-course-acct199-02f732419a"
URL = "https://avc.elumenapp.com/catalog/2026-27/course/acct199"
DURATION = "ceterms:estimatedDuration"
DESC = "ceterms:description"
TIME = "ceterms:timeRequired"

IN_CLASS = "Total Course In-Class (Contact) Hours"
OUT_OF_CLASS = "Total Course Out-of-Class Hours"
LECTURE = "Total Course Lecture Hours"
LAB = "Total Course Lab Hours"


def duration(description: str, time: str) -> dict:
    return {DESC: description, TIME: time}


GOLDEN_DURATIONS = [
    duration(IN_CLASS, "54.0 - 432.0"),
    duration(OUT_OF_CLASS, "0.0 - 0.0"),
    duration(LECTURE, "0.0"),
    duration(LAB, "432.0"),
]
RULE_B = list(GOLDEN_DURATIONS)
RULE_A = [*GOLDEN_DURATIONS, duration("Minimum Credit Units", "1.0")]
RULE_C = [
    duration(IN_CLASS, "0.0 - 0.0"),
    duration(OUT_OF_CLASS, "54.0 - 432.0"),
    duration(LECTURE, "0.0"),
    duration(LAB, "432.0"),
]


def field(prop: str, value: object, **extra: object) -> dict:
    return {"ctdl_property": prop, "value": value, "source_url": URL, **extra}


def absent(prop: str) -> dict:
    return field(prop, None, absent=True, location=None)


def golden_durations() -> list[dict]:
    return [field(DURATION, d) for d in GOLDEN_DURATIONS]


def record(expected: dict) -> dict:
    return {"record_id": STEM, "source_url": URL, "expected": expected}


def units(result: dict) -> list[str]:
    return sorted(u["outcome"] for u in result["units"])


class Stores:
    def __init__(self, tmp_path: Path) -> None:
        self.records = open_store(str(tmp_path / "records"))
        self.baseline = open_store(str(tmp_path / "baseline"))

    def put(self, fields: list[dict], expected: dict) -> None:
        self.baseline.put_json(
            baseline_record_key(FOLDER, RUN, STEM), [{"fields": fields}]
        )
        self.records.put_json(record_key(FOLDER, RUN, STEM), record(expected))

    def match(self, mode: str = MODE_EXACT) -> dict:
        return match_extraction_run(
            self.records, self.baseline, FOLDER, RUN, mode
        )


@pytest.fixture
def stores(tmp_path: Path) -> Stores:
    return Stores(tmp_path)


# --- the ACCT199 examples ---------------------------------------------------


def test_rule_b_is_exact_four_of_four_found_and_right(stores: Stores) -> None:
    stores.put(golden_durations(), {DURATION: RULE_B})

    report = stores.match()

    stats = report["by_property"][DURATION]
    assert (stats["golden"], stats["extracted"], stats["match"]) == (4, 4, 4)
    assert (stats["found"], stats["right"]) == (1.0, 1.0)
    assert stats["entities_exact"] == 1.0
    assert report["extras"]["count"] == 0


def test_rule_a_grabs_too_much_found_four_of_four_right_four_of_five(
    stores: Stores,
) -> None:
    stores.put(golden_durations(), {DURATION: RULE_A})

    report = stores.match()

    stats = report["by_property"][DURATION]
    assert (stats["match"], stats["extra"]) == (4, 1)
    assert (stats["golden"], stats["extracted"]) == (4, 5)
    assert stats["found"] == 1.0
    assert stats["right"] == 0.8
    assert stats["entities_exact"] == 0.0
    [extra] = report["extras"]["outliers"]
    assert extra["extracted_value"] == duration("Minimum Credit Units", "1.0")
    assert extra["unit"] == "object"
    # exact_match_rate stays match / golden units: extras don't touch it
    assert report["exact_match_rate"] == 1.0


def test_rule_c_mixes_up_pairs_found_two_of_four_right_two_of_four(
    stores: Stores,
) -> None:
    stores.put(golden_durations(), {DURATION: RULE_C})

    report = stores.match()

    stats = report["by_property"][DURATION]
    assert (stats["match"], stats["wrong"], stats["extra"]) == (2, 2, 0)
    assert (stats["found"], stats["right"]) == (0.5, 0.5)
    wrong = [o for o in report["outliers"] if o["unit"] == "object"]
    assert {o["baseline_value"][DESC] for o in wrong} == {
        IN_CLASS,
        OUT_OF_CLASS,
    }
    one = next(o for o in wrong if o["baseline_value"][DESC] == IN_CLASS)
    # paired by the key field, so the description is exact and the time not
    assert one["extracted_value"] == duration(IN_CLASS, "0.0 - 0.0")
    assert one["object_fields"][DESC]["exact"] is True
    assert one["object_fields"][TIME]["exact"] is False
    assert one["similarity"] < 0.8
    assert one["outcome"] == "mismatch"


def test_scored_as_loose_values_all_three_rules_looked_perfect() -> None:
    """Why objects: flattened, the swapped times of rule C all appear."""
    flat = [d[TIME] for d in RULE_C]
    assert sorted(flat) == sorted(d[TIME] for d in GOLDEN_DURATIONS)


# --- every outcome ----------------------------------------------------------


def test_match_partial_wrong_missing_and_extra_for_values() -> None:
    golden = [
        field("ceterms:name", "Work Experience Education"),
        field("ceterms:description", "Supervised employment for students."),
        field("ceterms:codedNotation", "ACCT 199"),
        field("ceterms:identifier", "ACCT199"),
    ]
    result = match_entity(
        golden,
        record(
            {
                "ceterms:name": "Work Experience Education",
                "ceterms:description": "Supervised employment for student",
                "ceterms:codedNotation": ["MATH 100", "ACCT 199", "BIO 1"],
            }
        ),
        MODE_PARTIAL,
    )
    by = {f["ctdl_property"]: f["outcome"] for f in result["fields"]}
    assert by == {
        "ceterms:description": "partial",
        "ceterms:identifier": "missing",
    }
    assert units(result) == [
        "extra",
        "extra",
        "match",
        "match",
        "missing",
        "partial",
    ]
    assert {e["extracted_value"] for e in result["extras"]} == {
        "MATH 100",
        "BIO 1",
    }


def test_a_value_far_from_the_golden_one_is_wrong() -> None:
    result = match_entity(
        [field("ceterms:name", "Work Experience Education")],
        record({"ceterms:name": "Basket Weaving"}),
        MODE_PARTIAL,
    )
    assert units(result) == ["wrong"]


def test_an_object_with_every_field_close_is_partial() -> None:
    result = match_entity(
        [field(DURATION, duration(LECTURE, "54.0"))],
        record({DURATION: [duration("Total Course Lecture Hours:", "54.0")]}),
        MODE_PARTIAL,
    )
    [only] = result["fields"]
    assert only["outcome"] == "partial"
    assert only["object_fields"][DESC]["similarity"] >= 0.8


def test_an_object_cut_short_is_wrong() -> None:
    result = match_entity(
        [field(DURATION, duration(IN_CLASS, "54.0 - 432.0"))],
        record({DURATION: [duration(IN_CLASS, "54.0")]}),
        MODE_PARTIAL,
    )
    assert units(result) == ["wrong"]


def test_a_golden_object_with_no_partner_is_missing() -> None:
    result = match_entity(
        golden_durations(), record({DURATION: RULE_B[:3]}), MODE_EXACT
    )
    assert units(result) == ["match", "match", "match", "missing"]


def test_extras_only_count_for_properties_the_entity_covers() -> None:
    result = match_entity(
        [field("ceterms:name", "Work Experience Education")],
        record(
            {
                "ceterms:name": "Work Experience Education",
                DURATION: RULE_B,
            }
        ),
        MODE_EXACT,
    )
    assert units(result) == ["match"]
    assert DURATION in result["unscored_extras"]


# --- not on the page ----------------------------------------------------------


def test_golden_absent_against_the_extractors_null_is_a_match() -> None:
    result = match_entity(
        [field("ceterms:name", "X"), absent("ceterms:prerequisite")],
        record({"ceterms:name": "X", "ceterms:prerequisite": None}),
        MODE_EXACT,
    )
    assert units(result) == ["match", "match"]
    one = next(f for f in result["fields"] if f["unit"] == "absent")
    assert one["outcome"] == "match"
    assert one["extracted_value"] is None


def test_golden_absent_with_no_key_in_the_record_is_unsure() -> None:
    result = match_entity(
        [field("ceterms:name", "X"), absent("ceterms:prerequisite")],
        record({"ceterms:name": "X"}),
        MODE_EXACT,
    )
    assert units(result) == ["match", "unsure"]
    assert result["extras"] == []


def test_golden_absent_against_a_value_is_missing_and_the_value_extra() -> None:
    result = match_entity(
        [absent("ceterms:prerequisite")],
        record({"ceterms:prerequisite": "Grade Mode: Normal Grading Mode"}),
        MODE_EXACT,
    )
    assert units(result) == ["extra", "missing"]
    [extra] = result["extras"]
    assert extra["extracted_value"] == "Grade Mode: Normal Grading Mode"


def test_a_golden_value_against_the_extractors_null_is_missing() -> None:
    """A false claim: the golden value is missed, the claim is an extra."""
    result = match_entity(
        [field("ceterms:prerequisite", "ATH 100")],
        record({"ceterms:prerequisite": None}),
        MODE_EXACT,
    )
    assert units(result) == ["extra", "missing"]
    assert result["extras"][0]["unit"] == "absent"


def test_an_entity_with_no_record_misses_even_its_absent_fields() -> None:
    result = match_entity([absent("ceterms:prerequisite")], None, MODE_EXACT)
    assert units(result) == ["missing"]


def test_an_absent_field_is_scored_although_its_location_is_null() -> None:
    result = match_entity(
        [absent("ceterms:prerequisite")], record({}), MODE_EXACT
    )
    assert result["skipped_implied"] == 0
    assert units(result) == ["unsure"]


def test_a_null_is_a_claim_and_a_missing_key_is_none() -> None:
    pool, claims = extracted_claims(
        record({"ceterms:prerequisite": None, "ceterms:name": "X"})
    )
    assert claims == {"ceterms:prerequisite"}
    assert "ceterms:prerequisite" not in pool


def test_a_null_credit_value_claims_its_minimum_and_maximum_too() -> None:
    _, claims = extracted_claims(record({"ceterms:creditValue": None}))
    assert claims == {
        "ceterms:creditValue",
        "ceterms:creditMinValue",
        "ceterms:creditMaxValue",
    }


# --- other readings -----------------------------------------------------------


def test_durations_are_kept_whole_as_objects() -> None:
    pool, _ = extracted_claims(record({DURATION: RULE_B}))
    assert pool[DURATION] == RULE_B


def test_a_value_profile_reads_its_schema_keys() -> None:
    pool, _ = extracted_claims(
        record(
            {
                "ceterms:creditValue": [
                    {"schema:minValue": 1.0, "schema:maxValue": 4.0}
                ]
            }
        )
    )
    assert pool["ceterms:creditMinValue"] == [1.0]
    assert pool["ceterms:creditMaxValue"] == [4.0]


# --- the report ---------------------------------------------------------------


def test_the_report_carries_found_right_extras_unsure_and_entities_exact(
    stores: Stores,
) -> None:
    stores.put(
        [*golden_durations(), absent("ceterms:prerequisite")],
        {DURATION: RULE_A},
    )

    for mode in (MODE_EXACT, MODE_PARTIAL):
        report = stores.match(mode)
        assert (
            report["schema"]
            == REPORT_SCHEMA
            == ("xtra-extraction-match-report-2")
        )
        assert report["units"]["golden"] == 5
        assert report["units"]["extracted"] == 5
        assert report["found"] == 0.8
        assert report["right"] == 0.8
        assert report["unsure"] == 1
        assert report["extras"]["count"] == 1
        assert report["entities"] == 1
        assert report["entities_exact"] == 0.0
        assert set(report["by_property"][DURATION]) >= {
            "golden",
            "extracted",
            "match",
            "partial",
            "wrong",
            "missing",
            "extra",
            "unsure",
            "found",
            "right",
        }
    assert stores.match()["outcomes"]["unsure"] == 1


def test_the_table_prints_found_and_right_per_property(stores: Stores) -> None:
    stores.put(golden_durations(), {DURATION: RULE_A})

    table = format_table(stores.match())

    assert "found (recall) 1.0000 = 4/4" in table
    assert "right (precision) 0.8000 = 4/5" in table
    row = next(line for line in table.splitlines() if line.startswith(DURATION))
    assert row.split()[-2:] == ["4/4", "4/5"]
    assert "Extras (1 of 1):" in table


def test_an_old_golden_file_scores_as_before_plus_extra_and_right(
    stores: Stores,
) -> None:
    """No objects, no absent: the old counts, exact_match_rate = found."""
    stores.put(
        [
            field("ceterms:name", "Work Experience Education"),
            field("ceterms:codedNotation", "ACCT 199"),
            field("ceterms:inLanguage", "English", location=None),
        ],
        {
            "ceterms:name": "Work Experience Education",
            "ceterms:codedNotation": ["ACCT 199", "ACCT199"],
        },
    )

    report = stores.match()

    assert report["fields_total"] == 2
    assert report["outcomes"] == {
        "match": 2,
        "mismatch": 0,
        "missing": 0,
        "unsure": 0,
    }
    assert report["skipped_implied"] == 1
    assert report["exact_match_rate"] == report["found"] == 1.0
    assert report["extras"]["count"] == 1
    assert report["right"] == round(2 / 3, 4)
