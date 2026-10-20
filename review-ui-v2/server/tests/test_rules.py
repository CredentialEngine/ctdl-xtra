import copy

import pytest

from review_ui.rules import RulesetError, validate_ruleset


def broken(ruleset, mutate):
    clone = copy.deepcopy(ruleset)
    mutate(clone)
    return clone


def problems_of(ruleset, known=None):
    with pytest.raises(RulesetError) as info:
        validate_ruleset(ruleset, known)
    return "\n".join(info.value.problems)


def test_shipped_ruleset_is_valid(ruleset):
    validate_ruleset(ruleset)


def test_bad_regex_is_reported(ruleset):
    bad = broken(ruleset, lambda r: r["field_rules"][4]["properties"].update(regex="("))
    assert "bad regex" in problems_of(bad)


def test_bad_selector_is_reported(ruleset):
    bad = broken(
        ruleset, lambda r: r["field_rules"][0]["properties"].update(selector="a[[")
    )
    assert "bad selector" in problems_of(bad)


def test_unknown_label_rule_reference(ruleset):
    bad = broken(ruleset, lambda r: r["field_rules"][0].update(applies_to=["nope"]))
    assert "unknown label rule 'nope'" in problems_of(bad)


def test_duplicate_rule_ids(ruleset):
    bad = broken(
        ruleset,
        lambda r: r["field_rules"][1].update(rule_id=r["field_rules"][0]["rule_id"]),
    )
    assert "duplicate rule_id" in problems_of(bad)


def test_constant_needs_value(ruleset):
    def mutate(r):
        rule = next(x for x in r["field_rules"] if x["rule_type"] == "constant")
        rule["properties"].pop("value")

    assert "needs properties.value" in problems_of(broken(ruleset, mutate))


def test_unknown_transform(ruleset):
    bad = broken(
        ruleset,
        lambda r: r["field_rules"][0]["properties"].update(transforms=["shout"]),
    )
    assert "unknown transform" in problems_of(bad)


def test_repeat_filter_requires_repeat(ruleset):
    def mutate(r):
        props = r["field_rules"][0]["properties"]
        props.pop("repeat")
        props["repeat_filter"] = {"regex": "x"}

    assert "repeat_filter needs properties.repeat" in problems_of(
        broken(ruleset, mutate)
    )


def test_map_must_be_a_table_of_strings(ruleset):
    bad = broken(
        ruleset, lambda r: r["field_rules"][0]["properties"].update(map={"a": 1})
    )
    assert "map" in problems_of(bad)


def test_page_title_rules_are_validated(ruleset):
    def mutate(r):
        r["page_title"] = [
            {"selector": "a[[", "regex": "(", "transforms": ["shout"], "url_regex": "("}
        ]

    text = problems_of(broken(ruleset, mutate))
    assert "page_title[0]: bad selector" in text and "bad regex" in text
    assert "unknown transform" in text


def test_canonical_label_must_be_a_template_property(ruleset):
    bad = broken(
        ruleset, lambda r: r["field_rules"][0].update(canonical_label="Nonsense")
    )
    assert "not a template property" in problems_of(bad, {"Coded Notation"})


def test_all_problems_are_listed_together(ruleset):
    def mutate(r):
        r["field_rules"][0]["properties"]["selector"] = "a[["
        r["field_rules"][1]["applies_to"] = ["nope"]

    text = problems_of(broken(ruleset, mutate))
    assert "bad selector" in text and "unknown label rule" in text


def test_schema_violations_are_reported():
    assert "ruleset_id" in problems_of({"version": 1})
