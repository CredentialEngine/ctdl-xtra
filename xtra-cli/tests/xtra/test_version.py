from __future__ import annotations

import sys
import types
from importlib.metadata import PackageNotFoundError

import pytest

from xtra import version as version_module
from xtra.version import DEFAULT_VERSION, get_version


@pytest.fixture
def no_generated_version(monkeypatch) -> None:
    """None in sys.modules makes the import fail, as it does in a checkout."""
    monkeypatch.setitem(sys.modules, "xtra._generated_version", None)


def test_get_version_returns_semver_string() -> None:
    version = get_version()
    assert isinstance(version, str)
    assert version[0].isdigit()
    assert "." in version


def test_get_version_prefers_generated_version(monkeypatch) -> None:
    generated_version = types.ModuleType("xtra._generated_version")
    generated_version.VERSION = "2026.09.24.17"
    monkeypatch.setitem(
        sys.modules, "xtra._generated_version", generated_version
    )

    assert get_version() == "2026.09.24.17"


def test_get_version_reads_the_installed_package_when_not_stamped(
    monkeypatch, no_generated_version
) -> None:
    asked: list[str] = []

    def installed(name: str) -> str:
        asked.append(name)
        return "1.2.3"

    monkeypatch.setattr(version_module, "package_version", installed)

    assert get_version() == "1.2.3"
    assert asked == ["xtra-cli"]


def test_get_version_falls_back_when_the_package_is_not_installed(
    monkeypatch, no_generated_version
) -> None:
    def missing(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(version_module, "package_version", missing)

    assert get_version() == DEFAULT_VERSION
