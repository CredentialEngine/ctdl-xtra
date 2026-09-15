"""xtra catalog transform

  xtra catalog transform --with-ctdl --source-uri URI --target-uri URI --catalog-id ID --run-id TS
"""

from __future__ import annotations

import json

import click

from common.keys import expected_key, jsonld_key, record_key, run_prefix
from common.object_store import open_store
from implementations.transform import to_expected, to_jsonld
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


@click.command(name="transform")
@strategy_options("ctdl", "ai-agent")
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
    """Map extracted labels to CTDL JSON-LD. Does not invent CTIDs or publish."""
    strategy = require_strategy(strategy, example="--with-ctdl")
    if strategy != "ctdl":
        raise click.ClickException(
            unimplemented_message("transform", strategy, implemented="ctdl")
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
    prefix = f"{run_prefix(catalog_id, run_id)}/records/"
    written = []
    for key in source.list_keys(under=f"{run_prefix(catalog_id, run_id)}/records"):
        if not key.endswith(".json"):
            continue
        record = source.get_json(key)
        record_id = record.get("record_id") or record.get("id")
        node = to_jsonld(record)
        expected = to_expected(record)
        record["ctdl_expected"] = record.get("ctdl_expected") or {}
        target.put_json(record_key(catalog_id, run_id, record_id), record)
        target.put_json(jsonld_key(catalog_id, run_id, record_id), node)
        target.put_json(expected_key(catalog_id, run_id, record_id), expected)
        written.append(record_id)

    click.echo(
        json.dumps(
            {
                "strategy": strategy,
                "catalog_id": catalog_id,
                "run_id": run_id,
                "records": written,
                "scanned_prefix": prefix,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
