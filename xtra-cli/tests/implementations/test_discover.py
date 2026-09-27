from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from discovery_doubles import seed_crawl_manifest, seed_crawl_page

from common.keys import discovery_key
from common.object_store import open_store
from implementations.discover import (
    DiscoverSettings,
    NoPagesError,
    UnknownStemError,
    field_labels_csv,
    latest_discovery_run_id,
    mark_duplicates,
    patterns_markdown,
    patterns_table,
    read_saved_pages,
    run_discovery,
    sample_file_name,
)
from implementations.discover_page import profile_page
from implementations.discover_patterns import (
    assign_patterns,
    build_patterns,
    build_stats,
    build_vocabulary,
)

FOLDER = "catalog-example-edu"
RUN = "2026-09-17T14:20:01Z"
RUN_PATH = "2026-09-17T14-20-01Z"
DISCOVERY = "2026-09-18T09-00-00Z"

ALL_FIXTURES = (
    "course-single.html",
    "course-prereq-coreq-combined.html",
    "course-lecture-lab-credit.html",
    "course-with-outcomes.html",
    "course-credit-hours-min.html",
    "course-list-no-credits.html",
    "program.html",
    "learning-program.html",
    "credential-certification.html",
    "outcomes-only.html",
    "multi-course.html",
    "policy-course-numbering.html",
    "error-page.html",
    "blocked-page.html",
    "course-title-in-h2.html",
)


def seed_run(
    tmp_path: Path,
    fixture_html_dir: Path,
    names=ALL_FIXTURES,
    *,
    extra: dict[str, str] | None = None,
):
    """Write a crawl run into storage, the way the crawler would have."""
    store = open_store(str(tmp_path))
    pages = {Path(name).stem: name for name in names}
    for stem, name in pages.items():
        html = (fixture_html_dir / name).read_text(encoding="utf-8")
        _put(store, stem, html, f"https://catalog.example.edu/{stem}")
    for stem, name in (extra or {}).items():
        html = (fixture_html_dir / name).read_text(encoding="utf-8")
        _put(store, stem, html, f"https://catalog.example.edu/{stem}")
    return store


def _put(store, stem: str, html: str, url: str) -> None:
    seed_crawl_page(store, FOLDER, RUN, stem, html, url)


def settings(
    discovery_run_id: str = DISCOVERY, **overrides
) -> DiscoverSettings:
    return DiscoverSettings(
        catalog_folder=FOLDER,
        run_id=RUN,
        discovery_run_id=discovery_run_id,
        source_uri=overrides.pop("source_uri", "file:///tmp/xtra"),
        **overrides,
    )


def discovery_dir(tmp_path: Path, discovery_run_id: str = DISCOVERY) -> Path:
    return tmp_path / FOLDER / RUN_PATH / "discovery" / discovery_run_id


def test_discovery_reads_every_saved_page(
    tmp_path: Path, fixture_html_dir
) -> None:
    store = seed_run(tmp_path, fixture_html_dir)
    pages = read_saved_pages(store, FOLDER, RUN)
    assert len(pages) == len(ALL_FIXTURES)
    assert all(html.strip().startswith("<!DOCTYPE") for _, html in pages)


def test_a_run_with_no_pages_says_so(tmp_path: Path) -> None:
    store = open_store(str(tmp_path))
    with pytest.raises(NoPagesError, match="no saved pages"):
        run_discovery(settings(), source=store, target=store)


def test_discovery_writes_every_report(
    tmp_path: Path, fixture_html_dir
) -> None:
    store = seed_run(tmp_path, fixture_html_dir)
    outcome = run_discovery(
        settings(), source=store, target=store, version="0.2.0"
    )

    written = sorted(path.name for path in discovery_dir(tmp_path).iterdir())
    assert written == [
        "field-labels.csv",
        "golden-sample-course.json",
        "labels.json",
        "pages.jsonl",
        "patterns.json",
        "patterns.md",
        "summary.json",
    ]
    assert outcome.summary["pages"] == len(ALL_FIXTURES)
    assert outcome.summary["xtra_version"] == "0.2.0"


def test_nothing_normalized_is_written(
    tmp_path: Path, fixture_html_dir
) -> None:
    store = seed_run(tmp_path, fixture_html_dir)
    run_discovery(settings(), source=store, target=store)
    names = [path.name for path in discovery_dir(tmp_path).iterdir()]
    assert not [name for name in names if name.endswith(".txt")]
    assert "normalized" not in " ".join(names)


