"""Review API (W4): catalogs, rules, rows, page overlays, courses (Records tab) and annotations.

Every list is computed from one in-memory `Snapshot` of an extraction plus the annotation log (read
incrementally), so a request costs milliseconds once the extraction is loaded (spec §10).

Each section starts with its routes, in the order they are registered; the helpers they call follow them, and the
helpers every section shares are at the bottom.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Query, Request

from .. import classes, facets, golden, layout, manifest, model, profiles_rule, properties, telemetry
from ..catalogs import CATALOGS, KNOWN, info
from ..errors import UserError
from ..log import FULL_NAMES, new_id, validate
from ..profiles import role_of, roles
from ..review import (
    LOADER,
    Review,
    Snapshot,
    annotated_match,
    human_reviewed_counts,
    list_item,
    norm,
    reset_clears,
)
from .state import not_found, studio

router = APIRouter(prefix="/api")

PAGE_RULE_TITLES = {"course-page": "Course pages", "program-page": "Program pages",
                    "program-page-with-courses": "Program pages that list courses",
                    "learningprogram-page": "Program pages"}
PLAIN_SUBTITLES = {"course-page": "Which pages are a single course's own page",
                   "program-page": "Which pages describe a degree or certificate",
                   "program-page-with-courses": "Which program pages name courses in their requirements",
                   "learningprogram-page": "Pages with a program: degree, minor, certificate"}
#: Record locators listed first, in this order (their titles come from their definitions: `locator_title`).
KNOWN_LOCATORS = ("locator-course-page", "locator-program-requirement")
#: What a class's records are called (the class menu's counts).
RECORD_NOUN = {"course": ("course", "courses"), "learningprogram": ("program", "programs")}
#: The rule list's groups after Page rules and Record locators: the class's three tiers (LearningProgram spec,
#: approved item 13; Phase 2 starts shut), then rules on another record locator. `collapsed` ones start shut.
PROPERTY_GROUPS = (("required", "Required", False), ("phase1", "Phase 1", False), ("phase2", "Phase 2", True),
                   ("program", "Other record locators", True))
#: "Annotated by" choices that aren't a person: they don't tag rows with the ruleset versions annotated in.
NOT_A_PERSON = (None, "", "nobody", "waiting", "experts", "engineers")
#: A target's fields, null when the client didn't send them.
TARGET_FIELDS = ("kind", "rule_id", "rule_version_seen", "extraction_seen", "occurrence_key",
                 "record_external_identifier", "page_stem", "value_index", "value_seen")
NO_MATCH = {"value": None, "status": "none", "full_css_path": None, "char_start": None, "char_end": None}


# =====================================================================================================
# Catalogs
# =====================================================================================================
@router.get("/catalogs")
def catalogs(request: Request) -> list[dict]:
    st = studio(request)
    entries = {c["catalog"]: c for c in st.ctx(next(iter(CATALOGS))).manifest()["catalogs"]}
    folders = sorted(set(CATALOGS) | set(entries), key=lambda folder: _shown_name(folder, entries))
    cards = _with_catalogs_being_added(st, entries, [_catalog_card(st, f, entries.get(f)) for f in folders])
    telemetry.set({"ce.catalogs.count": len(cards), "ce.catalogs.ready": sum(c["status"] == "ready" for c in cards),
                   "ce.catalogs.adding": len(st.adding)})
    return cards


@router.get("/catalogs/{catalog}")
def catalog(request: Request, catalog: str, ext: str | None = None) -> dict:
    st = studio(request)
    ctx = st.ctx(catalog)
    if not ctx.ruleset_versions() or not ctx.extractions():
        return _empty_catalog(st, ctx)
    rv = _review(request, catalog, ext)
    ctx = rv.snap.ctx
    return {**_catalog_header(ctx, _crawl_started(ctx) or ctx.crawl),
            "extraction": rv.snap.ext, "ruleset_version": rv.snap.ruleset_version,
            "extractions": [{"extraction": e["extraction"], "ruleset_version": e["ruleset_version"],
                             "parent_extraction": e.get("parent_extraction")} for e in ctx.extractions()],
            "rulesets": [_ruleset_brief(ctx, v) for v in ctx.ruleset_versions()], "authors": _authors(rv.events),
            "pane_css": rv.snap.settings.get("pane_css", ""),
            "root": ctx.root.uri, "cls": ctx.cls, "classes": class_summaries(st, ctx.catalog)}


def _shown_name(folder: str, entries: dict[str, dict]) -> str:
    name = info(folder)["name"] if folder in CATALOGS or folder in KNOWN else (entries[folder].get("name") or folder)
    return name.lower()


def _catalog_card(st, folder: str, entry: dict | None) -> dict:
    meta = _catalog_meta(folder, entry)
    card = {"catalog": folder, "short": meta["short"], "name": meta["name"], "institution": meta["institution"],
            "platform": meta["platform"], "logo": _logo(meta),
            "pages": None, "crawl": None, "ruleset_version": None, "rules_total": 0, "rules_approved": 0,
            "status": "not imported",
            # the classes this catalog has none of (the home page says "Not a LearningProgram source"): the
            # catalog's entry in the manifest, else catalogs.py
            "not_sources": list((entry or {}).get("not_sources") or meta.get("not_sources") or [])}
    if entry:
        card.update(_crawl_progress(st, folder, entry))
    return card


def _catalog_meta(folder: str, entry: dict | None) -> dict:
    meta = info(folder)
    if folder not in CATALOGS and folder not in KNOWN and entry:  # added from the picker: named from its crawl
        meta = {**meta, "name": entry.get("name") or folder, "institution": entry.get("name") or folder}
    return meta


def _crawl_progress(st, folder: str, entry: dict) -> dict:
    crawl = next((c for c in entry["crawls"] if c["crawl"] == entry.get("current_crawl")), None)
    progress = {"pages": (crawl or {}).get("page_count"), "crawl": entry.get("current_crawl")}
    runs = manifest.crawl_class(crawl, "course", create=False)["extractions"]
    if manifest.has_rules(entry, "course") and crawl and runs:
        progress.update(_approvals(st.ctx(folder), runs))
    return progress


def _approvals(ctx, runs: list[dict]) -> dict:
    """Only the ruleset and the log are needed to count approvals, not the extraction: the picker stays fast on a
    cold cache (spec §10)."""
    latest = sorted(runs, key=lambda x: (x["ruleset_version"], x["extraction"]))[-1]
    ruleset = ctx.ruleset(latest["ruleset_version"])
    return {"status": "ready", "ruleset_version": ruleset["version"], "rules_total": len(ruleset["rules"]),
            "rules_approved": approved_count(ruleset, LOADER.log(ctx).events())}


def _with_catalogs_being_added(st, entries: dict[str, dict], cards: list[dict]) -> list[dict]:
    """Catalogs being added from the picker (spec §7.1): a card with their progress until they're in the manifest."""
    for job in list(st.adding.values()):
        if job["step"] == "done" and job["catalog"] in entries:
            st.adding.pop(job["catalog"], None)
        elif job["catalog"] not in entries or job["step"] == "failed":
            cards = [c for c in cards if c["catalog"] != job["catalog"]] + [_adding_card(job)]
    return cards


def _adding_card(job: dict) -> dict:
    return {"catalog": job["catalog"], "short": job["catalog"], "name": job["name"],
            "institution": job["name"], "platform": "", "logo": None, "pages": job["pages"],
            "crawl": job["crawl"], "ruleset_version": None, "rules_total": 0, "rules_approved": 0,
            "status": "failed" if job["step"] == "failed" else "adding",
            "adding": {k: job[k] for k in ("step", "done", "total", "error")}}


def approved_count(ruleset: dict, events: list[dict]) -> int:
    """Rules of this ruleset whose latest approve / reopen event for their current version is an approve."""
    superseded = {e["supersedes"] for e in events if e.get("supersedes")}
    last: dict[tuple, str] = {}
    for e in sorted((e for e in events if e["annotation_id"] not in superseded), key=lambda e: e["at"]):
        t = e.get("target") or {}
        if e["type"] in ("approve", "reopen") and t.get("kind") == "rule":
            last[(t.get("rule_id"), t.get("rule_version_seen"))] = e["type"]
        elif e["type"] == "reset" and t.get("kind") == "rule":  # ends the approval of every version
            last = {k: v for k, v in last.items() if k[0] != t.get("rule_id")}
    return sum(1 for r in ruleset["rules"] if last.get((r["rule_id"], r["version"])) == "approve")


