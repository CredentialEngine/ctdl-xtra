from __future__ import annotations

from discovery_doubles import make_profile

from implementations.discover_patterns import (
    assign_patterns,
    build_patterns,
    build_stats,
    build_vocabulary,
    pattern_id_of,
    signature_of,
)


def run_of(profiles):
    vocabulary = build_vocabulary(profiles)
    assign_patterns(profiles, vocabulary)
    stats = build_stats(profiles, vocabulary)
    return vocabulary, stats, build_patterns(profiles, vocabulary, stats)


def test_a_label_on_nearly_every_page_is_site_chrome() -> None:
    """A menu heading is printed everywhere and distinguishes nothing."""
    profiles = [
        make_profile(
            f"course{index}", field_labels=["search catalog", "credits"]
        )
        for index in range(10)
    ]
    profiles.extend(
        make_profile(f"other{index}", field_labels=["search catalog"])
        for index in range(10)
    )
    vocabulary = build_vocabulary(profiles)
    assert vocabulary.share("search catalog") == 1.0
    assert "search catalog" in vocabulary.chrome
    assert "search catalog" not in vocabulary.signature_labels
    assert "credits" in vocabulary.signature_labels


def test_a_label_on_one_page_stays_in_the_report_but_not_the_signature() -> (
    None
):
    profiles = [
        make_profile(f"p{index}", field_labels=["credits"])
        for index in range(9)
    ]
    profiles.append(make_profile("odd", field_labels=["credits", "studio fee"]))
    vocabulary = build_vocabulary(profiles)
    assert "studio fee" in vocabulary.single_page
    assert "studio fee" not in vocabulary.signature_labels
    assert vocabulary.label_pages["studio fee"] == 1
    assert vocabulary.label_examples["studio fee"][1] == "odd"


def test_a_signature_is_the_page_type_its_labels_and_its_markers() -> None:
    profiles = [
        make_profile(
            f"course{index}",
            field_labels=["credits", "department"],
            markers={"prerequisite": "x"},
        )
        for index in range(10)
    ]
    profiles.extend(make_profile(f"bare{index}") for index in range(10))
    vocabulary = build_vocabulary(profiles)
    signature = signature_of(profiles[0], vocabulary)
    assert signature == "Course|credits;department|prerequisite"
    assert len(pattern_id_of(signature)) == 8


def test_the_catalog_year_is_left_out_of_the_signature() -> None:
    """Otherwise every page of a second catalog year is its own pattern."""
    profiles = [
        make_profile(
            "a", field_labels=["credits"], markers={"catalog_year": "2026-2027"}
        ),
        make_profile(
            "b", field_labels=["credits"], markers={"catalog_year": "2025-2026"}
        ),
    ]
    _, _, patterns = run_of(profiles)
    assert len(patterns) == 1


def test_pages_of_the_same_shape_land_in_one_pattern() -> None:
    profiles = [
        make_profile(f"p{index}", field_labels=["credits"])
        for index in range(5)
    ]
    profiles.append(
        make_profile("odd", field_labels=["credits"], markers={"ceu": "CEU"})
    )
    _, _, patterns = run_of(profiles)
    assert [pattern.count for pattern in patterns] == [5, 1]
    assert patterns[0].page_type == "Course"


def test_a_small_pattern_is_special() -> None:
    profiles = [
        make_profile(f"p{index}", field_labels=["credits"])
        for index in range(40)
    ]
    profiles.append(
        make_profile("odd", field_labels=["credits"], markers={"ceu": "CEU"})
    )
    _, _, patterns = run_of(profiles)
    odd = next(pattern for pattern in patterns if pattern.count == 1)
    assert odd.special
    assert any("only" in reason for reason in odd.special_because)
    assert not patterns[0].special


def test_a_marker_on_half_the_page_type_is_not_uncommon() -> None:
    profiles = [
        make_profile(f"p{index}", field_labels=["credits"])
        for index in range(10)
    ]
    profiles.extend(
        make_profile(
            f"q{index}", field_labels=["credits"], markers={"ceu": "CEU"}
        )
        for index in range(10)
    )
    _, _, patterns = run_of(profiles)
    assert all(
        "markers on under" not in " ".join(pattern.special_because)
        for pattern in patterns
    )


