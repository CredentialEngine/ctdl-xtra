"""Runtime paths for this folder. Set GOLDEN_SET_PACK before importing engine modules."""

from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).absolute().parent
REPO_ROOT = HERE
ROOT = HERE
_pack = (os.environ.get("GOLDEN_SET_PACK") or "").strip()
PACK = Path(_pack).expanduser().absolute() if _pack else (HERE / "out").absolute()
SCHEMA_PATH = PACK / "record.schema.json"
SNAPSHOT_DIR = PACK / "snapshots"
NORMALIZED_DIR = PACK / "normalized"
RECORD_DIR = PACK / "records"
SLOTS_NAME = os.environ.get("GOLDEN_SET_SLOTS", "dynamic")

NORMALIZER_TOOL = "normalize"
NORMALIZER_VERSION = "1.0.0"
MAPPING_VERSION = "v4-pilot-0.1"
SCHEMA_RELEASE = "ctdl-json-2026-09-07-audit-pin"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
REGISTRY_USER_AGENT = "create-goldenset/1.0"