def class_summaries(st, folder: str) -> list[dict]:
    """The class menu (LearningProgram spec, approved item 11): each class's rules, approvals and records in this
    catalog, and its properties. Records come from the latest rule run's `extraction.json` (no tables are read)."""
    return [_class_summary(st.ctx(folder, c.slug), c) for c in classes.CLASSES.values()]


def _class_summary(ctx, cls) -> dict:
    summary = {"slug": cls.slug, "name": cls.name, "properties": len(properties.active(cls.slug)),
               "noun": RECORD_NOUN.get(cls.slug, ("record", "records")), "ruleset_version": None, "rules_total": 0,
               "rules_approved": 0, "records": None}
    try:
        _add_class_rules(ctx, summary)
    except (UserError, FileNotFoundError):
        pass
    return summary


def _add_class_rules(ctx, summary: dict) -> None:
    versions = ctx.ruleset_versions()
    if not versions:
        return
    ruleset = ctx.ruleset(versions[-1])
    summary.update(ruleset_version=versions[-1], rules_total=len(ruleset["rules"]),
                   rules_approved=approved_count(ruleset, LOADER.log(ctx).events()))
    ext = ctx.latest_extraction()
    if ext:
        files = ctx.extraction_meta(ext).get("files") or {}
        summary["records"] = (files.get("occurrences.parquet") or {}).get("rows")


def _empty_catalog(st, ctx) -> dict:
    """A catalog with no rules in this class yet: enough for the top bar and the class menu, and the tabs' empty
    state (`extraction` None)."""
    return {**_catalog_header(ctx, ctx.crawl), "extraction": None, "ruleset_version": None,
            "extractions": [], "rulesets": [], "authors": [], "pane_css": "", "root": ctx.root.uri, "cls": ctx.cls,
            "classes": class_summaries(st, ctx.catalog)}


def _catalog_header(ctx, crawl_started: str) -> dict:
    meta = info(ctx.catalog)
    return {"catalog": ctx.catalog, "short": meta["short"], "name": meta["name"], "institution": meta["institution"],
            "logo": _logo(meta), "crawl": ctx.crawl, "crawl_started": crawl_started,
            "pages": ctx.crawl_entry().get("page_count")}


def _crawl_started(ctx) -> str | None:
    try:
        crawl_json = json.loads(ctx.crawl_root.local_path(layout.crawl_json(ctx.catalog, ctx.crawl)).read_bytes())
    except FileNotFoundError:
        return None
    return crawl_json.get("run_id")


def _ruleset_brief(ctx, version: int) -> dict:
    ruleset = ctx.ruleset(version)
    return {"version": version, "note": ruleset.get("note"), "published_at": ruleset.get("published_at"),
            "published_by": ruleset.get("published_by"), "changed_rules": ruleset.get("changed_rules", []),
            "extraction": ctx.extraction_for(version)}


def _authors(events: list[dict]) -> list[str]:
    return sorted({e["author"] for e in events if not e["author"].startswith("golden-datasets")})


def _logo(meta: dict) -> str | None:
    return f"/logos/{meta['logo']}" if meta.get("logo") else None


# =====================================================================================================
# Rules
# =====================================================================================================
@router.get("/catalogs/{catalog}/rules")
def rules(request: Request, catalog: str, ext: str | None = None) -> dict:
    """The rule list. Properties in the class's tiers: Required (in a fixed order, the record key first), Phase 1 and
    Phase 2, each by how many values experts reviewed across every catalog, then sheet order, with the properties
    that have no rule yet last; then rules on another record locator. Sorted when the list loads (a verdict doesn't
    re-sort the list someone is looking at)."""
    rv = _review(request, catalog, ext)
    snap = rv.snap
    groups = [_kind_group(rv, kind, label) for kind, label in (("page", "Page rules"), ("locator", "Record locators"))]
    groups += _property_groups(rv, _property_ids_in_order(request, snap))
    telemetry.set({"ce.rules.groups": len(groups), "ce.rules.count": len(snap.rules)})
    return {"extraction": snap.ext, "ruleset_version": snap.ruleset_version, "groups": groups, "cls": snap.ctx.cls}


@router.get("/catalogs/{catalog}/rules/{rule_id}")
def rule(request: Request, catalog: str, rule_id: str, ext: str | None = None) -> dict:
    rv = _rule_review(request, catalog, rule_id, ext)
    r = rv.snap.rules[rule_id]
    loc = rv.snap.rules.get(r["definition"].get("locator") or "")  # where a property rule looks, titled like the locator
    return {**_rule_summary(rv, rule_id), "definition": r["definition"], "what": r.get("what", ""),
            "locator_title": locator_title(loc["definition"])[0] if loc else None,
            "how": r.get("how", ""), "why": r.get("why", ""), "examples": r.get("examples", []),
            "depends_on": r.get("depends_on", []), "content_hash": r["content_hash"],
            "published_by": r.get("published_by"), "published_at": r.get("published_at"),
            "parent_version": r.get("parent_version"), "versions": rv.snap.ctx.rule_versions(rule_id),
            "fill": rv.snap.fill(rule_id), "signal_counts": dict(rv.snap.signal_counts.get(rule_id, {})),
            "settings": {"content_root": rv.snap.settings.get("content_root")}}


@router.get("/catalogs/{catalog}/rules/{rule_id}/rows")
def rows(request: Request, catalog: str, rule_id: str, ext: str | None = None, offset: int = 0,
         limit: int = 200, q: str | None = None, focus: str | None = None,
         f: Annotated[list[str] | None, Query()] = None, order: str = "review",
         cross: Annotated[list[str] | None, Query()] = None, seed: int = 0, prior: bool = False,
         by: str | None = None, verdict: str | None = None) -> dict:
    """One page of a rule's rows in review order. `focus` (a row key, occurrence key, record key or page stem)
    extends the page so it includes that row, and returns its index as `focus_index` (links from Compare).
    The Sample drawer (facets.py): `f` filters by strata (`f=length:0–99 chars`, repeatable); `order` is `review`
    (the default above), `auto` (Autostratify: one combination of the `cross` strata after another, rarest first;
    `cross` omitted = the ones that split the rows most evenly) or `shuffle`, both seeded by `seed`. The first page
    also returns `sample`: the strata histograms, the crossed strata and their combinations. Rows carry `tags`:
    their bucket in each crossed or filtered stratum. `prior`: rows not reviewed yet whose record was reviewed in
    another rule come first (tagged "Reviewed in"); `sample.elsewhere` counts them either way. The "Annotated by"
filter (Evals spec §6.7): `by` = a person (the rows they marked or commented on, in any ruleset version, tagged with
the versions: "Annotated in"), `nobody` or `waiting` (engineer-checked); `verdict` = correct · wrong · note."""
    started = time.perf_counter()
    rv = _rule_review(request, catalog, rule_id, ext)
    ordered = _matching_rows(rv, rule_id, q, by, verdict)
    filters = facets.parse_filters(f)
    _check_order(order)
    ordered, sample, elsewhere = _sampled_rows(rv, rule_id, ordered, filters, order, cross, seed, prior, by)
    focus_index = _find_row(ordered, focus) if focus else None
    limit = _limit_with_focus(focus_index, offset, limit)
    view = _RowView.of(request, rv, rule_id, sample["tag_dims"], order == "review" and not filters, elsewhere, prior)
    shown = [view.row(r, s) for r, s in ordered[offset:offset + limit]]
    missing = [_event_brief(e) | {"page_stem": e["target"].get("page_stem")} for e in rv.missing_events(rule_id)]
    _report_rows(ordered, shown, missing, order, f, by, verdict, focus_index)
    return {"rule_id": rule_id, "extraction": rv.snap.ext, "total": len(ordered), "offset": offset, "rows": shown,
            "spread": _spread(rv, rule_id), "sample": sample if offset == 0 else None, "missing": missing,
            "focus_index": focus_index, "elapsed_ms": round(1000 * (time.perf_counter() - started), 1)}


@router.get("/catalogs/{catalog}/key-source")
def key_source(request: Request, catalog: str, occ: str, ext: str | None = None) -> dict:
    """Where a record's External Identifier came from (the Rules tab's record-key card, approved item 13): the rule
    that reads it, the text it was read from on the page, whether it was generated (`{type}-{normalized name}`), and
    the page rule that matched the page, with its URL pattern."""
    snap = _review(request, catalog, ext).snap
    o = snap.occurrences.get(occ)
    if o is None:
        raise not_found(occ)
    rid, from_code = model.key_rule_for(o["locator_rule_id"], snap.rules)
    key_rule = snap.rules.get(rid) if rid else None
    key_match = snap.matches_by_occ[occ].get(rid) if rid else None
    page = snap.rules.get(o.get("page_rule_id") or "") or {}
    return {"identifier": o["record_external_identifier"], "rule_id": rid,
            "rule_label": (key_rule or {}).get("property_label"), "from_code": from_code,
            "generated": _generated_key(snap, key_rule, o), "text": _key_text(snap, o, key_rule, key_match),
            "page_rule": rule_title(page, snap.rules)[0] if page else None,
            "url_pattern": (page.get("definition") or {}).get("url_regex")}


