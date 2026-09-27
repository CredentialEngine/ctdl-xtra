"""xtra catalog crawl

  xtra catalog crawl --with-playwright --url https://catalog.example.edu --target-uri ./cache --limit 5

Download and save. The crawl does not classify pages, name an institution,
or normalize anything; discovery and extraction read what it saved.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import click

from common.clock import is_iso8601_utc, utc_timestamp
from common.keys import catalog_folder_name
from common.object_store import open_store
from implementations.crawl import (
    CrawlSettings,
    StrategyMismatchError,
    run_crawl,
)
from implementations.crawl_fetchers import (
    DEFAULT_FIRECRAWL_API_URL,
    StrategyNotImplementedError,
    StrategyOptionError,
    fetcher_factory_for,
)
from implementations.crawl_strategy import strategy_facts
from xtra.click import (
    crawl_pacing_options,
    env_option,
    limit_option,
    non_empty_string,
    require_strategy,
    resolve_connection,
    resolve_uri,
    storage_connection_options,
    strategy_options,
    target_uri_option,
)

logger = logging.getLogger(__name__)


def read_seed_urls(path: Path | None) -> tuple[str, ...]:
    """One URL per line. Blank lines and # comments are ignored."""
    if path is None:
        return ()
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return tuple(
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    )


def compile_rules(patterns: tuple[str, ...], flag: str) -> tuple[str, ...]:
    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise click.UsageError(
                f"{flag} {pattern!r} is not a regex: {exc}"
            ) from exc
    return patterns


def check_scope_prefix(url: str, scope_prefix: str | None) -> None:
    if not scope_prefix:
        return
    from urllib.parse import urlsplit

    prefix_host = (urlsplit(scope_prefix).hostname or "").lower()
    seed_host = (urlsplit(url).hostname or "").lower()
    if prefix_host and prefix_host != seed_host:
        raise click.UsageError(
            f"--scope-prefix is on {prefix_host} but --url is on {seed_host}. "
            "A crawl stays on one host; --scope-prefix only narrows the path."
        )


@click.command(name="crawl")
@strategy_options(
    "playwright", "crawl4ai", "firecrawl", "ai-agent", "third-party"
)
@click.option("--url", required=True, help="Catalog URL the crawl starts from.")
@env_option()
@target_uri_option()
@click.option(
    "--run-id",
    default=None,
    help=(
        "UTC run id, yyyy-MM-ddTHH:mm:ssZ or yyyy-MM-ddTHH-mm-ssZ. "
        "Default: now. Reuse one to resume that run."
    ),
)
@limit_option()
@crawl_pacing_options()
@click.option(
    "--scope-prefix",
    default=None,
    callback=non_empty_string,
    help=(
        "Keep only URLs whose path starts with this URL's path. "
        "Default: the directory of --url."
    ),
)
@click.option(
    "--include-regex",
    multiple=True,
    help=(
        "Keep a followed URL only when it matches. Repeatable. Example for a "
        "host that keeps several catalog years: --include-regex catoid=13"
    ),
)
@click.option(
    "--exclude-regex",
    multiple=True,
    help="Drop a followed URL when it matches. Repeatable.",
)
@click.option(
    "--seed-urls-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Extra start URLs, one per line, for pages no link reaches.",
)
@click.option(
    "--firecrawl-api-key",
    envvar="FIRECRAWL_API_KEY",
    required=False,
    help="API key for --with-firecrawl. Never logged and never stored.",
)
@click.option(
    "--firecrawl-api-url",
    default=DEFAULT_FIRECRAWL_API_URL,
    show_default=True,
    help="Firecrawl endpoint, for a self-hosted instance.",
)
@storage_connection_options()
def main(
    strategy: str | None,
    url: str,
    env_name: str | None,
    target_uri: str | None,
    run_id: str | None,
    limit: int | None,
    concurrency_limit: int,
    min_interval_in_seconds: float,
    max_interval_in_seconds: float,
    max_retries: int,
    scope_prefix: str | None,
    include_regex: tuple[str, ...],
    exclude_regex: tuple[str, ...],
    seed_urls_file: Path | None,
    firecrawl_api_key: str | None,
    firecrawl_api_url: str,
    azure_storage_connection_string: str | None,
) -> None:
    """Download every page of one catalog and save it.

    Output goes under {catalog-folder}/{run-id}/ in --target-uri, where the
    catalog folder is --url with hyphens for everything that is not a letter
    or a digit. Rerun with the same --url and --run-id to resume: pages
    already saved are read back from storage instead of fetched again.
    """
    strategy = require_strategy(strategy, example="--with-playwright")
    try:
        fetcher_factory = fetcher_factory_for(
            strategy,
            firecrawl_api_key=firecrawl_api_key,
            firecrawl_api_url=firecrawl_api_url,
        )
    except StrategyNotImplementedError as exc:
        raise click.ClickException(str(exc)) from exc
    except StrategyOptionError as exc:
        raise click.UsageError(str(exc)) from exc

    run_id = run_id or utc_timestamp()
    if not is_iso8601_utc(run_id):
        raise click.UsageError(
            f"--run-id {run_id!r} is not a UTC timestamp. "
            "Use 2026-09-17T14:20:01Z or 2026-09-17T14-20-01Z."
        )
    check_scope_prefix(url, scope_prefix)
    include_regex = compile_rules(include_regex, "--include-regex")
    exclude_regex = compile_rules(exclude_regex, "--exclude-regex")

    target_uri = resolve_uri(target_uri, env_name=env_name, flag="--target-uri")
    azure_storage_connection_string = resolve_connection(
        azure_storage_connection_string, env_name=env_name
    )

    try:
        settings = CrawlSettings(
            seed_url=url,
            catalog_folder=catalog_folder_name(url),
            run_id=run_id,
            target_uri=target_uri,
            limit=limit,
            concurrency_limit=concurrency_limit,
            min_interval_in_seconds=min_interval_in_seconds,
            max_interval_in_seconds=max_interval_in_seconds,
            max_retries=max_retries,
            scope_prefix=scope_prefix,
            include_regex=include_regex,
            exclude_regex=exclude_regex,
            seed_urls=read_seed_urls(seed_urls_file),
            strategy=strategy,
        )
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc

    store = open_store(
        target_uri,
        azure_storage_connection_string=azure_storage_connection_string,
        concurrency=concurrency_limit,
    )
    try:
        outcome = run_crawl(
            settings,
            store=store,
            fetcher_factory=fetcher_factory,
            facts=strategy_facts(strategy, firecrawl_api_url=firecrawl_api_url),
        )
    except StrategyMismatchError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(outcome.crawl_doc, indent=2))
    if outcome.exit_code:
        click.echo(outcome.reason, err=True)
        raise SystemExit(outcome.exit_code)


if __name__ == "__main__":
    main()
