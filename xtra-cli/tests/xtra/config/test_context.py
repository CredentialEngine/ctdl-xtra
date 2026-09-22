from __future__ import annotations

import pytest

from xtra.config.context import (
    EnvironmentConfig,
    build_environment,
    environment_for,
    get_current_environment,
    resolve_connection_string,
    resolve_data_uri,
)
from xtra.config.environments import AZURITE_CONNECTION_STRING
from xtra.config.settings import ConfigNotFoundError, StoredConfig, save_config

PROD_URI = "azure://https://ceprod.blob.core.windows.net/xtra"
SANDBOX_URI = "azure://https://cesandbox.blob.core.windows.net/xtra"


def test_build_environment_uses_builtin_defaults() -> None:
    dev = build_environment("dev")
    assert dev.name == "dev"
    assert dev.data_uri.startswith("azure://http://127.0.0.1:10000/")
    assert dev.is_azure is True


def test_build_environment_lowercases_and_applies_overrides() -> None:
    prod = build_environment("PROD", data_uri=PROD_URI, connection_string_env="CE_PROD")
    assert prod.name == "prod"
    assert prod.data_uri == PROD_URI
    assert prod.connection_string_env == "CE_PROD"


def test_build_environment_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="dev, test, sandbox, prod"):
        build_environment("staging")


def test_local_data_uri_is_not_azure() -> None:
    assert build_environment("test", data_uri="./cache").is_azure is False


def test_connection_string_reads_the_named_variable(monkeypatch) -> None:
    environment = EnvironmentConfig(
        name="prod",
        data_uri=PROD_URI,
        connection_string_env="CE_PROD_STORAGE",
    )
    monkeypatch.setenv("CE_PROD_STORAGE", "  secret  ")
    assert environment.connection_string() == "secret"

    monkeypatch.setenv("CE_PROD_STORAGE", "")
    assert environment.connection_string() == ""


def test_dev_falls_back_to_azurite(monkeypatch) -> None:
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    assert build_environment("dev").connection_string() == AZURITE_CONNECTION_STRING


def test_variable_wins_over_the_azurite_fallback(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "real")
    assert build_environment("dev").connection_string() == "real"


def test_get_current_environment_reads_stored_overrides() -> None:
    save_config(StoredConfig(env_name="prod", data_uri=PROD_URI))
    assert get_current_environment().data_uri == PROD_URI


def test_get_current_environment_without_config() -> None:
    with pytest.raises(ConfigNotFoundError):
        get_current_environment()


def test_environment_for_named_env_uses_stored_overrides() -> None:
    save_config(StoredConfig(env_name="prod", data_uri=PROD_URI))
    assert environment_for("prod").data_uri == PROD_URI
    assert environment_for("PROD").data_uri == PROD_URI


def test_environment_for_other_env_ignores_stored_overrides() -> None:
    save_config(StoredConfig(env_name="prod", data_uri=PROD_URI))
    assert environment_for("sandbox").data_uri == ""
    assert environment_for("dev").data_uri.startswith("azure://http://127.0.0.1")


def test_environment_for_named_env_without_any_config() -> None:
    assert environment_for("dev").name == "dev"


def test_resolve_data_uri_prefers_the_explicit_flag() -> None:
    save_config(StoredConfig(env_name="prod", data_uri=PROD_URI))
    assert resolve_data_uri("./cache", env_name="prod") == "./cache"


def test_resolve_data_uri_falls_back_to_named_then_active_env() -> None:
    save_config(StoredConfig(env_name="prod", data_uri=PROD_URI))
    assert resolve_data_uri(None, env_name="prod") == PROD_URI
    assert resolve_data_uri(None) == PROD_URI
    assert resolve_data_uri(None, env_name="dev").startswith("azure://http://")


def test_resolve_data_uri_without_active_env() -> None:
    with pytest.raises(ConfigNotFoundError, match="xtra environment set"):
        resolve_data_uri(None)


def test_resolve_data_uri_when_env_has_no_container() -> None:
    with pytest.raises(ConfigNotFoundError, match="environment set sandbox"):
        resolve_data_uri(None, env_name="sandbox")


def test_resolve_connection_string_prefers_the_explicit_flag(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "from-env")
    save_config(StoredConfig(env_name="prod", data_uri=PROD_URI))
    assert resolve_connection_string("from-flag") == "from-flag"


def test_resolve_connection_string_reads_the_environments_variable(monkeypatch) -> None:
    save_config(
        StoredConfig(
            env_name="sandbox",
            data_uri=SANDBOX_URI,
            connection_string_env="CE_SANDBOX_STORAGE",
        )
    )
    monkeypatch.setenv("CE_SANDBOX_STORAGE", "sandbox-secret")
    assert resolve_connection_string(None) == "sandbox-secret"
    assert resolve_connection_string(None, env_name="sandbox") == "sandbox-secret"


def test_resolve_connection_string_is_none_without_config(monkeypatch) -> None:
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    assert resolve_connection_string(None) is None


def test_resolve_connection_string_is_none_when_unset(monkeypatch) -> None:
    save_config(StoredConfig(env_name="prod", data_uri=PROD_URI))
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    assert resolve_connection_string(None) is None