@router.get("/catalogs/{catalog}/match")
def match(request: Request, catalog: str, rule: str, occ: str, ext: str | None = None) -> dict:
    """One property rule's row on one occurrence, as `/rows` has it (its value, verdict, comments, review marks): what
    Evals and Compare show beside a diff, and what a note or a verdict there supersedes."""
    rv = _rule_review(request, catalog, rule, ext)
    snap = rv.snap
    rule_rows = snap.rows(rule)
    row = next((r for r in rule_rows if r["occurrence_key"] == occ), None)
    if row is None:
        raise not_found(f"{rule} has no row on {occ} in {snap.ext}")
    s = rv.row_states(rule, rule_rows).get(row["key"])  # every row: annotations re-attach across them
    r = snap.rules[rule]
    return {"rule_id": rule, "kind": r["kind"], "ctdl_property": r.get("ctdl_property"),
            "property_label": r.get("property_label"), "extraction": snap.ext, "key": row["key"],
            "occurrence_key": occ, "record_external_identifier": row["record_external_identifier"],
            "page_stem": row["page_stem"], "value": row["value"], "status": row["status"],
            "css_path": row["css_path"], "char_start": row["char_start"], "char_end": row["char_end"],
            **_judgement(s), "comments": _comments(s)}


@router.get("/catalogs/{catalog}/annotators")
def annotators(request: Request, catalog: str, ext: str | None = None, by: str | None = None,
               verdict: str | None = None) -> dict:
    """The "Annotated by" dropdown of the Rules and Records tabs (Evals spec §6.7, §6.8): `people` [{name, role,
    values}] (property values each annotated), `waiting` (values an engineer checked, waiting for an expert), `experts` /
    `engineers` (values any subject matter expert / any engineer annotated) and, with
    `by` or `verdict`, `rules` {rule_id: rows that pass the filter} for the rule list."""
    rv = _review(request, catalog, ext)
    out = rv.people()
    out["rules"] = {rid: rv.annotated_count(rid, by, verdict) for rid in rv.snap.rules} if by or verdict else None
    return out


@router.get("/catalogs/{catalog}/pages/{stem}/overlay")
def overlay(request: Request, catalog: str, stem: str, rule: str, ext: str | None = None) -> dict:
    """What the page pane outlines and marks in a record locator's view (spec §7.2): every course block the rule
    found on this page, numbered, and the text that looks like a course code outside all of them."""
    snap = _review(request, catalog, ext).snap
    if rule not in snap.rules:
        raise not_found(rule)
    blocks = sorted((o for loc in _outlined_locators(snap, rule) for o in snap.occ_by_locator.get(loc, [])
                     if o["page_stem"] == stem), key=lambda o: (o["locator_rule_id"], o["locator_index"]))
    marks = [s for s in snap.page_signals.get(stem, []) if s["signal"] == "uncovered-code" and s["rule_id"] == rule]
    return {"blocks": [{"occurrence_key": o["occurrence_key"], "css_path": o["css_path"], "n": i + 1,
                        "record_external_identifier": o["record_external_identifier"]} for i, o in enumerate(blocks)],
            "marks": [{"css_path": m["css_path"], "char_start": m["char_start"], "char_end": m["char_end"],
                       "detail": m["detail"]} for m in marks]}


@router.get("/catalogs/{catalog}/unclassified-pages")
def unclassified(request: Request, catalog: str, ext: str | None = None) -> list[dict]:
    """Pages no page rule recognised although they name many course codes ("Add a page this rule missed")."""
    rv = _review(request, catalog, ext)
    out = []
    for item in rv.snap.unclassified_pages():
        p = rv.snap.page[item["page_stem"]]
        out.append({"page_stem": item["page_stem"], "url": p["url"], "title": p["title"],
                    "detail": item["signals"][0]["detail"]})
    return sorted(out, key=lambda x: x["title"] or "")


@router.get("/catalogs/{catalog}/page-search")
def page_search(request: Request, catalog: str, q: str = "", rule: str | None = None, ext: str | None = None,
                limit: int = 30) -> list[dict]:
    """Saved pages whose title or address contains `q` ("Add a page this rule missed"), with whether `rule`
    already recognises each one."""
    rv = _review(request, catalog, ext)
    ql = q.strip().lower()
    out = []
    for stem, p in rv.snap.page.items():
        if ql and ql not in (p["title"] or "").lower() and ql not in (p["url"] or "").lower():
            continue
        out.append({"page_stem": stem, "url": p["url"], "title": p["title"],
                    "matched": bool(rule) and rule in rv.snap.matched_pages.get(stem, set())})
    out.sort(key=lambda x: (x["matched"], x["title"] or ""))
    return out[:limit]


# -- the rule list ------------------------------------------------------------------------------------------
def _kind_group(rv: Review, kind: str, label: str) -> dict:
    ids = sorted((rid for rid, r in rv.snap.rules.items() if r["kind"] == kind),
                 key=lambda r: (r not in PAGE_RULE_TITLES and r not in KNOWN_LOCATORS, r))
    items = [_rule_summary(rv, rid) for rid in ids]
    return {"id": kind, "kind": kind, "label": label, "rules": items, "collapsed": False,
            "approved": sum(1 for i in items if i["status"] == "approved")}


def _property_groups(rv: Review, ids_by_group: dict[str, list[str]]) -> list[dict]:
    groups = []
    for gid, label, collapsed in PROPERTY_GROUPS:
        if ids_by_group[gid]:
            items = [_rule_summary(rv, rid) for rid in ids_by_group[gid]]
            groups.append({"id": gid, "kind": "property", "label": label, "rules": items, "collapsed": collapsed,
                           "approved": sum(1 for i in items if i["status"] == "approved"),
                           "not_started": sum(1 for i in items if i.get("no_rule"))})
    return groups


def _property_ids_in_order(request: Request, snap: Snapshot) -> dict[str, list[str]]:
    """Required in sheet order; Phase 1 and 2 by values experts reviewed, then sheet order, no rule yet at the end;
    other record locators by locator."""
    counts = _expert_counts(request, snap)
    ids_by_group = _property_ids_by_group(snap)
    position = _list_position(snap)
    ids_by_group["required"].sort(key=position)
    for tier in ("phase1", "phase2"):
        ids_by_group[tier].sort(key=lambda rid: (snap.rules[rid]["definition"].get("rule_type") == "none",
                                                 -counts.get(rid, 0), *position(rid)[1:]))
    ids_by_group["program"].sort(key=lambda rid: (snap.rules[rid]["definition"]["locator"], *position(rid)))
    return ids_by_group


def _expert_counts(request: Request, snap: Snapshot) -> Counter:
    with_rules = [c["catalog"] for c in snap.ctx.manifest()["catalogs"] if manifest.has_rules(c, snap.ctx.cls)]
    return human_reviewed_counts(snap.ctx.root, with_rules, studio(request).ctx)


def _property_ids_by_group(snap: Snapshot) -> dict[str, list[str]]:
    rows_by_label = property_row(snap.ctx.cls)
    locator = properties.record_locator(snap.rules, snap.ctx.cls)
    ids_by_group: dict[str, list[str]] = {g: [] for g, _, _ in PROPERTY_GROUPS}
    for rid, r in snap.rules.items():
        if r["kind"] == "property":
            ids_by_group[property_group(r, rows_by_label, locator)].append(rid)
    return ids_by_group


def _list_position(snap: Snapshot):
    """A rule's place in the class's fixed order, then its sheet row, then its id."""
    rows_by_label, place = property_row(snap.ctx.cls), model.property_order(snap.ctx.cls)

    def position(rid: str) -> tuple:
        label = snap.rules[rid].get("property_label")
        row = rows_by_label.get(label)
        return (place.get(label, 99), row["sheet_row"] if row else 999, rid)
    return position


def property_group(rule: dict, rows: dict[str, dict], locator: str | None) -> str:
    """`rows`: the class's properties by label; `locator`: the class's record locator. A property the class's file
    doesn't list (an old rule) goes with Phase 2."""
    if rule["definition"].get("locator") not in (None, locator):
        return "program"
    row = rows.get(rule.get("property_label"))
    return properties.tier(row) if row is not None else "phase2"


