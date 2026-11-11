"""xtra catalog extract

  xtra catalog extract ceterms:name --catalog-id ID --run-id TS

Extracts one CTDL property from every page discovery gave one of its
classes to, and writes one file per resource under extraction_report/,
beside records/. One command for every property: the property picks the
extractor, and each extractor is one file in its vocabulary's folder, named
the way CE's split schema names its files (Schema-Development,
Split/properties/ceterms_name.jsonld). The output follows the same folders:

  ceterms:name -> xtra/catalog/extract/ceterms/ceterms_name.py
               -> extraction_report/ceterms/ceterms_name/{resource_id}.json

The file declares PROPERTY, CLASS (the classes it is read from) and read.
Adding a property is adding its file. A class is defined once, in
implementations/, and listed in CLASSES.
"""

from __future__ import annotations

import importlib
import json
import logging
import pkgutil
import re
from types import ModuleType

import click

from common.keys import property_key
from common.object_store import open_store
from implementations.discover import latest_discovery_run_id
from implementations.extract import (
    ExtractionError,
    Extractor,
    RdfClass,
    run_extraction,
)
from implementations.extract_course import COURSE
from xtra.click import (
    POSITIVE_INT,
    env_option,
    non_empty_string,
    resolve_connection,
    resolve_uri,
    source_uri_option,
    storage_connection_options,
    target_uri_option,
)
from xtra.version import get_version

logger = logging.getLogger(__name__)

PROPERTY_RE = re.compile(r"[a-z][a-z0-9]*:[A-Za-z][A-Za-z0-9]*")
PROPERTY_PATH_RE = re.compile(
    rf"{PROPERTY_RE.pattern}(?:\s*>\s*{PROPERTY_RE.pattern})*"
)


# Every class a property can name in its CLASS tuple.
CLASSES: dict[str, RdfClass] = {c.rdf_type: c for c in (COURSE,)}


class RegistryError(Exception):
    """An extractor module breaks the naming or shape the registry needs."""


def extractors(
    package: str = __name__, classes: dict[str, RdfClass] = CLASSES
) -> dict[str, Extractor]:
    """Every property with an extractor, from the file tree.

    Each subpackage is a vocabulary, named for its prefix (ceterms). Each
    module in it is a property and declares PROPERTY, CLASS and read. A
    file has to be named for the property it declares (ceterms_name), so
    the tree and the properties can't drift, and nothing nests deeper than
    the vocabulary.
    """
    root = importlib.import_module(package)
    found: dict[str, Extractor] = {}
    for vocabulary in pkgutil.iter_modules(root.__path__):
        if not vocabulary.ispkg:
            raise RegistryError(
                f"{package}.{vocabulary.name} is outside a vocabulary "
                "folder. Put it in the folder of its prefix, e.g. "
                "ceterms/ceterms_name.py"
            )
        vocabulary_module = importlib.import_module(
            f"{package}.{vocabulary.name}"
        )
        for info in pkgutil.iter_modules(vocabulary_module.__path__):
            name = f"{vocabulary_module.__name__}.{info.name}"
            if info.ispkg:
                raise RegistryError(
                    f"{name} is a folder. A vocabulary holds one file "
                    "per property and nothing deeper"
                )
            module = importlib.import_module(name)
            prop = _declared(module, "PROPERTY", PROPERTY_PATH_RE)
            _named_for(module, info.name, prop)
            prefix = prop.split(":", 1)[0]
            if prefix != vocabulary.name:
                raise RegistryError(
                    f"{name} declares {prop}, so it belongs in {prefix}/"
                )
            if prop in found:
                raise RegistryError(f"two extractors declare {prop}")
            found[prop] = Extractor(
                prop=prop,
                classes=_classes(module, classes),
                read=_required(module, "read"),
            )
    return dict(sorted(found.items()))


def _classes(
    module: ModuleType, classes: dict[str, RdfClass]
) -> tuple[RdfClass, ...]:
    declared = _required(module, "CLASS")
    if (
        not isinstance(declared, tuple)
        or not declared
        or not all(isinstance(rdf_type, str) for rdf_type in declared)
    ):
        raise RegistryError(
            f"{module.__name__}.CLASS = {declared!r} is not a tuple of "
            "CTDL classes"
        )
    unknown = [rdf_type for rdf_type in declared if rdf_type not in classes]
    if unknown:
        raise RegistryError(
            f"{module.__name__}.CLASS names {', '.join(unknown)}. "
            f"Classes: {', '.join(sorted(classes))}"
        )
    return tuple(classes[rdf_type] for rdf_type in declared)


