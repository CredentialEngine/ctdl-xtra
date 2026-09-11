#!/usr/bin/env python3
"""page classify: stamp CMS family and extractor template on cached pages.

Family detection during catalog crawl still uses catalog.py.

  python3 xtra-cli/xtra_cli.py page classify --pack my_pack
  python3 xtra-cli/extraction/classify.py --url https://catalog.brookdalecc.edu/courses/ENGL121

With --pack: stamps template_id onto every slot and drops unknown layouts.
With --url: fetches one page and prints its family only. No pack, no writes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _boot  # noqa: E402,F401

from _stage import configure_pack, run  # noqa: E402


def probe_one(url: str) -> int:
    """Family only, from a single live page. Does not touch a pack."""
    from catalog import detect_family, is_course_detail_url

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("probing a URL needs playwright: pip install playwright", file=sys.stderr)
        return 2
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="load", timeout=60000)
        html = page.content()
        browser.close()
    family = detect_family(html, url)
    print(
        json.dumps(
            {
                "url": url,
                "family": family,
                "is_course_detail_url": is_course_detail_url(url, family),
                "note": "family only; template is decided from the cached freeze text",
            },
            indent=2,
        )
    )
    return 0 if family != "unknown" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pack", metavar="DIR", help="Classify every slot in this pack")
    parser.add_argument("--url", metavar="URL", help="Probe one live page for its family")
    args = parser.parse_args(argv)
    if bool(args.pack) == bool(args.url):
        parser.error("pass exactly one of --pack or --url")
    if args.url:
        return probe_one(args.url)
    configure_pack(args.pack)
    return run("classify", [])


if __name__ == "__main__":
    raise SystemExit(main())