def _rule_summary(rv: Review, rid: str) -> dict:
    rule = rv.snap.rules[rid]
    title, subtitle = rule_title(rule, rv.snap.rules)
    status = rv.rule_status(rid)
    talk = _rule_talk(rv, rid)
    page_q = sum(map(len, _page_questions(rv, rid).values())) if rule["kind"] == "page" else 0
    extra = _property_summary(rv, rule) if rule["kind"] == "property" else {}
    return {"rule_id": rid, "kind": rule["kind"], "version": rule["version"], "title": title, "subtitle": subtitle,
            "ctdl_property": rule.get("ctdl_property"), "property_label": rule.get("property_label"),
            "locator": rule["definition"].get("locator"), **status, "comments": talk["comments"] + talk["questions"],
            "page_questions": page_q, "rule_comments": talk["rule_comments"], **extra}


def _rule_talk(rv: Review, rid: str) -> dict[str, int]:
    """Comments on the rule's rows, comments on the rule itself, and questions."""
    return {"comments": sum(1 for e in rv.live if e["type"] == "comment" and e["target"].get("rule_id") == rid
                            and e["target"]["kind"] != "rule"),
            "rule_comments": sum(1 for e in rv.live if e["type"] == "comment" and e["target"]["kind"] == "rule"
                                 and e["target"].get("rule_id") == rid),
            "questions": sum(1 for e in rv.live if e["type"] == "verdict" and e.get("verdict") == "question"
                             and e["target"].get("rule_id") == rid)}


def _property_summary(rv: Review, rule: dict) -> dict:
    row = property_row(rv.snap.ctx.cls).get(rule.get("property_label"))
    path = rule.get("ctdl_property") or ""
    return {"required": bool(row and row["required"]), "record_key": bool(row and row["record_key"]),
            "tier": properties.tier(row) if row else None,
            "no_rule": rule["definition"].get("rule_type") == "none", "list": bool(rule["definition"].get("multiple")),
            "path_shown": properties.shown(path) or None,
            "parent_label": parent_name(path, rv.snap.ctx.cls) if ">" in path else None,
            "input": input_words(rule, rv.snap.rules)}


def input_words(rule: dict, rules: dict[str, dict]) -> str:
    """What a property rule reads, in words, for the rule header (§4.2): "the course record", "the whole page"…"""
    from ..engine import input_of

    d = rule["definition"]
    source = input_of(d)
    if d.get("rule_type") == "none":
        return "nothing yet: no rule"
    if d.get("rule_type") in model.DERIVED_RULE_TYPES:
        return "nothing on the page (a constant)" if d["rule_type"] == "constant" else "the page URL"
    return _source_words(rule, rules, source)


def _source_words(rule: dict, rules: dict[str, dict], source: dict) -> str:
    if source["from"] == "page":
        return "the whole page"
    if source["from"] == "url":
        return "the page URL"
    if source["from"] == "rule":
        name = rules.get(source.get("rule") or "", {}).get("property_label") or source.get("rule")
        return f"{name}'s {'element' if source.get('use') == 'element' else 'value'}"
    return f"the {RECORD_NOUN.get(_class_of(rule), ('record',))[0]} record"


# -- a rule's rows ------------------------------------------------------------------------------------------
def _matching_rows(rv: Review, rule_id: str, q: str | None, by: str | None, verdict: str | None) -> list:
    """The rule's rows in review order, with their states, that match the search and the "Annotated by" filter."""
    ordered = rv.ordered(rule_id)
    if q:
        ql = q.lower().replace(" ", "")
        ordered = [(r, s) for r, s in ordered if ql in (r.get("record_external_identifier") or "").lower()
                   or ql in (r.get("value") or "").lower().replace(" ", "") or ql in r["page_stem"]]
    if by or verdict:
        annotations = rv.annotations(rule_id)
        ordered = [(r, s) for r, s in ordered if annotated_match(annotations[r["key"]], by, verdict)]
    return ordered


def _check_order(order: str) -> None:
    if order not in facets.ORDERS:
        raise HTTPException(status_code=422, detail=f"order must be one of {', '.join(facets.ORDERS)}")


def _sampled_rows(rv: Review, rule_id: str, ordered: list, filters, order: str, cross: list[str] | None, seed: int,
                  prior: bool, by: str | None) -> tuple[list, dict, dict]:
    """The rows in the Sample drawer's order, its `sample`, and the rows whose record was reviewed elsewhere."""
    by_key = {r["key"]: (r, s) for r, s in ordered}
    keys, sample = facets.sample_order(rv.facet_dims(rule_id), list(by_key), filters, order,
                                       None if cross is None else [c for c in cross if c], seed)
    if by not in NOT_A_PERSON and "annotated_in" not in sample["tag_dims"]:  # whose rows: say which ruleset too
        sample["tag_dims"].append("annotated_in")
    elsewhere = rv.reviewed_elsewhere(rule_id, rv.snap.rows(rule_id), rv.row_states(rule_id, rv.snap.rows(rule_id)))
    sample["elsewhere"] = sum(1 for k in keys if k in elsewhere)
    sample["prior"] = prior
    if prior:
        keys = [k for k in keys if k in elsewhere] + [k for k in keys if k not in elsewhere]
    ordered = [by_key[k] for k in keys]
    if repeats(rv, rule_id):  # one row per page (sme-fixes §3): a page's courses together, in page order
        ordered = by_page(ordered)
    return ordered, sample, elsewhere


def _limit_with_focus(focus_index: int | None, offset: int, limit: int) -> int:
    if focus_index is not None and focus_index >= offset + limit:
        return focus_index - offset + 20
    return limit


@dataclass
class _RowView:
    """What every row of a /rows page is shown with."""
    snap: Snapshot
    dims: list
    tag_dims: list
    group: dict | None            # row key → spread group, in review order with no strata filter
    elsewhere: dict               # row key → the other rules its record was reviewed in, when `prior`
    page_questions: dict
    course_pages: dict
    per_page: Counter | None

    @classmethod
    def of(cls, request: Request, rv: Review, rule_id: str, tag_dims: list, grouped: bool, elsewhere: dict,
           prior: bool) -> _RowView:
        kind = rv.snap.rules[rule_id]["kind"]
        return cls(rv.snap, rv.facet_dims(rule_id), tag_dims, rv.spread_groups(rule_id)[1] if grouped else None,
                   elsewhere if prior else {}, _page_questions(rv, rule_id) if kind == "page" else {},
                   _course_pages(request, rv) if kind != "page" else {}, repeats(rv, rule_id))

    def row(self, r: dict, s) -> dict:
        return {**_row_value(self.snap, r), **_judgement(s), "reattached": s.reattached, "comments": _comments(s),
                "signal_count": len(r["signals"]) + len(s.history),
                "group": self.group.get(r["key"]) if self.group is not None else None,
                "tags": self._tags(r["key"]),
                "page_questions": [_event_brief(e) for e in self.page_questions.get(r["page_stem"], [])],
                "other_pages": self._other_pages(r), **_items(r, s),
                **({"page_courses": self.per_page[r["page_stem"]]} if self.per_page else {})}

    def _tags(self, key: str) -> list[dict]:
        tags = facets.tags(self.dims, key, self.tag_dims)
        if key not in self.elsewhere:
            return tags
        rules = ", ".join(_rule_name(self.snap.rules, x) for x in self.elsewhere[key])
        return tags + [{"dim": "elsewhere", "label": "Reviewed in", "bucket": rules}]

    def _other_pages(self, r: dict) -> list[dict]:
        others = [st for st in self.course_pages.get(r["record_external_identifier"], []) if st != r["page_stem"]][:6]
        return [{"page_stem": st, "url": self.snap.page[st]["url"], "title": self.snap.page[st]["title"]}
                for st in others]


def _row_value(snap: Snapshot, r: dict) -> dict:
    p = snap.page[r["page_stem"]]
    rei = r["record_external_identifier"]
    return {"key": r["key"], "occurrence_key": r["occurrence_key"], "record_external_identifier": rei,
            "key_generated": bool(rei and rei.startswith(f"{snap.ctx.ctdl_class.id_prefix}-")),
            "page_stem": r["page_stem"], "url": p["url"], "page_title": p["title"], "value": r["value"],
            "status": r["status"], "css_path": r["css_path"], "char_start": r["char_start"],
            "char_end": r["char_end"], "occurrence_css_path": r["occurrence_css_path"], "context": r["context"]}


def _items(row: dict, st) -> dict:
    """A list row's items, each with its own verdict (property-rules spec §4.4), and items marked missing."""
    if row.get("items") is None:
        return {}
    out = []
    for it in row["items"]:
        x = st.items.get(norm(it["value"]))
        out.append({**it, "state": x.state if x else None, "verdict": _event_brief(x.verdict) if x else None,
                    "human": bool(x and x.human)})
    return {"items": out, "missing_items": [_event_brief(e) for e in st.missing_items]}


