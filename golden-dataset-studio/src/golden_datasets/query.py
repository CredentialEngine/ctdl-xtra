"""DuckDB as an in-process query library over one catalog's files (spec §4, §5.8). There is no database file.

Views (every path comes from the manifest; files are read from the local disk cache):

    pages, assets, page_assets
    rule_versions (every version), rulesets, ruleset_rules (ruleset_version × rule), rules (the latest ruleset's)
    extractions
    page_labels, occurrences, raw_matches, matches (+ record_external_identifier from occurrences), signals   — all extractions,
        with an `extraction` column; `*_latest` views hold only the latest extraction
    annotations (annotations.jsonl)
    lineage (every golden publication)

Every view after the assets is per class: it has a `class` column, and `sql` holds every class the catalog has.
"""

from __future__ import annotations

import json
import sys

import duckdb
import pyarrow as pa

from . import layout, model
from .context import Ctx

ANNOTATION_COLUMNS = """{'annotation_id':'VARCHAR', 'type':'VARCHAR', 'at':'VARCHAR', 'author':'VARCHAR',
 'catalog':'VARCHAR', 'crawl':'VARCHAR',
 'target':'STRUCT(kind VARCHAR, rule_id VARCHAR, rule_version_seen INTEGER, extraction_seen VARCHAR,
   occurrence_key VARCHAR, record_external_identifier VARCHAR, page_stem VARCHAR, value_index INTEGER, value_seen VARCHAR,
   item BOOLEAN)',
 'verdict':'VARCHAR',
 'expected':'STRUCT(text VARCHAR, css_path VARCHAR, char_start INTEGER, char_end INTEGER,
   quote STRUCT(prefix VARCHAR, exact VARCHAR, suffix VARCHAR), located_by VARCHAR, author VARCHAR,
   segments STRUCT(text VARCHAR, css_path VARCHAR, char_start INTEGER, char_end INTEGER, polarity VARCHAR)[],
   objects JSON)',
 'anchor':'STRUCT(css_path VARCHAR, char_start INTEGER, char_end INTEGER, text VARCHAR)',
 'note':'VARCHAR', 'supersedes':'VARCHAR', 'imported_from':'JSON',
 'reasons':'VARCHAR[]'}"""


