from __future__ import annotations

import xtra
from xtra.version import get_version


def test_package_version_matches_get_version() -> None:
    assert xtra.__version__ == get_version()
    assert xtra.__doc__
