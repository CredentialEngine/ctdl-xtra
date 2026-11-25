"""`golden-datasets check`: every primary key, foreign key and hash of spec §4.1 (spec §5.7).

Each SQL check returns the violating rows (zero rows = pass). `extract` and `rule publish` run
`check_before_write` on the tables they are about to write; `golden publish` runs the lineage checks.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

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
    ("matches", "FK", "(rule_id, rule_version) → property rule in the extraction's ruleset",
     """SELECT m.rule_id, m.rule_version, count(*) FROM raw_matches m JOIN extractions e USING (extraction)
        LEFT JOIN ruleset_rules rr ON rr.ruleset_version = e.ruleset_version AND rr.rule_id = m.rule_id
        AND rr.rule_version = m.rule_version AND rr.kind = 'property' WHERE rr.rule_id IS NULL GROUP BY ALL""",
     "raw_matches"),
    ("matches", "FK", "property rule's locator = occurrence's locator",
     """SELECT m.rule_id, o.locator_rule_id FROM raw_matches m JOIN occurrences o USING (extraction, occurrence_key)
        JOIN rule_versions rv ON rv.rule_id = m.rule_id AND rv.version = m.rule_version
        WHERE rv.locator <> o.locator_rule_id""", "raw_matches"),
    ("matches", "CHK", "every occurrence × every property rule of its locator (with a definition), from value 0",
     """SELECT o.extraction, o.occurrence_key, rv.rule_id FROM occurrences o JOIN extractions e USING (extraction)
        JOIN ruleset_rules rr ON rr.ruleset_version = e.ruleset_version AND rr.kind = 'property'
        JOIN rule_versions rv ON rv.rule_id = rr.rule_id AND rv.version = rr.rule_version
        AND rv.locator = o.locator_rule_id AND rv.rule_type <> 'none'
        LEFT JOIN raw_matches m ON m.extraction = o.extraction AND m.occurrence_key = o.occurrence_key
        AND m.rule_id = rv.rule_id AND m.value_index = 0 WHERE m.rule_id IS NULL""", "raw_matches"),
    ("matches", "CHK", "a list's values are numbered 0…n-1; only found values come in more than one",
     """SELECT extraction, rule_id, occurrence_key, count(*) n, max(value_index) top FROM raw_matches GROUP BY ALL
        HAVING top <> n - 1 OR (n > 1 AND bool_or(status <> 'found'))""", "raw_matches"),
    ("matches", "CHK", "a rule with no definition (rule_type none) has no matches",
     """SELECT m.rule_id, count(*) FROM raw_matches m JOIN rule_versions rv ON rv.rule_id = m.rule_id
        AND rv.version = m.rule_version WHERE rv.rule_type = 'none' GROUP BY ALL""", "raw_matches"),
    ("matches", "CHK", "status ∈ found/empty/no_match/absent; found ⇔ value present",
     """SELECT * FROM raw_matches WHERE status NOT IN ('found','empty','no_match','absent')
        OR (status = 'found') <> (value IS NOT NULL)""", "raw_matches"),
    ("matches", "CHK", "css_path is relative to the occurrence (unless the rule reads the page); offsets within bounds",
     """SELECT m.* FROM raw_matches m JOIN rule_versions rv ON rv.rule_id = m.rule_id AND rv.version = m.rule_version
        WHERE (starts_with(m.css_path, 'html') AND json_extract_string(rv.definition, '$.input.from')
        IS DISTINCT FROM 'page' AND json_extract_string(rv.definition, '$.fallback.input.from') IS DISTINCT FROM 'page')
        OR m.char_start > m.char_end OR m.char_start < 0""",
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
    ("annotations", "FK", "occurrence_key → occurrences of extraction_seen, record_external_identifier agrees",
     """SELECT a.annotation_id FROM annotations a LEFT JOIN occurrences o ON o.extraction = a.target.extraction_seen
        AND o.occurrence_key = a.target.occurrence_key WHERE a.target.occurrence_key IS NOT NULL
        AND (o.occurrence_key IS NULL OR o.record_external_identifier IS DISTINCT FROM a.target.record_external_identifier)""", "annotations"),
    ("annotations", "FK", "match target → matches of extraction_seen",
     """SELECT a.annotation_id FROM annotations a LEFT JOIN raw_matches m ON m.extraction = a.target.extraction_seen
        AND m.rule_id = a.target.rule_id AND m.occurrence_key = a.target.occurrence_key
        AND m.value_index = coalesce(a.target.value_index, 0)
        LEFT JOIN rule_versions rv ON rv.rule_id = a.target.rule_id AND rv.version = a.target.rule_version_seen
        WHERE a.target.kind = 'match' AND m.rule_id IS NULL AND rv.rule_type IS DISTINCT FROM 'none'""",
     "annotations"),
    ("annotations", "FK", "page_stem → pages",
     """SELECT annotation_id FROM annotations WHERE target.page_stem IS NOT NULL
        AND target.page_stem NOT IN (SELECT page_stem FROM pages)""", "annotations"),
    ("annotations", "FK", "supersedes → annotation",
     """SELECT annotation_id FROM annotations WHERE supersedes IS NOT NULL
        AND supersedes NOT IN (SELECT annotation_id FROM annotations)""", "annotations"),
    ("annotations", "CHK", "type ∈ verdict/comment/approve/reopen/reset; verdict ∈ correct/wrong/missing/question",
     """SELECT annotation_id FROM annotations WHERE type NOT IN ('verdict','comment','approve','reopen','reset')
        OR (type = 'verdict' AND verdict NOT IN ('correct','wrong','missing','question'))
        OR (type <> 'verdict' AND verdict IS NOT NULL)""", "annotations"),
    ("annotations", "CHK", "missing only on record locators, page rules and a list's items",
     """SELECT annotation_id FROM annotations WHERE verdict = 'missing' AND target.kind NOT IN ('occurrence','page')
        AND NOT (target.kind = 'match' AND coalesce(target.item, false))""",
     "annotations"),
]
LINEAGE_CHECKS = [
    ("lineage", "PK", "(publication, golden_record_id, page_stem, property, value_index) unique",
     pk("lineage", "publication, golden_record_id, page_stem, property, value_index"), "lineage"),
    ("lineage", "FK", "page_stem → pages", "SELECT * FROM lineage WHERE page_stem NOT IN (SELECT page_stem FROM pages)",
     "lineage"),
    ("lineage", "FK", "(extraction, rule_id, occurrence_key, match_value_index) → matches (a reviewer's answer: "
     "no match index, an annotation instead)",
     """SELECT l.* FROM lineage l LEFT JOIN raw_matches m ON m.extraction = l.extraction AND m.rule_id = l.rule_id
        AND m.occurrence_key = l.occurrence_key AND m.value_index = l.match_value_index WHERE m.rule_id IS NULL
        AND NOT (l.match_value_index IS NULL AND len(l.annotation_ids) > 0)""",
     "lineage"),
    ("lineage", "FK", "annotation_ids → annotations",
     """SELECT l.golden_record_id, a.id FROM lineage l, UNNEST(l.annotation_ids) AS a(id)
        WHERE a.id NOT IN (SELECT annotation_id FROM annotations)""", "lineage"),
]



STALE_RUNNING = 600  # seconds: a score takes seconds, so one `running` for longer was left by a server that stopped
DOMAIN_LEAKS = ("rule_id", "rule_version", "occurrence_key", "annotation_ids", "extraction")


def cmd_check(args) -> int:
    from .storage import open_root

    root = open_root(args.root)
    failed = 0
    for catalog in _catalogs_to_check(root, args):
        failed += _check_catalog(root, catalog, args)
    return 1 if failed else 0


def _catalogs_to_check(root, args) -> list[str]:
    if args.catalog:
        return [resolve(args.catalog)]
    doc, _ = manifest.load(root)
    return [c["catalog"] for c in doc["catalogs"] if manifest.has_rules(c, args.cls)]


def _check_catalog(root, catalog: str, args) -> int:
    t0 = time.perf_counter()
    ctx = Ctx(root, catalog, args.crawl, cls=args.cls)
    results = run(ctx)
    _print_results(root, ctx, results)
    failed = sum(r[3] > 0 for r in results)
    print(f"{len(results)} checks, {failed} failed, {time.perf_counter() - t0:.2f} s\n")
    return failed


def _print_results(root, ctx: Ctx, results: list[tuple]) -> None:
    width = max(len(r[2]) for r in results)
    print(f"golden-datasets check: {root.uri} · {ctx.catalog} · {ctx.crawl}")
    print(f"{'table':<16} {'kind':<4} {'check':<{width}} {'rows':>7} {'bad':>4}  result")
    for table, kind, desc, bad, rows, examples in results:
        print(f"{table:<16} {kind:<4} {desc:<{width}} {rows:>7} {bad:>4}  {'ok' if bad == 0 else 'FAIL'}"
              + (f"  e.g. {examples[0]}" if bad and examples else ""))


def run(ctx: Ctx) -> list[tuple]:
    from .query import connect

    con = connect(ctx)
    results = _sql_check_results(con)
    results += file_checks(ctx, con)
    results += property_checks(ctx)
    return results


def _sql_check_results(con) -> list[tuple]:
    have = _tables(con)
    checks = SQL_CHECKS + (LINEAGE_CHECKS if "lineage" in have else [])
    return [_run_sql_check(con, check) for check in checks if _can_run(check, have)]


def _can_run(check: tuple, have: set[str]) -> bool:
    sql, base = check[3], check[4]
    if base not in have and base not in ("assets", "page_assets"):
        return False
    return "assets" not in sql or "assets" in have


def _run_sql_check(con, check: tuple) -> tuple:
    table, kind, desc, sql, base = check
    bad = _count(con, f"SELECT count(*) FROM ({sql})")
    total = _count(con, f"SELECT count(*) FROM {base}")
    return table, kind, desc, bad, total, []


def file_checks(ctx: Ctx, con) -> list[tuple]:
    """Checks that need Python: files exist, hashes recompute, copied rows are identical, golden files."""
    out = [_manifest_paths_check(ctx), _rule_versions_check(ctx), _extraction_files_check(ctx, con)]
    out += _copied_rows_checks(ctx, con)
    out.append(_saved_pages_check(ctx, con))
    out += _asset_files_checks(ctx, con)
    out += golden_file_checks(ctx, con)
    out += score_checks(ctx, con)
    return out


def _manifest_paths_check(ctx: Ctx) -> tuple:
    paths = _manifest_paths(ctx)
    missing = [p for p in paths if not ctx.root.exists(p)]
    return "manifest", "FK", "every path in manifest.json exists", len(missing), len(paths), missing[:3]


def _manifest_paths(ctx: Ctx) -> list[str]:
    catalog, mine = ctx.entry() or {}, ctx.class_entry()
    paths = list(mine.get("rule_versions", [])) + [r["path"] for r in mine.get("rulesets", [])]
    if mine.get("annotations"):
        paths.append(mine["annotations"])
    for crawl in catalog.get("crawls", []):
        paths += _crawl_paths(crawl, ctx.cls)
    return paths


def _crawl_paths(crawl: dict, cls: str) -> list[str]:
    paths = [crawl["pages"]] if crawl.get("pages") else []
    assets = crawl.get("assets") or {}
    paths += [assets[name] for name in ("assets", "page_assets") if assets.get(name)]
    crawl_class = manifest.crawl_class(crawl, cls, create=False)
    paths += [f"{e['path']}/extraction.json" for e in crawl_class.get("extractions", [])]
    paths += [f"{g['path']}/publication.json" for g in crawl_class.get("golden", [])]
    return paths


def _rule_versions_check(ctx: Ctx) -> tuple:
    paths = ctx.class_entry().get("rule_versions", [])
    bad = [path for path in paths if not _rule_version_matches(ctx, path)]
    return ("rule_version", "CHK", "content_hash = sha256(definition); path = rules/<id>/v<version>", len(bad),
            len(paths), bad[:3])


def _rule_version_matches(ctx: Ctx, path: str) -> bool:
    r = ctx.read_json(path)
    return model.content_hash(r) == r["content_hash"] \
        and path == layout.rule_version(ctx.catalog, ctx.cls, r["rule_id"], r["version"])


def _extraction_files_check(ctx: Ctx, con) -> tuple:
    """extraction.json: files' sha256 + row counts; input hashes recompute."""
    bad, total = [], 0
    for extraction in ctx.extractions():
        problems, files = _extraction_file_problems(ctx, con, extraction)
        bad += problems
        total += files
    return ("extraction", "CHK", "extraction.json: files' sha256 + rows, input_hashes recompute", len(bad), total,
            bad[:3])


