from __future__ import annotations

import xtra.catalog as catalog


def test_catalog_package_imports() -> None:
    assert catalog is not None
