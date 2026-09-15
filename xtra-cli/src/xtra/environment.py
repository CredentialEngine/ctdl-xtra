"""xtra environment set | show | list

  xtra environment set prod --data-uri azure://https://ACCOUNT.blob.core.windows.net/xtra
  xtra environment show
  xtra environment list
"""

from __future__ import annotations

import click

from xtra.config.context import build_environment, environment_for
from xtra.config.environments import ENV_NAMES
from xtra.config.settings import (
    ConfigNotFoundError,
    StoredConfig,
    load_config,
    save_config,
)

_ENV_CHOICE = click.Choice(ENV_NAMES, case_sensitive=False)


@click.group("environment")
def environment_group() -> None:
    """Manage the active xTRA environment."""


@environment_group.command("set")
@click.argument("env_name", type=_ENV_CHOICE)
@click.option(
    "--data-uri",
    default="",
    help=(
        "Storage container for this environment, used when a command omits "
        "--target-uri. Example: "
        "azure://https://ACCOUNT.blob.core.windows.net/xtra"
    ),
)
@click.option(
    "--connection-string-env",
    default="",
    help=(
        "Name of the variable holding this environment's Azure connection "
        "string. The secret itself is never saved to disk."
    ),
)
def environment_set(
    env_name: str,
    data_uri: str,
    connection_string_env: str,
) -> None:
    """Set the active environment (dev, test, sandbox, prod)."""
    environment = build_environment(
        env_name=env_name,
        data_uri=data_uri,
        connection_string_env=connection_string_env,
    )

    path = save_config(
        StoredConfig(
            env_name=environment.name,
            data_uri=environment.data_uri,
            connection_string_env=environment.connection_string_env,
        )
    )

    click.echo(f"Active environment set to {environment.name}.")
    click.echo(f"Data URI:    {environment.data_uri or '(not set)'}")
    click.echo(f"Secret from: {environment.connection_string_env}")
    click.echo(f"Config:      {path}")


@environment_group.command("show")
@click.option(
    "--env",
    "env_name",
    type=_ENV_CHOICE,
    default=None,
    envvar="XTRA_ENV",
    help="Show this environment instead of the active one.",
)
def environment_show(env_name: str | None) -> None:
    """Show the environment a command would use right now."""
    try:
        environment = environment_for(env_name)
    except ConfigNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Environment: {environment.name}")
    click.echo(f"Data URI:    {environment.data_uri or '(not set)'}")
    click.echo(f"Secret from: {environment.connection_string_env}")
    click.echo(
        "Secret set:  "
        + ("yes" if environment.connection_string() else "no")
    )


@environment_group.command("list")
def environment_list() -> None:
    """List available environments."""
    try:
        active = load_config().env_name.lower()
    except ConfigNotFoundError:
        active = ""

    for name in ENV_NAMES:
        marker = " (active)" if name == active else ""
        click.echo(f"  {name}{marker}")
