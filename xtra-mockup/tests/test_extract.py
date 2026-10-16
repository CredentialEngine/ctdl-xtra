"""Acceptance criteria for the extract step, run against the real page store if it has been crawled."""

import json
import shutil
from pathlib import Path

import pytest

from xtra.extract import run_extract

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "store"
SUBJECTS = ("ACCT", "CHEM", "CSCE", "ENGL", "NURS")

pytestmark = pytest.mark.skipif(not (STORE / "lookup.json").exists(), reason="run `xtra crawl` first")


def extract(tmp_path, name, language_model):
    data = tmp_path / name
    shutil.copytree(STORE, data / "store")
    shutil.copytree(ROOT / "data" / "ledger", data / "ledger")  # the same CTIDs as the real run
    assert run_extract(data, ROOT / "rules", ROOT / "reference", SUBJECTS, language_model) == 0
    return data / "out"


def files(out):
    return {p.relative_to(out).as_posix(): p.read_bytes() for p in sorted(out.rglob("*")) if p.is_file()}


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("extract")
    return {"none": extract(tmp, "a", "none"), "again": extract(tmp, "b", "none"), "nonsense": extract(tmp, "c", "nonsense")}


def test_546_records_by_subject(runs):
    report = json.loads((runs["none"] / "run-report.json").read_text())
    assert report["courses"] == {"total": 546, "bySubject": {"ACCT": 46, "CHEM": 86, "CSCE": 98, "ENGL": 171, "NURS": 145}}
    assert len(list((runs["none"] / "courses").glob("*.json"))) == 546


def test_every_title_line_matches_and_every_value_has_provenance(runs):
    report = json.loads((runs["none"] / "run-report.json").read_text())
    form = next(r for r in report["rules"] if r["name"] == "title-line.form")
    assert (form["matched"], form["misses"]) == (546, [])
    assert report["provenance"]["valuesWithoutAnEntry"] == []
    assert report["provenance"]["segmentsWhoseTextDoesNotMatch"] == 0
    assert report["conformance"]["failures"] == []


def test_running_twice_gives_the_same_output_apart_from_the_report_timestamp(runs):
    a, b = files(runs["none"]), files(runs["again"])
    assert a.keys() == b.keys()
    differing = [name for name in a if a[name] != b[name]]
    # The timestamp is to the second, so two quick runs can also be identical.
    assert differing in ([], ["run-report.json"])
    strip = lambda raw: {k: v for k, v in json.loads(raw).items() if k != "generatedAt"}
    assert strip(a["run-report.json"]) == strip(b["run-report.json"])


def test_running_again_changes_no_ctid(runs):
    ledger = (ROOT / "data" / "ledger" / "ctid-ledger.jsonl").read_text()
    assert (runs["none"].parent / "ledger" / "ctid-ledger.jsonl").read_text() == ledger


def test_a_language_model_that_returns_nonsense_changes_no_record(runs):
    for path in sorted((runs["none"] / "courses").glob("*.json")):
        plain = json.loads(path.read_text())["record"]
        nonsense = json.loads((runs["nonsense"] / "courses" / path.name).read_text())["record"]
        assert plain == nonsense, path.name


def test_sentences_are_kept_word_for_word_and_structures_name_only_linked_courses(runs):
    for path in sorted((runs["none"] / "courses").glob("*.json")):
        course = json.loads(path.read_text())
        for prop in ("ceterms:requires", "ceterms:corequisite", "ceterms:coPrerequisite"):
            entry = course["provenance"].get(f"/{prop}")
            if not entry:
                continue
            for profile, structure in zip(course["record"][prop], entry["structure"]):
                quote = " ".join(structure["sentence"]["quote"].replace(" ", " ").split())
                assert profile["ceterms:description"]["en-US"] == quote
                if structure["tree"]:
                    linked = [s for e in entry["evidence"] if e["role"] == "the course links" for s in e["segments"]]
                    links = sorted(s["start"] for s in linked if structure["sentence"]["start"] <= s["start"] < structure["sentence"]["end"])
                    used = sorted(n["start"] for n in walk(structure["tree"]) if n["kind"] == "course")
                    assert used == links, path.name  # none invented, none dropped


def walk(node):
    yield node
    for child in node.get("children", []):
        yield from walk(child)


def test_conformance_checks_can_fail(runs):
    from xtra.schema import Schema

    schema = Schema(ROOT / "reference")
    record = json.loads((runs["none"] / "courses" / "ACCT-20103.json").read_text())["record"]
    assert all(c["status"] == "pass" for c in schema.check(record, lambda ctid: True)[0])
    broken = {**record, "ceterms:madeUp": "x", "ceterms:name": "not wrapped", "ceterms:ctid": "123"}
    del broken["ceterms:inLanguage"]
    broken["ceterms:creditValue"] = [{**record["ceterms:creditValue"][0], "ceterms:creditUnitType": [{"@type": "ceterms:CredentialAlignmentObject", "ceterms:targetNode": "creditUnit:Fortnight"}]}]
    broken["ceterms:lifeCycleStatusType"] = "Active"
    failed = {c["id"] for c in schema.check(broken, lambda ctid: False)[0] if c["status"] == "fail"}
    assert {"V2", "V3", "V4", "V5", "V6", "V7"} <= failed
