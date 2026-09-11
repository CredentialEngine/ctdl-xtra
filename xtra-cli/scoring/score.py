#!/usr/bin/env python3
"""Stage 5. course score: compare extractor dumps to a pack.

  python3 xtra-cli/xtra_cli.py course score --reference DIR --candidate DIR
  python3 xtra-cli/scoring/score.py --reference DIR --candidate DIR

Wraps xtra-accuracy. --golden is a deprecated alias and still forwarded to
xtra_accuracy (that flag belongs to the other package). Forwarding disappears
when the scorer moves under scoring/.
Do not pass --signed-only unless two named humans have already signed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _boot  # noqa: E402,F401

# xTRA-Scoring only loads JSON from these class folders under --golden.
_SCORER_CLASS_DIRS = (
    "courses",
    "learning_programs",
    "competencies",
    "credentials",
)


def _pack_root_for_scorer(reference: str) -> str:
    """If DIR is a class folder, pass its pack. Keep the caller's path form (relative stays relative)."""
    path = Path(reference)
    if path.name in _SCORER_CLASS_DIRS:
        path = path.parent
    if path.is_absolute():
        return str(path)
    return path.as_posix()


def _invoke_accuracy(accuracy_main, argv: list[str]) -> int:
    try:
        result = accuracy_main(argv)
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        return 1
    if result is None:
        return 0
    return int(result)


def _accuracy_main():
    try:
        from xtra_accuracy.cli import main as accuracy_main
    except ImportError:
        print(
            "course score needs the xtra_accuracy package on PYTHONPATH "
            "(Windows: set PYTHONPATH=C:\\Code\\xTRA-Scoring). "
            "In-repo src/ is a fallback only and must not shadow that checkout.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return accuracy_main


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--reference",
        help=(
            "Pack directory (courses/ inside it) or a class folder of scoring JSON. "
            "Forwarded to xtra_accuracy as --golden."
        ),
    )
    parser.add_argument(
        "--golden",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--candidate", help="Directory of extractor JSON files")
    parser.add_argument("--signed-only", action="store_true")
    parser.add_argument(
        "--catalogue-type",
        choices=[
            "COURSES",
            "LEARNING_PROGRAMS",
            "COMPETENCIES",
            "CREDENTIALS",
            "COMPETENCY_FRAMEWORKS",
            "LINKS",
        ],
    )
    parser.add_argument("--pile")
    parser.add_argument("--runs", help="For determinism: directory of JSON files, one per run")
    if argv and argv[0] in {"score", "determinism"}:
        return _invoke_accuracy(_accuracy_main(), argv)
    args, extra = parser.parse_known_args(argv)
    accuracy_main = _accuracy_main()
    if args.runs:
        return _invoke_accuracy(accuracy_main, ["determinism", "--runs", args.runs, *extra])
    reference = args.reference or args.golden
    if args.golden and not args.reference:
        print(
            "warning: --golden is deprecated; use --reference",
            file=sys.stderr,
        )
    if not reference or not args.candidate:
        parser.error("need --reference and --candidate, or --runs for determinism")
    reference = _pack_root_for_scorer(reference)
    # Forward --golden to xtra_accuracy. Remove when the scorer lives under scoring/.
    passthrough = ["score", "--golden", reference, "--candidate", args.candidate]
    if args.signed_only:
        passthrough.append("--signed-only")
    if args.catalogue_type:
        passthrough += ["--catalogue-type", args.catalogue_type]
    if args.pile:
        passthrough += ["--pile", args.pile]
    passthrough.extend(extra)
    return _invoke_accuracy(accuracy_main, passthrough)


if __name__ == "__main__":
    raise SystemExit(main())
