"""`golden-datasets check`: every primary key, foreign key and hash of spec §4.1 (spec §5.7).

Each SQL check returns the violating rows (zero rows = pass). `extract` and `rule publish` run
`check_before_write` on the tables they are about to write; `golden publish` runs the lineage checks.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import Counter, defaultdict

from . import layout, manifest, model
from .catalogs import resolve
from .context import Ctx
from .errors import UserError


def pk(table: str, cols: str) -> str:
    return f"SELECT {cols}, count(*) n FROM {table} GROUP BY ALL HAVING n > 1"


SQL_CHECKS: list[tuple[str, str, str, str, str]] = [
    # (table, kind, description, violations SQL, base table for the row count)
    ("rule_version", "PK", "(catalog, rule_id, version) unique", pk("rule_versions", "catalog, rule_id, version"),
     "rule_versions"),
    ("rule_version", "FK", "depends_on → rule ids in every ruleset that lists the rule",
     """SELECT rr.ruleset_version, rv.rule_id, d.dep FROM ruleset_rules rr
        JOIN rule_versions rv ON rv.rule_id = rr.rule_id AND rv.version = rr.rule_version,
        UNNEST(rv.depends_on) AS d(dep)
        WHERE d.dep NOT IN (SELECT rule_id FROM ruleset_rules x WHERE x.ruleset_version = rr.ruleset_version)""",
     "rule_versions"),
    ("ruleset_version", "PK", "(catalog, version) unique", pk("rulesets", "catalog, version"), "rulesets"),
    ("ruleset_version", "FK", "rules[] → rule_version (rule_id, version, content_hash)",
     """SELECT rr.* FROM ruleset_rules rr LEFT JOIN rule_versions rv
        ON rv.rule_id = rr.rule_id AND rv.version = rr.rule_version AND rv.content_hash = rr.content_hash
        WHERE rv.rule_id IS NULL""", "ruleset_rules"),
    ("ruleset_version", "FK", "parent_version → ruleset_version",
     "SELECT version FROM rulesets WHERE parent_version IS NOT NULL AND parent_version NOT IN (SELECT version FROM rulesets)",
     "rulesets"),
    ("pages", "PK", "(crawl, page_stem) unique", pk("pages", "crawl, page_stem"), "pages"),
    ("page_assets", "PK", "(crawl, page_stem, url) unique", pk("page_assets", "crawl, page_stem, url"), "page_assets"),
    ("page_assets", "FK", "page_stem → pages",
     "SELECT * FROM page_assets WHERE (crawl, page_stem) NOT IN (SELECT (crawl, page_stem) FROM pages)", "page_assets"),
    ("page_assets", "FK", "url → assets",
     "SELECT DISTINCT url FROM page_assets WHERE url NOT IN (SELECT url FROM assets)", "page_assets"),
    ("assets", "PK", "(crawl, url) unique", pk("assets", "crawl, url"), "assets"),
    ("extraction", "PK", "extraction unique", pk("extractions", "extraction"), "extractions"),
    ("extraction", "FK", "ruleset_version → ruleset_version",
     "SELECT extraction FROM extractions WHERE ruleset_version NOT IN (SELECT version FROM rulesets)", "extractions"),
    ("extraction", "FK", "parent_extraction → extraction",
     """SELECT extraction FROM extractions WHERE parent_extraction IS NOT NULL
        AND parent_extraction NOT IN (SELECT extraction FROM extractions)""", "extractions"),
    ("page_labels", "PK", "(extraction, page_stem, rule_id) unique", pk("page_labels", "extraction, page_stem, rule_id"),
     "page_labels"),
    ("page_labels", "FK", "page_stem → pages",
     "SELECT * FROM page_labels WHERE page_stem NOT IN (SELECT page_stem FROM pages)", "page_labels"),
    ("page_labels", "FK", "(rule_id, rule_version) → page rule in the extraction's ruleset",
     """SELECT l.* FROM page_labels l JOIN extractions e USING (extraction) LEFT JOIN ruleset_rules rr
        ON rr.ruleset_version = e.ruleset_version AND rr.rule_id = l.rule_id AND rr.rule_version = l.rule_version
        AND rr.kind = 'page' WHERE rr.rule_id IS NULL""", "page_labels"),
    ("page_labels", "CHK", "every page × every page rule of the ruleset, once",
     """SELECT e.extraction, count(*) FROM extractions e JOIN ruleset_rules rr ON rr.ruleset_version = e.ruleset_version
        AND rr.kind = 'page' CROSS JOIN pages p
        LEFT JOIN page_labels l ON l.extraction = e.extraction AND l.rule_id = rr.rule_id AND l.page_stem = p.page_stem
        WHERE l.page_stem IS NULL GROUP BY ALL""", "page_labels"),
    ("occurrences", "PK", "(extraction, occurrence_key) unique", pk("occurrences", "extraction, occurrence_key"),
     "occurrences"),
    ("occurrences", "FK", "page_stem → pages; key = page_stem@css_path",
     """SELECT * FROM occurrences WHERE page_stem NOT IN (SELECT page_stem FROM pages)
        OR occurrence_key <> page_stem || '@' || css_path""", "occurrences"),
    ("occurrences", "FK", "(locator_rule_id, version) → locator in the extraction's ruleset",
     """SELECT o.* FROM occurrences o JOIN extractions e USING (extraction) LEFT JOIN ruleset_rules rr
        ON rr.ruleset_version = e.ruleset_version AND rr.rule_id = o.locator_rule_id
        AND rr.rule_version = o.locator_rule_version AND rr.kind = 'locator' WHERE rr.rule_id IS NULL""", "occurrences"),
    ("occurrences", "FK", "page_rule_id matched that page (page_labels)",
     """SELECT o.* FROM occurrences o LEFT JOIN page_labels l ON l.extraction = o.extraction
        AND l.page_stem = o.page_stem AND l.rule_id = o.page_rule_id AND l.matched WHERE l.rule_id IS NULL""",
     "occurrences"),
    ("matches", "PK", "(extraction, rule_id, occurrence_key, value_index) unique",
     pk("raw_matches", "extraction, rule_id, occurrence_key, value_index"), "raw_matches"),
    ("matches", "FK", "occurrence_key → occurrences (same extraction), same page",
     """SELECT m.* FROM raw_matches m LEFT JOIN occurrences o ON o.extraction = m.extraction
        AND o.occurrence_key = m.occurrence_key WHERE o.occurrence_key IS NULL OR o.page_stem <> m.page_stem""",
     "raw_matches"),
    ("matches", "FK", "(rule_id, rule_version) → field rule in the extraction's ruleset",
     """SELECT m.rule_id, m.rule_version, count(*) FROM raw_matches m JOIN extractions e USING (extraction)
        LEFT JOIN ruleset_rules rr ON rr.ruleset_version = e.ruleset_version AND rr.rule_id = m.rule_id
        AND rr.rule_version = m.rule_version AND rr.kind = 'field' WHERE rr.rule_id IS NULL GROUP BY ALL""",
     "raw_matches"),
    ("matches", "FK", "field rule's locator = occurrence's locator",
     """SELECT m.rule_id, o.locator_rule_id FROM raw_matches m JOIN occurrences o USING (extraction, occurrence_key)
        JOIN rule_versions rv ON rv.rule_id = m.rule_id AND rv.version = m.rule_version
        WHERE rv.locator <> o.locator_rule_id""", "raw_matches"),
    ("matches", "CHK", "every occurrence × every field rule of its locator, once",
     """SELECT o.extraction, o.occurrence_key, rv.rule_id FROM occurrences o JOIN extractions e USING (extraction)
        JOIN ruleset_rules rr ON rr.ruleset_version = e.ruleset_version AND rr.kind = 'field'
        JOIN rule_versions rv ON rv.rule_id = rr.rule_id AND rv.version = rr.rule_version
        AND rv.locator = o.locator_rule_id
        LEFT JOIN raw_matches m ON m.extraction = o.extraction AND m.occurrence_key = o.occurrence_key
        AND m.rule_id = rv.rule_id WHERE m.rule_id IS NULL""", "raw_matches"),
    ("matches", "CHK", "status ∈ found/empty/no_match; found ⇔ value present",
     """SELECT * FROM raw_matches WHERE status NOT IN ('found','empty','no_match')
        OR (status = 'found') <> (value IS NOT NULL)""", "raw_matches"),
    ("matches", "CHK", "css_path is relative to the occurrence; offsets within bounds",
     """SELECT * FROM raw_matches WHERE starts_with(css_path, 'html') OR char_start > char_end OR char_start < 0""",
     "raw_matches"),
    ("signals", "PK", "(extraction, target, signal, location) unique",
     pk("signals", "extraction, target_kind, rule_id, occurrence_key, value_index, page_stem, signal, css_path, char_start"),
     "signals"),
    ("signals", "FK", "match target → matches",
     """SELECT s.* FROM signals s LEFT JOIN raw_matches m ON m.extraction = s.extraction AND m.rule_id = s.rule_id
        AND m.occurrence_key = s.occurrence_key AND m.value_index = s.value_index
        WHERE s.target_kind = 'match' AND m.rule_id IS NULL""", "signals"),
    ("signals", "FK", "occurrence target → occurrences",
     """SELECT s.* FROM signals s LEFT JOIN occurrences o ON o.extraction = s.extraction
        AND o.occurrence_key = s.occurrence_key WHERE s.target_kind = 'occurrence' AND o.occurrence_key IS NULL""",
     "signals"),
    ("signals", "FK", "page target → pages; rule_id → rule in the ruleset (or null)",
     """SELECT s.* FROM signals s JOIN extractions e USING (extraction) WHERE s.target_kind = 'page' AND (
        s.page_stem NOT IN (SELECT page_stem FROM pages) OR (s.rule_id IS NOT NULL AND s.rule_id NOT IN
        (SELECT rule_id FROM ruleset_rules rr WHERE rr.ruleset_version = e.ruleset_version)))""", "signals"),
    ("annotations", "PK", "annotation_id unique", pk("annotations", "annotation_id"), "annotations"),
    ("annotations", "FK", "crawl → crawl",
     "SELECT annotation_id FROM annotations WHERE crawl IS NOT NULL AND crawl NOT IN (SELECT DISTINCT crawl FROM pages)",
     "annotations"),
    ("annotations", "FK", "(rule_id, rule_version_seen) → rule_version",
     """SELECT a.annotation_id FROM annotations a LEFT JOIN rule_versions rv ON rv.rule_id = a.target.rule_id
        AND rv.version = a.target.rule_version_seen WHERE a.target.rule_id IS NOT NULL AND rv.rule_id IS NULL""",
     "annotations"),
    ("annotations", "FK", "occurrence_key → occurrences of extraction_seen, course_key agrees",
     """SELECT a.annotation_id FROM annotations a LEFT JOIN occurrences o ON o.extraction = a.target.extraction_seen
        AND o.occurrence_key = a.target.occurrence_key WHERE a.target.occurrence_key IS NOT NULL
        AND (o.occurrence_key IS NULL OR o.course_key IS DISTINCT FROM a.target.course_key)""", "annotations"),
    ("annotations", "FK", "match target → matches of extraction_seen",
     """SELECT a.annotation_id FROM annotations a LEFT JOIN raw_matches m ON m.extraction = a.target.extraction_seen
        AND m.rule_id = a.target.rule_id AND m.occurrence_key = a.target.occurrence_key
        AND m.value_index = a.target.value_index WHERE a.target.kind = 'match' AND m.rule_id IS NULL""",
     "annotations"),
    ("annotations", "FK", "page_stem → pages",
     """SELECT annotation_id FROM annotations WHERE target.page_stem IS NOT NULL
        AND target.page_stem NOT IN (SELECT page_stem FROM pages)""", "annotations"),
    ("annotations", "FK", "supersedes → annotation",
     """SELECT annotation_id FROM annotations WHERE supersedes IS NOT NULL
        AND supersedes NOT IN (SELECT annotation_id FROM annotations)""", "annotations"),
    ("annotations", "CHK", "type ∈ verdict/comment/approve/reopen; verdict ∈ correct/wrong/missing/question",
     """SELECT annotation_id FROM annotations WHERE type NOT IN ('verdict','comment','approve','reopen')
        OR (type = 'verdict' AND verdict NOT IN ('correct','wrong','missing','question'))
        OR (type <> 'verdict' AND verdict IS NOT NULL)""", "annotations"),
    ("annotations", "CHK", "missing only on record locators and page rules",
     """SELECT annotation_id FROM annotations WHERE verdict = 'missing' AND target.kind NOT IN ('occurrence','page')""",
     "annotations"),
]
LINEAGE_CHECKS = [
    ("lineage", "PK", "(publication, golden_id, page_stem, property, value_index) unique",
     pk("lineage", "publication, golden_id, page_stem, property, value_index"), "lineage"),
    ("lineage", "FK", "page_stem → pages", "SELECT * FROM lineage WHERE page_stem NOT IN (SELECT page_stem FROM pages)",
     "lineage"),
    ("lineage", "FK", "(extraction, rule_id, occurrence_key, match_value_index) → matches",
     """SELECT l.* FROM lineage l LEFT JOIN raw_matches m ON m.extraction = l.extraction AND m.rule_id = l.rule_id
        AND m.occurrence_key = l.occurrence_key AND m.value_index = l.match_value_index WHERE m.rule_id IS NULL""",
     "lineage"),
    ("lineage", "FK", "annotation_ids → annotations",
     """SELECT l.golden_id, a.id FROM lineage l, UNNEST(l.annotation_ids) AS a(id)
        WHERE a.id NOT IN (SELECT annotation_id FROM annotations)""", "lineage"),
]


def _tables(con) -> set[str]:
    return {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}


def file_checks(ctx: Ctx, con) -> list[tuple]:
    """Checks that need Python: files exist, hashes recompute, copied rows are identical, golden files."""
    out = []
    cat = ctx.entry() or {}
    paths = list(cat.get("rule_versions", [])) + [r["path"] for r in cat.get("rulesets", [])]
    if cat.get("annotations"):
        paths.append(cat["annotations"])
    for k in cat.get("crawls", []):
        if k.get("pages"):
            paths.append(k["pages"])
        for name in ("assets", "page_assets"):
            if (k.get("assets") or {}).get(name):
                paths.append(k["assets"][name])
        paths += [f"{e['path']}/extraction.json" for e in k.get("extractions", [])]
        paths += [f"{g['path']}/publication.json" for g in k.get("golden", [])]
    missing = [p for p in paths if not ctx.root.exists(p)]
    out.append(("manifest", "FK", "every path in manifest.json exists", len(missing), len(paths), missing[:3]))
    # rule versions: hash recomputes, file name = version
    bad = []
    for path in cat.get("rule_versions", []):
        r = ctx.read_json(path)
        if model.content_hash(r) != r["content_hash"] or path != layout.rule_version(ctx.catalog, r["rule_id"], r["version"]):
            bad.append(path)
    out.append(("rule_version", "CHK", "content_hash = sha256(definition); path = rules/<id>/v<version>", len(bad),
                len(cat.get("rule_versions", [])), bad[:3]))
    # extraction.json: files' sha256 + row counts; input hashes recompute
    bad, total = [], 0
    for e in ctx.extractions():
        meta = ctx.extraction_meta(e["extraction"])
        rs, rules = ctx.ruleset_rules(meta["ruleset_version"])
        if meta.get("input_hashes") != model.input_hashes(rules, rs["settings"]["content_root"]):
            bad.append(f"{e['extraction']}: input_hashes")
        for name, info in meta["files"].items():
            total += 1
            local = ctx.root.local_path(f"{e['path']}/{name}")
            rows = con.execute(f"SELECT count(*) FROM read_parquet('{local}')").fetchone()[0]
            if hashlib.sha256(local.read_bytes()).hexdigest() != info["sha256"] or rows != info["rows"]:
                bad.append(f"{e['extraction']}/{name}")
    out.append(("extraction", "CHK", "extraction.json: files' sha256 + rows, input_hashes recompute", len(bad), total,
                bad[:3]))
    # copied rules are row-identical to the parent extraction (spec §4.1, §4.3)
    for e in ctx.extractions():
        meta = ctx.extraction_meta(e["extraction"])
        p, c = meta.get("parent_extraction"), meta["extraction"]
        if not p:
            continue
        copied = meta.get("copied_rules", [])
        fields = [r for r in copied if r in set(x[0] for x in con.execute(
            f"SELECT DISTINCT rule_id FROM raw_matches WHERE extraction = '{c}'").fetchall())]
        rid_list = ", ".join(f"'{r}'" for r in fields) or "''"
        n = con.execute(f"""SELECT count(*) FROM (
            (SELECT * EXCLUDE (extraction, rule_version) FROM raw_matches WHERE extraction = '{p}' AND rule_id IN ({rid_list})
             EXCEPT ALL SELECT * EXCLUDE (extraction, rule_version) FROM raw_matches WHERE extraction = '{c}' AND rule_id IN ({rid_list}))
            UNION ALL
            (SELECT * EXCLUDE (extraction, rule_version) FROM raw_matches WHERE extraction = '{c}' AND rule_id IN ({rid_list})
             EXCEPT ALL SELECT * EXCLUDE (extraction, rule_version) FROM raw_matches WHERE extraction = '{p}' AND rule_id IN ({rid_list})))""").fetchone()[0]
        total = con.execute(f"SELECT count(*) FROM raw_matches WHERE extraction = '{c}' AND rule_id IN ({rid_list})").fetchone()[0]
        out.append(("matches", "CHK", f"{c}: copied rules' rows identical to {p}", n, total, []))
        locs_copied = all(r in copied for r in [x[0] for x in con.execute(
            f"SELECT DISTINCT locator_rule_id FROM occurrences WHERE extraction = '{c}'").fetchall()])
        pages_copied = all(r in copied for r in [x[0] for x in con.execute(
            f"SELECT DISTINCT rule_id FROM page_labels WHERE extraction = '{c}'").fetchall()])
        for t, ok, excl, col in (("occurrences", locs_copied, "locator_rule_version", "locator_rule_id"),
                                 ("page_labels", pages_copied, "rule_version", "rule_id")):
            if not ok:
                continue
            # the parent's rows of rules still in this ruleset (a rule dropped from the ruleset leaves no rows)
            kept = f"{col} IN (SELECT DISTINCT {col} FROM {t} WHERE extraction = '{c}')"
            n = con.execute(f"""SELECT count(*) FROM (
                (SELECT * EXCLUDE (extraction, {excl}) FROM {t} WHERE extraction = '{p}' AND {kept}
                 EXCEPT ALL SELECT * EXCLUDE (extraction, {excl}) FROM {t} WHERE extraction = '{c}')
                UNION ALL (SELECT * EXCLUDE (extraction, {excl}) FROM {t} WHERE extraction = '{c}'
                 EXCEPT ALL SELECT * EXCLUDE (extraction, {excl}) FROM {t} WHERE extraction = '{p}' AND {kept}))""").fetchone()[0]
            out.append((t, "CHK", f"{c}: copied {t} identical to {p}", n,
                        con.execute(f"SELECT count(*) FROM {t} WHERE extraction = '{c}'").fetchone()[0], []))
    # pages: saved html exists (a sample when the root is remote: listing is what we avoid)
    html = [r[0] for r in con.execute("SELECT html_path FROM pages ORDER BY page_stem").fetchall()]
    sample = html if ctx.root.uri.startswith("/") else html[:: max(1, len(html) // 25)]
    out.append(("pages", "FK", "html_path → saved page file" + ("" if sample is html else " (sample)"),
                sum(not ctx.root.exists(h) for h in sample), len(sample), []))
    k = ctx.crawl_entry()
    if (k.get("assets") or {}).get("assets") and "assets" in _tables(con):
        shas = [r[0] for r in con.execute("SELECT DISTINCT sha256 FROM assets WHERE sha256 IS NOT NULL").fetchall()]
        out.append(("assets", "FK", "sha256 → assets/files/<sha256>",
                    sum(not ctx.root.exists(layout.asset_file(ctx.catalog, ctx.crawl, s)) for s in shas), len(shas), []))
    out += golden_file_checks(ctx, con)
    return out


DOMAIN_LEAKS = ("rule_id", "rule_version", "occurrence_key", "annotation_ids", "extraction")


def golden_file_checks(ctx: Ctx, con) -> list[tuple]:
    """Per golden set (publications to one target): its files now, against the lineage of the publication that last
    published each property (properties are published one or more at a time; spec §7.6)."""
    from concurrent.futures import ThreadPoolExecutor

    from .storage import open_root

    out = []
    by_target: dict[str, list[dict]] = defaultdict(list)
    for g in ctx.crawl_entry().get("golden", []):
        pub = ctx.read_json(f"{g['path']}/publication.json")
        by_target[(pub.get("to") or "").rstrip("/")].append(pub)
    all_props = list(model.PROPERTY_ORDER)
    for target, pubs in by_target.items():
        pubs.sort(key=lambda d: d.get("published_at") or "")
        owner: dict[str, str] = {}  # property → the publication that last published it
        for d in pubs:
            for prop in d.get("properties") or all_props:
                owner[prop] = d["publication"]
        latest = pubs[-1]
        groot = open_root(target) if target else ctx.root
        prefix = latest.get("to_prefix", "")
        stems = sorted({s for d in pubs for s in d.get("page_stems", [])})
        ids, leaked, n_rec, bad_files = set(), 0, 0, []

        def fetch(stem: str, groot=groot, prefix=prefix):  # one round trip each on Azure: run them together
            path = f"{prefix}{stem}/{stem}.json"
            try:
                data = json.loads(groot.read_bytes(path))
            except FileNotFoundError:
                return stem, None, path
            html = f"{prefix}{stem}/{stem}.html"
            return stem, data, None if groot.exists(html) else html

        with ThreadPoolExecutor(max_workers=32) as pool:
            fetched = list(pool.map(fetch, stems))
        for stem, records, missing in fetched:
            if missing:
                bad_files.append(missing)
            if records is None:
                continue
            counts = Counter()  # value_index counts per (golden_id, property) across the page's records
            for rec in records:
                n_rec += 1
                for fld in rec["fields"]:
                    key = (rec["golden_id"], fld["property"])
                    ids.add((owner.get(fld["property"]), rec["golden_id"], stem, fld["property"], counts[key]))
                    counts[key] += 1
                    leaked += sum(k in DOMAIN_LEAKS for k in fld)
                leaked += sum(k in DOMAIN_LEAKS for k in rec)
        lin = set()
        if "lineage" in _tables(con) and owner:
            pairs = " OR ".join(f"(publication = '{pb}' AND property = '{pr}')" for pr, pb in owner.items())
            lin = set(con.execute(f"""SELECT publication, golden_id, page_stem, property, value_index FROM lineage
                                      WHERE {pairs}""").fetchall())
        name = latest["publication"]
        out.append(("lineage", "FK", f"{name}: every golden value has one lineage row in the publication that last "
                    "published its property (and back)", len(ids ^ lin), len(ids), []))
        out.append(("golden page", "CHK", f"{name}: <stem>/<stem>.json + .html per page", len(bad_files), len(stems),
                    bad_files[:3]))
        out.append(("golden page", "CHK", f"{name}: domain-only (no rule ids / keys / annotation ids)", leaked, n_rec, []))
    return out


def run(ctx: Ctx) -> list[tuple]:
    from .query import connect

    con = connect(ctx)
    have = _tables(con)
    results = []
    checks = SQL_CHECKS + (LINEAGE_CHECKS if "lineage" in have else [])
    for table, kind, desc, sql, base in checks:
        if base not in have and base not in ("assets", "page_assets"):
            continue
        if any(t in sql for t in ("assets",)) and "assets" not in have:
            continue
        bad = con.execute(f"SELECT count(*) FROM ({sql})").fetchone()[0]
        total = con.execute(f"SELECT count(*) FROM {base}").fetchone()[0]
        results.append((table, kind, desc, bad, total, []))
    results += file_checks(ctx, con)
    return results


def check_before_write(ctx: Ctx, rs: dict, rules: dict[str, dict], tables: dict[str, list[dict]]) -> None:
    """The keys of an extraction about to be written (spec §4: extract and publish check before they write)."""
    errors = []
    stems = {p["page_stem"] for p in ctx.pages()}
    for name, cols in (("page_labels", ("page_stem", "rule_id")), ("occurrences", ("occurrence_key",)),
                       ("matches", ("rule_id", "occurrence_key", "value_index"))):
        dup = [k for k, n in Counter(tuple(r[c] for c in cols) for r in tables[name]).items() if n > 1]
        if dup:
            errors.append(f"{name}: {len(dup)} duplicate keys, e.g. {dup[0]}")
    occ = {o["occurrence_key"]: o for o in tables["occurrences"]}
    for o in tables["occurrences"]:
        if o["page_stem"] not in stems or o["occurrence_key"] != f"{o['page_stem']}@{o['css_path']}":
            errors.append(f"occurrence {o['occurrence_key'][:80]}: bad page or key")
            break
    for m in tables["matches"]:
        o = occ.get(m["occurrence_key"])
        if o is None or rules[m["rule_id"]]["definition"]["locator"] != o["locator_rule_id"]:
            errors.append(f"match {m['rule_id']} on {m['occurrence_key'][:80]}: no occurrence of its locator")
            break
        if rules[m["rule_id"]]["version"] != m["rule_version"]:
            errors.append(f"match {m['rule_id']}: version {m['rule_version']} not in the ruleset")
            break
    for r in tables["page_labels"]:
        if r["rule_id"] not in rules or rules[r["rule_id"]]["version"] != r["rule_version"]:
            errors.append(f"page label {r['rule_id']}: not in the ruleset")
            break
    if errors:
        raise UserError("refusing to write the extraction:\n  " + "\n  ".join(errors))


def cmd_check(args) -> int:
    from .storage import open_root

    root = open_root(args.root)
    if args.catalog:
        catalogs = [resolve(args.catalog)]
    else:
        doc, _ = manifest.load(root)
        catalogs = [c["catalog"] for c in doc["catalogs"] if c.get("rulesets")]
    failed = total = 0
    for catalog in catalogs:
        t0 = time.perf_counter()
        ctx = Ctx(root, catalog, args.crawl)
        results = run(ctx)
        width = max(len(r[2]) for r in results)
        print(f"golden-datasets check: {root.uri} · {catalog} · {ctx.crawl}")
        print(f"{'table':<16} {'kind':<4} {'check':<{width}} {'rows':>7} {'bad':>4}  result")
        for table, kind, desc, bad, rows, examples in results:
            print(f"{table:<16} {kind:<4} {desc:<{width}} {rows:>7} {bad:>4}  {'ok' if bad == 0 else 'FAIL'}"
                  + (f"  e.g. {examples[0]}" if bad and examples else ""))
        f = sum(r[3] > 0 for r in results)
        failed += f
        total += len(results)
        print(f"{len(results)} checks, {f} failed, {time.perf_counter() - t0:.2f} s\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(0)
