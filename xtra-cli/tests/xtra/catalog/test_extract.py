from __future__ import annotations

import json
import re
from pathlib import Path

import click
import pytest
from click.testing import CliRunner
from discovery_doubles import seed_crawl_page
from extract_doubles import COURSE_FIXTURES, fixture_html, fixture_url

from common.keys import (
    baseline_record_key,
    extract_resource_key,
    extraction_match_report_key,
    page_stem,
    property_extract_report_key,
    records_prefix,
)
from common.object_store import open_store
from implementations.score_extraction_match import MODE_EXACT
from xtra.catalog.extract import (
    CLASSES,
    PROPERTY_PATH_RE,
    RegistryError,
    choose_extractor,
    extractors,
)
from xtra.cli import cli

FOLDER = "catalog-example-edu"
RUN = "2026-09-17T14:20:01Z"
NAME = "ceterms:name"

# --- the registry ------------------------------------------------------------


def test_the_registry_finds_the_name_extractor() -> None:
    extractor = extractors()[NAME]
    assert [c.rdf_type for c in extractor.classes] == ["ceterms:Course"]
    assert extractor.classes[0].page_label == "Course"


def test_every_registered_property_is_a_ctdl_property() -> None:
    for prop in extractors():
        assert PROPERTY_PATH_RE.fullmatch(prop)


def test_every_class_is_keyed_by_its_own_rdf_type() -> None:
    for rdf_type, rdf_class in CLASSES.items():
        assert rdf_class.rdf_type == rdf_type


READS = "def read(occurrence, page):\n    return None\n"
COURSE_NAME = f"PROPERTY = 'ceterms:name'\nCLASS = ('ceterms:Course',)\n{READS}"


def _package(root: Path, name: str, files: dict[str, str]) -> None:
    """A throwaway extractor tree: {"ceterms/ceterms_name.py": body}."""
    (root / name).mkdir()
    (root / name / "__init__.py").write_text("")
    for relative, body in files.items():
        path = root / name / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        folder = path.parent
        while folder != root / name:
            (folder / "__init__.py").touch()
            folder = folder.parent
        path.write_text(body)


def _registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, files
) -> dict:
    _package(tmp_path, name, files)
    monkeypatch.syspath_prepend(str(tmp_path))
    return extractors(name)


def test_a_property_file_lives_in_its_vocabulary_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _registry(
        tmp_path,
        monkeypatch,
        "vocabularies",
        {"ceterms/ceterms_name.py": COURSE_NAME},
    )
    assert list(registry) == ["ceterms:name"]


