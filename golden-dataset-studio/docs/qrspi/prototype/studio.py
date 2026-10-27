"""Shared bits for the throwaway Golden Dataset Studio prototype.

Paths of the example storage root, and a DuckDB connection with one view per table of
spec §4.1. DuckDB is only a query library here: every view reads the Parquet / JSON /
JSONL files in place, nothing is stored in a database file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

SCRATCH = Path(
    "/private/tmp/claude-501/-Users-eric--superset-worktrees-ctdl-xtra-glowing-conchoraptor-79248126/"
    "9a24ca32-87da-41f1-8d05-111d893d1142/scratchpad/studio-example"
)
ROOT = Path(os.environ.get("GOLDEN_DATASETS_ROOT", SCRATCH / "root"))
MIRROR = Path.home() / "review-ui-v3-data" / "xtra-cli-output"

CATALOG = "avc-elumenapp-com-catalog-2026-27-welcome"
CRAWL = "2026-10-12T20-59-13Z"
STUDIO = "golden-dataset-studio"  # folder name used at every level of the layout


def catalog_dir(catalog: str = CATALOG) -> Path:
    return ROOT / catalog / STUDIO


def crawl_dir(catalog: str = CATALOG, crawl: str = CRAWL) -> Path:
    return ROOT / catalog / crawl / STUDIO


def extraction_dir(ext: str, catalog: str = CATALOG, crawl: str = CRAWL) -> Path:
    return crawl_dir(catalog, crawl) / "extractions" / ext


def manifest() -> dict:
    return json.loads((ROOT / STUDIO / "manifest.json").read_text())


def connect(catalog: str = CATALOG):
    """DuckDB in-memory connection with views over the files the manifest lists."""
    import duckdb

    con = duckdb.connect()
    man = manifest()
    cat = next(c for c in man["catalogs"] if c["catalog"] == catalog)
    crawl = cat["crawls"][0]
    exts = crawl["extractions"]

    def union(table: str) -> str:
        parts = [
            f"SELECT '{e['extraction']}' AS extraction, * FROM read_parquet('{ROOT / e['path'] / (table + '.parquet')}')"
            for e in exts
        ]
        return " UNION ALL BY NAME ".join(parts)

    con.execute(f"CREATE VIEW pages AS SELECT * FROM read_parquet('{ROOT / crawl['pages']}')")
    for table in ("page_labels", "occurrences", "matches", "signals"):
        con.execute(f"CREATE VIEW {table} AS {union(table)}")
    con.execute(
        "CREATE VIEW extractions AS SELECT * FROM read_json(["
        + ",".join(f"'{ROOT / e['path'] / 'extraction.json'}'" for e in exts)
        + "], union_by_name=true)"
    )
    con.execute(
        "CREATE VIEW rule_versions AS SELECT * FROM read_json(["
        + ",".join(f"'{ROOT / p}'" for p in cat["rule_versions"])
        + "], union_by_name=true, maximum_object_size=10000000)"
    )
    con.execute(
        "CREATE VIEW rulesets AS SELECT * FROM read_json(["
        + ",".join(f"'{ROOT / r['path']}'" for r in cat["rulesets"])
        + "], union_by_name=true)"
    )
    con.execute(
        "CREATE VIEW ruleset_rules AS SELECT r.version AS ruleset_version, u.rule_id, u.kind, "
        "u.version AS rule_version, u.content_hash FROM rulesets r, UNNEST(r.rules) AS t(u)"
    )
    ann = ROOT / cat["annotations"]
    con.execute(
        f"""CREATE VIEW annotations AS SELECT * FROM read_json('{ann}', format='newline_delimited',
        columns={{'annotation_id':'VARCHAR', 'type':'VARCHAR', 'at':'VARCHAR', 'author':'VARCHAR', 'catalog':'VARCHAR',
        'crawl':'VARCHAR', 'target':'STRUCT(kind VARCHAR, rule_id VARCHAR, rule_version_seen INTEGER,
        extraction_seen VARCHAR, occurrence_key VARCHAR, course_key VARCHAR, page_stem VARCHAR,
        value_index INTEGER, value_seen VARCHAR)', 'verdict':'VARCHAR',
        'expected':'STRUCT(text VARCHAR, css_path VARCHAR, char_start INTEGER, char_end INTEGER,
        quote STRUCT(prefix VARCHAR, exact VARCHAR, suffix VARCHAR), located_by VARCHAR, author VARCHAR)',
        'note':'VARCHAR', 'supersedes':'VARCHAR', 'imported_from':'JSON'}})"""
    )
    if crawl.get("golden"):
        con.execute(
            "CREATE VIEW lineage AS "
            + " UNION ALL BY NAME ".join(
                f"SELECT * FROM read_parquet('{ROOT / g['path'] / 'lineage.parquet'}')" for g in crawl["golden"]
            )
        )
    return con
