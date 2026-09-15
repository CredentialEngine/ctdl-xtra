"""xtra catalog crawl

  xtra catalog crawl --with-playwright --url https://catalog.example.edu --target-uri ./cache --limit 5
"""

from __future__ import annotations

import json
import logging

import click

from common.clock import utc_timestamp
from common.keys import crawl_key, page_html_key, page_meta_key, page_text_key, slots_key
from common.object_store import open_store
from common.polite import PoliteLimiter
from common.storage_uri import join_storage_uri
from implementations.crawl import catalog_id_from_url, harvest_playwright, slot_to_dict
from implementations.download import download_one, fetch_html_playwright
from implementations.strategies import unimplemented_message
from xtra.click import (
    env_option,
    limit_option,
    polite_options,
    require_strategy,
    resolve_connection,
    resolve_uri,
    storage_connection_options,
    strategy_options,
    target_uri_option,
)

logger = logging.getLogger(__name__)


@click.command(name="crawl")
@strategy_options("playwright", "ai-agent", "third-party")
@click.option("--url", required=True, help="Catalog home or course detail URL.")
@env_option()
@target_uri_option()
@click.option("--catalog-id", default=None, help="Override catalog id derived from --url.")
@click.option(
    "--run-id",
    default=None,
    help="ISO8601 UTC run id yyyy-MM-ddTHH:mm:ssZ. Default: now.",
)
@limit_option()
@click.option(
    "--discover-only",
    is_flag=True,
    help="Write slots.json only. Skip course-page downloads.",
)
@click.option("--institution", default=None, help="Override institution_name.")
@click.option("--all", "fetch_all", is_flag=True, help="Keep every discovered course URL.")
@polite_options()
@storage_connection_options()
def main(
    strategy: str | None,
    url: str,
    env_name: str | None,
    target_uri: str | None,
    catalog_id: str | None,
    run_id: str | None,
    limit: int | None,
    discover_only: bool,
    institution: str | None,
    fetch_all: bool,
    concurrency: int,
    min_interval: float,
    backoff_base: float,
    backoff_max: float,
    max_retries: int,
    azure_storage_connection_string: str | None,
) -> None:
    """Discover course URLs for one catalog and optionally download pages.

    Output is written under {catalog-id}/{run-id}/ in --target-uri, or in the
    active environment's container when --target-uri is omitted. There is no
    pack folder and no zip. --limit 5 is the usual test cap.
    """
    strategy = require_strategy(strategy, example="--with-playwright")
    if strategy != "playwright":
        raise click.ClickException(
            unimplemented_message("crawl", strategy, implemented="playwright")
        )

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
    run_id = run_id or utc_timestamp()
    catalog_id = catalog_id_from_url(url, catalog_id)
    store = open_store(
        target_uri,
        azure_storage_connection_string=azure_storage_connection_string,
        concurrency=concurrency,
    )

    report = harvest_playwright(
        url,
        limit=limit,
        fetch_all=fetch_all,
        institution=institution,
        between_pages=limiter.wait_turn,
    )
    slots = [slot_to_dict(slot) for slot in report["slots"]]
    if not slots:
        raise click.ClickException("no course URLs discovered")

    downloaded = 0
    if not discover_only:
        for slot in report["slots"]:
            html, meta, text, stem = download_one(
                slot.requested_url,
                limiter=limiter,
                fetch_fn=fetch_html_playwright,
                max_retries=max_retries,
            )
            store.put_text(
                page_html_key(catalog_id, run_id, stem),
                html,
                "text/html; charset=utf-8",
            )
            store.put_json(page_meta_key(catalog_id, run_id, stem), meta)
            store.put_text(page_text_key(catalog_id, run_id, stem), text)
            downloaded += 1

    crawl_doc = {
        "schema": "xtra-crawl-1",
        "catalog_id": catalog_id,
        "run_id": run_id,
        "seed_url": url,
        "strategy": strategy,
        "limit": limit,
        "concurrency": concurrency,
        "min_interval": min_interval,
        "family": report.get("family"),
        "institution_name": report.get("institution_name"),
        "discovered": report.get("discovered"),
        "kept": len(slots),
        "downloaded": downloaded,
        "discover_only": discover_only,
    }
    store.put_json(crawl_key(catalog_id, run_id), crawl_doc)
    store.put_json(
        slots_key(catalog_id, run_id),
        {"schema": "xtra-slots-1", "catalog_id": catalog_id, "run_id": run_id, "slots": slots},
    )
    run_uri = join_storage_uri(target_uri, catalog_id, run_id)
    click.echo(
        json.dumps(
            {
                **crawl_doc,
                "run_uri": run_uri,
                "location": store.describe_location(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
