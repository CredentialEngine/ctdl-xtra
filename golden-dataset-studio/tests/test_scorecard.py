from golden_datasets.scorecard import outcome, pair_rows, word_diff


def test_outcome_order_follows_the_spec_query():
    assert outcome("wrong", "Prereq: X. Text", "Prereq: X. Text", "Text") == "unchanged"
    assert outcome("wrong", "Prereq: X. Text", "Text", "Text") == "fixed"
    assert outcome("correct", "A", "B", None) == "newly wrong"
    assert outcome("wrong", "A", "B", "C") == "still wrong"
    assert outcome("wrong", "A  b", "A b", "x") == "unchanged"  # whitespace-insensitive


def test_pair_rows_falls_back_to_record_external_identifier():
    a = [{"key": "p@x", "record_external_identifier": "A1", "page_stem": "p", "value": "1"},
         {"key": "p@gone", "record_external_identifier": "Z9", "page_stem": "p", "value": "z"}]
    b = [{"key": "p@y", "record_external_identifier": "A1", "page_stem": "p", "value": "1"},
         {"key": "p@new", "record_external_identifier": "N1", "page_stem": "p", "value": "n"}]
    pairs, new, vanished = pair_rows(a, b)
    assert [(x["key"], y["key"]) for x, y in pairs] == [("p@x", "p@y")]
    assert [r["key"] for r in new] == ["p@new"] and [r["key"] for r in vanished] == ["p@gone"]


def test_word_diff():
    d = word_diff("Prerequisite: X. Text here", "Text here")
    assert "".join(p["text"] for p in d if p["op"] != "add") == "Prerequisite: X. Text here"
    assert "".join(p["text"] for p in d if p["op"] != "del") == "Text here"
