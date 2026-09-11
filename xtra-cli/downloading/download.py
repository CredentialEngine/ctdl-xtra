#!/usr/bin/env python3
"""Stage 2. page download: cache every page in slots.json under cache/{yyyy-mm-dd}/.

  python3 xtra-cli/xtra_cli.py page download --pack my_pack --normalize
  python3 xtra-cli/downloading/download.py --pack my_pack --normalize

Existing dated copies are reused, never overwritten. Set XTRA_CACHE_URL
to also upload each new file to a blob container.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _boot  # noqa: E402,F401

from _stage import add_pack_flag, configure_pack, run  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_pack_flag(parser)
    parser.add_argument(
        "--normalize",
        action="store_true",
        help="Also write normalized/*.txt after caching",
    )
    args = parser.parse_args(argv)
    configure_pack(args.pack)
    rc = run("freeze", [])
    if rc == 0 and args.normalize:
        rc = run("normalize", [])
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
