from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from discovery_doubles import seed_crawl_page

from common.keys import run_prefix
from common.object_store import open_store
from xtra.cli import cli

FOLDER = "catalog-example-edu"
RUN = "2026-09-17T14:20:01Z"
RUN_PATH = "2026-09-17T14-20-01Z"

# A page each extractor path has to deal with: one a college template
# reads, one that holds several courses, one whose text no template
# matches and whose markup does, a credential, a learning opportunity, a
# competency list, and a department page holding several credentials.
PAGES = {
    "engl101-aaaaaaaaaa": "course-clean-catalog.html",
    "multi-bbbbbbbbbb": "multi-course.html",
    "single-cccccccccc": "course-single.html",
    "program-dddddddddd": "program.html",
    "minor-eeeeeeeeee": "minor-requirements.html",
    "outcomes-ffffffffff": "outcomes-only.html",
    "department-gggggggggg": "department-multi-credential.html",
}


def seed(tmp_path: Path, fixture_html_dir: Path) -> None:
    store = open_store(str(tmp_path))
    for stem, name in PAGES.items():
        seed_crawl_page(
            store,
            FOLDER,
            RUN,
            stem,
            (fixture_html_dir / name).read_text(encoding="utf-8"),
            f"https://catalog.example.edu/{stem}",
        )


def discover(tmp_path: Path, *extra: str):
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


