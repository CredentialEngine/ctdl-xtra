"""CLI: freeze, normalize, build, hydrate, validate, assemble."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from config import NORMALIZED_DIR, PACK, RECORD_DIR, SNAPSHOT_DIR
from freeze import freeze_all, meta_path, snapshot_path
from inventory import csv_text as inventory_csv
from normalize import normalize_html, sha256_bytes, sha256_text
from active import unique_pages
from validate import validate_pack, validate_record


def cmd_freeze(_: argparse.Namespace) -> int:
    report = freeze_all()
    print(json.dumps({k: len(v) if isinstance(v, list) else v for k, v in report.items()}, indent=2))
    failed = [row for row in report.get("fetched", []) if row.get("status") != "ok"]
    return 1 if failed else 0


def cmd_normalize(_: argparse.Namespace) -> int:
    NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for slot in unique_pages():
        snap = snapshot_path(slot.stem)
        if not snap.is_file():
            print(f"missing snapshot {snap}", file=sys.stderr)
            return 1
        html = snap.read_text(encoding="utf-8", errors="replace")
        text = normalize_html(html)
        dest = NORMALIZED_DIR / f"{slot.stem}.txt"
        dest.write_text(text, encoding="utf-8")
        meta = {}
        mp = meta_path(slot.stem)
        if mp.is_file():
            meta = json.loads(mp.read_text(encoding="utf-8"))
        meta["normalized_text_sha256"] = sha256_text(text)
        meta["normalized_chars"] = len(text)
        mp.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        print(f"normalized {slot.stem} chars={len(text)}")
        n += 1
    print(f"normalized {n} pages")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    from build import build_pack

    errors = build_pack()
    for err in errors:
        print(err, file=sys.stderr)
    return 1 if errors else 0


def cmd_hydrate(_: argparse.Namespace) -> int:
    from build import hydrate_pack

    errors = hydrate_pack()
    for err in errors:
        print(err, file=sys.stderr)
    return 1 if errors else 0


def cmd_validate(args: argparse.Namespace) -> int:
    errors = validate_pack(PACK, strict_promotion=args.strict_promotion)
    n = len(list((PACK / "records").glob("*.json")))
    if not errors:
        print(f"ok: {n} candidate records passed runtime checks")
        return 0
    for err in errors:
        print(err, file=sys.stderr)
    return 1


def cmd_assemble(_: argparse.Namespace) -> int:
    from build import assemble_manifest

    path = assemble_manifest()
    print(path)
    return 0


def cmd_registry(_: argparse.Namespace) -> int:
    from registry import lookup_pack

    rows = lookup_pack()
    print(json.dumps({"lookups": len(rows)}, indent=2))
    return 0


def cmd_write_inventory(args: argparse.Namespace) -> int:
    dest = Path(args.out)
    dest.write_text(inventory_csv(), encoding="utf-8")
    print(dest)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Golden-set v4 candidate tooling")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("freeze", help="Copy existing HTML and fetch missing URLs")
    sub.add_parser("normalize", help="HTML snapshots -> normalized/*.txt")
    sub.add_parser("build", help="Write candidate JSON from freeze + transcriptions")
    sub.add_parser("hydrate", help="Fill evidence offsets and excerpt hashes")
    val = sub.add_parser("validate", help="Runtime + schema-shaped checks")
    val.add_argument(
        "--strict-promotion",
        action="store_true",
        help="Fail on signed-gold gates (reviewers, template 5-10). Default is candidate gates.",
    )
    sub.add_parser("assemble", help="Write MANIFEST.json and xTRA scoring goldens")
    sub.add_parser("registry", help="Exact ceterms:subjectWebpage Registry lookup")
    inv = sub.add_parser("write-inventory", help="Write FIELD_INVENTORY.csv")
    inv.add_argument("--out", default=str(PACK / "FIELD_INVENTORY.csv"))
    args = parser.parse_args(argv)
    fn = {
        "freeze": cmd_freeze,
        "normalize": cmd_normalize,
        "build": cmd_build,
        "hydrate": cmd_hydrate,
        "validate": cmd_validate,
        "assemble": cmd_assemble,
        "registry": cmd_registry,
        "write-inventory": cmd_write_inventory,
    }[args.cmd]
    return fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
