"""Runtime settings: XTRA_* names with their GOLDEN_SET_* fallbacks, the
pack paths bound from them, and the user agent crawl_robots borrows."""

from __future__ import annotations

import os
from pathlib import Path

import config
import pytest


def test_env_get_prefers_the_xtra_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("XTRA_PACK", "new")
    monkeypatch.setenv("GOLDEN_SET_PACK", "old")
    assert config.env_get("XTRA_PACK") == "new"
    assert capsys.readouterr().err == ""


def test_env_get_falls_back_to_the_golden_set_name_and_warns_once(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GOLDEN_SET_PILE", "old")
    assert config.env_get("XTRA_PILE") == "old"
    assert config.env_get("XTRA_PILE") == "old"
    assert capsys.readouterr().err == (
        "warning: GOLDEN_SET_PILE is deprecated; use XTRA_PILE\n"
    )


def test_a_blank_value_counts_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XTRA_MODE", "   ")
    assert config.env_get("XTRA_MODE", "college") == "college"
    monkeypatch.setenv("GOLDEN_SET_MODE", "legacy")
    assert config.env_get("XTRA_MODE") == "legacy"


def test_a_name_without_a_legacy_alias_just_takes_the_default() -> None:
    assert config.env_get("XTRA_NOT_A_SETTING", "fallback") == "fallback"


def test_env_set_writes_the_process_environment() -> None:
    config.env_set("XTRA_MODE", "college")
    assert os.environ["XTRA_MODE"] == "college"


def test_env_setdefault_keeps_a_value_set_under_either_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOLDEN_SET_PILE", "legacy-pile")
    config.env_setdefault("XTRA_PILE", "new-pile")
    assert "XTRA_PILE" not in os.environ
    monkeypatch.delenv("GOLDEN_SET_PILE")
    config.env_setdefault("XTRA_PILE", "new-pile")
    assert os.environ["XTRA_PILE"] == "new-pile"


def test_without_xtra_pack_every_path_hangs_off_xtra_cli_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("XTRA_PACK")
    config.bind_runtime_paths()
    out = (config.CLI_ROOT / "out").absolute()
    assert out == config.PACK
    assert out / "record.schema.json" == config.SCHEMA_PATH
    assert out / "snapshots" == config.SNAPSHOT_DIR
    assert out / "normalized" == config.NORMALIZED_DIR
    assert out / "records" == config.RECORD_DIR
    assert config.SLOTS_NAME == "dynamic"


def test_a_relative_xtra_pack_is_made_absolute(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XTRA_PACK", "packs/one")
    monkeypatch.setenv("XTRA_SLOTS", "fixed")
    config.bind_runtime_paths()
    assert tmp_path / "packs" / "one" == config.PACK
    assert config.SLOTS_NAME == "fixed"


def test_the_layout_constants_point_at_this_checkout(lib_dir: Path) -> None:
    assert config.LIB_DIR == config.HERE == lib_dir
    assert lib_dir.parent == config.CLI_ROOT
    assert config.REPO_ROOT == config.ROOT == lib_dir.parent.parent


def test_the_browser_user_agent_reads_as_desktop_chrome() -> None:
    agent = config.BROWSER_USER_AGENT
    assert agent.startswith("Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    assert "Chrome/" in agent
    assert config.REGISTRY_USER_AGENT == "xtra-cli/1.0"
