from __future__ import annotations

import logging
import os

import click

from xtra.environment import environment_group
from xtra.version import get_version


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _load_command(module_path: str) -> click.Command:
    import importlib

    module = importlib.import_module(module_path)
    command = getattr(module, "main", None)
    if not isinstance(command, click.Command):
        raise click.ClickException(f"{module_path} does not define main")
    return command


@click.version_option(version=get_version(), prog_name="xtra")
@click.group()
def cli() -> None:
    """Credential Engine xTRA operations CLI.

    Commands follow the ceops noun / verb layout:

    \b
      xtra environment set prod --data-uri <storage-uri>
      xtra catalog crawl --with-playwright --url <catalog-url> --limit 5
      xtra catalog extract --with-template --catalog-id ID --run-id TS
      xtra catalog transform --with-ctdl --catalog-id ID --run-id TS

    \b
    Those stages read and write the active environment. Pass --target-uri to
    override it, or --env test|sandbox|prod to switch it for one run.
    """
    configure_logging()


@cli.group(name="catalog")
def catalog_group() -> None:
    """Crawl, extract, and transform one catalog of any size."""


@cli.group(name="page")
def page_group() -> None:
    """Download individual catalog pages into object storage."""


cli.add_command(environment_group)
catalog_group.add_command(_load_command("xtra.catalog.crawl"))
catalog_group.add_command(_load_command("xtra.catalog.extract"))
catalog_group.add_command(_load_command("xtra.catalog.transform"))
page_group.add_command(_load_command("xtra.page.download"))
