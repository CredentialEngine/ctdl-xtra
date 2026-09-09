#!/usr/bin/env python3
"""Generate a NEW candidate Course golden set from catalog or course URLs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from lib import (
    ROOT,
    check_pack,
    configure,
    json_dumps,
    load_url_file,
    refuse_protected_pack,
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
            "Create a new freeze-backed Course golden set from college catalog "
            "home pages and/or course detail URLs. Does not rebuild NJ 30."
        ),
        epilog=(
            "Example: python3 run.py "
            "--url https://catalog.brookdalecc.edu"
        ),
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
        help="Pack folder under C:\\Code\\golden_set (default golden_set_<college>_courses)",
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
        print("\nNeed --url or --url-file. Need --url or --url-file.")
        return 2

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    pack = resolve_pack(args.out, urls)
    blocked = refuse_protected_pack(pack)
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
    print(json_dumps({**result, "check_ok": not errors, "pack": str(pack)}))
    if errors:
        print("CHECK failed (pack is not freeze-perfect):", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 0 if args.allow_errors else 1
    print(f"CHECK passed: {pack / 'CHECK.json'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
