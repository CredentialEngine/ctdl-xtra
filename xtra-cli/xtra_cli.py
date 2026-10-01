#!/usr/bin/env python3
"""Shim so `python3 xtra-cli/xtra_cli.py` matches `xtra` / `xtra-cli`."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from xtra.cli import cli

if __name__ == "__main__":
    cli()
