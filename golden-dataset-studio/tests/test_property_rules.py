"""New rule abilities (property-rules spec §4.2–§4.4, §4.6), on synthetic pages built from the real text the spec
quotes: inputs (record · page · url · rule), lists (three splits and `keep`), `labelled`, `attribute`, `join`,
script text left out, and properties with no rule yet."""

from __future__ import annotations

import pytest

from golden_datasets import engine, rulesets
from golden_datasets.errors import UserError

PAGE = b"""<html><head><title>t</title></head><body>
<h1>Statistics (STA)</h1>
<main id="content">
  <div class="course">
    <h3>STA 345 Applied Statistics</h3>
    <span class="credits">1-4 Credit hours</span>
    <div class="labs"><span>Lecture - 87.5</span><span>Lab - 35</span></div>
    <p class="hours">Total Course In-Class (Contact) Hours 180.0 Total Course Out-of-Class Hours 90.0</p>
    <p class="attrs">Attributes: No Textbook Required, Onsite Learning Experience</p>
    <p class="req"><strong>Prerequisites:</strong> HIST 21103 , <a>HIST 21203</a> , and six hours.<br>Three credit
      hours.</p>
    <div class="modes"><a class="btn-link" data-bs-content="Taught over the web">Online</a>
      <a class="btn-link" data-bs-content="At your own pace">Self-Paced</a></div>
    <div class="desc">A course.<script>var x = "Prerequisite: none";</script> On data.</div>
    <div class="prior">With no prior expertise required.</div>
  </div>
</main></body></html>"""
URL = "https://training.uark.edu/portal/training?cmd=catalog&course=bookkeeping-quickBooks"
SETTINGS = {"content_root": "#content"}
BASE = {
    "course-page": {"kind": "page", "version": 1, "definition": {"requires_selector": ".course"}},
    "loc": {"kind": "locator", "version": 1, "definition": {"page_rules": ["course-page"], "repeat": "div.course"}},
}


def _run(**props) -> dict[str, list[dict]]:
    rules = dict(BASE)
    for rid, d in props.items():
        rules[rid] = {"kind": "property", "version": 1, "definition": {"locator": "loc", **d}}
    need = {"labels": True, "matched": None, "locators": ["loc"], "properties": list(props), "page_facts": False}
    out = engine.run_page("p", URL, PAGE, rules, SETTINGS, need)
    got: dict[str, list[dict]] = {}
    for m in out["matches"]:
        got.setdefault(m["rule_id"], []).append(m)
    return got


def _text_content(css_path: str) -> str:
    doc = engine.parse(PAGE)
    return engine.text_content(engine.select_one(doc, css_path, True))


def _occ() -> str:
    doc = engine.parse(PAGE)
    return engine.Paths()(engine.select_one(doc, "div.course"))


def _located(m: dict) -> str:
    from golden_datasets.model import full_css_path

    return _text_content(full_css_path(_occ(), m["css_path"]))[m["char_start"]:m["char_end"]]


def test_split_elements_gives_one_value_per_element_numbered_in_page_order():  # CCSF MED 49
    got = _run(dur={"rule_type": "css", "selector": ".labs > span", "multiple": {"split": "elements"}})["dur"]
    assert [(m["value_index"], m["value"]) for m in got] == [(0, "Lecture - 87.5"), (1, "Lab - 35")]
    assert [_located(m) for m in got] == ["Lecture - 87.5", "Lab - 35"]


def test_split_regex_takes_every_match_of_one_text():  # AVC ABDY 212 (W6)
    got = _run(dur={"rule_type": "css", "selector": ".hours",
                    "multiple": {"split": "regex", "regex": r"(Total Course [^0-9]+ \d+(?:\.\d+)?)"}})["dur"]
    assert [m["value"] for m in got] == ["Total Course In-Class (Contact) Hours 180.0",
                                         "Total Course Out-of-Class Hours 90.0"]
    assert _located(got[1]) == "Total Course Out-of-Class Hours 90.0"


def test_split_separator_after_the_rules_regex():  # Marshall Attributes
    got = _run(kw={"rule_type": "css+regex", "selector": ".attrs", "regex": r"Attributes:\s*(.*)",
                   "multiple": {"split": "separator", "separator": ","}, "transforms": ["strip"]})["kw"]
    assert [m["value"] for m in got] == ["No Textbook Required", "Onsite Learning Experience"]
    assert _located(got[1]).strip() == "Onsite Learning Experience"


def test_keep_and_attribute():  # UARK's modality links (W9, G7)
    got = _run(delivery={"rule_type": "css", "selector": "a.btn-link",
                         "multiple": {"split": "elements", "keep": "^(Online|Hybrid|In-Person|Blended)$"}},
               method={"rule_type": "css", "selector": "a.btn-link",
                       "multiple": {"split": "elements", "keep": "^(Self-Paced|Instructor-led)$"}},
               popover={"rule_type": "css", "selector": "a.btn-link", "attribute": "data-bs-content",
                        "multiple": {"split": "elements"}})
    assert [m["value"] for m in got["delivery"]] == ["Online"]
    assert [m["value"] for m in got["method"]] == ["Self-Paced"]
    assert [m["value"] for m in got["popover"]] == ["Taught over the web", "At your own pace"]
    assert got["popover"][0]["css_path"].startswith("div:nth-of-type") and got["popover"][0]["char_start"] is None


