"""The pack CLI (python lib/cli.py <command>): its arguments, and the exit
code and output of each command with the engine stage behind it faked."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import build
import cli
import college_capture
import dynamic_slots
import pytest
import registry
import validate
from inventory import csv_text
from lib_doubles import (
    COURSE_HTML,
    example_slot,
    write_freeze,
    write_normalized,
)
from normalize import normalize_html, sha256_text
from template_texts import CLEAN_CATALOG

STEM = "catalog-example-edu-english-engl101"


def test_url_files_skip_blank_lines_comments_and_trailing_notes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "urls.txt"
    path.write_text(
        "# seeds\n\nhttps://a.example.edu  note\n https://b.example.edu\n",
        encoding="utf-8",
    )
    assert cli._load_url_file(path) == [
        "https://a.example.edu",
        "https://b.example.edu",
    ]


def test_urls_from_flags_and_a_file_are_deduplicated_in_order(
    tmp_path: Path,
) -> None:
    path = tmp_path / "urls.txt"
    path.write_text("https://b.example.edu\nhttps://c.example.edu\n", "utf-8")
    args = argparse.Namespace(
        urls=["https://a.example.edu", "https://b.example.edu"],
        url_file=str(path),
    )
    assert cli._collect_urls(args) == [
        "https://a.example.edu",
        "https://b.example.edu",
        "https://c.example.edu",
    ]


def test_a_command_is_required() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2


def test_crawl_without_any_url_exits_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["crawl"]) == 2
    assert "crawl needs --url or --url-file" in capsys.readouterr().err


def fake_harvest(monkeypatch: pytest.MonkeyPatch, slots: list) -> list[dict]:
    calls: list[dict] = []

    def harvest(urls: list[str], **options: object) -> tuple:
        calls.append({"urls": urls, **options})
        return list(slots), [{"seed_url": urls[0], "family": "custom_html"}], 5

    monkeypatch.setattr(college_capture, "harvest_seeds", harvest)
    return calls


def test_crawl_that_finds_nothing_exits_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_harvest(monkeypatch, [])
    assert cli.main(["crawl", "--url", "https://catalog.example.edu"]) == 1
    assert "no course URLs discovered" in capsys.readouterr().err


def test_crawl_queues_the_harvest_trimmed_to_the_limit(
    pack: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slots = [
        example_slot(),
        example_slot(
            record_id="example-math101-course",
            requested_url="https://catalog.example.edu/math/math101",
        ),
    ]
    calls = fake_harvest(monkeypatch, slots)
    argv = ["crawl", "--url", "https://catalog.example.edu", "--limit", "1"]
    assert cli.main([*argv, "--institution", "Example"]) == 0
    assert calls == [
        {
            "urls": ["https://catalog.example.edu"],
            "per_college": None,
            "total_limit": 1,
            "fetch_all": False,
            "institution": "Example",
        }
    ]
    payload = json.loads((pack / "slots.json").read_text(encoding="utf-8"))
    assert [row["record_id"] for row in payload["slots"]] == [
        "example-engl101-course"
    ]
    assert payload["discovery"][0]["family"] == "custom_html"


def test_crawl_all_keeps_everything_it_found(
    pack: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slots = [example_slot(), example_slot(record_id="example-engl101-link")]
    fake_harvest(monkeypatch, slots)
    argv = ["crawl", "--url", "https://catalog.example.edu", "--all"]
    assert cli.main([*argv, "--limit", "1"]) == 0
    assert len(dynamic_slots.load_slots()) == 2


@pytest.mark.parametrize(
    ("status", "code"), [("ok", 0), ("refused", 0), ("error", 1)]
)
def test_freeze_fails_only_when_a_fetch_failed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: str,
    code: int,
) -> None:
    report = {"copied": [], "fetched": [{"status": status}], "records": 1}
    monkeypatch.setattr(cli, "freeze_all", lambda: report)
    assert cli.main(["freeze"]) == code
    assert json.loads(capsys.readouterr().out) == {
        "copied": 0,
        "fetched": 1,
        "records": 1,
    }


def test_normalize_writes_the_text_and_records_its_hash_in_the_meta(
    pack: Path,
) -> None:
    snapshot = write_freeze(pack, example_slot(), COURSE_HTML)
    dynamic_slots.write_slots([example_slot()])
    assert cli.main(["normalize"]) == 0
    text = (pack / "normalized" / f"{STEM}.txt").read_text(encoding="utf-8")
    assert text == normalize_html(COURSE_HTML)
    meta = json.loads(
        (snapshot.parent / f"{STEM}.meta.json").read_text(encoding="utf-8")
    )
    assert meta["normalized_text_sha256"] == sha256_text(text)
    assert meta["normalized_chars"] == len(text)


def test_normalize_without_a_snapshot_exits_1(
    pack: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dynamic_slots.write_slots([example_slot()])
    assert cli.main(["normalize"]) == 1
    assert "missing snapshot" in capsys.readouterr().err


def queue_two_pages(pack: Path) -> None:
    known = example_slot(template_id="custom_html")
    unknown = example_slot(
        record_id="example-about-course",
        requested_url="https://catalog.example.edu/about/staff",
    )
    write_normalized(pack, known, CLEAN_CATALOG)
    write_normalized(pack, unknown, "Staff directory\n")
    dynamic_slots.write_slots(
        [known, unknown], extra={"discovery": [{"family": "custom_html"}]}
    )


def test_classify_stamps_templates_drops_unknown_pages_and_keeps_extras(
    pack: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    queue_two_pages(pack)
    assert cli.main(["classify"]) == 0
    out = capsys.readouterr().out
    assert out.startswith(
        "drop unknown template https://catalog.example.edu/about/staff\n"
    )
    report = json.loads(out[out.index("{") :])
    assert report["classified"] == 1
    assert report["dropped_unknown_template"] == 1
    payload = json.loads((pack / "slots.json").read_text(encoding="utf-8"))
    assert [row["template_id"] for row in payload["slots"]] == [
        "clean_catalog_course_detail"
    ]
    assert payload["discovery"] == [{"family": "custom_html"}]


def test_classify_leaves_a_fixed_slot_list_alone(
    pack: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue_two_pages(pack)
    before = (pack / "slots.json").read_text(encoding="utf-8")
    monkeypatch.setattr(cli, "SLOTS_NAME", "fixed")
    assert cli.main(["classify"]) == 0
    assert (pack / "slots.json").read_text(encoding="utf-8") == before


def test_classify_with_nothing_recognised_exits_1(pack: Path) -> None:
    write_normalized(pack, example_slot(), "Staff directory\n")
    dynamic_slots.write_slots([example_slot()])
    assert cli.main(["classify"]) == 1


@pytest.mark.parametrize(
    ("command", "module", "name"),
    [("build", build, "build_pack"), ("hydrate", build, "hydrate_pack")],
)
@pytest.mark.parametrize(("errors", "code"), [([], 0), (["r: broken"], 1)])
def test_build_and_hydrate_exit_1_on_any_record_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    module: object,
    name: str,
    errors: list[str],
    code: int,
) -> None:
    monkeypatch.setattr(module, name, lambda: errors)
    assert cli.main([command]) == code
    assert capsys.readouterr().err == "".join(f"{e}\n" for e in errors)


def test_validate_reports_ok_or_every_error(
    pack: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[bool] = []

    def validate_pack(path: Path, *, strict_promotion: bool) -> list[str]:
        calls.append(strict_promotion)
        return [] if not strict_promotion else ["template gate"]

    monkeypatch.setattr(validate, "validate_pack", validate_pack)
    assert cli.main(["validate"]) == 0
    assert capsys.readouterr().out == (
        "ok: 0 candidate records passed runtime checks\n"
    )
    assert cli.main(["validate", "--strict-promotion"]) == 1
    assert capsys.readouterr().err == "template gate\n"
    assert calls == [False, True]


def test_assemble_and_registry_print_what_they_wrote(
    pack: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        build, "assemble_manifest", lambda: pack / "MANIFEST.json"
    )
    assert cli.main(["assemble"]) == 0
    assert capsys.readouterr().out == f"{pack / 'MANIFEST.json'}\n"
    monkeypatch.setattr(registry, "lookup_pack", lambda: [{}, {}])
    assert cli.main(["registry"]) == 0
    assert json.loads(capsys.readouterr().out) == {"lookups": 2}


def test_write_inventory_writes_the_field_inventory_csv(tmp_path: Path) -> None:
    out = tmp_path / "FIELD_INVENTORY.csv"
    assert cli.main(["write-inventory", "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == csv_text()
