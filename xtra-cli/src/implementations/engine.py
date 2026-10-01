"""Put xtra-cli/lib on sys.path so implementations can reuse the extractors."""

from __future__ import annotations

import sys
from pathlib import Path

_CLI_ROOT = Path(__file__).resolve().parents[2]
_LIB = _CLI_ROOT / "lib"


def load_engine() -> Path:
    lib = str(_LIB)
    if lib not in sys.path:
        sys.path.append(lib)
    return _LIB
