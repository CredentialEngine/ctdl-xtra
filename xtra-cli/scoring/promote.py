#!/usr/bin/env python3
"""pack promote: copy courses/*.json into a destination folder.

This is a business copy, not a second pipeline. It does not set human_signed.
`--to golden_sets/courses` is a user-supplied path; the code does not treat
that folder as a special mode.

  python3 xtra-cli/xtra_cli.py pack promote --pack my_pack --to golden_sets/courses
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _boot  # noqa: E402,F401

from _stage import add_pack_flag, configure_pack  # noqa: E402
from lib import resolve_existing_pack  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_pack_flag(parser)
    parser.add_argument(
        "--to",
        required=True,
        help="Destination directory for courses/*.json copies",
    )
    args = parser.parse_args(argv)
    pack = resolve_existing_pack(args.pack)
    configure_pack(str(pack))
    src = pack / "courses"
    if not src.is_dir():
        print(f"missing {src}; run transform first", file=sys.stderr)
        return 1
    dest = Path(args.to).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for path in sorted(src.glob("*.json")):
        shutil.copy2(path, dest / path.name)
        n += 1
        print(f"copied {path.name}")
    print(f"copied {n} files to {dest}")
    return 0 if n else 1


if __name__ == "__main__":
    raise SystemExit(main())
