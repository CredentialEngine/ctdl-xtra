"""`golden-datasets golden publish`: golden dataset versions and their lineage (spec §4.2 golden_record_id, §5.6,
§7.6; Evals spec §4.1, §4.3).

A golden dataset's ID is its ruleset's: *ruleset v3*. A column (property) is published once its field rule is
approved; publishing it writes the whole golden dataset of that ruleset again (every column published in it so far,
all from the same immutable extraction), never merged with what was there. The first publication in a ruleset
creates its version; later ones rewrite it with the extra column. Every version is kept, and the latest also
replaces each page's file at the usual location, in the `xtra-golden-sets` container:

    <golden root>/<catalog>/<crawl>/<page_stem>/<page_stem>.json                          the latest version
    <golden root>/catalogs/<catalog>/versions/ruleset-vN/<catalog>/<crawl>/<page_stem>/<page_stem>.json

(`<catalog>/<crawl>` repeats so `xtra score --baseline-uri …/versions/ruleset-vN` reads a version as it is.) Each
file is [{golden_record_id, approval, fields: [{ctdl_property, property, value, source_url, location, approval,
approved_by, approved_at}]}], with `<page_stem>.html` (the page as crawled) beside it.

Every value says who approved it: `approval` is `human` when a subject matter expert confirmed that value (marked it
correct and it hasn't changed since, or marked it wrong and selected the text it now is), else `rule` (its rule's
approval covers it); `approved_by` / `approved_at` name that person and when, or who approved the rule. A record's
`approval` is `human` when every value is, `rule` when none is, else `mixed`. The lineage has the same three columns.

Human-reviewed values have their own life cycle (Evals §4.3): they are in the files in any column, published or not,
and each verdict rewrites its page's file in the latest version's folder and the latest location (`publish_page`),
then asks for a score 5 minutes later (`scores/pending.json`).

The files are domain-only: no rule ids, occurrence keys or annotation ids. The Studio keeps the lineage, which traces
every golden value back to its match, rule version and annotations, and a Parquet copy of the values:

    <studio root>/<catalog>/<crawl>/golden-dataset-studio/golden/ruleset-vN/{publication.json, lineage.parquet,
                                                                              golden.parquet}

Every course found on a page is published, course pages and program-page course lines alike. `golden_record_id` is the
`course_key`, unless the course pages with that code name different courses (Marshall, WVU): then each distinct
name gets `course_key~<n>`, and the Golden screen lists them for confirmation.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import layout, manifest, model
from .context import Ctx
from .errors import UserError
from .review import HUMAN_STATES, LOADER, Review  # noqa: F401  (HUMAN_STATES: the row states a person confirmed)
from .storage import AzureRoot, LocalRoot, open_root

FULL_LOCATOR = "locator-course-page"
VERSION = re.compile(r"ruleset-v(\d+)$")
RESCORE_AFTER = timedelta(minutes=5)


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
    """Everything a publication would write for these properties (None: all), without writing it. Human-reviewed
    values are in it whatever their property."""
    snap = rv.snap
    ids, collisions = golden_record_ids(rv)
    ann = defaultdict(list)
    for e in rv.live:
        t = e["target"]
        if t.get("rule_id") and t.get("occurrence_key"):
            ann[(t["rule_id"], t["occurrence_key"])].append(e["annotation_id"])
    # who approved each value: an expert who confirmed it (on the Rules or Records tab), else the rule's approval
    human: dict[tuple[str, str], dict] = {}
    by_rule: dict[str, dict] = {}
    for rid, r in snap.rules.items():
        if r["kind"] != "field":
            continue
        rows = snap.rows(rid)
        states = rv.row_states(rid, rows)
        for row in rows:
            if states[row["key"]].human:
                human[(rid, row["occurrence_key"])] = states[row["key"]].human
        if properties is None or r.get("property_label") in properties:
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
            v = human.get((rid, key))
            if properties is not None and r.get("property_label") not in properties and v is None:
                continue
            loc = ({"css_path": m["full_css_path"], "char_start": m["char_start"], "char_end": m["char_end"]}
                   if m["css_path"] is not None else None)
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


def published_properties(ctx: Ctx, to: str) -> dict[str, dict]:
    """property → the latest publication to `to` that published it (publications before per-property publishing
    published every property)."""
    out: dict[str, dict] = {}
    docs = []
    for g in ctx.crawl_entry().get("golden", []):
        if g.get("to", "").rstrip("/") != to.rstrip("/"):
            continue
        try:
            docs.append(ctx.read_json(f"{g['path']}/publication.json", immutable=False))
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
    """Where the Studio publishes: GOLDEN_DATASETS_GOLDEN_ROOT if set (a local folder or a scratch prefix); else, for
    a local Studio root, the folder `golden` beside it (so development never writes to the shared container); else
    the xtra-golden-sets container."""
    if os.environ.get("GOLDEN_DATASETS_GOLDEN_ROOT"):
        return os.environ["GOLDEN_DATASETS_GOLDEN_ROOT"]
    if isinstance(ctx.root, LocalRoot):
        return str(Path(ctx.root.base).parent / "golden")
    return GOLDEN_CONTAINER


def version_name(ruleset_version: int) -> str:
    return f"ruleset-v{ruleset_version}"


def latest_prefix(ctx: Ctx) -> str:
    return f"{ctx.catalog}/{ctx.crawl}/"


def version_prefix(ctx: Ctx, ruleset_version: int) -> str:
    return f"catalogs/{ctx.catalog}/versions/{version_name(ruleset_version)}/{ctx.catalog}/{ctx.crawl}/"


def versions(ctx: Ctx) -> dict[int, dict]:
    """ruleset version → its golden dataset's manifest entry ({publication, path, to})."""
    out = {}
    for g in ctx.crawl_entry().get("golden", []):
        m = VERSION.match(g["publication"])
        if m:
            out[int(m.group(1))] = g
    return out


