"""The report tells the reader what to do (one-rule-runs spec pass 7, answers-pass6.md), on the real case: live run
20261106T012457Z-b970 on AVC, Subject Webpage. Its files are in fixtures/live-run-b970 (report.json and the resolved
report and summary.md it gave before pass 7), with `report.pass7.json`: the same report as the new prompt asks for it
(`why`, each option's `label`, `then.publish`). The web renders `web/src/agent/fixtures/b970-pass7.resolved.json`; its
shape is checked here against what `resolve` writes, so the two can't drift."""

from __future__ import annotations

import json
from pathlib import Path

from golden_datasets import report
from golden_datasets.report import Known, check, markdown, sentences

HERE = Path(__file__).parent
LIVE = HERE / "fixtures" / "live-run-b970"
WEB = HERE.parent / "web" / "src" / "agent" / "fixtures"
SW, IC = "course-subject-webpage", "course-in-catalog"
NOTE = "an-39127172c8e8"


def known() -> Known:
    """What `check` needs from AVC for this report: the two rules, the courses it names and Jared's note."""
    rules = {SW: {"kind": "property", "definition": {"rule_type": "source_url"}},
             IC: {"kind": "property", "definition": {"rule_type": "none"}}}
    courses = {c: {"title": c} for c in ("ACCT199", "AERO199", "GEOG222")}
    notes = {NOTE: {"author": "Jared Diener", "at": "2026-11-04T15:27:29Z", "rule": SW, "course": "ACCT199",
                    "kind": "comment", "expected": None,
                    "text": "When the resource is in a catalog, use the property ceterms:inCatalog instead of "
                            "ceterms:subjectWebpage."}}
    return Known(catalog="avc", folder="avc-x", rules=rules, names={SW: "Subject Webpage", IC: "In Catalog"},
                 courses=courses, notes=notes, run={"run_id": "20261106T012457Z-b970"}, goals=[SW])


def test_the_live_report_is_refused_until_it_says_why_and_labels_its_answers():
    live = json.loads((LIVE / "report.json").read_text())
    problems = check(live, known())
    assert "to_do[0].why: missing" in problems
    assert "to_do[0].options[0].label: missing" in problems and "to_do[0].options[1].label: missing" in problems
    new = json.loads((LIVE / "report.pass7.json").read_text())
    # rows[0] needs the catalog's extraction, which this stand-in doesn't have; nothing else is wrong
    assert [p for p in check(new, known()) if not p.startswith("rows[0]")] == []
    assert sentences(new["to_do"][0]["why"]) == 2


def test_sentences_ignore_dots_inside_words():
    assert sentences("Use ceterms:inCatalog for avc.edu pages. Values like 1.0 stay.") == 2
    assert sentences("One") == 1 and sentences("") == 0


def keys(x) -> set:
    return set(x) if isinstance(x, dict) else set()


def test_the_web_fixture_has_the_shape_resolve_writes(tmp_path):
    """Every field the CLI writes for a decision is in the web's fixture (built from the live run), and no other."""
    fx = json.loads((WEB / "b970-pass7.resolved.json").read_text())
    t = fx["to_do"][0]
    assert keys(t) == {"ask", "why", "open", "rule", "rule_name", "about", "evidence", "options", "effect"}
    yes, no = t["options"]
    assert keys(yes) == keys(no) == {"answer", "label", "button", "text", "link", "do", "done", "then", "effect",
                                     "no_rule_yet"}
    assert keys(yes["do"]) == {"mark", "rule", "rule_name", "words", "event", "count", "courses"}
    assert keys(yes["then"]) == {"publish", "run_again", "text"}
    course = yes["do"]["courses"][0]
    assert keys(course) == {"course", "rule", "title", "value", "status", "occurrence_key", "page_stem", "verdict",
                            "state", "current", "links"}
    assert keys(t["evidence"][1]) == {"kind", "label", "rule", "count", "rows", "courses", "others_lead", "link"}
    assert "lead" in t["about"][0] and "lead" in t["evidence"][1]["rows"][0]
    # the real case: 13 courses to mark Not on the page, each superseding Jared Diener's ✓; or ACCT199 correct
    assert yes["do"]["count"] == 13 and {c["current"]["verdict"] for c in yes["do"]["courses"]} == {"correct"}
    assert {c["current"]["author"] for c in yes["do"]["courses"]} == {"Jared Diener"}
    assert no["do"]["courses"][0]["current"]["annotation_id"] == "an-f69f1da3e976"
    assert yes["no_rule_yet"] == ["In Catalog has no rule yet; the next run writes one."]


def test_summary_md_of_the_real_case_says_what_to_do_first():
    fx = json.loads((WEB / "b970-pass7.resolved.json").read_text())
    md = markdown(fx, "https://studio.test/")
    order = [md.index(x) for x in (
        "### Is Jared Diener's note on ACCT199 right", "His note says a course in a catalog uses In Catalog",
        "**Yes: mark the 13 courses Not on the page**", "In Catalog has no rule yet; the next run writes one.",
        "Then run again with Subject Webpage and In Catalog.", "**No: mark ACCT199 correct**",
        "Here is the row Jared Diener marked wrong:", "Here is one of the 13 courses Jared Diener marked correct:",
        "The other 12 courses Jared Diener marked correct:")]
    assert order == sorted(order)
    assert "AERO199, AJ912" not in md  # no comma-separated codes: one line per course
    assert "- [AJ912](https://studio.test/#/c/avc/rules/course-subject-webpage?row=AJ912" in md
    # ACCT199's row is in the decision; the Subject Webpage section points back to it instead of repeating it
    section = md.split("## Subject Webpage", 1)[1]
    assert "- ACCT199's row is shown above." in section and "acct199`" not in section
    assert "·" not in md and " Jared:" not in md


def test_a_report_resolved_before_pass_7_still_renders_as_markdown():
    old = json.loads((LIVE / "report.resolved.json").read_text())
    md = markdown(old, "https://studio.test/")
    assert "- If yes, mark the 13 courses" in md and "- If no, mark ACCT199 correct" in md
    assert report.row_keys(old)[0] == (SW, "ACCT199")