def _spread(rv: Review, rule_id: str) -> dict:
    spread_by, group, group_order = rv.spread_groups(rule_id)
    sizes = Counter(group.values())
    return {"by": spread_by, "groups": [{"label": g, "rows": sizes[g]} for g in group_order if sizes[g]]}


def _report_rows(ordered: list, shown: list, missing: list, order: str, f: list[str] | None, by: str | None,
                 verdict: str | None, focus_index: int | None) -> None:
    telemetry.set({"ce.rows.total": len(ordered), "ce.rows.returned": len(shown), "ce.rows.missing": len(missing),
                   "ce.rows.order": order, "ce.rows.strata_filters": len(f or []),
                   "ce.rows.annotated_by": by, "ce.rows.verdict_filter": verdict, "ce.rows.focus_index": focus_index})


def _find_row(ordered: list, focus: str) -> int | None:
    """Index of the row a link asks for (`?row=`): its key, else an occurrence key, a record key or a page stem."""
    for name in ("key", "occurrence_key", "record_external_identifier", "page_stem"):
        for i, (r, _) in enumerate(ordered):
            if r.get(name) == focus:
                return i
    if "@" not in focus:  # a record key typed with a space, or lower case
        f = focus.replace(" ", "").upper()
        for i, (r, _) in enumerate(ordered):
            if (r.get("record_external_identifier") or "") == f:
                return i
    return None


def repeats(rv: Review, rule_id: str) -> Counter | None:
    """A record locator that finds several courses per page (`repeat`): how many it found on each page, else None."""
    rule = rv.snap.rules[rule_id]
    if rule["kind"] != "locator" or not rule["definition"].get("repeat"):
        return None
    return Counter(r["page_stem"] for r in rv.snap.rows(rule_id))


def by_page(ordered: list) -> list:
    """Rows grouped by page: pages in the order their first row comes, each page's courses in page order."""
    pages: dict[str, list] = {}
    for r, s in ordered:
        pages.setdefault(r["page_stem"], []).append((r, s))
    return [x for rs in pages.values() for x in sorted(rs, key=lambda x: x[0].get("locator_index") or 0)]


def _page_questions(rv: Review, rid: str) -> dict[str, list[dict]]:
    """Page-level questions and comments (target `{kind: page, rule_id: null}`) on the pages this page rule
    recognised, by page stem. v2's page notes became these (spec §5.5); the page rule's rows show them."""
    stems = {lb["page_stem"] for lb in rv.snap.labels_by_rule.get(rid, [])}
    out: dict[str, list[dict]] = {}
    for e in sorted(rv.live, key=lambda x: x["at"]):
        t = e["target"]
        if t.get("kind") == "page" and t.get("rule_id") is None and t.get("page_stem") in stems \
                and (e["type"] == "comment" or e.get("verdict") == "question"):
            out.setdefault(t["page_stem"], []).append(e)
    return out


def _course_pages(request: Request, rv: Review) -> dict[str, list[str]]:
    """record_external_identifier → page stems it was found on (course pages first), memoized per extraction."""
    snap = rv.snap
    key = ("w4-course-pages", snap.ctx.root.uri, snap.ctx.catalog, snap.ctx.cls, snap.ext)
    cache = studio(request).cache
    if key not in cache:
        cache[key] = _pages_per_record(snap)
    return cache[key]


def _pages_per_record(snap: Snapshot) -> dict[str, list[str]]:
    pages: dict[str, list[tuple]] = {}
    for o in snap.occurrences.values():
        if o["record_external_identifier"]:
            pages.setdefault(o["record_external_identifier"], []).append(
                (o["locator_rule_id"] != "locator-course-page", o["page_stem"]))
    return {record: list(dict.fromkeys(stem for _, stem in sorted(found))) for record, found in pages.items()}


def _rule_name(rules: dict[str, dict], rid: str) -> str:
    r = rules.get(rid)
    return (r and (r.get("property_label") or rule_title(r)[0])) or rid


# -- one record's key, a page's outlines ----------------------------------------------------------------------
def _key_text(snap: Snapshot, o: dict, key_rule: dict | None, key_match: dict | None) -> str | None:
    """The text on the page the record's key was read from."""
    from .. import engine

    if not (key_match and key_match.get("full_css_path")):
        return None
    try:
        doc = engine.parse(snap.ctx.page_path(o["page_stem"]).read_bytes())
        el = _key_element(doc, key_match["full_css_path"], (key_rule or {}).get("definition") or {})
        return " ".join(el.text_content().split())[:160] if el is not None else None
    except (OSError, ValueError, re.error):
        return None


def _key_element(doc, css_path: str, definition: dict):
    from .. import engine

    el = engine.select_one(doc, css_path, True)
    if definition.get("regex") and definition.get("selector"):  # a joined read: the smallest element whose text has the match
        hits = [x for top in engine.select(doc, definition["selector"]) for x in top.iter()
                if isinstance(x.tag, str) and re.search(definition["regex"], " ".join(x.text_content().split()))]
        el = min(hits, key=lambda x: len(x.text_content())) if hits else el
    return el


def _generated_key(snap: Snapshot, key_rule: dict | None, o: dict) -> bool:
    by_transform = bool(key_rule and any(str(t).startswith("generated_id:")
                                         for t in key_rule["definition"].get("transforms") or []))
    rei = o["record_external_identifier"] or ""
    return by_transform or rei.startswith(f"{snap.ctx.ctdl_class.id_prefix}-")  # from the rule's fallback


def _outlined_locators(snap: Snapshot, rule: str) -> list[str]:
    if snap.rules[rule]["kind"] == "page":  # a page rule's view outlines the courses its locators found
        return [rid for rid, r in snap.rules.items() if r["kind"] == "locator"
                and rule in (r["definition"].get("page_rules") or [])]
    return [rule]


# =====================================================================================================
# Courses (Records tab)
# =====================================================================================================
@router.get("/catalogs/{catalog}/courses")
def courses(request: Request, catalog: str, q: str | None = None, ext: str | None = None, limit: int = 50,
            who: Annotated[str | None, Query(alias="by")] = None, verdict: str | None = None) -> list[dict]:
    """Courses by code, the annotated first; `by` / `verdict` (the "Annotated by" filter, as on /rows): only the
    courses with a property value that passes it (`by=nobody`: no property value annotated)."""
    rv = _review(request, catalog, ext)
    records = _collect_records(rv)
    items = _annotated_first(rv, records)
    if who or verdict:
        items = _annotated_by(rv, items, who, verdict)
    if q:  # the identifier or the name (approved item 16)
        items = _search_records(items, q)
    telemetry.set({"ce.records.total": len(records), "ce.records.matched": len(items),
                   "ce.records.returned": len(items[:limit])})
    return items[:limit]


@router.get("/catalogs/{catalog}/courses/{record_external_identifier}")
def course(request: Request, catalog: str, record_external_identifier: str, ext: str | None = None) -> dict:
    rv = _review(request, catalog, ext)
    occurrences = _occurrences_of(rv.snap, record_external_identifier)
    if not occurrences:
        raise not_found(record_external_identifier)
    # the record's own pages: each rule's rows and states are built there alone (`rows_on`), not over the whole
    # catalog (every property rule's rows, and the parent's, took 10 s+ on the big catalogs for one record)
    states = _StatesOnPages(rv, {o["page_stem"] for o in occurrences})
    out = [_occurrence_view(rv, o, states) for o in occurrences]
    telemetry.set({"ce.record.occurrences": len(out), "ce.record.properties": sum(len(o["properties"]) for o in out)})
    return {"record_external_identifier": record_external_identifier, "extraction": rv.snap.ext, "occurrences": out}


def _collect_records(rv: Review) -> dict[str, dict]:
    records: dict[str, dict] = {}
    for o in rv.snap.occurrences.values():
        if o["record_external_identifier"] is not None:
            _add_occurrence(rv.snap, records, o)
    for item in records.values():
        item["pages"] = len(item["pages"])
    for e in rv.live:
        ck = e["target"].get("record_external_identifier")
        if ck in records and e["type"] in ("verdict", "comment") and not e["author"].startswith("golden-datasets"):
            records[ck]["annotated"] = True
    return records


def _add_occurrence(snap: Snapshot, records: dict[str, dict], o: dict) -> None:
    item = records.setdefault(o["record_external_identifier"], {
        "record_external_identifier": o["record_external_identifier"], "occurrences": 0, "line": None, "name": None,
        "pages": set(), "annotated": False})
    item["occurrences"] += 1
    item["pages"].add(o["page_stem"])
    if item["line"] is None or o["locator_rule_id"] == "locator-course-page":
        item["line"] = snap.course_line(o["occurrence_key"])
    if item["name"] is None:
        item["name"] = _found_name(snap, o)


