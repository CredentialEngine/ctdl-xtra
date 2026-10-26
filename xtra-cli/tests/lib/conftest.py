"""Shared setup for the tests of xtra-cli/lib.

src/lib/ is a folder of flat modules that import one another by bare name, so
it has to be on sys.path before any of them loads. load_engine() is the
same bridge the xtra CLI uses. It runs when pytest imports this conftest,
which pytest does before it imports any test module below it.

Several lib modules copy config.PACK, and the paths built from it, when
they are imported. The autouse pack fixture points config and every copy
at a fresh temporary pack, so no test can read or write xtra-cli/out. The
other autouse fixtures keep environment variables, config globals, the
browser, subprocesses and the blob client from leaking between tests.
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from lib_doubles import (
    DAY,
    NOW,
    FakeSyncPlaywright,
    PlaywrightError,
    PlaywrightTimeout,
    refuse_browser,
)

from implementations.engine import load_engine

LIB_DIR = load_engine()
LIB_MODULES = tuple(sorted(path.stem for path in LIB_DIR.glob("*.py")))
_LIB_PREFIX = os.path.normcase(str(LIB_DIR)) + os.sep

# config binds these when it is imported, and other modules copy them.
PATH_GLOBALS = (
    "PACK",
    "SCHEMA_PATH",
    "SNAPSHOT_DIR",
    "NORMALIZED_DIR",
    "RECORD_DIR",
    "SLOTS_NAME",
)
REGISTRY_KEYS = ("REGISTRY_API_KEY", "CE_API_KEY", "CE_REGISTRY_API_KEY")


def refuse_upload(*args: Any, **kwargs: Any) -> None:
    raise AssertionError(
        "a lib test tried to upload to Azure Blob Storage. Put a fake "
        "BlobClient in sys.modules['azure.storage.blob'] instead."
    )


def refuse_subprocess(*args: Any, **kwargs: Any) -> None:
    raise AssertionError(
        "a lib test tried to run a subprocess. Patch subprocess.run with a "
        "fake instead."
    )


def lib_modules() -> list[types.ModuleType]:
    """Every loaded module that lives under src/lib/, templates included."""
    return [
        module
        for module in list(sys.modules.values())
        if os.path.normcase(getattr(module, "__file__", None) or "").startswith(
            _LIB_PREFIX
        )
    ]


@pytest.fixture
def lib_dir() -> Path:
    return LIB_DIR


@pytest.fixture(autouse=True)
def lib_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """No XTRA_*, GOLDEN_SET_* or Registry key from the developer's shell."""
    import config

    for name in (*config.ENV_OLD, *config.ENV_OLD.values(), *REGISTRY_KEYS):
        # setenv first: delenv on an absent name records nothing, and then
        # a value the code writes straight into os.environ would outlive
        # the test.
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    # pack_home() falls back to xtra-cli/out, and configure_pack makes
    # folders under it.
    monkeypatch.setenv("XTRA_HOME", str(tmp_path_factory.mktemp("xtra-home")))
    monkeypatch.setattr(config, "_warned", set())
    for name in PATH_GLOBALS:
        monkeypatch.setattr(config, name, getattr(config, name))


@pytest.fixture(autouse=True)
def lib_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse the three ways lib reaches outside the process.

    The root conftest already refuses urllib. lib also starts Playwright
    (discover, freeze), runs a subprocess (union_fields) and uploads blobs
    (freeze). Each fails loudly here unless the test installs a fake.
    """
    playwright = types.ModuleType("playwright.sync_api")
    playwright.Error = PlaywrightError
    playwright.TimeoutError = PlaywrightTimeout
    playwright.sync_playwright = refuse_browser
    monkeypatch.setitem(sys.modules, "playwright.sync_api", playwright)

    blob = types.ModuleType("azure.storage.blob")
    blob.BlobClient = types.SimpleNamespace(from_blob_url=refuse_upload)
    monkeypatch.setitem(sys.modules, "azure.storage.blob", blob)

    monkeypatch.setattr(subprocess, "run", refuse_subprocess)


@pytest.fixture(autouse=True)
def pack(
    lib_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """A fresh pack that config, and every copy of its paths, point at."""
    for name in LIB_MODULES:
        importlib.import_module(name)
    import config
    import freeze

    root = tmp_path / "pack"
    root.mkdir()
    monkeypatch.setenv("XTRA_PACK", str(root))
    config.bind_runtime_paths()
    for module in lib_modules():
        if module is config:
            continue
        for name in PATH_GLOBALS:
            if hasattr(module, name):
                monkeypatch.setattr(module, name, getattr(config, name))
    # _existing_html also looks for freezes under the repo root.
    monkeypatch.setattr(freeze, "REPO_ROOT", tmp_path / "repo")
    shutil.copyfile(LIB_DIR / "record.schema.json", root / "record.schema.json")
    return root


@pytest.fixture
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> str:
    """Pin today's cache folder and every lib timestamp."""
    import freeze
    import record
    import registry

    monkeypatch.setattr(freeze, "utc_day", lambda: DAY)
    for module in (freeze, record, registry):
        monkeypatch.setattr(module, "_now", lambda: NOW)
    return NOW


@pytest.fixture
def fake_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., FakeSyncPlaywright]:
    """Install a FakeSyncPlaywright as playwright.sync_api.sync_playwright."""

    def install(pages: dict[str, Any], **options: Any) -> FakeSyncPlaywright:
        world = FakeSyncPlaywright(pages, **options)
        monkeypatch.setattr(
            sys.modules["playwright.sync_api"], "sync_playwright", world
        )
        return world

    return install
