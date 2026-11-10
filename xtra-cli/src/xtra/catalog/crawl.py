"""xtra catalog crawl

  xtra catalog crawl --with-playwright --url https://catalog.example.edu --target-uri ./cache --limit 5

  xtra catalog crawl --with-playwright --url https://catalog.example.edu --from-run-id <run-id>

  xtra catalog crawl status --url https://catalog.example.edu --run-id <run-id>

  xtra catalog crawl summary --url https://catalog.example.edu --run-id <run-id>

  xtra catalog crawl navigation --url https://catalog.example.edu --run-id <run-id>

Download and save. The crawl does not classify pages, name an institution,
or normalize anything; discovery and extraction read what it saved.
`crawl status` counts what a run has done so far, `crawl summary` lists it,
`crawl navigation` maps which source URL led to which target URLs.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import click
from click.core import ParameterSource

from common.clock import is_iso8601_utc, utc_timestamp
from common.keys import catalog_folder_name
from common.object_store import open_store
from implementations.crawl import (
    MAX_CONSECUTIVE_FAILURES,
    CrawlSettings,
    RunStopError,
    StrategyMismatchError,
    run_crawl,
)
from implementations.crawl_browser import BROWSER_CHROMIUM, BROWSERS
from implementations.crawl_fetchers import (
    DEFAULT_FIRECRAWL_API_URL,
    StrategyNotImplementedError,
    StrategyOptionError,
    fetcher_factory_for,
)
from implementations.crawl_manifest import ManifestError
from implementations.crawl_strategy import strategy_facts
from xtra.catalog.crawl_navigation import main as navigation_command
from xtra.catalog.crawl_status import main as status_command
from xtra.catalog.crawl_summary import main as summary_command
from xtra.click import (
    POSITIVE_INT,
    blank_as_unset,
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


def refuse_crawl_options_before_a_subcommand(ctx: click.Context) -> None:
    given = sorted(
        {
            param.opts[0]
            for param in ctx.command.params
            if param.name is not None
            and ctx.get_parameter_source(param.name)
            == ParameterSource.COMMANDLINE
        }
    )
    if not given:
        return
    raise click.UsageError(
        f"{', '.join(given)} came before '{ctx.invoked_subcommand}'. "
        f"Put every option after it: xtra catalog crawl "
        f"{ctx.invoked_subcommand} --url <catalog-url> --run-id <run-id>",
        ctx=ctx,
    )


def read_seed_urls(path: Path | None) -> tuple[str, ...]:
    """One URL per line. Blank lines and # comments are ignored.

    A byte order mark is dropped: PowerShell 5.1 writes one with
    Set-Content -Encoding utf8, and it would turn the first URL into one
    with no scheme, skipped without a word.
    """
    if path is None:
        return ()
    lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
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


@click.group(
    name="crawl",
    invoke_without_command=True,
    subcommand_metavar="[status|summary|navigation [OPTIONS]]",
)
@strategy_options(
    "playwright", "crawl4ai", "firecrawl", "ai-agent", "third-party"
)
@click.option(
    "--url",
    default=None,
    help="Catalog URL the crawl starts from. Required to crawl.",
)
@env_option()
@target_uri_option()
@click.option(
    "--run-id",
    default=None,
    help=(
        "UTC run id, yyyy-MM-ddTHH:mm:ssZ or yyyy-MM-ddTHH-mm-ssZ. "
        "Default: now. A run id is used once."
    ),
)
@click.option(
    "--from-run-id",
    default=None,
    callback=blank_as_unset,
    help=(
        "An earlier run of the same --url to continue from. Each page it "
        "saved is copied into this run when the crawl reaches it, instead "
        "of fetched; its failed and skipped URLs, and any bot-challenge "
        "page it kept, are fetched again. The earlier run is only read. "
        "An empty value is the same as leaving it out."
    ),
)
@limit_option()
@crawl_pacing_options()
@click.option(
    "--max-consecutive-failures",
    type=POSITIVE_INT,
    default=MAX_CONSECUTIVE_FAILURES,
    show_default=True,
    help=(
        "Stop the run after this many blocking failures in a row: HTTP "
        "401, 403, 429 or 5xx after every retry, bot-challenge pages, and "
        "network errors. A saved page resets the count. A 404, 410 or other "
        "page-level 4xx is recorded but never counts. May differ from one "
        "run to the next."
    ),
)
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
        "Keep a followed URL only when it matches, searched anywhere in the "
        "full URL. Repeatable. Example for a host that keeps several catalog "
        r"years: --include-regex '[?&;]catoid=13(?!\d)', which does not "
        "match catoid=130. Seeds skip it, so when the start page does not "
        "link to that catalog, put its index page in --seed-urls-file."
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
    "--browser",
    type=click.Choice(BROWSERS),
    default=BROWSER_CHROMIUM,
    show_default=True,
    help=(
        "With --with-playwright: chromium, the lighter browser that comes "
        "with Playwright, or chrome, Google Chrome as installed on this "
        "machine, for a site that challenges Chromium. Chrome is never "
        "swapped for Chromium: if it is not installed the run stops."
    ),
)
@click.option(
    "--keep-browser-open",
    is_flag=True,
    help=(
        "With --with-playwright, keep each worker's browser open for the "
        "whole run. By default a worker closes its browser after each page, "
        "keeping the cookies, and opens it again for the next, so it holds "
        "no browser while it waits."
    ),
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
@click.pass_context
def main(
    ctx: click.Context,
    strategy: str | None,
    url: str | None,
    env_name: str | None,
    target_uri: str | None,
    run_id: str | None,
    from_run_id: str | None,
    limit: int | None,
    concurrency_limit: int,
    min_interval_in_seconds: float,
    max_interval_in_seconds: float,
    max_retries: int,
    max_consecutive_failures: int,
    scope_prefix: str | None,
    include_regex: tuple[str, ...],
    exclude_regex: tuple[str, ...],
    seed_urls_file: Path | None,
    browser: str,
    keep_browser_open: bool,
    firecrawl_api_key: str | None,
    firecrawl_api_url: str,
    azure_storage_connection_string: str | None,
) -> None:
    """Download every page of one catalog and save it.

    Output goes under {catalog-folder}/{run-id}/ in --target-uri, where the
    catalog folder is --url with hyphens for everything that is not a letter
    or a digit. A run is never continued in place: to carry on after one
    stops, start a new run with --from-run-id naming it, and the pages it
    saved are copied instead of fetched again.

    `xtra catalog crawl status` counts what a run has done so far,
    `xtra catalog crawl summary` lists it, one row per URL, and
    `xtra catalog crawl navigation` writes navigation.json, the source
    URL each URL was first found on, from the pages a run saved.
    """
    if ctx.invoked_subcommand is not None:
        refuse_crawl_options_before_a_subcommand(ctx)
        return
    if not url:
        raise click.UsageError("Missing option '--url'.", ctx=ctx)
    strategy = require_strategy(strategy, example="--with-playwright")
    try:
        fetcher_factory = fetcher_factory_for(
            strategy,
            firecrawl_api_key=firecrawl_api_key,
            firecrawl_api_url=firecrawl_api_url,
            keep_browser_open=keep_browser_open,
            browser=browser,
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
    if from_run_id is not None and not is_iso8601_utc(from_run_id):
        raise click.UsageError(
            f"--from-run-id {from_run_id!r} is not a UTC timestamp. "
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
            max_consecutive_failures=max_consecutive_failures,
            scope_prefix=scope_prefix,
            include_regex=include_regex,
            exclude_regex=exclude_regex,
            seed_urls=read_seed_urls(seed_urls_file),
            strategy=strategy,
            from_run_id=from_run_id,
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
            facts=strategy_facts(
                strategy,
                firecrawl_api_url=firecrawl_api_url,
                keep_browser_open=keep_browser_open,
                browser=browser,
            ),
        )
    except (StrategyMismatchError, ManifestError, RunStopError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(outcome.crawl_doc, indent=2))
    if outcome.exit_code:
        click.echo(outcome.reason, err=True)
        raise SystemExit(outcome.exit_code)


main.add_command(status_command, name="status")
main.add_command(summary_command, name="summary")
main.add_command(navigation_command, name="navigation")


if __name__ == "__main__":
    main()