def _found_name(snap: Snapshot, o: dict) -> str | None:
    name_rule = snap.name_rule.get(o["locator_rule_id"])
    m = snap.matches_by_occ[o["occurrence_key"]].get(name_rule) if name_rule else None
    return m["value"] if m and m["status"] == "found" else None


def _annotated_first(rv: Review, records: dict[str, dict]) -> list[dict]:
    """Records someone has looked at first (a dot in the list, screen 07), then courses by code and other classes'
    records by name (w2-records-lp: a generated identifier sorts with its name)."""
    named = rv.snap.ctx.cls != "course"
    return sorted(records.values(), key=lambda x: (not x["annotated"], ((x["name"] or "").casefold() if named else ""),
                                                   x["record_external_identifier"]))


def _annotated_by(rv: Review, items: list[dict], who: str | None, verdict: str | None) -> list[dict]:
    keep, touched = _records_annotated(rv, who, verdict)
    if who == "nobody":
        return [i for i in items if i["record_external_identifier"] not in touched]
    return [i for i in items if i["record_external_identifier"] in keep]


def _records_annotated(rv: Review, who: str | None, verdict: str | None) -> tuple[set[str], set[str]]:
    """The records with a property value that passes the filter, and those with any annotated property value."""
    keep, touched = set(), set()
    for rid, r in rv.snap.rules.items():
        if r["kind"] != "property":
            continue
        for k, a in rv.annotations(rid).items():
            record = rv.snap.occurrences[k]["record_external_identifier"]
            if a["people"]:
                touched.add(record)
            if annotated_match(a, who, verdict):
                keep.add(record)
    return keep, touched


def _search_records(items: list[dict], q: str) -> list[dict]:
    ql = q.lower().replace(" ", "")
    return [i for i in items if ql in i["record_external_identifier"].lower()
            or ql in (i["line"] or "").lower().replace(" ", "") or ql in (i["name"] or "").lower().replace(" ", "")]


def _occurrences_of(snap: Snapshot, record: str) -> list[dict]:
    return sorted((o for o in snap.occurrences.values() if o["record_external_identifier"] == record),
                  key=lambda o: (o["locator_rule_id"] != "locator-course-page", o["page_stem"], o["locator_index"]))


class _StatesOnPages:
    """Each rule's row states on a record's pages alone (`Snapshot.rows_on`), built once per rule."""

    def __init__(self, rv: Review, stems: set[str]):
        self.rv, self.stems, self.states = rv, stems, {}

    def of(self, rule_id: str, occurrence_key: str):
        if rule_id not in self.states:
            rows_there = self.rv.snap.rows_on(rule_id, self.stems)
            self.states[rule_id] = self.rv.row_states(rule_id, rows_there, self.stems)
        return self.states[rule_id].get(occurrence_key)


def _occurrence_view(rv: Review, o: dict, states: _StatesOnPages) -> dict:
    props = [_property_view(rv, o, rid, states.of(rid, o["occurrence_key"])) for rid in _rule_ids_on(rv.snap, o)]
    p = rv.snap.page[o["page_stem"]]
    return {"occurrence_key": o["occurrence_key"], "page_stem": o["page_stem"], "url": p["url"],
            "page_title": p["title"], "locator_rule_id": o["locator_rule_id"],
            "css_path": o["css_path"], "properties": props}


def _rule_ids_on(snap: Snapshot, o: dict) -> list[str]:
    """Every property of the occurrence's record locator, with a rule or not (R1), in the class's order."""
    place = model.property_order(snap.ctx.cls)
    rids = [rid for rid, r in snap.rules.items() if r["kind"] == "property"
            and r["definition"].get("locator") == o["locator_rule_id"]]
    return sorted(rids, key=lambda x: (place.get(snap.rules[x].get("property_label"), 99), x))


def _property_view(rv: Review, o: dict, rid: str, s) -> dict:
    snap = rv.snap
    r = snap.rules[rid]
    m = snap.matches_by_occ[o["occurrence_key"]].get(rid) or NO_MATCH
    found = [x for x in snap.items_by_occ[o["occurrence_key"]].get(rid) or [] if x["status"] == "found"]
    is_list = bool(r["definition"].get("multiple"))
    return {"rule_id": rid, "property_label": r.get("property_label"), "ctdl_property": r.get("ctdl_property"),
            "value": profiles_rule.row_value(found) if is_list and found else m["value"], "status": m["status"],
            "css_path": m["full_css_path"], "char_start": m["char_start"], "char_end": m["char_end"],
            **({"items": [list_item(x, o["css_path"]) for x in found]} if is_list else {}),
            **_judgement(s), "annotators": (rv.annotation(s) if s else {"people": {}})["people"],
            "comments": _comments(s)}


# =====================================================================================================
# Annotations
# =====================================================================================================
@router.post("/catalogs/{catalog}/annotations")
def add_annotation(request: Request, catalog: str, event: Annotated[dict, Body()]) -> dict:
    """Append one event (verdict · comment · approve · reopen). The server assigns the id and the time and fills
    the target from the current extraction; the client sends type, author, target {kind, rule_id, key…},
    verdict, expected (its segments `in` or `out` of the answer), note, supersedes, anchor (a comment's text on the
    page), and optionally author_role (else the author's profile says it) and
    compared_with. A verdict on a value rewrites its page's file in the latest golden dataset (Evals spec §4.3)."""
    started = time.perf_counter()
    rv = _review(request, catalog, event.get("extraction"))
    full = _full_event(rv, event, _target(rv, event))
    _check_event(rv, full)
    _report_annotation(full)
    _append(rv.snap.ctx, full)
    after = _review(request, catalog, rv.snap.ext)
    published, score = _publish_after(request, rv.snap.ctx, after, full)
    _report_published(full, published, score)
    rid = full["target"]["rule_id"]
    return {"event": full, "rule": _rule_summary(after, rid) if rid else None, "published": published,
            "score": score, "elapsed_ms": round(1000 * (time.perf_counter() - started), 1)}


@router.get("/catalogs/{catalog}/rules/{rule_id}/reset-preview")
def reset_preview(request: Request, catalog: str, rule_id: str) -> dict:
    """The Reset rule dialog's numbers: what a reset clears (✓, ✕ with an answer, by author), the approval it ends,
    what it keeps, and whether the property's column leaves the silver dataset."""
    rv = _review(request, catalog)
    if rule_id not in rv.snap.rules:
        raise not_found(f"unknown rule {rule_id}")
    status = rv.rule_status(rule_id)
    prop = rv.snap.rules[rule_id].get("property_label")
    column = _golden_column(rv.snap.ctx, prop)
    return {"rule_id": rule_id, "property": prop, **_reset_counts(rv, rule_id), "approval": _approval(status),
            "column": column}


@router.get("/catalogs/{catalog}/discussion")
def discussion(request: Request, catalog: str) -> dict:
    """Comments on a whole rule or on the ruleset (the Rules tab sidebar): {ruleset: [...], rules: {rule_id: [...]}}.
    Each: annotation_id, author, at, note, topic (new-rule · approach · question-rule · other), rule_version_seen."""
    talk = _review(request, catalog).discussion()
    return {"ruleset": [_discussion_brief(e) for e in talk["ruleset"]],
            "rules": {rid: [_discussion_brief(e) for e in es] for rid, es in talk["rules"].items()}}


@router.get("/catalogs/{catalog}/annotations")
def list_annotations(request: Request, catalog: str, rule: str | None = None) -> list[dict]:
    rv = _review(request, catalog)
    return [e for e in rv.live if rule is None or e["target"].get("rule_id") == rule]


# -- filling in an event --------------------------------------------------------------------------------------
def _target(rv: Review, event: dict) -> dict:
    """The event's target, filled in from the current extraction: the versions seen, the record and page, the value
    seen."""
    t = dict(event.get("target") or {})
    _stamp_versions(rv.snap, t)
    t["extraction_seen"] = rv.snap.ext
    if t.get("kind") in ("match", "occurrence") and t.get("occurrence_key"):
        _place_on_occurrence(rv, event, t)
    for k in TARGET_FIELDS:
        t.setdefault(k, None)
    if not t.get("item"):
        t.pop("item", None)
    return t


def _stamp_versions(snap: Snapshot, t: dict) -> None:
    rid = t.get("rule_id")
    if t.get("kind") == "ruleset":  # a comment on the whole ruleset: no rule
        t["rule_id"] = None
        t["ruleset_version_seen"] = snap.ruleset_version
    elif t.get("kind") != "page" or rid is not None:
        if rid not in snap.rules:
            raise HTTPException(400, f"unknown rule {rid}")
        t["rule_version_seen"] = snap.rules[rid]["version"]


