from __future__ import annotations

import common


def test_common_package_docstring() -> None:
    assert common.__doc__
    assert "storage" in common.__doc__.lower()
