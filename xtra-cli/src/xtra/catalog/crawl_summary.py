"""xtra catalog crawl summary

  xtra catalog crawl summary --url https://catalog.example.edu
      --run-id 2026-11-04T19:30:22Z --failed

What a run has done, one row per URL, then the totals line. Read-only:
safe to run while the crawl is still going.
"""

from __future__ import annotations

import click

from common.keys import catalog_folder_name
from implementations.crawl_status import (
    GROUP_FAILED,
    GROUP_SAVED,
    GROUP_SKIPPED,
    list_run_files,
    read_report,
    read_rows,
    render_csv,
    render_table,
    run_started,
    totals_line,
)
from xtra.catalog.crawl_status import open_run_store, run_options
from xtra.click import storage_connection_options


@click.command(name="summary")
@run_options
@click.option("--saved", "show_saved", is_flag=True, help="Show saved pages.")
@click.option("--failed", "show_failed", is_flag=True, help="Show failed URLs.")
@click.option(
    "--skipped", "show_skipped", is_flag=True, help="Show skipped URLs."
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "csv"]),
    default="table",
    show_default=True,
    help="csv for Excel. The totals line is printed with table only.",
)
@storage_connection_options()
def main(
    url: str,
    run_id: str,
    env_name: str | None,
    target_uri: str | None,
    show_saved: bool,
    show_failed: bool,
    show_skipped: bool,
    output_format: str,
    azure_storage_connection_string: str | None,
) -> None:
    """Show every URL a run has asked for and what came of it.

    One row per URL, read from its .meta.json: saved (and from which run,
    when it was copied), failed, failed-retryable, or skipped-<reason>.
    With no filter, all of them; --saved, --failed and --skipped can be
    combined. URLs found but not asked for yet have no row. Every
    .meta.json is read, so on a large run in Azure this takes a while;
    `xtra catalog crawl status` gives the counts at once.
    """
    store = open_run_store(
        run_id, target_uri, env_name, azure_storage_connection_string
    )
    folder = catalog_folder_name(url)
    files = list_run_files(store, folder, run_id)
    groups = set()
    if show_saved:
        groups.add(GROUP_SAVED)
    if show_failed:
        groups.add(GROUP_FAILED)
    if show_skipped:
        groups.add(GROUP_SKIPPED)
    rows = read_rows(store, files, groups)

    if output_format == "csv":
        click.echo(render_csv(rows), nl=False)
        return
    if rows:
        click.echo(render_table(rows))
    else:
        click.echo("No pages match.")
    click.echo(
        totals_line(
            files,
            read_report(store, folder, run_id),
            started=run_started(store, folder, run_id),
        )
    )


if __name__ == "__main__":
    main()
