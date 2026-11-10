"""xtra catalog crawl navigation

  xtra catalog crawl navigation --url https://catalog.example.edu
      --run-id 2026-11-04T19:30:22Z

Writes navigation.json into the run folder: every URL the run found, Built from the pages the run saved.
"""

from __future__ import annotations

import json

import click

from common.keys import catalog_folder_name
from implementations.crawl_navigation import NavigationError, build_navigation
from xtra.catalog.crawl_status import open_run_store, run_options
from xtra.click import storage_connection_options


@click.command(name="navigation")
@run_options
@click.option(
    "--force",
    is_flag=True,
    help="Replace the run's navigation.json when it already has one.",
)
@storage_connection_options()
def main(
    url: str,
    run_id: str,
    env_name: str | None,
    target_uri: str | None,
    force: bool,
    azure_storage_connection_string: str | None,
) -> None:
    store = open_run_store(
        run_id, target_uri, env_name, azure_storage_connection_string
    )
    try:
        key, doc = build_navigation(
            store, catalog_folder_name(url), run_id, force=force
        )
    except NavigationError as exc:
        raise click.ClickException(str(exc)) from exc
    summary = {
        "navigation": key,
        "totals": doc["totals"],
        "notes": doc["notes"],
    }
    click.echo(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
