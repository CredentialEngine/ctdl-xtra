from __future__ import annotations

import importlib


def test_config_package_imports() -> None:
    module = importlib.import_module("xtra.config")
    assert module.__doc__