def _place_on_occurrence(rv: Review, event: dict, t: dict) -> None:
    o = rv.snap.occurrences.get(t["occurrence_key"])
    if o is None:
        raise HTTPException(400, "unknown occurrence_key")
    t["record_external_identifier"], t["page_stem"] = o["record_external_identifier"], o["page_stem"]
    if t["kind"] == "match":
        t["value_index"], t["value_seen"] = _value_seen(rv, event, t, o)


def _value_seen(rv: Review, event: dict, t: dict, o: dict) -> tuple[int | None, str | None]:
    rid = t["rule_id"]
    definition = rv.snap.rules[rid]["definition"]
    items = rv.snap.items_by_occ[o["occurrence_key"]].get(rid) or []
    if definition.get("rule_type") == "none":  # no rule yet: anyone can still say what the page shows
        if definition.get("locator") != o["locator_rule_id"]:
            raise HTTPException(400, f"{rid} has no row on this occurrence")
        return None, None
    if t.get("item"):  # one item of a list (property-rules spec §4.4)
        return _item_seen(rv, event, t, items)
    if not items:
        raise HTTPException(400, f"{rid} has no row on this occurrence")
    found = [x["value"] for x in items if x["status"] == "found"]
    return 0, "\n".join(found) if definition.get("multiple") and found else items[0]["value"]


def _item_seen(rv: Review, event: dict, t: dict, items: list[dict]) -> tuple[int | None, str | None]:
    if event.get("verdict") == "missing":
        return None, None
    if t.get("value_index") is None and event.get("supersedes"):
        return None, _taken_back_text(rv, event)
    m = next((x for x in items if x["value_index"] == t.get("value_index") and x["status"] == "found"), None)
    if m is None:
        raise HTTPException(400, f"{t['rule_id']} has no item {t.get('value_index')} on this occurrence")
    return m["value_index"], m["value"]


def _taken_back_text(rv: Review, event: dict) -> str | None:
    """✕ on an object a reviewer added: it takes the add back (phase1-followups spec §3.4)."""
    added = rv.by_id.get(event["supersedes"])
    if added is None or added.get("verdict") != "missing":
        raise HTTPException(400, "only an added item can be taken back")
    return (added.get("expected") or {}).get("text")


def _full_event(rv: Review, event: dict, t: dict) -> dict:
    full = _event_core(rv.snap.ctx, event, t)
    if event.get("topic"):
        full["topic"] = event["topic"]
    if event.get("anchor") is not None:  # a comment on a piece of text on the page (sme-fixes §1)
        full["anchor"] = event["anchor"]
    role = event.get("author_role") or role_of(full, roles(rv.snap.ctx.root))
    if role:
        full["author_role"] = role
    if event.get("compared_with") is not None:
        full["compared_with"] = event["compared_with"]
    if event.get("reasons"):  # "Why wrong?" flags on a ✕ (sme-fixes §6)
        full["reasons"] = event["reasons"]
    if full["type"] == "reset":  # what the confirm dialog showed, for the record (nothing reads it back)
        full["counts"] = _reset_counts(rv, t["rule_id"])["counts"]
    return full


def _event_core(ctx, event: dict, t: dict) -> dict:
    return {"annotation_id": new_id("ap" if event.get("type") in ("approve", "reopen", "reset") else "an"),
            "type": event.get("type"), "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "author": (event.get("author") or "").strip(), "catalog": ctx.catalog, "crawl": ctx.crawl, "target": t,
            "verdict": event.get("verdict"), "expected": profiles_rule.with_object_text(event.get("expected")),
            "note": event.get("note") or None,
            "supersedes": event.get("supersedes")}


def _check_event(rv: Review, full: dict) -> None:
    if full["type"] == "approve":
        status = rv.rule_status(full["target"]["rule_id"])
        if status["open_wrong"] or status["open_missing"]:
            raise HTTPException(409, "a course is marked wrong or missing for this rule; it can't be approved")
    try:
        validate(full)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


def _append(ctx, full: dict) -> None:
    log = LOADER.log(ctx)
    log.append(full)
    log.refresh()


def _report_annotation(full: dict) -> None:
    t = full["target"]
    telemetry.set({"ce.annotation.type": full["type"], "ce.annotation.verdict": full.get("verdict"),
                   "ce.annotation.target_kind": t["kind"], "ce.annotation.author_role": full.get("author_role"),
                   "ce.rule.id": t["rule_id"], "ce.course.key": t.get("course_key"), "ce.page.stem": t.get("page_stem")})


def _report_published(full: dict, published: dict | None, score: dict | None) -> None:
    telemetry.set({"ce.annotation.id": full.get("annotation_id"),
                   "ce.golden.published": bool(published and published.get("written")),
                   "ce.golden.publication": (published or {}).get("publication"),
                   "ce.golden.publish_error": (published or {}).get("error"), "ce.score.id": (score or {}).get("id")})


# -- what an event publishes --------------------------------------------------------------------------------
def _publish_after(request: Request, ctx, rv: Review, full: dict) -> tuple[dict | None, dict | None]:
    """What the event changes in the golden dataset, and the score that follows: a verdict on a value rewrites its
    page; approving a column's rule publishes it, then scores it (Evals spec §4.1, §6.6); a reset takes the column out
    of the silver dataset and the cleared values out of the golden one (§4.5)."""
    if full["type"] == "verdict" and full["target"]["kind"] == "match":
        return _publish_page(ctx, rv, full), None
    if full["type"] == "approve":
        return _publish_approval(request, ctx, rv, full)
    if full["type"] == "reset":
        return _publish_reset(request, ctx, rv, full)
    return None, None


def _publish_page(ctx, rv: Review, full: dict) -> dict:
    t, rid = full["target"], full["target"]["rule_id"]
    try:  # the verdict is saved either way; say if its page's golden file couldn't be rewritten
        with telemetry.span("golden.publish_page", {"ce.page.stem": t["page_stem"]}):
            return golden.publish_page(ctx, t["page_stem"], f"{full['author']} marked {rid} {full['verdict']}",
                                       f"{full['author']} via the Studio UI", create=full.get("author_role") == "sme",
                                       column=_column_of(rv, rid, ctx.cls) if rid in rv.snap.rules else None)
    except (OSError, UserError) as exc:
        return {"error": str(exc)}


def _publish_approval(request: Request, ctx, rv: Review, full: dict) -> tuple[dict | None, dict | None]:
    rid = full["target"]["rule_id"]
    what = golden.approval_publishes(rv, rid)
    if not what:
        return None, None
    if not what["writes"]:
        return {"written": False, "column": None, "property": what["property"]}, None
    try:
        return _publish_approved(request, ctx, rid, full["author"], what["column"])
    except (OSError, UserError) as exc:
        return {"error": str(exc)}, None


def _publish_approved(request: Request, ctx, rid: str, author: str, column: str) -> tuple[dict, dict | None]:
    with telemetry.span("golden.publish", {"ce.golden.reason": "approve", "ce.rule.id": rid}):
        doc = golden.publish_approved(ctx, rid, f"{author} via the Studio UI")
        telemetry.set({"ce.golden.publication": doc["publication"], "ce.golden.files": doc["pages"]})
    published = {"written": True, "publication": doc["publication"], "created": doc["created"],
                 "column": column, "columns": golden.columns_of(doc["properties"]), "files": doc["pages"]}
    return published, _score_after(request, ctx, author, [column])


def _publish_reset(request: Request, ctx, rv: Review, full: dict) -> tuple[dict | None, dict | None]:
    rid = full["target"]["rule_id"]
    try:
        with telemetry.span("golden.publish", {"ce.golden.reason": "reset", "ce.rule.id": rid}):
            doc = golden.publish_reset(ctx, rid, f"{full['author']} via the Studio UI", full["note"])
        if not doc:
            return None, None
        published = {"written": True, "publication": doc["publication"],
                     "columns": golden.columns_of(doc["properties"]), "files": doc["pages"]}
        column = _column_of(rv, rid, ctx.cls)
        return published, _score_after(request, ctx, full["author"], [column] if column else None)
    except (OSError, UserError) as exc:
        return {"error": str(exc)}, None


def _score_after(request: Request, ctx, author: str, columns: list[str] | None) -> dict | None:
    job = request.app.state.scores.after_publish(ctx, author, columns)
    return {k: job[k] for k in ("id", "status")} | {"golden": job["golden"]["id"]} if job else None


