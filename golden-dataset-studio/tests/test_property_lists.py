"""`properties apply`, properties with no rule yet, list rows with per-item verdicts and a rule reading another's
output, through the CLI and the API (property-rules spec §4.1, §4.2, §4.4, §4.6), on the three-page catalog."""

from __future__ import annotations

import json

from test_golden_versions import CAT, JARED, _rows, studio  # noqa: F401  (studio: the fixture)

from golden_datasets import golden, properties
from golden_datasets.cli import main
from golden_datasets.context import Ctx

B = f"/api/catalogs/{CAT}"
LISTS = {"catalog": CAT, "rules": [
    {"rule_id": "course-subject", "definition": {"locator": "locator-course-page", "rule_type": "css",
                                                 "selector": "h1", "multiple": {"split": "separator",
                                                                                "separator": " "}}},
    {"rule_id": "course-content-description",
     "definition": {"locator": "locator-course-page", "rule_type": "regex", "regex": r"(\d+)",
                    "input": {"from": "rule", "rule": "course-subject"}}},
]}


def _apply(ctx: Ctx, capsys) -> None:
    assert main(["properties", "apply", "--root", ctx.root.uri, "-c", CAT]) == 0
    assert "adds 34 property rules with no rule yet" in capsys.readouterr().out


def test_apply_adds_every_property_with_no_rule_and_anyone_can_annotate_them(studio, capsys):  # noqa: F811
    c, ctx, _ = studio
    _apply(ctx, capsys)
    rs, rules = Ctx(ctx.root, CAT).ruleset_rules(2)
    assert rs["note"] == "added 34 property rules from the Phase 1 sheet"
    assert len([r for r in rules.values() if r["kind"] == "property"]) == 36
    assert rules["course-in-catalog"]["definition"] == {"locator": "locator-course-page", "rule_type": "none"}
    assert properties.apply(Ctx(ctx.root, CAT), "again") is None  # nothing left to add
    assert main(["check", "--root", ctx.root.uri, "-c", CAT]) == 0
    capsys.readouterr()

    rows = _rows(c, "course-in-catalog")
    assert len(rows) == 3 and {r["status"] for r in rows.values()} == {"none"}
    assert c.get(f"{B}/rules/course-in-catalog").json()["fill"] == {"rows": 3, "found": 0}
    r = c.post(f"{B}/annotations", json={"type": "verdict", "author": JARED, "verdict": "wrong",
                                         "expected": {"text": "C 0"}, "target": {
                                             "kind": "match", "rule_id": "course-in-catalog",
                                             "occurrence_key": rows["page-0"]["key"]}})
    assert r.status_code == 200, r.text
    assert r.json()["rule"]["status"] == "needs work"
    course = c.get(f"{B}/courses/C0").json()["occurrences"][0]["properties"]
    assert len(course) == 36 and next(p for p in course if p["rule_id"] == "course-in-catalog")["status"] == "none"
    assert main(["check", "--root", ctx.root.uri, "-c", CAT]) == 0


def test_a_list_rule_has_one_row_per_course_and_a_verdict_per_item(studio, tmp_path, capsys):  # noqa: F811
    c, ctx, gold = studio
    _apply(ctx, capsys)
    draft = tmp_path / "lists.json"
    draft.write_text(json.dumps(LISTS))
    assert main(["rule", "publish", "--root", ctx.root.uri, "-c", CAT, str(draft)]) == 0
    capsys.readouterr()
    rows = _rows(c, "course-subject")
    row = rows["page-0"]
    assert [(i["value_index"], i["value"]) for i in row["items"]] == [(0, "C"), (1, "0")]
    assert row["value"] == "C\n0"
    child = _rows(c, "course-content-description")["page-2"]
    assert child["value"] == "2" and child["css_path"].endswith("h1:nth-of-type(1)") and child["char_start"] == 2

    def item(verdict: str, value_index=None, expected=None) -> dict:
        target = {"kind": "match", "rule_id": "course-subject", "occurrence_key": row["key"], "item": True,
                  "value_index": value_index}
        r = c.post(f"{B}/annotations", json={"type": "verdict", "author": JARED, "verdict": verdict,
                                             "expected": expected, "target": target})
        assert r.status_code == 200, r.text
        return r.json()

    assert item("correct", 1)["event"]["target"]["value_seen"] == "0"
    assert item("wrong", 0)["rule"]["open_wrong"] == 1
    assert item("missing", expected={"text": "Calculus"})["rule"]["open_wrong"] == 2
    got = _rows(c, "course-subject")["page-0"]
    assert [i["state"] for i in got["items"]] == ["wrong", "correct"] and got["items"][1]["human"]
    assert [m["expected"]["text"] for m in got["missing_items"]] == ["Calculus"]
    assert got["state"] is None  # item verdicts don't make a verdict on the whole row

    rv = golden.LOADER.review(Ctx(ctx.root, CAT))
    plan = golden.plan(rv, {"Subjects"})
    subject = [(r["value_index"], r["approval"]) for r in plan["lineage"]
               if r["page_stem"] == "page-0" and r["property"] == "Subjects"]
    assert subject == [(0, "rule"), (1, "human")]
    assert main(["check", "--root", ctx.root.uri, "-c", CAT]) == 0