def page_json(records: list[dict]) -> str:
    """The text of one <page_stem>.json, exactly as written."""
    return json.dumps(records, indent=2, ensure_ascii=False) + "\n"


def golden_rows(ctx: Ctx, pages: dict[str, list[dict]]) -> list[dict]:
    """golden.parquet: one row per value of the page files."""
    out = []
    for stem, records in sorted(pages.items()):
        n: Counter = Counter()  # value_index per (golden_record_id, property) across the page's records
        for rec in records:
            for f in rec["fields"]:
                k = (rec["golden_record_id"], f["property"])
                out.append({"catalog": ctx.catalog, "crawl": ctx.crawl, "stem": stem,
                            "golden_record_id": rec["golden_record_id"], "property": f["property"],
                            "ctdl_property": f["ctdl_property"], "value_index": n[k], "value": f["value"],
                            "source_url": f["source_url"], "location": f["location"], "approval": f["approval"],
                            "approved_by": f["approved_by"], "approved_at": f["approved_at"]})
                n[k] += 1
    return out


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
                 "meaning": "human: a subject matter expert confirmed the value (marked it correct, or selected the "
                            "right text it now is); rule: the value is approved by its rule's approval"}
    return {"publication": pub, "properties": chosen, "approvals": approvals,
            "property_gate": [{k: props[x][k] for k in ("property", "ctdl_property", "rule_id", "version", "status",
                                                         "approved_by")} for x in chosen if x in props],
            "identity_rules": [{k: s[k] for k in ("rule_id", "version", "status", "approved_by")}
                               for s in statuses if s["kind"] in ("page", "locator")], "catalog": ctx.catalog, "crawl": ctx.crawl, "extraction": rv.snap.ext,
            "ruleset_version": rv.snap.ruleset_version, "published_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "published_by": by, "to": to, "to_prefix": latest_prefix(ctx),
            "version_prefix": version_prefix(ctx, rv.snap.ruleset_version), "pages": len(p["pages"]),
            "page_stems": sorted(p["pages"]), "courses": p["courses"], "records": p["records"],
            "lineage_rows": info["rows"], "lineage_sha256": info["sha256"],
            "golden_record_id_collisions": p["collisions"], "skipped_no_course_key": p["skipped_no_course_key"],
            "format": "golden sets per-page shape: <catalog>/<crawl>/<stem>/<stem>.json = "
                      "[{golden_record_id, approval, fields: [{ctdl_property, property, value, source_url, location, "
                      "approval, approved_by, approved_at}]}], "
                      "plus <stem>.html as crawled; the whole golden dataset of this ruleset, never merged",
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


def _copy_html(ctx: Ctx, target, path: str, stem: str) -> None:
    if target.stat(path) is not None:
        return
    src = layout.page_html(ctx.catalog, ctx.crawl, stem)
    if isinstance(target, AzureRoot) and isinstance(ctx.root, AzureRoot) and target.account == ctx.root.account:
        target.copy_from_url(path, ctx.root.blob_url_with_sas(src))  # server-side, nothing downloaded
    else:
        target.write_file(path, ctx.page_path(stem))


def _stems_written(ctx: Ctx, to: str) -> set[str]:
    """Pages any publication to `to` wrote at the latest location."""
    out = set()
    for g in ctx.crawl_entry().get("golden", []):
        if g.get("to", "").rstrip("/") == to.rstrip("/"):
            try:
                out |= set(ctx.read_json(f"{g['path']}/publication.json", immutable=False).get("page_stems", []))
            except FileNotFoundError:
                pass
    return out


def publish(ctx: Ctx, to: str, by: str, allow_unapproved: bool = False, log=print,
            properties: list[str] | None = None, ext: str | None = None, published_at: str | None = None,
            note: dict | None = None) -> dict:
    """Publish these properties (None: every property whose rule is approved; []: none, only the human-reviewed
    values) into the golden dataset of the extraction's ruleset (`ext`, default the latest): the whole version is
    written again with every column published in it so far."""
    rv = LOADER.review(ctx, ext)
    n = rv.snap.ruleset_version
    ok, statuses = approval(rv)
    chosen = choose(rv, properties, allow_unapproved) if properties != [] else []
    pub = version_name(n)
    gdir = layout.golden_dir(ctx.catalog, ctx.crawl, pub)
    try:
        before = ctx.read_json(f"{gdir}/publication.json", immutable=False)
    except FileNotFoundError:
        before = None
    columns = sorted(set(chosen) | set((before or {}).get("properties", [])), key=lambda x: model.PROPERTY_ORDER.get(x, 99))
    p = plan(rv, set(columns))
    target = open_root(to)
    latest = n >= max(versions(ctx), default=0)
    # pages the version (or, at the latest location, any publication to this root) had but has no course on now
    writes = {f"{version_prefix(ctx, n)}{s}": [] for s in (before or {}).get("page_stems", [])}
    if latest:
        writes |= {f"{latest_prefix(ctx)}{s}": [] for s in _stems_written(ctx, target.uri)}
    for stem, records in p["pages"].items():
        writes[f"{version_prefix(ctx, n)}{stem}"] = records
        if latest:
            writes[f"{latest_prefix(ctx)}{stem}"] = records
    from concurrent.futures import ThreadPoolExecutor

    def write_page(item) -> None:
        folder, records = item
        stem = folder.rsplit("/", 1)[1]
        target.write_text(f"{folder}/{stem}.json", page_json(records))
        if records:
            _copy_html(ctx, target, f"{folder}/{stem}.html", stem)

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(write_page, sorted(writes.items())))
    for r in p["lineage"]:
        r["publication"] = pub
    info = ctx.write_table(f"{gdir}/lineage.parquet", p["lineage"], model.LINEAGE, if_none_match=False)
    ctx.write_table(f"{gdir}/golden.parquet", golden_rows(ctx, p["pages"]), model.GOLDEN, if_none_match=False)
    doc = publication_doc(ctx, rv, p, pub, target.uri, by, ok, statuses, info, columns)
    if published_at:
        doc["published_at"] = published_at
    if before:
        doc["created_at"] = before.get("created_at") or before.get("published_at")
    doc.setdefault("created_at", doc["published_at"])
    if note:
        doc.update(note)
    ctx.root.write_json(f"{gdir}/publication.json", doc)

    def change(m: dict) -> None:
        k = manifest.crawl_entry(manifest.catalog_entry(m, ctx.catalog), ctx.crawl)
        manifest.add_unique(k.setdefault("golden", []), {"publication": pub, "path": gdir, "to": target.uri},
                            key=lambda g: g["publication"])

    manifest.update(ctx.root, change)
    ctx.invalidate()
    return doc | {"latest": latest}  # whether it also went to the latest location (not saved: a newer one may come)


