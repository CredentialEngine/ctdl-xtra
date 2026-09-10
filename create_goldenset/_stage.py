"""Shared entry point for the standalone stage scripts.

Each stage script is a thin wrapper: it resolves --pack, sets GOLDEN_SET_*
in the environment BEFORE any engine module is imported (config.py reads the
environment at import time), then delegates to the matching cli subcommand.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).absolute().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def add_pack_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--pack",
        required=True,
        metavar="DIR",
        help="Pack directory. A relative name is created under GOLDEN_SET_HOME.",
    )


def configure_pack(pack_arg: str) -> Path:
    """Set the environment the engine reads at import time. Call before importing cli."""
    from lib import golden_set_home

    pack = Path(pack_arg).expanduser()
    if not pack.is_absolute():
        pack = golden_set_home() / pack
    pack = pack.absolute()
    os.environ["GOLDEN_SET_PACK"] = str(pack)
    os.environ.setdefault("GOLDEN_SET_SLOTS", "dynamic")
    os.environ.setdefault("GOLDEN_SET_MODE", "college")
    os.environ.setdefault("GOLDEN_SET_PILE", pack.name)
    pack.mkdir(parents=True, exist_ok=True)
    schema = HERE / "record.schema.json"
    if schema.is_file() and not (pack / "record.schema.json").is_file():
        (pack / "record.schema.json").write_bytes(schema.read_bytes())
    return pack


def run(subcommand: str, passthrough: list[str]) -> int:
    import cli

    return cli.main([subcommand, *passthrough])
