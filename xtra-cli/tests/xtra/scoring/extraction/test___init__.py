from __future__ import annotations

from xtra.scoring import extraction


def test_extraction_package_imports() -> None:
    assert extraction is not None