def _required(module: ModuleType, name: str):
    if not hasattr(module, name):
        raise RegistryError(f"{module.__name__} declares no {name}")
    return getattr(module, name)


def _declared(module: ModuleType, name: str, pattern: re.Pattern[str]) -> str:
    value = _required(module, name)
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise RegistryError(
            f"{module.__name__}.{name} = {value!r} is not a CTDL property"
        )
    return value


def _named_for(module: ModuleType, name: str, prop: str) -> None:
    if name != property_key(prop):
        raise RegistryError(
            f"{module.__name__} declares {prop}, so it has to be named "
            f"{property_key(prop)}"
        )


def _available(registry: dict[str, Extractor]) -> str:
    return "\n".join(
        f"  {prop}  (class: {', '.join(c.rdf_type for c in e.classes)})"
        for prop, e in registry.items()
    )


def choose_extractor(registry: dict[str, Extractor], prop: str) -> Extractor:
    """The extractor for the property, or a UsageError naming what exists."""
    if not PROPERTY_PATH_RE.fullmatch(prop):
        raise click.UsageError(
            f"{prop!r} is not a CTDL property, e.g. ceterms:name"
        )
    extractor = registry.get(prop)
    if extractor is None:
        raise click.UsageError(
            f"no extractor for {prop}. Properties: {', '.join(registry)}"
        )
    return extractor


class _ExtractionCommand(click.Command):
    """Lists the extractors under the help, read when help is asked."""

    def format_epilog(self, ctx, formatter) -> None:
        super().format_epilog(ctx, formatter)
        with formatter.section("Extractors"):
            formatter.write_text(_available(extractors()))


@click.command(name="extract", cls=_ExtractionCommand)
@click.argument("prop", metavar="PROPERTY")
@env_option()
@source_uri_option()
@target_uri_option()
@click.option("--catalog-id", required=True, callback=non_empty_string)
@click.option(
    "--run-id",
    required=True,
    callback=non_empty_string,
    help="Crawl run id from catalog crawl.",
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
@click.option(
    "--limit",
    type=POSITIVE_INT,
    default=None,
    help="Read at most this many pages. Use 5 while testing.",
)
@storage_connection_options()
def main(
    prop: str,
    env_name: str | None,
    source_uri: str | None,
    target_uri: str | None,
    catalog_id: str,
    run_id: str,
    discovery_run_id: str | None,
    only_golden_sample: bool,
    limit: int | None,
    azure_storage_connection_string: str | None,
) -> None:
    """Extract one CTDL PROPERTY into extraction_report/.

    PROPERTY is a CTDL property: ceterms:name. For each class it declares,
    reads every page discovery labelled with the class and each resource
    on it (a page of course blocks has one per block), and writes
    extraction_report/<prefix>/<property key>/{resource_id}.json. The class
    says how a resource is identified: a course by its catalog and code,
    catalog-example-edu_ABA610. A resource with no id is not written,
    only counted; a repeated id gets -2, -3. A value not found is written,
    marked absent. Counts go to extraction-<property>-report.json, beside
    extraction_report/.
    """
    try:
        registry = extractors()
    except RegistryError as exc:
        raise click.ClickException(str(exc)) from exc
    extractor = choose_extractor(registry, prop)

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

    try:
        report = run_extraction(
            source,
            target,
            extractor,
            catalog_id=catalog_id,
            run_id=run_id,
            discovery_run_id=discovery_run_id,
            only_golden_sample=only_golden_sample,
            limit=limit,
            version=get_version(),
        )
    except ExtractionError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "property",
                    "class",
                    "catalog_folder",
                    "run_id",
                    "discovery_run_id",
                    "pages_read",
                    "occurrences",
                    "found",
                    "not_found",
                    "files_cleared",
                    "resources_written",
                    "no_resource_id",
                    "repeated_resource_ids",
                    "by_strategy",
                    "not_found_by_reason",
                    "report_key",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
