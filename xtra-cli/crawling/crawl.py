#!/usr/bin/env python3
"""Stage 1. catalog crawl: discover course detail URLs and write slots.json.

  python3 xtra-cli/xtra_cli.py catalog crawl --pack my_pack --url https://catalog.brookdalecc.edu --limit 5
  python3 xtra-cli/crawling/crawl.py --pack my_pack --url https://catalog.brookdalecc.edu --limit 5

Writes {pack}/slots.json. Downloads nothing; page download caches HTML.
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
        "--url",
        action="append",
        dest="urls",
        metavar="URL",
        help="Catalog home or course detail URL (repeatable)",
    )
    parser.add_argument("--url-file", metavar="PATH", help="One URL per line")
    parser.add_argument("--limit", type=int, default=None, help="Total course cap")
    parser.add_argument("--per-college", type=int, default=None, help="Cap per catalog")
    parser.add_argument("--all", action="store_true", help="Every discovered course")
    parser.add_argument("--institution", help="Override institution_name")
    args = parser.parse_args(argv)
    if not args.urls and not args.url_file:
        parser.error("need --url or --url-file")
    configure_pack(args.pack)
    passthrough: list[str] = []
    for url in args.urls or []:
        passthrough += ["--url", url]
    if args.url_file:
        passthrough += ["--url-file", args.url_file]
    if args.limit is not None:
        passthrough += ["--limit", str(args.limit)]
    if args.per_college is not None:
        passthrough += ["--per-college", str(args.per_college)]
    if args.all:
        passthrough.append("--all")
    if args.institution:
        passthrough += ["--institution", args.institution]
    return run("crawl", passthrough)


if __name__ == "__main__":
    raise SystemExit(main())
