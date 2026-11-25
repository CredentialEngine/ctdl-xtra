"""`golden-datasets golden publish`: golden dataset versions and their lineage (spec §4.2 golden_record_id, §5.6,
§7.6; Evals spec §4.1, §4.3).

A golden dataset's ID is its ruleset's: *ruleset v3*. A column (property) is published once its property rule is
approved; publishing it writes the whole golden dataset of that ruleset again (every column published in it or in an
earlier version so far, all from this ruleset's immutable extraction), never merged with what was there: columns only
grow (Evals spec §1 rows 3, 16), except that Reset rule withdraws its column until the rule is approved again
(phase1-followups spec §4.5). The first publication in a ruleset
creates its version; later ones rewrite it with the extra column. Every version is kept as two parallel trees, and
the latest version's rule-matched tree also replaces each page's file at the usual location, in the
`xtra-golden-sets` container (for Course; every other class has the same tree under `<class>/`, `class_prefix`):

    <golden root>/<catalog>/<crawl>/<page_stem>/<page_stem>.{json,html}                     the latest version
    <golden root>/catalogs/<catalog>/versions/ruleset-vN/rule-matched/<catalog>/<crawl>/<page_stem>/<page_stem>.json
    <golden root>/catalogs/<catalog>/versions/ruleset-vN/human-reviewed/<catalog>/<crawl>/<page_stem>/<page_stem>.json

`rule-matched/` holds every value; `human-reviewed/` only the `approval: human` ones, and only the pages and records
that have one. (`<catalog>/<crawl>` repeats so `xtra score --baseline-uri …/versions/ruleset-vN/<tree>` scores a tree
as it is.) Each file is [{golden_record_id, approval, fields: [{ctdl_property, property, value, source_url, location,
approval, approved_by, approved_at}]}]. `<page_stem>.html` (the page as crawled, ~3 MB) is only at the latest
location: xtra's scorer reads only the JSON, so the version trees hold JSON only.

The files hold what `xtra score` accepts (`tree_pages`): values with no CTDL term (Learning Type) are left out (the
Studio keeps them in its lineage and golden.parquet); the scorer pairs a page's records with the extract's by
position and rejects a record with no values, so trailing empty records are dropped and a page whose empty record
comes before a non-empty one is left out.

Every value says who approved it: `approval` is `human` when a subject matter expert confirmed that value (marked it
correct and it hasn't changed since, or marked it wrong and selected the text it now is), else `rule` (its rule's
approval covers it); `approved_by` / `approved_at` name that person and when, or who approved the rule. A record's
`approval` is `human` when every value is, `rule` when none is, else `mixed`. The lineage has the same three columns.

Human-reviewed values have their own life cycle (Evals §4.3): they are in the files in any column, published or not,
and each verdict rewrites its page's file in both trees of the latest version and at the latest location
(`publish_page`), then asks for a score 5 minutes later (`scores/pending.json`).

The files are domain-only: no rule ids, occurrence keys or annotation ids. The Studio keeps the lineage, which traces
every golden value back to its match, rule version and annotations, and a Parquet copy of the values:

    <studio root>/<catalog>/<crawl>/golden-dataset-studio/golden/ruleset-vN/{publication.json, lineage.parquet,
                                                                              golden.parquet}

Every course found on a page is published, course pages and program-page course lines alike. `golden_record_id` is the
`record_external_identifier`, unless the course pages with that code name different courses (Marshall, WVU): then each distinct
name gets `record_external_identifier~<n>`, and the Golden screen lists them for confirmation.

The file reads top-down: the commands, then publishing (`publish`, `publish_page`, after an approval or a reset), then
`plan` (what a publication writes), then the trees, paths and names they use.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import golden_answers, layout, manifest, model, properties, telemetry
from .context import Ctx
from .errors import UserError
from .review import HUMAN_STATES, LOADER, Review, norm  # noqa: F401  (HUMAN_STATES: the row states a person confirmed)
from .storage import AzureRoot, LocalRoot, open_root

FULL_LOCATOR = "locator-course-page"  # Course's record locator (properties.record_locator finds any class's)
VERSION = re.compile(r"ruleset-v(\d+)$")
RESCORE_AFTER = timedelta(minutes=5)
RULE_MATCHED, HUMAN_REVIEWED = "rule-matched", "human-reviewed"
TREES = (RULE_MATCHED, HUMAN_REVIEWED)
GOLDEN_CONTAINER = "azure://https://ceteststorage.blob.core.windows.net/xtra-golden-sets"
#: Where a version's trees are stored (property-rules spec §4.16, X1): the golden dataset is only human-reviewed
#: values, the silver dataset (also called rule-matched) every value of an approved rule. Versions written before keep
#: their folders (`rule-matched/`, `human-reviewed/`): stored data isn't rewritten (O7).
TREE_DIRS = {RULE_MATCHED: "silver", HUMAN_REVIEWED: "golden"}
NAMED = "golden-silver"  # the manifest entry's `trees` for a version stored in TREE_DIRS
APPROVAL_FIELDS = ("approval", "approved_by", "approved_at")
GATE_FIELDS = ("rule_id", "version", "status", "approved_by")
PAGE_FORMAT = ("golden sets per-page shape: <catalog>/<crawl>/<stem>/<stem>.json = "
               "[{golden_record_id, approval, fields: [{ctdl_property, property, value, source_url, location, "
               "approval, approved_by, approved_at}]}], in two trees (rule-matched: every value; "
               "human-reviewed: approval human only), values with a CTDL term only (the rest are in the "
               "lineage); <stem>.html as crawled only at the latest location; the whole golden dataset of "
               "this ruleset, never merged")
APPROVAL_MEANING = ("human: a subject matter expert confirmed the value (marked it correct, or selected the "
                    "right text it now is); rule: the value is approved by its rule's approval")


# =====================================================================================================
# Commands
# =====================================================================================================
def cmd_golden_publish(args) -> int:
    from .check import golden_file_checks
    from .query import connect

    ctx = Ctx.from_args(args)
    started = time.perf_counter()
    doc = publish(ctx, args.to or default_target(ctx), "golden-datasets golden publish", args.allow_unapproved,
                  properties=args.property)
    _print_publication(doc, time.perf_counter() - started)
    return _report_checks(ctx, golden_file_checks, connect, {doc["publication"]})


def cmd_golden_backfill(args) -> int:
    from .check import golden_file_checks
    from .query import connect

    ctx = Ctx.from_args(args)
    docs = backfill(ctx, args.to or default_target(ctx), again=getattr(args, "again", False))
    if not docs:
        print("nothing to backfill: every publication is a golden dataset version already")
        return 0
    return _report_checks(ctx, golden_file_checks, connect, {d["publication"] for d in docs})


def _print_publication(doc: dict, seconds: float) -> None:
    print(f"silver dataset {doc['publication']} ({', '.join(doc['properties'])}): {doc['pages']:,} pages, {doc['courses']:,} courses, "
          f"{doc['records']:,} records, {doc['lineage_rows']:,} lineage rows → {doc['to']}/{doc['version_prefix']}"
          f"{' and ' + doc['to_prefix'] if doc['latest'] else ''} ({seconds:.1f}s)")
    if not doc["approval_gate"]["all_rules_approved"]:
        print("  warning: published with --allow-unapproved; publication.json records approval_gate.all_rules_approved = false")
    if doc["golden_record_id_collisions"]:
        print(f"  golden_record_id collisions to confirm: {len(doc['golden_record_id_collisions'])} course codes")


def _report_checks(ctx: Ctx, golden_file_checks, connect, pubs: set[str]) -> int:
    results = golden_file_checks(Ctx(ctx.root, ctx.catalog, ctx.crawl, cls=ctx.cls),
                                 connect(Ctx(ctx.root, ctx.catalog, ctx.crawl, cls=ctx.cls)))
    mine = [r for r in results if r[2].split(":")[0] in pubs]
    for r in mine:
        print(f"  check: {r[2]} — {r[4]} rows, {r[3]} bad")
    return 1 if any(r[3] for r in mine) else 0


# =====================================================================================================
# Publishing
# =====================================================================================================
def publish(ctx: Ctx, to: str, by: str, allow_unapproved: bool = False, log=print,
            properties: list[str] | None = None, ext: str | None = None, published_at: str | None = None,
            note: dict | None = None) -> dict:
    """Publish these properties (None: every property whose rule is approved; []: none, only the human-reviewed
    values) into the golden dataset of the extraction's ruleset (`ext`, default the latest): the whole version is
    written again with every column published in it, or in an earlier version, so far."""
    rv = LOADER.review(ctx, ext)
    n = rv.snap.ruleset_version
    ok, statuses = approval(rv)
    gdir = layout.golden_dir(ctx.catalog, ctx.crawl, ctx.cls, version_name(n))
    before = _read_publication(ctx, gdir)
    columns = _columns_kept(ctx, rv, _chosen(rv, properties, allow_unapproved), before)
    p = plan(rv, set(columns))
    target = open_root(to)
    latest = n >= max(versions(ctx), default=0)
    files = _write_trees(ctx, target, n, p["pages"], latest)
    info = _write_tables(ctx, gdir, version_name(n), p)
    doc = _dated(publication_doc(ctx, rv, p, version_name(n), target.uri, by, ok, statuses, info, columns, files),
                 before, published_at, note)
    _save_publication(ctx, gdir, doc, target.uri, named_trees(ctx, n))
    return doc | {"latest": latest}  # whether it also went to the latest location (not saved: a newer one may come)


def publish_page(ctx: Ctx, stem: str, reason: str, by: str, create: bool = False,
                 column: str | None = None) -> dict | None:
    """After a verdict on a value of this page: rebuild its file from the Studio's state and overwrite it in both
    trees of the latest golden dataset and at the latest location (small files; a page with no values left in a tree
    loses its file there), then ask for a score 5 minutes from now. With no golden dataset yet, `create` (an expert's verdict) creates the current ruleset's. Returns
    what changed, or None."""
    vs = versions(ctx)
    if not vs:
        return _create_golden(ctx, reason, by, column) if create else None
    n = max(vs)
    doc = ctx.read_json(f"{vs[n]['path']}/publication.json", immutable=False)
    changed = _rewrite_page(ctx, n, doc, stem)
    if not changed:
        return None
    return {"publication": doc["publication"], "created": False, "files": changed,
            "due_at": request_score(ctx, reason, [column] if column else None)}


def publish_approved(ctx: Ctx, rule_id: str, by: str) -> dict | None:
    """After a column's rule is approved: publish the column into its ruleset's golden dataset (with every other
    column approved so far). None when the rule isn't a column's or its column has no CTDL term."""
    p = approval_publishes(LOADER.review(ctx), rule_id)
    if not p or not p["writes"]:
        return None
    doc = publish(ctx, default_target(ctx), by, properties=p["approved"])  # earlier versions' columns come along
    return doc | {"created": p["creates"]}


def publish_reset(ctx: Ctx, rule_id: str, by: str, why: str) -> dict | None:
    """After Reset rule: the latest golden dataset written again without the rule's column, and without the values its
    reviews made human (phase1-followups spec §4.5). None when there is no golden dataset yet."""
    if not versions(ctx):
        return None
    rv = LOADER.review(ctx)
    prop = rv.snap.rules[rule_id].get("property_label")
    return publish(ctx, default_target(ctx), by, properties=[], note={"reset": {"rule_id": rule_id, "property": prop,
                                                                              "by": by, "why": why}})


def approval_publishes(rv: Review, rule_id: str) -> dict | None:
    """What approving this rule publishes (Evals spec §4.1, §6.6), or None for a rule that isn't a column's (page
    rules, record locators, property rules for program-page lines). The column goes into the golden dataset of the
    rule's ruleset: the first approval creates that version with every column approved so far, later ones rewrite it
    with the extra column. A rule with no CTDL term (Learning Type) is approved but not written (`writes` False).
    `now` / `after`: the version's properties before and after (after: with the columns of earlier versions too)."""
    col = next((r for r in property_rules(rv) if r["rule_id"] == rule_id), None)
    if col is None:
        return None
    n = rv.snap.ruleset_version
    now, creates = _version_properties(rv.snap.ctx, n)
    adds = [r["property"] for r in property_rules(rv)
            if r["ctdl_property"] and (r["status"] == "approved" or r["rule_id"] == rule_id)]
    after = _columns_after_approval(rv, col["property"], now, adds) if col["ctdl_property"] else now
    return {"rule_id": rule_id, "property": col["property"], "column": column_name(col["property"], rv.snap.ctx.cls),
            "writes": bool(col["ctdl_property"]), "golden": version_name(n), "ruleset_version": n, "creates": creates,
            "now": now, "after": after, "adds": [p for p in after if p not in now] or [col["property"]],
            "approved": adds}


def request_score(ctx: Ctx, reason: str, columns: list[str] | None = None) -> str:
    """scores-pending.json: a score is due 5 minutes from now (each review moves it on; the server's loop runs it),
    for the columns reviewed since the last one (`columns`, gathered; None: every column)."""
    due = (datetime.now(UTC) + RESCORE_AFTER).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = layout.pending_score(ctx.catalog, ctx.crawl, ctx.cls)
    try:
        before = ctx.root.read_json(path).get("columns", [])
    except FileNotFoundError:
        before = []
    cols = None if columns is None or before is None else sorted(set(before) | set(columns))
    ctx.root.write_json(path, {"due_at": due, "reason": reason, "columns": cols})
    return due


def backfill(ctx: Ctx, to: str, log=print, again: bool = False) -> list[dict]:
    """Rebuild the publications made before golden dataset versions (`pub-…`, merged in place) as versions: each
    ruleset's columns from their lineage (plus every earlier version's: columns only grow), values from the immutable
    extraction they were published from. The old
    entries leave the manifest; their folders stay. `again` also writes every existing version again (oldest first,
    so the newest ends at the latest location), e.g. after the layout changed."""
    old = _old_publications(ctx)
    done = [_backfill_ruleset(ctx, to, items, log) for _, items in sorted(_by_ruleset(old).items())]
    _drop_golden_entries(ctx, {d["publication"] for d, _ in old})
    if again:
        done += _write_versions_again(ctx, to, {d["publication"] for d in done}, log)
    return done


# -- publish ------------------------------------------------------------------------------------------------
def approval(rv: Review) -> tuple[bool, list[dict]]:
    statuses = [{"rule_id": rid, "version": r["version"], "kind": r["kind"], **rv.rule_status(rid)}
                for rid, r in sorted(rv.snap.rules.items(), key=lambda kv: (model.KIND_ORDER[kv[1]["kind"]], kv[0]))]
    return all(s["status"] == "approved" for s in statuses), statuses


def choose(rv: Review, properties: list[str] | None, allow_unapproved: bool = False) -> list[str]:
    """The properties to publish: those asked for (None: every property whose rule is approved). Each needs its
    property rule approved, unless `allow_unapproved` (testing)."""
    rules = {r["property"]: r for r in property_rules(rv)}
    if properties is None:
        chosen = [p for p, r in rules.items() if r["status"] == "approved" or allow_unapproved]
        if not chosen:
            raise UserError("no property's rule is approved yet; approve one on the Rules tab, then publish it")
        return chosen
    unknown = [p for p in properties if p not in rules]
    if unknown:
        raise UserError(f"unknown properties: {', '.join(unknown)} (known: {', '.join(rules)})")
    pending = [p for p in properties if rules[p]["status"] != "approved"]
    if pending and not allow_unapproved:
        names = ", ".join(f"{p} ({rules[p]['rule_id']})" for p in pending)
        raise UserError(f"not approved yet: {names}; a property is published once its rule is approved")
    return [p for p in rules if p in properties]


def _chosen(rv: Review, properties: list[str] | None, allow_unapproved: bool) -> list[str]:
    """`choose`, except that [] asks for no property (only the human-reviewed values)."""
    return choose(rv, properties, allow_unapproved) if properties != [] else []


def _read_publication(ctx: Ctx, gdir: str) -> dict | None:
    try:
        return ctx.read_json(f"{gdir}/publication.json", immutable=False)
    except FileNotFoundError:
        return None


def _columns_kept(ctx: Ctx, rv: Review, chosen: list[str], before: dict | None) -> list[str]:
    """Columns only grow, except a column whose rule was reset since its approval (phase1-followups §4.5)."""
    kept = set(chosen) | set((before or {}).get("properties", [])) | inherited_columns(ctx, rv.snap.ruleset_version)
    return sorted(kept - (rv.withdrawn() - set(chosen)), key=lambda x: model.property_order(ctx.cls).get(x, 99))


def _write_trees(ctx: Ctx, target, n: int, pages: dict[str, list[dict]], latest: bool) -> dict:
    """Every page file of the version's trees (and of the latest location, for the latest version); a page a tree had
    but doesn't now loses its file. Returns the trees."""
    files = trees(pages)
    writes = _stale_pages(ctx, target, n, latest) | _page_files(ctx, n, files, latest)
    with ThreadPoolExecutor(max_workers=16) as pool:
        write_page = telemetry.in_this_request(lambda kv: _write_page(ctx, target, kv[0], kv[1]))
        list(pool.map(write_page, sorted(writes.items())))
    return files


def _stale_pages(ctx: Ctx, target, n: int, latest: bool) -> dict[str, list]:
    """Pages the version's trees (or, at the latest location, any publication to this root) have now: none, until
    `_page_files` says otherwise."""
    stale: dict[str, list] = {}
    for t in TREES:
        stale |= {f"{version_prefix(ctx, n, t)}{s}": [] for s in tree_stems(target, version_prefix(ctx, n, t))}
    if latest:
        stale |= {f"{latest_prefix(ctx)}{s}": [] for s in _stems_written(ctx, target.uri)}
    return stale


def _page_files(ctx: Ctx, n: int, files: dict, latest: bool) -> dict[str, list[dict]]:
    out = {f"{version_prefix(ctx, n, t)}{stem}": records for t in TREES for stem, records in files[t].items()}
    if latest:
        out |= {f"{latest_prefix(ctx)}{stem}": records for stem, records in files[RULE_MATCHED].items()}
    return out


def _write_tables(ctx: Ctx, gdir: str, pub: str, p: dict) -> dict:
    """lineage.parquet and golden.parquet; returns what writing the lineage said (rows, sha256)."""
    for r in p["lineage"]:
        r["publication"] = pub
    info = ctx.write_table(f"{gdir}/lineage.parquet", p["lineage"], model.LINEAGE, if_none_match=False)
    ctx.write_table(f"{gdir}/golden.parquet", golden_rows(ctx, p["pages"]), model.GOLDEN, if_none_match=False)
    return info


def _dated(doc: dict, before: dict | None, published_at: str | None, note: dict | None) -> dict:
    if published_at:
        doc["published_at"] = published_at
    if before:
        doc["created_at"] = before.get("created_at") or before.get("published_at")
    doc.setdefault("created_at", doc["published_at"])
    if note:
        doc.update(note)
    return doc


def _save_publication(ctx: Ctx, gdir: str, doc: dict, to: str, named: bool) -> None:
    ctx.root.write_json(f"{gdir}/publication.json", doc)
    entry = {"publication": doc["publication"], "path": gdir, "to": to, **({"trees": NAMED} if named else {})}
    manifest.update(ctx.root, lambda m: manifest.add_unique(_golden_entries(ctx, m), entry,
                                                              key=lambda g: g["publication"]))
    ctx.invalidate()


def publication_doc(ctx: Ctx, rv: Review, p: dict, pub: str, to: str, by: str, ok: bool, statuses: list[dict],
                    info: dict, properties: list[str] | None = None, files: dict | None = None) -> dict:
    """publication.json: which properties, extraction and ruleset were published, where to, and the gates."""
    props = {r["property"]: r for r in property_rules(rv)}
    chosen = properties if properties is not None else list(props)
    return {"publication": pub, "properties": chosen, "approvals": _approval_counts(p["lineage"]),
            "property_gate": [{k: props[x][k] for k in ("property", "ctdl_property", *GATE_FIELDS)}
                              for x in chosen if x in props],
            "identity_rules": [{k: s[k] for k in GATE_FIELDS} for s in statuses if s["kind"] in ("page", "locator")],
            **_source_and_target(ctx, rv, by, to, files), **_contents(p, info), "format": PAGE_FORMAT,
            "approval_gate": {"all_rules_approved": ok, "rules": [{k: s[k] for k in GATE_FIELDS} for s in statuses]}}


def _approval_counts(lineage: list[dict]) -> dict:
    counts: dict[str, Counter] = defaultdict(Counter)
    for row in lineage:
        counts[row["property"]][row["approval"]] += 1
    return {"human": sum(c["human"] for c in counts.values()), "rule": sum(c["rule"] for c in counts.values()),
            "by_property": {prop: {"human": c["human"], "rule": c["rule"]} for prop, c in counts.items()},
            "meaning": APPROVAL_MEANING}


def _source_and_target(ctx: Ctx, rv: Review, by: str, to: str, files: dict | None) -> dict:
    n = rv.snap.ruleset_version
    return {"catalog": ctx.catalog, "crawl": ctx.crawl, "extraction": rv.snap.ext, "ruleset_version": n,
            "published_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "published_by": by, "to": to,
            "to_prefix": latest_prefix(ctx), "version_prefix": version_prefix(ctx, n),
            "trees": {t: {"prefix": version_prefix(ctx, n, t), "pages": len((files or {}).get(t, {}))} for t in TREES}}


def _contents(p: dict, info: dict) -> dict:
    return {"pages": len(p["pages"]), "page_stems": sorted(p["pages"]), "courses": p["courses"],
            "records": p["records"], "lineage_rows": info["rows"], "lineage_sha256": info["sha256"],
            "golden_record_id_collisions": p["collisions"],
            "skipped_no_record_external_identifier": p["skipped_no_record_external_identifier"]}


# -- one page, after a verdict --------------------------------------------------------------------------------
def _create_golden(ctx: Ctx, reason: str, by: str, column: str | None) -> dict:
    doc = publish(ctx, default_target(ctx), by, properties=[])
    due = request_score(ctx, reason, [column] if column else None)
    return {"publication": doc["publication"], "created": True, "files": doc["pages"], "due_at": due}


def _rewrite_page(ctx: Ctx, n: int, doc: dict, stem: str) -> list[str]:
    """The page's files in both trees of version `n` and at the latest location, rewritten where they changed."""
    rv = LOADER.review(ctx, doc["extraction"])
    files = trees({stem: plan(rv, set(doc["properties"]), stems={stem})["pages"].get(stem, [])})
    target = open_root(doc["to"])
    folders = ((f"{version_prefix(ctx, n, RULE_MATCHED)}{stem}", files[RULE_MATCHED].get(stem)),
               (f"{version_prefix(ctx, n, HUMAN_REVIEWED)}{stem}", files[HUMAN_REVIEWED].get(stem)),
               (f"{latest_prefix(ctx)}{stem}", files[RULE_MATCHED].get(stem)))
    return [f"{folder}/{stem}.json" for folder, records in folders
            if _rewrite_if_changed(ctx, target, folder, stem, records)]


def _rewrite_if_changed(ctx: Ctx, target, folder: str, stem: str, records: list[dict] | None) -> bool:
    try:
        old = target.read_text(f"{folder}/{stem}.json")
    except FileNotFoundError:
        old = None
    if old == (page_json(records) if records else None):
        return False
    _write_page(ctx, target, folder, records or [])
    return True


# -- after an approval ------------------------------------------------------------------------------------------
def _version_properties(ctx: Ctx, n: int) -> tuple[list[str], bool]:
    """The properties version `n` has now, and whether publishing creates it."""
    try:
        doc = ctx.read_json(f"{layout.golden_dir(ctx.catalog, ctx.crawl, ctx.cls, version_name(n))}/publication.json",
                            immutable=False)
    except FileNotFoundError:
        return [], True
    return doc.get("properties") or [], False


def _columns_after_approval(rv: Review, prop: str, now: list[str], adds: list[str]) -> list[str]:
    columns = set(now) | set(adds) | inherited_columns(rv.snap.ctx, rv.snap.ruleset_version)
    return sorted(columns - (rv.withdrawn() - {prop}), key=lambda x: model.property_order(rv.snap.ctx.cls).get(x, 99))


# -- backfill ---------------------------------------------------------------------------------------------------
def _old_publications(ctx: Ctx) -> list[tuple[dict, set[str]]]:
    """Publications from before versions, each with the properties its lineage has."""
    import pyarrow.parquet as pq

    old = []
    for g in ctx.crawl_class().get("golden", []):
        if VERSION.match(g["publication"]):
            continue
        d = ctx.read_json(f"{g['path']}/publication.json", immutable=False)
        cols = set(pq.read_table(ctx.root.local_path(f"{g['path']}/lineage.parquet", mutable=True),
                                 columns=["property"]).column("property").to_pylist())
        old.append((d, cols))
    return old


def _by_ruleset(old: list[tuple[dict, set[str]]]) -> dict[int, list]:
    by_ruleset: dict[int, list] = defaultdict(list)
    for d, cols in sorted(old, key=lambda x: x[0].get("published_at") or ""):
        by_ruleset[d["ruleset_version"]].append((d, cols))
    return by_ruleset


def _backfill_ruleset(ctx: Ctx, to: str, items: list[tuple[dict, set[str]]], log) -> dict:
    last = items[-1][0]
    cols = sorted(set().union(*(c for _, c in items)), key=lambda x: model.property_order(ctx.cls).get(x, 99))
    doc = publish(ctx, to, last["published_by"], allow_unapproved=True, properties=cols, ext=last["extraction"],
                  published_at=last["published_at"], note={"backfilled_from": [d["publication"] for d, _ in items]})
    log(f"{doc['publication']} ({', '.join(doc['properties'])}) from {', '.join(d['publication'] for d, _ in items)}: "
        f"{doc['pages']:,} pages, {doc['records']:,} records, {doc['lineage_rows']:,} values "
        f"({doc['approvals']['human']:,} human-reviewed)")
    return doc


def _drop_golden_entries(ctx: Ctx, gone: set[str]) -> None:
    def change(m: dict) -> None:
        k = manifest.crawl_class(manifest.crawl_entry(manifest.catalog_entry(m, ctx.catalog), ctx.crawl), ctx.cls)
        k["golden"] = [g for g in k["golden"] if g["publication"] not in gone]

    manifest.update(ctx.root, change)
    ctx.invalidate()


def _write_versions_again(ctx: Ctx, to: str, skip: set[str], log) -> list[dict]:
    done = []
    for _, g in sorted(versions(ctx).items()):
        if g["publication"] in skip:
            continue
        d = ctx.read_json(f"{g['path']}/publication.json", immutable=False)
        doc = publish(ctx, to, d["published_by"], allow_unapproved=True, properties=d.get("properties") or [],
                      ext=d["extraction"], published_at=d["published_at"],
                      note={k: d[k] for k in ("backfilled_from",) if k in d})
        log(f"{doc['publication']} ({', '.join(doc['properties'])}) written again: "
            f"{doc['trees'][RULE_MATCHED]['pages']:,} rule-matched pages, "
            f"{doc['trees'][HUMAN_REVIEWED]['pages']:,} human-reviewed, {doc['lineage_rows']:,} values "
            f"({doc['approvals']['human']:,} human-reviewed)")
        done.append(doc)
    return done


# =====================================================================================================
# The plan: what a publication writes
# =====================================================================================================
def plan(rv: Review, properties: set[str] | None = None, stems: set[str] | None = None) -> dict:
    """Everything a publication would write for these properties (None: all), without writing it. Human-reviewed
    values are in it whatever their property. `stems`: only these pages (a verdict rewrites one page's file; working
    out the whole catalog took ~10 s a verdict on Marshall). A page's rows get the same states either way: the rows
    of other pages only re-attach annotations to their own course and page."""
    ids, collisions = golden_record_ids(rv)
    planning = _planning(rv, properties, stems)
    book = _GoldenPages()
    for key, o in _occurrences_in_page_order(rv.snap, stems):
        gid = ids.get(key)
        if gid is None:
            book.skipped_no_key += 1
            continue
        fields, rows = _course_values(planning, key, o, gid)
        if properties is None or fields:  # else nothing of the chosen properties for this course
            book.add(o["page_stem"], gid, fields, rows)
    return {"pages": dict(book.pages), "lineage": book.lineage, "collisions": collisions,
            "skipped_no_record_external_identifier": book.skipped_no_key,
            "courses": len({r["golden_record_id"] for r in book.lineage}), "records": sum(map(len, book.pages.values()))}


@dataclass
class _Planning:
    """What every course's values are planned with."""
    rv: Review
    properties: set[str] | None
    place: dict            # property → its place in the class's order, read once (it checks the properties file)
    annotation_ids: dict   # (rule, occurrence) → the annotations on it
    states: dict           # rule → occurrence_key → its row's state
    human_at: dict         # (rule, occurrence) → value_index → the expert's verdict that makes it human-reviewed
    statuses: dict         # rule → its status (who approved it), for the properties asked for
    answered: dict         # occurrence_key → rules with no found value that still publish a reviewer's answer


def _planning(rv: Review, properties: set[str] | None, stems: set[str] | None) -> _Planning:
    planning = _Planning(rv, properties, model.property_order(rv.snap.ctx.cls), _annotation_ids(rv), {},
                         defaultdict(dict), {}, {})
    for rid, r in rv.snap.rules.items():
        if r["kind"] == "property":
            _review_rule(planning, rid, r, stems)
    planning.answered = _answered(planning.states)
    return planning


def _annotation_ids(rv: Review) -> dict[tuple, list[str]]:
    ids = defaultdict(list)
    for e in rv.live:
        t = e["target"]
        if t.get("rule_id") and t.get("occurrence_key"):
            ids[(t["rule_id"], t["occurrence_key"])].append(e["annotation_id"])
    return ids


def _review_rule(planning: _Planning, rid: str, rule: dict, stems: set[str] | None) -> None:
    """Who approved each of the rule's values: an expert who confirmed it (on the Rules or Records tab), else the
    rule's approval."""
    rv = planning.rv
    rows = rv.snap.rows(rid) if stems is None else rv.snap.rows_on(rid, stems)
    states = rv.row_states(rid, rows, stems)
    planning.states[rid] = {row["occurrence_key"]: states[row["key"]] for row in rows if row.get("occurrence_key")}
    for row in rows:
        _note_human(planning.human_at, rid, row, states[row["key"]])
    if planning.properties is None or rule.get("property_label") in planning.properties:
        # a rule's status needs every row's state (and is cached across Reviews): only the whole rule's states
        planning.statuses[rid] = rv.rule_status(rid, states if stems is None else None)


def _note_human(human_at: dict, rid: str, row: dict, st) -> None:
    if row.get("items") is not None:  # a list: each item's own expert ✓ (property-rules spec §4.4)
        for it in row["items"]:
            x = st.items.get(norm(it["value"]))
            if x is not None and x.human:
                human_at[(rid, row["occurrence_key"])][it["value_index"]] = x.human
    elif st.human:
        human_at[(rid, row["occurrence_key"])][0] = st.human


def _answered(states: dict[str, dict]) -> dict[str, set[str]]:
    """The reviewers' answers (sme-fixes §5.4, §6, §7, golden_answers.py): the rows where the rule found nothing that
    still publish something (a ✕ with an answer, a ✓ on "nothing found")."""
    answered: dict[str, set[str]] = defaultdict(set)
    for rid, by_occurrence in states.items():
        for k, st in by_occurrence.items():
            if golden_answers.wants_row(st):
                answered[k].add(rid)
    return answered


def _occurrences_in_page_order(snap, stems: set[str] | None) -> list[tuple[str, dict]]:
    occurrences = snap.occurrences.items() if stems is None else \
        ((k, o) for k, o in snap.occurrences.items() if o["page_stem"] in stems)
    return sorted(occurrences, key=lambda kv: (kv[1]["page_stem"], kv[1]["locator_index"]))


def _course_values(planning: _Planning, key: str, o: dict, gid: str) -> tuple[list[dict], list[dict]]:
    """One course's golden fields, and the lineage row of each."""
    snap = planning.rv.snap
    url = snap.page[o["page_stem"]]["url"]
    fields, rows = [], []
    for rid in _rules_with_values(planning, key):
        rule = snap.rules[rid]
        for g in _golden_values(planning, rid, rule, key, o):
            approved = {k: g[k] for k in APPROVAL_FIELDS}
            fields.append({"ctdl_property": rule.get("ctdl_property"), "property": rule["property_label"],
                           "value": g["value"], **({"absent": True} if g.get("absent") else {}),
                           "source_url": url, "location": g["location"], **approved})
            rows.append(_lineage_row(planning, snap, rid, rule, key, o, gid, g) | approved)
    return fields, rows


def _rules_with_values(planning: _Planning, key: str) -> list[str]:
    snap = planning.rv.snap
    return sorted(set(snap.items_by_occ[key]) | planning.answered.get(key, set()), key=lambda rid: (
        planning.place.get(snap.rules[rid].get("property_label"), 99), rid))


def _golden_values(planning: _Planning, rid: str, rule: dict, key: str, o: dict):
    status = planning.statuses.get(rid, {})
    rule_ok = {"approval": "rule", "approved_by": status.get("approved_by"), "approved_at": status.get("approved_at")}
    in_column = planning.properties is None or rule.get("property_label") in planning.properties
    return golden_answers.fields(rule, planning.rv.snap.items_by_occ[key].get(rid, []),
                                 planning.states.get(rid, {}).get(key), o["css_path"],
                                 planning.human_at.get((rid, key), {}), rule_ok, in_column)


def _lineage_row(planning: _Planning, snap, rid: str, rule: dict, key: str, o: dict, gid: str, g: dict) -> dict:
    return {"golden_record_id": gid, "page_stem": o["page_stem"], "property": rule["property_label"],
            "ctdl_property": rule.get("ctdl_property"), "extraction": snap.ext, "rule_id": rid,
            "rule_version": rule["version"], "occurrence_key": key, "match_value_index": g["match_value_index"],
            "annotation_ids": sorted(planning.annotation_ids.get((rid, key), []))}


class _GoldenPages:
    """The pages' records as they are planned, and their lineage."""

    def __init__(self) -> None:
        self.pages: dict[str, list[dict]] = defaultdict(list)
        self.lineage: list[dict] = []
        self.skipped_no_key = 0
        self._used: Counter = Counter()  # (golden_record_id, page_stem, property) → values already published
        self._seen: dict[tuple, list[dict]] = defaultdict(list)  # (page, golden_record_id) → its records there

    def add(self, stem: str, gid: str, fields: list[dict], rows: list[dict]) -> None:
        record = _record(gid, fields)
        if any(r == record for r in self._seen[(stem, gid)]):
            return  # the same course listed twice on a page with identical values: once is enough
        self._seen[(stem, gid)].append(record)
        # A second, different record with the same golden_record_id on the same page: its values get the next value_index.
        for row in rows:
            row["value_index"] = self._used[(gid, stem, row["property"])]
            self._used[(gid, stem, row["property"])] += 1
        self.pages[stem].append(record)
        self.lineage.extend(rows)


def golden_record_ids(rv: Review) -> tuple[dict[str, str], list[dict]]:
    """occurrence_key → golden_record_id, and the collisions (codes whose course pages name different courses)."""
    names, occ_name = _record_names(rv.snap)
    variant, collisions = _name_variants(names)
    ids = {key: variant.get((o["record_external_identifier"], _name_key(occ_name[key])), o["record_external_identifier"])
           for key, o in rv.snap.occurrences.items() if o["record_external_identifier"] is not None}
    return ids, collisions


def _record_names(snap) -> tuple[dict[str, dict[str, str]], dict[str, str | None]]:
    """Each occurrence's name, and each record's names on its own pages (normalized name → as shown)."""
    full = properties.record_locator(snap.rules, snap.ctx.cls)
    names: dict[str, dict[str, str]] = defaultdict(dict)
    occ_name = {}
    for o in snap.occurrences.values():
        name = occ_name[o["occurrence_key"]] = _found_name(snap, o)
        key = o["record_external_identifier"]
        if key and o["locator_rule_id"] == full and name:
            names[key].setdefault(_name_key(name), name)
    return names, occ_name


def _found_name(snap, o: dict) -> str | None:
    name_rule = snap.name_rule.get(o["locator_rule_id"])
    m = snap.matches_by_occ[o["occurrence_key"]].get(name_rule) if name_rule else None
    return m["value"] if m and m["status"] == "found" else None


def _name_variants(names: dict[str, dict[str, str]]) -> tuple[dict[tuple, str], list[dict]]:
    """`<identifier>~<n>` for each name of an identifier whose pages name different courses, and those collisions."""
    variant, collisions = {}, []
    for ck, by_name in sorted(names.items()):
        if len(by_name) > 1:
            keys = sorted(by_name)
            variant.update({(ck, k): f"{ck}~{i}" for i, k in enumerate(keys, 1)})
            collisions.append({"record_external_identifier": ck,
                               "golden_record_ids": [f"{ck}~{i}" for i in range(1, len(keys) + 1)],
                               "names": [by_name[k] for k in keys]})
    return variant, collisions


def property_rules(rv: Review) -> list[dict]:
    """Each property the property rules fill, with its rule and status (for the full courses' locator, i.e. the
    course pages)."""
    out = []
    place, full = model.property_order(rv.snap.ctx.cls), properties.record_locator(rv.snap.rules, rv.snap.ctx.cls)
    for rid, r in sorted(rv.snap.rules.items(), key=lambda kv: (place.get(kv[1].get("property_label"), 99), kv[0])):
        if r["kind"] != "property" or r["definition"].get("locator") != full:
            continue
        st = rv.rule_status(rid)
        out.append({"property": r["property_label"], "ctdl_property": r.get("ctdl_property"), "rule_id": rid,
                    "version": r["version"], "status": st["status"], "approved_by": st.get("approved_by")})
    return out


# =====================================================================================================
# Trees, files and what was published
# =====================================================================================================
def trees(pages: dict[str, list[dict]]) -> dict[str, dict[str, list[dict]]]:
    """{tree: pages}: the human-reviewed tree is the `approval: human` subset of the rule-matched one."""
    rule, _ = tree_pages(pages, RULE_MATCHED)
    return {RULE_MATCHED: rule, HUMAN_REVIEWED: tree_pages(rule, HUMAN_REVIEWED)[0]}


def tree_pages(pages: dict[str, list[dict]], tree: str) -> tuple[dict[str, list[dict]], list[dict]]:
    """The pages as one tree holds them (`rule-matched`: every value with a CTDL term; `human-reviewed`: only the
    `approval: human` ones), and the pages left out (with why). The scorer pairs a page's records with the extract's
    by position and rejects a record with no values: trailing empty records are dropped, and a page whose empty record
    comes before a non-empty one is left out."""
    out, left_out = {}, []
    for stem, records in pages.items():
        recs = _tree_records(records, tree)
        if not recs:
            continue
        if any(not r["fields"] for r in recs):
            why = "rule-matched" if tree == RULE_MATCHED else "human-reviewed"
            left_out.append({"stem": stem, "why": f"an earlier course on the page has no {why} values"})
            continue
        out[stem] = recs
    return out, left_out


def _tree_records(records: list[dict], tree: str) -> list[dict]:
    """The page's records with the tree's values only, trailing empty records dropped."""
    recs = [_record(r.get("golden_record_id"),
                    [f for f in r.get("fields", [])
                     if f.get("ctdl_property") and (tree == RULE_MATCHED or f.get("approval") == "human")])
            for r in records]
    while recs and not recs[-1]["fields"]:
        recs.pop()
    return recs


def tree_stems(target, prefix: str) -> list[str]:
    """The pages that have a file below `prefix`."""
    prefix = prefix.rstrip("/")
    out = []
    for p in target.list(prefix):
        parts = p[len(prefix) + 1:].split("/")
        if len(parts) == 2 and parts[1] == f"{parts[0]}.json":
            out.append(parts[0])
    return out


def golden_rows(ctx: Ctx, pages: dict[str, list[dict]]) -> list[dict]:
    """golden.parquet: one row per value of the page files."""
    out = []
    for stem, records in sorted(pages.items()):
        index: Counter = Counter()  # value_index per (golden_record_id, property) across the page's records
        for rec in records:
            for f in rec["fields"]:
                k = (rec["golden_record_id"], f["property"])
                out.append(_golden_row(ctx, stem, rec["golden_record_id"], f, index[k]))
                index[k] += 1
    return out


def _golden_row(ctx: Ctx, stem: str, gid: str, f: dict, value_index: int) -> dict:
    is_object = isinstance(f["value"], dict)  # a list of objects' object (§5.4): JSON text, its key field's place
    loc = f["location"]
    if is_object and loc:
        loc = next(iter(loc.values()), None)
    return {"catalog": ctx.catalog, "crawl": ctx.crawl, "stem": stem, "golden_record_id": gid,
            "property": f["property"], "ctdl_property": f["ctdl_property"], "value_index": value_index,
            "value": model.canon(f["value"]) if is_object else f["value"],
            "source_url": f["source_url"], "location": loc, "approval": f["approval"],
            "approved_by": f["approved_by"], "approved_at": f["approved_at"]}


def _write_page(ctx: Ctx, target, folder: str, records: list[dict]) -> None:
    """One page's file in `folder` (`…/<stem>`), or none when it has no records. The page's HTML goes only to the
    latest location; version trees are JSON only."""
    stem = folder.rsplit("/", 1)[1]
    html = f"{folder}/{stem}.html" if folder.startswith(latest_prefix(ctx)) else None
    if records:
        target.write_text(f"{folder}/{stem}.json", page_json(records))
        if html:
            _copy_html(ctx, target, html, stem)
    else:
        target.delete(f"{folder}/{stem}.json")
        if html:
            target.delete(html)


def _copy_html(ctx: Ctx, target, path: str, stem: str) -> None:
    if target.stat(path) is not None:
        return
    src = layout.page_html(ctx.catalog, ctx.crawl, stem)
    crawls = ctx.crawl_root
    if isinstance(target, AzureRoot) and isinstance(crawls, AzureRoot) and target.account == crawls.account:
        target.copy_from_url(path, crawls.blob_url_with_sas(src))  # server-side, nothing downloaded
    else:
        target.write_file(path, ctx.page_path(stem))


def page_json(records: list[dict]) -> str:
    """The text of one <page_stem>.json, exactly as written."""
    return json.dumps(records, indent=2, ensure_ascii=False) + "\n"


def published_properties(ctx: Ctx, to: str) -> dict[str, dict]:
    """property → the latest publication to `to` that published it (publications before per-property publishing
    published every property)."""
    out: dict[str, dict] = {}
    for d in sorted(_publications_to(ctx, to), key=lambda d: d.get("published_at") or ""):
        for prop in _published_in(d):
            gate = next((r for r in d.get("property_gate", []) if r["property"] == prop), {})
            out[prop] = {"publication": d["publication"], "published_at": d.get("published_at"),
                         "published_by": d.get("published_by"), "extraction": d.get("extraction"),
                         "rule_version": gate.get("version")}
    return out


def _published_in(d: dict) -> list[str]:
    return d.get("properties") or [r["property"] for r in d.get("property_gate", [])] \
        or list(model.FIRST_EIGHT_ORDER)  # before the property list: the eight


def _stems_written(ctx: Ctx, to: str) -> set[str]:
    """Pages any publication to `to` wrote at the latest location."""
    return {stem for d in _publications_to(ctx, to) for stem in d.get("page_stems", [])}


def _publications_to(ctx: Ctx, to: str) -> list[dict]:
    """publication.json of every publication to `to` the manifest lists (those still there)."""
    docs = []
    for g in ctx.crawl_class().get("golden", []):
        if g.get("to", "").rstrip("/") == to.rstrip("/"):
            try:
                docs.append(ctx.read_json(f"{g['path']}/publication.json", immutable=False))
            except FileNotFoundError:
                continue
    return docs


def inherited_columns(ctx: Ctx, ruleset_version: int) -> set[str]:
    """The columns (properties) published in the golden datasets of earlier rulesets: every later version has them
    too, its values from its own ruleset's extraction (columns only grow, Evals spec §1 rows 3, 16)."""
    out: set[str] = set()
    for v, g in versions(ctx).items():
        if v < ruleset_version:
            try:
                out |= set(ctx.read_json(f"{g['path']}/publication.json", immutable=False).get("properties") or [])
            except FileNotFoundError:
                continue
    return out


def versions(ctx: Ctx) -> dict[int, dict]:
    """ruleset version → its golden dataset's manifest entry ({publication, path, to})."""
    out = {}
    for g in ctx.crawl_class().get("golden", []):
        m = VERSION.match(g["publication"])
        if m:
            out[int(m.group(1))] = g
    return out


# =====================================================================================================
# Paths and names
# =====================================================================================================
def default_target(ctx: Ctx) -> str:
    """Where the Studio publishes: GOLDEN_DATASETS_GOLDEN_ROOT if set (a local folder or a scratch prefix); else, for
    a local Studio root, the folder `golden` beside it (so development never writes to the shared container); else
    the xtra-golden-sets container."""
    if os.environ.get("GOLDEN_DATASETS_GOLDEN_ROOT"):
        return os.environ["GOLDEN_DATASETS_GOLDEN_ROOT"]
    if isinstance(ctx.root, LocalRoot):
        return str(Path(ctx.root.base).parent / "golden")
    return GOLDEN_CONTAINER


def version_root(ctx: Ctx, ruleset_version: int, tree: str = RULE_MATCHED) -> str:
    """What `xtra score --baseline-uri` points at (below the golden root) to score one tree of a version."""
    folder = TREE_DIRS[tree] if named_trees(ctx, ruleset_version) else tree
    return f"{class_prefix(ctx)}catalogs/{ctx.catalog}/versions/{version_name(ruleset_version)}/{folder}"


def version_prefix(ctx: Ctx, ruleset_version: int, tree: str = RULE_MATCHED) -> str:
    return f"{version_root(ctx, ruleset_version, tree)}/{ctx.catalog}/{ctx.crawl}/"


def latest_prefix(ctx: Ctx) -> str:
    return f"{class_prefix(ctx)}{ctx.catalog}/{ctx.crawl}/"


def class_prefix(ctx: Ctx) -> str:
    """A class's part of the golden root: Course keeps the paths xtra-cli reads today; every other class sits under
    its own folder, so its page files never meet Course's (`learningprogram/<catalog>/<crawl>/…`)."""
    return "" if ctx.cls == "course" else f"{ctx.cls}/"


def named_trees(ctx: Ctx, ruleset_version: int) -> bool:
    """Whether this version's trees are stored as golden/ and silver/ (a version not written yet will be)."""
    g = versions(ctx).get(ruleset_version)
    return g is None or g.get("trees") == NAMED


def version_name(ruleset_version: int) -> str:
    return f"ruleset-v{ruleset_version}"


def column_name(prop: str, cls: str = "course") -> str | None:
    """A property's column: its CTDL path without prefixes (None for one with no CTDL term, e.g. Learning Type)."""
    term = model.ctdl_term(cls).get(prop)
    return ">".join(t.split(":", 1)[-1] for t in term.split(">")) if term else None


def columns_of(props: list[str], cls: str = "course") -> list[str]:
    """The columns of these properties, in display order; properties with no CTDL term aren't columns."""
    return [c for c in (column_name(p, cls) for p in sorted(props, key=lambda x: model.property_order(cls).get(x, 99))) if c]


def record_approval(fields: list[dict]) -> str:
    """A record's approval from its fields': human (every value confirmed by a person), rule (none), or mixed."""
    kinds = {f.get("approval", "rule") for f in fields}
    return "human" if kinds == {"human"} else "rule" if kinds <= {"rule"} else "mixed"


def _record(gid: str, fields: list[dict]) -> dict:
    return {"golden_record_id": gid, "approval": record_approval(fields), "fields": fields}


def _golden_entries(ctx: Ctx, m: dict) -> list[dict]:
    return manifest.crawl_class(manifest.crawl_entry(manifest.catalog_entry(m, ctx.catalog), ctx.crawl), ctx.cls)["golden"]


def _name_key(v: str | None) -> str:
    return re.sub(r"\s+", " ", v or "").strip().lower()
