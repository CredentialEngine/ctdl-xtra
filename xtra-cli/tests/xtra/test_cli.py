from __future__ import annotations

from click.testing import CliRunner
import pytest

from xtra.cli import cli
from xtra.version import get_version


def test_cli_returns_zero_for_top_level_help() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "catalog" in result.output
    assert "page" in result.output
    assert "environment" in result.output


def test_top_level_help_keeps_examples_on_their_own_lines() -> None:
    """Click rewraps any example paragraph that is not preceded by \\b."""
    lines = [line.strip() for line in CliRunner().invoke(cli, ["--help"]).output.splitlines()]
    assert "xtra environment set prod --data-uri <storage-uri>" in lines
    assert "xtra catalog crawl --with-playwright --url <catalog-url> --limit 5" in lines


def test_environment_help_lists_verbs() -> None:
    result = CliRunner().invoke(cli, ["environment", "--help"])
    assert result.exit_code == 0
    assert "set" in result.output
    assert "show" in result.output
    assert "list" in result.output


def test_cli_exposes_version() -> None:
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "xtra" in result.output
    assert get_version() in result.output


def test_catalog_help_lists_verbs() -> None:
    result = CliRunner().invoke(cli, ["catalog", "--help"])
    assert result.exit_code == 0
    assert "crawl" in result.output
    assert "extract" in result.output
    assert "transform" in result.output


def test_catalog_crawl_help_lists_strategies() -> None:
    result = CliRunner().invoke(cli, ["catalog", "crawl", "--help"])
    assert result.exit_code == 0
    assert "--with-playwright" in result.output
    assert "--with-ai-agent" in result.output
    assert "--with-third-party" in result.output
    assert "--min-interval" in result.output
    assert "--concurrency" in result.output
    assert "--limit" in result.output
    assert "--target-uri" in result.output
    assert "--env" in result.output
    assert "--pack" not in result.output


@pytest.mark.parametrize(
    "args",
    [
        ["catalog", "crawl"],
        ["catalog", "extract"],
        ["catalog", "transform"],
        ["page", "download"],
    ],
)
def test_every_etl_command_accepts_env(args: list[str]) -> None:
    result = CliRunner().invoke(cli, [*args, "--help"])
    assert result.exit_code == 0
    assert "--env" in result.output


def test_catalog_extract_help_lists_strategies() -> None:
    result = CliRunner().invoke(cli, ["catalog", "extract", "--help"])
    assert result.exit_code == 0
    assert "--with-template" in result.output
    assert "--with-ai-agent" in result.output


def test_catalog_transform_help_lists_strategies() -> None:
    result = CliRunner().invoke(cli, ["catalog", "transform", "--help"])
    assert result.exit_code == 0
    assert "--with-ctdl" in result.output
    assert "--with-ai-agent" in result.output


def test_page_download_help_lists_strategies() -> None:
    result = CliRunner().invoke(cli, ["page", "download", "--help"])
    assert result.exit_code == 0
    assert "--with-playwright" in result.output
    assert "--min-interval" in result.output


def test_configure_logging_accepts_env(monkeypatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    from xtra.cli import configure_logging

    configure_logging()


def test_load_command_rejects_non_click_main() -> None:
    import sys
    import types

    import click

    from xtra.cli import _load_command

    mod = types.ModuleType("xtra._fake_cmd")
    mod.main = lambda: None
    sys.modules["xtra._fake_cmd"] = mod
    try:
        with pytest.raises(click.ClickException, match="does not define main"):
            _load_command("xtra._fake_cmd")
    finally:
        sys.modules.pop("xtra._fake_cmd", None)
