from __future__ import annotations

import json
import logging
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
    assert record["expected"]["ceterms:codedNotation"] == "ENGL101"
    assert record["expected"]["ceterms:creditValue"] == 3


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
    assert record["expected"]["ceterms:creditValue"] == 3
    assert record["expected"]["ceterms:creditUnitType"] == "Credits"
    assert record["expected"]["ceterms:prerequisite"] == (
        "placement into college-level reading."
    )
    # The department is read, but it is not minimum data for a course.
    assert "English" not in record["expected"].values()


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
        assert "ctdl_expected" not in record
        entities[path.stem] = record["entity_type"]
    assert entities["program-dddddddddd"] == "Credential"
    assert entities["minor-eeeeeeeeee"] == "LearningProgram"
    assert entities["outcomes-ffffffffff"] == "Competency"


def test_a_competency_record_carries_one_competency_per_outcome(
    discovered: Path,
) -> None:
    extract(discovered)
    record = json.loads(
        (
            run_dir(discovered) / "records" / "outcomes-ffffffffff.json"
        ).read_text(encoding="utf-8")
    )
    texts = record["expected"]["ceasn:competencyText"]
    read = [
        field
        for field in record["source_expected"]["fields"]
        if field["property"] == "ceasn:competencyText"
    ]
    assert isinstance(texts, list)
    assert len(texts) == len(read) >= 2
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


def extract_log(caplog) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == "xtra.catalog.extract"
        and record.levelno >= logging.INFO
    ]


def test_the_log_says_what_extraction_is_doing(
    discovered: Path, caplog, monkeypatch
) -> None:
    monkeypatch.setattr("xtra.catalog.extract.PROGRESS_EVERY", 2)
    with caplog.at_level(logging.INFO):
        result = extract(discovered)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    report = report_of(discovered)
    lines = extract_log(caplog)

    assert lines[0] == (
        f"EXTRACT {FOLDER} run {RUN} from {discovered}, using discovery run "
        f"{payload['discovery_run_id']}"
    )
    assert lines[1] == f"PAGES {report['pages_considered']} pages to extract"
    assert any(line.startswith("EXTRACT 2/") for line in lines)
    assert f"RECORDS {len(payload['records'])} written: " in "\n".join(lines)
    skips = " ".join(
        f"{reason}={count}"
        for reason, count in sorted(report["skipped_by_reason"].items())
    )
    assert f"SKIPPED {len(report['skipped'])}: {skips}" in lines
    assert lines[-2].startswith("WRITE extract-report.json -> ")
    assert lines[-1].startswith("DONE extraction in 00:00:")


def test_each_page_is_logged_only_at_debug(discovered: Path, caplog) -> None:
    with caplog.at_level(logging.DEBUG):
        extract(discovered)
    debug = [
        record.getMessage()
        for record in caplog.records
        if record.name == "xtra.catalog.extract"
        and record.levelno == logging.DEBUG
    ]
    assert any(line.startswith("RECORD engl101-aaaaaaaaaa ") for line in debug)
    assert any(
        line.startswith("SKIP https://catalog.example.edu/multi-bbbbbbbbbb ")
        for line in debug
    )


def test_a_reader_that_crashes_is_a_warning_not_the_end_of_the_run(
    discovered: Path, caplog, monkeypatch
) -> None:
    def crash(*args, **kwargs):
        raise StopIteration

    monkeypatch.setattr("xtra.catalog.extract.extract_record", crash)
    with caplog.at_level(logging.WARNING):
        result = extract(discovered)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["records"] == []
    fails = [line for line in extract_log(caplog) if line.startswith("FAIL ")]
    assert fails
    assert all(line.endswith(": StopIteration") for line in fails)


def test_records_left_from_an_earlier_run_are_a_warning(
    discovered: Path, caplog
) -> None:
    old = run_dir(discovered) / "records" / "from-an-earlier-run.json"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text("{}", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        extract(discovered)
    assert any(
        line.startswith("STALE 1 records in records/ were not written")
        for line in extract_log(caplog)
    )


def test_nothing_to_extract_is_a_warning(
    tmp_path: Path, fixture_html_dir, caplog
) -> None:
    seed_crawl_page(
        open_store(str(tmp_path)),
        FOLDER,
        RUN,
        "error-hhhhhhhhhh",
        (fixture_html_dir / "error-page.html").read_text(encoding="utf-8"),
        "https://catalog.example.edu/error-hhhhhhhhhh",
    )
    assert discover(tmp_path).exit_code in (0, 1)
    with caplog.at_level(logging.WARNING):
        result = extract(tmp_path)
    assert result.exit_code == 0, result.output
    assert any(
        line.startswith("PAGES nothing to extract")
        for line in extract_log(caplog)
    )


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
