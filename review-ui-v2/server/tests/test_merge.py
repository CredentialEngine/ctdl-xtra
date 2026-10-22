import pytest
from conftest import fixture_html, fixture_url

from review_ui.engine import run_page
from review_ui.merge import _loose_key, field_id, merge_pages
from review_ui.runs import split_page


def results_for(ruleset, *names):
    out = []
    for name in names:
        main, _ = split_page(fixture_html(name), "#content-body")
        result = run_page(ruleset, fixture_url(name), main)
        result["stem"] = name
        out.append(result)
    return out


def test_one_record_per_course_code_even_with_many_courses_on_a_page(
    ruleset, properties
):
    records = merge_pages(
        results_for(ruleset, "course_admj", "course_mixed"), properties
    )
    assert set(records) == {
        "ADMJ51",
        "ADMJ52",
        "ADMJ53",
        "ADMJ71",
        "LACR9806",
        "STATC1000E",
        "LIS10",
    }


def test_program_stubs_become_records(ruleset, properties):
    records = merge_pages(results_for(ruleset, "program_vmd"), properties)
    assert len(records) == 10
    assert records["VMD100"]["source_expected"]["fields"][0][
        "source_url"
    ] == fixture_url("program_vmd")


def stub(code, credit, url="https://x/program/p"):
    def field(label, value):
        return {
            "canonical_label": label,
            "ctdl_property": None,
            "rule_id": "s",
            "rule_type": "css",
            "presence": "present",
            "value": value,
            "raw_text": value,
            "location": None,
        }

    return {
        "url": url,
        "stem": "p",
        "labels": [],
        "entities": [
            {
                "label_rule_id": "l",
                "label": "Course",
                "root_path": "#r",
                "index": 0,
                "fields": [
                    field("Coded Notation", code),
                    field("Credit Value", credit),
                ],
            }
        ],
    }


def test_course_seen_on_two_pages_merges_with_a_source_url_per_value(
    ruleset, properties
):
    results = results_for(ruleset, "course_admj") + [stub("ADMJ 51", "3")]
    record = merge_pages(results, properties)["ADMJ51"]
    assert len(record["source_urls"]) == 2
    credit = [
        f
        for f in record["source_expected"]["fields"]
        if f["canonical_label"] == "Credit Value"
    ]
    assert {f["source_url"] for f in credit} == {
        fixture_url("course_admj"),
        "https://x/program/p",
    }
    assert record["conflicts"] == []  # "3.0" and "3" are the same number


def test_genuinely_different_values_are_flagged(ruleset, properties):
    results = results_for(ruleset, "course_admj") + [stub("ADMJ 51", "44")]
    record = merge_pages(results, properties)["ADMJ51"]
    assert [c["canonical_label"] for c in record["conflicts"]] == ["Credit Value"]
    assert {v["value"] for v in record["conflicts"][0]["values"]} == {"3.0", "44"}


def test_required_fields_with_no_value_get_one_absent_entry(ruleset, properties):
    record = merge_pages(results_for(ruleset, "program_vmd"), properties)["VMD100"]
    absent = {
        f["canonical_label"]
        for f in record["source_expected"]["fields"]
        if f["presence"] == "absent"
    }
    assert {"Description", "Subject Webpage"} <= absent


def test_fields_follow_template_order(ruleset, properties):
    fields = merge_pages(results_for(ruleset, "course_admj"), properties)["ADMJ51"][
        "source_expected"
    ]["fields"]
    names = [f["canonical_label"] for f in fields]
    order = {p.name: i for i, p in enumerate(properties)}
    assert names == sorted(names, key=lambda n: order[n])


def test_entity_without_a_code_is_kept_under_an_uncoded_id(properties):
    result = {
        "url": "https://x/p",
        "stem": "p",
        "labels": [],
        "entities": [
            {
                "label_rule_id": "l",
                "label": "Course",
                "root_path": "#r",
                "index": 3,
                "fields": [
                    {
                        "canonical_label": "Credit Value",
                        "ctdl_property": None,
                        "rule_id": "s",
                        "rule_type": "css",
                        "presence": "present",
                        "value": "3",
                        "raw_text": "3",
                        "location": None,
                    }
                ],
            }
        ],
    }
    assert list(merge_pages([result], properties)) == ["UNCODED-p-l-3"]


def test_field_ids_are_stable_keys():
    assert field_id("A1", "Name", "https://x", 0) == "A1::Name::https://x::0"


@pytest.mark.parametrize(
    "a,b,same",
    [("1.0", "1", True), ("MUSC 124A", "musc124a", True), ("Intro", "Intro II", False)],
)
def test_loose_key(a, b, same):
    assert (_loose_key(a) == _loose_key(b)) is same
