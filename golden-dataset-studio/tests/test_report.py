"""The run report (report.py, docs/qrspi/report-links/03-spec.md): Claude's report.json is checked id by id, then
rendered into Markdown whose links the CLI builds from the Studio address saved with the run."""

from __future__ import annotations

import json

import pytest

from golden_datasets import agent_runs, report
from golden_datasets.agent_runs import AgentRuns
from golden_datasets.context import Ctx
from golden_datasets.errors import UserError
from golden_datasets.report import Known, check, headline, linkify, render
from golden_datasets.storage import LocalRoot

S = "https://studio.test/"


def known(**kw) -> Known:
    base = dict(catalog="avc",
                rules={"course-in-catalog": "In Catalog", "course-description": "Description",
                       "course-credit-value": "Credit Value"},
                courses={"ACCT199", "AERO199", "CFE114", "NS922L"},
                notes={"course-in-catalog": {"an-1": {"author": "Jared", "course": "ACCT199", "kind": "wrong"}},
                       "course-description": {"an-2": {"author": "Jared", "course": "ACCT199", "kind": "wrong"},
                                              "an-3": {"author": "Jared", "course": "ACCT199", "kind": "comment"}}},
                ruleset_before=9, ruleset_after=9)
    return Known(**(base | kw))


NEEDS = {
    "ending": "needs_you",
    "summary": "Nothing was published.",
    "to_do": [{"rule": "course-in-catalog", "course": "ACCT199", "notes": ["an-1"],
               "do": "Save the page address as ACCT199's expected value",
               "value": "https://avc.elumenapp.com/catalog/2026-27/course/acct199",
               "then": "The next run publishes course-in-catalog as drafted."},
              {"rule": "course-description", "course": "ACCT199", "notes": ["an-2", "an-3"],
               "do": "Pick one of the two notes", "then": "If the text goes, re-mark AERO199 and CFE114."}],
    "rules": [{"rule": "course-credit-value", "tried": "Leave it empty", "result": "not published",
               "why": "ACCT199@course-in-catalog would change"}],
    "notes": "One more thing.",
}
RUN = {"run_id": "20261104T000000Z-abcd", "studio_url": S}


def test_a_good_report_has_no_problems():
    assert check(NEEDS, known()) == []


@pytest.mark.parametrize("change, problem", [
    ({"ending": "done"}, "ending: must be one of"),
    ({"to_do": []}, "to_do: a needs_you report needs"),
    ({"colour": "red"}, "colour: not a report field"),
    ({"notes": "1\n2\n3\n4\n5\n6"}, "notes: text of at most 5 lines"),
    ({"to_do": [{"rule": "course-nope", "do": "x"}]}, "to_do[0].rule: 'course-nope' is not a rule"),
    ({"to_do": [{"rule": "course-in-catalog", "course": "ZZZ999", "do": "x"}]}, "to_do[0].course: 'ZZZ999'"),
    ({"to_do": [{"rule": "course-in-catalog", "notes": ["an-2"], "do": "x"}]}, "an-2 is not an annotation on course-in-catalog"),
    ({"to_do": [{"rule": "course-in-catalog", "do": " "}]}, "to_do[0].do: say it"),
    ({"to_do": [{"rule": "course-in-catalog", "do": "x", "link": "y"}]}, "to_do[0].link: not a field here"),
    ({"rules": [{"rule": "course-description", "tried": "x", "result": "maybe"}]}, "rules[0].result: must be one of"),
])
def test_each_problem_is_named(change, problem):
    out = check(NEEDS | change, known())
    assert any(problem in p for p in out), out


def test_failed_needs_a_reason_and_published_needs_a_new_ruleset():
    assert any("reason:" in p for p in check({"ending": "failed"}, known()))
    assert any("still v9" in p for p in check({"ending": "published"}, known()))
    assert check({"ending": "published"}, known(ruleset_after=10)) == []


def test_headlines():
    k = known()
    assert headline(NEEDS, k) == "2 things to fix before Claude can publish"
    assert headline(NEEDS | {"to_do": NEEDS["to_do"][:1]}, k) == "1 thing to fix before Claude can publish"
    assert headline({"ending": "published"}, known(ruleset_after=10)) == "Claude published ruleset v10"
    assert headline({"ending": "failed", "reason": "the install  failed"}, k) == "Claude couldn't finish: the install failed"


