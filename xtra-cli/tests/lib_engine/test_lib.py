"""Pack helpers: URL files, where packs live, the pack check and the
files it writes."""

from __future__ import annotations

import json
import os
from pathlib import Path

import config
import pytest
import quality
import validate
from lib_doubles import course_record

import lib

D11 = (
    "D11: check_pack leaves XTRA_MODE set when only GOLDEN_SET_MODE was: "
    "env_get reads the legacy name, and the finally block writes it back "
    "under the new one"
)


def test_a_url_file_skips_blank_lines_comments_and_trailing_notes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "urls.txt"
    path.write_text(
        "# seeds\n\nhttps://a.example.edu  first catalog\n"
        "  https://b.example.edu\n#https://c.example.edu\n",
        encoding="utf-8",
    )
    assert lib.load_url_file(path) == [
        "https://a.example.edu",
        "https://b.example.edu",
    ]


def test_a_bare_url_file_name_is_also_looked_for_next_to_lib(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    urls = lib.load_url_file(Path("union_fields_urls.txt"))
    assert urls[0] == "https://catalog.tamiu.edu"
    assert len(urls) == 12


def test_packs_live_under_xtra_home_when_it_is_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XTRA_HOME", str(tmp_path / "home"))
    assert lib.pack_home() == tmp_path / "home"


def test_without_xtra_home_packs_live_in_xtra_cli_out(
    monkeypatch: pytest.MonkeyPatch, lib_dir: Path
) -> None:
    monkeypatch.delenv("XTRA_HOME")
    assert lib.pack_home() == (lib_dir.parent / "out").absolute()


@pytest.mark.parametrize(
    ("out", "urls", "name"),
    [
        (None, ["https://catalog.brookdalecc.edu"], "brookdalecc_courses"),
        (
            None,
            ["https://a.example.edu", "https://b.example.edu"],
            "courses_mix",
        ),
        (None, [], "courses_mix"),
        ("my_pack", ["https://a.example.edu"], "my_pack"),
    ],
)
def test_a_new_pack_is_named_after_its_seed_under_the_pack_home(
    out: str | None, urls: list[str], name: str
) -> None:
    assert lib.resolve_pack(out, urls) == lib.pack_home() / name


def test_an_absolute_pack_path_is_used_as_given(tmp_path: Path) -> None:
    assert lib.resolve_pack(str(tmp_path / "abs"), []) == tmp_path / "abs"
    assert lib.resolve_existing_pack(str(tmp_path)) == tmp_path


def test_an_existing_pack_name_resolves_under_the_pack_home() -> None:
    assert lib.resolve_existing_pack("nj30") == lib.pack_home() / "nj30"


def test_a_pack_folder_with_anything_in_it_is_not_overwritten(
    tmp_path: Path,
) -> None:
    target = tmp_path / "out_pack"
    assert lib.refuse_existing_pack(target) is None
    target.mkdir()
    assert lib.refuse_existing_pack(target) is None
    (target / "slots.json").write_text("{}", encoding="utf-8")
    assert lib.refuse_existing_pack(target) == (
        f"refusing to overwrite existing pack {target}. Pick a new --out name."
    )


def test_json_dumps_leaves_the_slot_list_out() -> None:
    text = lib.json_dumps({"records": 1, "slots": [{"record_id": "r"}]})
    assert json.loads(text) == {"records": 1}
    assert text == '{\n  "records": 1\n}'


def skip_inner_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(quality, "cross_check_pack", lambda pack: [])
    monkeypatch.setattr(
        validate, "validate_pack", lambda pack, strict_promotion: []
    )


def write_course(pack: Path, name: str, **row: object) -> None:
    folder = pack / "courses"
    folder.mkdir(exist_ok=True)
    body = {
        "id": name,
        "catalogue_type": "COURSES",
        "source_url": "https://catalog.example.edu/english/engl101",
        "expected": {"course_id": "ENGL101", "course_name": "Composition I"},
    }
    body.update(row)
    (folder / f"{name}.json").write_text(json.dumps(body), encoding="utf-8")


def test_a_missing_pack_directory_is_reported(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    assert lib.check_pack(missing) == [f"missing pack directory {missing}"]


def test_a_pack_without_records_says_capture_extracted_nothing(
    pack: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skip_inner_checks(monkeypatch)
    assert lib.check_pack(pack) == [
        "no records/*.json - capture did not extract any course"
    ]


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ({"catalogue_type": "PROGRAMS"}, "c1: catalogue_type must be COURSES"),
        ({"source_url": "catalog.example.edu/x"}, "c1: missing source_url"),
        (
            {"expected": {"course_id": "ENGL101"}},
            "c1: expected needs course_id and course_name",
        ),
        (
            {
                "expected": {
                    "course_id": "ENGL101",
                    "course_name": "Composition I",
                    "course_credits": 3,
                    "course_credits_min": 1,
                    "course_credits_max": 4,
                }
            },
            "c1: course_credits cannot also have min/max",
        ),
        (
            {
                "expected": {
                    "course_id": "ENGL101",
                    "course_name": "Composition I",
                    "course_credits_max": 4,
                }
            },
            "c1: printed range needs both min and max",
        ),
    ],
)
def test_each_scoring_file_rule_is_reported(
    pack: Path, monkeypatch: pytest.MonkeyPatch, row: dict, message: str
) -> None:
    skip_inner_checks(monkeypatch)
    course_record(pack)
    write_course(pack, "c1", **row)
    assert lib.check_pack(pack) == [message]


def test_scoring_files_and_records_must_pair_up(
    pack: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skip_inner_checks(monkeypatch)
    course_record(pack)
    write_course(pack, "c1")
    write_course(pack, "c2")
    assert lib.check_pack(pack) == ["courses/ has 2 files but records/ has 1"]


def test_the_inner_checks_errors_are_passed_through(
    pack: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course_record(pack)
    monkeypatch.setattr(quality, "cross_check_pack", lambda pack: ["q"])
    monkeypatch.setattr(
        validate, "validate_pack", lambda pack, strict_promotion: ["v"]
    )
    assert lib.check_pack(pack) == ["q", "v"]


@pytest.mark.parametrize("before", [None, "strict"])
def test_check_pack_runs_in_college_mode_and_puts_xtra_mode_back(
    pack: Path, monkeypatch: pytest.MonkeyPatch, before: str | None
) -> None:
    seen: list[str | None] = []

    def inner(checked: Path) -> list[str]:
        seen.append(os.environ.get("XTRA_MODE"))
        return []

    monkeypatch.setattr(lib, "_check_pack_college", inner)
    if before:
        monkeypatch.setenv("XTRA_MODE", before)
    lib.check_pack(pack)
    assert seen == ["college"]
    assert os.environ.get("XTRA_MODE") == before


def test_xtra_mode_is_put_back_even_when_the_check_raises(
    pack: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def inner(checked: Path) -> list[str]:
        raise RuntimeError("check failed")

    monkeypatch.setattr(lib, "_check_pack_college", inner)
    with pytest.raises(RuntimeError, match="check failed"):
        lib.check_pack(pack)
    assert "XTRA_MODE" not in os.environ


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=D11)
def test_check_pack_leaves_xtra_mode_unset_when_only_the_old_name_was_set(
    pack: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(lib, "_check_pack_college", lambda checked: [])
    monkeypatch.setenv("GOLDEN_SET_MODE", "legacy")
    lib.check_pack(pack)
    assert "XTRA_MODE" not in os.environ


def test_the_check_file_says_ok_only_without_errors(pack: Path) -> None:
    course_record(pack)
    path = lib.write_check(pack, [])
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "ok": True,
        "records": 1,
        "errors": [],
    }
    lib.write_check(pack, ["bad"], extra=5)
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "ok": False,
        "records": 5,
        "errors": ["bad"],
    }


def test_the_pack_readme_gives_the_status_and_a_relative_pack_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("XTRA_HOME", str(home))
    target = home / "brookdalecc_courses"
    (target / "records").mkdir(parents=True)
    seeds = ["https://a.example.edu", "https://b.example.edu"]
    text = lib.write_pack_readme(target, seeds=seeds, errors=[]).read_text(
        encoding="utf-8"
    )
    assert "- Check: **READY_FOR_HUMAN_REVIEW** (`CHECK.json`)" in text
    assert "- Pack: `brookdalecc_courses`" in text
    assert "- Seeds: https://a.example.edu, https://b.example.edu" in text
    assert "--pile brookdalecc_courses" in text
    assert str(tmp_path) not in text
    failed = lib.write_pack_readme(target, seeds=[], errors=["x"])
    assert "**FAILED_CHECKS**" in failed.read_text(encoding="utf-8")


def checkout_at(monkeypatch: pytest.MonkeyPatch, root: Path) -> Path:
    """Pretend the repo is checked out at `root`, wherever it really is.

    With xtra-cli copied to /app, the repo root would be /, and every path
    would count as inside the repo.
    """
    monkeypatch.setattr(lib, "ROOT", root)
    monkeypatch.setattr(lib, "CLI_ROOT", root / "xtra-cli")
    return root


def test_a_pack_outside_every_known_root_shows_only_its_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    checkout_at(monkeypatch, tmp_path / "checkout")
    assert lib._display_pack(tmp_path / "elsewhere" / "p") == Path("p")


def test_a_pack_inside_the_repo_shows_its_repo_relative_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = checkout_at(monkeypatch, tmp_path / "checkout")
    pack = root / "xtra-cli" / "out" / "p"
    assert lib._display_pack(pack) == Path("xtra-cli", "out", "p")


def test_configure_points_the_engine_at_a_pack_and_refreshes_its_schema(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, lib_dir: Path
) -> None:
    monkeypatch.setenv("XTRA_MODE", "something-else")
    target = tmp_path / "new_pack"
    target.mkdir()
    (target / "record.schema.json").write_text("{}", encoding="utf-8")
    lib.configure(target)
    assert os.environ["XTRA_PACK"] == str(target)
    assert os.environ["XTRA_SLOTS"] == "dynamic"
    assert os.environ["XTRA_MODE"] == "college"
    assert os.environ["XTRA_PILE"] == "new_pack"
    assert target == config.PACK
    assert (target / "record.schema.json").read_bytes() == (
        lib_dir / "record.schema.json"
    ).read_bytes()


def test_configure_keeps_a_pile_set_under_either_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GOLDEN_SET_PILE", "nj30")
    lib.configure(tmp_path / "p")
    assert "XTRA_PILE" not in os.environ
    assert (tmp_path / "p").is_dir()
