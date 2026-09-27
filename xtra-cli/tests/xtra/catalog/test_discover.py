from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner
from discovery_doubles import seed_crawl_manifest, seed_crawl_page

from common.object_store import open_store
from xtra.cli import cli
from xtra.config.settings import StoredConfig, save_config

FOLDER = "catalog-example-edu"
RUN = "2026-09-17T14:20:01Z"
RUN_PATH = "2026-09-17T14-20-01Z"

FIXTURES = (
    "course-single.html",
    "course-prereq-coreq-combined.html",
    "course-lecture-lab-credit.html",
    "course-with-outcomes.html",
    "program.html",
    "outcomes-only.html",
    "multi-course.html",
    "policy-course-numbering.html",
    "error-page.html",
    "course-title-in-h2.html",
)


def seed(tmp_path: Path, fixture_html_dir: Path) -> None:
    store = open_store(str(tmp_path))
    for name in FIXTURES:
        stem = Path(name).stem
        seed_crawl_page(
            store,
            FOLDER,
            RUN,
            stem,
            (fixture_html_dir / name).read_text(encoding="utf-8"),
            f"https://catalog.example.edu/{stem}",
        )


def invoke(tmp_path: Path, *extra: str):
    return CliRunner().invoke(
        cli,
        [
            "catalog",
            "discover",
            "--source-uri",
            str(tmp_path),
            "--target-uri",
            str(tmp_path),
            "--catalog-id",
            FOLDER,
            "--run-id",
            RUN,
            *extra,
        ],
    )


def discovery_runs(tmp_path: Path) -> list[Path]:
    root = tmp_path / FOLDER / RUN_PATH / "discovery"
    return sorted(root.iterdir()) if root.is_dir() else []


def summary_of(result) -> dict:
    return json.loads(result.output.split("\n\n", 1)[1])


def test_discover_profiles_the_run_and_writes_a_report(
    tmp_path: Path, fixture_html_dir
) -> None:
    seed(tmp_path, fixture_html_dir)
    result = invoke(tmp_path)
    assert result.exit_code == 0, result.output

    summary = summary_of(result)
    assert summary["schema"] == "xtra-discovery-1"
    assert summary["pages"] == len(FIXTURES)
    assert summary["catalog_folder"] == FOLDER
    assert summary["run_id"] == RUN
    assert summary["patterns_total"] >= 5

    runs = discovery_runs(tmp_path)
    assert len(runs) == 1
    assert sorted(path.name for path in runs[0].iterdir()) == [
        "field-labels.csv",
        "golden-sample-course.json",
        "labels.json",
        "pages.jsonl",
        "patterns.json",
        "patterns.md",
        "summary.json",
    ]


def test_the_pattern_table_is_printed_before_the_summary(
    tmp_path: Path, fixture_html_dir
) -> None:
    seed(tmp_path, fixture_html_dir)
    result = invoke(tmp_path)
    table = result.output.split("\n\n", 1)[0]
    assert table.splitlines()[0].startswith("pattern")
    assert "page_type" in table
    assert "special" in table


def test_the_discovery_run_folder_is_a_utc_timestamp(
    tmp_path: Path, fixture_html_dir
) -> None:
    seed(tmp_path, fixture_html_dir)
    invoke(tmp_path)
    name = discovery_runs(tmp_path)[0].name
    assert name.endswith("Z")
    assert ":" not in name


def test_a_second_run_lands_beside_the_first(
    tmp_path: Path, fixture_html_dir, monkeypatch
) -> None:
    """Never overwrite: two runs are how a rule change is compared."""
    seed(tmp_path, fixture_html_dir)
    stamps = iter(["2026-09-18T09:00:00Z", "2026-09-19T09:00:00Z"])
    monkeypatch.setattr(
        "xtra.catalog.discover.utc_timestamp", lambda: next(stamps)
    )
    assert invoke(tmp_path).exit_code == 0
    assert invoke(tmp_path).exit_code == 0
    assert [path.name for path in discovery_runs(tmp_path)] == [
        "2026-09-18T09-00-00Z",
        "2026-09-19T09-00-00Z",
    ]


def test_running_twice_in_the_same_second_is_refused(
    tmp_path: Path, fixture_html_dir, monkeypatch
) -> None:
    seed(tmp_path, fixture_html_dir)
    monkeypatch.setattr(
        "xtra.catalog.discover.utc_timestamp", lambda: "2026-09-18T09:00:00Z"
    )
    assert invoke(tmp_path).exit_code == 0
    again = invoke(tmp_path)
    assert again.exit_code != 0
    assert "never overwritten" in again.output


