"""`golden-datasets golden publish`: the golden dataset and its lineage (spec §4.2 golden_record_id, §5.6, §7.6).

Published one property (field) at a time: a property can be published once its field rule is approved, whatever
the other fields' rules say. Publishing writes the chosen properties' values from the current extraction into each
page's file and keeps what earlier publications put there for the other properties, so the golden set fills up
property by property. The page rule and record locator (which courses exist) are recorded in publication.json
with their status; they don't hold a property back.

The output keeps the per-page shape of the golden sets saved so far, in the `xtra-golden-sets` container:

    <golden root>/<catalog>/<crawl>/<page_stem>/<page_stem>.json   [{golden_record_id, approval, fields: [{ctdl_property,
                                                     property, value, source_url, location, approval, approved_by,
                                                     approved_at}]}]

Every value says who approved it: `approval` is `human` when a person confirmed that value (marked it correct and it
hasn't changed since, or marked it wrong and selected the text it now is), else `rule` (its rule's approval covers
it); `approved_by` / `approved_at` name that person and when, or who approved the rule. A record's `approval` is
`human` when every value is, `rule` when none is, else `mixed`. The lineage has the same three columns.
    <golden root>/<catalog>/<crawl>/<page_stem>/<page_stem>.html   the page as crawled

It is domain-only: no rule ids, occurrence keys or annotation ids. The Studio keeps the lineage, which traces every
golden value back to its match, rule version and annotations:

    <studio root>/<catalog>/<crawl>/golden-dataset-studio/golden/<publication>/{publication.json, lineage.parquet}

Every course found on a page is published, course pages and program-page course lines alike. `golden_record_id` is the
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
#: Row states where a person confirmed the value itself: marked it correct (and it hasn't changed since), or marked
#: it wrong and selected the right text, which the value now is. Every other published value is approved by its rule.
HUMAN_STATES = ("correct", "fixed")


def record_approval(fields: list[dict]) -> str:
    """A record's approval from its fields': human (every value confirmed by a person), rule (none), or mixed."""
    kinds = {f.get("approval", "rule") for f in fields}
    return "human" if kinds == {"human"} else "rule" if kinds <= {"rule"} else "mixed"


def _record(gid: str, fields: list[dict]) -> dict:
    return {"golden_record_id": gid, "approval": record_approval(fields), "fields": fields}


def _name_key(v: str | None) -> str:
    return re.sub(r"\s+", " ", v or "").strip().lower()


def golden_record_ids(rv: Review) -> tuple[dict[str, str], list[dict]]:
    """occurrence_key → golden_record_id, and the collisions (codes whose course pages name different courses)."""
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
            collisions.append({"course_key": ck, "golden_record_ids": [f"{ck}~{i}" for i in range(1, len(keys) + 1)],
                               "names": [by_name[k] for k in keys]})
    out = {}
    for key, o in snap.occurrences.items():
        ck = o["course_key"]
        if ck is None:
            continue
        out[key] = variant.get((ck, _name_key(occ_name[key])), ck)
    return out, collisions


def plan(rv: Review, properties: set[str] | None = None) -> dict:
    """Everything a publication would write for these properties (None: all), without writing it."""
    snap = rv.snap
    ids, collisions = golden_record_ids(rv)
    ann = defaultdict(list)
    for e in rv.live:
        t = e["target"]
        if t.get("rule_id") and t.get("occurrence_key"):
            ann[(t["rule_id"], t["occurrence_key"])].append(e["annotation_id"])
    # who approved each value: a person who confirmed it (on the Rules or Records tab), else the rule's approval
    human: dict[tuple[str, str], dict] = {}
    by_rule: dict[str, dict] = {}
    for rid, r in snap.rules.items():
        if r["kind"] != "field" or (properties is not None and r.get("property_label") not in properties):
            continue
        rows = snap.rows(rid)
        states = rv.row_states(rid, rows)
        for row in rows:
            st = states[row["key"]]
            if st.state in HUMAN_STATES and st.verdict:
                human[(rid, row["occurrence_key"])] = st.verdict
        by_rule[rid] = rv.rule_status(rid, states)
    pages: dict[str, list[dict]] = defaultdict(list)
    lineage: list[dict] = []
    skipped_no_key = 0
    used: Counter = Counter()  # (golden_record_id, page_stem, property) → values already published
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
            if properties is not None and r.get("property_label") not in properties:
                continue
            loc = ({"css_path": m["full_css_path"], "char_start": m["char_start"], "char_end": m["char_end"]}
                   if m["css_path"] is not None else None)
            v = human.get((rid, key))
            st = by_rule.get(rid, {})
            ok = {"approval": "human", "approved_by": v["author"], "approved_at": v["at"]} if v else \
                {"approval": "rule", "approved_by": st.get("approved_by"), "approved_at": st.get("approved_at")}
            fields.append({"ctdl_property": r.get("ctdl_property"), "property": r["property_label"],
                           "value": m["value"], "source_url": url, "location": loc, **ok})
            rows.append({"golden_record_id": gid, "page_stem": stem, "property": r["property_label"],
                         "ctdl_property": r.get("ctdl_property"), "extraction": snap.ext, "rule_id": rid,
                         "rule_version": m["rule_version"], "occurrence_key": key, "match_value_index": m["value_index"],
                         "annotation_ids": sorted(ann.get((rid, key), [])), **ok})
        if properties is not None and not fields:
            continue  # nothing of the chosen properties for this course
        record = _record(gid, fields)
        if any(r["golden_record_id"] == gid and r == record for r in pages[stem]):
            continue  # the same course listed twice on a page with identical values: once is enough
        # A second, different record with the same golden_record_id on the same page: its values get the next value_index.
        for row in rows:
            row["value_index"] = used[(gid, stem, row["property"])]
            used[(gid, stem, row["property"])] += 1
        pages[stem].append(record)
        lineage.extend(rows)
    return {"pages": dict(pages), "lineage": lineage, "collisions": collisions, "skipped_no_course_key": skipped_no_key,
            "courses": len({r["golden_record_id"] for r in lineage}), "records": sum(len(v) for v in pages.values())}


def property_rules(rv: Review) -> list[dict]:
    """Each property the field rules fill, with its rule and status (for the full courses' locator, i.e. the
    course pages)."""
    out = []
    for rid, r in sorted(rv.snap.rules.items(), key=lambda kv: (model.PROPERTY_ORDER.get(kv[1].get("property_label"), 99),
                                                                 kv[0])):
        if r["kind"] != "field" or r["definition"].get("locator") != FULL_LOCATOR:
            continue
        st = rv.rule_status(rid)
        out.append({"property": r["property_label"], "ctdl_property": r.get("ctdl_property"), "rule_id": rid,
                    "version": r["version"], "status": st["status"], "approved_by": st.get("approved_by")})
    return out


def merge_page(old: list[dict], new: list[dict], properties: set[str]) -> list[dict]:
    """One page's records after publishing `properties`: their values come from `new`; every other property keeps
    what `old` (the file already in the golden set) has. Records pair by golden_record_id, in order on the page."""
    def order(fields: list[dict]) -> list[dict]:
        return sorted(fields, key=lambda f: model.PROPERTY_ORDER.get(f["property"], 99))

    seen: Counter = Counter()
    by_gid: dict[tuple[str, int], dict] = {}
    for rec in old:
        rec = {**rec, "golden_record_id": rec.get("golden_record_id", rec.get("golden_id"))}  # files before the rename
        by_gid[(rec["golden_record_id"], seen[rec["golden_record_id"]])] = rec
        seen[rec["golden_record_id"]] += 1
    seen.clear()
    used, out = set(), []
    for rec in new:
        k = (rec["golden_record_id"], seen[rec["golden_record_id"]])
        seen[rec["golden_record_id"]] += 1
        kept = [f for f in by_gid[k]["fields"] if f["property"] not in properties] if k in by_gid else []
        used.add(k)
        out.append(_record(rec["golden_record_id"], order(kept + rec["fields"])))
    for k, rec in by_gid.items():  # courses only the earlier publications have: keep their other properties
        if k in used:
            continue
        kept = [f for f in rec["fields"] if f["property"] not in properties]
        if kept:
            out.append(_record(rec["golden_record_id"], order(kept)))
    return out


def published_properties(ctx: Ctx, to: str) -> dict[str, dict]:
    """property → the latest publication to `to` that published it (publications before per-property publishing
    published every property)."""
    out: dict[str, dict] = {}
    docs = []
    for g in ctx.crawl_entry().get("golden", []):
        if g.get("to", "").rstrip("/") != to.rstrip("/"):
            continue
        try:
            docs.append(ctx.read_json(f"{g['path']}/publication.json"))
        except FileNotFoundError:
            continue
    for d in sorted(docs, key=lambda d: d.get("published_at") or ""):
        props = d.get("properties") or [r["property"] for r in d.get("property_gate", [])] or list(model.PROPERTY_ORDER)
        for prop in props:
            gate = next((r for r in d.get("property_gate", []) if r["property"] == prop), {})
            out[prop] = {"publication": d["publication"], "published_at": d.get("published_at"),
                         "published_by": d.get("published_by"), "extraction": d.get("extraction"),
                         "rule_version": gate.get("version")}
    return out


def approval(rv: Review) -> tuple[bool, list[dict]]:
    statuses = [{"rule_id": rid, "version": r["version"], "kind": r["kind"], **rv.rule_status(rid)}
                for rid, r in sorted(rv.snap.rules.items(), key=lambda kv: (model.KIND_ORDER[kv[1]["kind"]], kv[0]))]
    return all(s["status"] == "approved" for s in statuses), statuses


GOLDEN_CONTAINER = "azure://https://ceteststorage.blob.core.windows.net/xtra-golden-sets"


def default_target(ctx: Ctx) -> str:
    """Where the UI publishes: the xtra-golden-sets container, unless GOLDEN_DATASETS_GOLDEN_ROOT names another
    root (a local folder or a scratch prefix, for trying a publication out)."""
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
                    info: dict, properties: list[str] | None = None) -> dict:
    """publication.json: which properties, extraction and ruleset were published, where to, and the gates."""
    props = {r["property"]: r for r in property_rules(rv)}
    chosen = properties if properties is not None else list(props)
    counts: dict[str, Counter] = defaultdict(Counter)
    for row in p["lineage"]:
        counts[row["property"]][row["approval"]] += 1
    approvals = {"human": sum(c["human"] for c in counts.values()), "rule": sum(c["rule"] for c in counts.values()),
                 "by_property": {prop: {"human": c["human"], "rule": c["rule"]} for prop, c in counts.items()},
                 "meaning": "human: a person confirmed the value (marked it correct, or selected the right text it now "
                            "is); rule: the value is approved by its rule's approval"}
    return {"publication": pub, "properties": chosen, "approvals": approvals,
            "property_gate": [{k: props[x][k] for k in ("property", "ctdl_property", "rule_id", "version", "status",
                                                         "approved_by")} for x in chosen if x in props],
            "identity_rules": [{k: s[k] for k in ("rule_id", "version", "status", "approved_by")}
                               for s in statuses if s["kind"] in ("page", "locator")], "catalog": ctx.catalog, "crawl": ctx.crawl, "extraction": rv.snap.ext,
            "ruleset_version": rv.snap.ruleset_version, "published_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "published_by": by, "to": to, "to_prefix": f"{ctx.catalog}/{ctx.crawl}/", "pages": len(p["pages"]),
            "page_stems": sorted(p["pages"]), "courses": p["courses"], "records": p["records"],
            "lineage_rows": info["rows"], "lineage_sha256": info["sha256"],
            "golden_record_id_collisions": p["collisions"], "skipped_no_course_key": p["skipped_no_course_key"],
            "format": "golden sets per-page shape: <catalog>/<crawl>/<stem>/<stem>.json = "
                      "[{golden_record_id, approval, fields: [{ctdl_property, property, value, source_url, location, "
                      "approval, approved_by, approved_at}]}], "
                      "plus <stem>.html as crawled",
            "approval_gate": {"all_rules_approved": ok,
                              "rules": [{k: s[k] for k in ("rule_id", "version", "status", "approved_by")}
                                        for s in statuses]}}


def choose(rv: Review, properties: list[str] | None, allow_unapproved: bool = False) -> list[str]:
    """The properties to publish: those asked for (None: every property whose rule is approved). Each needs its
    field rule approved, unless `allow_unapproved` (testing)."""
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


def merged_page(target, prefix: str, stem: str, records: list[dict], properties: set[str]) -> list[dict]:
    """A page's records as they will be written: merged with the file the golden set already has."""
    try:
        old = json.loads(target.read_text(f"{prefix}{stem}/{stem}.json"))
    except FileNotFoundError:
        old = []
    return merge_page(old, records, properties)


