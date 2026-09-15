from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from xtra.config.settings import (
    ConfigNotFoundError,
    StoredConfig,
    clear_config,
    config_dir,
    config_file,
    has_config,
    load_config,
    save_config,
)

PROD_URI = "azure://https://ceprod.blob.core.windows.net/xtra"


def test_config_dir_follows_the_override(isolated_config_dir: Path) -> None:
    assert config_dir() == isolated_config_dir
    assert config_file() == isolated_config_dir / "config.json"


def test_config_dir_defaults_to_home(monkeypatch) -> None:
    monkeypatch.delenv("XTRA_CONFIG_DIR", raising=False)
    assert config_dir() == Path.home() / ".xtra"


def test_blank_override_falls_back_to_home(monkeypatch) -> None:
    monkeypatch.setenv("XTRA_CONFIG_DIR", "   ")
    assert config_dir() == Path.home() / ".xtra"


def test_save_then_load_round_trips() -> None:
    assert has_config() is False
    path = save_config(StoredConfig(env_name="prod", data_uri=PROD_URI))

    assert has_config() is True
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "env_name": "prod",
        "data_uri": PROD_URI,
        "connection_string_env": "AZURE_STORAGE_CONNECTION_STRING",
    }

    stored = load_config()
    assert stored.env_name == "prod"
    assert stored.data_uri == PROD_URI


def test_saved_config_is_owner_only() -> None:
    path = save_config(StoredConfig(env_name="test"))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_config_never_stores_the_secret() -> None:
    path = save_config(StoredConfig(env_name="prod", data_uri=PROD_URI))
    assert "AccountKey" not in path.read_text(encoding="utf-8")


def test_load_without_config_names_the_fix() -> None:
    with pytest.raises(ConfigNotFoundError, match="xtra environment set"):
        load_config()


def test_corrupt_config_is_reported(isolated_config_dir: Path) -> None:
    config_file().write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigNotFoundError, match="Corrupt"):
        load_config()


def test_config_with_unknown_keys_is_reported() -> None:
    config_file().write_text(json.dumps({"nope": 1}), encoding="utf-8")
    with pytest.raises(ConfigNotFoundError, match="Corrupt"):
        load_config()


def test_clear_config_is_idempotent() -> None:
    save_config(StoredConfig(env_name="dev"))
    clear_config()
    clear_config()
    assert has_config() is False
