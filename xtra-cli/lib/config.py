"""Runtime paths. Set XTRA_PACK, then call bind_runtime_paths().

Engine modules copy PACK at import time, so the env must be set and rebound
before freeze/build/college_capture are imported.

Deprecated GOLDEN_SET_* names still work and print a stderr warning.

Schema contract deferred: record.schema.json keeps $id
.../golden-set/v2/... and the key golden_value. Those are a versioned data
contrac.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

LIB_DIR = Path(__file__).resolve().parent
HERE = LIB_DIR
CLI_ROOT = LIB_DIR.parent
REPO_ROOT = CLI_ROOT.parent
ROOT = REPO_ROOT

# new name → old GOLDEN_SET_* name (stderr warning, then treat as the new name)
ENV_OLD = {
    "XTRA_HOME": "GOLDEN_SET_HOME",
    "XTRA_PACK": "GOLDEN_SET_PACK",
    "XTRA_MODE": "GOLDEN_SET_MODE",
    "XTRA_SLOTS": "GOLDEN_SET_SLOTS",
    "XTRA_PILE": "GOLDEN_SET_PILE",
    "XTRA_CACHE_URL": "GOLDEN_SET_CACHE_URL",
}

_warned: set[str] = set()


def env_get(name: str, default: str = "") -> str:
    """Read XTRA_* ; fall back to GOLDEN_SET_* with one warning per process."""
    raw = (os.environ.get(name) or "").strip()
    if raw:
        return raw
    old = ENV_OLD.get(name)
    if old:
        legacy = (os.environ.get(old) or "").strip()
        if legacy:
            if old not in _warned:
                print(
                    f"warning: {old} is deprecated; use {name}",
                    file=sys.stderr,
                )
                _warned.add(old)
            return legacy
    return default


def env_set(name: str, value: str) -> None:
    os.environ[name] = value


def env_setdefault(name: str, value: str) -> None:
    if env_get(name):
        return
    os.environ[name] = value


PACK: Path
SCHEMA_PATH: Path
SNAPSHOT_DIR: Path
NORMALIZED_DIR: Path
RECORD_DIR: Path
SLOTS_NAME: str


def bind_runtime_paths() -> None:
    """Re-read XTRA_PACK / XTRA_SLOTS into the module globals this process uses."""
    global PACK, SCHEMA_PATH, SNAPSHOT_DIR, NORMALIZED_DIR, RECORD_DIR, SLOTS_NAME
    _pack = env_get("XTRA_PACK")
    PACK = Path(_pack).expanduser().absolute() if _pack else (CLI_ROOT / "out").absolute()
    SCHEMA_PATH = PACK / "record.schema.json"
    SNAPSHOT_DIR = PACK / "snapshots"
    NORMALIZED_DIR = PACK / "normalized"
    RECORD_DIR = PACK / "records"
    SLOTS_NAME = env_get("XTRA_SLOTS", "dynamic")


bind_runtime_paths()

NORMALIZER_TOOL = "normalize"
NORMALIZER_VERSION = "1.0.0"
MAPPING_VERSION = "v4-pilot-0.1"
SCHEMA_RELEASE = "ctdl-json-2026-09-07-audit-pin"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
REGISTRY_USER_AGENT = "xtra-cli/1.0"
