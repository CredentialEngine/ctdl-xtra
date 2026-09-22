"""Shared Click options. Mirrors ceops/src/ceops/click.py for storage and limits."""

from __future__ import annotations

import click

from xtra.config.context import resolve_connection_string, resolve_data_uri
from xtra.config.environments import ENV_NAMES
from xtra.config.settings import ConfigNotFoundError

POSITIVE_INT = click.IntRange(min=1)

DEFAULT_MIN_INTERVAL_SECONDS = 180.0
DEFAULT_BACKOFF_BASE_SECONDS = 180.0
DEFAULT_BACKOFF_MAX_SECONDS = 3600.0


def non_empty_string(ctx, param, value):
    if value is None:
        return value
    normalized = value.strip()
    if not normalized:
        raise click.BadParameter("Value cannot be empty")
    return normalized


def strategy_options(*names: str):
    """Mutually exclusive --with-<strategy> flags sharing dest `strategy`."""

    def decorator(func):
        for name in reversed(names):
            func = click.option(
                f"--with-{name}",
                "strategy",
                flag_value=name,
                help=f"Run this command with the {name} strategy.",
            )(func)
        return func

    return decorator


def require_strategy(strategy: str | None, *, example: str) -> str:
    if strategy:
        return strategy
    raise click.UsageError(
        f"Specify a strategy, for example {example}."
    )


def storage_connection_options():
    def decorator(func):
        return click.option(
            "--azure-storage-connection-string",
            envvar="AZURE_STORAGE_CONNECTION_STRING",
            required=False,
            help=(
                "Azure Blob Storage connection string. "
                "UseDevelopmentStorage=true for the Azurite emulator."
            ),
        )(func)

    return decorator


def env_option():
    return click.option(
        "--env",
        "env_name",
        type=click.Choice(ENV_NAMES, case_sensitive=False),
        default=None,
        envvar="XTRA_ENV",
        help=(
            "Environment to read and write, overriding the one saved by "
            "'xtra environment set'. Ignored when a URI is given explicitly."
        ),
    )


def target_uri_option():
    return click.option(
        "--target-uri",
        required=False,
        callback=non_empty_string,
        help=(
            "Where to write this run. Not a pack folder and not a zip. "
            "Defaults to the active environment's data URI. Examples:\n"
            "  azure://https://account.blob.core.windows.net/xtra\n"
            "  azure://http://127.0.0.1:10000/devstoreaccount1/xtra\n"
            "  file:///tmp/xtra\n"
            "  ./xtra-cache"
        ),
    )


def source_uri_option():
    return click.option(
        "--source-uri",
        required=False,
        callback=non_empty_string,
        help=(
            "Where to read the previous stage. Same URI schemes and same "
            "environment default as --target-uri."
        ),
    )


def resolve_uri(explicit: str | None, *, env_name: str | None, flag: str) -> str:
    """Storage URI for `flag`, falling back to the selected environment."""
    try:
        return resolve_data_uri(explicit, env_name=env_name)
    except ConfigNotFoundError as exc:
        raise click.UsageError(f"{flag} is required. {exc}") from exc


def resolve_connection(
    explicit: str | None,
    *,
    env_name: str | None,
) -> str | None:
    """Azure secret for this run, or None when the target needs no credential."""
    return resolve_connection_string(explicit, env_name=env_name)


def polite_options():
    def decorator(func):
        options = [
            click.option(
                "--concurrency",
                type=POSITIVE_INT,
                default=1,
                show_default=True,
                help=(
                    "Max in-flight page fetches. Keep at 1 so catalog sites "
                    "are not overloaded."
                ),
            ),
            click.option(
                "--min-interval",
                type=click.FloatRange(min=0),
                default=DEFAULT_MIN_INTERVAL_SECONDS,
                show_default=True,
                help=(
                    "Minimum seconds between page fetches. Default is 3 minutes "
                    "so long-running cache refreshes stay polite."
                ),
            ),
            click.option(
                "--backoff-base",
                type=click.FloatRange(min=0),
                default=DEFAULT_BACKOFF_BASE_SECONDS,
                show_default=True,
                help="First retry wait in seconds. Doubles after each failure.",
            ),
            click.option(
                "--backoff-max",
                type=click.FloatRange(min=0),
                default=DEFAULT_BACKOFF_MAX_SECONDS,
                show_default=True,
                help="Cap for exponential backoff in seconds.",
            ),
            click.option(
                "--max-retries",
                type=POSITIVE_INT,
                default=5,
                show_default=True,
            ),
        ]
        for option in reversed(options):
            func = option(func)
        return func

    return decorator


def limit_option():
    return click.option(
        "--limit",
        type=POSITIVE_INT,
        required=False,
        help="Cap discovered or downloaded pages. Use 5 while testing.",
    )
