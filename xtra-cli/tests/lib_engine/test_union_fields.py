"""The label-union report across catalogs (python lib/union_fields.py).
Captures run as subprocesses; here subprocess.run is faked."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import union_fields
from lib_doubles import course_record

import lib

URL = "https://catalog.example.edu"
D7 = (
    "D7: run_one starts xtra-cli/extraction/run.py, which no longer exists, "
    "so a live union run fails for every catalog"
)


class FakeCompleted:
    def __init__(self, returncode: int = 0, stderr: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = ""


def fake_run(
    monkeypatch: pytest.MonkeyPatch, result: FakeCompleted | None = None
) -> list[tuple]:
    calls: list[tuple] = []

    def run(cmd: list[str], **options: object) -> FakeCompleted:
        calls.append((cmd, options))
        return result or FakeCompleted()

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_a_pack_is_counted_by_label_template_and_family(
    pack: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The pack is shown relative to the repo; keep the real checkout's
    # location out of it.
    monkeypatch.setattr(lib, "ROOT", tmp_path / "checkout")
    monkeypatch.setattr(lib, "CLI_ROOT", tmp_path / "checkout" / "xtra-cli")
    course_record(pack)
    course_record(
        pack,
        record_id="example-math101-course",
        requested_url="https://catalog.example.edu/math/math101",
        source_family="coursedog",
        template_id="coursedog_mccc_course_detail",
        fields=[("course_id", "ENGL101", "ENGL101:")],
    )
    assert union_fields.count_pack(pack) == {
        "pack": "pack",
        "records": 2,
        "label_counts": {"course_id": 2, "course_name": 1, "course_credits": 1},
        "template_counts": {
            "clean_catalog_course_detail": 1,
            "coursedog_mccc_course_detail": 1,
        },
        "family_counts": {"custom_html": 1, "coursedog": 1},
    }


def test_without_records_the_scoring_files_are_counted(tmp_path: Path) -> None:
    scored = tmp_path / "scored"
    for folder, name, body in (
        (
            "courses",
            "a.json",
            {
                "template_id": "t1",
                "expected": {"course_id": "X", "course_name": "Y"},
            },
        ),
        ("credentials", "b.json", {"expected": {"credential_name": "Z"}}),
    ):
        (scored / folder).mkdir(parents=True)
        (scored / folder / name).write_text(json.dumps(body), encoding="utf-8")
    report = union_fields.count_pack(scored)
    assert report["records"] == 2
    assert report["label_counts"] == {
        "course_id": 1,
        "course_name": 1,
        "credential_name": 1,
    }
    assert report["template_counts"] == {"t1": 1, "unknown": 1}
    assert report["family_counts"] == {"unknown": 2}


def test_run_one_captures_a_catalog_and_reports_how_it_went(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stderr = "".join(f"line {n}\n" for n in range(30))
    stderr += "drop unknown template https://catalog.example.edu/x"
    calls = fake_run(monkeypatch, FakeCompleted(returncode=1, stderr=stderr))
    row = union_fields.run_one(URL, limit=3)
    cmd, options = calls[0]
    target = union_fields.resolve_pack(None, [URL])
    assert cmd[0] == sys.executable
    assert cmd[2:] == [
        "--url",
        URL,
        "--limit",
        "3",
        "--skip-registry",
        "--allow-errors",
        "--out",
        str(target),
    ]
    assert options["cwd"] == str(union_fields.CLI_ROOT)
    assert options["check"] is False
    assert row["returncode"] == 1
    assert row["dropped_unknown"] is True
    assert len(row["stderr_tail"].splitlines()) == 20
    assert (row["records"], row["label_counts"]) == (0, {})


def test_run_one_reads_the_pack_the_capture_left_behind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = union_fields.resolve_pack(None, [URL])
    (target / "records").mkdir(parents=True)
    (target / "slots.json").write_text(
        json.dumps({"slots": [{}, {}], "discovery": [{"family": "acalog"}]}),
        encoding="utf-8",
    )
    fake_run(monkeypatch)
    row = union_fields.run_one(URL, limit=5)
    assert row["discovered_slots"] == 2
    assert row["family"] == "acalog"
    assert row["records"] == 0


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=D7)
def test_run_one_starts_a_capture_script_that_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = fake_run(monkeypatch)
    union_fields.run_one(URL, limit=5)
    assert Path(calls[0][0][1]).is_file()


def test_main_without_urls_or_packs_prints_help_and_exits_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert union_fields.main([]) == 2
    assert capsys.readouterr().out.startswith("usage:")


def test_main_combines_packs_and_live_runs_into_one_report(
    pack: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    course_record(pack)
    url_file = tmp_path / "urls.txt"
    url_file.write_text("https://catalog.other.edu\n", encoding="utf-8")
    ran: list[str] = []

    def run_one(url: str, *, limit: int) -> dict:
        ran.append(url)
        return {"url": url, "records": 0, "label_counts": {}}

    monkeypatch.setattr(union_fields, "run_one", run_one)
    out = tmp_path / "union.json"
    argv = ["--from-pack", str(pack), "--url", URL, "--url-file", str(url_file)]
    assert union_fields.main([*argv, "--out", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert ran == [URL, "https://catalog.other.edu"]
    assert len(payload["catalogs"]) == 3
    assert payload["union_label_counts"] == {
        "course_id": 1,
        "course_name": 1,
        "course_credits": 1,
    }
    assert payload["unreadable_or_empty"] == [URL, "https://catalog.other.edu"]
