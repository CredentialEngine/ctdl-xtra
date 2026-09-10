#!/usr/bin/env python3
"""Stage 1b. Cache every page in slots.json under cache/{yyyy-mm-dd}/.

  python3 download.py --pack my_pack

Existing dated copies are reused, never overwritten. Set GOLDEN_SET_CACHE_URL
to also upload each new file to a blob container.
"""

from __future__ import annotations

import argparse

from _stage import add_pack_flag, configure_pack, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_pack_flag(parser)
    parser.add_argument("--normalize", action="store_true",
                        help="Also write normalized/*.txt after caching")
    args = parser.parse_args(argv)
    configure_pack(args.pack)
    rc = run("freeze", [])
    if rc == 0 and args.normalize:
        rc = run("normalize", [])
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
