"""One-rule runs, CLI side (one-rule-runs spec §2–§5, §9), on a six-course catalog shaped like AVC (minicat.py): the
whole golden suite and each kind of regression, inferred values, `rule downstream`, publish rebased or refused, the
publish lock, `ruleset revert`, and the report v2 (references, quotes, `also_changed`, `report.resolved.json`,
`summary.md`, Claude's row comments) through `run done`, then the routes that show it."""

from __future__ import annotations

import json
import os
import threading
import time

import minicat as m
import pytest
from fastapi.testclient import TestClient
from test_agent_runs import FakeK2

from golden_datasets import publishing, report
from golden_datasets.agent_runs import AgentRuns
from golden_datasets.errors import UserError
from golden_datasets.prompt import build_prompt
from golden_datasets.review import LOADER
from golden_datasets.server.app import create_app

CV, CUT, DESC, SW, IC = ("course-credit-value", "course-credit-value-credit-unit-type", "course-description",
                         "course-subject-webpage", "course-in-catalog")


@pytest.fixture
def cat(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("GOLDEN_DATASETS_GOLDEN_ROOT", str(tmp_path / "golden"))
    monkeypatch.delenv("GOLDEN_DATASETS_RUN", raising=False)
    monkeypatch.chdir(tmp_path)
    root = m.build(tmp_path)
    capsys.readouterr()
    return root


def empty_cv(d):  # the real AVC surgical edit (research §7.9): Credit Value empty, Credit Unit Type reads the page
    d[CV]["definition"] = {"locator": "locator-course-page", "rule_type": "none"}
    d[CUT]["definition"] = {"locator": "locator-course-page", "rule_type": "css+regex", "selector": "p.meta",
                            "regex": "([A-Za-z]+)\\s*$"}


def run_cli(root, capsys, *argv) -> tuple[int, str, str]:
    capsys.readouterr()
    code = m.cli(root, *argv)
    out = capsys.readouterr()
    return code, out.out, out.err


# =====================================================================================================
# The whole suite
# =====================================================================================================
def test_the_whole_suite_line_and_an_inferred_value(cat, tmp_path, capsys):
    wrong = m.mark(cat, CV, "ACCT199", "wrong", note="There should be no values for this property.")
    m.mark(cat, CUT, "ACCT199", "correct")
    m.mark(cat, DESC, "GEOG222", "correct")
    p = m.draft(cat, tmp_path, capsys, "d.json", CV, CUT, edit=empty_cv)
    code, out, _ = run_cli(cat, capsys, "rule", "try", p)
    assert code == 0
    assert out.splitlines()[2] == "Whole suite: 9 rules, 2 golden values. 0 now right, 0 got worse."
    assert "Changed: Credit Value (6 values), Credit Unit Type (0 values)" in out and "·" not in out
    (tmp_path / "inferred.json").write_text(json.dumps([{"rule": CV, "course": "ACCT199", "annotation": wrong,
                                                         "value": ""}]))
    code, out, _ = run_cli(cat, capsys, "rule", "try", p)
    assert "Whole suite: 9 rules, 3 golden values. 1 now right (1 inferred), 0 got worse." in out
    assert "  Credit Value: now right ACCT199 (inferred)" in out
    (tmp_path / "inferred.json").write_text(json.dumps([{"rule": CV, "course": "ACCT199", "annotation": "an-nope",
                                                         "value": ""}]))
    code, _, err = run_cli(cat, capsys, "rule", "try", p)
    assert code == 2 and "an-nope is not a live wrong verdict" in err


@pytest.mark.parametrize("kind", ["correct", "expected", "inferred", "fewer"])
def test_each_kind_of_regression_blocks_the_publish(cat, tmp_path, capsys, kind):
    if kind == "correct":  # a ✓ value changed
        m.mark(cat, DESC, "GEOG222", "correct")
    elif kind == "expected":  # a ✕'s expected value no longer produced
        m.mark(cat, DESC, "GEOG222", "wrong", expected="Landforms, climate and water.")
    elif kind == "inferred":  # an inferred value no longer produced
        aid = m.mark(cat, DESC, "GEOG222", "wrong", note="Should be the whole text.")
        (tmp_path / "inferred.json").write_text(json.dumps([{"rule": DESC, "course": "GEOG222", "annotation": aid,
                                                             "value": "Landforms, climate and water."}]))
    else:  # the rule matches fewer of its golden values (two ✓ lost, one ✕ fixed)
        m.mark(cat, DESC, "GEOG222", "correct")
        m.mark(cat, DESC, "KINF244", "correct")

    def lose(d):
        d[DESC]["definition"]["selector"] = "div.nothing"
    p = m.draft(cat, tmp_path, capsys, "d.json", DESC, edit=lose)
    code, out, err = run_cli(cat, capsys, "rule", "publish", p)
    assert code == 2 and "refusing to publish" in err and "nothing written" in err
    assert "got worse GEOG222" in out
    words = {"correct": "marked correct, value changed", "expected": "expected value no longer produced",
             "inferred": "inferred value no longer produced", "fewer": "marked correct, value changed"}[kind]
    assert words in out
    assert m.ctx(cat).ruleset_versions() == [1]


def test_suite_counts_values_changed_and_regressions_directly(cat, tmp_path, capsys):
    from golden_datasets import suite

    m.mark(cat, DESC, "GEOG222", "correct")
    c = m.ctx(cat)
    base = LOADER.snapshot(c, c.latest_extraction())
    s = suite.score(base, base, LOADER.log(c).events(), drafted=[])
    assert (s["rules"], s["golden"], s["now_right"], s["got_worse"], s["changed"]) == (9, 1, 0, 0, {})
    assert suite.checked_fact(s) == "All 9 rules against 1 golden values. Nothing that was right got worse."
    assert suite.checked_fact(s | {"got_worse": 2}).endswith("2 that were right got worse.")


def test_rule_downstream(cat, capsys):
    code, out, _ = run_cli(cat, capsys, "rule", "downstream", CV, "locator-course-page", DESC)
    assert code == 0
    assert "Credit Value (course-credit-value) reads: Whole page is one course (locator-course-page)" in out
    assert "  read by 1 rule: Credit Unit Type (course-credit-value-credit-unit-type)" in out
    assert "  read by 7 rules: " in out and "  read by 0 rules" in out


# =====================================================================================================
# Publishing: rebase or refuse, the lock, revert
# =====================================================================================================
def test_publish_rebases_when_the_rules_dont_overlap(cat, tmp_path, capsys):
    mine = m.draft(cat, tmp_path, capsys, "mine.json", DESC,
                   edit=lambda d: d[DESC]["definition"].update(transforms=["strip", "collapse_ws"]))
    theirs = m.draft(cat, tmp_path, capsys, "theirs.json", CV, CUT, edit=empty_cv)
    assert run_cli(cat, capsys, "rule", "publish", theirs)[0] == 0  # v2: another run, meanwhile
    code, out, _ = run_cli(cat, capsys, "rule", "publish", mine)
    assert code == 0, out
    assert "Rebased on v2 (Claude Code via golden-datasets rule publish published Credit Unit Type, Credit Value " \
           "meanwhile)" in out
    c = m.ctx(cat)
    c.invalidate()
    _, rules = c.ruleset_rules(3)
    assert c.ruleset(3)["changed_rules"] == [DESC]
    assert rules[CV]["definition"]["rule_type"] == "none"  # theirs kept: only my changed rule went on top


def test_publish_refuses_when_another_run_changed_the_same_rule(cat, tmp_path, capsys):
    a = m.draft(cat, tmp_path, capsys, "a.json", CV, CUT, edit=empty_cv)
    b = m.draft(cat, tmp_path, capsys, "b.json", CUT,
                edit=lambda d: d[CUT]["definition"].update(regex="(Units)"))
    c = m.ctx(cat)
    # run A was started by Seth: its ruleset names him
    c.root.write_json("x.json", {})
    assert run_cli(cat, capsys, "rule", "publish", a, "--by", "Seth Alt")[0] == 0
    code, out, err = run_cli(cat, capsys, "rule", "publish", b)
    assert code == 2
    assert "Credit Unit Type was also changed in v2 by Seth Alt. Draft it again from v2 (`rule draft`) and redo " \
           "your change." in err
    c.invalidate()
    assert c.ruleset_versions() == [1, 2]  # nothing written


def test_the_publish_lock_lets_one_publish_at_a_time(cat):
    c = m.ctx(cat)
    order, said = [], []

    def hold(name: str, wait: float) -> None:
        with publishing.publish_lock(c, f"run-{name}", name, say=said.append, sleep=lambda s: time.sleep(0.01)):
            order.append(f"{name} in")
            time.sleep(wait)
            order.append(f"{name} out")
    t1 = threading.Thread(target=hold, args=("A", 0.3))
    t1.start()
    time.sleep(0.05)
    t2 = threading.Thread(target=hold, args=("B", 0))
    t2.start()
    t1.join()
    t2.join()
    assert order == ["A in", "A out", "B in", "B out"]
    assert said and said[0].startswith("waiting for run run-A to finish publishing (0 s)")
    assert c.root.read_json(publishing.lock_path(c.catalog))["holder"] is None
    with publishing.publish_lock(c, "run-C", "C"):  # held: a short wait gives up
        with pytest.raises(publishing.LockBusy):
            with publishing.publish_lock(c, "run-D", "D", wait_s=0.1, say=lambda m: None):
                pass


def test_revert_a_two_rule_version(cat, tmp_path, capsys):
    p = m.draft(cat, tmp_path, capsys, "d.json", CV, CUT, edit=empty_cv)
    assert run_cli(cat, capsys, "rule", "publish", p)[0] == 0
    c = m.ctx(cat)
    plan = publishing.revert_plan(c, 2)
    assert [(r["rule"], r["from_version"], r["to_version"]) for r in plan["rules"]] == [(CV, 2, 1), (CUT, 2, 1)]
    names = report.rule_names(c.ruleset_rules(2)[1])
    assert publishing.revert_text(plan, names) == \
        "Revert v2? This publishes v3 with Credit Value and Credit Unit Type back to how they were in v1."
    code, out, _ = run_cli(cat, capsys, "ruleset", "revert", "2")
    assert code == 0 and "published ruleset v3, reverting v2: Credit Value v2 to v1, Credit Unit Type v2 to v1" in out
    c.invalidate()
    assert c.ruleset(3)["reverts"] == 2 and sorted(c.ruleset(3)["changed_rules"]) == [CV, CUT]
    assert {r["rule_id"]: r["version"] for r in c.ruleset(3)["rules"]}[CV] == 1
    # a later version changed one of v2's rules again: refused, naming it
    q = m.draft(cat, tmp_path, capsys, "e.json", CUT, edit=lambda d: d[CUT]["definition"].update(regex="(Units)"))
    assert run_cli(cat, capsys, "rule", "publish", q)[0] == 0  # v4
    code, _, err = run_cli(cat, capsys, "ruleset", "revert", "2")
    assert code == 2 and "Credit Value and Credit Unit Type were changed again in v3" in err  # the revert itself
    code, _, err = run_cli(cat, capsys, "ruleset", "revert", "1")
    assert code == 2 and "nothing before it" in err


# =====================================================================================================
# A run, end to end: try, publish, report, run done
# =====================================================================================================
@pytest.fixture
def run(cat, monkeypatch):
    ar = AgentRuns(m.ctx(cat), FakeK2())
    r = ar.start({"kind": "rules", "rules": [CV]}, "Jared Diener", studio_url="https://studio.test/",
                 rule_names={CV: "Credit Value"})
    ar.change(r["run_id"], state="running", sent_at=r["created_at"], annotations_as_of="2026-01-01T00:00:00Z")
    monkeypatch.setenv("GOLDEN_DATASETS_RUN", r["run_id"])
    return ar, r


def published_report(ar, cat, tmp_path, capsys, run_id) -> tuple[dict, str]:
    wrong = m.mark(cat, CV, "ACCT199", "wrong", note="There should be no values for this property. "
                                                     "ceterms:creditValue takes the sub-class Value Profile.")
    m.mark(cat, CUT, "ACCT199", "correct")
    (tmp_path / "inferred.json").write_text(json.dumps([{"rule": CV, "course": "ACCT199", "annotation": wrong,
                                                         "value": ""}]))
    p = m.draft(cat, tmp_path, capsys, "d.json", CV, CUT, edit=empty_cv)
    code, out, err = run_cli(cat, capsys, "rule", "publish", p)
    assert code == 0, err
    facts = {
        "ending": "published",
        "rules": [{"rule": CV, "outcome": "published", "now": "empty on every course"}],
        "also_changed": [{"rule": CUT, "because": {"reads": CV},
                          "why": "It took its unit word from Credit Value; it now reads the same line on the page."}],
        "rows": [{"rule": CV, "course": "ACCT199", "comment": "Empty is the value Jared's note asks for."}],
        "inferred": [{"rule": CV, "course": "ACCT199", "annotation": wrong, "value": "",
                      "evidence": [{"quote": "There should be no values for this property", "from": {"note": wrong}}]}],
    }
    return facts, wrong


def test_run_done_writes_the_resolved_report_and_claudes_comments(cat, tmp_path, capsys, run):
    ar, r = run
    facts, wrong = published_report(ar, cat, tmp_path, capsys, r["run_id"])
    c = m.ctx(cat)
    assert c.ruleset(2)["run_id"] == r["run_id"] and c.ruleset(2)["started_by"] == "Jared Diener"
    # refused first: a quote that isn't in its note, and Credit Unit Type left out of also_changed
    bad = facts | {"also_changed": [],
                   "inferred": [facts["inferred"][0] | {"evidence": [{"quote": "made up", "from": {"note": wrong}}]}]}
    with pytest.raises(UserError) as exc:
        ar.done_report(r["run_id"], bad, by="golden-rules agent")
    assert "also_changed: Credit Unit Type (course-credit-value-credit-unit-type) was changed in v2" in str(exc.value)
    assert "inferred[0].evidence[0].quote: not in" in str(exc.value)
    assert not [e for e in LOADER.log(c).events() if e["author"] == "Claude"]  # nothing appended
    assert ar.live_run(r["run_id"]) is not None

    ended, md = ar.done_report(r["run_id"], facts, by="golden-rules agent")
    assert ended["state"] == "finished" and ended["outcome"] == "Claude published Credit Value in v2."
    assert ended["also_changed"] == [CUT] and ended["rule_names"][CUT] == "Credit Unit Type"
    assert ended["rulesets_published"] == [2] and ended["report_version"] == 2
    claude = [e for e in LOADER.log(c).events() if e["author"] == "Claude"]
    assert len(claude) == 1 and claude[0]["author_role"] == "ai" and claude[0]["run_id"] == r["run_id"]
    assert claude[0]["ruleset_version"] == 2 and claude[0]["note"] == "Empty is the value Jared's note asks for."

    rep = ar.report(r["run_id"])
    assert rep["version"] == 2 and rep["ending"] == "published"
    assert rep["facts"] == [
        {"label": "Rules to improve", "text": "Credit Value"}, {"label": "Also changed", "text": "Credit Unit Type"},
        {"label": "Checked", "text": "All 9 rules against 2 golden values. Nothing that was right got worse."},
        {"label": "Ruleset", "text": "v1 to v2"}]
    assert rep["ruleset"]["ext"] == "rs-0002" and rep["ruleset"]["compare"]["url"] == "#/c/" + \
        f"{m.CAT}/compare?a=1&b=2"
    goal = rep["rules"][0]
    assert goal["values_changed"]["count"] == 6 and goal["values_changed"]["text"] == "6 of 6 courses"
    assert goal["values_changed"]["compare_url"].endswith("compare?a=1&b=2&rule=course-credit-value")
    card = goal["rows"][0]
    assert card["course"] == "ACCT199" and card["title"] == "ACCT 199 - Work Experience Education"
    assert card["value"] is None and card["value_before"] == {"version": 1, "value": "1.0 - 8.0 Units"}
    assert card["comment"] == "Empty is the value Jared's note asks for."
    assert card["inferred"] == {"value": "", "annotation": wrong, "saves": "correct"}
    assert card["links"]["rules"] == f"#/c/{m.CAT}/rules/{CV}?row=ACCT199&by=anyone&ext=rs-0002"
    assert card["links"]["wrong"].endswith("&mark=wrong")
    hist = card["history"]
    assert [h["author"] for h in hist] == ["Jared Diener", "Claude"]
    assert hist[1]["run_id"] == r["run_id"] and hist[1]["ruleset_version"] == 2 and hist[1]["author_role"] == "ai"
    also = rep["also_changed"][0]
    assert also["because"] == {"reads": CV, "name": "Credit Value"} and also["values_changed"]["count"] == 0
    assert [x["course"] for x in also["rows"]] == ["ACCT199"]  # no value changed: a golden value that held
    assert rep["inferred"][0]["evidence"][0]["source"]["annotation_id"] == wrong
    assert rep["revert"]["text"] == \
        "Revert v2? This publishes v3 with Credit Value and Credit Unit Type back to how they were in v1."
    assert "·" not in json.dumps(rep) and "·" not in md
    assert "**Claude published Credit Value in v2.**" in md and "[This report](https://studio.test/#/c/" in md

    # the routes: the run with its report, and its rows as they are now
    app = create_app(str(cat))
    cl = TestClient(app)
    d = cl.get(f"/api/catalogs/{m.CAT}/agent-runs/{r['run_id']}").json()
    assert d["report"]["version"] == 2 and d["summary"] == md
    rows = cl.get(f"/api/catalogs/{m.CAT}/agent-runs/{r['run_id']}/rows").json()
    assert rows["rules_touched"] == [CV, CUT] and rows["new_feedback"] == 2  # Jared's ✕ and ✓, after as_of
    acct = next(x for x in rows["rows"] if x["rule"] == CV)
    assert acct["history"][-1]["author"] == "Claude" and acct["history"][-1]["run_at"] == \
        f"{r['run_id'][:4]}-{r['run_id'][4:6]}-{r['run_id'][6:8]}T{r['run_id'][9:11]}:{r['run_id'][11:13]}:" \
        f"{r['run_id'][13:15]}Z"
    assert acct["verdict"]["verdict"] == "wrong" and acct["verdict"]["after_run"] is True


def test_report_references_resolve_and_refuse(cat, tmp_path, capsys, run):
    ar, r = run
    wrong = m.mark(cat, SW, "ACCT199", "wrong")
    comment = m.mark(cat, SW, "ACCT199", None, note="When the resource is in a catalog, use the property "
                                                     "ceterms:inCatalog instead of ceterms:subjectWebpage.")
    m.mark(cat, SW, "GEOG222", "correct", author="Jared")  # a first-profile name: the report says "Jared Diener"
    m.mark(cat, SW, "KINF244", "correct")
    k = report.build_known(m.ctx(cat), ar.run(r["run_id"]))
    good = {"ending": "needs_you",
            "rules": [{"rule": CV, "outcome": "held", "now": "unchanged"}],
            "to_do": [{"ask": "Should Subject Webpage be empty for every course in the catalog?",
                       "why": "Jared's note on ACCT199 says to use In Catalog instead of Subject Webpage. But he "
                              "marked 2 courses with the page's address correct.",
                       "about": [{"course": "ACCT199"}, {"value": {"course": "GEOG222", "rule": SW}}],
                       "evidence": [{"quote": "use the property ceterms:inCatalog … ceterms:subjectWebpage",
                                     "from": {"note": comment}},
                                    {"quote": "A comprehensive and in-depth introduction",
                                     "from": {"page": "BIOL110"}},
                                    {"set": {"courses": {"rule": SW, "verdict": "correct"}},
                                     "label": "marked correct"}],
                       "options": [{"answer": "yes", "label": "mark the 2 courses Not on the page",
                                    "do": {"mark": "not_on_page", "courses": {"rule": SW, "verdict": "correct"}},
                                    "then": {"publish": [SW, IC]}},
                                   {"answer": "no", "label": "mark ACCT199 correct",
                                    "do": {"mark": "correct", "courses": ["ACCT199"], "rule": SW},
                                    "then": {"publish": [IC]}}],
                       "effect": [{"rule": SW, "after": ""}, {"rule": IC, "after": {"source": "page_url"}}]}],
            "together": [{"rules": [SW, IC], "because": {"quote": "instead of ceterms:subjectWebpage",
                                                          "from": {"note": comment}}}]}
    assert report.check(good, k) == []
    for change, problem in [
        ({"ending": "done"}, "ending: must be one of"),
        ({"colour": "red"}, "colour: not a report field"),
        ({"notes": "1\n2\n3\n4\n5\n6"}, "notes: text of at most 5 lines"),
        ({"rules": []}, "rules: no entry for Credit Value"),
        ({"rules": [{"rule": DESC, "outcome": "held"}, good["rules"][0]]}, "isn't a rule to improve"),
        ({"rules": [{"rule": CV, "outcome": "published"}]}, "no version this run published changed Credit Value"),
        ({"ending": "published"}, "this run published no ruleset"),
        ({"also_changed": [{"rule": CUT, "why": "x"}]}, "wasn't changed in any version this run published"),
        ({"rows": [{"rule": "nope", "course": "ACCT199", "comment": "x"}]}, "'nope' is not a rule"),
        ({"rows": [{"rule": SW, "course": "ZZZ999", "comment": "x"}]}, "'ZZZ999' is not a course"),
        ({"to_do": [good["to_do"][0] | {"about": [{"course": "ZZZ999"}]}]}, "about[0]: 'ZZZ999'"),
        ({"to_do": [good["to_do"][0] | {"about": [{"note": "an-nope"}]}]}, "'an-nope' is not an annotation"),
        ({"to_do": [good["to_do"][0] | {"about": [{"page": {"course": "BIOL110", "quote": "not there"}}]}]},
         "not found on BIOL110's saved page"),
        ({"to_do": [good["to_do"][0] | {"about": [{"courses": {"rule": SW, "verdict": "maybe"}}]}]},
         "courses.verdict: correct or wrong"),
        ({"to_do": [good["to_do"][0] | {"about": [{"value": {"course": "ACCT199", "rule": "nope"}}]}]},
         "value.rule: 'nope'"),
        ({"to_do": [good["to_do"][0] | {"about": [{"thing": 1}]}]}, "'thing' is not a kind of reference"),
        ({"to_do": [good["to_do"][0] | {"evidence": [{"quote": "Jared said so", "from": {"note": comment}}]}]},
         "quote: not in"),
        ({"to_do": [good["to_do"][0] | {"options": [{"answer": "yes", "label": "x",
                                                     "do": {"mark": "delete", "courses": []}}]}]},
         "do.mark: one of"),
        ({"to_do": [{k: v for k, v in good["to_do"][0].items() if k != "why"}]}, "to_do[0].why: missing"),
        ({"to_do": [good["to_do"][0] | {"why": "One. Two. Three."}]}, "to_do[0].why: at most 2 short sentences"),
        ({"to_do": [good["to_do"][0] | {"options": [{"answer": "yes"}]}]}, "options[0].label: missing"),
        ({"to_do": [good["to_do"][0] | {"options": [{"answer": "yes", "label": "x" * 81}]}]},
         "options[0].label: the action, in a few words"),
        ({"to_do": [good["to_do"][0] | {"options": [{"answer": "yes", "label": "x",
                                                     "do": {"mark": "correct", "courses": ["ACCT199"],
                                                            "rule": "locator-course-page"}}]}]},
         "rows are property rules' courses"),
        ({"inferred": [{"rule": SW, "course": "ACCT199", "annotation": wrong, "value": "x"}]},
         "isn't in your last try"),
        ({"inferred": [{"rule": SW, "course": "GEOG222", "annotation": wrong, "value": "x"}]},
         "is not an annotation on GEOG222"),
    ]:
        out = report.check(good | change, k)
        assert any(problem in p for p in out), (change, out)
    res = report.resolve(good, k)
    t = res["to_do"][0]
    assert t["open"] and t["rule"] == SW and [c["course"] for c in t["about"]] == ["ACCT199", "GEOG222"]
    assert t["why"].startswith("Jared's note on ACCT199")
    # every row card is introduced in words, people by their full names
    assert [c["lead"] for c in t["about"]] == ["Here is the row Jared Diener marked wrong:",
                                               "Here is the row Jared Diener marked correct:"]
    assert t["about"][1]["verdict"]["author"] == "Jared Diener"
    assert t["evidence"][0]["source"] == {"kind": "note", "annotation_id": comment, "author": "Jared Diener",
                                          "at": t["evidence"][0]["source"]["at"], "rule": SW, "course": "ACCT199"}
    page = t["evidence"][1]["source"]
    assert page["kind"] == "page" and page["before"] == "Prerequisite: None."
    # the set: GEOG222 is already shown above, so its card is KINF244's; no row card twice in one to-do
    s = t["evidence"][2]
    assert s["count"] == 2 and s["label"] == "Jared Diener marked correct"
    assert [c["course"] for c in s["rows"]] == ["KINF244"]
    assert s["rows"][0]["lead"] == "Here is one of the 2 courses Jared Diener marked correct:"
    assert [c["course"] for c in s["courses"]] == ["GEOG222"] and s["others_lead"] == \
        "The other course Jared Diener marked correct:"
    other = s["courses"][0]
    assert other["verdict"] == "correct" and other["current"]["author"] == "Jared Diener"
    assert other["links"]["rules"] == f"#/c/{m.CAT}/rules/{SW}?row=GEOG222&by=anyone&ext=rs-0001"
    assert s["link"].endswith(f"rules/{SW}?by=anyone&verdict=correct")
    # the answers: buttons, what each posts per course (rule, occurrence, the verdict it supersedes), done words
    yes, no = t["options"]
    assert yes["button"] == "Yes: mark the 2 courses Not on the page" and no["button"] == "No: mark ACCT199 correct"
    assert yes["do"]["event"] == {"verdict": "wrong", "reasons": ["not_on_page"]} and yes["do"]["rule"] == SW
    assert [c["course"] for c in yes["do"]["courses"]] == ["GEOG222", "KINF244"]
    g = yes["do"]["courses"][0]
    assert g["occurrence_key"] and g["page_stem"] and g["current"]["verdict"] == "correct"
    assert g["current"]["annotation_id"] and g["state"] == "correct"
    assert yes["done"] == "2 courses marked Not on the page" and no["done"] == "ACCT199 marked correct"
    assert no["do"]["event"] == {"verdict": "correct"} and no["do"]["courses"][0]["current"]["annotation_id"] == wrong
    assert yes["then"]["publish"] == [{"rule": SW, "name": "Subject Webpage", "has_rule": True},
                                      {"rule": IC, "name": "In Catalog", "has_rule": False}]
    assert [x["rule"] for x in yes["then"]["run_again"]] == [CV, SW, IC]
    assert yes["then"]["text"] == "Then run again with Credit Value, Subject Webpage and In Catalog."
    assert yes["no_rule_yet"] == ["In Catalog has no rule yet; the next run writes one."]
    # the web's fixture of the live run (test_report_pass7.py) has exactly the fields resolve writes
    from pathlib import Path
    fx = json.loads((Path(__file__).parent.parent / "web/src/agent/fixtures/b970-pass7.resolved.json").read_text())
    ft = fx["to_do"][0]
    assert set(t) == set(ft) and set(yes) == set(ft["options"][0]) and set(yes["do"]) == set(ft["options"][0]["do"])
    assert set(g) == set(ft["options"][0]["do"]["courses"][0]) and set(s) == set(ft["evidence"][1])
    assert set(t["about"][0]) == set(ft["about"][0]) and set(s["courses"][0]) == set(ft["evidence"][1]["courses"][0])
    assert yes["effect"] == "Subject Webpage becomes empty. In Catalog reads the page's address."
    assert no["effect"] is None
    assert yes["text"] == ("If yes, mark the 2 courses \"Not on the page\" for Subject Webpage. The next "
                           "run publishes Subject Webpage and In Catalog together.")  # for Studios before pass 7
    assert [e["text"] for e in t["effect"]] == ["Subject Webpage becomes empty.", "In Catalog reads the page's address."]
    assert res["outcome"] == "1 decision before Claude can publish Credit Value."
    assert res["together"][0]["names"] == ["Subject Webpage", "In Catalog"]
    assert res["facts"][-1] == {"label": "Ruleset", "text": "v1, unchanged"} and res["revert"] is None
    # /rows brings the current verdict of every course an answer marks
    assert report.row_keys(res)[:3] == [(SW, "ACCT199"), (SW, "GEOG222"), (SW, "KINF244")]
    # summary.md: what to decide and why, the answers, then the evidence; no comma-separated codes
    md = report.markdown(res, "https://studio.test/")
    order = [md.index(x) for x in ("### Should Subject Webpage", "Jared's note on ACCT199",
                                   "**Yes: mark the 2 courses Not on the page**", "**No: mark ACCT199 correct**",
                                   "Here is the row Jared Diener marked wrong:",
                                   "Here is one of the 2 courses Jared Diener marked correct:")]
    assert order == sorted(order)
    assert "- [GEOG222](https://studio.test/#/c/" in md and "·" not in md


def test_inferred_value_of_a_rule_not_published_comes_from_the_last_try(cat, tmp_path, capsys, run):
    ar, r = run
    wrong = m.mark(cat, IC, "ACCT199", "wrong", note=f"{m.SEED}c/0")

    def source(d):
        d[IC]["definition"] = {"locator": "locator-course-page", "rule_type": "source_url"}
    (tmp_path / "inferred.json").write_text(json.dumps([{"rule": IC, "course": "ACCT199", "annotation": wrong,
                                                         "value": f"{m.SEED}c/0"}]))
    p = m.draft(cat, tmp_path, capsys, "d.json", IC, edit=source)
    assert run_cli(cat, capsys, "rule", "try", p)[0] == 0
    k = report.build_known(m.ctx(cat), ar.run(r["run_id"]))
    item = {"rule": IC, "course": "ACCT199", "annotation": wrong, "value": f"{m.SEED}c/0",
            "evidence": [{"quote": f"{m.SEED}c/0", "from": {"note": wrong}}]}
    facts = {"ending": "needs_you", "rules": [{"rule": CV, "outcome": "not changed"}], "inferred": [item],
             "to_do": [{"ask": "Is the page's address ACCT199's In Catalog?", "why": "Jared marked it wrong.",
                        "about": [{"course": "ACCT199"}]}]}
    assert report.check(facts, k) == []
    assert any("your last try gives" in p for p in report.check(facts | {"inferred": [item | {"value": "x"}]}, k))
    res = report.resolve(facts, k)
    assert res["inferred"][0]["published"] is False and res["inferred"][0]["row"]["inferred"]["saves"] == "expected"


def test_run_context_lists_the_last_run_and_the_annotations_since(cat, tmp_path, capsys, run):
    ar, r = run
    ar.done_report(r["run_id"], {"ending": "needs_you", "rules": [{"rule": CV, "outcome": "held", "now": "as is"}],
                                 "to_do": [{"ask": "Should Credit Value be empty?", "why": "Jared said so.", "rule": CV}]}, by="agent")
    m.mark(cat, CV, "ACCT199", "wrong", note="Empty, please.")
    code, out, _ = run_cli(cat, capsys, "run", "context", CV)
    assert code == 0 and f"Last run {r['run_id']} by Jared Diener" in out
    assert "  Asked people: Should Credit Value be empty?" in out
    assert "Annotations since then: 1" in out and "Empty, please." in out


# =====================================================================================================
# Routes: start, picker, revert; the prompt
# =====================================================================================================
@pytest.fixture
def studio(cat):
    app = create_app(str(cat))
    st = app.state.studio
    st.k2 = st.queue.k2 = FakeK2()
    return TestClient(app), st


def test_start_picker_and_goal_claims(cat, studio):
    c, st = studio
    B = f"/api/catalogs/{m.CAT}"
    r = c.post(f"{B}/agent-runs", json={"scope": {"kind": "rules", "rules": [DESC]}, "author": "Jared Diener"})
    assert r.status_code == 400 and "Nothing to improve" in r.json()["detail"]
    m.mark(cat, DESC, "GEOG222", "wrong", note="Drop the label.")
    m.mark(cat, CV, "ACCT199", "wrong")
    m.mark(cat, CV, "BIOL110", None, note="A comment.")
    pk = c.get(f"{B}/rules/picker").json()
    by = {x["rule"]: x for x in pk["rules"]}
    assert by[DESC]["ticked"] and by[DESC]["why"] == "1 open" and by[CV]["why"] == "1 open, 1 comment"
    assert not by[SW]["ticked"] and by[SW]["why"] == "nothing open"
    assert by[CV]["downstream_names"] == ["Credit Unit Type"] and pk["ticked"] == 2
    assert pk["note"] == "No AI run is working, so this one starts now."
    r = c.post(f"{B}/agent-runs", json={"scope": {"kind": "rules", "rules": [DESC, CV]}, "author": "Jared Diener"})
    assert r.status_code == 201 and r.json()["run"]["state"] == "waiting" and r.json()["queue"] == \
        {"place": 1, "start_in_min": 0}
    assert r.json()["run"]["rule_names"] == {DESC: "Description", CV: "Credit Value"}
    again = c.post(f"{B}/agent-runs", json={"scope": {"kind": "rules", "rules": [CV]}, "author": "Seth Alt"})
    assert again.status_code == 409 and again.json()["rule"] == CV
    assert again.json()["detail"] == "Credit Value is being improved in Jared Diener's run"
    pk = c.get(f"{B}/rules/picker").json()
    held = next(x for x in pk["rules"] if x["rule"] == CV)
    assert not held["ticked"] and held["why"].startswith("Being improved in Jared Diener's run, ")
    assert c.post(f"{B}/agent-runs", json={"scope": {"kind": "rules", "rules": ["nope"]}, "author": "x"}).status_code == 400


def test_revert_routes(cat, tmp_path, capsys, studio):
    c, _ = studio
    p = m.draft(cat, tmp_path, capsys, "d.json", CV, CUT, edit=empty_cv)
    assert run_cli(cat, capsys, "rule", "publish", p)[0] == 0
    B = f"/api/catalogs/{m.CAT}"
    pre = c.get(f"{B}/rulesets/2/revert").json()
    assert pre["blocked"] is None and pre["text"].startswith("Revert v2? This publishes v3 with Credit Value")
    r = c.post(f"{B}/rulesets/2/revert", json={"author": "Jared Diener"})
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 3 and [x["to_version"] for x in r.json()["rules"]] == [1, 1]
    assert r.json()["suite"]["line"].startswith("Whole suite: 9 rules")
    assert c.post(f"{B}/rulesets/1/revert", json={"author": "x"}).status_code == 400
    assert c.get(f"{B}/rulesets/9/revert").status_code == 404
    # a run report for v2 no longer offers Revert, and says v3 reverted it; one for v3 still does
    from golden_datasets.server.routes_agent import _with_revert_state
    st = studio[1]
    assert _with_revert_state(st, m.CAT, {"revert": {"version": 2, "text": "t"}}) == {"revert": None, "reverted_in": 3}
    assert _with_revert_state(st, m.CAT, {"revert": {"version": 3, "text": "t"}}) == {"revert": {"version": 3, "text": "t"}}
    assert _with_revert_state(st, m.CAT, None) is None


def test_prompt_for_rules_to_improve_with_a_per_run_install(cat):
    c = m.ctx(cat)
    run = {"run_id": "20261106T150000Z-ab12", "started_by": "Jared Diener", "k2": {"agent": "golden-rules"}}
    text = build_prompt(c, rules=[CV, DESC], target="k2", run=run)["text"]
    d = "/var/lib/k2/work/golden-rules/runs/20261106T150000Z-ab12"
    assert text.startswith("# Improve 2 rules — ")
    assert f"UV_TOOL_DIR={d}/.tools UV_TOOL_BIN_DIR={d}/bin uv tool install '" in text
    assert "uv tool install --reinstall" not in text and "`golden-datasets rule " not in text
    assert f"cd {d} && ./bin/golden-datasets run note \"<one line>\"" in text
    assert "don't use `k2 respond` or `k2 done`" in text
    assert "You may change any other rule if a goal needs it" in text and "BETTER" not in text
    assert "`inferred.json`" in text and "Don't tell people what to press" in text
    assert "Don't join fragments with `·` or other separators" in text
    # pass 7: each to-do leads with what to decide (`ask`, `why`), every option an action with its button's `label`
    assert "Lead with what they must decide" in text and "`why`: at most two short sentences" in text
    assert "Make every option an action the reviewer can take" in text and '"label": "mark ACCT199 correct"' in text
    assert "never show a bare course code without saying what it is" in text
    assert "| Read by | `course-credit-value-credit-unit-type` |" in text
    assert f"cd {d} && ./bin/golden-datasets run done --report report.json" in text
    assert os.environ.get("GOLDEN_DATASETS_RUN") is None
    cl = TestClient(create_app(str(cat)))
    one = cl.get(f"/api/catalogs/{m.CAT}/prompt?rules={CV}").json()
    assert one["rules"] == [CV] and one["text"].startswith(f"# Improve rule `{CV}`")


def test_prompt_paths_follow_the_k2_work_folder(cat, monkeypatch):
    """$GOLDEN_DATASETS_K2_WORK moves the run folder and the SAS file (a K2 daemon on a laptop, for a test)."""
    monkeypatch.setenv("GOLDEN_DATASETS_K2_WORK", "/private/tmp/k2e2e/work/")
    run = {"run_id": "20261106T150000Z-ab12", "started_by": "Jared Diener", "k2": {"agent": "golden-rules"}}
    text = build_prompt(m.ctx(cat), rules=[CV], target="k2", run=run)["text"]
    d = "/private/tmp/k2e2e/work/golden-rules/runs/20261106T150000Z-ab12"
    assert f"mkdir -p {d} && cd {d} && UV_TOOL_DIR={d}/.tools" in text
    assert "SAS tokens for the storage containers are in `/private/tmp/k2e2e/work/golden-datasets.env`" in text
    assert f"cd {d} && ./bin/golden-datasets run done --report report.json" in text
    assert "/var/lib/k2" not in text


def _publish_elsewhere(cat, tmp_path, capsys, monkeypatch, name):
    """Another run's publish (no GOLDEN_DATASETS_RUN): Description gets one more transform."""
    run_id = os.environ.get("GOLDEN_DATASETS_RUN")
    monkeypatch.delenv("GOLDEN_DATASETS_RUN")
    p = m.draft(cat, tmp_path, capsys, name, DESC,
                edit=lambda d: d[DESC]["definition"].update(transforms=["strip", "collapse_ws"]))
    assert run_cli(cat, capsys, "rule", "publish", p)[0] == 0
    monkeypatch.setenv("GOLDEN_DATASETS_RUN", run_id)


def test_a_run_ends_on_the_version_it_published_not_a_later_one(cat, tmp_path, capsys, run, monkeypatch):
    """Two runs at once (e2e, 2026-11-05): run A published v2, then run B published v3 before A's `run done`. A's
    record says v2, and Compare is v1 → v2."""
    ar, r = run
    facts, _ = published_report(ar, cat, tmp_path, capsys, r["run_id"])  # v2, in this run
    _publish_elsewhere(cat, tmp_path, capsys, monkeypatch, "other.json")  # v3, another run
    ended, _ = ar.done_report(r["run_id"], facts, by="golden-rules agent")
    assert ended["ruleset_before"] == 1 and ended["ruleset_after"] == 2 and ended["ruleset_base"] == 1
    assert ar.report(r["run_id"])["ruleset"]["compare"] == {"a": 1, "b": 2, "url": f"#/c/{m.CAT}/compare?a=1&b=2"}


def test_a_rebased_run_compares_from_the_version_it_built_on(cat, tmp_path, capsys, run, monkeypatch):
    """Run B published v2 first; run A (started on v1) rebased on v2 and published v3: Compare is v2 → v3, not
    v1 → v3, which would show B's change as A's."""
    ar, r = run
    _publish_elsewhere(cat, tmp_path, capsys, monkeypatch, "other.json")  # v2, another run
    facts, _ = published_report(ar, cat, tmp_path, capsys, r["run_id"])  # v3, rebased on v2
    ended, _ = ar.done_report(r["run_id"], facts, by="golden-rules agent")
    assert ended["ruleset_before"] == 1 and ended["ruleset_after"] == 3 and ended["ruleset_base"] == 2
    rep = ar.report(r["run_id"])
    assert rep["ruleset"]["compare"]["a"] == 2 and rep["ruleset"]["compare"]["b"] == 3
    assert rep["links"]["compare"] == f"#/c/{m.CAT}/compare?a=2&b=3"
    assert {"label": "Ruleset", "text": "Based on v2; started on v1."} in rep["facts"]