def test_render_sections_in_order_with_links():
    md = render(NEEDS, known(), RUN)
    order = [md.index(h) for h in ("**2 things to fix", "## What you need to do", "## Rule by rule", "## Notes", "[This report]")]
    assert order == sorted(order)
    row = f"{S}#/c/avc/rules/course-in-catalog?row=ACCT199&by=anyone"
    assert f"1. **[In Catalog]({S}#/c/avc/rules/course-in-catalog) · [ACCT199]({row})**" in md
    assert "   - *Value to save:* `https://avc.elumenapp.com/catalog/2026-27/course/acct199`" in md
    assert f"([Jared's note]({row}&note=an-1))" in md
    assert "[Jared's note 1](" in md and "[Jared's comment 2](" in md
    # course codes and rule ids in text become links; ACCT199@rule points at another rule
    assert f"[In Catalog]({S}#/c/avc/rules/course-in-catalog) as drafted" in md
    assert f"[AERO199]({S}#/c/avc/rules/course-description?row=AERO199&by=anyone)" in md
    assert f"[ACCT199 (In Catalog)]({row})" in md
    assert f"[This report]({S}#/c/avc/rules?run=20261104T000000Z-abcd)" in md
    assert "ruleset v9 unchanged" in md


def test_a_value_of_several_lines_is_a_block_under_its_item():
    facts = NEEDS | {"to_do": [NEEDS["to_do"][1] | {"value": "First paragraph.\n\nSecond paragraph."}]}
    md = render(facts, known(), RUN)
    assert "   - *Value to save:*\n\n     ```\n     First paragraph.\n     \n     Second paragraph.\n     ```" in md


def test_render_without_a_studio_address_has_no_links():
    md = render(NEEDS, known(), {"run_id": "r1"})
    assert "](" not in md and "**In Catalog · ACCT199**" in md and "This report" not in md


def test_published_report_links_compare_and_the_last_try():
    last = {"base_ruleset": 9, "published": 10, "totals": {"fixed": 1, "still_wrong": 0, "newly_wrong": 0, "unchanged": 4},
            "cards": [{"rule_id": "course-in-catalog", "fixed": ["ACCT199"], "still_wrong": [], "newly_wrong": []}]}
    md = render({"ending": "published"}, known(ruleset_after=10), RUN, last)
    assert f"ruleset v9 → v10 · [Compare]({S}#/c/avc/compare?a=9&b=10)" in md
    assert "## What publishing changed" in md and "1 now right · 0 still wrong" in md
    assert f"now right: [ACCT199]({S}#/c/avc/rules/course-in-catalog?row=ACCT199&by=anyone)" in md


def test_linkify_leaves_other_words_alone():
    k = known()
    L = report.Links(S, k, None)
    assert linkify("the `course-description` rule, not course-nope", k, L, None) == \
        f"the [Description]({S}#/c/avc/rules/course-description) rule, not course-nope"
    assert linkify("ACCT199 in no rule", k, L, None) == "ACCT199 in no rule"


def test_done_report_ends_the_run_needs_you(tmp_path, monkeypatch, capsys):
    root = LocalRoot(tmp_path)
    r = AgentRuns(Ctx(root, "avc"), k2=type("K", (), {"agent": "golden-rules", "agent_url": "http://k2.test",
                                                       "send": lambda self, t, s: "m1"})())
    monkeypatch.setattr(AgentRuns, "_latest_ruleset", lambda self: 9)
    run = r.start({"kind": "needs_work"}, "Eric", lambda run: {"text": "x", "rules": []}, studio_url=S)
    assert run["studio_url"] == S
    import golden_datasets.loop as loop
    monkeypatch.setattr(loop, "current_review", lambda ctx: None)
    monkeypatch.setattr(report, "known_from", lambda ctx, rv, run: known())
    with pytest.raises(UserError, match="to_do\\[0\\].rule"):
        r.done_report(run["run_id"], NEEDS | {"to_do": [{"rule": "nope", "do": "x"}]}, by="agent")
    assert r.live()[0] is not None  # refused: still running, nothing written
    ended, md = r.done_report(run["run_id"], NEEDS, by="agent")
    assert ended["state"] == "needs_you" and ended["to_do_count"] == 2
    assert ended["outcome"] == "2 things to fix before Claude can publish"
    assert r.summary(run["run_id"]) == md
    assert json.loads(root.read_text(f"avc-elumenapp-com-catalog-2026-27-welcome/golden-dataset-studio/agent-runs/"
                                     f"{run['run_id']}/report.json"))["ending"] == "needs_you"
    # the run folder's settings name the run: --run defaults to it
    monkeypatch.setenv("GOLDEN_DATASETS_RUN", "r-from-env")
    assert agent_runs._run_id(type("A", (), {"run": None})()) == "r-from-env"
