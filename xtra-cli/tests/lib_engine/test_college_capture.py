"""College capture: harvest seeds, drop dead and unreadable pages, and the
trimming run_college_capture does around the build. Every engine stage it
drives is faked here; tests/lib_engine/test_pipeline_offline.py runs the
real ones."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from pathlib import Path

import build
import cli
import college_capture
import dynamic_slots
import pytest
import quality
import registry
import validate
from college_capture import (
    _is_dead_html,
    attach_templates,
    drop_dead_slots,
    harvest_seeds,
    run_college_capture,
)
from discover import HarvestError
from lib_doubles import example_slot, write_freeze, write_normalized
from slots import Slot
from template_texts import CLEAN_CATALOG

SEED = "https://catalog.example.edu"


def slot_at(path: str, host: str = "catalog.example.edu") -> Slot:
    name = path.strip("/").replace("/", "-")
    return example_slot(
        record_id=f"{host.split('.')[1]}-{name}-course",
        requested_url=f"https://{host}/{path}",
        page_id=f"{host.split('.')[1]}-{name}",
    )


@pytest.mark.parametrize(
    ("html", "status", "dead"),
    [
        ("<p>ok</p>", 404, True),
        ("<p>ok</p>", 410, True),
        ("<title>404 Page</title>", 200, True),
        ("<TITLE>Page Not Found</TITLE>", None, True),
        ("<title>Course not found</title>", None, True),
        ("<title>ENGL101 | Catalog</title>", 200, False),
        ("<p>no title at all</p>", None, False),
        # A title tag with attributes is not looked at.
        ('<title lang="en">Not Found</title>', None, False),
    ],
)
def test_a_page_is_dead_by_its_status_or_its_title(
    html: str, status: int | None, dead: bool
) -> None:
    assert _is_dead_html(html, status) is dead


def test_dead_and_unfrozen_pages_are_dropped(
    pack: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    live = slot_at("english/engl101")
    dead = slot_at("english/engl999")
    unfrozen = slot_at("english/engl102")
    write_freeze(pack, live, "<title>ENGL101</title>")
    write_freeze(pack, dead, "<p>gone</p>", meta={"http_status": 404})
    assert drop_dead_slots([live, dead, unfrozen]) == [live]
    assert capsys.readouterr().out == f"drop 404 {dead.requested_url}\n"


def test_attach_templates_copies_every_field_and_stamps_the_template(
    pack: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """college_capture rebuilds Slot positionally; a dataclasses.replace
    comparison catches a field that lands in the wrong place."""
    known = example_slot(
        template_id="custom_html",
        copy_html=Path("saved/x.html"),
        multi_entity_bundle=True,
        notes="bundle",
    )
    unknown = slot_at("about/staff")
    unread = slot_at("english/engl102")
    write_normalized(pack, known, CLEAN_CATALOG)
    write_normalized(pack, unknown, "Staff directory\n")
    result = attach_templates([known, unknown, unread], pack / "normalized")
    assert result == [
        dataclasses.replace(known, template_id="clean_catalog_course_detail")
    ]
    assert capsys.readouterr().out == (
        f"drop unknown template {unknown.requested_url}\n"
    )


def fake_harvester(
    monkeypatch: pytest.MonkeyPatch, found: int = 2
) -> list[tuple]:
    calls: list[tuple] = []

    def harvest(seed: str, *, want: int, fetch_all: bool) -> dict:
        calls.append((seed, want, fetch_all))
        host = seed.split("//")[1]
        return {
            "seed_url": seed,
            "family": "custom_html",
            "institution_name": "Harvested",
            "discovered": found,
            "slots": [slot_at(f"english/c{n}", host) for n in range(found)],
        }

    monkeypatch.setattr(college_capture, "harvest_with_playwright", harvest)
    return calls


@pytest.mark.parametrize(
    ("seeds", "options", "want_each"),
    [
        ([SEED], {"fetch_all": True}, 10_000),
        ([SEED], {"per_college": 3}, 3),
        ([SEED], {"total_limit": 7}, 7),
        ([SEED], {}, 30),
        ([SEED, "https://catalog.other.edu"], {}, 5),
    ],
)
def test_the_per_college_target_follows_the_flags(
    monkeypatch: pytest.MonkeyPatch,
    seeds: list[str],
    options: dict,
    want_each: int,
) -> None:
    calls = fake_harvester(monkeypatch)
    flags = {
        "per_college": None,
        "total_limit": None,
        "fetch_all": False,
        "institution": None,
        **options,
    }
    _, reports, want = harvest_seeds(seeds, **flags)
    assert want == want_each
    assert [want for _, want, _ in calls] == [want_each * 4] * len(seeds)
    assert all("slots" not in report for report in reports)


def test_an_institution_name_overrides_the_harvested_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_harvester(monkeypatch)
    slots, reports, _ = harvest_seeds(
        [SEED],
        per_college=None,
        total_limit=None,
        fetch_all=False,
        institution="Example Community College",
    )
    assert {slot.institution_name for slot in slots} == {
        "Example Community College"
    }
    assert reports[0]["institution_name"] == "Example Community College"


def test_each_college_is_capped_at_four_times_its_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_harvester(monkeypatch, found=30)
    slots, _, _ = harvest_seeds(
        [SEED, "https://catalog.other.edu"],
        per_college=None,
        total_limit=None,
        fetch_all=False,
        institution=None,
    )
    assert len(slots) == 2 * 20


def test_a_seed_that_cannot_be_opened_stops_the_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def harvest(seed: str, **options: object) -> dict:
        raise HarvestError(f"cannot open {seed}: host not found")

    monkeypatch.setattr(college_capture, "harvest_with_playwright", harvest)
    with pytest.raises(SystemExit) as exc:
        harvest_seeds(
            [SEED],
            per_college=None,
            total_limit=None,
            fetch_all=False,
            institution=None,
        )
    assert exc.value.code == 1
    assert f"cannot open {SEED}: host not found" in capsys.readouterr().err


@pytest.fixture
def stages(
    pack: Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[..., dict[str, list]]:
    """Fake every stage run_college_capture drives, recording the calls.

    The fake build writes a record file for every queued slot, so the
    trimming afterwards has real files to keep or delete.
    """

    def install(slots: list[Slot], built: int | None = None) -> dict:
        calls: dict[str, list] = {"lookup": [], "assemble": []}

        def harvest(seeds, **options):
            return list(slots), [{"seed_url": seeds[0]}], 2

        def build_pack():
            (pack / "records").mkdir(exist_ok=True)
            for slot in dynamic_slots.load_slots()[:built]:
                (pack / "records" / f"{slot.record_id}.json").write_text(
                    "{}", encoding="utf-8"
                )
            return ["broken: not a template page"]

        monkeypatch.setattr(college_capture, "harvest_seeds", harvest)
        monkeypatch.setattr(college_capture, "freeze_all", dict)
        monkeypatch.setattr(college_capture, "drop_dead_slots", list)
        monkeypatch.setattr(
            college_capture, "attach_templates", lambda slots, folder: slots
        )
        monkeypatch.setattr(cli, "cmd_normalize", lambda args: 0)
        monkeypatch.setattr(build, "build_pack", build_pack)
        monkeypatch.setattr(
            build, "assemble_manifest", lambda: calls["assemble"].append(1)
        )
        monkeypatch.setattr(
            registry, "lookup_pack", lambda: calls["lookup"].append(1)
        )
        monkeypatch.setattr(quality, "cross_check_pack", lambda p: ["quality"])
        monkeypatch.setattr(
            validate, "validate_pack", lambda p, strict_promotion: ["runtime"]
        )
        return calls

    return install


def capture(**options: object) -> dict:
    flags = {
        "per_college": None,
        "total_limit": None,
        "fetch_all": False,
        "institution": None,
        **options,
    }
    return run_college_capture([SEED], **flags)


def test_capture_keeps_the_target_per_college_and_the_total_limit(
    pack: Path, stages: Callable[..., dict]
) -> None:
    slots = [slot_at(f"english/c{n}") for n in range(3)]
    slots += [slot_at(f"math/m{n}", "catalog.other.edu") for n in range(3)]
    calls = stages(slots)
    result = capture(total_limit=3)
    assert result == {
        "records": 3,
        "errors": ["quality", "runtime"],
        "pack": pack.name,
    }
    kept = sorted(path.stem for path in (pack / "records").glob("*.json"))
    assert kept == [
        "example-english-c0-course",
        "example-english-c1-course",
        "other-math-m0-course",
    ]
    payload = json.loads((pack / "slots.json").read_text(encoding="utf-8"))
    assert payload["final"] is True
    assert payload["dropped_extract_errors"] == ["broken: not a template page"]
    report = json.loads(
        (pack / "CAPTURE_REPORT.json").read_text(encoding="utf-8")
    )
    assert report["records"] == 3
    assert report["quality_errors"] == ["quality", "runtime"]
    assert calls == {"lookup": [1], "assemble": [1]}
    assert (pack / "record.schema.json").is_file()


def test_capture_can_skip_the_registry(stages: Callable[..., dict]) -> None:
    calls = stages([slot_at("english/c0")])
    capture(skip_registry=True)
    assert calls["lookup"] == []


def test_capture_with_nothing_discovered_stops(
    stages: Callable[..., dict],
) -> None:
    stages([])
    with pytest.raises(SystemExit, match="no course URLs discovered"):
        capture()


def test_capture_where_every_page_failed_to_transcribe_stops(
    stages: Callable[..., dict],
) -> None:
    stages([slot_at("english/c0")], built=0)
    with pytest.raises(SystemExit, match="every freeze failed transcription"):
        capture()
