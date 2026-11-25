"""The stage-script bootstrap: resolve --pack and set XTRA_* before any
engine module reads them."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import _stage
import cli
import config
import pytest

import lib


def test_the_pack_flag_is_required() -> None:
    parser = argparse.ArgumentParser()
    _stage.add_pack_flag(parser)
    assert parser.parse_args(["--pack", "nj30"]).pack == "nj30"
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_a_relative_pack_is_made_under_the_pack_home_with_defaults(
    lib_dir: Path,
) -> None:
    pack = _stage.configure_pack("nj30")
    assert pack == lib.pack_home() / "nj30"
    assert pack.is_dir()
    assert os.environ["XTRA_PACK"] == str(pack)
    assert os.environ["XTRA_SLOTS"] == "dynamic"
    assert os.environ["XTRA_MODE"] == "college"
    assert os.environ["XTRA_PILE"] == "nj30"
    assert pack == config.PACK
    assert (pack / "record.schema.json").read_bytes() == (
        lib_dir / "record.schema.json"
    ).read_bytes()


def test_settings_already_given_under_either_name_are_kept(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XTRA_SLOTS", "fixed")
    monkeypatch.setenv("GOLDEN_SET_MODE", "legacy")
    monkeypatch.setenv("XTRA_PILE", "nj30")
    _stage.configure_pack(str(tmp_path / "abs"))
    assert os.environ["XTRA_SLOTS"] == "fixed"
    assert "XTRA_MODE" not in os.environ
    assert os.environ["XTRA_PILE"] == "nj30"


def test_a_schema_already_in_the_pack_is_left_alone(tmp_path: Path) -> None:
    target = tmp_path / "abs"
    target.mkdir()
    (target / "record.schema.json").write_text("{}", encoding="utf-8")
    _stage.configure_pack(str(target))
    assert (target / "record.schema.json").read_text(encoding="utf-8") == "{}"


def test_run_hands_the_subcommand_to_the_pack_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def main(argv: list[str]) -> int:
        calls.append(argv)
        return 3

    monkeypatch.setattr(cli, "main", main)
    assert _stage.run("validate", ["--strict-promotion"]) == 3
    assert calls == [["validate", "--strict-promotion"]]
