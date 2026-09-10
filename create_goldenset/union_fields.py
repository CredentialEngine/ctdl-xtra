#!/usr/bin/env python3
"""Sept 4 1.c.i — count which inventory labels appear, and which catalogs drop.

Live (Playwright, slow):

  python3 create_goldenset/union_fields.py --url-file create_goldenset/union_fields_urls.txt --limit 5

From an existing pack (no crawl):

  python3 create_goldenset/union_fields.py --from-pack handoff/golden_set_courses_30
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).absolute().parent
ROOT = HERE.parent.absolute()
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from lib import load_url_file, resolve_pack  # noqa: E402


def count_pack(pack: Path) -> dict:
    labels: Counter[str] = Counter()
    templates: Counter[str] = Counter()
    families: Counter[str] = Counter()
    records = 0
    rec_dir = pack / "records"
    if rec_dir.is_dir():
        files = sorted(rec_dir.glob("*.json"))
    else:
        files = []
        for folder in ("courses", "learning_programs", "credentials", "competencies"):
            files.extend(sorted((pack / folder).glob("*.json")))
    for path in files:
        rec = json.loads(path.read_text(encoding="utf-8"))
        records += 1
        src = rec.get("source") or {}
        templates[src.get("template_id") or rec.get("template_id") or "unknown"] += 1
        families[src.get("source_family") or "unknown"] += 1
        fields = (rec.get("source_expected") or {}).get("fields") or []
        if fields:
            for field in fields:
                labels[field["canonical_label"]] += 1
            continue
        expected = rec.get("expected") or {}
        for key in expected:
            labels[key] += 1
    return {
        "pack": str(pack),
        "records": records,
        "label_counts": dict(labels),
        "template_counts": dict(templates),
        "family_counts": dict(families),
    }


def run_one(url: str, *, limit: int) -> dict:
    pack = resolve_pack(None, [url])
    cmd = [
        sys.executable,
        str(HERE / "run.py"),
        "--url",
        url,
        "--limit",
        str(limit),
        "--skip-registry",
        "--allow-errors",
        "--out",
        str(pack),
    ]
    proc = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True)
    row = {
        "url": url,
        "pack": str(pack),
        "returncode": proc.returncode,
        "stderr_tail": "\n".join((proc.stderr or "").splitlines()[-20:]),
        "dropped_unknown": "drop unknown template" in (proc.stderr or ""),
    }
    if pack.is_dir():
        row.update(count_pack(pack))
        slots = pack / "slots.json"
        if slots.is_file():
            payload = json.loads(slots.read_text(encoding="utf-8"))
            row["discovered_slots"] = len(payload.get("slots") or [])
            row["family"] = None
            for item in payload.get("discovery") or []:
                row["family"] = item.get("family")
    else:
        row["records"] = 0
        row["label_counts"] = {}
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Union of course labels across catalogs")
    parser.add_argument("--url", action="append", dest="urls")
    parser.add_argument("--url-file")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--from-pack", action="append", dest="packs")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    reports = []
    if args.packs:
        for pack in args.packs:
            p = Path(pack).expanduser()
            p = p.absolute() if p.is_absolute() else (ROOT / p).absolute()
            reports.append(count_pack(p))
    urls = list(args.urls or [])
    if args.url_file:
        urls.extend(load_url_file(Path(args.url_file)))
    for url in urls:
        print(f"union {url}", flush=True)
        reports.append(run_one(url, limit=args.limit))

    if not reports:
        parser.print_help()
        return 2

    combined: Counter[str] = Counter()
    unknown = []
    for row in reports:
        combined.update(row.get("label_counts") or {})
        if row.get("dropped_unknown") or not row.get("records"):
            unknown.append(row.get("url") or row.get("pack"))

    payload = {
        "catalogs": reports,
        "union_label_counts": dict(combined),
        "unreadable_or_empty": unknown,
    }
    text = json.dumps(payload, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(args.out, file=sys.stderr)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
