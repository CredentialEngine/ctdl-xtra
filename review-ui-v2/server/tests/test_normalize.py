from review_ui.normalize import (
    normalize_value,
    record_id_from_code,
    safe_filename,
    values_match,
)


def test_values_match_ignores_whitespace_and_case():
    assert values_match("  Basic   Auto\nBody ", "basic auto body")


def test_values_match_distinguishes_different_text():
    assert not values_match("5.0", "5")


def test_none_matches_only_empty():
    assert values_match(None, "  ")
    assert not values_match(None, "x")
    assert normalize_value(None) == ""


def test_record_id_treats_spaced_and_unspaced_codes_as_the_same_course():
    assert record_id_from_code("AJ 101") == record_id_from_code("aj101") == "AJ101"


def test_safe_filename_replaces_path_characters():
    assert safe_filename("A/B C") == "A_B_C"
