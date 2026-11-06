"""xtra catalog crawl status

  xtra catalog crawl status --url https://catalog.example.edu
      --run-id 2026-11-04T19:30:22Z

How far a run has got, in one line. Read-only and quick: it lists the
run's pages without opening them, so it is safe to run while the crawl is
still going.
"""

from __future__ import annotations

import click

from common.clock import is_iso8601_utc
from common.keys import catalog_folder_name
from common.object_store import ObjectStore, open_store
from implementations.crawl_status import (
    list_run_files,
    read_report,
    run_started,
    totals_line,
)
from xtra.click import (
    env_option,
    resolve_connection,
    resolve_uri,
    storage_connection_options,
    target_uri_option,
)


def run_options(command):
    """--url, --run-id and where the run lives, shared with crawl summary."""
    for option in reversed(
        (
            click.option(
                "--url",
                required=True,
                help="Catalog URL the crawl started from.",
            ),
            click.option(
                "--run-id",
                required=True,
                help="The run to show, as crawl.json or the run folder names it.",
            ),
            env_option(),
            target_uri_option(),
        )
    ):
        command = option(command)
    return command


def open_run_store(
    run_id: str,
    target_uri: str | None,
    env_name: str | None,
    azure_storage_connection_string: str | None,
) -> ObjectStore:
    if not is_iso8601_utc(run_id):
        raise click.UsageError(
            f"--run-id {run_id!r} is not a UTC timestamp. "
            "Use 2026-09-17T14:20:01Z or 2026-09-17T14-20-01Z."
        )
    resolved = resolve_uri(target_uri, env_name=env_name, flag="--target-uri")
    return open_store(
        resolved,
        azure_storage_connection_string=resolve_connection(
            azure_storage_connection_string, env_name=env_name
        ),
    )


@click.command(name="status")
@run_options
@storage_connection_options()
def main(
    url: str,
    run_id: str,
    env_name: str | None,
    target_uri: str | None,
    azure_storage_connection_string: str | None,
) -> None:
    """Count what a run has saved, failed and skipped so far.

    One line: the counts from the run's pages/ folder, live, then copied
    and fetched, the run it copied from, its status and what was left in
    the queue, from crawl.json, which is written when the run ends. For one
    row per URL, use `xtra catalog crawl summary`.
    """
    store = open_run_store(
        run_id, target_uri, env_name, azure_storage_connection_string
    )
    folder = catalog_folder_name(url)
    click.echo(
        totals_line(
            list_run_files(store, folder, run_id),
            read_report(store, folder, run_id),
            started=run_started(store, folder, run_id),
        )
    )


if __name__ == "__main__":
    main()
