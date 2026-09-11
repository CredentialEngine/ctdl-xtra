#!/usr/bin/env python3
"""Stage 4. course transform: map labels to CTDL JSON-LD and scoring JSON.

  python3 xtra-cli/xtra_cli.py course transform --pack my_pack
  python3 xtra-cli/transformation/transform.py --pack my_pack

Rewrites ctdl_expected from source_expected, writes jsonld/{id}.json (no CTIDs),
and exports courses/*.json for scoring. Does not publish to the Registry.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _boot  # noqa: E402,F401

from _stage import add_pack_flag, configure_pack, run  # noqa: E402


def remap_and_write_jsonld() -> int:
    from config import PACK, RECORD_DIR
    from mapping import map_fields

    if not RECORD_DIR.is_dir():
        print(f"missing {RECORD_DIR}; run extract first", file=sys.stderr)
        return 1
    dest_dir = PACK / "jsonld"
    dest_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for path in sorted(RECORD_DIR.glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        fields = rec.get("source_expected", {}).get("fields") or []
        rec["ctdl_expected"] = map_fields(rec["entity_type"], fields)
        path.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        node = {
            "@context": "https://credreg.net/ctdl/schema/context/json",
            "@type": rec["ctdl_expected"]["class_uri"],
            "ceterms:subjectWebpage": rec["source"]["requested_url"],
        }
        for prop in rec["ctdl_expected"].get("properties") or []:
            node[prop["property"]] = prop["value"]
        # Never invent a CTID. Registry publish is out of scope for this CLI.
        (dest_dir / f"{rec['record_id']}.json").write_text(
            json.dumps(node, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        n += 1
        print(f"jsonld {rec['record_id']}")
    print(json.dumps({"records": n, "jsonld": str(dest_dir)}, indent=2))
    return 0 if n else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_pack_flag(parser)
    args = parser.parse_args(argv)
    configure_pack(args.pack)
    rc = remap_and_write_jsonld()
    if rc != 0:
        return rc
    return run("assemble", [])


if __name__ == "__main__":
    raise SystemExit(main())
