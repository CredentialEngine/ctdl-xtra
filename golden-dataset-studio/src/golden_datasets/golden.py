"""`golden-datasets golden publish`: the golden dataset and its lineage (spec §4.2 golden_id, §5.6, §7.6).

The output keeps the existing shape of `xtra-golden-sets-verified`, so its readers keep working:

    <golden root>/<catalog>/<crawl>/<page_stem>/<page_stem>.json   [{golden_id, fields: [{ctdl_property, property,
                                                                      value, source_url, location}]}]
    <golden root>/<catalog>/<crawl>/<page_stem>/<page_stem>.html   the page as crawled

It is domain-only: no rule ids, occurrence keys or annotation ids. The Studio keeps the lineage, which traces every
golden value back to its match, rule version and annotations:

    <studio root>/<catalog>/<crawl>/golden-dataset-studio/golden/<publication>/{publication.json, lineage.parquet}

Every course found on a page is published, course pages and program-page course lines alike. `golden_id` is the
`course_key`, unless the course pages with that code name different courses (Marshall, WVU): then each distinct
name gets `course_key~<n>`, and the Golden screen lists them for confirmation.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime

from . import layout, manifest, model
from .context import Ctx
from .errors import ConflictError, UserError
from .review import LOADER, Review
from .storage import AzureRoot, open_root

FULL_LOCATOR = "locator-course-page"


def _name_key(v: str | None) -> str:
    return re.sub(r"\s+", " ", v or "").strip().lower()


def golden_ids(rv: Review) -> tuple[dict[str, str], list[dict]]:
    """occurrence_key → golden_id, and the collisions (codes whose course pages name different courses)."""
    snap = rv.snap
    names: dict[str, dict[str, str]] = defaultdict(dict)  # course_key → {normalized name: display name}
    occ_name = {}
    for o in snap.occurrences.values():
        name_rule = snap.name_rule.get(o["locator_rule_id"])
        m = snap.matches_by_occ[o["occurrence_key"]].get(name_rule) if name_rule else None
        occ_name[o["occurrence_key"]] = m["value"] if m and m["status"] == "found" else None
        if o["course_key"] and o["locator_rule_id"] == FULL_LOCATOR and occ_name[o["occurrence_key"]]:
            names[o["course_key"]].setdefault(_name_key(occ_name[o["occurrence_key"]]), occ_name[o["occurrence_key"]])
    variant = {}
    collisions = []
    for ck, by_name in sorted(names.items()):
        if len(by_name) > 1:
            keys = sorted(by_name)
            for i, k in enumerate(keys, 1):
                variant[(ck, k)] = f"{ck}~{i}"
            collisions.append({"course_key": ck, "golden_ids": [f"{ck}~{i}" for i in range(1, len(keys) + 1)],
                               "names": [by_name[k] for k in keys]})
    out = {}
    for key, o in snap.occurrences.items():
        ck = o["course_key"]
        if ck is None:
            continue
        out[key] = variant.get((ck, _name_key(occ_name[key])), ck)
    return out, collisions


def plan(rv: Review) -> dict:
    """Everything a publication would write, without writing it."""
    snap = rv.snap
    ids, collisions = golden_ids(rv)
    ann = defaultdict(list)
    for e in rv.live:
        t = e["target"]
        if t.get("rule_id") and t.get("occurrence_key"):
            ann[(t["rule_id"], t["occurrence_key"])].append(e["annotation_id"])
    pages: dict[str, list[dict]] = defaultdict(list)
    lineage: list[dict] = []
    skipped_no_key = 0
    used: Counter = Counter()  # (golden_id, page_stem, property) → values already published
    for key, o in sorted(snap.occurrences.items(), key=lambda kv: (kv[1]["page_stem"], kv[1]["locator_index"])):
        gid = ids.get(key)
        if gid is None:
            skipped_no_key += 1
            continue
        stem = o["page_stem"]
        url = snap.page[stem]["url"]
        fields, rows = [], []
        for rid, m in sorted(snap.matches_by_occ[key].items(),
                             key=lambda kv: (model.PROPERTY_ORDER.get(snap.rules[kv[0]].get("property_label"), 99), kv[0])):
            if m["status"] != "found":
                continue
            r = snap.rules[rid]
            loc = ({"css_path": m["full_css_path"], "char_start": m["char_start"], "char_end": m["char_end"]}
                   if m["css_path"] is not None else None)
            fields.append({"ctdl_property": r.get("ctdl_property"), "property": r["property_label"],
                           "value": m["value"], "source_url": url, "location": loc})
            rows.append({"golden_id": gid, "page_stem": stem, "property": r["property_label"],
                         "ctdl_property": r.get("ctdl_property"), "extraction": snap.ext, "rule_id": rid,
                         "rule_version": m["rule_version"], "occurrence_key": key, "match_value_index": m["value_index"],
                         "annotation_ids": sorted(ann.get((rid, key), []))})
        record = {"golden_id": gid, "fields": fields}
        if any(r["golden_id"] == gid and r == record for r in pages[stem]):
            continue  # the same course listed twice on a page with identical values: once is enough
        # A second, different record with the same golden_id on the same page: its values get the next value_index.
        for row in rows:
            row["value_index"] = used[(gid, stem, row["property"])]
            used[(gid, stem, row["property"])] += 1
        pages[stem].append(record)
        lineage.extend(rows)
    return {"pages": dict(pages), "lineage": lineage, "collisions": collisions, "skipped_no_course_key": skipped_no_key,
            "courses": len({r["golden_id"] for r in lineage}), "records": sum(len(v) for v in pages.values())}


def approval(rv: Review) -> tuple[bool, list[dict]]:
    statuses = [{"rule_id": rid, "version": r["version"], "kind": r["kind"], **rv.rule_status(rid)}
                for rid, r in sorted(rv.snap.rules.items(), key=lambda kv: (model.KIND_ORDER[kv[1]["kind"]], kv[0]))]
    return all(s["status"] == "approved" for s in statuses), statuses


GOLDEN_CONTAINER = "azure://https://ceteststorage.blob.core.windows.net/xtra-golden-sets-verified"


def default_target(ctx: Ctx) -> str:
    """Where the UI publishes: the xtra-golden-sets-verified container, unless GOLDEN_DATASETS_GOLDEN_ROOT names
    another root (a local folder or a scratch prefix, for trying a publication out)."""
    import os

    return os.environ.get("GOLDEN_DATASETS_GOLDEN_ROOT") or GOLDEN_CONTAINER


def publication_name(ctx: Ctx, rv: Review) -> str:
    """pub-<today>-<catalog short>-<extraction>, with -2, -3… when that name is taken."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    short = ctx.catalog.split("-")[0] if ctx.catalog.startswith("catalog-") is False else ctx.catalog.split("-")[1]
    existing = {g["publication"] for g in ctx.crawl_entry().get("golden", [])}
    pub = f"pub-{today}-{short}-{rv.snap.ext}"
    n = 2
    while pub in existing:
        pub = f"pub-{today}-{short}-{rv.snap.ext}-{n}"
        n += 1
    return pub


