from __future__ import annotations

from discovery_doubles import make_profile

from implementations.discover_patterns import (
    assign_patterns,
    build_patterns,
    build_stats,
    build_vocabulary,
)
from implementations.discover_sample import (
    choose_sample,
    features_of,
    largest_remainder,
    order_key,
    population_for,
)


def sample_of(profiles, *, label="Course", size=30):
    vocabulary = build_vocabulary(profiles)
    assign_patterns(profiles, vocabulary)
    stats = build_stats(profiles, vocabulary)
    patterns = build_patterns(profiles, vocabulary, stats)
    return choose_sample(
        profiles,
        vocabulary,
        label=label,
        size=size,
        patterns_total=len(patterns),
    )


def ordinary_run(count: int = 60):
    """A run where one label and one marker are common and two are not."""
    profiles = [
        make_profile(f"course{index}", field_labels=["credits", "department"])
        for index in range(count)
    ]
    profiles[0].markers = {"ceu": "CEU"}
    profiles[1].markers = {"printed_zero_hours": "Hours 0"}
    profiles[2].field_labels = ["credits", "department", "studio fee"]
    return profiles


def test_the_population_is_the_label_minus_copies_and_empty_pages() -> None:
    profiles = [
        make_profile("keep"),
        make_profile("copy", duplicate_of="keep"),
        make_profile("empty", markers={"empty_or_error_page": "0 characters"}),
        make_profile("program", page_type="LearningOpportunity"),
    ]
    assert [p.stem for p in population_for(profiles, "Course")] == ["keep"]


def test_a_duplicate_never_reaches_the_sample() -> None:
    profiles = ordinary_run(10)
    for profile in profiles[5:]:
        profile.duplicate_of = "course0"
    sample = sample_of(profiles, size=30)
    assert sample.population_size == 5
    assert len(sample.pages) == 5
    assert all(not page.stem.startswith("course5") for page in sample.pages)


def test_the_sample_covers_every_feature_in_the_population() -> None:
    profiles = ordinary_run()
    sample = sample_of(profiles)
    assert sample.feature_count > 0
    assert sample.features_covered_count == sample.feature_count

    vocabulary = build_vocabulary(profiles)
    chosen = {page.stem for page in sample.pages}
    covered: set[str] = set()
    for profile in profiles:
        if profile.stem in chosen:
            covered |= features_of(profile, vocabulary)
    every = set()
    for profile in population_for(profiles, "Course"):
        every |= features_of(profile, vocabulary)
    assert every <= covered


def test_the_rare_pages_are_the_first_ones_taken() -> None:
    """A page carrying a marker nobody else has must be in the sample."""
    profiles = ordinary_run()
    sample = sample_of(profiles, size=30)
    stems = {page.stem for page in sample.pages}
    assert {"course0", "course1"} <= stems
    forced = next(page for page in sample.pages if page.stem == "course0")
    assert "marker:ceu" in forced.features_covered
    assert forced.reason.startswith("covers ")


def test_a_label_only_one_page_prints_is_not_something_to_cover() -> None:
    """It cannot group anything, so it stays in the report, not the sample.

    course2 is the only page with `studio fee`, so it is not forced in; the
    label is still counted in the vocabulary for a reviewer to look at.
    """
    profiles = ordinary_run()
    vocabulary = build_vocabulary(profiles)
    assert vocabulary.label_pages["studio fee"] == 1
    assert "studio fee" in vocabulary.single_page
    course2 = next(p for p in profiles if p.stem == "course2")
    assert "label:studio fee" not in features_of(course2, vocabulary)


def test_the_sample_reaches_the_requested_size() -> None:
    sample = sample_of(ordinary_run(), size=30)
    assert len(sample.pages) == 30
    assert sample.population_smaller_than_requested is False
    filled = [page for page in sample.pages if "proportional" in page.reason]
    assert filled


def test_a_small_population_is_taken_whole_and_says_so() -> None:
    sample = sample_of(ordinary_run(7), size=30)
    assert sample.population_size == 7
    assert len(sample.pages) == 7
    assert sample.population_smaller_than_requested is True


def test_coverage_may_need_more_pages_than_asked_for() -> None:
    """Every page is its own special case, so the cap cannot be honoured."""
    profiles = [
        make_profile(f"odd{index}", markers={f"marker{index}": "x"})
        for index in range(12)
    ]
    sample = sample_of(profiles, size=3)
    assert len(sample.pages) == 12
    assert sample.features_covered_count == sample.feature_count
    assert sample.coverage_forced_extra
    assert all(
        name.startswith("marker:") for name in sample.coverage_forced_extra
    )


def test_the_same_pages_always_give_the_same_sample() -> None:
    first = sample_of(ordinary_run(), size=30)
    second = sample_of(ordinary_run(), size=30)
    assert first.as_dict() == second.as_dict()


def test_the_sample_does_not_depend_on_the_order_pages_arrive_in() -> None:
    forwards = sample_of(ordinary_run(), size=25)
    backwards = sample_of(list(reversed(ordinary_run())), size=25)
    assert [page.stem for page in forwards.pages] == [
        page.stem for page in backwards.pages
    ]


def test_the_filled_part_of_the_sample_follows_pattern_share() -> None:
    common = [
        make_profile(f"common{index}", field_labels=["credits", "department"])
        for index in range(80)
    ]
    rare = [
        make_profile(
            f"rare{index}",
            field_labels=["credits", "department"],
            markers={"ceu": "CEU"},
        )
        for index in range(20)
    ]
    sample = sample_of(common + rare, size=20)
    chosen = {page.stem for page in sample.pages}
    from_common = sum(1 for stem in chosen if stem.startswith("common"))
    assert 12 <= from_common <= 18
    assert sample.patterns_in_sample == 2


def test_a_page_is_never_taken_twice() -> None:
    sample = sample_of(ordinary_run(), size=30)
    stems = [page.stem for page in sample.pages]
    assert len(stems) == len(set(stems))


def test_the_report_counts_match_the_pages_listed() -> None:
    sample = sample_of(ordinary_run(), size=30)
    payload = sample.as_dict()
    assert payload["features_covered_count"] == payload["feature_count"]
    assert payload["patterns_in_sample"] <= payload["patterns_total"]
    assert len(payload["pages"]) == 30
    assert payload["label"] == "Course"


def test_the_catalog_year_is_not_something_to_cover() -> None:
    """Every page of one catalog shares it, so it demonstrates nothing."""
    profiles = ordinary_run(5)
    for profile in profiles:
        profile.markers["catalog_year"] = "2026-2027"
    vocabulary = build_vocabulary(profiles)
    assert all(
        "catalog_year" not in name
        for name in features_of(profiles[0], vocabulary)
    )


def test_largest_remainder_hands_out_every_seat() -> None:
    quota = largest_remainder({"a": 80, "b": 15, "c": 5}, 10, 100)
    assert sum(quota.values()) == 10
    assert quota["a"] == 8


def test_largest_remainder_is_safe_at_the_edges() -> None:
    assert largest_remainder({"a": 1}, 0, 1) == {"a": 0}
    assert largest_remainder({}, 5, 0) == {}


def test_the_order_key_is_the_hash_of_the_url() -> None:
    assert order_key("https://x.edu/a") != order_key("https://x.edu/b")
    assert order_key("https://x.edu/a") == order_key("https://x.edu/a")