def test_the_summary_counts_what_the_run_contains(
    tmp_path: Path, fixture_html_dir
) -> None:
    store = seed_run(tmp_path, fixture_html_dir)
    summary = run_discovery(settings(), source=store, target=store).summary
    assert summary["pages"] == 15
    assert summary["duplicates"] == 0
    assert summary["pages_by_page_type"] == {
        "Competency": 1,
        "Course": 7,
        "Credential": 2,
        "LearningOpportunity": 1,
        "Multiple": 1,
        "Unknown": 3,
    }
    assert summary["empty_or_error_pages"] == 2
    assert summary["unknown_share"] == 0.2
    assert summary["run_id"] == RUN
    assert summary["discovery_run_id"] == DISCOVERY
    assert summary["patterns_total"] >= 5


def test_the_same_text_under_two_urls_is_one_page_and_one_copy(
    tmp_path: Path, fixture_html_dir
) -> None:
    store = seed_run(
        tmp_path,
        fixture_html_dir,
        extra={"course-single-copy": "course-single.html"},
    )
    outcome = run_discovery(settings(), source=store, target=store)
    assert outcome.summary["duplicates"] == 1

    pair = {"course-single", "course-single-copy"}
    copies = [profile for profile in outcome.profiles if profile.duplicate_of]
    assert len(copies) == 1
    # Which of the two is kept is decided by storage order, not by luck, so
    # the only thing worth pinning is that one of the pair points at the other.
    assert {copies[0].stem, copies[0].duplicate_of} == pair
    assert copies[0].stem not in {page.stem for page in outcome.sample.pages}

    again = run_discovery(
        settings("2026-09-19T09-00-00Z"), source=store, target=store
    )
    kept = [profile for profile in again.profiles if profile.duplicate_of]
    assert kept[0].stem == copies[0].stem


def test_mark_duplicates_keeps_the_first_page_seen() -> None:
    first = profile_page(url="https://x.edu/a", html="<h1>Same</h1>", stem="a")
    second = profile_page(url="https://x.edu/b", html="<h1>Same</h1>", stem="b")
    assert mark_duplicates([first, second]) == 1
    assert first.duplicate_of is None
    assert second.duplicate_of == "a"


def test_labels_json_is_the_preprocessed_list_for_extraction(
    tmp_path: Path, fixture_html_dir
) -> None:
    store = seed_run(tmp_path, fixture_html_dir)
    run_discovery(settings(), source=store, target=store)
    payload = json.loads(
        (discovery_dir(tmp_path) / "labels.json").read_text(encoding="utf-8")
    )
    assert payload["schema"] == "xtra-labels-1"
    entry = next(
        page for page in payload["pages"] if page["stem"] == "course-single"
    )
    assert set(entry) == {
        "url",
        "stem",
        "page_type",
        "labels",
        "course_block_count",
        # Names only. Extract reads them to skip a page holding several
        # entities; the evidence for each marker is in patterns.md.
        "markers",
        "pattern_id",
    }
    assert all(isinstance(name, str) for name in entry["markers"])
    assert entry["labels"] == ["Course"]
    assert entry["course_block_count"] == 1

    multi = next(
        page for page in payload["pages"] if page["stem"] == "multi-course"
    )
    assert multi["course_block_count"] == 3