def _extraction_file_problems(ctx: Ctx, con, extraction: dict) -> tuple[list[str], int]:
    name = extraction["extraction"]
    meta = ctx.extraction_meta(name)
    rs, rules = ctx.ruleset_rules(meta["ruleset_version"])
    problems = []
    if meta.get("input_hashes") != model.input_hashes(rules, rs["settings"]["content_root"]):
        problems.append(f"{name}: input_hashes")
    problems += [f"{name}/{file}" for file, info in meta["files"].items()
                 if not _file_matches(ctx, con, f"{extraction['path']}/{file}", info)]
    return problems, len(meta["files"])


def _file_matches(ctx: Ctx, con, path: str, info: dict) -> bool:
    local = ctx.root.local_path(path)
    rows = _count(con, f"SELECT count(*) FROM read_parquet('{local}')")
    return hashlib.sha256(local.read_bytes()).hexdigest() == info["sha256"] and rows == info["rows"]


def _copied_rows_checks(ctx: Ctx, con) -> list[tuple]:
    """Copied rules are row-identical to the parent extraction (spec §4.1, §4.3)."""
    out = []
    for extraction in ctx.extractions():
        meta = ctx.extraction_meta(extraction["extraction"])
        if meta.get("parent_extraction"):
            out += _copied_checks(con, meta)
    return out


