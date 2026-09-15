"""CLI: crawl, freeze, normalize, classify, build, hydrate, validate, assemble."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from config import NORMALIZED_DIR, PACK, SLOTS_NAME
from active import active_slots, unique_pages
from freeze import freeze_all, meta_path, snapshot_path
from inventory import csv_text as inventory_csv
from normalize import normalize_html, sha256_text


def _load_url_file(path: Path) -> list[str]:
    urls: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line.split()[0])
    return urls


def _collect_urls(args: argparse.Namespace) -> list[str]:
    urls = list(args.urls or [])
    if args.url_file:
        urls.extend(_load_url_file(Path(args.url_file)))
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def cmd_crawl(args: argparse.Namespace) -> int:
    from college_capture import harvest_seeds
    from dynamic_slots import write_slots

    urls = _collect_urls(args)
    if not urls:
        print("crawl needs --url or --url-file", file=sys.stderr)
        return 2
    all_slots, reports, _want = harvest_seeds(
        urls,
        per_college=args.per_college,
        total_limit=args.limit,
        fetch_all=args.all,
        institution=args.institution,
    )
    if not args.all and args.limit is not None:
        all_slots = all_slots[: args.limit]
    if not all_slots:
        print("no course URLs discovered", file=sys.stderr)
        return 1
    dest = write_slots(all_slots, extra={"discovery": reports})
    print(json.dumps({"slots": len(all_slots), "path": str(dest), "discovery": reports}, indent=2))
    return 0


def cmd_freeze(_: argparse.Namespace) -> int:
    report = freeze_all()
    print(json.dumps({k: len(v) if isinstance(v, list) else v for k, v in report.items()}, indent=2))
    failed = [row for row in report.get("fetched", []) if row.get("status") not in {"ok", "refused"}]
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


def cmd_classify(_: argparse.Namespace) -> int:
    from college_capture import attach_templates
    from dynamic_slots import slots_path, write_slots

    incoming = list(active_slots())
    classified = attach_templates(incoming, NORMALIZED_DIR)
    dropped = max(0, len(incoming) - len(classified))
    extra = {}
    path = slots_path()
    if SLOTS_NAME == "dynamic" and path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        extra = {k: v for k, v in payload.items() if k not in {"schema", "slots"}}
        write_slots(classified, extra=extra or None)
    print(
        json.dumps(
            {
                "classified": len(classified),
                "dropped_unknown_template": dropped,
                "templates": [
                    {
                        "record_id": s.record_id,
                        "url": s.requested_url,
                        "source_family": s.source_family,
                        "template_id": s.template_id,
                    }
                    for s in classified
                ],
            },
            indent=2,
        )
    )
    return 0 if classified else 1


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
    from validate import validate_pack

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


def _add_url_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", action="append", dest="urls", metavar="URL")
    parser.add_argument("--url-file", metavar="PATH")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--per-college", type=int, default=None)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--institution")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Course pack candidate tooling")
    sub = parser.add_subparsers(dest="cmd", required=True)
    crawl = sub.add_parser("crawl", help="Discover course URLs → slots.json")
    _add_url_flags(crawl)
    sub.add_parser("freeze", help="Cache HTML under cache/{yyyy-mm-dd}/; skip existing")
    sub.add_parser("normalize", help="HTML snapshots -> normalized/*.txt")
    sub.add_parser("classify", help="Stamp template_id from freeze text")
    sub.add_parser("build", help="Write candidate JSON from freeze + transcriptions")
    sub.add_parser("hydrate", help="Fill evidence offsets and excerpt hashes")
    val = sub.add_parser("validate", help="Runtime + schema-shaped checks")
    val.add_argument(
        "--strict-promotion",
        action="store_true",
        help="Fail on signed-gold gates (reviewers, template 5-10). Default is candidate gates.",
    )
    sub.add_parser("assemble", help="Write MANIFEST.json and xTRA scoring JSON")
    sub.add_parser("registry", help="Exact ceterms:subjectWebpage Registry lookup")
    inv = sub.add_parser("write-inventory", help="Write FIELD_INVENTORY.csv")
    inv.add_argument("--out", default=str(PACK / "FIELD_INVENTORY.csv"))
    args = parser.parse_args(argv)
    fn = {
        "crawl": cmd_crawl,
        "freeze": cmd_freeze,
        "normalize": cmd_normalize,
        "classify": cmd_classify,
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
