#!/usr/bin/env python3
"""Re-check a generated Course pack. Does not invent expected or sign records."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).absolute().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from lib import check_pack, configure, resolve_existing_pack, write_check


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate freeze-backed Course golden files in an existing pack"
    )
    parser.add_argument(
        "--pack",
        required=True,
        help="Pack directory (absolute path, or a folder name under GOLDEN_SET_HOME)",
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