def test_a_file_has_to_be_named_for_the_property_it_declares(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(RegistryError, match="named ceterms_name"):
        _registry(
            tmp_path,
            monkeypatch,
            "misnamed_extractors",
            {"ceterms/name.py": COURSE_NAME},
        )


def test_a_file_has_to_be_in_the_folder_of_its_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(RegistryError, match="belongs in ceterms/"):
        _registry(
            tmp_path,
            monkeypatch,
            "wrong_vocabulary",
            {"schema/ceterms_name.py": COURSE_NAME},
        )


def test_a_property_file_outside_a_vocabulary_folder_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(RegistryError, match="outside a vocabulary folder"):
        _registry(
            tmp_path,
            monkeypatch,
            "loose",
            {"ceterms_name.py": COURSE_NAME},
        )


def test_nothing_nests_deeper_than_the_vocabulary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(RegistryError, match="nothing deeper"):
        _registry(
            tmp_path,
            monkeypatch,
            "nested",
            {"ceterms/ceterms_Course/ceterms_name.py": COURSE_NAME},
        )


def test_a_property_file_has_to_declare_its_property(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(RegistryError, match="declares no PROPERTY"):
        _registry(
            tmp_path,
            monkeypatch,
            "undeclared",
            {"ceterms/ceterms_name.py": READS},
        )


def test_a_declared_property_has_to_be_a_ctdl_property(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(RegistryError, match="is not a CTDL property"):
        _registry(
            tmp_path,
            monkeypatch,
            "not_a_property",
            {"ceterms/ceterms_name.py": f"PROPERTY = 'name'\n{READS}"},
        )


def test_a_property_file_has_to_declare_its_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(RegistryError, match="declares no CLASS"):
        _registry(
            tmp_path,
            monkeypatch,
            "no_class",
            {"ceterms/ceterms_name.py": f"PROPERTY = 'ceterms:name'\n{READS}"},
        )


@pytest.mark.parametrize(
    ("declared", "message"),
    [
        ("'ceterms:Course'", "is not a tuple of CTDL classes"),
        ("()", "is not a tuple of CTDL classes"),
        ("('ceterms:Nope',)", "names ceterms:Nope. Classes: ceterms:Course"),
    ],
)
def test_its_class_is_a_tuple_of_known_classes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    declared: str,
    message: str,
) -> None:
    body = f"PROPERTY = 'ceterms:name'\nCLASS = {declared}\n{READS}"
    with pytest.raises(RegistryError, match=message):
        _registry(
            tmp_path,
            monkeypatch,
            f"class_{abs(hash(declared))}",
            {"ceterms/ceterms_name.py": body},
        )


def test_a_property_path_is_named_with_double_underscores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _registry(
        tmp_path,
        monkeypatch,
        "paths",
        {
            "ceterms/ceterms_creditValue__schema_value.py": (
                "PROPERTY = 'ceterms:creditValue > schema:value'\n"
                f"CLASS = ('ceterms:Course',)\n{READS}"
            )
        },
    )
    assert list(registry) == ["ceterms:creditValue > schema:value"]


# --- choosing from the command line ----------------------------------------


def test_a_registered_property_is_chosen() -> None:
    assert choose_extractor(extractors(), NAME).prop == NAME


@pytest.mark.parametrize(
    ("prop", "message"),
    [
        ("name", "is not a CTDL property"),
        ("ceterms:nope", "Properties: ceterms:name"),
    ],
)
def test_an_unknown_property_names_what_there_is(
    prop: str, message: str
) -> None:
    with pytest.raises(click.UsageError, match=message):
        choose_extractor(extractors(), prop)


def test_help_lists_the_extractors_with_their_class() -> None:
    result = CliRunner().invoke(cli, ["catalog", "extract", "--help"])
    assert result.exit_code == 0
    assert "[OPTIONS] PROPERTY" in result.output
    assert "ceterms:name  (class: ceterms:Course)" in result.output


# --- end to end --------------------------------------------------------------


def _stem(name: str) -> str:
    return page_stem(fixture_url(name))


def _seed(tmp_path: Path) -> None:
    store = open_store(str(tmp_path))
    for path in sorted(COURSE_FIXTURES.glob("*.html")):
        url = fixture_url(path.stem)
        seed_crawl_page(
            store, FOLDER, RUN, page_stem(url), fixture_html(path.stem), url
        )


def _invoke(tmp_path: Path, *args: str):
    return CliRunner().invoke(
        cli,
        [
            "catalog",
            *args,
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


def _extract_names(tmp_path: Path):
    return _invoke(tmp_path, "extract", NAME)


@pytest.fixture
def discovered(tmp_path: Path) -> Path:
    _seed(tmp_path)
    assert _invoke(tmp_path, "discover").exit_code == 0
    return tmp_path


def _written(tmp_path: Path, code: str) -> dict:
    return open_store(str(tmp_path)).get_json(
        extract_resource_key(FOLDER, RUN, NAME, f"{FOLDER}_{code}")
    )


def test_every_course_on_a_page_gets_its_name(discovered: Path) -> None:
    result = _extract_names(discovered)
    assert result.exit_code == 0, result.output
    assert _written(discovered, "PHAR191") == {
        "type": "ceterms:Course",
        "resource_id": f"{FOLDER}_PHAR191",
        "ctdl_property": "ceterms:name",
        "value": "First-Year Seminar",
        "catalog_id": FOLDER,
        "source_url": fixture_url("courseleaf-courseblocks"),
        "retrieved_at": _written(discovered, "PHAR191")["retrieved_at"],
        "notes": _written(discovered, "PHAR191")["notes"],
    }
    assert _written(discovered, "PHAR199")["value"] == (
        "Orientation to Pharmacy 1-2 Hr"
    )


def test_the_files_follow_the_extractor_folders(discovered: Path) -> None:
    _extract_names(discovered)
    assert extract_resource_key(FOLDER, RUN, NAME, "x").endswith(
        "/extraction_report/ceterms/ceterms_name/x.json"
    )


def test_stdout_is_one_json_summary(discovered: Path) -> None:
    summary = json.loads(_extract_names(discovered).stdout)
    assert summary["property"] == "ceterms:name"
    assert summary["class"] == ["ceterms:Course"]
    assert summary["not_found_by_reason"] == {"empty_title": 1}
    assert summary["no_resource_id"] == 0
    assert summary["report_key"] == property_extract_report_key(
        FOLDER, RUN, NAME
    )


def test_the_report_counts_by_strategy_class_and_platform(
    discovered: Path,
) -> None:
    _extract_names(discovered)
    report = open_store(str(discovered)).get_json(
        property_extract_report_key(FOLDER, RUN, NAME)
    )
    assert report["found"] + report["not_found"] == report["resources_written"]
    assert (
        report["resources_written"] + report["no_resource_id"]
        == report["occurrences"]
    )
    assert report["by_strategy"]["profile_title"] == report["found"]
    assert {"courseleaf", "curriqunet", "elumen"} <= set(report["by_platform"])


def test_a_course_with_no_title_is_written_absent(discovered: Path) -> None:
    _extract_names(discovered)
    written = _written(discovered, "LAW793")
    assert written["value"] is None
    assert "reason=empty_title" in written["notes"]


def test_running_again_writes_the_same_files(discovered: Path) -> None:
    _extract_names(discovered)
    first = _written(discovered, "PSYCC1000")
    _extract_names(discovered)
    assert _written(discovered, "PSYCC1000") == first


def test_nothing_is_written_to_records(discovered: Path) -> None:
    _extract_names(discovered)
    store = open_store(str(discovered))
    assert list(store.list_keys(records_prefix(FOLDER, RUN))) == []


def _baseline_names(names: list[str], url: str) -> list[dict]:
    return [
        {
            "fields": [
                {"ctdl_property": "ceterms:name", "value": n, "source_url": url}
            ]
        }
        for n in names
    ]


def test_scoring_reads_the_extraction_report(
    discovered: Path, tmp_path_factory
) -> None:
    """Pages of one course and of several, paired in page order."""
    _extract_names(discovered)
    baseline = tmp_path_factory.mktemp("baseline")
    store = open_store(str(baseline))
    store.put_json(
        baseline_record_key(FOLDER, RUN, _stem("elumen-course")),
        _baseline_names(
            ["Introduction to Administration of Justice"],
            fixture_url("elumen-course"),
        ),
    )
    store.put_json(
        baseline_record_key(FOLDER, RUN, _stem("courseleaf-courseblocks")),
        _baseline_names(
            ["First-Year Seminar", "Orientation to Pharmacy 1-2 Hr"],
            fixture_url("courseleaf-courseblocks"),
        ),
    )
    result = CliRunner().invoke(
        cli,
        [
            "score",
            "extraction",
            "match",
            "--exactly",
            "--source-uri",
            str(discovered),
            "--baseline-uri",
            str(baseline),
            "--catalog-id",
            FOLDER,
            "--run-id",
            RUN,
        ],
    )
    assert result.exit_code == 0, result.output
    report = open_store(str(discovered)).get_json(
        extraction_match_report_key(FOLDER, RUN, MODE_EXACT)
    )
    assert report["by_property"]["ceterms:name"]["match"] == 3
    assert report["by_property"]["ceterms:name"]["mismatch"] == 0


def test_without_discovery_it_says_to_run_discover_first(
    tmp_path: Path,
) -> None:
    result = _extract_names(tmp_path)
    assert result.exit_code != 0
    assert "Run xtra catalog discover first" in result.output


# --- nothing fitted to one catalog -------------------------------------------

SRC = Path(__file__).resolve().parents[3] / "src"
EXTRACTION_CODE = [
    SRC / "implementations" / "extract_run.py",
    SRC / "implementations" / "extract_course.py",
    SRC / "xtra" / "catalog" / "extract.py",
    *sorted((SRC / "implementations" / "extract").rglob("*.py")),
]


def test_no_extraction_code_names_a_catalog_it_was_tested_on() -> None:
    """The fixtures come from real catalogs; the code must not know them."""
    hosts = {
        fixture_url(path.stem).split("/")[2]
        for path in COURSE_FIXTURES.glob("*.html")
    }
    # Words of an address that name no college: the vendors that host
    # catalogs (a platform may be named in the code) and the generic parts.
    generic = {
        "catalog",
        "training",
        "www",
        "edu",
        "com",
        "elumenapp",
        "curriqunet",
        "curricunet",
        "courseleaf",
    }
    words = (
        hosts
        | {label for host in hosts for label in host.split(".")[:-1]} - generic
    )
    for path in EXTRACTION_CODE:
        text = path.read_text(encoding="utf-8").lower()
        named = sorted(
            word
            for word in words
            if re.search(rf"\b{re.escape(word.lower())}\b", text)
        )
        assert named == [], f"{path.name} names {named}"