def _q(path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def rule_versions_table(ctx: Ctx) -> pa.Table:
    rows = []
    for path in ctx.class_entry().get("rule_versions", []):
        r = model.current_kind(ctx.read_json(path))
        rows.append({"class": ctx.cls, "catalog": r.get("catalog"), "rule_id": r["rule_id"], "version": r["version"],
                     "kind": r["kind"], "parent_version": r.get("parent_version"),
                     "ctdl_property": r.get("ctdl_property"), "property_label": r.get("property_label"),
                     "locator": r["definition"].get("locator"), "rule_type": r["definition"].get("rule_type"),
                     "definition": json.dumps(r["definition"]), "what": r.get("what"), "how": r.get("how"),
                     "why": r.get("why"), "depends_on": r.get("depends_on", []), "content_hash": r["content_hash"],
                     "path": path})
    schema = pa.schema([("class", pa.string()), ("catalog", pa.string()), ("rule_id", pa.string()),
                        ("version", pa.int32()), ("kind", pa.string()), ("parent_version", pa.int32()),
                        ("ctdl_property", pa.string()), ("property_label", pa.string()), ("locator", pa.string()),
                        ("rule_type", pa.string()), ("definition", pa.string()), ("what", pa.string()),
                        ("how", pa.string()), ("why", pa.string()), ("depends_on", pa.list_(pa.string())),
                        ("content_hash", pa.string()), ("path", pa.string())])
    return pa.Table.from_pylist(rows, schema=schema)


#: The views each class has; `connect` makes each one the union over the classes, with a `class` column.
CLASS_VIEWS = ("rule_versions", "rulesets", "ruleset_rules", "rules", "extractions", "page_labels", "occurrences",
               "raw_matches", "matches", "signals", "page_labels_latest", "occurrences_latest", "matches_latest",
               "signals_latest", "annotations", "lineage")


def connect(ctx: Ctx, classes: list[str] | None = None) -> duckdb.DuckDBPyConnection:
    """The views over one catalog and crawl: the pages and assets, then every class view (`CLASS_VIEWS`) over
    `classes` (default: the context's class), each row with its `class`."""
    con = duckdb.connect()
    k = ctx.crawl_entry()
    con.execute(f"CREATE VIEW pages AS SELECT * FROM read_parquet({_q(ctx.root.local_path(k['pages']))})")
    assets = k.get("assets") or {}
    for name in ("assets", "page_assets"):
        if assets.get(name):
            con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet("
                        f"{_q(ctx.root.local_path(assets[name], mutable=True))})")  # rewritten by assets fetch
    made: dict[str, list[str]] = {v: [] for v in CLASS_VIEWS}
    for cls in classes or [ctx.cls]:
        c = Ctx(ctx.root, ctx.catalog, ctx.crawl, cls=cls)
        for view in _class_views(c, con):
            made[view].append(f"SELECT {_q(cls)} AS class, * FROM {view}__{cls}")
    for view, parts in made.items():
        if parts:
            con.execute(f"CREATE VIEW {view} AS " + " UNION ALL BY NAME ".join(parts))
    return con


def _class_views(ctx: Ctx, con: duckdb.DuckDBPyConnection) -> list[str]:
    """One class's views, named `<view>__<class>`; returns the views it made."""
    sfx = f"__{ctx.cls}"
    made = []
    rv = rule_versions_table(ctx)
    con.register(f"rule_versions{sfx}", rv.drop(["class"]))
    rulesets, rr = [], []
    for v in ctx.ruleset_versions():
        rs = ctx.ruleset(v)
        rulesets.append({"catalog": rs["catalog"], "version": v, "parent_version": rs.get("parent_version"),
                         "note": rs.get("note"), "published_by": rs.get("published_by"),
                         "published_at": rs.get("published_at"), "settings": json.dumps(rs["settings"]),
                         "changed_rules": rs.get("changed_rules", [])})
        rr += [{"ruleset_version": v, "rule_id": e["rule_id"], "kind": e["kind"], "rule_version": e["version"],
                "content_hash": e["content_hash"]} for e in rs["rules"]]
    con.register(f"rulesets{sfx}", pa.Table.from_pylist(rulesets, schema=pa.schema([
        ("catalog", pa.string()), ("version", pa.int32()), ("parent_version", pa.int32()), ("note", pa.string()),
        ("published_by", pa.string()), ("published_at", pa.string()), ("settings", pa.string()),
        ("changed_rules", pa.list_(pa.string()))])))
    con.register(f"ruleset_rules{sfx}", pa.Table.from_pylist(rr, schema=pa.schema([
        ("ruleset_version", pa.int32()), ("rule_id", pa.string()), ("kind", pa.string()),
        ("rule_version", pa.int32()), ("content_hash", pa.string())])))
    latest_rs = max((r["version"] for r in rulesets), default=0)
    con.execute(f"""CREATE VIEW rules{sfx} AS SELECT rv.* FROM rule_versions{sfx} rv JOIN ruleset_rules{sfx} rr
                    ON rr.rule_id = rv.rule_id AND rr.rule_version = rv.version WHERE rr.ruleset_version = {latest_rs}""")
    made += ["rule_versions", "rulesets", "ruleset_rules", "rules"]

    exts = ctx.extractions()
    metas = [ctx.extraction_meta(e["extraction"]) for e in exts]
    con.register(f"extractions{sfx}", pa.Table.from_pylist(
        [{"extraction": m["extraction"], "crawl": m["crawl"], "ruleset_version": m["ruleset_version"],
          "parent_extraction": m.get("parent_extraction"), "created_at": m.get("created_at"),
          "rerun_rules": m.get("rerun_rules", []), "copied_rules": m.get("copied_rules", []),
          "files": json.dumps(m.get("files", {}))} for m in metas],
        schema=pa.schema([("extraction", pa.string()), ("crawl", pa.string()), ("ruleset_version", pa.int32()),
                          ("parent_extraction", pa.string()), ("created_at", pa.string()),
                          ("rerun_rules", pa.list_(pa.string())), ("copied_rules", pa.list_(pa.string())),
                          ("files", pa.string())])))
    made.append("extractions")
    latest = ctx.latest_extraction() if exts else None
    from .model import TABLE_SCHEMAS

    for table in layout.EXTRACTION_TABLES:
        name = "raw_matches" if table == "matches" else table
        parts = [f"SELECT {_q(e['extraction'])} AS extraction, * FROM read_parquet("
                 f"{_q(ctx.root.local_path(layout.extraction_file(ctx.catalog, ctx.crawl, ctx.cls, e['extraction'], table)))})"
                 for e in exts]
        if parts:
            con.execute(f"CREATE VIEW {name}{sfx} AS " + " UNION ALL BY NAME ".join(parts))
        else:  # an empty view with the right columns
            con.register(f"_{name}_empty{sfx}", pa.Table.from_pylist([], schema=TABLE_SCHEMAS[table]))
            con.execute(f"CREATE VIEW {name}{sfx} AS SELECT NULL::VARCHAR AS extraction, * FROM _{name}_empty{sfx}")
        made.append(name)
    con.execute(f"""CREATE VIEW matches{sfx} AS SELECT m.*, o.record_external_identifier FROM raw_matches{sfx} m
                    LEFT JOIN occurrences{sfx} o USING (extraction, occurrence_key)""")
    made.append("matches")
    for table in ("page_labels", "occurrences", "matches", "signals"):
        con.execute(f"CREATE VIEW {table}_latest{sfx} AS SELECT * EXCLUDE (extraction) FROM {table}{sfx} "
                    f"WHERE extraction = {_q(latest or '')}")
        made.append(f"{table}_latest")

    ann_path = layout.annotations(ctx.catalog, ctx.cls)
    if ctx.root.exists(ann_path):
        local = ctx.root.local_path(ann_path, mutable=True)
        con.execute(f"""CREATE VIEW annotations{sfx} AS SELECT * FROM read_json({_q(local)},
                        format='newline_delimited', columns={ANNOTATION_COLUMNS})""")
    else:
        con.execute(f"""CREATE VIEW annotations{sfx} AS SELECT NULL::VARCHAR annotation_id, NULL::VARCHAR type,
                       NULL::VARCHAR verdict, NULL::VARCHAR crawl, NULL::VARCHAR supersedes,
                       NULL::STRUCT(kind VARCHAR, rule_id VARCHAR, rule_version_seen INTEGER, extraction_seen VARCHAR,
                       occurrence_key VARCHAR, record_external_identifier VARCHAR, page_stem VARCHAR,
                       value_index INTEGER, value_seen VARCHAR, item BOOLEAN) target WHERE false""")
    made.append("annotations")
    import pyarrow.parquet as pq

    lineage = []
    for g in ctx.crawl_class().get("golden") or []:
        if not ctx.root.exists(g["path"] + "/lineage.parquet"):
            continue
        local = ctx.root.local_path(g["path"] + "/lineage.parquet", mutable=True)  # a version is rewritten per column
        # publications before the rename call the record id golden_id
        old = "golden_id" in pq.read_schema(local).names
        lineage.append(f"SELECT *{' RENAME (golden_id AS golden_record_id)' if old else ''} FROM read_parquet({_q(local)})")
    if lineage:
        con.execute(f"CREATE VIEW lineage{sfx} AS " + " UNION ALL BY NAME ".join(lineage))
        made.append("lineage")
    return made


def cmd_sql(args) -> int:
    """Every class's data, each row with its `class` (sql takes no --class: approved item 19)."""
    from . import classes, manifest

    ctx = Ctx.from_args(args)
    have = [c for c in classes.SLUGS if manifest.has_rules(ctx.entry() or {}, c)]
    con = connect(ctx, have or [ctx.cls])
    rel = con.sql(args.query)
    if rel is None:
        return 0
    if args.format == "csv":
        rel.write_csv("/dev/stdout")
    elif args.format == "json":
        cols = rel.columns
        for row in rel.fetchall():
            print(json.dumps(dict(zip(cols, row)), ensure_ascii=False, default=str))
    else:
        rel.show(max_width=sys.maxsize if not sys.stdout.isatty() else 200, max_rows=200)
    return 0
