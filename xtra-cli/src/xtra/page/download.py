"""xtra page download

  xtra page download --with-playwright --source-uri URI --target-uri URI --catalog-id ID --run-id TS
"""

from __future__ import annotations

import json

import click

from common.keys import page_html_key, page_meta_key, page_text_key, slots_key
from common.object_store import open_store
from common.polite import PoliteLimiter
from implementations.download import download_one, fetch_html_playwright
from implementations.extract import slot_from_dict
from implementations.strategies import unimplemented_message
from xtra.click import (
    env_option,
    limit_option,
    polite_options,
    require_strategy,
    resolve_connection,
    resolve_uri,
    source_uri_option,
    storage_connection_options,
    strategy_options,
    target_uri_option,
)


@click.command(name="download")
@strategy_options("playwright", "ai-agent", "third-party")
@env_option()
@source_uri_option()
@target_uri_option()
@click.option("--catalog-id", required=True)
@click.option("--run-id", required=True, help="ISO8601 UTC run id from catalog crawl.")
@limit_option()
@polite_options()
@storage_connection_options()
def main(
    strategy: str | None,
    env_name: str | None,
    source_uri: str | None,
    target_uri: str | None,
    catalog_id: str,
    run_id: str,
    limit: int | None,
    concurrency: int,
    min_interval: float,
    backoff_base: float,
    backoff_max: float,
    max_retries: int,
    azure_storage_connection_string: str | None,
) -> None:
    """Download course pages listed in slots.json, one at a time by default."""
    strategy = require_strategy(strategy, example="--with-playwright")
    if strategy != "playwright":
        raise click.ClickException(
            unimplemented_message("download", strategy, implemented="playwright")
        )

    source_uri = resolve_uri(source_uri, env_name=env_name, flag="--source-uri")
    target_uri = resolve_uri(target_uri, env_name=env_name, flag="--target-uri")
    azure_storage_connection_string = resolve_connection(
        azure_storage_connection_string, env_name=env_name
    )

    limiter = PoliteLimiter(
        concurrency=concurrency,
        min_interval=min_interval,
        backoff_base=backoff_base,
        backoff_max=backoff_max,
    )
    source = open_store(
        source_uri,
        azure_storage_connection_string=azure_storage_connection_string,
        concurrency=concurrency,
    )
    target = open_store(
        target_uri,
        azure_storage_connection_string=azure_storage_connection_string,
        concurrency=concurrency,
    )
    payload = source.get_json(slots_key(catalog_id, run_id))
    slots = payload.get("slots") or []
    if limit is not None:
        slots = slots[:limit]

    downloaded = []
    for raw in slots:
        slot = slot_from_dict(raw)
        html, meta, text, stem = download_one(
            slot.requested_url,
            limiter=limiter,
            fetch_fn=fetch_html_playwright,
            max_retries=max_retries,
        )
        target.put_text(
            page_html_key(catalog_id, run_id, stem),
            html,
            "text/html; charset=utf-8",
        )
        target.put_json(page_meta_key(catalog_id, run_id, stem), meta)
        target.put_text(page_text_key(catalog_id, run_id, stem), text)
        downloaded.append(stem)

    click.echo(
        json.dumps(
            {
                "strategy": strategy,
                "catalog_id": catalog_id,
                "run_id": run_id,
                "downloaded": downloaded,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
