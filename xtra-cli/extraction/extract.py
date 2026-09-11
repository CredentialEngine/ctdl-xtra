#!/usr/bin/env python3
"""Stage 3. course extract: printed course fields from cached, normalized pages.

  python3 xtra-cli/xtra_cli.py course extract --pack my_pack
  python3 xtra-cli/extraction/extract.py --pack my_pack

Classifies templates from freeze text, writes records/*.json, hydrates evidence.
Does not invent expected values and does not mark records human_signed.
Same command for a live extract and for a pack later copied after review.
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
        "--skip-classify",
        action="store_true",
        help="Use template_id already stamped on slots.json",
    )
    args = parser.parse_args(argv)
    configure_pack(args.pack)
    if not args.skip_classify:
        rc = run("classify", [])
        if rc != 0:
            return rc
    rc = run("build", [])
    if rc != 0:
        return rc
    return run("hydrate", [])


if __name__ == "__main__":
    raise SystemExit(main())
