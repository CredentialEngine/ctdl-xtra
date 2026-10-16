import re

from xtra import prereq
from xtra.prereq import ALL_OF, ANY_OF, COURSE, TEXT, Link
from xtra.rules import Phrase

PHRASES = [
    Phrase("each with a grade of C or better", "modifier"),
    Phrase("with a grade of C or better", "modifier"),
    Phrase("Honors standing", "condition"),
    Phrase("Department consent", "condition"),
]
CODE = re.compile(r"[A-Z]{4} \d{3}[\dH][\dV]")


def links(sentence, offset=100):
    return [Link(offset + m.start(), offset + m.end(), m.group()) for m in CODE.finditer(sentence)]


def read(sentence):
    return prereq.parse(sentence, 100, links(sentence), PHRASES)


def shape(node):
    if node is None:
        return None
    if node.kind == COURSE:
        return node.code
    if node.kind == TEXT:
        return "text"
    return (node.kind, [shape(c) for c in node.children])


def test_single_course():
    assert shape(read("ACCT 20103.")) == "ACCT 20103"


def test_plain_list():
    tree = read("CHEM 36203 and CHEM 36201.")
    assert shape(tree) == (ALL_OF, ["CHEM 36203", "CHEM 36201"])
    assert prereq.is_plain_list_of_courses(tree)


def test_comma_list_ending_in_and():
    assert shape(read("NURS 30001, NURS 30002, and NURS 30003.")) == (ALL_OF, ["NURS 30001", "NURS 30002", "NURS 30003"])


def test_bracketed_alternatives():
    tree = read("(CHEM 36203 and CHEM 36201) or (CHEM 362H3 and CHEM 362H2).")
    assert shape(tree) == (ANY_OF, [(ALL_OF, ["CHEM 36203", "CHEM 36201"]), (ALL_OF, ["CHEM 362H3", "CHEM 362H2"])])
    assert not prereq.is_plain_list_of_courses(tree)


def test_grade_on_one_course():
    assert shape(read("ACCT 20103 with a grade of C or better.")) == (ALL_OF, ["ACCT 20103", "text"])


def test_grade_on_a_list_of_alternatives():
    assert shape(read("MATH 20503 or MATH 22003, each with a grade of C or better.")) == (ALL_OF, [(ANY_OF, ["MATH 20503", "MATH 22003"]), "text"])


def test_known_condition_stands_where_a_course_could():
    assert shape(read("Department consent and ACCT 37203 with a grade of C or better.")) == (ALL_OF, ["text", (ALL_OF, ["ACCT 37203", "text"])])


def test_declines_and_mixed_with_or_at_one_level():
    assert read("ACCT 20103 and ACCT 20203 or ACCT 24003.") is None


def test_declines_unknown_words():
    assert read("Graduate standing in the Master of Accountancy program.") is None
    assert read("ACCT 20103 or equivalent.") is None


def test_declines_when_a_grade_might_cover_more_than_one_course():
    assert read("ACCT 20103 or ACCT 20203 with a grade of C or better.") is None


def test_positions_point_at_the_words():
    sentence = "CHEM 36203 and (CHEM 36201 or CHEM 362H2)."
    tree = read(sentence)
    assert sentence[tree.children[1].start - 100 : tree.children[1].end - 100] == "(CHEM 36201 or CHEM 362H2)"


# --- guards ---------------------------------------------------------------------------------

SENTENCE = "(CHEM 36203 and CHEM 36201) or (CHEM 362H3 and CHEM 362H2)."


def guard(proposal, sentence=SENTENCE):
    tree, problems = prereq.tree_from_proposal(proposal, sentence, 100, links(sentence))
    return {g.id: g.passed for g in prereq.run_guards(tree, problems, sentence, 100, links(sentence))}


def group(kind, *items):
    return {"kind": kind, "quote": "", "items": list(items)}


def course(code):
    return {"kind": "course", "quote": code}


def test_a_faithful_proposal_passes_every_guard():
    good = group("any_of", group("all_of", course("CHEM 36203"), course("CHEM 36201")), group("all_of", course("CHEM 362H3"), course("CHEM 362H2")))
    assert all(guard(good).values())


def test_g1_invented_wording():
    bad = group("all_of", course("CHEM 36203"), {"kind": "text", "quote": "and a pony"}, course("CHEM 36201"), course("CHEM 362H3"), course("CHEM 362H2"))
    assert guard(bad)["G1"] is False


def test_g2_invented_course():
    assert guard(group("all_of", course("NURS 40001"), course("CHEM 36203")))["G2"] is False


def test_g3_dropped_course():
    assert guard(group("all_of", course("CHEM 36203"), course("CHEM 36201")))["G3"] is False


def test_g4_and_mislabelled_as_or_inside_a_bracketed_group():
    # What the probe did: the right four courses, but each pair labelled "one of".
    bad = group("any_of", group("any_of", course("CHEM 36203"), course("CHEM 36201")), group("any_of", course("CHEM 362H3"), course("CHEM 362H2")))
    result = guard(bad)
    assert result["G4"] is False and result["G1"] and result["G2"] and result["G3"]


def test_g5_rearrangement():
    bad = group("all_of", course("CHEM 36201"), course("CHEM 36203"), course("CHEM 362H3"), course("CHEM 362H2"))
    assert guard(bad)["G5"] is False


# --- from a tree to CTDL ----------------------------------------------------------------------


def to_ctdl(sentence):
    tree = read(sentence)
    return prereq.to_condition_profile(tree, lambda code: f"uri:{code}", lambda n: sentence[n.start - 100 : n.end - 100])


def test_courses_under_all_of_become_target_learning_opportunities():
    mapped = to_ctdl("CHEM 36203 and CHEM 36201.")
    assert mapped.profile["ceterms:targetLearningOpportunity"] == ["uri:CHEM 36203", "uri:CHEM 36201"]
    assert not mapped.partly_structured


def test_any_of_becomes_alternative_condition():
    mapped = to_ctdl("(CHEM 36203 and CHEM 36201) or CHEM 362H3.")
    alternatives = mapped.profile["ceterms:alternativeCondition"]
    assert alternatives[0]["ceterms:targetLearningOpportunity"] == ["uri:CHEM 36203", "uri:CHEM 36201"]
    assert alternatives[1]["ceterms:targetLearningOpportunity"] == ["uri:CHEM 362H3"]
    assert "ceterms:targetLearningOpportunity" not in mapped.profile


def test_text_conditions_are_kept_as_their_exact_words():
    mapped = to_ctdl("ACCT 20103 with a grade of C or better.")
    assert mapped.profile["ceterms:condition"] == {"en-US": ["with a grade of C or better"]}


def test_a_second_set_of_choices_is_kept_as_text_and_reported():
    mapped = to_ctdl("(CHEM 36203 or CHEM 36201) and (CHEM 362H3 or CHEM 362H2).")
    assert len(mapped.profile["ceterms:alternativeCondition"]) == 2
    assert mapped.profile["ceterms:condition"] == {"en-US": ["(CHEM 362H3 or CHEM 362H2)"]}
    assert mapped.partly_structured