def publish_page(ctx: Ctx, stem: str, reason: str, by: str, create: bool = False) -> dict | None:
    """After a verdict on a value of this page: rebuild its file from the Studio's state and overwrite it in the
    latest golden dataset's folder and at the latest location (one small file), then ask for a score 5 minutes
    from now. With no golden dataset yet, `create` (an expert's verdict) creates the current ruleset's. Returns
    what changed, or None."""
    vs = versions(ctx)
    if not vs:
        if not create:
            return None
        doc = publish(ctx, default_target(ctx), by, properties=[])
        due = request_score(ctx, reason)
        return {"publication": doc["publication"], "created": True, "files": doc["pages"], "due_at": due}
    n = max(vs)
    doc = ctx.read_json(f"{vs[n]['path']}/publication.json", immutable=False)
    rv = LOADER.review(ctx, doc["extraction"])
    records = plan(rv, set(doc["properties"]))["pages"].get(stem, [])
    target = open_root(doc["to"])
    text, changed = page_json(records), []
    for folder in (f"{version_prefix(ctx, n)}{stem}", f"{latest_prefix(ctx)}{stem}"):
        try:
            old = target.read_text(f"{folder}/{stem}.json")
        except FileNotFoundError:
            old = None
        if old == text or (old is None and not records):
            continue
        target.write_text(f"{folder}/{stem}.json", text)
        if records:
            _copy_html(ctx, target, f"{folder}/{stem}.html", stem)
        changed.append(f"{folder}/{stem}.json")
    if not changed:
        return None
    return {"publication": doc["publication"], "created": False, "files": changed, "due_at": request_score(ctx, reason)}