def page_json(records: list[dict]) -> str:
    """The text of one <page_stem>.json, exactly as written."""
    return json.dumps(records, indent=2, ensure_ascii=False) + "\n"


def publication_doc(ctx: Ctx, rv: Review, p: dict, pub: str, to: str, by: str, ok: bool, statuses: list[dict],
                    info: dict) -> dict:
    """publication.json: which extraction and ruleset were published, where to, and the approval gate."""
    return {"publication": pub, "catalog": ctx.catalog, "crawl": ctx.crawl, "extraction": rv.snap.ext,
            "ruleset_version": rv.snap.ruleset_version, "published_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "published_by": by, "to": to, "to_prefix": f"{ctx.catalog}/{ctx.crawl}/", "pages": len(p["pages"]),
            "page_stems": sorted(p["pages"]), "courses": p["courses"], "records": p["records"],
            "lineage_rows": info["rows"], "lineage_sha256": info["sha256"],
            "golden_id_collisions": p["collisions"], "skipped_no_course_key": p["skipped_no_course_key"],
            "format": "xtra-golden-sets-verified per-page shape: <catalog>/<crawl>/<stem>/<stem>.json = "
                      "[{golden_id, fields: [{ctdl_property, property, value, source_url, location}]}], "
                      "plus <stem>.html as crawled",
            "approval_gate": {"all_rules_approved": ok,
                              "rules": [{k: s[k] for k in ("rule_id", "version", "status", "approved_by")}
                                        for s in statuses]}}


