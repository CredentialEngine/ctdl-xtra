"""xtra score extraction match

  xtra score extraction match --exactly --catalog-id ID --run-id TS
  xtra score extraction match --partially --catalog-id ID --run-id TS

Matches the records of one extraction run against a baseline, without
extracting again. --exactly counts the values identical to the baseline.
--partially sets those aside and measures how close the rest come. Neither
averages: the report is counts plus the outliers, worst first.
"""

from __future__ import annotations

import json
import logging

import click

from common.keys import extraction_match_report_key
from common.object_store import ObjectStore, open_store
from implementations.score_extraction_match import (
    MODE_EXACT,
    MODE_PARTIAL,
    ExtractionMatchError,
    format_table,
    match_extraction_run,
)
from xtra.click import (
    baseline_uri_option,
    env_option,
    resolve_baseline,
    resolve_connection,
    resolve_uri,
    source_uri_option,
    storage_connection_options,
)

logger = logging.getLogger(__name__)


def match_and_report(
    store: ObjectStore,
    baseline: ObjectStore,
    *,
    catalog_id: str,
    run_id: str,
    mode: str,
) -> dict:
    """Match the run's records, write the report beside them, show the table.

    The table goes to stderr so stdout stays one JSON document. Raises
    ClickException when nothing could be matched.
    """
    try:
        report = match_extraction_run(store, baseline, catalog_id, run_id, mode)
    except ExtractionMatchError as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - storage SDKs raise their own types
        raise click.ClickException(f"matching failed: {exc}") from exc

    store.put_json(
        extraction_match_report_key(catalog_id, run_id, mode), report
    )
    click.echo(format_table(report), err=True)
    return report


def match_summary(report: dict) -> dict:
    """The few numbers worth printing: counts, and the exact rate if any."""
    summary = {
        "mode": report["mode"],
        "fields_total": report["fields_total"],
        "outcomes": report["outcomes"],
        "pages_scored": report["pages_scored"],
        "pages_skipped": report["pages_skipped"],
        "pages_out_of_scope": report["pages_out_of_scope"],
        "outliers": len(report["outliers"]),
    }
    if "exact_match_rate" in report:
        summary["exact_match_rate"] = report["exact_match_rate"]
    if "excluded_exact" in report:
        summary["excluded_exact"] = report["excluded_exact"]
    return summary


@click.command(name="match")
@click.option(
    "--exactly",
    is_flag=True,
    help="Count the extracted values identical to the baseline.",
)
@click.option(
    "--partially",
    is_flag=True,
    help=(
        "Set the exact matches aside and measure how close the other "
        "values come to the baseline."
    ),
)
@env_option()
@source_uri_option()
@baseline_uri_option()
@click.option("--catalog-id", required=True)
@click.option(
    "--run-id",
    required=True,
    help="Extraction run id, the one the baseline files are filed under.",
)
@storage_connection_options()
def main(
    exactly: bool,
    partially: bool,
    env_name: str | None,
    source_uri: str | None,
    baseline_uri: str | None,
    catalog_id: str,
    run_id: str,
    azure_storage_connection_string: str | None,
) -> None:
    """Match an extraction run against a baseline.

    Reads the records and extract-report.json of the run from --source-uri,
    and the baseline files of the same catalog and run from --baseline-uri.
    The report is written beside the records.
    """
    if exactly == partially:
        raise click.UsageError(
            "Specify exactly one of --exactly or --partially."
        )
    mode = MODE_EXACT if exactly else MODE_PARTIAL

    source_uri = resolve_uri(source_uri, env_name=env_name, flag="--source-uri")
    baseline_uri = resolve_baseline(baseline_uri, env_name=env_name)
    azure_storage_connection_string = resolve_connection(
        azure_storage_connection_string, env_name=env_name
    )
    store = open_store(
        source_uri,
        azure_storage_connection_string=azure_storage_connection_string,
    )
    baseline = open_store(
        baseline_uri,
        azure_storage_connection_string=azure_storage_connection_string,
    )

    report = match_and_report(
        store, baseline, catalog_id=catalog_id, run_id=run_id, mode=mode
    )
    click.echo(
        json.dumps(
            {
                "catalog_id": catalog_id,
                "run_id": run_id,
                **match_summary(report),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
