"""Command line: `xtra crawl`, then `xtra extract`. There is no `xtra publish`, and there will not be."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="xtra", description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"), help="data folder (default: data)")
    sub = parser.add_subparsers(dest="command", required=True)

    crawl = sub.add_parser("crawl", help="step 1: fetch pages into the page store (uses the internet)")
    crawl.add_argument("--subjects", default="ACCT,CHEM,CSCE,ENGL,NURS",
                       help='comma-separated subject codes, or "all"')
    crawl.add_argument("--refetch", action="append", default=[], metavar="ADDRESS",
                       help="fetch this address again even though it is stored (never overwrites)")

    extract = sub.add_parser("extract", help="step 2: build records from the page store (no internet)")
    extract.add_argument("--subjects", default="ACCT,CHEM,CSCE,ENGL,NURS")
    extract.add_argument("--language-model", default="ollama:qwen3.5:9b",
                         help='"ollama:<name>", "nonsense" (a stand-in that returns rubbish) or "none"')
    extract.add_argument("--rules", type=Path, default=Path("rules"))
    extract.add_argument("--reference", type=Path, default=Path("reference"))

    args = parser.parse_args(argv)
    if args.command == "crawl":
        from .crawl import Crawler, HttpFetcher
        from .store import PageStore

        subjects = "all" if args.subjects == "all" else tuple(s.strip() for s in args.subjects.split(","))
        crawler = Crawler(PageStore(args.data / "store"), HttpFetcher())
        report = crawler.run(subjects=subjects, refetch=tuple(args.refetch))
        print(f"requests made: {report.requests_made}")
        for address in report.fetched:
            print(f"  fetched         {address}")
        for address in report.already_stored:
            print(f"  already stored  {address}")
        for address in report.disallowed:
            print(f"  disallowed by robots.txt, not requested  {address}")
        for address in report.no_robots:
            print(f"  no robots.txt, so nothing is disallowed  {address}")
        for code in report.unknown_subjects:
            print(f"  no link on the index page for subject {code}")
        for address, why in report.failed:
            print(f"  COULD NOT GET   {address}  ({why})")
        return 1 if report.failed or report.unknown_subjects else 0

    if args.command == "extract":
        from .extract import run_extract

        return run_extract(
            data=args.data,
            rules_dir=args.rules,
            reference_dir=args.reference,
            subjects=tuple(s.strip().upper() for s in args.subjects.split(",")),
            language_model=args.language_model,
        )
    return 2


if __name__ == "__main__":
    sys.exit(main())