def test_labelled_takes_the_bare_text_after_a_label_up_to_the_br():  # UALR (G6)
    got = _run(pre={"rule_type": "labelled", "label": "Prerequisites:", "transforms": ["collapse_ws"]})["pre"]
    assert got[0]["value"] == "HIST 21103 , HIST 21203 , and six hours."
    assert " ".join(_located(got[0]).split()) == "HIST 21103 , HIST 21203 , and six hours."
    assert _run(pre={"rule_type": "labelled", "label": "Corequisites:"})["pre"][0]["status"] == "no_match"


def test_input_rule_reads_the_parents_output_and_points_into_the_page():  # Marshall credits (G4)
    got = _run(credit={"rule_type": "css", "selector": "span.credits"},
               cmax={"rule_type": "regex", "input": {"from": "rule", "rule": "credit"}, "regex": r"-\s*(\d+)"},
               unit={"rule_type": "regex", "input": {"from": "rule", "rule": "credit"}, "regex": r"\d\s+(.+)$"},
               orphan={"rule_type": "regex", "input": {"from": "rule", "rule": "nothing"}, "regex": "."},
               nothing={"rule_type": "css", "selector": ".absent"})
    assert got["cmax"][0]["value"] == "4" and _located(got["cmax"][0]) == "4"
    assert got["unit"][0]["value"] == "Credit hours" and _located(got["unit"][0]) == "Credit hours"
    assert got["nothing"][0]["status"] == "no_match" and got["orphan"][0]["status"] == "empty"


def test_a_child_of_a_list_gives_one_value_per_item():  # Estimated Duration's children (P14)
    got = _run(dur={"rule_type": "css", "selector": ".labs > span", "multiple": {"split": "elements"}},
               desc={"rule_type": "regex", "input": {"from": "rule", "rule": "dur"}, "regex": r"^(\w+)",
                     "multiple": {"split": "regex", "regex": r"^(\w+)"}},
               exact={"rule_type": "regex", "input": {"from": "rule", "rule": "dur"}, "regex": r"([\d.]+)$",
                      "multiple": {"split": "regex", "regex": r"([\d.]+)$"}})
    assert [m["value"] for m in got["desc"]] == ["Lecture", "Lab"]
    assert [m["value"] for m in got["exact"]] == ["87.5", "35"]
    assert [_located(m) for m in got["exact"]] == ["87.5", "35"]


def test_input_page_reads_outside_the_record_and_input_url_reads_the_url():  # Marshall h1 (G2), UARK (G3)
    got = _run(subject={"rule_type": "css", "input": {"from": "page"}, "selector": "h1"},
               code={"rule_type": "regex", "input": {"from": "url"}, "regex": r"course=([^&]+)"})
    s = got["subject"][0]
    assert s["value"] == "Statistics (STA)" and s["css_path"].startswith("html > body")
    assert got["code"][0]["value"] == "bookkeeping-quickBooks" and got["code"][0]["css_path"] is None


def test_join_takes_every_matched_element_as_one_value():  # UARK description + Prior Learning (W11)
    got = _run(desc={"rule_type": "css", "selector": ".desc, .prior", "join": "\n\n", "transforms": ["strip"]})["desc"]
    assert got[0]["value"] == "A course. On data.\n\nWith no prior expertise required."


def test_script_text_is_left_out_and_offsets_still_match_text_content():  # UARK (G8)
    got = _run(desc={"rule_type": "css+regex", "selector": ".desc", "regex": r"(On data\.)"})["desc"]
    assert got[0]["value"] == "On data." and _located(got[0]) == "On data."
    assert "Prerequisite" not in _run(d={"rule_type": "css", "selector": ".desc"})["d"][0]["value"]


def test_a_property_with_no_rule_writes_no_rows():
    got = _run(none={"rule_type": "none"}, code={"rule_type": "css", "selector": "h3"})
    assert "none" not in got and got["code"][0]["value"] == "STA 345 Applied Statistics"


def _rules(**props) -> dict:
    rules = {k: {**v, "rule_id": k} for k, v in BASE.items()}
    for rid, d in props.items():
        rules[rid] = {"rule_id": rid, "kind": "property", "version": 1, "definition": {"locator": "loc", **d}}
    return rules


def test_publish_refuses_a_cycle_an_unknown_input_and_a_bad_split():
    rulesets.validate_ruleset(_rules(a={"rule_type": "none"}, b={"rule_type": "regex", "regex": ".",
                                                                  "input": {"from": "rule", "rule": "a"}}))
    with pytest.raises(UserError, match="circle"):
        rulesets.validate_ruleset(_rules(a={"rule_type": "regex", "input": {"from": "rule", "rule": "b"}},
                                         b={"rule_type": "regex", "input": {"from": "rule", "rule": "a"}}))
    with pytest.raises(UserError, match="isn't in the ruleset"):
        rulesets.validate_ruleset(_rules(a={"rule_type": "regex", "input": {"from": "rule", "rule": "zz"}}))
    with pytest.raises(UserError, match="multiple.split"):
        rulesets.validate_ruleset(_rules(a={"rule_type": "css", "multiple": {"split": "words"}}))
    with pytest.raises(UserError, match="input.from"):
        rulesets.validate_ruleset(_rules(a={"rule_type": "css", "input": {"from": "web"}}))


def test_examples_of_a_list_rule_compare_lists():
    from golden_datasets.loop import check_examples

    rule = {"kind": "property", "definition": {"locator": "l", "rule_type": "css", "multiple": {
        "split": "separator", "separator": ","}, "transforms": ["strip"]},
        "examples": [{"input": "a, b", "output": ["a", "b"]}, {"input": "a", "output": ["b"]}]}
    assert check_examples({"r": rule}) == ['r example 2: got ["a"], expected ["b"]']
