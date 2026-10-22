"""xtra catalog score

  xtra catalog score --extraction --catalog-id ID --run-id TS

Scores the records of one run against the verified golden sets, without
extracting again. xtra catalog extract --with-scoring runs the same scoring
right after it writes the records.
"""

from __future__ import annotations

import json
import logging

import click

from common.keys import extraction_score_report_key
from common.object_store import ObjectStore, open_store
from implementations.extraction_score import (
    ExtractionScoreError,
    format_table,
    score_extraction_run,
)
from xtra.click import (
    env_option,
    golden_uri_option,
    resolve_connection,
    resolve_golden,
    resolve_uri,
    source_uri_option,
    storage_connection_options,
)

logger = logging.getLogger(__name__)


def score_and_report(
    store: ObjectStore,
    golden: ObjectStore,
    *,
    catalog_id: str,
    run_id: str,
) -> dict:
    """Score the run's records, write the report beside them, show the table.

    The table goes to stderr so stdout stays one JSON document. Raises
    ClickException when nothing could be scored.
    """
    try:
        report = score_extraction_run(store, golden, catalog_id, run_id)
    except ExtractionScoreError as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - storage SDKs raise their own types
        raise click.ClickException(f"scoring failed: {exc}") from exc

    store.put_json(extraction_score_report_key(catalog_id, run_id), report)
    click.echo(format_table(report), err=True)
    return report


def score_summary(report: dict) -> dict:
    """The few numbers worth printing beside the stage summary."""
    return {
        "overall": report["overall"],
        "pages_scored": report["pages_scored"],
        "pages_skipped": report["pages_skipped"],
        "pages_out_of_scope": report["pages_out_of_scope"],
    }


@click.command(name="score")
@click.option(
    "--extraction",
    "stage",
    flag_value="extraction",
    help="Score the extracted records against the golden sets.",
)
@env_option()
@source_uri_option()
@golden_uri_option()
@click.option("--catalog-id", required=True)
@click.option(
    "--run-id",
    required=True,
    help="Crawl run id, the same one the golden sets are filed under.",
)
@storage_connection_options()
def main(
    stage: str | None,
    env_name: str | None,
    source_uri: str | None,
    golden_uri: str | None,
    catalog_id: str,
    run_id: str,
    azure_storage_connection_string: str | None,
) -> None:
    """Score a stage's output against the verified golden sets.

    Reads the records and extract-report.json of the run from --source-uri,
    and the golden sets of the same catalog and run from --golden-uri. The
    report is written beside the records.
    """
    if stage != "extraction":
        raise click.UsageError("Specify a stage, for example --extraction.")

    source_uri = resolve_uri(source_uri, env_name=env_name, flag="--source-uri")
    golden_uri = resolve_golden(golden_uri, env_name=env_name)
    azure_storage_connection_string = resolve_connection(
        azure_storage_connection_string, env_name=env_name
    )
    store = open_store(
        source_uri,
        azure_storage_connection_string=azure_storage_connection_string,
    )
    golden = open_store(
        golden_uri,
        azure_storage_connection_string=azure_storage_connection_string,
    )

    report = score_and_report(
        store, golden, catalog_id=catalog_id, run_id=run_id
    )
    click.echo(
        json.dumps(
            {
                "stage": stage,
                "catalog_id": catalog_id,
                "run_id": run_id,
                **score_summary(report),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
