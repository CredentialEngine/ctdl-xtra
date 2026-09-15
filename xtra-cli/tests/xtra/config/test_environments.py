from __future__ import annotations

from xtra.config.environments import (
    AZURITE_CONNECTION_STRING,
    DEFAULT_CONNECTION_STRING_ENV,
    ENV_NAMES,
    ENVIRONMENTS,
)


def test_env_names_cover_dev_through_prod() -> None:
    assert ENV_NAMES == ("dev", "test", "sandbox", "prod")


def test_every_environment_declares_the_same_keys() -> None:
    expected = {"data_uri", "connection_string_env", "fallback_connection_string"}
    for name, values in ENVIRONMENTS.items():
        assert set(values) == expected, name
        assert values["connection_string_env"] == DEFAULT_CONNECTION_STRING_ENV


def test_dev_defaults_to_azurite() -> None:
    dev = ENVIRONMENTS["dev"]
    assert dev["data_uri"].startswith("azure://http://127.0.0.1:10000/")
    assert dev["fallback_connection_string"] == AZURITE_CONNECTION_STRING


def test_shared_environments_ship_without_a_guessed_account() -> None:
    for name in ("test", "sandbox", "prod"):
        assert ENVIRONMENTS[name]["data_uri"] == ""
        assert ENVIRONMENTS[name]["fallback_connection_string"] == ""
