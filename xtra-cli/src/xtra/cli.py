from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass

import click

from xtra.environment import environment_group
from xtra.version import get_version


@dataclass(frozen=True, slots=True)
class CommandSpec:
    module_name: str
    module_path: str


CATALOG_COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        module_name="crawl",
        module_path="xtra.catalog.crawl",
    ),
    CommandSpec(
        module_name="discover",
        module_path="xtra.catalog.discover",
    ),
    CommandSpec(
        module_name="extract",
        module_path="xtra.catalog.extract",
    ),
    CommandSpec(
        module_name="transform",
        module_path="xtra.catalog.transform",
    ),
)


SCORE_EXTRACTION_COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        module_name="match",
        module_path="xtra.score.extraction.match",
    ),
)


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # The Azure SDK and httpx2 log every request at INFO, which buries the
    # one line per page this CLI exists to print.
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)


def load_command(
    spec: CommandSpec,
) -> click.Command:
    module = importlib.import_module(spec.module_path)

    if not hasattr(module, "main"):
        raise click.ClickException(
            f"Command module '{spec.module_path}' does not define main"
        )

    command = module.main

    if not isinstance(command, click.Command):
        raise click.ClickException(
            f"Command module '{spec.module_path}' does not define main"
        )

    return command


def register_catalog_commands(
    group: click.Group,
) -> None:
    for command_spec in CATALOG_COMMAND_SPECS:
        catalog_command = load_command(command_spec)

        group.add_command(
            catalog_command,
            name=command_spec.module_name,
        )


def register_score_extraction_commands(
    group: click.Group,
) -> None:
    for command_spec in SCORE_EXTRACTION_COMMAND_SPECS:
        score_command = load_command(command_spec)

        group.add_command(
            score_command,
            name=command_spec.module_name,
        )


@click.version_option(version=get_version(), prog_name="xtra")
@click.group()
def cli() -> None:
    """Credential Engine xTRA operations CLI."""
    configure_logging()


@cli.group(name="catalog")
def catalog_group() -> None:
    """Crawl, discover, extract, and transform one catalog of any size."""


@cli.group(name="score")
def score_group() -> None:
    """Score the output of a stage against a baseline."""


@score_group.group(name="extraction")
def score_extraction_group() -> None:
    """Score extraction records."""


cli.add_command(environment_group)
register_catalog_commands(catalog_group)
register_score_extraction_commands(score_extraction_group)
