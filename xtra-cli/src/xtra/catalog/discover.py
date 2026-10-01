"""xtra catalog discover

  xtra catalog discover --catalog-id catalog-example-edu --run-id 2026-09-17T14:20:01Z

Reads every page a crawl saved and says what is in it. No network, no
sampling while profiling, and nothing is fetched or refetched.
"""

from __future__ import annotations

import json
import logging

import click

from common.clock import is_iso8601_utc, run_id_for_path, utc_timestamp
from common.object_store import open_store
from implementations.discover import (
    DiscoverSettings,
    NoPagesError,
    UnknownStemError,
    run_discovery,
)
from implementations.discover_rules import (
    DEFAULT_SAMPLE_LABEL,
    DEFAULT_SAMPLE_SIZE,
)
from xtra.click import (
    POSITIVE_INT,
    env_option,
    non_empty_string,
    non_empty_strings,
    resolve_connection,
    resolve_uri,
    source_uri_option,
    storage_connection_options,
    target_uri_option,
)
from xtra.version import get_version

logger = logging.getLogger(__name__)


@click.command(name="discover")
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
@click.option(
    "--stem",
    "stems",
    multiple=True,
    callback=non_empty_strings,
    help=(
        "Read only this saved page, by the stem the crawl wrote it under. "
        "Repeatable. Default: every page of the run, which is the only "
        "way the shares and the special patterns mean anything."
    ),
)
@click.option(
    "--sample-label",
    default=DEFAULT_SAMPLE_LABEL,
    show_default=True,
    callback=non_empty_string,
    help="Which label the golden sample is drawn from.",
)
@click.option(
    "--sample-size",
    type=POSITIVE_INT,
    default=DEFAULT_SAMPLE_SIZE,
    show_default=True,
    help=(
        "How many pages the golden sample should reach. Coverage of every "
        "special case comes first and may need more than this."
    ),
)
@storage_connection_options()
def main(
    env_name: str | None,
    source_uri: str | None,
    target_uri: str | None,
    catalog_id: str,
    run_id: str,
    stems: tuple[str, ...],
    sample_label: str,
    sample_size: int,
    azure_storage_connection_string: str | None,
) -> None:
    """Profile every saved page, group the shapes, and pick a golden sample.

    Writes to {catalog-id}/{run-id}/discovery/{discovery-run-id}/. Each run
    gets its own folder, so an earlier one is never overwritten and two runs
    can be compared after a rule changes.

    With --stem it reads only the pages named, which answers why one page
    is labelled the way it is without rereading the crawl. The reports are
    written the same way and say they cover a subset, because every share
    and every rare marker in them is then counted over those pages alone.
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

    settings = DiscoverSettings(
        catalog_folder=catalog_id,
        run_id=run_id,
        discovery_run_id=run_id_for_path(utc_timestamp()),
        source_uri=source_uri,
        sample_label=sample_label,
        sample_size=sample_size,
        stems=tuple(stems),
    )
    try:
        outcome = run_discovery(
            settings, source=source, target=target, version=get_version()
        )
    except NoPagesError as exc:
        raise click.ClickException(
            f"{exc}. Run xtra catalog crawl for this run id first."
        ) from exc
    except UnknownStemError as exc:
        raise click.ClickException(
            f"{exc}. A stem is the name the crawl saved the page under, "
            "without the .html; it is the `stem` field of the page's "
            ".meta.json, and `html_path` there says where the page is."
        ) from exc
    except FileExistsError as exc:
        raise click.ClickException(
            f"discovery run {settings.discovery_run_id} already exists at {exc}. "
            "Wait a second and run again; a discovery run is never overwritten."
        ) from exc

    click.echo(outcome.table)
    click.echo("")
    click.echo(json.dumps(outcome.summary, indent=2))
    if outcome.exit_code:
        click.echo(outcome.reason, err=True)
        raise SystemExit(outcome.exit_code)


if __name__ == "__main__":
    main()
