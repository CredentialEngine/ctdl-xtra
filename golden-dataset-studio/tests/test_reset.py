"""Reset rule (phase1-followups spec §4) on a three-page catalog: a `reset` event takes back a rule's reviews in this
catalog (✓, ✕ with an answer) and its approval, keeps comments and ✕ with no answer, withdraws its column from the
silver dataset and its values from the golden one until the rule is approved again, and no longer blocks
`rule publish`. Reopen ends an approval and keeps the reviews."""

from __future__ import annotations

import json

from test_golden_versions import CAT, ERIC, JARED, RULES, B, _mark, _page, _rows, studio  # noqa: F401  (studio: the fixture)

from golden_datasets import golden
from golden_datasets.cli import main
from golden_datasets.review import human_reviewed_counts


def _event(c, type_: str, rule: str, author: str = JARED, note: str | None = None, status: int = 200) -> dict:
    r = c.post(f"{B}/annotations", json={"type": type_, "author": author, "note": note,
                                         "target": {"kind": "rule", "rule_id": rule}})
    assert r.status_code == status, r.text
    return r.json()


def _columns(ctx) -> list[str]:
    vs = golden.versions(ctx)
    return ctx.read_json(f"{vs[max(vs)]['path']}/publication.json", immutable=False)["properties"]


def test_reset_takes_back_the_reviews_and_the_approval_and_withdraws_the_column(studio, tmp_path, capsys):  # noqa: F811
    c, ctx, gold = studio
    for stem in ("page-0", "page-1", "page-2"):
        _mark(c, JARED, "course-code", _rows(c, "course-code")[stem], "correct")
    assert _event(c, "approve", "course-code")["published"]["columns"] == ["codedNotation"]
    assert [f["property"] for f in _page(gold, ctx, "page-0", 1, golden.HUMAN_REVIEWED)[0]["fields"]] == ["Coded Notation"]

    # a changed rule would change values marked correct: refused
    rules = json.loads(json.dumps(RULES))
    rules["rules"][2]["definition"]["regex"] = "^(C)"
    draft = tmp_path / "v2.json"
    draft.write_text(json.dumps(rules))
    publish = ["rule", "publish", "--root", ctx.root.uri, "--catalog", CAT, str(draft), "--note", "v2"]
    assert main(publish) == 2
    capsys.readouterr()

    pre = c.get(f"{B}/rules/course-code/reset-preview").json()
    assert pre["counts"] == {"correct": 3, "answered": 0} and pre["by_author"] == {JARED: 3}
    assert pre["approval"]["by"] == JARED and pre["column"] == {"column": "codedNotation", "golden": "ruleset-v1"}
    assert c.get(f"{B}/rules/nope/reset-preview").status_code == 404

    _event(c, "reset", "course-code", ERIC, status=400)  # a reset says why
    out = _event(c, "reset", "course-code", ERIC, note="the code is the subject and number, not the prefix")
    assert out["event"]["counts"] == {"correct": 3, "answered": 0} and out["event"]["annotation_id"].startswith("ap-")
    assert out["rule"]["status"] == "in review" and out["rule"]["reviewed"] == 0  # an engineer's reset clears an expert's ✓
    assert out["published"]["columns"] == [] and _columns(ctx) == []
    assert _page(gold, ctx, "page-0", 1, golden.HUMAN_REVIEWED) is None  # the golden dataset loses the cleared values
    row = _rows(c, "course-code")["page-0"]
    assert (row["state"], row["human_reviewed"], row["before_reset"]["author"]) == (None, False, JARED)
    assert human_reviewed_counts(ctx.root, [CAT])["course-code"] == 0
    assert main(publish) == 0  # nothing marked correct stands in the way now
    capsys.readouterr()

    # approving again brings the column back
    _mark(c, JARED, "course-code", _rows(c, "course-code")["page-0"], "correct")
    assert _event(c, "approve", "course-code")["published"]["columns"] == ["codedNotation"]
    assert _columns(ctx) == ["Coded Notation"]
    assert _rows(c, "course-code")["page-0"]["before_reset"] is None  # reviewed again
    assert main(["properties", "apply", "--root", ctx.root.uri, "-c", CAT]) == 0  # `check` asks for every property
    assert main(["check", "--root", ctx.root.uri, "-c", CAT]) == 0  # a reset event is a valid annotation
    capsys.readouterr()


def test_reset_keeps_comments_and_wrong_without_an_answer(studio):  # noqa: F811
    c, ctx, _ = studio
    rows = _rows(c, "course-name")
    _mark(c, JARED, "course-name", rows["page-0"], "correct")
    r = c.post(f"{B}/annotations", json={"type": "verdict", "author": JARED, "verdict": "wrong",
                                         "expected": {"text": "Course 1", "css_path": None, "char_start": None,
                                                      "char_end": None},
                                         "target": {"kind": "match", "rule_id": "course-name",
                                                    "occurrence_key": rows["page-1"]["key"]}})
    assert r.status_code == 200, r.text
    _mark(c, JARED, "course-name", rows["page-2"], "wrong")  # no answer
    c.post(f"{B}/annotations", json={"type": "comment", "author": ERIC, "note": "check the title",
                                     "target": {"kind": "match", "rule_id": "course-name",
                                                "occurrence_key": rows["page-0"]["key"]}})
    pre = c.get(f"{B}/rules/course-name/reset-preview").json()
    assert pre["counts"] == {"correct": 1, "answered": 1} and pre["approval"] is None and pre["column"] is None
    assert pre["kept"] == {"wrong_no_answer": 1, "questions": 0, "comments": 1}
    _event(c, "reset", "course-name", note="names are the course title")
    got = _rows(c, "course-name")
    assert [got[s]["state"] for s in ("page-0", "page-1", "page-2")] == [None, None, "wrong"]
    assert [x["note"] for x in got["page-0"]["comments"]] == ["check the title"]
    assert got["page-1"]["before_reset"]["expected"]["text"] == "Course 1"
    # a verdict after the reset counts again
    _mark(c, JARED, "course-name", got["page-0"], "correct")
    assert _rows(c, "course-name")["page-0"]["state"] == "correct"


def test_reopen_ends_the_approval_and_keeps_the_reviews(studio):  # noqa: F811
    c, ctx, _ = studio
    for stem in ("page-0", "page-1", "page-2"):
        _mark(c, JARED, "course-code", _rows(c, "course-code")[stem], "correct")
    _event(c, "approve", "course-code")
    out = _event(c, "reopen", "course-code")
    assert out["rule"]["status"] == "in review" and out["rule"]["reviewed"] == 3
    assert human_reviewed_counts(ctx.root, [CAT])["course-code"] == 3
    assert _columns(ctx) == ["Coded Notation"]  # columns only grow: a reopen doesn't withdraw it
