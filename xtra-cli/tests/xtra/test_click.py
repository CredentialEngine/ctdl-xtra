from __future__ import annotations

import click
import pytest
from click.testing import CliRunner

from xtra.click import (
    DEFAULT_MAX_INTERVAL_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MIN_INTERVAL_SECONDS,
    crawl_pacing_options,
    env_option,
    limit_option,
    non_empty_string,
    require_strategy,
    resolve_connection,
    resolve_uri,
    source_uri_option,
    strategy_options,
    target_uri_option,
)
from xtra.config.settings import StoredConfig, save_config

PROD_URI = "azure://https://ceprod.blob.core.windows.net/xtra"


def test_non_empty_string_strips_and_rejects_blank() -> None:
    ctx = click.Context(click.Command("t"))
    param = click.Option(["--x"])
    assert non_empty_string(ctx, param, None) is None
    assert non_empty_string(ctx, param, "  azure://x  ") == "azure://x"
    with pytest.raises(click.BadParameter):
        non_empty_string(ctx, param, "   ")


def test_require_strategy_errors_without_flag() -> None:
    with pytest.raises(click.UsageError, match="--with-playwright"):
        require_strategy(None, example="--with-playwright")
    assert require_strategy("playwright", example="--with-playwright") == (
        "playwright"
    )


def test_strategy_options_are_mutually_exclusive() -> None:
    @click.command()
    @strategy_options("playwright", "ai-agent")
    def cmd(strategy):
        click.echo(strategy or "missing")

    runner = CliRunner()
    assert runner.invoke(cmd, ["--with-playwright"]).output.strip() == (
        "playwright"
    )
    assert runner.invoke(cmd, ["--with-ai-agent"]).output.strip() == "ai-agent"
    last_wins = runner.invoke(cmd, ["--with-playwright", "--with-ai-agent"])
    assert last_wins.exit_code == 0
    assert last_wins.output.strip() == "ai-agent"


def test_crawl_pacing_and_limit_defaults() -> None:
    """A rare, one-time crawl is slow by default so nobody has to redo it."""

    @click.command()
    @crawl_pacing_options()
    @limit_option()
    def cmd(
        concurrency_limit,
        min_interval_in_seconds,
        max_interval_in_seconds,
        max_retries,
        limit,
    ):
        click.echo(
            f"{concurrency_limit},{min_interval_in_seconds},"
            f"{max_interval_in_seconds},{max_retries},{limit}"
        )

    result = CliRunner().invoke(cmd, [])
    assert result.exit_code == 0
    assert result.output.strip() == (
        f"1,{DEFAULT_MIN_INTERVAL_SECONDS},{DEFAULT_MAX_INTERVAL_SECONDS},"
        f"{DEFAULT_MAX_RETRIES},None"
    )
    assert DEFAULT_MIN_INTERVAL_SECONDS == 180.0
    assert DEFAULT_MAX_INTERVAL_SECONDS == 3600.0


def test_uri_options_are_optional_and_stripped() -> None:
    @click.command()
    @env_option()
    @source_uri_option()
    @target_uri_option()
    def cmd(env_name, source_uri, target_uri):
        click.echo(f"{env_name},{source_uri},{target_uri}")

    runner = CliRunner()
    assert runner.invoke(cmd, []).output.strip() == "None,None,None"
    filled = runner.invoke(
        cmd, ["--env", "PROD", "--source-uri", " ./a ", "--target-uri", "./b"]
    )
    assert filled.output.strip() == "prod,./a,./b"


def test_env_option_rejects_unknown_environment() -> None:
    @click.command()
    @env_option()
    def cmd(env_name):
        click.echo(env_name)

    result = CliRunner().invoke(cmd, ["--env", "staging"])
    assert result.exit_code != 0


def test_resolve_uri_prefers_the_flag_then_the_environment() -> None:
    save_config(StoredConfig(env_name="prod", data_uri=PROD_URI))
    assert (
        resolve_uri("./cache", env_name=None, flag="--target-uri") == "./cache"
    )
    assert resolve_uri(None, env_name=None, flag="--target-uri") == PROD_URI
    assert resolve_uri(None, env_name="dev", flag="--target-uri").startswith(
        "azure://http://127.0.0.1"
    )


def test_resolve_uri_reports_the_missing_flag_as_a_usage_error() -> None:
    with pytest.raises(click.UsageError, match="--target-uri is required"):
        resolve_uri(None, env_name=None, flag="--target-uri")

    with pytest.raises(click.UsageError, match="--source-uri is required"):
        resolve_uri(None, env_name="sandbox", flag="--source-uri")


def test_resolve_connection_prefers_the_flag(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "from-env")
    save_config(StoredConfig(env_name="prod", data_uri=PROD_URI))
    assert resolve_connection("from-flag", env_name=None) == "from-flag"
    assert resolve_connection(None, env_name=None) == "from-env"


def test_resolve_connection_is_none_when_nothing_is_configured(
    monkeypatch,
) -> None:
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    assert resolve_connection(None, env_name=None) is None
