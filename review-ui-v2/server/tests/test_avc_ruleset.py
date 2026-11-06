"""The AVC (eLumen) ruleset on the same engine as CCSF: only the ruleset differs."""

import json

import pytest
from bs4 import BeautifulSoup
from conftest import FIXTURES, fixture_html, fixture_url

from review_ui.engine import check_examples, run_page
from review_ui.rules import load_ruleset
from review_ui.runs import PageRef, page_type_of, split_page
from review_ui.sample import pick_sample

AVC_RULES = (
    FIXTURES / "rulesets" / "avc-elumenapp-com-catalog-2026-27-welcome" / "rules.json"
)


@pytest.fixture
def avc(properties):
    return load_ruleset(AVC_RULES, {p.name for p in properties})


def page(avc, name):
    main, _ = split_page(fixture_html(name), avc["content_root"])
    return run_page(avc, fixture_url(name), main)


def fields(result, index=0):
    return {f["canonical_label"]: f for f in result["entities"][index]["fields"]}


def test_the_ruleset_is_valid_and_its_examples_hold(avc):
    assert check_examples(avc) == []
    assert avc["content_root"] == "#mainContent"


def test_a_course_page_is_one_course(avc):
    result = page(avc, "avc_course")
    assert [l["label"] for l in result["labels"]] == ["Course"]
    assert len(result["entities"]) == 1
    f = fields(result)
    assert f["Learning Opportunity Name"]["value"] == "Basic Auto Body Repair"
    assert (f["Coded Notation"]["value"], f["External Identifier"]["value"]) == (
        "ABDY 113",
        "ABDY113",
    )
    assert (f["Credit Value"]["value"], f["Credit Unit Type Description"]["value"]) == (
        "5.0",
        "Units",
    )
    assert f["Description"]["value"].startswith("Prerequisite: Completion of ABDY 112")


def test_credit_ranges_and_zero_units(avc):
    f = fields(page(avc, "avc_course_range"))
    assert (
        f["Credit Unit Min Value"]["value"],
        f["Credit Unit Max Value"]["value"],
    ) == ("1.0", "8.0")
    assert f["Credit Value"]["presence"] == "absent"
    assert fields(page(avc, "avc_course_zero"))["Credit Value"]["value"] == "0.0"


def test_program_page_yields_stub_courses(avc):
    result = page(avc, "avc_program")
    assert {l["label"] for l in result["labels"]} == {"Program", "Course"}
    assert len(result["entities"]) == 19
    first = fields(result)
    assert (first["Coded Notation"]["value"], first["Credit Value"]["value"]) == (
        "AJ101",
        "3",
    )


def test_department_and_info_pages_get_no_labels(avc):
    for name in ("avc_department", "avc_info"):
        assert page(avc, name)["labels"] == []


def test_the_page_title_is_the_header_heading(avc):
    assert page(avc, "avc_course")["title"] == "Basic Auto Body Repair"


def test_a_value_location_resolves_inside_the_content_root(avc):
    main, _ = split_page(fixture_html("avc_course"), avc["content_root"])
    path = fields(run_page(avc, fixture_url("avc_course"), main))["Coded Notation"][
        "location"
    ]["css_path"]
    soup = BeautifulSoup(f'<div id="xtra-root">{main}</div>', "lxml")
    assert soup.select_one(path).get_text(strip=True) == "ABDY 113:"


def test_page_types_follow_elumen_urls(avc):
    base = "https://avc.elumenapp.com/catalog/2026-27"
    types = avc["page_types"]
    assert page_type_of(f"{base}/course/abdy113", types) == "course"
    assert (
        page_type_of(f"{base}/program/administration-of-justice-aa-fall-2026", types)
        == "program"
    )
    assert page_type_of(f"{base}/department/accounting", types) == "department"
    assert page_type_of(f"{base}/department,accounting", types) == "department"
    assert page_type_of(f"{base}/pathways/arts", types) == "pathways"
    assert page_type_of(f"{base}/glossary", types) == "info"


def test_the_sample_mix_covers_unit_kinds(avc):
    base = "https://avc.elumenapp.com/catalog/2026-27"
    pages = [
        PageRef(f"c{n}", f"{base}/course/{chr(97 + n % 20)}{n}", "", "")
        for n in range(60)
    ]
    pages += [PageRef(f"p{n}", f"{base}/program/p{n}", "", "") for n in range(20)]
    pages += [PageRef(f"d{n}", f"{base}/department/d{n}", "", "") for n in range(10)]
    pages += [PageRef(f"i{n}", f"{base}/info{n}", "", "") for n in range(10)]
    pages += [PageRef(f"w{n}", f"{base}/pathways/w{n}", "", "") for n in range(3)]

    def html_of(p):
        n = int(p.stem[1:]) if p.stem[0] == "c" else 0
        units = (
            "1.0 - 8.0 Units"
            if n % 3 == 0
            else "0.0 Units"
            if n % 3 == 1
            else "3.0 Units"
        )
        return f'<p class="header-x-meta">{units}</p>'

    picked = pick_sample(pages, avc["sample"], avc["page_types"], html_of)
    reasons = {e["reason"] for e in picked if e["page_type"] == "course"}
    assert reasons == {
        "course, range units",
        "course, zero units",
        "course, fixed units",
    }
    assert len(picked) == 30


def test_fixtures_are_the_real_pages_markup():
    assert json.loads((FIXTURES / "avc_course.meta.json").read_text())[
        "final_url"
    ].startswith("https://avc.")
