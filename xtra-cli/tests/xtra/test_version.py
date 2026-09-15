from __future__ import annotations

from xtra.version import get_version


def test_get_version_returns_semver_string() -> None:
    version = get_version()
    assert isinstance(version, str)
    assert version[0].isdigit()
    assert "." in version