def publish(ctx: Ctx, to: str, by: str, allow_unapproved: bool = False, log=print) -> dict:
    rv = LOADER.review(ctx)
    ok, statuses = approval(rv)
    if not ok and not allow_unapproved:
        pending = [s["rule_id"] for s in statuses if s["status"] != "approved"]
        raise UserError(f"{len(pending)} rule(s) not approved: {', '.join(pending)}; publish needs every rule approved")
    p = plan(rv)
    target = open_root(to)
    pub = publication_name(ctx, rv)
    prefix = f"{ctx.catalog}/{ctx.crawl}/"
    from concurrent.futures import ThreadPoolExecutor

    def write_page(item) -> None:
        stem, records = item
        target.write_text(f"{prefix}{stem}/{stem}.json", page_json(records))
        html_path = f"{prefix}{stem}/{stem}.html"
        if target.stat(html_path) is None:
            src = layout.page_html(ctx.catalog, ctx.crawl, stem)
            if isinstance(target, AzureRoot) and isinstance(ctx.root, AzureRoot) and target.account == ctx.root.account:
                target.copy_from_url(html_path, ctx.root.blob_url_with_sas(src))  # server-side, nothing downloaded
            else:
                target.write_file(html_path, ctx.page_path(stem))

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(write_page, sorted(p["pages"].items())))
    for r in p["lineage"]:
        r["publication"] = pub
    gdir = layout.golden_dir(ctx.catalog, ctx.crawl, pub)
    info = ctx.write_table(f"{gdir}/lineage.parquet", p["lineage"], model.LINEAGE)
    doc = publication_doc(ctx, rv, p, pub, target.uri, by, ok, statuses, info)
    try:
        ctx.root.write_json(f"{gdir}/publication.json", doc, if_none_match=True)
    except ConflictError:
        raise UserError(f"{pub} exists already") from None

    def change(m: dict) -> None:
        k = manifest.crawl_entry(manifest.catalog_entry(m, ctx.catalog), ctx.crawl)
        manifest.add_unique(k.setdefault("golden", []), {"publication": pub, "path": gdir, "to": target.uri},
                            key=lambda g: g["publication"])

    manifest.update(ctx.root, change)
    ctx.invalidate()
    return doc


def cmd_golden_publish(args) -> int:
    import time

    from .check import golden_file_checks
    from .query import connect

    ctx = Ctx.from_args(args)
    t0 = time.perf_counter()
    doc = publish(ctx, args.to, "golden-datasets golden publish", args.allow_unapproved)
    print(f"{doc['publication']}: {doc['pages']:,} pages, {doc['courses']:,} courses, {doc['records']:,} records, "
          f"{doc['lineage_rows']:,} lineage rows → {doc['to']}/{doc['to_prefix']} "
          f"({time.perf_counter() - t0:.1f}s)")
    if not doc["approval_gate"]["all_rules_approved"]:
        print("  warning: published with --allow-unapproved; publication.json records approval_gate.all_rules_approved = false")
    if doc["golden_id_collisions"]:
        print(f"  golden_id collisions to confirm: {len(doc['golden_id_collisions'])} course codes")
    results = golden_file_checks(Ctx(ctx.root, ctx.catalog, ctx.crawl), connect(Ctx(ctx.root, ctx.catalog, ctx.crawl)))
    bad = [r for r in results if r[3] and r[2].startswith(doc["publication"])]
    for r in results:
        if r[2].startswith(doc["publication"]):
            print(f"  check: {r[2]} — {r[4]} rows, {r[3]} bad")
    return 1 if bad else 0
