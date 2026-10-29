"""xtra catalog navigation

  xtra catalog navigation --catalog-id catalog-example-edu --run-id 2026-09-17T14:20:01Z

Builds the link tree for a crawl that already ran, from its saved pages.
Nothing is fetched from the website.
"""

from __future__ import annotations

import json

import click

from common.clock import is_iso8601_utc
from common.keys import navigation_key
from common.object_store import open_store
from common.storage_uri import join_storage_uri
from implementations.crawl_navigation import NavigationError, build_navigation
from xtra.click import (
    env_option,
    non_empty_string,
    resolve_connection,
    resolve_uri,
    source_uri_option,
    storage_connection_options,
    target_uri_option,
)


@click.command(name="navigation")
@env_option()
@source_uri_option()
@target_uri_option()
@click.option(
    "--catalog-id",
    required=True,
    callback=non_empty_string,
    help="Catalog folder the crawl wrote, for example catalog-example-edu.",
)
@click.option("--run-id", required=True, help="Crawl run id to read.")
@storage_connection_options()
def main(
    env_name: str | None,
    source_uri: str | None,
    target_uri: str | None,
    catalog_id: str,
    run_id: str,
    azure_storage_connection_string: str | None,
) -> None:
    """Build navigation.json for a crawl that already ran.

    Writes it into the crawl's folder in --target-uri. A tree the crawl
    built itself with --with-navigation is more exact, so it's never replaced.
    """
    if not is_iso8601_utc(run_id):
        raise click.UsageError(
            f"--run-id {run_id!r} is not a UTC timestamp. "
            "Use 2026-09-17T14:20:01Z or 2026-09-17T14-20-01Z."
        )

    source_uri = resolve_uri(source_uri, env_name=env_name, flag="--source-uri")
    target_uri = resolve_uri(target_uri, env_name=env_name, flag="--target-uri")
    azure_storage_connection_string = resolve_connection(
        azure_storage_connection_string, env_name=env_name
    )
    source = open_store(
        source_uri,
        azure_storage_connection_string=azure_storage_connection_string,
    )
    target = open_store(
        target_uri,
        azure_storage_connection_string=azure_storage_connection_string,
    )
    try:
        navigation = build_navigation(source, target, catalog_id, run_id)
    except NavigationError as exc:
        raise click.ClickException(str(exc)) from exc

    summary = {key: value for key, value in navigation.items() if key != "tree"}
    summary["written_to"] = join_storage_uri(
        target_uri, navigation_key(catalog_id, run_id)
    )
    click.echo(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
