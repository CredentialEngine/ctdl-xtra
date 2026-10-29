"""The Claude loop (W6): `rule list/show/annotations/draft/try/publish`, `pages get/sample`.

Fast tests cover the draft checks; `slow` tests run the real loop on AVC in a copy of `.data/root` (pages are
symlinks into the read-only mirror, never written)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from golden_datasets import loop
from golden_datasets.cli import main
from golden_datasets.errors import UserError

DESCRIPTION_V2_REGEX = (r"\A\s*(?:(?i:pre-?requisites?|co-?requisites?)\s*:[^\n]*?(?:\.[ \t]+(?=[A-Z(])|\n|\Z)\s*)*"
                        r"(\S[\s\S]*?)\s*\Z")
# A first draft that also drops Advisory / Limitation lines (spec §5.1 "why"): changes 4 values marked correct.
TOO_EAGER_REGEX = DESCRIPTION_V2_REGEX.replace("co-?requisites?)", "co-?requisites?|advisory|limitation on enrollment)")


# ---------------------------------------------------------------------------------------------- fast
def _field(definition, examples):
    return {"kind": "field", "definition": {"locator": "loc", "rule_type": "css", "selector": ".x", **definition},
            "examples": examples}


def test_examples_pass_and_fail():
    ok = _field({"regex": DESCRIPTION_V2_REGEX, "group": 1, "transforms": ["strip"]},
                [{"input": "Prerequisite: Completion of DFST 201.\n\nAdvanced study of ASL grammar.",
                  "output": "Advanced study of ASL grammar."},
                 {"input": "Advisory: Skills.\nText.", "output": "Advisory: Skills.\nText."}])
    assert loop.check_examples({"course-description": ok}) == []
    bad = _field({"transforms": ["strip"]}, [{"input": " A ", "output": "B"}, {"output": "no input"}])
    failures = loop.check_examples({"r": bad})
    assert len(failures) == 2 and 'got "A", expected "B"' in failures[0] and "needs" in failures[1]


def test_examples_skip_constants_and_empty_output_matches_no_value():
    const = {"kind": "field", "definition": {"locator": "l", "rule_type": "constant", "value": "Course"},
             "examples": [{"input": "x", "output": "y"}]}
    empty = _field({"regex": r"^(Z+)$"}, [{"input": "abc", "output": ""}])
    assert loop.check_examples({"c": const, "e": empty}) == []


def test_invalid_regex_and_selector_are_user_errors():
    with pytest.raises(UserError, match="not a valid regex"):
        loop._validate_definition("r", _field({"regex": "(unclosed"}, []))
    with pytest.raises(UserError, match="not a valid CSS selector"):
        loop._validate_definition("r", _field({"selector": "div[[["}, []))
    loop._validate_definition("r", _field({"selector": "div.introtext > p"}, []))


def test_read_draft_errors(tmp_path):
    with pytest.raises(UserError, match="no draft file"):
        loop.read_draft(str(tmp_path / "missing.json"))
    p = tmp_path / "d.json"
    p.write_text("{not json")
    with pytest.raises(UserError, match="not valid JSON"):
        loop.read_draft(str(p))


# ---------------------------------------------------------------------------------------------- slow
@pytest.fixture(scope="module")
def root(tmp_path_factory, avc_v1_root):
    """An independent copy of the session's AVC v1 root (AVC at ruleset v1, rs-0001, Jared's 153 annotations)."""
    dst = tmp_path_factory.mktemp("w6") / "root"
    assert main(["sync", "--from", str(avc_v1_root), "--to", str(dst), "-c", "avc", "--pages", "link"]) == 0
    return str(dst)


def run(root, capsys, *argv) -> tuple[int, str, str]:
    capsys.readouterr()
    code = main([*argv, "--root", root, "-c", "avc"])
    out = capsys.readouterr()
    return code, out.out, out.err


def _draft(root, capsys, tmp_path, name, regex) -> str:
    code, out, _ = run(root, capsys, "rule", "draft", "course-description")
    assert code == 0
    doc = json.loads(out)
    assert doc["base_ruleset"] == 1 and doc["rules"][0]["definition"]["selector"] == ".introtext"
    r = doc["rules"][0]
    r["definition"].update(regex=regex, group=1)
    r["why"] = "Jared marked 5 descriptions wrong (GEOG222, PHYS102, DFST202, AUTO230, ENGR955): Prerequisite line."
    r["examples"] = [{"input": "Prerequisite: Completion of DFST 201.\n\nAdvanced study of ASL grammar.",
                      "output": "Advanced study of ASL grammar."}]
    path = tmp_path / name
    path.write_text(json.dumps(doc))
    return str(path)


@pytest.mark.slow
def test_read_commands(root, capsys):
    code, out, _ = run(root, capsys, "rule", "list")
    assert code == 0
    line = next(x for x in out.splitlines() if " course-description " in x)
    assert "needs work" in line and "14 / 1,062" in line and "contains-label-text 547" in line
    code, out, _ = run(root, capsys, "rule", "show", "course-description")
    assert code == 0 and '"selector": ".introtext"' in out and "versions:     v1 (current)" in out
    code, out, _ = run(root, capsys, "rule", "annotations", "course-description", "--open")
    assert code == 0 and "5 annotation(s) that still need work" in out
    for code_ in ("GEOG222", "PHYS102", "DFST202", "AUTO230", "ENGR955"):
        assert f"WRONG — {code_}" in out
    assert "$GOLDEN_DATASETS_ROOT/avc-elumenapp-com-catalog-2026-27-welcome/" in out and "expected at: html > " in out
    code, out, _ = run(root, capsys, "rule", "annotations", "course-description")
    assert out.count("CORRECT — ") == 9
    code, out, _ = run(root, capsys, "pages", "get", "course-geog222")
    path = Path(out.split("\t")[0])
    assert code == 0 and path.name.startswith("avc-elumenapp-com-catalog-2026-27-course-geog222") and path.exists()
    code, out, _ = run(root, capsys, "pages", "sample", "--rule", "course-description", "--signal",
                       "contains-label-text", "-n", "3")
    assert code == 0 and out.count("$GOLDEN_DATASETS_ROOT/") == 3


@pytest.mark.slow
def test_try_refuse_publish_check(root, capsys, tmp_path):
    good = _draft(root, capsys, tmp_path, "good.json", DESCRIPTION_V2_REGEX)
    eager = _draft(root, capsys, tmp_path, "eager.json", TOO_EAGER_REGEX)

    code, out, _ = run(root, capsys, "rule", "try", good)
    assert code == 0, out
    assert "fixed 5 · still wrong 0 · newly wrong 0" in out
    assert "values changed    278 of 1062" in out and "BETTER" in out and "nothing written" in out

    code, out, _ = run(root, capsys, "rule", "try", good, "--json")
    card = json.loads(out)["cards"][0]
    assert (card["annotated"]["fixed"], card["values"]["changed"], card["b_version"]) == (5, 278, 2)

    code, out, err = run(root, capsys, "rule", "publish", eager)
    assert code == 2 and "refusing to publish" in err
    assert "newly wrong (marked correct, value changed): ACCT199, AERO199, CFE114, NS922L" in out
    code, out, _ = run(root, capsys, "rule", "list")
    assert "ruleset v1 · extraction rs-0001" in out  # nothing written

    bad_example = json.loads(Path(good).read_text())
    bad_example["rules"][0]["examples"][0]["output"] = "nope"
    p = tmp_path / "bad-example.json"
    p.write_text(json.dumps(bad_example))
    code, _, err = run(root, capsys, "rule", "try", str(p))
    assert code == 1 and "example 1" in err
    code, _, _ = run(root, capsys, "rule", "publish", str(p))
    assert code == 2

    code, out, _ = run(root, capsys, "rule", "publish", good, "--by", "test", "--note", "drop requisite lines")
    assert code == 0, out
    assert "published ruleset v2 (parent v1): course-description v2" in out
    assert "extraction rs-0002 (parent rs-0001)" in out and "copied 16 rules" in out
    code, out, _ = run(root, capsys, "rule", "publish", good)
    assert code == 0 and "no-op" in out
    code, out, _ = run(root, capsys, "check")
    assert code == 0, out
    code, out, _ = run(root, capsys, "rule", "list")
    line = next(x for x in out.splitlines() if " course-description " in x)
    assert "ruleset v2 · extraction rs-0002" in out and " v2 " in line and "in review" in line
    code, out, _ = run(root, capsys, "rule", "annotations", "course-description")
    assert out.count("— fixed") == 5
