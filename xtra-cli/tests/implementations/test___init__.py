from __future__ import annotations

import implementations


def test_implementations_package_imports() -> None:
    assert implementations.__doc__
    assert "crawl" in implementations.__doc__.lower()
