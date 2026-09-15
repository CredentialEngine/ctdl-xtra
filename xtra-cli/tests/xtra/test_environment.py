from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from xtra.environment import environment_group

PROD_URI = "azure://https://ceprod.blob.core.windows.net/xtra"


def run(*args: str):
    return CliRunner().invoke(environment_group, list(args))


def test_set_writes_the_active_environment(isolated_config_dir: Path) -> None:
    result = run("set", "prod", "--data-uri", PROD_URI)

    assert result.exit_code == 0, result.output
    assert "Active environment set to prod." in result.output
    assert PROD_URI in result.output

    stored = json.loads(
        (isolated_config_dir / "config.json").read_text(encoding="utf-8")
    )
    assert stored == {
        "env_name": "prod",
        "data_uri": PROD_URI,
        "connection_string_env": "AZURE_STORAGE_CONNECTION_STRING",
    }


def test_set_accepts_a_custom_secret_variable(isolated_config_dir: Path) -> None:
    result = run(
        "set",
        "sandbox",
        "--data-uri",
        PROD_URI,
        "--connection-string-env",
        "CE_SANDBOX_STORAGE",
    )

    assert result.exit_code == 0, result.output
    assert "Secret from: CE_SANDBOX_STORAGE" in result.output
    stored = json.loads(
        (isolated_config_dir / "config.json").read_text(encoding="utf-8")
    )
    assert stored["connection_string_env"] == "CE_SANDBOX_STORAGE"


def test_set_dev_needs_no_data_uri() -> None:
    result = run("set", "dev")
    assert result.exit_code == 0, result.output
    assert "127.0.0.1:10000" in result.output


def test_set_rejects_an_unknown_environment() -> None:
    result = run("set", "staging")
    assert result.exit_code != 0
    assert "staging" in result.output


def test_set_is_case_insensitive() -> None:
    assert run("set", "PROD", "--data-uri", PROD_URI).exit_code == 0
    assert "Environment: prod" in run("show").output


def test_show_without_a_configured_environment() -> None:
    result = run("show")
    assert result.exit_code != 0
    assert "xtra environment set" in result.output


def test_show_reports_whether_the_secret_is_set(monkeypatch) -> None:
    run("set", "prod", "--data-uri", PROD_URI)

    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    assert "Secret set:  no" in run("show").output

    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "secret")
    assert "Secret set:  yes" in run("show").output


def test_show_never_prints_the_secret(monkeypatch) -> None:
    run("set", "prod", "--data-uri", PROD_URI)
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "super-secret-key")
    assert "super-secret-key" not in run("show").output


def test_show_honours_the_env_override() -> None:
    run("set", "prod", "--data-uri", PROD_URI)
    result = run("show", "--env", "dev")
    assert result.exit_code == 0, result.output
    assert "Environment: dev" in result.output


def test_show_reads_xtra_env(monkeypatch) -> None:
    run("set", "prod", "--data-uri", PROD_URI)
    monkeypatch.setenv("XTRA_ENV", "dev")
    assert "Environment: dev" in run("show").output


def test_show_reports_an_environment_without_a_container() -> None:
    run("set", "prod", "--data-uri", PROD_URI)
    assert "Data URI:    (not set)" in run("show", "--env", "sandbox").output


def test_list_marks_the_active_environment() -> None:
    plain = run("list")
    assert plain.exit_code == 0
    assert "(active)" not in plain.output

    run("set", "test", "--data-uri", PROD_URI)
    marked = run("list").output
    assert "test (active)" in marked
    assert "  prod\n" in marked
