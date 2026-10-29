"""Engine unit tests on a synthetic page: paths, offsets, locators, field rules, the implied tbody."""

from __future__ import annotations

from golden_datasets import engine
from golden_datasets.model import course_key

PAGE = b"""<html><head><title>t</title></head><body>
<div id="top">nav</div>
<main id="content">
  <div class="course"><h3>GEOG 222:</h3><h2>Cartography</h2>
    <div class="intro">Prerequisite: GEOG 205.<br>This course provides<!-- c --> a survey.</div></div>
  <div class="course"><h3>MATH 150:</h3><h2>Calculus</h2><div class="intro">Limits.</div></div>
  <p>See also CS 150 elsewhere.</p>
  <table class="list"><tr><td class="code">ENGL 101</td></tr></table>
</main></body></html>"""

RULES = {
    "course-page": {"kind": "page", "version": 1, "definition": {"requires_selector": ".course"}},
    "loc": {"kind": "locator", "version": 1, "definition": {"page_rules": ["course-page"], "repeat": "div.course"}},
    "code": {"kind": "field", "version": 1, "ctdl_property": "ceterms:codedNotation",
             "definition": {"locator": "loc", "rule_type": "css", "selector": "h3", "transforms": ["strip", "rstrip::"]}},
    "desc": {"kind": "field", "version": 1, "definition": {
        "locator": "loc", "rule_type": "css+regex", "selector": ".intro",
        "regex": r"\A(?:Prerequisite:[^\n]*\n)?([\s\S]*)", "group": 1}},
    "lang": {"kind": "field", "version": 1, "definition": {"locator": "loc", "rule_type": "constant", "value": "English"}},
    "url": {"kind": "field", "version": 1, "definition": {"locator": "loc", "rule_type": "source_url"}},
}
SETTINGS = {"content_root": "#content"}
NEED = {"labels": True, "matched": None, "locators": ["loc"], "fields": ["code", "desc", "lang", "url"],
        "page_facts": False}


def run():
    return engine.run_page("p", "https://x/p", PAGE, RULES, SETTINGS, NEED)


def test_occurrences_and_document_root_paths():
    out = run()
    assert [o["course_key"] for o in out["occurrences"]] == ["GEOG222", "MATH150"]
    assert out["occurrences"][0]["css_path"] == "html > body:nth-of-type(1) > main:nth-of-type(1) > div:nth-of-type(1)"
    assert out["occurrences"][1]["occurrence_key"].startswith("p@html > body:nth-of-type(1)")


def test_match_paths_are_relative_and_offsets_are_textcontent():
    m = {(x["rule_id"], x["occurrence_key"][-3:]): x for x in run()["matches"]}
    code = next(x for x in run()["matches"] if x["rule_id"] == "code")
    assert code["css_path"] == "h3:nth-of-type(1)" and code["value"] == "GEOG 222"
    desc = next(x for x in run()["matches"] if x["rule_id"] == "desc")
    # v2 text has "\n" for the <br>; the value keeps it, the offsets skip it (textContent has no newline there).
    assert desc["value"] == "This course provides a survey."
    text_content = "Prerequisite: GEOG 205.This course provides a survey."
    assert text_content[desc["char_start"]:desc["char_end"]] == desc["value"]
    lang = next(x for x in run()["matches"] if x["rule_id"] == "lang")
    assert lang["css_path"] is None and lang["value"] == "English"
    assert len(m) == 8


def test_labels_and_missing_content_root():
    out = engine.run_page("p", "u", b"<html><body><p>x</p></body></html>", RULES, SETTINGS, NEED)
    assert out["page_labels"][0]["reason"] == "missing_required_element"
    assert out["occurrences"] == []


def test_implied_tbody_matches_the_browser():
    doc = engine.parse(PAGE)
    td = engine.select_one(doc, "td.code", True)
    assert engine.Paths()(td).endswith("table:nth-of-type(1) > tbody:nth-of-type(1) > tr:nth-of-type(1) > td:nth-of-type(1)")


def test_selector_semantics_match_soupsieve():
    doc = engine.parse(PAGE)
    root = engine.select_one(doc, "#content", True)
    # From the content root the root itself can match (v2 searched from a wrapper around it) …
    assert engine.select_one(root, "#content", True) is root
    # … but a field selector never matches the occurrence element itself.
    course = engine.select(root, "div.course", True)[0]
    assert engine.select_one(course, "div.course") is None


def test_course_key():
    assert course_key("abdy 113") == "ABDY113" and course_key(None) is None
