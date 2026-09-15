"""Persistent storage for the active environment.

Mirrors ceops `~/.ceops/config.json`. Set `XTRA_CONFIG_DIR` to relocate it,
which CI and containers need since they have no writable home directory.

Secrets are never written here. The config records only the *name* of the
variable that holds the connection string.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from xtra.config.environments import DEFAULT_CONNECTION_STRING_ENV

CONFIG_DIR_ENV = "XTRA_CONFIG_DIR"


class ConfigNotFoundError(Exception):
    """No active environment on disk."""


@dataclass
class StoredConfig:
    env_name: str
    data_uri: str = ""
    connection_string_env: str = DEFAULT_CONNECTION_STRING_ENV


def config_dir() -> Path:
    override = (os.getenv(CONFIG_DIR_ENV) or "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".xtra"


def config_file() -> Path:
    return config_dir() / "config.json"


def has_config() -> bool:
    return config_file().exists()


def load_config() -> StoredConfig:
    """Load the active environment.

    Raises ConfigNotFoundError when nothing is stored or the file is corrupt.
    """
    path = config_file()
    if not path.exists():
        raise ConfigNotFoundError(
            "No active environment configured. "
            "Run 'xtra environment set <env> --data-uri <uri>'."
        )
    try:
        return StoredConfig(**json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, TypeError, KeyError) as exc:
        raise ConfigNotFoundError(f"Corrupt config file: {exc}") from exc


def save_config(config: StoredConfig) -> Path:
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = config_file()
    path.write_text(
        json.dumps(asdict(config), indent=2) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def clear_config() -> None:
    config_file().unlink(missing_ok=True)
