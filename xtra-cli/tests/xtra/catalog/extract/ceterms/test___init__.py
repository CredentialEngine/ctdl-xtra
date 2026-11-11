from __future__ import annotations

import pkgutil

from xtra.catalog.extract import ceterms


def test_every_module_is_a_ceterms_property_file() -> None:
    names = [info.name for info in pkgutil.iter_modules(ceterms.__path__)]
    assert "ceterms_name" in names
    assert all(name.startswith("ceterms_") for name in names)
