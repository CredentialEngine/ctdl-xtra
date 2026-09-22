from __future__ import annotations


def get_version() -> str:
    try:
        from importlib.metadata import version

        return version("xtra-cli")
    except Exception:
        return "0.2.0"
