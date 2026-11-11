from __future__ import annotations

import pkgutil

from xtra.catalog.extract import ceasn, extractors


def test_every_module_is_a_ceasn_property_file() -> None:
    names = [info.name for info in pkgutil.iter_modules(ceasn.__path__)]
    assert all(name.startswith("ceasn_") for name in names)


def test_the_registry_accepts_the_vocabulary_folder() -> None:
    """A placeholder with no property files yet adds no extractors."""
    registered = {prop.split(":", 1)[0] for prop in extractors()}
    modules = list(pkgutil.iter_modules(ceasn.__path__))
    assert ("ceasn" in registered) == bool(modules)