def _column_of(rv: Review, rid: str, cls: str) -> str | None:
    return golden.column_name(rv.snap.rules[rid].get("property_label") or "", cls)


# -- reset and discussion -----------------------------------------------------------------------------------
def _reset_counts(rv: Review, rid: str) -> dict:
    """What Reset rule clears and keeps on this rule (phase1-followups spec §4.3): the verdicts that make a value
    human (✓, and ✕ with an answer), by author, and the ✕ with no answer, questions and comments that stay."""
    mine = [e for e in rv.live if e["target"].get("rule_id") == rid and e["target"].get("kind") != "rule"]
    cleared = [e for e in mine if reset_clears(e)]
    by = Counter(FULL_NAMES.get(e["author"], e["author"]) for e in cleared)
    return {"counts": {"correct": sum(e["verdict"] == "correct" for e in cleared),
                       "answered": sum(e["verdict"] != "correct" for e in cleared)},
            "by_author": dict(by.most_common()),
            "kept": {"wrong_no_answer": sum(e["type"] == "verdict" and e["verdict"] in ("wrong", "missing")
                                            and not reset_clears(e) for e in mine),
                     "questions": sum(e.get("verdict") == "question" for e in mine),
                     "comments": sum(e["type"] == "comment" for e in mine)}}


def _golden_column(ctx, prop: str | None) -> dict | None:
    """The property's column in the latest golden dataset, if it has one."""
    versions = golden.versions(ctx)
    if not versions:
        return None
    latest = max(versions)
    if prop not in _published_properties(ctx, versions[latest]["path"]):
        return None
    return {"column": golden.column_name(prop), "golden": golden.version_name(latest)}


def _published_properties(ctx, path: str) -> list[str]:
    try:
        return ctx.read_json(f"{path}/publication.json", immutable=False).get("properties") or []
    except FileNotFoundError:
        return []


def _approval(status: dict) -> dict | None:
    if status["status"] != "approved":
        return None
    return {"by": FULL_NAMES.get(status["approved_by"], status["approved_by"]), "at": status["approved_at"]}


def _discussion_brief(e: dict) -> dict:
    t = e["target"]
    return {"annotation_id": e["annotation_id"], "author": e["author"], "at": e["at"], "note": e.get("note"),
            "topic": e.get("topic"), "rule_id": t.get("rule_id"), "rule_version_seen": t.get("rule_version_seen"),
            "ruleset_version_seen": t.get("ruleset_version_seen")}


# =====================================================================================================
# Shared: the review behind a request, rule titles, events as the client sees them
# =====================================================================================================
def _review(request: Request, catalog: str, ext: str | None = None) -> Review:
    ctx = studio(request).ctx(catalog)
    try:
        ext = ext or ctx.latest_extraction()
    except UserError as exc:
        raise not_found(str(exc)) from None
    if not ext:
        raise not_found(f"{catalog}: no extraction yet")
    rv = LOADER.review(ctx, ext)
    rv.report_sizes()
    telemetry.set({"ce.extraction.id": ext, "ce.ruleset.version": rv.snap.ruleset_version, "ce.crawl.id": ctx.crawl})
    return rv


def _rule_review(request: Request, catalog: str, rule_id: str, ext: str | None) -> Review:
    rv = _review(request, catalog, ext)
    if rule_id not in rv.snap.rules:
        raise not_found(f"{rule_id} is not in ruleset v{rv.snap.ruleset_version}")
    return rv


def rule_title(rule: dict, rules: dict[str, dict] | None = None) -> tuple[str, str]:
    """(title, subtitle) as the rule list shows them (screen 03). `rules` (the ruleset's): a page rule whose pages a
    repeating record locator reads is "Pages with courses", not a single course's own page."""
    if rule["kind"] == "page":
        return _page_rule_title(rule, rules or {})
    if rule["kind"] == "locator":
        return locator_title(rule["definition"], _class_of(rule))
    label = _property_title(rule, rules)
    path = rule.get("ctdl_property") or ""
    if ">" in path:  # a child: no path in the sidebar, the parent's name instead (#8)
        return label, f"part of {parent_name(path, _class_of(rule))}"
    return label, path or "no CTDL term"


def _page_rule_title(rule: dict, rules: dict[str, dict]) -> tuple[str, str]:
    repeats = any(r["kind"] == "locator" and r["definition"].get("repeat")
                  and rule["rule_id"] in (r["definition"].get("page_rules") or []) for r in rules.values())
    return (PAGE_RULE_TITLES.get(rule["rule_id"], rule["rule_id"]),
            "Pages with courses" if repeats else PLAIN_SUBTITLES.get(rule["rule_id"]) or rule.get("what") or "")


def _property_title(rule: dict, rules: dict[str, dict] | None) -> str:
    """The property's label, and the record locator it reads when that isn't the class's own."""
    label = rule.get("property_label") or rule["rule_id"]
    own = (properties.record_locator(rules, _class_of(rule)) if rules else None) or "locator-course-page"
    locator = rule["definition"].get("locator")
    if locator in (None, own, f"locator-{_class_of(rule)}-page"):
        return label
    return label + (" · program pages" if locator == "locator-program-requirement"
                    else f" · {locator.removeprefix('locator-')}")


def locator_title(d: dict, cls: str = "course") -> tuple[str, str]:
    """A record locator's (title, subtitle), from what its definition does (sme-fixes §3): with `repeat`, many records
    share a page (CCSF's department pages); without, the page is one record (AVC). In the class's words."""
    one, many = RECORD_NOUN.get(cls, ("record", "records"))
    if d.get("repeat"):
        return (f"{one.capitalize()} blocks: every {d['repeat']} on the page",
                f"Several {many} on one page, one block each")
    return f"Whole page is one {one}", f"Each page's content area is one {one}"


def parent_name(path: str, cls: str = "course") -> str:
    parent = path.split(">", 1)[0]
    return next((r["label"] for r in properties.active(cls) if r["path"] == parent), properties.label_of(parent))


def property_row(cls: str) -> dict[str, dict]:
    """A class's properties by label."""
    return {r["label"]: r for r in model.property_rows(cls)}


def _class_of(rule: dict) -> str:
    """The class a rule's id names (`learningprogram-name`), else Course."""
    c = classes.of_rule(rule["rule_id"])
    return c.slug if c else "course"


def _judgement(s) -> dict:
    """A row's state, verdict and review marks; all empty for a row with no state."""
    return {"state": s.state if s else None, "verdict": _event_brief(s.verdict) if s else None, **_review_state(s)}


def _comments(s) -> list[dict]:
    return [_event_brief(c) for c in s.comments] if s else []


def _review_state(s) -> dict:
    """Whether an expert confirmed the value (human-reviewed: `human` is their verdict), or only an engineer did
    (waiting for an expert); `checked` is the latest engineer's ✓ (the check an expert confirmed, or waits on)."""
    if s is None:
        return {"human_reviewed": False, "engineer_checked": False, "role": None, "human": None, "checked": None,
                "before_reset": None}
    return {"human_reviewed": s.human is not None, "engineer_checked": s.engineer_checked, "role": s.role,
            "human": _by_full_name(s.human), "checked": _by_full_name(s.checked),
            "before_reset": _by_full_name(s.before_reset)}


def _by_full_name(e: dict | None) -> dict | None:
    """The event's brief, its first-name author (the first profiles) by their full name."""
    return e and {**_event_brief(e), "author": FULL_NAMES.get(e["author"], e["author"])}


def _event_brief(e: dict | None) -> dict | None:
    if e is None:
        return None
    return {"annotation_id": e["annotation_id"], "type": e["type"], "verdict": e.get("verdict"), "author": e["author"],
            "author_role": e.get("author_role"), "at": e["at"], "note": e.get("note"), "expected": e.get("expected"),
            "compared_with": e.get("compared_with"), "anchor": e.get("anchor"),
            **({"reasons": e["reasons"]} if e.get("reasons") else {}),
            "rule_version_seen": e["target"].get("rule_version_seen"), "value_seen": e["target"].get("value_seen"),
            **run_fields(e)}


def run_fields(e: dict) -> dict:
    """Claude's comments from a run (one-rule-runs spec §1.6): the run, the ruleset it published (or started from), and
    when the run started (read from its id), for "(v10, AI run Nov 6)". Null on people's events."""
    rid = e.get("run_id")
    at = None
    if rid and len(rid) >= 16 and rid[8] == "T":
        at = f"{rid[0:4]}-{rid[4:6]}-{rid[6:8]}T{rid[9:11]}:{rid[11:13]}:{rid[13:15]}Z"
    return {"run_id": rid, "ruleset_version": e.get("ruleset_version"), "run_at": at}
