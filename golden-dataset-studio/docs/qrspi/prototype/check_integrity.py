"""Check every primary and foreign key of spec §4.1 over the example storage root.

Each check is one SQL query that returns the violating rows; zero rows = pass. This is what
`golden-datasets check` would run (and `extract` / `publish` before they write). Exit code 1 on any failure.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import studio  # noqa: E402
from studio import ROOT  # noqa: E402

sys.path.insert(0, str(HERE))


def pk(table: str, cols: str) -> str:
    return f"SELECT {cols}, count(*) n FROM {table} GROUP BY ALL HAVING n > 1"


CHECKS: list[tuple[str, str, str, str]] = [
    # (table, kind, description, sql returning violations)
    # --- rule versions / rulesets
    ("rule_version", "PK", "(catalog, rule_id, version) unique", pk("rule_versions", "catalog, rule_id, version")),
    ("rule_version", "FK", "depends_on → rule ids in every ruleset that lists the rule",
     """SELECT rr.ruleset_version, rv.rule_id, d.dep FROM ruleset_rules rr
        JOIN rule_versions rv ON rv.rule_id = rr.rule_id AND rv.version = rr.rule_version,
        UNNEST(rv.depends_on) AS d(dep)
        WHERE d.dep NOT IN (SELECT rule_id FROM ruleset_rules x WHERE x.ruleset_version = rr.ruleset_version)"""),
    ("ruleset_version", "PK", "(catalog, version) unique", pk("rulesets", "catalog, version")),
    ("ruleset_version", "FK", "rules[] → rule_version (rule_id, version, content_hash)",
     """SELECT rr.* FROM ruleset_rules rr LEFT JOIN rule_versions rv
        ON rv.rule_id = rr.rule_id AND rv.version = rr.rule_version AND rv.content_hash = rr.content_hash
        WHERE rv.rule_id IS NULL"""),
    ("ruleset_version", "FK", "parent_version → ruleset_version",
     "SELECT version FROM rulesets WHERE parent_version IS NOT NULL AND parent_version NOT IN (SELECT version FROM rulesets)"),
    # --- pages and assets
    ("pages", "PK", "(crawl, page_stem) unique", pk("pages", "crawl, page_stem")),
    ("page_assets", "PK", "(crawl, page_stem, url) unique", pk("page_assets", "crawl, page_stem, url")),
    ("page_assets", "FK", "page_stem → pages",
     "SELECT * FROM page_assets WHERE (crawl, page_stem) NOT IN (SELECT (crawl, page_stem) FROM pages)"),
    ("page_assets", "FK", "url → assets", "SELECT DISTINCT url FROM page_assets WHERE url NOT IN (SELECT url FROM assets)"),
    ("assets", "PK", "(crawl, url) unique", pk("assets", "crawl, url")),
    # --- extractions
    ("extraction", "PK", "(crawl, ruleset_version) unique", pk("extractions", "crawl, ruleset_version")),
    ("extraction", "FK", "ruleset_version → ruleset_version",
     "SELECT extraction FROM extractions WHERE ruleset_version NOT IN (SELECT version FROM rulesets)"),
    ("extraction", "FK", "parent_extraction → extraction",
     "SELECT extraction FROM extractions WHERE parent_extraction IS NOT NULL AND parent_extraction NOT IN (SELECT extraction FROM extractions)"),
    ("page_labels", "PK", "(extraction, page_stem, rule_id) unique", pk("page_labels", "extraction, page_stem, rule_id")),
    ("page_labels", "FK", "page_stem → pages", "SELECT * FROM page_labels WHERE page_stem NOT IN (SELECT page_stem FROM pages)"),
    ("page_labels", "FK", "(rule_id, rule_version) → page rule in the extraction's ruleset",
     """SELECT l.* FROM page_labels l JOIN extractions e USING (extraction) LEFT JOIN ruleset_rules rr
        ON rr.ruleset_version = e.ruleset_version AND rr.rule_id = l.rule_id AND rr.rule_version = l.rule_version AND rr.kind = 'page'
        WHERE rr.rule_id IS NULL"""),
    ("occurrences", "PK", "(extraction, occurrence_key) unique", pk("occurrences", "extraction, occurrence_key")),
    ("occurrences", "FK", "page_stem → pages; key = page_stem@css_path",
     """SELECT * FROM occurrences WHERE page_stem NOT IN (SELECT page_stem FROM pages)
        OR occurrence_key <> page_stem || '@' || css_path"""),
    ("occurrences", "FK", "(locator_rule_id, version) → locator in the extraction's ruleset",
     """SELECT o.* FROM occurrences o JOIN extractions e USING (extraction) LEFT JOIN ruleset_rules rr
        ON rr.ruleset_version = e.ruleset_version AND rr.rule_id = o.locator_rule_id
        AND rr.rule_version = o.locator_rule_version AND rr.kind = 'locator' WHERE rr.rule_id IS NULL"""),
    ("occurrences", "FK", "page_rule_id matched that page (page_labels)",
     """SELECT o.* FROM occurrences o LEFT JOIN page_labels l ON l.extraction = o.extraction
        AND l.page_stem = o.page_stem AND l.rule_id = o.page_rule_id AND l.matched WHERE l.rule_id IS NULL"""),
    ("matches", "PK", "(extraction, rule_id, occurrence_key, value_index) unique",
     pk("matches", "extraction, rule_id, occurrence_key, value_index")),
    ("matches", "FK", "occurrence_key → occurrences (same extraction), same page and course_key",
     """SELECT m.* FROM matches m LEFT JOIN occurrences o ON o.extraction = m.extraction
        AND o.occurrence_key = m.occurrence_key WHERE o.occurrence_key IS NULL OR o.page_stem <> m.page_stem
        OR o.course_key IS DISTINCT FROM m.course_key"""),
    ("matches", "FK", "(rule_id, rule_version) → field rule in the extraction's ruleset",
     """SELECT m.rule_id, m.rule_version, count(*) FROM matches m JOIN extractions e USING (extraction)
        LEFT JOIN ruleset_rules rr ON rr.ruleset_version = e.ruleset_version AND rr.rule_id = m.rule_id
        AND rr.rule_version = m.rule_version AND rr.kind = 'field' WHERE rr.rule_id IS NULL GROUP BY ALL"""),
    ("matches", "FK", "field rule's locator = occurrence's locator",
     """SELECT m.rule_id, o.locator_rule_id FROM matches m JOIN occurrences o USING (extraction, occurrence_key)
        JOIN rule_versions rv ON rv.rule_id = m.rule_id AND rv.version = m.rule_version
        WHERE rv.definition.locator <> o.locator_rule_id"""),
    ("matches", "CHK", "status ∈ found/empty/no_match; found ⇔ value present",
     """SELECT * FROM matches WHERE status NOT IN ('found','empty','no_match')
        OR (status = 'found') <> (value IS NOT NULL)"""),
    ("signals", "PK", "(extraction, target, signal, location) unique",
     pk("signals", "extraction, target_kind, rule_id, occurrence_key, value_index, page_stem, signal, css_path, char_start")),
    ("signals", "FK", "match target → matches",
     """SELECT s.* FROM signals s LEFT JOIN matches m ON m.extraction = s.extraction AND m.rule_id = s.rule_id
        AND m.occurrence_key = s.occurrence_key AND m.value_index = s.value_index
        WHERE s.target_kind = 'match' AND m.rule_id IS NULL"""),
    ("signals", "FK", "occurrence target → occurrences",
     """SELECT s.* FROM signals s LEFT JOIN occurrences o ON o.extraction = s.extraction
        AND o.occurrence_key = s.occurrence_key WHERE s.target_kind = 'occurrence' AND o.occurrence_key IS NULL"""),
    ("signals", "FK", "page target → pages",
     "SELECT * FROM signals WHERE target_kind = 'page' AND page_stem NOT IN (SELECT page_stem FROM pages)"),
    # --- annotations
    ("annotations", "PK", "annotation_id unique", pk("annotations", "annotation_id")),
    ("annotations", "FK", "crawl → crawl", "SELECT annotation_id FROM annotations WHERE crawl IS NOT NULL AND crawl NOT IN (SELECT DISTINCT crawl FROM pages)"),
    ("annotations", "FK", "(rule_id, rule_version_seen) → rule_version",
     """SELECT a.annotation_id FROM annotations a LEFT JOIN rule_versions rv ON rv.rule_id = a.target.rule_id
        AND rv.version = a.target.rule_version_seen WHERE a.target.rule_id IS NOT NULL AND rv.rule_id IS NULL"""),
    ("annotations", "FK", "occurrence_key → occurrences of extraction_seen, course_key agrees",
     """SELECT a.annotation_id FROM annotations a LEFT JOIN occurrences o ON o.extraction = a.target.extraction_seen
        AND o.occurrence_key = a.target.occurrence_key WHERE a.target.occurrence_key IS NOT NULL
        AND (o.occurrence_key IS NULL OR o.course_key IS DISTINCT FROM a.target.course_key)"""),
    ("annotations", "FK", "match target → matches of extraction_seen",
     """SELECT a.annotation_id FROM annotations a LEFT JOIN matches m ON m.extraction = a.target.extraction_seen
        AND m.rule_id = a.target.rule_id AND m.occurrence_key = a.target.occurrence_key
        AND m.value_index = a.target.value_index WHERE a.target.kind = 'match' AND m.rule_id IS NULL"""),
    ("annotations", "FK", "page_stem → pages",
     "SELECT annotation_id FROM annotations WHERE target.page_stem IS NOT NULL AND target.page_stem NOT IN (SELECT page_stem FROM pages)"),
    ("annotations", "FK", "supersedes → annotation",
     "SELECT annotation_id FROM annotations WHERE supersedes IS NOT NULL AND supersedes NOT IN (SELECT annotation_id FROM annotations)"),
    ("lineage", "FK", "page_stem → pages", "SELECT * FROM lineage WHERE page_stem NOT IN (SELECT page_stem FROM pages)"),
    ("annotations", "CHK", "verdict ∈ correct/wrong/missing/question for type=verdict",
     "SELECT annotation_id FROM annotations WHERE type = 'verdict' AND verdict NOT IN ('correct','wrong','missing','question')"),
    # --- golden
    ("lineage", "PK", "(publication, golden_id, property, value_index) unique",
     pk("lineage", "publication, golden_id, property, value_index")),
    ("lineage", "FK", "(extraction, rule_id, occurrence_key, match_value_index) → matches, same value",
     """SELECT l.* FROM lineage l LEFT JOIN matches m ON m.extraction = l.extraction AND m.rule_id = l.rule_id
        AND m.occurrence_key = l.occurrence_key AND m.value_index = l.match_value_index WHERE m.rule_id IS NULL"""),
    ("lineage", "FK", "annotation_ids → annotations",
     """SELECT l.golden_id, a.id FROM lineage l, UNNEST(l.annotation_ids) AS a(id)
        WHERE a.id NOT IN (SELECT annotation_id FROM annotations)"""),
]


def file_checks(con) -> list[tuple[str, str, str, int, int]]:
    """Checks that need Python: files exist, hashes recompute, copied rows are identical."""
    out = []
    man = studio.manifest()
    cat = man["catalogs"][0]
    # every path in the manifest exists
    paths = cat["rule_versions"] + [r["path"] for r in cat["rulesets"]] + [cat["annotations"]]
    for crawl in cat["crawls"]:
        paths += [crawl["pages"], crawl["assets"]["assets"], crawl["assets"]["page_assets"]]
        paths += [e["path"] for e in crawl["extractions"]] + [g["path"] for g in crawl["golden"]]
    missing = [p for p in paths if not (ROOT / p).exists()]
    out.append(("manifest", "FK", "every path in manifest.json exists", len(missing), len(paths)))
    # page html files exist (through the symlinked pages/ folder)
    html = [r[0] for r in con.execute("SELECT html_path FROM pages").fetchall()]
    out.append(("pages", "FK", "html_path → saved page file", sum(not (ROOT / h).exists() for h in html), len(html)))
    # asset sha256 → files
    shas = [r[0] for r in con.execute("SELECT sha256 FROM assets WHERE sha256 IS NOT NULL").fetchall()]
    files = ROOT / cat["crawls"][0]["assets"]["files"]
    out.append(("assets", "FK", "sha256 → assets/files/<sha256>", sum(not (files / s).exists() for s in shas), len(shas)))
    # rule content_hash recomputes; file name = version
    import make_example as mk

    bad = 0
    for rs in con.execute("SELECT version FROM rulesets").fetchall():
        _, rules = mk.load_ruleset(rs[0])
        bad += sum(mk.rule_hash(rid, rules) != r["content_hash"] for rid, r in rules.items())
    out.append(("rule_version", "CHK", "content_hash = sha256(definition + dependencies)", bad, len(cat["rule_versions"])))
    # extraction.json file hashes and row counts
    bad = total = 0
    for e in cat["crawls"][0]["extractions"]:
        meta = json.loads((ROOT / e["path"] / "extraction.json").read_text())
        for name, info in meta["files"].items():
            total += 1
            data = (ROOT / e["path"] / name).read_bytes()
            rows = con.execute(f"SELECT count(*) FROM read_parquet('{ROOT / e['path'] / name}')").fetchone()[0]
            bad += hashlib.sha256(data).hexdigest() != info["sha256"] or rows != info["rows"]
    out.append(("extraction", "CHK", "extraction.json files[] sha256 + row counts match", bad, total))
    # copied rules are identical to the parent extraction (rerun scope, spec §4.3)
    for e in cat["crawls"][0]["extractions"]:
        meta = json.loads((ROOT / e["path"] / "extraction.json").read_text())
        if not meta.get("parent_extraction"):
            continue
        p, c = meta["parent_extraction"], meta["extraction"]
        copied = "', '".join(meta["copied_rules"] + [r for r in meta["rerun_rules"] if r not in ("course-description",)])
        n = con.execute(f"""SELECT count(*) FROM (
            (SELECT * EXCLUDE extraction FROM matches WHERE extraction = '{p}' AND rule_id IN ('{copied}')
             EXCEPT SELECT * EXCLUDE extraction FROM matches WHERE extraction = '{c}' AND rule_id IN ('{copied}'))
            UNION ALL
            (SELECT * EXCLUDE extraction FROM matches WHERE extraction = '{c}' AND rule_id IN ('{copied}')
             EXCEPT SELECT * EXCLUDE extraction FROM matches WHERE extraction = '{p}' AND rule_id IN ('{copied}')))""").fetchone()[0]
        total = con.execute(f"SELECT count(*) FROM matches WHERE extraction = '{c}' AND rule_id IN ('{copied}')").fetchone()[0]
        out.append(("matches", "CHK", f"{c}: unchanged rules' rows identical to {p}", n, total))
        for t, k in (("occurrences", "occurrence_key"), ("page_labels", "page_stem, rule_id")):
            n = con.execute(f"""SELECT count(*) FROM (SELECT * EXCLUDE extraction FROM {t} WHERE extraction = '{p}'
                EXCEPT SELECT * EXCLUDE extraction FROM {t} WHERE extraction = '{c}')""").fetchone()[0]
            out.append((t, "CHK", f"{c}: copied {t} identical to {p}", n,
                        con.execute(f"SELECT count(*) FROM {t} WHERE extraction = '{c}'").fetchone()[0]))
    # golden per-page JSON ↔ lineage (xtra-golden-sets-verified shape)
    for g in cat["crawls"][0]["golden"]:
        pub = ROOT / g["path"]
        ids, leaked, n_rec, bad_stem = set(), 0, 0, 0
        for f in sorted(pub.glob("*/*.json")):
            records = json.loads(f.read_text())
            bad_stem += f.parent.name != f.stem or not (f.parent / f"{f.stem}.html").exists()
            for rec in records:
                n_rec += 1
                for i, fld in enumerate(rec["fields"]):
                    ids.add((rec["golden_id"], f.stem, fld["property"], 0))
                leaked += sum(k in ("rule_id", "rule_version", "occurrence_key", "annotation_ids") for fld in rec["fields"] for k in fld)
        lin = set(con.execute(f"SELECT golden_id, page_stem, property, value_index FROM lineage WHERE publication = '{g['publication']}'").fetchall())
        out.append(("lineage", "FK", "every golden value (page JSON) has exactly one lineage row (and back)", len(ids ^ lin), len(ids)))
        out.append(("golden page", "CHK", "<stem>/<stem>.json + <stem>.html per page; stem is a saved page", bad_stem, len(list(pub.glob("*/*.json")))))
        out.append(("golden page", "CHK", "domain-only: no rule ids / occurrence keys / annotation ids", leaked, n_rec))
    return out


def main() -> int:
    t0 = time.perf_counter()
    con = studio.connect()
    cat = studio.manifest()["catalogs"][0]
    a = cat["crawls"][0]["assets"]
    con.execute(f"CREATE VIEW assets AS SELECT * FROM read_parquet('{ROOT / a['assets']}')")
    con.execute(f"CREATE VIEW page_assets AS SELECT * FROM read_parquet('{ROOT / a['page_assets']}')")
    results = []
    for table, kind, desc, sql in CHECKS:
        bad = con.execute(f"SELECT count(*) FROM ({sql})").fetchone()[0]
        base = table if table not in ("rule_version", "ruleset_version", "extraction") else {
            "rule_version": "rule_versions", "ruleset_version": "rulesets", "extraction": "extractions"}[table]
        total = con.execute(f"SELECT count(*) FROM {base}").fetchone()[0]
        results.append((table, kind, desc, bad, total))
    results += file_checks(con)
    width = max(len(r[2]) for r in results)
    print(f"golden-datasets check: {ROOT}")
    print(f"{'table':<16} {'kind':<4} {'check':<{width}} {'rows':>7} {'bad':>4}  result")
    for table, kind, desc, bad, total in results:
        print(f"{table:<16} {kind:<4} {desc:<{width}} {total:>7} {bad:>4}  {'ok' if bad == 0 else 'FAIL'}")
    failed = sum(r[3] > 0 for r in results)
    print(f"\n{len(results)} checks, {failed} failed, {time.perf_counter() - t0:.2f} s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
