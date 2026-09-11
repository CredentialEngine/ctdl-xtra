#!/usr/bin/env python3
"""xTRA CLI. Same commands for a live extract and for a pack humans later copy.

Noun-verb form: <noun> [<noun>] <verb> [--parameters]
Hidden aliases (old verb-only names) still work.

  python3 xtra-cli/xtra_cli.py catalog crawl --pack my_pack --url https://catalog.brookdalecc.edu --limit 5
  python3 xtra-cli/xtra_cli.py page download --pack my_pack --normalize
  python3 xtra-cli/xtra_cli.py course extract --pack my_pack
  python3 xtra-cli/xtra_cli.py course transform --pack my_pack
  python3 xtra-cli/xtra_cli.py course score --reference PACK --candidate DUMPS
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# (noun, verb) → stage script
NOUN_VERB = {
    ("catalog", "crawl"): HERE / "crawling" / "crawl.py",
    ("page", "download"): HERE / "downloading" / "download.py",
    ("page", "classify"): HERE / "extraction" / "classify.py",
    ("course", "extract"): HERE / "extraction" / "extract.py",
    ("pipeline", "run"): HERE / "extraction" / "run.py",
    ("course", "transform"): HERE / "transformation" / "transform.py",
    ("course", "score"): HERE / "scoring" / "score.py",
    ("pack", "check"): HERE / "scoring" / "check.py",
    ("pack", "promote"): HERE / "scoring" / "promote.py",
    ("field", "union"): HERE / "lib" / "union_fields.py",
}

# Hidden aliases so in-flight verb-only calls keep working.
ALIASES = {
    "crawl": ("catalog", "crawl"),
    "download": ("page", "download"),
    "classify": ("page", "classify"),
    "extract": ("course", "extract"),
    "run": ("pipeline", "run"),
    "transform": ("course", "transform"),
    "score": ("course", "score"),
    "check": ("pack", "check"),
    "promote": ("pack", "promote"),
    "union-fields": ("field", "union"),
}

STAGE_HELP = [
    (("catalog", "crawl"), "crawl", "Discover course URLs and write slots.json"),
    (("page", "download"), "download", "Cache HTML under cache/{yyyy-mm-dd}/ (optional --normalize)"),
    (("page", "classify"), "classify", "Stamp CMS family / template_id from freeze text"),
    (("course", "extract"), "extract", "Transcribe printed fields into records/*.json"),
    (("pipeline", "run"), "run", "One-shot catalog crawl through course transform from --url"),
    (("course", "transform"), "transform", "Map labels to CTDL JSON-LD and scoring JSON"),
    (("course", "score"), "score", "Compare extractor dumps to a pack (wraps xtra-accuracy)"),
    (("pack", "check"), "check", "Re-validate a pack (does not sign records)"),
    (("pack", "promote"), "promote", "Copy courses/*.json to another folder (still unsigned)"),
    (("field", "union"), "union-fields", "Count inventory labels across catalogs or packs"),
]


def _run(script: Path, rest: list[str]) -> int:
    sys.argv = [str(script), *rest]
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        return 1
    return 0


def print_help() -> None:
    print("usage: xtra-cli [-h] <noun> <verb> [options]")
    print()
    print("xTRA ETL. Same scripts for extract and for packs later copied into a")
    print("golden folder after human review. Golden is that folder, not a code path.")
    print()
    print("Commands (hidden alias in parentheses still works):")
    for (noun, verb), alias, help_text in STAGE_HELP:
        label = f"{noun} {verb}"
        print(f"  {label:<22} ({alias:<12}) {help_text}")
    print()
    print("Or run a stage file: python3 xtra-cli/crawling/crawl.py ...")


def _resolve(argv: list[str]) -> tuple[Path, list[str]] | None:
    if len(argv) >= 2 and (argv[0], argv[1]) in NOUN_VERB:
        return NOUN_VERB[(argv[0], argv[1])], argv[2:]
    if argv and argv[0] in ALIASES:
        return NOUN_VERB[ALIASES[argv[0]]], argv[1:]
    return None


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        print_help()
        return 0 if argv else 2
    resolved = _resolve(argv)
    if resolved is None:
        print_help()
        print(f"\nunknown command: {' '.join(argv[:2])}", file=sys.stderr)
        return 2
    script, rest = resolved
    return _run(script, rest)


if __name__ == "__main__":
    raise SystemExit(main())
