import copy

from bs4 import BeautifulSoup
from conftest import fixture_html, fixture_url

from review_ui.engine import (
    apply_transforms,
    check_examples,
    css_path,
    extract_from_text,
    run_page,
    text_of,
)
from review_ui.runs import split_page


def page_result(ruleset, name):
    main, _ = split_page(fixture_html(name), "#content-body")
    return run_page(ruleset, fixture_url(name), main)


def fields_of(result, index=0):
    return {f["canonical_label"]: f for f in result["entities"][index]["fields"]}


def test_a_department_page_yields_one_entity_per_course(ruleset):
    result = page_result(ruleset, "course_admj")
    assert [l["label"] for l in result["labels"]] == ["Course"]
    codes = [fields_of(result, i)["Coded Notation"]["value"] for i in range(3)]
    assert codes == ["ADMJ 51", "ADMJ 52", "ADMJ 53"]


def test_fixed_credit_course(ruleset):
    fields = fields_of(page_result(ruleset, "course_admj"))
    assert fields["Learning Opportunity Name"]["value"] == "Juvenile Procedures"
    assert fields["External Identifier"]["value"] == "ADMJ51"
    assert fields["Credit Value"]["value"] == "3.0"
    assert fields["Credit Unit Min Value"]["presence"] == "absent"
    assert fields["Is Non-Credit"]["presence"] == "absent"  # a credit course
    assert fields["Description"]["value"].startswith("Juvenile procedure")


def test_credit_range_fills_min_and_max_not_value(ruleset):
    fields = fields_of(page_result(ruleset, "course_mixed"), 0)
    assert fields["Credit Value"]["presence"] == "absent"
    assert (
        fields["Credit Unit Min Value"]["value"],
        fields["Credit Unit Max Value"]["value"],
    ) == ("1.0", "3.0")


def test_noncredit_course_is_flagged_true_and_keeps_its_zero(ruleset):
    fields = fields_of(page_result(ruleset, "course_mixed"), 1)
    assert fields["Is Non-Credit"]["value"] == "TRUE"
    assert fields["Credit Value"]["value"] == "0.0"


def test_a_missing_description_is_absent(ruleset):
    fields = fields_of(page_result(ruleset, "course_mixed"), 2)
    assert fields["Coded Notation"]["value"] == "STAT C1000E"
    assert fields["Description"]["presence"] == "absent"


def test_subjects_that_contain_a_space_keep_their_code_intact(ruleset):
    fields = fields_of(page_result(ruleset, "course_mixed"), 3)
    assert fields["Coded Notation"]["value"] == "LI S 10"
    assert fields["External Identifier"]["value"] == "LIS10"


def test_derived_fields_have_no_page_location(ruleset):
    fields = fields_of(page_result(ruleset, "course_admj"))
    assert fields["Subject Webpage"]["value"] == fixture_url("course_admj")
    assert fields["Learning Type"]["value"] == "Course"
    assert fields["Language"]["location"] is None


def test_each_courses_location_is_inside_its_own_block(ruleset):
    main, _ = split_page(fixture_html("course_admj"), "#content-body")
    result = run_page(ruleset, fixture_url("course_admj"), main)
    soup = BeautifulSoup(f'<div id="xtra-root">{main}</div>', "lxml")
    titles = [
        soup.select_one(
            fields_of(result, i)["Learning Opportunity Name"]["location"]["css_path"]
        ).get_text(strip=True)
        for i in range(3)
    ]
    assert titles == [
        "Juvenile Procedures",
        "Concepts of Criminal Law",
        "Legal Aspects of Evidence",
    ]


def test_regex_location_spans_the_match_inside_the_element(ruleset):
    field = fields_of(page_result(ruleset, "course_mixed"), 0)["Credit Unit Max Value"]
    assert (field["location"]["char_start"], field["location"]["char_end"]) == (5, 8)
    assert field["raw_text"] == "3.0"


def test_program_page_yields_one_stub_course_per_requirement_row(ruleset):
    result = page_result(ruleset, "program_vmd")
    assert {l["label"] for l in result["labels"]} == {"Program", "Course"}
    assert len(result["entities"]) == 10
    first = fields_of(result)
    assert (first["Coded Notation"]["value"], first["Credit Value"]["value"]) == (
        "VMD 100",
        "1.0",
    )
    assert (
        first["Learning Opportunity Name"]["value"]
        == "Orientation to Visual Media Design"
    )


def test_index_and_info_pages_get_no_labels(ruleset):
    for name in ("index_courses", "info_policy"):
        result = page_result(ruleset, name)
        assert result["labels"] == [] and result["entities"] == []


def test_page_title_comes_from_the_first_matching_title_rule(ruleset):
    assert (
        page_result(ruleset, "course_admj")["title"]
        == "ADMJ - Administration of Justice"
    )
    assert (
        page_result(ruleset, "program_vmd")["title"]
        == "Digital Art Foundation – Certificate of Achievement"
    )
    assert page_result(ruleset, "index_courses")["title"] is None


def test_page_without_main_content_has_no_labels_or_title(ruleset):
    result = run_page(ruleset, fixture_url("course_admj"), None)
    assert (
        result["labels"] == [] and result["entities"] == [] and result["title"] is None
    )


def test_forbids_selector_blocks_a_label(ruleset):
    rules = copy.deepcopy(ruleset)
    rules["label_rules"][0]["forbids_selector"] = "#content-body .course-title"
    assert page_result(rules, "course_admj")["labels"] == []


def test_repeat_filter_skips_rows_that_do_not_match(ruleset):
    rules = copy.deepcopy(ruleset)
    for rule in rules["field_rules"]:
        if rule["rule_id"].startswith("stub-"):
            rule["properties"]["repeat_filter"] = {
                "selector": ".course-entry-link-content",
                "regex": r"^\s*ART\b",
            }
    result = page_result(rules, "program_vmd")
    assert [
        fields_of(result, i)["Coded Notation"]["value"]
        for i in range(len(result["entities"]))
    ] == [
        "ART 130A",
        "ART 125A",
        "ART 126",
    ]


def test_text_of_turns_br_into_newline_and_skips_comments():
    soup = BeautifulSoup("<p>a<br/>b<!-- hidden -->c</p>", "lxml")
    assert text_of(soup.p) == "a\nbc"


def test_css_path_distinguishes_identical_siblings():
    soup = BeautifulSoup('<div id="xtra-root"><p>x</p><p>x</p></div>', "lxml")
    second = soup.find_all("p")[1]
    assert css_path(second) == "#xtra-root > p:nth-of-type(2)"


def test_transforms():
    assert (
        apply_transforms(" ABDY 113: ", ["strip", "rstrip::", "remove_spaces"])
        == "ABDY113"
    )
    assert apply_transforms("a   b\n c", ["collapse_ws", "upper"]) == "A B C"


def test_extract_from_text_without_a_match_is_absent():
    rule = {"properties": {"regex": r"(\d+) Units"}}
    assert extract_from_text(rule, "no digits") == (None, None, None)


def test_map_replaces_known_values_and_drops_unknown_ones():
    rule = {"properties": {"transforms": ["strip"], "map": {"Noncredit": "TRUE"}}}
    assert extract_from_text(rule, " Noncredit ")[0] == "TRUE"
    assert extract_from_text(rule, "Credit (Degree Applicable)") == (None, None, None)


def test_check_examples_reports_a_rule_whose_example_is_wrong(ruleset):
    rules = copy.deepcopy(ruleset)
    assert check_examples(rules) == []
    rules["field_rules"][0]["example_output"] = "wrong"
    assert "course-name" in check_examples(rules)[0]