def test_a_pattern_with_an_uncommon_marker_is_special() -> None:
    """A marker on under a fifth of its page type is the point of the run."""
    profiles = [
        make_profile(f"p{index}", field_labels=["credits", "department"])
        for index in range(90)
    ]
    profiles.extend(
        make_profile(
            f"ceu{index}",
            field_labels=["credits", "department"],
            markers={"ceu": "CEU"},
        )
        for index in range(8)
    )
    _, stats, patterns = run_of(profiles)
    assert stats.marker_share("Course", "ceu") < 0.20
    odd = next(pattern for pattern in patterns if "ceu" in pattern.markers)
    assert odd.special
    assert any("markers on under" in reason for reason in odd.special_because)


def test_a_pattern_with_a_rare_field_label_is_special() -> None:
    profiles = [
        make_profile(f"p{index}", field_labels=["credits", "department"])
        for index in range(40)
    ]
    for index in range(2):
        profiles.append(
            make_profile(
                f"rare{index}",
                field_labels=["credits", "studio fee", "department"],
            )
        )
    _, stats, patterns = run_of(profiles)
    odd = next(
        pattern for pattern in patterns if "studio fee" in pattern.field_labels
    )
    assert odd.rare_field_labels == ["studio fee"]
    assert odd.special
    assert stats.label_share("Course", "studio fee") < 0.05


def test_an_archived_or_empty_pattern_is_always_special() -> None:
    profiles = [make_profile(f"p{index}") for index in range(10)]
    for name, marker in (
        ("arch", "archived"),
        ("empty", "empty_or_error_page"),
    ):
        profiles.extend(
            make_profile(f"{name}{index}", markers={marker: "x"})
            for index in range(10)
        )
    _, _, patterns = run_of(profiles)
    for marker in ("archived", "empty_or_error_page"):
        odd = next(pattern for pattern in patterns if marker in pattern.markers)
        assert odd.special, marker


def test_a_pattern_from_another_catalog_year_is_special() -> None:
    profiles = [
        make_profile(
            f"p{index}",
            field_labels=["credits"],
            markers={"catalog_year": "2026-2027"},
        )
        for index in range(20)
    ]
    profiles.append(
        make_profile(
            "old",
            field_labels=["credits"],
            markers={"catalog_year": "2019-2020", "ceu": "CEU"},
        )
    )
    _, _, patterns = run_of(profiles)
    odd = next(
        pattern for pattern in patterns if "2019-2020" in pattern.catalog_years
    )
    assert odd.special
    assert any("2019-2020" in reason for reason in odd.special_because)


def test_rarity_is_measured_inside_a_page_type_not_across_the_run() -> None:
    """One rare Competency label must not look common next to 90 courses."""
    profiles = [
        make_profile(f"c{index}", field_labels=["credits"])
        for index in range(90)
    ]
    profiles.extend(
        make_profile(
            f"k{index}", page_type="Competency", field_labels=["outcome"]
        )
        for index in range(10)
    )
    _, stats, _ = run_of(profiles)
    assert stats.label_share("Competency", "outcome") == 1.0
    assert stats.label_share("Course", "outcome") == 0.0


def test_patterns_are_reported_largest_first_and_stay_stable() -> None:
    profiles = [
        make_profile(f"p{index}", field_labels=["credits"])
        for index in range(3)
    ]
    profiles.append(
        make_profile("odd", field_labels=["credits"], markers={"ceu": "c"})
    )
    _, _, first = run_of(profiles)
    _, _, second = run_of(profiles)
    assert [p.pattern_id for p in first] == [p.pattern_id for p in second]
    assert first[0].count >= first[-1].count


def test_a_pattern_carries_evidence_and_examples() -> None:
    profiles = [
        make_profile(
            f"p{index}",
            field_labels=["credits"],
            markers={"ceu": f"quote {index}"},
        )
        for index in range(4)
    ]
    _, _, patterns = run_of(profiles)
    payload = patterns[0].as_dict()
    assert payload["markers"]["ceu"] == "quote 0"
    assert len(payload["example_urls"]) == 3
    assert len(payload["example_stems"]) == 3
