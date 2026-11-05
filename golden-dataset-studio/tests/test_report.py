"""The run report's pure helpers (report.py, one-rule-runs spec §2): quotes are found as people read them, page text is
one line per block, lists are said in words. The checks and the resolved report run on a real catalog in
test_one_rule_runs.py."""

from __future__ import annotations

from golden_datasets.report import context_lines, found, page_text, plain, words


def test_quotes_are_found_with_plain_quotes_dashes_and_whitespace():
    note = "When the resource is in a catalog,  use the property “ceterms:inCatalog” instead – not here."
    assert found('use the property "ceterms:inCatalog" instead - not', note)
    assert found("When the resource … instead", note) and found("When the resource ... instead", note)
    assert not found("instead … When the resource", note)  # pieces in order
    assert not found("Jared said so", note) and not found("…", note) and not found("x", None)
    assert plain("a  b\n c") == "a b c"


def test_page_text_is_one_line_per_block_and_context_lines():
    html = (b"<html><head><title>T</title></head><body><h1>BIOL 110 - General Biology</h1><p>4.0 Units</p>"
            b"<div>Prerequisite: None.<br>A comprehensive and in-depth introduction.</div><p>Lecture.</p></body></html>")
    text = page_text(html)
    assert text.split("\n") == ["BIOL 110 - General Biology", "4.0 Units", "Prerequisite: None.",
                                "A comprehensive and in-depth introduction.", "Lecture."]
    assert context_lines("A comprehensive and in-depth", text) == ("Prerequisite: None.", "Lecture.")
    assert context_lines("BIOL 110", text) == (None, "4.0 Units")


def test_words():
    assert [words(x) for x in ([], ["A"], ["A", "B"], ["A", "B", "C"])] == ["", "A", "A and B", "A, B and C"]
