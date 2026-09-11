#!/usr/bin/env python3
"""pipeline run: one-shot catalog crawl → page download → course extract → course transform.

Same pipeline for a working extract and for a pack later copied after humans
review freeze + JSON. That copy is a folder, not a second codebase.

  python3 xtra-cli/xtra_cli.py pipeline run --url https://catalog.brookdalecc.edu
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _boot  # noqa: E402,F401

from lib import (  # noqa: E402
    _display_pack,
    check_pack,
    configure,
    json_dumps,
    load_url_file,
    refuse_existing_pack,
    resolve_pack,
    write_check,
    write_pack_readme,
)


def collect_urls(args: argparse.Namespace) -> list[str]:
    urls = list(args.urls or [])
    if args.url_file:
        urls.extend(load_url_file(Path(args.url_file)))
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create a freeze-backed Course pack from college catalog home pages "
            "and/or course detail URLs."
        ),
        epilog="Example: python3 xtra-cli/xtra_cli.py run --url https://catalog.brookdalecc.edu",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--url",
        action="append",
        dest="urls",
        metavar="URL",
        help="Catalog home or course detail URL (repeatable)",
    )
    parser.add_argument(
        "--url-file",
        metavar="PATH",
        help="Text file: one URL per line (# comments ok)",
    )
    parser.add_argument(
        "--out",
        help="Pack folder (absolute path, or a name under XTRA_HOME / xtra-cli/out)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Total course cap after sampling")
    parser.add_argument(
        "--per-college",
        type=int,
        default=None,
        help="Max courses per catalog URL (default 30 one URL, 5 several)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Freeze every discovered course page (no sampling)",
    )
    parser.add_argument("--institution", help="Override institution_name on every record")
    parser.add_argument(
        "--skip-registry",
        action="store_true",
        help="Skip Credential Engine exact-URL lookup",
    )
    parser.add_argument(
        "--allow-errors",
        action="store_true",
        help="Exit 0 even if CHECK.json.ok is false (still writes the pack)",
    )
    args = parser.parse_args(argv)
    urls = collect_urls(args)
    if not urls:
        parser.print_help()
        print("\nNeed --url or --url-file.")
        return 2

    pack = resolve_pack(args.out, urls)
    blocked = refuse_existing_pack(pack)
    if blocked:
        print(blocked, file=sys.stderr)
        return 2
    configure(pack)

    from college_capture import run_college_capture

    result = run_college_capture(
        urls,
        per_college=args.per_college,
        total_limit=args.limit,
        fetch_all=args.all,
        institution=args.institution,
        skip_registry=args.skip_registry,
    )
    errors = check_pack(pack)
    write_check(pack, errors, extra=result.get("records"))
    write_pack_readme(pack, seeds=urls, errors=errors)
    print(json_dumps({**result, "check_ok": not errors, "pack": str(_display_pack(pack))}))
    if errors:
        print("CHECK failed (pack is not freeze-perfect):", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 0 if args.allow_errors else 1
    print(f"CHECK passed: {pack / 'CHECK.json'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