def _copied_checks(con, meta: dict) -> list[tuple]:
    parent, child = meta["parent_extraction"], meta["extraction"]
    copied = meta.get("copied_rules", [])
    out = [_copied_matches_check(con, parent, child, copied)]
    for table, version_col, rule_col in (("occurrences", "locator_rule_version", "locator_rule_id"),
                                         ("page_labels", "rule_version", "rule_id")):
        if all(r in copied for r in _distinct(con, rule_col, table, child)):
            out.append(_copied_table_check(con, table, version_col, rule_col, parent, child))
    return out


def _copied_matches_check(con, parent: str, child: str, copied: list[str]) -> tuple:
    with_matches = set(_distinct(con, "rule_id", "raw_matches", child))
    rule_ids = ", ".join(f"'{r}'" for r in copied if r in with_matches) or "''"
    rows_of = "SELECT * EXCLUDE (extraction, rule_version) FROM raw_matches WHERE extraction = '{}' AND rule_id IN ({})"
    n = _count(con, _difference_sql(rows_of.format(parent, rule_ids), rows_of.format(child, rule_ids)))
    total = _count(con, f"SELECT count(*) FROM raw_matches WHERE extraction = '{child}' AND rule_id IN ({rule_ids})")
    return "matches", "CHK", f"{child}: copied rules' rows identical to {parent}", n, total, []


