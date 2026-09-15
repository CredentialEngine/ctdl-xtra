"""Resolve which environment a command runs against.

Precedence for every run, highest first:

1. an explicit `--target-uri` / `--source-uri` on the command
2. `--env <name>` (or `XTRA_ENV`)
3. the active environment saved by `xtra environment set`
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from xtra.config.environments import (
    DEFAULT_CONNECTION_STRING_ENV,
    ENV_NAMES,
    ENVIRONMENTS,
)
from xtra.config.settings import ConfigNotFoundError, load_config


@dataclass(frozen=True)
class EnvironmentConfig:
    """Storage target for one environment."""

    name: str
    data_uri: str = ""
    connection_string_env: str = DEFAULT_CONNECTION_STRING_ENV
    fallback_connection_string: str = ""

    @property
    def is_azure(self) -> bool:
        return self.data_uri.lower().startswith("azure://")

    def connection_string(self) -> str:
        """Secret for this environment, read from its variable at call time."""
        return (
            os.getenv(self.connection_string_env) or ""
        ).strip() or self.fallback_connection_string


def build_environment(
    env_name: str,
    data_uri: str = "",
    connection_string_env: str = "",
) -> EnvironmentConfig:
    """Build the named environment, applying any stored overrides."""
    key = env_name.lower()

    if key not in ENVIRONMENTS:
        raise ValueError(
            f"Unknown environment '{env_name}'. "
            f"Valid environments: {', '.join(ENV_NAMES)}"
        )

    values = ENVIRONMENTS[key]

    return EnvironmentConfig(
        name=key,
        data_uri=data_uri or values["data_uri"],
        connection_string_env=(
            connection_string_env or values["connection_string_env"]
        ),
        fallback_connection_string=values["fallback_connection_string"],
    )


def get_current_environment() -> EnvironmentConfig:
    """Return the active environment. Raises ConfigNotFoundError if unset."""
    config = load_config()

    return build_environment(
        env_name=config.env_name,
        data_uri=config.data_uri,
        connection_string_env=config.connection_string_env,
    )


def environment_for(env_name: str | None) -> EnvironmentConfig:
    """Resolve `--env <name>`, or the active environment when name is empty."""
    if not env_name:
        return get_current_environment()

    key = env_name.lower()
    try:
        stored = load_config()
    except ConfigNotFoundError:
        return build_environment(key)

    if stored.env_name.lower() != key:
        return build_environment(key)

    return build_environment(
        env_name=key,
        data_uri=stored.data_uri,
        connection_string_env=stored.connection_string_env,
    )


def resolve_data_uri(explicit: str | None, *, env_name: str | None = None) -> str:
    """Storage URI for this run, from the flag or the environment."""
    if explicit:
        return explicit

    environment = environment_for(env_name)

    if not environment.data_uri:
        raise ConfigNotFoundError(
            f"Environment '{environment.name}' has no data URI. "
            f"Run 'xtra environment set {environment.name} "
            f"--data-uri azure://https://<account>.blob.core.windows.net/<container>'."
        )

    return environment.data_uri


def resolve_connection_string(
    explicit: str | None,
    *,
    env_name: str | None = None,
) -> str | None:
    """Azure secret for this run. None when the target needs no credential."""
    if explicit:
        return explicit

    try:
        environment = environment_for(env_name)
    except ConfigNotFoundError:
        return None

    return environment.connection_string() or None
