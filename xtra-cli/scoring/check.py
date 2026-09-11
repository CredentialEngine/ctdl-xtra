#!/usr/bin/env python3
"""pack check: re-check a Course pack. Does not invent expected or sign records.

  python3 xtra-cli/xtra_cli.py pack check --pack my_pack
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _boot  # noqa: E402,F401

from lib import check_pack, configure, resolve_existing_pack, write_check  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate freeze-backed Course files in an existing pack"
    )
    parser.add_argument(
        "--pack",
        required=True,
        help="Pack directory (absolute path, or a folder name under XTRA_HOME)",
    )
    args = parser.parse_args(argv)
    pack = resolve_existing_pack(args.pack)
    configure(pack)
    errors = check_pack(pack)
    dest = write_check(pack, errors)
    if errors:
        print(f"FAIL {dest} ({len(errors)} errors)", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print(f"PASS {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