def extract(tmp_path: Path, *extra: str):
    return CliRunner().invoke(
        cli,
        [
            "catalog",
            "extract",
            "--with-template",
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


def run_dir(tmp_path: Path) -> Path:
    return tmp_path / run_prefix(FOLDER, RUN)


def report_of(tmp_path: Path) -> dict:
    return json.loads(
        (run_dir(tmp_path) / "extract-report.json").read_text(encoding="utf-8")
    )


@pytest.fixture
def discovered(tmp_path: Path, fixture_html_dir: Path) -> Path:
    seed(tmp_path, fixture_html_dir)
    assert discover(tmp_path).exit_code == 0
    return tmp_path


def test_extract_writes_a_record_for_each_single_course_page(
    discovered: Path,
) -> None:
    result = extract(discovered)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "engl101-aaaaaaaaaa" in payload["records"]

    record = json.loads(
        (run_dir(discovered) / "records" / "engl101-aaaaaaaaaa.json").read_text(
            encoding="utf-8"
        )
    )
    assert record["verification"]["status"] == "candidate"
    assert record["expected"]["course_id"] == "ENGL101"
    assert record["expected"]["course_credits"] == 3


def test_the_record_carries_the_crawl_stem_not_the_old_slug(
    discovered: Path,
) -> None:
    """Slot.stem still slugs the URL, which finds nothing in storage."""
    extract(discovered)
    record = json.loads(
        (run_dir(discovered) / "records" / "engl101-aaaaaaaaaa.json").read_text(
            encoding="utf-8"
        )
    )
    assert record["stem"] == "engl101-aaaaaaaaaa"
    assert record["record_id"] == "engl101-aaaaaaaaaa"
    assert "catalog-example-edu-engl101" not in record["stem"]


def test_the_record_takes_its_time_from_the_sidecar(discovered: Path) -> None:
    extract(discovered)
    record = json.loads(
        (run_dir(discovered) / "records" / "engl101-aaaaaaaaaa.json").read_text(
            encoding="utf-8"
        )
    )
    assert record["retrieved_at"] == "2026-09-17T14:20:05Z"
    assert record["institution_name"] == ""


def test_a_multi_course_page_is_skipped_with_its_reason(
    discovered: Path,
) -> None:
    extract(discovered)
    report = report_of(discovered)
    skip = next(
        item for item in report["skipped"] if item["stem"] == "multi-bbbbbbbbbb"
    )
    assert skip["reason"] == "multi_course_page"
    assert "3 course block" in skip["detail"]


def test_a_page_matching_no_template_is_read_from_its_markup(
    discovered: Path,
) -> None:
    """The college templates are not the only reading any more.

    This page matches none of them. Its markup labels its fields, which
    is all any of them was ever reading for.
    """
    extract(discovered)
    record = json.loads(
        (run_dir(discovered) / "records" / "single-cccccccccc.json").read_text(
            encoding="utf-8"
        )
    )
    assert record["template_id"] == "markup"
    assert record["entity_type"] == "Course"
    assert record["expected"]["course_credits"] == 3
    assert record["expected"]["course_department"] == "English"


def test_each_entity_discovery_labels_becomes_its_own_record(
    discovered: Path,
) -> None:
    """Discovery labels four entities, and all four are extracted now.

    A credential and a learning opportunity were labelled and then went
    nowhere: the templates are course templates, so nothing downstream
    could read either of them.
    """
    extract(discovered)
    entities = {}
    for path in (run_dir(discovered) / "records").iterdir():
        record = json.loads(path.read_text(encoding="utf-8"))
        entities[path.stem] = (
            record["entity_type"],
            record["ctdl_expected"]["class_uri"],
        )
    assert entities["program-dddddddddd"] == (
        "Credential",
        "ceterms:Credential",
    )
    assert entities["minor-eeeeeeeeee"] == (
        "LearningProgram",
        "ceterms:LearningProgram",
    )
    assert entities["outcomes-ffffffffff"] == ("Competency", "ceasn:Competency")


def test_a_competency_record_carries_one_competency_per_outcome(
    discovered: Path,
) -> None:
    extract(discovered)
    record = json.loads(
        (
            run_dir(discovered) / "records" / "outcomes-ffffffffff.json"
        ).read_text(encoding="utf-8")
    )
    texts = [
        prop["value"]
        for prop in record["ctdl_expected"]["properties"]
        if prop["property"] == "ceasn:competencyText"
    ]
    assert len(texts) >= 2
    assert all(isinstance(text, str) and text for text in texts)


def test_a_page_of_several_credentials_is_skipped_with_its_reason(
    discovered: Path,
) -> None:
    """The same rule as a page of several courses, one entity up."""
    extract(discovered)
    report = report_of(discovered)
    skip = next(
        item
        for item in report["skipped"]
        if item["stem"] == "department-gggggggggg"
    )
    assert skip["reason"] == "multi_credential_page"


def test_the_report_sits_beside_records_and_never_inside_it(
    discovered: Path,
) -> None:
    """transform reads every JSON under records/, so a report there is a course."""
    extract(discovered)
    assert (run_dir(discovered) / "extract-report.json").is_file()
    assert not (
        run_dir(discovered) / "records" / "extract-report.json"
    ).exists()
    record_files = sorted(
        path.name for path in (run_dir(discovered) / "records").iterdir()
    )
    assert "extract-report.json" not in record_files
    assert "engl101-aaaaaaaaaa.json" in record_files


def test_the_report_counts_the_skips_by_reason(discovered: Path) -> None:
    extract(discovered)
    report = report_of(discovered)
    assert report["schema"] == "xtra-extract-report-1"
    assert report["records_written"] == 5
    assert report["skipped_by_reason"] == {
        "multi_course_page": 1,
        "multi_credential_page": 1,
    }


def test_extract_reads_the_newest_discovery_run(
    discovered: Path, monkeypatch
) -> None:
    """A rule change means a new discovery run, and extract follows it."""
    monkeypatch.setattr(
        "xtra.catalog.discover.utc_timestamp", lambda: "2036-09-19T09:00:00Z"
    )
    assert discover(discovered).exit_code == 0
    result = extract(discovered)
    assert result.exit_code == 0, result.output
    assert (
        json.loads(result.output)["discovery_run_id"] == "2036-09-19T09-00-00Z"
    )


def test_a_named_discovery_run_wins_over_the_newest(
    discovered: Path, monkeypatch
) -> None:
    first = json.loads(extract(discovered).output)["discovery_run_id"]
    monkeypatch.setattr(
        "xtra.catalog.discover.utc_timestamp", lambda: "2036-09-19T09:00:00Z"
    )
    assert discover(discovered).exit_code == 0
    result = extract(discovered, "--discovery-run-id", first)
    assert json.loads(result.output)["discovery_run_id"] == first


def test_only_golden_sample_limits_extraction_to_the_sample(
    tmp_path: Path, fixture_html_dir
) -> None:
    seed(tmp_path, fixture_html_dir)
    assert discover(tmp_path, "--sample-size", "1").exit_code == 0

    sample_stems = {
        page["stem"]
        for page in json.loads(
            next((tmp_path / run_prefix(FOLDER, RUN) / "discovery").iterdir())
            .joinpath("golden-sample-course.json")
            .read_text(encoding="utf-8")
        )["pages"]
    }
    result = extract(tmp_path, "--only-golden-sample")
    assert result.exit_code == 0, result.output
    report = report_of(tmp_path)
    assert report["only_golden_sample"] is True
    assert report["pages_considered"] == len(sample_stems)
    assert report["pages_considered"] < 3


def test_extract_without_a_discovery_run_says_what_to_do(
    tmp_path: Path, fixture_html_dir
) -> None:
    seed(tmp_path, fixture_html_dir)
    result = extract(tmp_path)
    assert result.exit_code != 0
    assert "xtra catalog discover" in result.output


def test_extract_requires_a_strategy(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "extract",
            "--source-uri",
            str(tmp_path),
            "--target-uri",
            str(tmp_path),
            "--catalog-id",
            FOLDER,
            "--run-id",
            RUN,
        ],
    )
    assert result.exit_code != 0
    assert "--with-template" in result.output


def test_extract_ai_agent_is_stub(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "catalog",
            "extract",
            "--with-ai-agent",
            "--source-uri",
            str(tmp_path),
            "--target-uri",
            str(tmp_path),
            "--catalog-id",
            FOLDER,
            "--run-id",
            RUN,
        ],
    )
    assert result.exit_code != 0
    assert "not implemented" in result.output.lower()


def test_extract_help_lists_the_new_flags() -> None:
    help_text = CliRunner().invoke(cli, ["catalog", "extract", "--help"]).output
    assert "--only-golden-sample" in help_text
    assert "--discovery-run-id" in help_text
