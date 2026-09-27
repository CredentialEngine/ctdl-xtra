from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

DISTRIBUTION_NAME = "xtra-cli"
DEFAULT_VERSION = "0.2.0"


def get_version() -> str:
    generated_version = _get_generated_version()
    if generated_version:
        return generated_version

    try:
        return package_version(DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return DEFAULT_VERSION


def _get_generated_version() -> str | None:
    """The release version, stamped by the release workflow before a build.

    A checkout never has the file, so this is None outside a release.
    """
    try:
        from xtra._generated_version import VERSION
    except ImportError:
        return None
    return VERSION