def test_pages_jsonl_has_one_line_per_page(
    tmp_path: Path, fixture_html_dir
) -> None:
    store = seed_run(tmp_path, fixture_html_dir)
    run_discovery(settings(), source=store, target=store)
    lines = (
        (discovery_dir(tmp_path) / "pages.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(lines) == len(ALL_FIXTURES)
    first = json.loads(lines[0])
    assert first["signature"]
    assert len(first["pattern_id"]) == 8


def test_a_second_discovery_run_does_not_overwrite_the_first(
    tmp_path: Path, fixture_html_dir
) -> None:
    store = seed_run(tmp_path, fixture_html_dir)
    run_discovery(settings(), source=store, target=store)
    run_discovery(settings("2026-09-19T09-00-00Z"), source=store, target=store)
    runs = sorted(
        path.name
        for path in (tmp_path / FOLDER / RUN_PATH / "discovery").iterdir()
    )
    assert runs == [DISCOVERY, "2026-09-19T09-00-00Z"]
    assert (discovery_dir(tmp_path) / "summary.json").is_file()


def test_rerunning_the_same_discovery_id_is_refused(
    tmp_path: Path, fixture_html_dir
) -> None:
    store = seed_run(tmp_path, fixture_html_dir)
    run_discovery(settings(), source=store, target=store)
    with pytest.raises(FileExistsError):
        run_discovery(settings(), source=store, target=store)


def test_the_newest_discovery_run_is_found_by_its_timestamp(
    tmp_path: Path, fixture_html_dir
) -> None:
    store = seed_run(tmp_path, fixture_html_dir)
    assert latest_discovery_run_id(store, FOLDER, RUN) is None
    run_discovery(settings("2026-09-18T09-00-00Z"), source=store, target=store)
    run_discovery(settings("2026-09-19T09-00-00Z"), source=store, target=store)
    assert latest_discovery_run_id(store, FOLDER, RUN) == "2026-09-19T09-00-00Z"


def test_the_field_label_report_lists_the_rarest_first(
    tmp_path: Path, fixture_html_dir
) -> None:
    store = seed_run(tmp_path, fixture_html_dir)
    run_discovery(settings(), source=store, target=store)
    csv_text = (discovery_dir(tmp_path) / "field-labels.csv").read_text(
        encoding="utf-8"
    )
    lines = csv_text.splitlines()
    assert lines[0] == (
        "label,pages,share,is_chrome,is_rare,example_url,example_stem"
    )
    counts = [
        int(line.split(",")[1])
        for line in lines[1:]
        if line and not line.startswith("heading,") and line.count(",") >= 6
    ]
    assert counts == sorted(counts)
    assert "heading,pages" in csv_text
    assert "Student Learning Outcomes" in csv_text


def test_the_pattern_report_puts_special_patterns_first(
    tmp_path: Path, fixture_html_dir
) -> None:
    store = seed_run(tmp_path, fixture_html_dir)
    run_discovery(settings(), source=store, target=store)
    markdown = (discovery_dir(tmp_path) / "patterns.md").read_text(
        encoding="utf-8"
    )
    assert markdown.index("## Special patterns") < markdown.index(
        "## Other patterns"
    )
    assert "storage" not in markdown.lower() or "file:///tmp/xtra" in markdown
    assert "Why it is special:" in markdown


def test_the_pattern_report_explains_each_marker(
    tmp_path: Path, fixture_html_dir
) -> None:
    store = seed_run(tmp_path, fixture_html_dir)
    outcome = run_discovery(settings(), source=store, target=store)
    markdown = patterns_markdown(outcome.patterns, settings=settings())
    assert "printed 0 is a real value" in markdown
    assert "Several courses share the page" in markdown


def test_the_pattern_report_links_the_saved_pages(
    tmp_path: Path, fixture_html_dir
) -> None:
    store = seed_run(tmp_path, fixture_html_dir)
    outcome = run_discovery(
        settings(source_uri="azure://https://acct.blob.core.windows.net/x"),
        source=store,
        target=store,
    )
    markdown = patterns_markdown(
        outcome.patterns,
        settings=settings(
            source_uri="azure://https://acct.blob.core.windows.net/x"
        ),
    )
    assert (
        f"azure://https://acct.blob.core.windows.net/x/{FOLDER}/{RUN_PATH}/pages/"
        in markdown
    )


def test_the_table_is_one_line_per_pattern(
    tmp_path: Path, fixture_html_dir
) -> None:
    store = seed_run(tmp_path, fixture_html_dir)
    outcome = run_discovery(settings(), source=store, target=store)
    lines = outcome.table.splitlines()
    assert lines[0].startswith("pattern")
    assert len(lines) == len(outcome.patterns) + 2
    assert "yes" in outcome.table


def test_the_golden_sample_is_written_under_its_label(
    tmp_path: Path, fixture_html_dir
) -> None:
    store = seed_run(tmp_path, fixture_html_dir)
    run_discovery(
        settings(sample_label="Course", sample_size=3),
        source=store,
        target=store,
    )
    payload = json.loads(
        (discovery_dir(tmp_path) / sample_file_name("Course")).read_text(
            encoding="utf-8"
        )
    )
    assert payload["label"] == "Course"
    assert payload["features_covered_count"] == payload["feature_count"]
    for page in payload["pages"]:
        assert page["reason"]


def test_discovery_never_opens_the_network(
    tmp_path: Path, fixture_html_dir
) -> None:
    """The autouse guard in conftest would fail this test if it did."""
    store = seed_run(tmp_path, fixture_html_dir)
    outcome = run_discovery(settings(), source=store, target=store)
    assert outcome.summary["pages"] == len(ALL_FIXTURES)


def test_helpers_survive_an_empty_run() -> None:
    vocabulary = build_vocabulary([])
    stats = build_stats([], vocabulary)
    assert build_patterns([], vocabulary, stats) == []
    assert patterns_table([]).splitlines()[0].startswith("pattern")
    assert "label,pages" in field_labels_csv(vocabulary, stats)


def test_the_profiles_carry_their_pattern_id(
    tmp_path: Path, fixture_html_dir
) -> None:
    store = seed_run(tmp_path, fixture_html_dir)
    outcome = run_discovery(settings(), source=store, target=store)
    assert all(len(profile.pattern_id) == 8 for profile in outcome.profiles)
    ids = {profile.pattern_id for profile in outcome.profiles}
    assert ids == {pattern.pattern_id for pattern in outcome.patterns}


def test_assign_patterns_is_what_writes_the_signature() -> None:
    profiles = [
        profile_page(url="https://x.edu/a", html="<dt>Credits</dt>", stem="a")
    ]
    assert profiles[0].signature == ""
    vocabulary = build_vocabulary(profiles)
    assign_patterns(profiles, vocabulary)
    assert profiles[0].signature.startswith("Unknown|")


def test_a_discovery_key_lands_under_the_crawl_run() -> None:
    key = discovery_key(FOLDER, RUN, DISCOVERY, "summary.json")
    assert key == f"{FOLDER}/{RUN_PATH}/discovery/{DISCOVERY}/summary.json"


# --- provenance and an empty sample -----------------------------------------


def test_the_summary_and_the_report_carry_the_crawl_provenance(
    tmp_path: Path, fixture_html_dir
) -> None:
    """A report read months later has to say what produced these pages."""
    store = seed_run(tmp_path, fixture_html_dir)
    seed_crawl_manifest(
        store,
        FOLDER,
        RUN,
        resolved_seed_url="https://catalog.elsewhere.edu/",
        status="incomplete",
        pages_saved=41,
    )
    outcome = run_discovery(settings(), source=store, target=store)

    crawl = outcome.summary["crawl"]
    assert crawl["crawl_json_found"] is True
    assert crawl["strategy"] == "playwright"
    assert crawl["seed_url"] == "https://catalog.example.edu/"
    assert crawl["resolved_seed_url"] == "https://catalog.elsewhere.edu/"
    assert crawl["effective_min_interval_in_seconds"] == 10.0
    assert crawl["status"] == "incomplete"
    assert crawl["pages_saved"] == 41
    assert crawl["note"] is None

    report = (discovery_dir(tmp_path) / "patterns.md").read_text(
        encoding="utf-8"
    )
    assert "## Where these pages came from" in report
    assert "`playwright`" in report
    assert "catalog.elsewhere.edu" in report
    assert "`incomplete`" in report
    assert "10.0 seconds per worker" in report


def test_a_run_with_no_crawl_json_says_so_instead_of_inventing_provenance(
    tmp_path: Path, fixture_html_dir, caplog
) -> None:
    store = seed_run(tmp_path, fixture_html_dir)
    with caplog.at_level(logging.WARNING):
        outcome = run_discovery(settings(), source=store, target=store)

    crawl = outcome.summary["crawl"]
    assert crawl["crawl_json_found"] is False
    assert crawl["strategy"] is None
    assert crawl["seed_url"] is None
    assert crawl["pages_saved"] is None
    assert "crawl.json was not found" in crawl["note"]
    assert [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("CRAWL ")
    ]

    report = (discovery_dir(tmp_path) / "patterns.md").read_text(
        encoding="utf-8"
    )
    assert "crawl.json was not found" in report


def test_an_empty_golden_sample_is_an_error_naming_what_was_found(
    tmp_path: Path, fixture_html_dir, caplog
) -> None:
    """Exit 0 with an empty sample is how a useless run went unnoticed."""
    store = seed_run(tmp_path, fixture_html_dir)
    with caplog.at_level(logging.ERROR):
        outcome = run_discovery(
            settings(sample_label="Rubric"), source=store, target=store
        )
    assert outcome.exit_code == 1
    assert outcome.sample.population_size == 0
    assert "Rubric" in outcome.reason

    errors = [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.ERROR
    ]
    assert len(errors) == 1
    assert "Rubric" in errors[0]
    assert "Course 7" in errors[0]
    assert "Unknown 3" in errors[0]

    # The reports are still written: they are what the tuning is read from.
    written = sorted(path.name for path in discovery_dir(tmp_path).iterdir())
    assert "summary.json" in written
    assert sample_file_name("Rubric") in written
    assert outcome.summary["sample_population"] == 0


def test_a_population_smaller_than_the_sample_size_warns_with_both_numbers(
    tmp_path: Path, fixture_html_dir, caplog
) -> None:
    store = seed_run(tmp_path, fixture_html_dir)
    with caplog.at_level(logging.WARNING):
        outcome = run_discovery(
            settings(sample_size=30), source=store, target=store
        )
    assert outcome.exit_code == 0
    assert outcome.summary["sample_population"] == 8

    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("SAMPLE ")
    ]
    assert len(warnings) == 1
    assert "only 8 pages" in warnings[0]
    assert "30" in warnings[0]


def test_a_sample_the_population_can_fill_says_nothing(
    tmp_path: Path, fixture_html_dir, caplog
) -> None:
    store = seed_run(tmp_path, fixture_html_dir)
    with caplog.at_level(logging.WARNING):
        outcome = run_discovery(
            settings(sample_size=2), source=store, target=store
        )
    assert outcome.exit_code == 0
    assert not [
        record
        for record in caplog.records
        if record.getMessage().startswith("SAMPLE ")
    ]


# --- reading named pages instead of the whole run ---------------------------


def test_named_stems_read_only_those_pages(
    tmp_path: Path, fixture_html_dir
) -> None:
    store = seed_run(tmp_path, fixture_html_dir)
    pages = read_saved_pages(store, FOLDER, RUN, ("course-single", "program"))
    assert [meta["stem"] for meta, _ in pages] == ["course-single", "program"]


def test_a_stem_the_run_never_saved_is_an_error(
    tmp_path: Path, fixture_html_dir
) -> None:
    """Silently profiling nothing would look like a page with no labels."""
    store = seed_run(tmp_path, fixture_html_dir)
    with pytest.raises(UnknownStemError) as raised:
        read_saved_pages(store, FOLDER, RUN, ("course-single", "not-a-page"))
    assert "not-a-page" in str(raised.value)
    assert "course-single" not in str(raised.value)


def test_a_run_of_named_stems_writes_the_usual_reports(
    tmp_path: Path, fixture_html_dir
) -> None:
    """The reports are the point: one page, all of its evidence."""
    store = seed_run(tmp_path, fixture_html_dir)
    outcome = run_discovery(
        settings(stems=("course-single",)), source=store, target=store
    )
    assert outcome.summary["pages"] == 1
    assert outcome.summary["stems_requested"] == ["course-single"]
    assert outcome.summary["whole_run"] is False
    lines = (
        (discovery_dir(tmp_path) / "pages.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(lines) == 1
    assert json.loads(lines[0])["labels"] == ["Course"]


def test_a_whole_run_says_so_in_its_summary(
    tmp_path: Path, fixture_html_dir
) -> None:
    """A reader has to know whether the shares below cover the crawl."""
    store = seed_run(tmp_path, fixture_html_dir)
    outcome = run_discovery(settings(), source=store, target=store)
    assert outcome.summary["whole_run"] is True
    assert outcome.summary["stems_requested"] == []


def test_reading_named_stems_warns_that_the_shares_are_narrowed(
    tmp_path: Path, fixture_html_dir, caplog
) -> None:
    store = seed_run(tmp_path, fixture_html_dir)
    with caplog.at_level(logging.WARNING):
        run_discovery(
            settings(stems=("course-single",)), source=store, target=store
        )
    assert any(
        "counted over those pages alone" in record.getMessage()
        for record in caplog.records
    )
