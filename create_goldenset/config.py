"""Runtime paths for this generator folder. Set GOLDEN_SET_PACK before importing."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACK = Path(os.environ.get("GOLDEN_SET_PACK", str(ROOT / "out")))
SCHEMA_PATH = PACK / "record.schema.json"
SNAPSHOT_DIR = PACK / "snapshots"
NORMALIZED_DIR = PACK / "normalized"
RECORD_DIR = PACK / "records"
SLOTS_NAME = os.environ.get("GOLDEN_SET_SLOTS", "dynamic")

NORMALIZER_TOOL = "normalize"
NORMALIZER_VERSION = "1.0.0"
MAPPING_VERSION = "course-pack-0.1"
SCHEMA_RELEASE = "ctdl-json-2026-09-07-audit-pin"
