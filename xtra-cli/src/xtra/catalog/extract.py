"""xtra catalog extract

  xtra catalog extract --with-template --source-uri URI --target-uri URI --catalog-id ID --run-id TS
"""

from __future__ import annotations

import json
import logging

import click

from common.keys import page_html_key, record_key, slots_key
from common.object_store import open_store
from implementations.extract import extract_record, slot_from_dict
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


@click.command(name="extract")
@strategy_options("template", "ai-agent")
@env_option()
@source_uri_option()
@target_uri_option()
@click.option("--catalog-id", required=True)
@click.option("--run-id", required=True, help="ISO8601 UTC run id from catalog crawl.")
@storage_connection_options()
def main(
    strategy: str | None,
    env_name: str | None,
    source_uri: str | None,
    target_uri: str | None,
    catalog_id: str,
    run_id: str,
    azure_storage_connection_string: str | None,
) -> None:
    """Transcribe printed course fields from frozen HTML. Candidate status only."""
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
    payload = source.get_json(slots_key(catalog_id, run_id))
    slots = payload.get("slots") or []
    written = []
    for raw in slots:
        slot = slot_from_dict(raw)
        html = source.get_text(page_html_key(catalog_id, run_id, slot.stem))
        record = extract_record(slot, html, retrieved_at=raw.get("retrieved_at"))
        target.put_json(record_key(catalog_id, run_id, slot.record_id), record)
        written.append(slot.record_id)

    click.echo(
        json.dumps(
            {
                "strategy": strategy,
                "catalog_id": catalog_id,
                "run_id": run_id,
                "records": written,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
