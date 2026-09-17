from __future__ import annotations

from xtra import catalog


def test_catalog_package_imports() -> None:
    assert catalog is not None