def test_the_sample_size_and_label_are_honoured(
    tmp_path: Path, fixture_html_dir
) -> None:
    seed(tmp_path, fixture_html_dir)
    result = invoke(tmp_path, "--sample-size", "2", "--sample-label", "Course")
    assert result.exit_code == 0, result.output
    assert summary_of(result)["sample_size"] == 2
    sample = json.loads(
        (discovery_runs(tmp_path)[0] / "golden-sample-course.json").read_text(
            encoding="utf-8"
        )
    )
    assert sample["label"] == "Course"
    assert sample["requested_size"] == 2


def test_a_different_label_writes_a_different_sample_file(
    tmp_path: Path, fixture_html_dir
) -> None:
    seed(tmp_path, fixture_html_dir)
    result = invoke(tmp_path, "--sample-label", "Competency")
    assert result.exit_code == 0, result.output
    names = [path.name for path in discovery_runs(tmp_path)[0].iterdir()]
    assert "golden-sample-competency.json" in names


def test_a_run_with_nothing_crawled_points_at_the_crawl(tmp_path: Path) -> None:
    result = invoke(tmp_path)
    assert result.exit_code != 0
    assert "xtra catalog crawl" in result.output


def test_a_run_id_that_is_not_a_timestamp_is_rejected(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "discover",
            "--source-uri",
            str(tmp_path),
            "--target-uri",
            str(tmp_path),
            "--catalog-id",
            FOLDER,
            "--run-id",
            "yesterday",
        ],
    )
    assert result.exit_code != 0
    assert "2026-09-17T14:20:01Z" in result.output


def test_discover_uses_the_active_environment(
    tmp_path: Path, fixture_html_dir
) -> None:
    seed(tmp_path, fixture_html_dir)
    save_config(StoredConfig(env_name="dev", data_uri=str(tmp_path)))
    result = CliRunner().invoke(
        cli,
        ["catalog", "discover", "--catalog-id", FOLDER, "--run-id", RUN],
    )
    assert result.exit_code == 0, result.output
    assert discovery_runs(tmp_path)


def test_discover_help_lists_its_flags() -> None:
    help_text = (
        CliRunner().invoke(cli, ["catalog", "discover", "--help"]).output
    )
    for flag in (
        "--catalog-id",
        "--run-id",
        "--stem",
        "--sample-label",
        "--sample-size",
        "--source-uri",
        "--target-uri",
        "--env",
    ):
        assert flag in help_text


def test_an_empty_golden_sample_exits_non_zero_and_still_writes_the_reports(
    tmp_path: Path, fixture_html_dir
) -> None:
    """Nothing to review is a result, and a result has to be noticed."""
    seed(tmp_path, fixture_html_dir)
    result = invoke(tmp_path, "--sample-label", "Rubric")
    assert result.exit_code == 1
    assert "golden sample is empty" in result.output
    assert "Course 5" in result.output

    written = [path.name for path in discovery_runs(tmp_path)[0].iterdir()]
    assert "golden-sample-rubric.json" in written
    assert "summary.json" in written


def test_the_summary_says_which_crawl_these_pages_came_from(
    tmp_path: Path, fixture_html_dir
) -> None:
    seed(tmp_path, fixture_html_dir)
    seed_crawl_manifest(open_store(str(tmp_path)), FOLDER, RUN)
    result = invoke(tmp_path)
    assert result.exit_code == 0, result.output
    crawl = summary_of(result)["crawl"]
    assert crawl["crawl_json_found"] is True
    assert crawl["strategy"] == "playwright"
    assert crawl["status"] == "complete"


def test_stem_reads_one_page_of_the_run(
    tmp_path: Path, fixture_html_dir
) -> None:
    """Why is this page labelled that way, without rereading the crawl."""
    seed(tmp_path, fixture_html_dir)
    result = invoke(tmp_path, "--stem", "course-single")
    assert result.exit_code == 0, result.output

    summary = summary_of(result)
    assert summary["pages"] == 1
    assert summary["stems_requested"] == ["course-single"]
    assert summary["whole_run"] is False


def test_stem_is_repeatable(tmp_path: Path, fixture_html_dir) -> None:
    seed(tmp_path, fixture_html_dir)
    result = invoke(tmp_path, "--stem", "course-single", "--stem", "program")
    assert result.exit_code == 0, result.output
    assert summary_of(result)["stems_requested"] == [
        "course-single",
        "program",
    ]


def test_a_stem_the_crawl_never_saved_says_where_stems_come_from(
    tmp_path: Path, fixture_html_dir
) -> None:
    seed(tmp_path, fixture_html_dir)
    result = invoke(tmp_path, "--stem", "not-a-page")
    assert result.exit_code != 0
    assert "not-a-page" in result.output
    assert ".meta.json" in result.output