def test_generate_rules_lists_every_property_and_rule_type(studio, capsys):  # noqa: F811
    """Property-rules spec §4.11: the prompt is structured and exhaustive; on a catalog with rules it asks for the
    properties still without one."""
    from golden_datasets.prompt import build_first_rules_prompt

    c, ctx, _ = studio
    _apply(ctx, capsys)
    text = build_first_rules_prompt(Ctx(ctx.root, CAT), target="local")["text"]
    assert text.startswith("# Write the rules still missing")
    for heading in ("## Every property", "## Every rule type and input", "## Requisite words",
                    "## When it isn't clear which property a text belongs to", "## How to work"):
        assert heading in text
    table = text[text.index("## Every property"):text.index("## Every rule type")]
    assert table.count("\n| ") == 37  # the header and 36 properties
    assert "`ceterms:creditValue → schema:minValue`" in table and "| none yet |" in table
    assert "`multiple.split: regex`" in text and "`input: rule`" in text and "`labelled`" in text
    assert "rule draft --all > drafts/more-rules.json" in text and "out of scope" not in text
    assert "coverage (properties with a rule, of 36)" in text


def test_the_rule_list_groups_and_sorts_properties(studio, tmp_path, capsys):  # noqa: F811
    """Property-rules spec §4.8: Required first (the course key first), then Other properties by values experts
    reviewed across catalogs, then Not started (collapsed); a child reads "part of <parent>"."""
    c, ctx, _ = studio
    _apply(ctx, capsys)
    draft = tmp_path / "lists.json"
    draft.write_text(json.dumps(LISTS))
    assert main(["rule", "publish", "--root", ctx.root.uri, "-c", CAT, str(draft)]) == 0
    capsys.readouterr()

    def groups() -> dict[str, list[dict]]:
        out = c.get(f"{B}/rules").json()["groups"]
        return {g["id"]: g for g in out}

    g = groups()
    assert list(g) == ["page", "locator", "required", "other", "not-started"]
    assert [r["rule_id"] for r in g["required"]["rules"]][:3] == ["course-code", "course-external-id",
                                                                   "course-learning-type"]
    assert g["required"]["rules"][0]["course_key"] and g["not-started"]["collapsed"]
    assert [r["rule_id"] for r in g["other"]["rules"]] == ["course-content-description", "course-subject"]  # sheet
    child = next(r for r in g["not-started"]["rules"] if r["rule_id"] == "course-credit-value-min-value")
    assert child["subtitle"] == "part of Credit Value" and child["path_shown"] == "ceterms:creditValue → schema:minValue"
    assert child["no_rule"] and child["input"] == "nothing yet: no rule"
    other = {r["rule_id"]: r for r in g["other"]["rules"]}
    assert other["course-content-description"]["input"] == "Subjects's value" and other["course-subject"]["list"]

    row = _rows(c, "course-subject")["page-1"]  # an expert's ✓ on Subjects: it sorts first now
    r = c.post(f"{B}/annotations", json={"type": "verdict", "author": JARED, "verdict": "correct", "target": {
        "kind": "match", "rule_id": "course-subject", "occurrence_key": row["key"], "item": True, "value_index": 0}})
    assert r.status_code == 200, r.text
    assert [r["rule_id"] for r in groups()["other"]["rules"]] == ["course-subject", "course-content-description"]