def _copied_table_check(con, table: str, version_col: str, rule_col: str, parent: str, child: str) -> tuple:
    # the parent's rows of rules still in this ruleset (a rule dropped from the ruleset leaves no rows)
    kept = f"{rule_col} IN (SELECT DISTINCT {rule_col} FROM {table} WHERE extraction = '{child}')"
    rows = f"SELECT * EXCLUDE (extraction, {version_col}) FROM {table}"
    n = _count(con, _difference_sql(f"{rows} WHERE extraction = '{parent}' AND {kept}",
                                    f"{rows} WHERE extraction = '{child}'"))
    total = _count(con, f"SELECT count(*) FROM {table} WHERE extraction = '{child}'")
    return table, "CHK", f"{child}: copied {table} identical to {parent}", n, total, []


def _saved_pages_check(ctx: Ctx, con) -> tuple:
    """Saved html exists (a sample when the root is remote: listing is what we avoid)."""
    html = [r[0] for r in con.execute("SELECT html_path FROM pages ORDER BY page_stem").fetchall()]
    sample = html if ctx.crawl_root.uri.startswith("/") else html[:: max(1, len(html) // 25)]
    return ("pages", "FK", "html_path → saved page file in xtra-cli's container" + (
        "" if sample is html else " (sample)"), sum(not ctx.crawl_root.exists(h) for h in sample), len(sample), [])


def _asset_files_checks(ctx: Ctx, con) -> list[tuple]:
    if not ((ctx.crawl_entry().get("assets") or {}).get("assets") and "assets" in _tables(con)):
        return []
    shas = [r[0] for r in con.execute("SELECT DISTINCT sha256 FROM assets WHERE sha256 IS NOT NULL").fetchall()]
    missing = sum(not ctx.root.exists(layout.asset_file(ctx.catalog, ctx.crawl, s)) for s in shas)
    return [("assets", "FK", "sha256 → assets/files/<sha256>", missing, len(shas), [])]


def golden_file_checks(ctx: Ctx, con) -> list[tuple]:
    """Per golden dataset version: its rule-matched tree, and the latest location's files for the latest version,
    against the version's lineage (values with a CTDL term: the rest stay out of the files); its human-reviewed tree
    is the `approval: human` subset of the rule-matched one; the HTML is only at the latest location. Human-reviewed
    values outside its columns have no lineage row (their annotations trace them; Evals spec §4.3). Publications
    from before versions (`pub-…`) are checked at their latest location."""
    from . import properties
    from .golden import VERSION

    known_paths = {r["path"] for r in properties.load(ctx.cls)} | {t for _, t in model.FIRST_EIGHT if t}
    docs = [ctx.read_json(f"{g['path']}/publication.json", immutable=False)
            for g in ctx.crawl_class().get("golden", [])]
    newest = max((d["ruleset_version"] for d in docs if VERSION.match(d["publication"])), default=None)
    out = []
    for doc in docs:
        out += _PublicationCheck(ctx, con, doc, known_paths).run(newest)
    return out


class _PublicationCheck:
    """One golden dataset publication's trees against its lineage."""

    def __init__(self, ctx: Ctx, con, doc: dict, known_paths: set[str]):
        from .golden import VERSION
        from .storage import open_root

        self.ctx, self.doc, self.known_paths = ctx, doc, known_paths
        self.name = doc["publication"]
        self.columns = set(doc.get("properties") or model.FIRST_EIGHT_ORDER)  # an old publication: the eight
        self.groot = open_root(doc["to"]) if doc.get("to") else ctx.root
        self.versioned = bool(VERSION.match(self.name))
        self.lineage = _lineage_ids(con, self.name, self.columns, self.versioned)
        self.rule_files: dict[str, list] = {}

    def run(self, newest) -> list[tuple]:
        stems, prefixes = self.trees(newest)
        out = []
        for prefix, html in prefixes:
            out += self.tree_checks(stems, prefix, html)
        if self.versioned:
            out.append(self.human_reviewed_check())
        return out

    def trees(self, newest) -> tuple[list[str], list[tuple[str, bool]]]:
        from .golden import RULE_MATCHED, latest_prefix, tree_stems, version_prefix

        if not self.versioned:
            return sorted(self.doc.get("page_stems", [])), [(self.doc.get("to_prefix", ""), True)]
        version = self.doc["ruleset_version"]
        rule_matched = version_prefix(self.ctx, version, RULE_MATCHED)
        stems = sorted(tree_stems(self.groot, rule_matched))
        prefixes = [(rule_matched, False)] + ([(latest_prefix(self.ctx), True)] if version == newest else [])
        return stems, prefixes

    def tree_checks(self, stems: list[str], prefix: str, html: bool) -> list[tuple]:
        tally = _TreeTally(self.columns, self.known_paths)
        for stem, records, bad in self.fetch_all(stems, prefix, html):
            if bad:
                tally.bad_files.append(bad)
            if records is None:
                continue
            if not html:
                self.rule_files[stem] = records
            tally.count_page(stem, records)
        return self.tree_results(tally, f"{self.name}: {prefix}", html, len(stems))

    def tree_results(self, tally: _TreeTally, where: str, html: bool, pages: int) -> list[tuple]:
        return [
            ("lineage", "FK", f"{where} every value of its columns has one lineage row (and back)",
             len(tally.ids ^ self.lineage), len(tally.ids), []),
            ("golden page", "CHK", f"{where} <stem>/<stem>.json{' + .html' if html else ', no .html'} "
             "per page", len(tally.bad_files), pages, tally.bad_files[:3]),
            ("golden page", "CHK", f"{where} domain-only (no rule ids / keys / annotation ids)", tally.leaked,
             tally.records, []),
            ("golden page", "FK", f"{where} every ctdl_property is a path of properties/{self.ctx.cls}.csv",
             len(tally.unknown), tally.values, sorted(set(tally.unknown))[:3]),
        ]

    def fetch_all(self, stems: list[str], prefix: str, html: bool) -> list[tuple]:
        """One round trip each on Azure: run them together."""
        with ThreadPoolExecutor(max_workers=32) as pool:
            return list(pool.map(lambda stem: self.fetch(stem, prefix, html), stems))

    def fetch(self, stem: str, prefix: str, html: bool) -> tuple:
        path = f"{prefix}{stem}/{stem}.json"
        try:
            data = json.loads(self.groot.read_bytes(path))
        except FileNotFoundError:
            return stem, None, path
        has_html = self.groot.exists(f"{prefix}{stem}/{stem}.html")
        return stem, data, None if has_html == html else f"{prefix}{stem}/{stem}.html"

    def human_reviewed_check(self) -> tuple:
        from .golden import HUMAN_REVIEWED, tree_pages, tree_stems, version_prefix

        prefix = version_prefix(self.ctx, self.doc["ruleset_version"], HUMAN_REVIEWED)
        want, _ = tree_pages(self.rule_files, HUMAN_REVIEWED)
        have = set(tree_stems(self.groot, prefix))
        with ThreadPoolExecutor(max_workers=32) as pool:
            got = dict(pool.map(lambda stem: (stem, self.read_page(prefix, stem)), sorted(have)))
        bad = sorted(s for s in have | set(want) if got.get(s) != want.get(s)
                     or self.groot.exists(f"{prefix}{s}/{s}.html"))
        return ("golden page", "CHK", f"{self.name}: {prefix} the approval: human subset of rule-matched, JSON only",
                len(bad), len(have | set(want)), bad[:3])

    def read_page(self, prefix: str, stem: str):
        return json.loads(self.groot.read_bytes(f"{prefix}{stem}/{stem}.json"))


class _TreeTally:
    """What one tree's page files hold: lineage ids of its columns, leaked keys, unknown CTDL terms."""

    def __init__(self, columns: set[str], known_paths: set[str]):
        self.columns, self.known_paths = columns, known_paths
        self.ids: set[tuple] = set()
        self.bad_files: list[str] = []
        self.unknown: list[str] = []
        self.leaked = self.records = self.values = 0

    def count_page(self, stem: str, records: list[dict]) -> None:
        counts = Counter()  # value_index counts per (golden_record_id, property) across the page's records
        for rec in records:
            self.records += 1
            gid = rec.get("golden_record_id", rec.get("golden_id"))  # files before the rename say golden_id
            for fld in rec["fields"]:
                self.count_field(stem, gid, fld, counts)
            self.leaked += sum(k in DOMAIN_LEAKS for k in rec)

    def count_field(self, stem: str, gid, fld: dict, counts: Counter) -> None:
        key = (gid, fld["property"])
        if fld["property"] in self.columns:
            self.ids.add((gid, stem, fld["property"], counts[key]))
        counts[key] += 1
        self.leaked += sum(k in DOMAIN_LEAKS for k in fld)
        self.values += 1
        if fld.get("ctdl_property") and fld["ctdl_property"] not in self.known_paths:
            self.unknown.append(fld["ctdl_property"])


def _lineage_ids(con, name: str, columns: set[str], versioned: bool) -> set[tuple]:
    if "lineage" not in _tables(con) or not columns:
        return set()
    names = ", ".join(f"'{c}'" for c in columns)
    term = " AND ctdl_property IS NOT NULL" if versioned else ""
    return set(con.execute(f"""SELECT golden_record_id, page_stem, property, value_index FROM lineage
                               WHERE publication = '{name}' AND property IN ({names}){term}""").fetchall())


def score_checks(ctx: Ctx, con) -> list[tuple]:
    """Every score's provenance resolves (Evals spec §4): its golden dataset (a version that exists, the human-reviewed
    values as of a time, or a draft extraction) and its extract output (a kept copy under extract-outputs/, with the
    report it was identified by); every values.parquet row's page is in pages/; scores/pending.json is well-formed;
    no score is left `running` (a restarted server marks it interrupted; this only reports it)."""
    from . import scores

    ids = scores.score_ids(ctx)
    outputs = {o["id"]: o for o in ctx.crawl_entry().get("extract_outputs", [])}
    if not ids and not outputs and not ctx.root.exists(layout.pending_score(ctx.catalog, ctx.crawl, ctx.cls)):
        return []
    out = [_kept_outputs_check(ctx, outputs, ids)]
    docs, unreadable = _read_scores(ctx, ids)
    out.append(("score", "FK", "every score in manifest.json has its score.json", len(unreadable), len(ids),
                unreadable))
    out += [_score_golden_check(ctx, docs), _score_output_check(docs, outputs), _score_values_check(ctx, con, docs)]
    out += [_stale_running_check(docs), _score_status_check(docs)]
    return out + _pending_score_checks(ctx)


def _kept_outputs_check(ctx: Ctx, outputs: dict[str, dict], ids: list[str]) -> tuple:
    from . import scores

    xtra = scores.xtra(ctx) if outputs or ids else None
    kept = {i: o for i, o in outputs.items() if o.get("copy")}
    bad = [i for i, o in kept.items() if not _has_extract_report(ctx, xtra, o)]
    return ("extract output", "FK", "a kept copy → extract/<id>/ in xtra-cli's container has its extract report",
            len(bad), len(kept), bad)


def _has_extract_report(ctx: Ctx, xtra, output: dict) -> bool:
    """extract-report.json, or today's extraction-<property>-report.json files."""
    from . import scores

    reports = scores.RecordsStore(xtra, output["copy"], ctx.catalog, ctx.crawl).reports()
    return any(xtra.exists(f"{output['copy']}/{n}") for n in reports)


def _read_scores(ctx: Ctx, ids: list[str]) -> tuple[list[dict], list[str]]:
    from . import scores

    docs, unreadable = [], []
    for sid in ids:
        try:
            docs.append(scores.read(ctx, sid))
        except FileNotFoundError:
            unreadable.append(sid)
    return docs, unreadable


def _score_golden_check(ctx: Ctx, docs: list[dict]) -> tuple:
    from .golden import versions

    have = versions(ctx)
    drafts = {e["extraction"] for e in ctx.extractions()}
    bad = [d["id"] for d in docs if not _golden_resolves(d.get("golden") or {}, have, drafts)]
    return ("score", "FK", "golden → a version, human-reviewed as of a time, or a draft extraction", len(bad),
            len(docs), bad)


def _golden_resolves(golden: dict, have, drafts: set[str]) -> bool:
    from . import scores
    from .golden import VERSION

    m = VERSION.match(golden.get("id") or "")
    if golden.get("kind") == "version":
        return bool(m) and int(m.group(1)) in have
    if golden.get("kind") == "human-reviewed":
        return golden.get("id") == scores.HUMAN_REVIEWED and bool(golden.get("as_of")) and bool(have)
    return golden.get("kind") == "draft" and golden.get("id") in drafts


def _score_output_check(docs: list[dict], outputs: dict[str, dict]) -> tuple:
    bad = [d["id"] for d in docs if (outputs.get(d["output"].get("id")) or {}).get("report_etag")
           != d["output"].get("report_etag")]
    return "score", "FK", "output → a registered extract output (same report ETag)", len(bad), len(docs), bad


def _score_values_check(ctx: Ctx, con, docs: list[dict]) -> tuple:
    from . import scores

    stems = {r[0] for r in con.execute("SELECT page_stem FROM pages").fetchall()}
    bad, n = [], 0
    for d in (d for d in docs if d["status"] == "done"):
        try:
            rows = [r["page_stem"] for r in scores.values(ctx, d["id"])]
        except OSError:
            bad.append(f"{d['id']}: no values.parquet")
            continue
        n += len(rows)
        bad += [f"{d['id']}: {s}" for s in sorted(set(rows) - stems)]
    return "score values", "FK", "values.parquet page_stem → pages (done scores)", len(bad), n, bad[:3]


def _stale_running_check(docs: list[dict]) -> tuple:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    stale = [d["id"] for d in docs if d["status"] == "running"
             and (now - _parse_time(d["created_at"])).total_seconds() > STALE_RUNNING]
    return ("score", "CHK", f"none left running (> {STALE_RUNNING // 60} min; a server start marks it interrupted)",
            len(stale), len(docs), stale)


def _score_status_check(docs: list[dict]) -> tuple:
    bad = [d["id"] for d in docs if d["status"] not in ("running", "done", "failed", "interrupted")]
    return "score", "CHK", "status ∈ running/done/failed/interrupted", len(bad), len(docs), bad


def _pending_score_checks(ctx: Ctx) -> list[tuple]:
    path = layout.pending_score(ctx.catalog, ctx.crawl, ctx.cls)
    if not ctx.root.exists(path):
        return []
    ok = _is_pending_doc(ctx.root, path)
    return [("pending score", "CHK", "scores/pending.json is {due_at: ISO time, reason}", int(not ok), 1, [])]


def _is_pending_doc(root, path: str) -> bool:
    try:
        p = root.read_json(path)
        return isinstance(p, dict) and isinstance(p.get("reason"), str) and bool(_parse_time(str(p.get("due_at"))))
    except (ValueError, TypeError):
        return False


def _parse_time(text: str):
    from datetime import datetime

    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def property_checks(ctx: Ctx) -> list[tuple]:
    """The class's properties file and each catalog's rules against it (property-rules spec §4.15)."""
    from . import properties

    out = _properties_file_checks(ctx.cls, properties.load(ctx.cls))
    if ctx.ruleset_versions():
        out += _ruleset_property_checks(ctx)
    return out


def _properties_file_checks(cls: str, rows: list[dict]) -> list[tuple]:
    out = []
    for col in ("rule_id", "label", "path"):
        vals = [r[col] for r in rows if r[col] or col != "path"]
        dup = sorted({v for v in vals if vals.count(v) > 1})
        out.append((f"properties/{cls}.csv", "PK", f"{col} unique", len(dup), len(rows), dup[:3]))
    paths = {r["path"] for r in rows}
    orphans = [r["rule_id"] for r in rows if r["parent"] and r["parent"] not in paths]
    out.append((f"properties/{cls}.csv", "FK", "every parent is a row", len(orphans), len(rows), orphans[:3]))
    unnoted = [r["rule_id"] for r in rows if r["sheet_path"] != r["path"] and r["sheet_path"] and not r["path_note"]]
    out.append((f"properties/{cls}.csv", "CHK", "a path that differs from the sheet's has a path_note", len(unnoted),
                len(rows), unnoted[:3]))
    return out


def _ruleset_property_checks(ctx: Ctx) -> list[tuple]:
    from . import properties

    rs, rules = ctx.ruleset_rules(ctx.latest_ruleset())
    missing = sorted(properties.missing_rules(rules, ctx.cls))
    active = properties.active(ctx.cls)
    props = {rid: r for rid, r in rules.items() if r["kind"] == "property"}
    bad = _bad_rule_inputs(rules, props)
    return [("ruleset", "CHK", f"the latest ruleset has a property rule for every row of properties/{ctx.cls}.csv "
             "(golden-datasets properties apply)", len(missing), len(active), missing[:3]),
            ("ruleset", "FK", "input.rule → a property rule on the same locator, with no cycles", len(bad),
             len(props), bad[:3])]


def _bad_rule_inputs(rules: dict[str, dict], props: dict[str, dict]) -> list[str]:
    from . import engine

    bad = [rid for rid, r in props.items() if _reads_another_locator(r, props)]
    try:
        engine.property_order(rules, list(props))
    except ValueError as exc:
        bad.append(str(exc))
    return bad


def _reads_another_locator(rule: dict, props: dict[str, dict]) -> bool:
    from . import engine

    parent = engine.input_of(rule["definition"]).get("rule")
    return bool(parent) and (parent not in props or props[parent]["definition"].get("locator")
                             != rule["definition"].get("locator"))


def check_before_write(ctx: Ctx, rs: dict, rules: dict[str, dict], tables: dict[str, list[dict]]) -> None:
    """The keys of an extraction about to be written (spec §4: extract and publish check before they write)."""
    stems = {p["page_stem"] for p in ctx.pages()}
    errors = _duplicate_key_errors(tables)
    errors += _occurrence_errors(stems, tables["occurrences"])
    errors += _match_errors(rules, tables)
    errors += _page_label_errors(rules, tables["page_labels"])
    if errors:
        raise UserError("refusing to write the extraction:\n  " + "\n  ".join(errors))


def _duplicate_key_errors(tables: dict[str, list[dict]]) -> list[str]:
    errors = []
    for name, cols in (("page_labels", ("page_stem", "rule_id")), ("occurrences", ("occurrence_key",)),
                       ("matches", ("rule_id", "occurrence_key", "value_index"))):
        dup = [k for k, n in Counter(tuple(r[c] for c in cols) for r in tables[name]).items() if n > 1]
        if dup:
            errors.append(f"{name}: {len(dup)} duplicate keys, e.g. {dup[0]}")
    return errors


def _occurrence_errors(stems: set[str], occurrences: list[dict]) -> list[str]:
    for o in occurrences:
        if o["page_stem"] not in stems or o["occurrence_key"] != f"{o['page_stem']}@{o['css_path']}":
            return [f"occurrence {o['occurrence_key'][:80]}: bad page or key"]
    return []


def _match_errors(rules: dict[str, dict], tables: dict[str, list[dict]]) -> list[str]:
    occurrences = {o["occurrence_key"]: o for o in tables["occurrences"]}
    for m in tables["matches"]:
        error = _match_error(m, occurrences.get(m["occurrence_key"]), rules)
        if error:
            return [error]
    return []


def _match_error(m: dict, occurrence: dict | None, rules: dict[str, dict]) -> str | None:
    if occurrence is None or rules[m["rule_id"]]["definition"]["locator"] != occurrence["locator_rule_id"]:
        return f"match {m['rule_id']} on {m['occurrence_key'][:80]}: no occurrence of its locator"
    if rules[m["rule_id"]]["version"] != m["rule_version"]:
        return f"match {m['rule_id']}: version {m['rule_version']} not in the ruleset"
    return None


def _page_label_errors(rules: dict[str, dict], page_labels: list[dict]) -> list[str]:
    for r in page_labels:
        if r["rule_id"] not in rules or rules[r["rule_id"]]["version"] != r["rule_version"]:
            return [f"page label {r['rule_id']}: not in the ruleset"]
    return []


def _tables(con) -> set[str]:
    return {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}


def _distinct(con, column: str, table: str, extraction: str) -> list:
    return [r[0] for r in con.execute(f"SELECT DISTINCT {column} FROM {table} WHERE extraction = '{extraction}'")
            .fetchall()]


def _difference_sql(left: str, right: str) -> str:
    return f"SELECT count(*) FROM (({left} EXCEPT ALL {right}) UNION ALL ({right} EXCEPT ALL {left}))"


def _count(con, sql: str) -> int:
    return con.execute(sql).fetchone()[0]


if __name__ == "__main__":
    sys.exit(0)