def request_score(ctx: Ctx, reason: str) -> str:
    """scores/pending.json: a score is due 5 minutes from now (each review moves it on; the server's loop runs it)."""
    due = (datetime.now(UTC) + RESCORE_AFTER).strftime("%Y-%m-%dT%H:%M:%SZ")
    ctx.root.write_json(layout.pending_score(ctx.catalog, ctx.crawl), {"due_at": due, "reason": reason})
    return due


def backfill(ctx: Ctx, to: str, log=print) -> list[dict]:
    """Rebuild the publications made before golden dataset versions (`pub-…`, merged in place) as versions: each
    ruleset's columns from their lineage, values from the immutable extraction they were published from. The old
    entries leave the manifest; their folders stay."""
    import pyarrow.parquet as pq

    old = []
    for g in ctx.crawl_entry().get("golden", []):
        if VERSION.match(g["publication"]):
            continue
        d = ctx.read_json(f"{g['path']}/publication.json", immutable=False)
        cols = set(pq.read_table(ctx.root.local_path(f"{g['path']}/lineage.parquet", mutable=True),
                                 columns=["property"]).column("property").to_pylist())
        old.append((d, cols))
    by_ruleset: dict[int, list] = defaultdict(list)
    for d, cols in sorted(old, key=lambda x: x[0].get("published_at") or ""):
        by_ruleset[d["ruleset_version"]].append((d, cols))
    done = []
    for _, items in sorted(by_ruleset.items()):
        last = items[-1][0]
        cols = sorted(set().union(*(c for _, c in items)), key=lambda x: model.PROPERTY_ORDER.get(x, 99))
        doc = publish(ctx, to, last["published_by"], allow_unapproved=True, properties=cols, ext=last["extraction"],
                      published_at=last["published_at"], note={"backfilled_from": [d["publication"] for d, _ in items]})
        log(f"{doc['publication']} ({', '.join(cols)}) from {', '.join(d['publication'] for d, _ in items)}: "
            f"{doc['pages']:,} pages, {doc['records']:,} records, {doc['lineage_rows']:,} values "
            f"({doc['approvals']['human']:,} human-reviewed)")
        done.append(doc)
    gone = {d["publication"] for d, _ in old}

    def change(m: dict) -> None:
        k = manifest.crawl_entry(manifest.catalog_entry(m, ctx.catalog), ctx.crawl)
        k["golden"] = [g for g in k.get("golden", []) if g["publication"] not in gone]

    manifest.update(ctx.root, change)
    ctx.invalidate()
    return done


def cmd_golden_publish(args) -> int:
    import time

    from .check import golden_file_checks
    from .query import connect

    ctx = Ctx.from_args(args)
    t0 = time.perf_counter()
    doc = publish(ctx, args.to or default_target(ctx), "golden-datasets golden publish", args.allow_unapproved,
                  properties=args.property)
    print(f"{doc['publication']} ({', '.join(doc['properties'])}): {doc['pages']:,} pages, {doc['courses']:,} courses, "
          f"{doc['records']:,} records, {doc['lineage_rows']:,} lineage rows → {doc['to']}/{doc['version_prefix']}"
          f"{' and ' + doc['to_prefix'] if doc['latest'] else ''} ({time.perf_counter() - t0:.1f}s)")
    if not doc["approval_gate"]["all_rules_approved"]:
        print("  warning: published with --allow-unapproved; publication.json records approval_gate.all_rules_approved = false")
    if doc["golden_record_id_collisions"]:
        print(f"  golden_record_id collisions to confirm: {len(doc['golden_record_id_collisions'])} course codes")
    return _report_checks(ctx, golden_file_checks, connect, {doc["publication"]})


def _report_checks(ctx: Ctx, golden_file_checks, connect, pubs: set[str]) -> int:
    results = golden_file_checks(Ctx(ctx.root, ctx.catalog, ctx.crawl), connect(Ctx(ctx.root, ctx.catalog, ctx.crawl)))
    mine = [r for r in results if r[2].split(":")[0] in pubs]
    for r in mine:
        print(f"  check: {r[2]} — {r[4]} rows, {r[3]} bad")
    return 1 if any(r[3] for r in mine) else 0


def cmd_golden_backfill(args) -> int:
    from .check import golden_file_checks
    from .query import connect

    ctx = Ctx.from_args(args)
    docs = backfill(ctx, args.to or default_target(ctx))
    if not docs:
        print("nothing to backfill: every publication is a golden dataset version already")
        return 0
    return _report_checks(ctx, golden_file_checks, connect, {d["publication"] for d in docs})
