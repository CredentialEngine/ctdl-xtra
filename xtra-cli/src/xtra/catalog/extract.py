"""xtra catalog extract

  xtra catalog extract --with-template --catalog-id ID --run-id TS

Works from the list discovery produced, so it no longer guesses which saved
pages are courses.
"""

from __future__ import annotations

import json
import logging

import click

from common.keys import (
    discovery_key,
    extract_report_key,
    page_html_key,
    page_meta_key,
    record_key,
)
from common.object_store import open_store
from implementations.discover import (
    LABELS_FILE,
    latest_discovery_run_id,
    sample_file_name,
)
from implementations.discover_rules import LABEL_COURSE
from implementations.extract import extract_record, slot_from_labels_entry
from implementations.extract_dom import (
    ENTITY_COURSE,
    entity_type_for,
    entity_types_for,
)
from implementations.strategies import unimplemented_message
from xtra.click import (
    env_option,
    require_strategy,
    resolve_connection,
    resolve_uri,
    source_uri_option,
    storage_connection_options,
    strategy_options,
    target_uri_option,
)

logger = logging.getLogger(__name__)

REPORT_SCHEMA = "xtra-extract-report-1"
REASON_MULTI_COURSE = "multi_course_page"
REASON_MULTI_CREDENTIAL = "multi_credential_page"
REASON_NO_COURSE_BLOCK = "no_course_block"
REASON_NOTHING_READ = "nothing_read_from_the_page"
MARKER_MULTI_CREDENTIAL = "multi_credential_page"


@click.command(name="extract")
@strategy_options("template", "ai-agent")
@env_option()
@source_uri_option()
@target_uri_option()
@click.option("--catalog-id", required=True)
@click.option(
    "--run-id", required=True, help="Crawl run id from catalog crawl."
)
@click.option(
    "--discovery-run-id",
    default=None,
    help="Which discovery run to read. Default: the newest one.",
)
@click.option(
    "--only-golden-sample",
    is_flag=True,
    help="Extract only the pages in the golden sample for review.",
)
@storage_connection_options()
def main(
    strategy: str | None,
    env_name: str | None,
    source_uri: str | None,
    target_uri: str | None,
    catalog_id: str,
    run_id: str,
    discovery_run_id: str | None,
    only_golden_sample: bool,
    azure_storage_connection_string: str | None,
) -> None:
    """Transcribe printed fields from saved HTML. Candidate status only.

    Reads labels.json from the newest discovery run and processes every
    page it gave an entity to: a course page with exactly one course
    block, a credential or learning-opportunity page that is about one of
    them, and a competency list. Anything skipped is written to
    extract-report.json, beside records/ and never inside it, because
    transform reads every JSON file under records/.
    """
    strategy = require_strategy(strategy, example="--with-template")
    if strategy != "template":
        raise click.ClickException(
            unimplemented_message("extract", strategy, implemented="template")
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

    discovery_run_id = discovery_run_id or latest_discovery_run_id(
        source, catalog_id, run_id
    )
    if not discovery_run_id:
        raise click.ClickException(
            f"no discovery run for {catalog_id} {run_id}. "
            "Run xtra catalog discover first."
        )

    labels = source.get_json(
        discovery_key(catalog_id, run_id, discovery_run_id, LABELS_FILE)
    )
    entries = [
        entry
        for entry in labels.get("pages") or []
        if entity_type_for(entry.get("labels") or [])
    ]
    if only_golden_sample:
        sample = source.get_json(
            discovery_key(
                catalog_id,
                run_id,
                discovery_run_id,
                sample_file_name(LABEL_COURSE),
            )
        )
        wanted = {page["stem"] for page in sample.get("pages") or []}
        entries = [entry for entry in entries if entry["stem"] in wanted]

    written: list[str] = []
    skipped: list[dict[str, str]] = []
    for entry in entries:
        stem = entry["stem"]
        refusal = _too_many_entities(entry)
        if refusal is not None:
            skipped.append(
                {"stem": stem, "url": entry.get("url", ""), **refusal}
            )
            continue

        html = source.get_text(page_html_key(catalog_id, run_id, stem))
        retrieved_at = _retrieved_at(source, catalog_id, run_id, stem)
        entity_types = entity_types_for(entry.get("labels") or [])
        for index, entity_type in enumerate(entity_types):
            # The page's own id belongs to what it is mainly about. A
            # second entity on the same page - the competency list a
            # credential page prints - gets an id of its own, because it
            # is published as its own entity and a record holds one.
            record_id = stem if index == 0 else f"{stem}--{entity_type.lower()}"
            slot = slot_from_labels_entry(
                entry,
                retrieved_at=retrieved_at,
                entity_type=entity_type,
                record_id=record_id,
            )
            try:
                record = extract_record(
                    slot, html, retrieved_at=retrieved_at, stem=stem
                )
            except Exception as exc:  # noqa: BLE001 - lib raises its own type
                skipped.append(
                    {
                        "stem": stem,
                        "url": entry.get("url", ""),
                        "entity_type": entity_type,
                        "reason": REASON_NOTHING_READ,
                        "detail": str(exc).splitlines()[0],
                    }
                )
                continue
            target.put_json(
                record_key(catalog_id, run_id, record["record_id"]), record
            )
            written.append(record["record_id"])

    report = {
        "schema": REPORT_SCHEMA,
        "catalog_folder": catalog_id,
        "run_id": run_id,
        "discovery_run_id": discovery_run_id,
        "only_golden_sample": only_golden_sample,
        "pages_considered": len(entries),
        "records_written": len(written),
        "skipped_by_reason": _counted(skipped),
        "skipped": skipped,
    }
    target.put_json(extract_report_key(catalog_id, run_id), report)

    click.echo(
        json.dumps(
            {
                "strategy": strategy,
                "catalog_id": catalog_id,
                "run_id": run_id,
                "discovery_run_id": discovery_run_id,
                "only_golden_sample": only_golden_sample,
                "records": written,
                "skipped_by_reason": report["skipped_by_reason"],
            },
            indent=2,
        )
    )


def _too_many_entities(entry: dict) -> dict[str, str] | None:
    """Why this page cannot become one record, or None.

    One page, one record. A page holding several courses would make one
    record out of twenty of them, and a department page holding several
    credentials would do the same one entity up. Discovery has already
    said so, in course_block_count and in the markers, so this only has
    to read what it said.
    """
    entity_type = entity_type_for(entry.get("labels") or [])
    markers = entry.get("markers") or []
    if entity_type == ENTITY_COURSE:
        blocks = entry.get("course_block_count") or 0
        if blocks != 1:
            return {
                "reason": (
                    REASON_MULTI_COURSE
                    if blocks > 1
                    else REASON_NO_COURSE_BLOCK
                ),
                "detail": f"{blocks} course block(s)",
            }
    elif MARKER_MULTI_CREDENTIAL in markers:
        return {
            "reason": REASON_MULTI_CREDENTIAL,
            "detail": "the page prints the requirements of several credentials",
        }
    return None


def _retrieved_at(
    source: object, catalog_id: str, run_id: str, stem: str
) -> str | None:
    """When the crawl captured this page, from its sidecar."""
    try:
        meta = source.get_json(page_meta_key(catalog_id, run_id, stem))
    except (FileNotFoundError, ValueError):
        return None
    return meta.get("retrieved_at")


def _counted(skipped: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in skipped:
        counts[item["reason"]] = counts.get(item["reason"], 0) + 1
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    main()
