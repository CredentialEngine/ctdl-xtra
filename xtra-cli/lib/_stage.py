"""Shared entry point for the standalone stage scripts.

Each stage script is a thin wrapper: it resolves --pack, sets XTRA_*
in the environment BEFORE any engine module is imported (config.py reads the
environment at import time), then delegates to the matching cli subcommand.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def add_pack_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--pack",
        required=True,
        metavar="DIR",
        help="Pack directory. A relative name is created under XTRA_HOME.",
    )


def configure_pack(pack_arg: str) -> Path:
    """Set XTRA_* then rebind config.PACK. Call before importing freeze/build/cli."""
    from lib import pack_home

    pack = Path(pack_arg).expanduser()
    if not pack.is_absolute():
        pack = pack_home() / pack
    pack = pack.absolute()
    os.environ["XTRA_PACK"] = str(pack)
    if not (os.environ.get("XTRA_SLOTS") or os.environ.get("GOLDEN_SET_SLOTS") or "").strip():
        os.environ["XTRA_SLOTS"] = "dynamic"
    if not (os.environ.get("XTRA_MODE") or os.environ.get("GOLDEN_SET_MODE") or "").strip():
        os.environ["XTRA_MODE"] = "college"
    if not (os.environ.get("XTRA_PILE") or os.environ.get("GOLDEN_SET_PILE") or "").strip():
        os.environ["XTRA_PILE"] = pack.name
    pack.mkdir(parents=True, exist_ok=True)
    schema = HERE / "record.schema.json"
    if schema.is_file() and not (pack / "record.schema.json").is_file():
        (pack / "record.schema.json").write_bytes(schema.read_bytes())
    import config

    config.bind_runtime_paths()
    return pack


def run(subcommand: str, passthrough: list[str]) -> int:
    import cli

    return cli.main([subcommand, *passthrough])