def publish(ctx: Ctx, to: str, by: str, allow_unapproved: bool = False, log=print,
            properties: list[str] | None = None) -> dict:
    rv = LOADER.review(ctx)
    ok, statuses = approval(rv)
    chosen = choose(rv, properties, allow_unapproved)
    p = plan(rv, set(chosen))
    target = open_root(to)
    pub = publication_name(ctx, rv)
    prefix = f"{ctx.catalog}/{ctx.crawl}/"
    # pages earlier publications wrote but this one has no course on: their chosen properties' old values go
    earlier = set()
    for g in ctx.crawl_entry().get("golden", []):
        if g.get("to", "").rstrip("/") == target.uri.rstrip("/"):
            try:
                earlier |= set(ctx.read_json(f"{g['path']}/publication.json").get("page_stems", []))
            except FileNotFoundError:
                pass
    pages = dict(p["pages"]) | {stem: [] for stem in earlier - set(p["pages"])}
    from concurrent.futures import ThreadPoolExecutor

    def write_page(item) -> None:
        stem, records = item
        target.write_text(f"{prefix}{stem}/{stem}.json", page_json(merged_page(target, prefix, stem, records, set(chosen))))
        html_path = f"{prefix}{stem}/{stem}.html"
        if target.stat(html_path) is None:
            src = layout.page_html(ctx.catalog, ctx.crawl, stem)
            if isinstance(target, AzureRoot) and isinstance(ctx.root, AzureRoot) and target.account == ctx.root.account:
                target.copy_from_url(html_path, ctx.root.blob_url_with_sas(src))  # server-side, nothing downloaded
            else:
                target.write_file(html_path, ctx.page_path(stem))

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(write_page, sorted(pages.items())))
    for r in p["lineage"]:
        r["publication"] = pub
    gdir = layout.golden_dir(ctx.catalog, ctx.crawl, pub)
    info = ctx.write_table(f"{gdir}/lineage.parquet", p["lineage"], model.LINEAGE)
    doc = publication_doc(ctx, rv, p, pub, target.uri, by, ok, statuses, info, chosen)
    doc["page_stems"] = sorted(set(doc["page_stems"]) | earlier)
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
    doc = publish(ctx, args.to, "golden-datasets golden publish", args.allow_unapproved, properties=args.property)
    print(f"{doc['publication']} ({', '.join(doc['properties'])}): {doc['pages']:,} pages, {doc['courses']:,} courses, {doc['records']:,} records, "
          f"{doc['lineage_rows']:,} lineage rows → {doc['to']}/{doc['to_prefix']} "
          f"({time.perf_counter() - t0:.1f}s)")
    if not doc["approval_gate"]["all_rules_approved"]:
        print("  warning: published with --allow-unapproved; publication.json records approval_gate.all_rules_approved = false")
    if doc["golden_record_id_collisions"]:
        print(f"  golden_record_id collisions to confirm: {len(doc['golden_record_id_collisions'])} course codes")
    results = golden_file_checks(Ctx(ctx.root, ctx.catalog, ctx.crawl), connect(Ctx(ctx.root, ctx.catalog, ctx.crawl)))
    bad = [r for r in results if r[3] and r[2].startswith(doc["publication"])]
    for r in results:
        if r[2].startswith(doc["publication"]):
            print(f"  check: {r[2]} — {r[4]} rows, {r[3]} bad")
    return 1 if bad else 0
