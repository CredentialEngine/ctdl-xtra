from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from xtra.environment import environment_group

UNIT_TEST_URI = "azure://http://127.0.0.1:10000/devstoreaccount1/xtra"
PORTAL_AS_AZURE_URI = "azure://https://unit-test.blob.core.windows.net/xtra"


def run(*args: str):
    return CliRunner().invoke(environment_group, list(args))


def test_set_writes_the_active_environment(isolated_config_dir: Path) -> None:
    result = run("set", "prod", "--data-uri", UNIT_TEST_URI)

    assert result.exit_code == 0, result.output
    assert "Active environment set to prod." in result.output
    assert UNIT_TEST_URI in result.output

    stored = json.loads(
        (isolated_config_dir / "config.json").read_text(encoding="utf-8")
    )
    assert stored == {
        "env_name": "prod",
        "data_uri": UNIT_TEST_URI,
        "baseline_uri": "",
        "connection_string_env": "AZURE_STORAGE_CONNECTION_STRING",
    }


def test_set_accepts_a_custom_secret_variable(
    isolated_config_dir: Path,
) -> None:
    result = run(
        "set",
        "sandbox",
        "--data-uri",
        UNIT_TEST_URI,
        "--connection-string-env",
        "CE_SANDBOX_STORAGE",
    )

    assert result.exit_code == 0, result.output
    assert "Secret from: CE_SANDBOX_STORAGE" in result.output
    stored = json.loads(
        (isolated_config_dir / "config.json").read_text(encoding="utf-8")
    )
    assert stored["connection_string_env"] == "CE_SANDBOX_STORAGE"


def test_set_saves_a_portal_container_url_as_azure(
    isolated_config_dir: Path,
) -> None:
    result = run(
        "set",
        "prod",
        "--data-uri",
        "https://unit-test.blob.core.windows.net/xtra",
    )

    assert result.exit_code == 0, result.output
    assert f"Data URI:    {PORTAL_AS_AZURE_URI}" in result.output
    stored = json.loads(
        (isolated_config_dir / "config.json").read_text(encoding="utf-8")
    )
    assert stored["data_uri"] == PORTAL_AS_AZURE_URI


def test_setting_the_active_environment_again_keeps_its_settings() -> None:
    run(
        "set",
        "test",
        "--data-uri",
        UNIT_TEST_URI,
        "--connection-string-env",
        "CE_TEST_STORAGE",
    )

    result = run("set", "test")

    assert result.exit_code == 0, result.output
    assert f"Data URI:    {UNIT_TEST_URI}" in result.output
    assert "Secret from: CE_TEST_STORAGE" in result.output


def test_switching_environments_does_not_carry_settings_over() -> None:
    run(
        "set",
        "test",
        "--data-uri",
        UNIT_TEST_URI,
        "--connection-string-env",
        "CE_TEST_STORAGE",
    )

    result = run("set", "prod")

    assert result.exit_code == 0, result.output
    assert "Data URI:    (not set)" in result.output
    assert "Secret from: AZURE_STORAGE_CONNECTION_STRING" in result.output


def test_set_dev_needs_no_data_uri() -> None:
    result = run("set", "dev")
    assert result.exit_code == 0, result.output
    assert "127.0.0.1:10000" in result.output


def test_set_rejects_an_unknown_environment() -> None:
    result = run("set", "staging")
    assert result.exit_code != 0
    assert "staging" in result.output


def test_set_is_case_insensitive() -> None:
    assert run("set", "PROD", "--data-uri", UNIT_TEST_URI).exit_code == 0
    assert "Environment: prod" in run("show").output


def test_show_without_a_configured_environment() -> None:
    result = run("show")
    assert result.exit_code != 0
    assert "xtra environment set" in result.output


def test_show_reports_whether_the_secret_is_set(monkeypatch) -> None:
    run("set", "prod", "--data-uri", UNIT_TEST_URI)

    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    assert "Secret set:  no" in run("show").output

    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "secret")
    assert "Secret set:  yes" in run("show").output


def test_show_never_prints_the_secret(monkeypatch) -> None:
    run("set", "prod", "--data-uri", UNIT_TEST_URI)
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "super-secret-key")
    assert "super-secret-key" not in run("show").output


def test_show_honours_the_env_override() -> None:
    run("set", "prod", "--data-uri", UNIT_TEST_URI)
    result = run("show", "--env", "dev")
    assert result.exit_code == 0, result.output
    assert "Environment: dev" in result.output


def test_show_reads_xtra_env(monkeypatch) -> None:
    run("set", "prod", "--data-uri", UNIT_TEST_URI)
    monkeypatch.setenv("XTRA_ENV", "dev")
    assert "Environment: dev" in run("show").output


def test_show_reports_an_environment_without_a_container() -> None:
    run("set", "prod", "--data-uri", UNIT_TEST_URI)
    assert "Data URI:    (not set)" in run("show", "--env", "sandbox").output


def test_list_marks_the_active_environment() -> None:
    plain = run("list")
    assert plain.exit_code == 0
    assert "(active)" not in plain.output

    run("set", "test", "--data-uri", UNIT_TEST_URI)
    marked = run("list").output
    assert "test (active)" in marked
    assert "  prod\n" in marked


BASELINE_URI = "azure://http://127.0.0.1:10000/devstoreaccount1/xtra-baseline"


def test_set_saves_and_shows_the_baseline_uri(
    isolated_config_dir: Path,
) -> None:
    result = run(
        "set",
        "prod",
        "--data-uri",
        UNIT_TEST_URI,
        "--baseline-uri",
        BASELINE_URI,
    )

    assert result.exit_code == 0, result.output
    assert f"Baseline URI: {BASELINE_URI}" in result.output
    stored = json.loads(
        (isolated_config_dir / "config.json").read_text(encoding="utf-8")
    )
    assert stored["baseline_uri"] == BASELINE_URI
    assert f"Baseline URI: {BASELINE_URI}" in run("show").output


def test_set_keeps_the_saved_baseline_uri_when_omitted(
    isolated_config_dir: Path,
) -> None:
    run("set", "prod", "--baseline-uri", BASELINE_URI)

    run("set", "prod", "--data-uri", UNIT_TEST_URI)

    stored = json.loads(
        (isolated_config_dir / "config.json").read_text(encoding="utf-8")
    )
    assert stored["baseline_uri"] == BASELINE_URI


def test_a_config_saved_before_baseline_uri_existed_still_loads(
    isolated_config_dir: Path,
) -> None:
    (isolated_config_dir / "config.json").write_text(
        json.dumps({"env_name": "prod", "data_uri": UNIT_TEST_URI}),
        encoding="utf-8",
    )

    result = run("show")

    assert result.exit_code == 0, result.output
    assert "Baseline URI: (not set)" in result.output
