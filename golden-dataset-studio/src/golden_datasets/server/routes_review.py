"""Review API (W4): catalogs, rules, rows, page overlays, courses (Records tab) and annotations.

Every list is computed from one in-memory `Snapshot` of an extraction plus the annotation log (read
incrementally), so a request costs milliseconds once the extraction is loaded (spec §10).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request

from .. import layout, model
from ..catalogs import CATALOGS, info
from ..errors import UserError
from ..log import new_id, validate
from ..review import LOADER, Review
from .state import not_found, studio

router = APIRouter(prefix="/api")

PAGE_RULE_TITLES = {"course-page": "Course pages", "program-page": "Program pages",
                    "program-page-with-courses": "Program pages that list courses"}
PLAIN_SUBTITLES = {"course-page": "Which pages are a single course's own page",
                   "program-page": "Which pages describe a degree or certificate",
                   "program-page-with-courses": "Which program pages name courses in their requirements",
                   "locator-course-page": "Where each course starts and ends on a course page",
                   "locator-program-requirement": "Where each course starts and ends on a program page"}
LOCATOR_TITLES = {"locator-course-page": "One course per course page",
                  "locator-program-requirement": "One course per requirement line"}


def rule_title(rule: dict) -> tuple[str, str]:
    """(title, subtitle) as the rule list shows them (screen 03)."""
    if rule["kind"] == "page":
        return (PAGE_RULE_TITLES.get(rule["rule_id"], rule["rule_id"]),
                PLAIN_SUBTITLES.get(rule["rule_id"]) or rule.get("what") or "")
    if rule["kind"] == "locator":
        return LOCATOR_TITLES.get(rule["rule_id"], "One course per " + rule["rule_id"].removeprefix("locator-")
                                  .replace("-", " ")), PLAIN_SUBTITLES.get(rule["rule_id"]) or rule.get("what") or ""
    label = rule.get("property_label") or rule["rule_id"]
    if rule["definition"].get("locator") not in (None, "locator-course-page"):
        label += " · program pages" if rule["definition"]["locator"] == "locator-program-requirement" \
            else f" · {rule['definition']['locator'].removeprefix('locator-')}"
    return label, rule.get("ctdl_property") or "no CTDL term"


def _review(request: Request, catalog: str, ext: str | None = None) -> Review:
    ctx = studio(request).ctx(catalog)
    try:
        ext = ext or ctx.latest_extraction()
    except UserError as exc:
        raise not_found(str(exc)) from None
    if not ext:
        raise not_found(f"{catalog}: no extraction yet")
    return LOADER.review(ctx, ext)


def _event_brief(e: dict | None) -> dict | None:
    if e is None:
        return None
    return {"annotation_id": e["annotation_id"], "type": e["type"], "verdict": e.get("verdict"), "author": e["author"],
            "at": e["at"], "note": e.get("note"), "expected": e.get("expected"),
            "rule_version_seen": e["target"].get("rule_version_seen"), "value_seen": e["target"].get("value_seen")}


# =====================================================================================================
# Catalogs
# =====================================================================================================
def approved_count(ruleset: dict, events: list[dict]) -> int:
    """Rules of this ruleset whose latest approve / reopen event for their current version is an approve."""
    superseded = {e["supersedes"] for e in events if e.get("supersedes")}
    last: dict[tuple, str] = {}
    for e in sorted((e for e in events if e["annotation_id"] not in superseded), key=lambda e: e["at"]):
        t = e.get("target") or {}
        if e["type"] in ("approve", "reopen") and t.get("kind") == "rule":
            last[(t.get("rule_id"), t.get("rule_version_seen"))] = e["type"]
    return sum(1 for r in ruleset["rules"] if last.get((r["rule_id"], r["version"])) == "approve")


@router.get("/catalogs")
def catalogs(request: Request) -> list[dict]:
    st = studio(request)
    doc = st.ctx(next(iter(CATALOGS))).manifest()
    entries = {c["catalog"]: c for c in doc["catalogs"]}
    out = []
    for folder in sorted(set(CATALOGS) | set(entries), key=lambda f: info(f)["name"].lower()):
        meta, e = info(folder), entries.get(folder)
        item = {"catalog": folder, "short": meta["short"], "name": meta["name"], "institution": meta["institution"],
                "platform": meta["platform"], "logo": f"/logos/{meta['logo']}" if meta.get("logo") else None,
                "pages": None, "crawl": None, "ruleset_version": None, "rules_total": 0, "rules_approved": 0,
                "status": "not imported"}
        if e:
            k = next((c for c in e["crawls"] if c["crawl"] == e.get("current_crawl")), None)
            item.update(pages=(k or {}).get("page_count"), crawl=e.get("current_crawl"))
            if e.get("rulesets") and k and k.get("extractions"):
                # Only the ruleset and the log are needed to count approvals, not the extraction: the picker stays
                # fast on a cold cache (spec §10).
                ctx = st.ctx(folder)
                ext = next((x for x in sorted(k["extractions"], key=lambda x: (x["ruleset_version"], x["extraction"]))
                            [::-1]), None)
                rs = ctx.ruleset(ext["ruleset_version"])
                events = LOADER.log(ctx).events()
                item.update(status="ready", ruleset_version=rs["version"], rules_total=len(rs["rules"]),
                            rules_approved=approved_count(rs, events))
        out.append(item)
    return out


@router.get("/catalogs/{catalog}")
def catalog(request: Request, catalog: str, ext: str | None = None) -> dict:
    rv = _review(request, catalog, ext)
    ctx = rv.snap.ctx
    meta = info(ctx.catalog)
    k = ctx.crawl_entry()
    rulesets = []
    for v in ctx.ruleset_versions():
        rs = ctx.ruleset(v)
        rulesets.append({"version": v, "note": rs.get("note"), "published_at": rs.get("published_at"),
                         "published_by": rs.get("published_by"), "changed_rules": rs.get("changed_rules", []),
                         "extraction": ctx.extraction_for(v)})
    retrieved = None
    try:
        crawl_json = ctx.read_json(layout.crawl_json(ctx.catalog, ctx.crawl))
        retrieved = crawl_json.get("run_id")
    except FileNotFoundError:
        pass
    authors = sorted({e["author"] for e in rv.events if not e["author"].startswith("golden-datasets")})
    return {"catalog": ctx.catalog, "short": meta["short"], "name": meta["name"], "institution": meta["institution"],
            "logo": f"/logos/{meta['logo']}" if meta.get("logo") else None, "crawl": ctx.crawl,
            "crawl_started": retrieved or ctx.crawl, "pages": k.get("page_count"),
            "extraction": rv.snap.ext, "ruleset_version": rv.snap.ruleset_version,
            "extractions": [{"extraction": e["extraction"], "ruleset_version": e["ruleset_version"],
                             "parent_extraction": e.get("parent_extraction")} for e in ctx.extractions()],
            "rulesets": rulesets, "authors": authors, "pane_css": rv.snap.settings.get("pane_css", ""),
            "root": ctx.root.uri}


# =====================================================================================================
# Rules
# =====================================================================================================
def _rule_summary(rv: Review, rid: str) -> dict:
    rule = rv.snap.rules[rid]
    title, subtitle = rule_title(rule)
    st = rv.rule_status(rid)
    comments = sum(1 for e in rv.live if e["type"] in ("comment",) and e["target"].get("rule_id") == rid)
    questions = sum(1 for e in rv.live if e["type"] == "verdict" and e.get("verdict") == "question"
                    and e["target"].get("rule_id") == rid)
    page_q = sum(map(len, _page_questions(rv, rid).values())) if rule["kind"] == "page" else 0
    return {"rule_id": rid, "kind": rule["kind"], "version": rule["version"], "title": title, "subtitle": subtitle,
            "ctdl_property": rule.get("ctdl_property"), "property_label": rule.get("property_label"),
            "locator": rule["definition"].get("locator"), **st, "comments": comments + questions,
            "page_questions": page_q}


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
    """course_key → page stems it was found on (course pages first), memoized per extraction."""
    snap = rv.snap
    key = ("w4-course-pages", snap.ctx.root.uri, snap.ctx.catalog, snap.ext)
    cache = studio(request).cache
    if key not in cache:
        by: dict[str, list[tuple]] = {}
        for o in snap.occurrences.values():
            if o["course_key"]:
                by.setdefault(o["course_key"], []).append((o["locator_rule_id"] != "locator-course-page",
                                                           o["page_stem"]))
        cache[key] = {ck: list(dict.fromkeys(st for _, st in sorted(v))) for ck, v in by.items()}
    return cache[key]


def _find_row(ordered: list, focus: str) -> int | None:
    """Index of the row a link asks for (`?row=`): its key, else an occurrence key, a course key or a page stem."""
    for field in ("key", "occurrence_key", "course_key", "page_stem"):
        for i, (r, _) in enumerate(ordered):
            if r.get(field) == focus:
                return i
    if "@" not in focus:  # a course key typed with a space, or lower case
        f = focus.replace(" ", "").upper()
        for i, (r, _) in enumerate(ordered):
            if (r.get("course_key") or "") == f:
                return i
    return None


@router.get("/catalogs/{catalog}/rules")
def rules(request: Request, catalog: str, ext: str | None = None) -> dict:
    rv = _review(request, catalog, ext)
    groups = []
    for kind, label in (("page", "Page rules"), ("locator", "Record locators"), ("field", "Field rules")):
        ids = [rid for rid, r in rv.snap.rules.items() if r["kind"] == kind]
        if kind == "field":  # property order, course pages first, then stubs
            ids.sort(key=lambda r: (rv.snap.rules[r]["definition"]["locator"] != "locator-course-page",
                                    rv.snap.rules[r]["definition"]["locator"],
                                    model.PROPERTY_ORDER.get(rv.snap.rules[r].get("property_label"), 99), r))
        else:
            ids.sort(key=lambda r: (r not in PAGE_RULE_TITLES and r not in LOCATOR_TITLES, r))
        items = [_rule_summary(rv, rid) for rid in ids]
        groups.append({"kind": kind, "label": label, "rules": items,
                       "approved": sum(1 for i in items if i["status"] == "approved")})
    return {"extraction": rv.snap.ext, "ruleset_version": rv.snap.ruleset_version, "groups": groups}


@router.get("/catalogs/{catalog}/rules/{rule_id}")
def rule(request: Request, catalog: str, rule_id: str, ext: str | None = None) -> dict:
    rv = _review(request, catalog, ext)
    if rule_id not in rv.snap.rules:
        raise not_found(f"{rule_id} is not in ruleset v{rv.snap.ruleset_version}")
    r = rv.snap.rules[rule_id]
    ctx = rv.snap.ctx
    return {**_rule_summary(rv, rule_id), "definition": r["definition"], "what": r.get("what", ""),
            "how": r.get("how", ""), "why": r.get("why", ""), "examples": r.get("examples", []),
            "depends_on": r.get("depends_on", []), "content_hash": r["content_hash"],
            "published_by": r.get("published_by"), "published_at": r.get("published_at"),
            "parent_version": r.get("parent_version"), "versions": ctx.rule_versions(rule_id),
            "fill": rv.snap.fill(rule_id), "signal_counts": dict(rv.snap.signal_counts.get(rule_id, {})),
            "settings": {"content_root": rv.snap.settings.get("content_root")}}


@router.get("/catalogs/{catalog}/rules/{rule_id}/rows")
def rows(request: Request, catalog: str, rule_id: str, ext: str | None = None, offset: int = 0,
         limit: int = 200, q: str | None = None, focus: str | None = None) -> dict:
    """One page of a rule's rows in review order. `focus` (a row key, occurrence key, course key or page stem)
    extends the page so it includes that row, and returns its index as `focus_index` (links from Compare)."""
    t0 = time.perf_counter()
    rv = _review(request, catalog, ext)
    if rule_id not in rv.snap.rules:
        raise not_found(f"{rule_id} is not in ruleset v{rv.snap.ruleset_version}")
    ordered = rv.ordered(rule_id)
    if q:
        ql = q.lower().replace(" ", "")
        ordered = [(r, s) for r, s in ordered if ql in (r.get("course_key") or "").lower()
                   or ql in (r.get("value") or "").lower().replace(" ", "") or ql in r["page_stem"]]
    focus_index = _find_row(ordered, focus) if focus else None
    if focus_index is not None and focus_index >= offset + limit:
        limit = focus_index - offset + 20
    page = ordered[offset:offset + limit]
    snap = rv.snap
    kind = snap.rules[rule_id]["kind"]
    page_q = _page_questions(rv, rule_id) if kind == "page" else {}
    course_pages = _course_pages(request, rv) if kind != "page" else {}
    out = []
    for r, s in page:
        p = snap.page[r["page_stem"]]
        others = [st for st in course_pages.get(r["course_key"], []) if st != r["page_stem"]][:6]
        out.append({"key": r["key"], "occurrence_key": r["occurrence_key"], "course_key": r["course_key"],
                    "page_stem": r["page_stem"], "url": p["url"], "page_title": p["title"], "value": r["value"],
                    "status": r["status"], "css_path": r["css_path"], "char_start": r["char_start"],
                    "char_end": r["char_end"], "occurrence_css_path": r["occurrence_css_path"],
                    "context": r["context"], "state": s.state, "verdict": _event_brief(s.verdict),
                    "reattached": s.reattached, "comments": [_event_brief(c) for c in s.comments],
                    "signal_count": len(r["signals"]) + len(s.history),
                    "page_questions": [_event_brief(e) for e in page_q.get(r["page_stem"], [])],
                    "other_pages": [{"page_stem": st, "url": snap.page[st]["url"], "title": snap.page[st]["title"]}
                                    for st in others]})
    missing = [_event_brief(e) | {"page_stem": e["target"].get("page_stem")} for e in rv.missing_events(rule_id)]
    return {"rule_id": rule_id, "extraction": snap.ext, "total": len(ordered), "offset": offset, "rows": out,
            "missing": missing, "focus_index": focus_index, "elapsed_ms": round(1000 * (time.perf_counter() - t0), 1)}


@router.get("/catalogs/{catalog}/pages/{stem}/overlay")
def overlay(request: Request, catalog: str, stem: str, rule: str, ext: str | None = None) -> dict:
    """What the page pane outlines and marks in a record locator's view (spec §7.2): every course block the rule
    found on this page, numbered, and the text that looks like a course code outside all of them."""
    rv = _review(request, catalog, ext)
    snap = rv.snap
    if rule not in snap.rules:
        raise not_found(rule)
    if snap.rules[rule]["kind"] == "page":  # a page rule's view outlines the courses its locators found
        locs = [rid for rid, r in snap.rules.items() if r["kind"] == "locator"
                and rule in (r["definition"].get("page_rules") or [])]
    else:
        locs = [rule]
    blocks = sorted((o for loc in locs for o in snap.occ_by_locator.get(loc, []) if o["page_stem"] == stem),
                    key=lambda o: (o["locator_rule_id"], o["locator_index"]))
    marks = [s for s in snap.page_signals.get(stem, []) if s["signal"] == "uncovered-code" and s["rule_id"] == rule]
    return {"blocks": [{"occurrence_key": o["occurrence_key"], "css_path": o["css_path"], "n": i + 1,
                        "course_key": o["course_key"]} for i, o in enumerate(blocks)],
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


# =====================================================================================================
# Courses (Records tab)
# =====================================================================================================
@router.get("/catalogs/{catalog}/courses")
def courses(request: Request, catalog: str, q: str | None = None, ext: str | None = None, limit: int = 50) -> list[dict]:
    rv = _review(request, catalog, ext)
    by = {}
    for o in rv.snap.occurrences.values():
        ck = o["course_key"]
        if ck is None:
            continue
        item = by.setdefault(ck, {"course_key": ck, "occurrences": 0, "line": None, "annotated": False})
        item["occurrences"] += 1
        if item["line"] is None or o["locator_rule_id"] == "locator-course-page":
            item["line"] = rv.snap.course_line(o["occurrence_key"])
    for e in rv.live:
        ck = e["target"].get("course_key")
        if ck in by and e["type"] in ("verdict", "comment") and not e["author"].startswith("golden-datasets"):
            by[ck]["annotated"] = True
    # courses someone has looked at first (a dot in the list, screen 07), then by code
    items = sorted(by.values(), key=lambda x: (not x["annotated"], x["course_key"]))
    if q:
        ql = q.lower().replace(" ", "")
        items = [i for i in items if ql in i["course_key"].lower() or ql in (i["line"] or "").lower().replace(" ", "")]
    return items[:limit]


@router.get("/catalogs/{catalog}/courses/{course_key}")
def course(request: Request, catalog: str, course_key: str, ext: str | None = None) -> dict:
    rv = _review(request, catalog, ext)
    snap = rv.snap
    occs = sorted((o for o in snap.occurrences.values() if o["course_key"] == course_key),
                  key=lambda o: (o["locator_rule_id"] != "locator-course-page", o["page_stem"], o["locator_index"]))
    if not occs:
        raise not_found(course_key)
    states_cache: dict = {}
    out = []
    for o in occs:
        fields = []
        for rid, m in sorted(snap.matches_by_occ[o["occurrence_key"]].items(),
                             key=lambda kv: model.PROPERTY_ORDER.get(snap.rules[kv[0]].get("property_label"), 99)):
            if rid not in states_cache:
                states_cache[rid] = rv.row_states(rid, snap.rows(rid))
            s = states_cache[rid].get(o["occurrence_key"])
            r = snap.rules[rid]
            fields.append({"rule_id": rid, "property_label": r.get("property_label"),
                           "ctdl_property": r.get("ctdl_property"), "value": m["value"], "status": m["status"],
                           "css_path": m["full_css_path"], "char_start": m["char_start"], "char_end": m["char_end"],
                           "state": s.state if s else None, "verdict": _event_brief(s.verdict) if s else None,
                           "comments": [_event_brief(c) for c in s.comments] if s else []})
        p = snap.page[o["page_stem"]]
        out.append({"occurrence_key": o["occurrence_key"], "page_stem": o["page_stem"], "url": p["url"],
                    "page_title": p["title"], "locator_rule_id": o["locator_rule_id"],
                    "css_path": o["css_path"], "fields": fields})
    return {"course_key": course_key, "extraction": snap.ext, "occurrences": out}


# =====================================================================================================
# Annotations
# =====================================================================================================
@router.post("/catalogs/{catalog}/annotations")
def add_annotation(request: Request, catalog: str, event: Annotated[dict, Body()]) -> dict:
    """Append one event (verdict · comment · approve · reopen). The server assigns the id and the time and fills
    the target from the current extraction; the client sends type, author, target {kind, rule_id, key…},
    verdict, expected, note, supersedes."""
    t0 = time.perf_counter()
    rv = _review(request, catalog, event.get("extraction"))
    snap = rv.snap
    t = dict(event.get("target") or {})
    rid = t.get("rule_id")
    if t.get("kind") != "page" or rid is not None:
        if rid not in snap.rules:
            raise HTTPException(400, f"unknown rule {rid}")
        t["rule_version_seen"] = snap.rules[rid]["version"]
    t["extraction_seen"] = snap.ext
    kind = t.get("kind")
    if kind in ("match", "occurrence") and t.get("occurrence_key"):
        o = snap.occurrences.get(t["occurrence_key"])
        if o is None:
            raise HTTPException(400, "unknown occurrence_key")
        t["course_key"], t["page_stem"] = o["course_key"], o["page_stem"]
        if kind == "match":
            m = snap.matches_by_occ[o["occurrence_key"]].get(rid)
            if m is None:
                raise HTTPException(400, f"{rid} has no row on this occurrence")
            t["value_index"], t["value_seen"] = m["value_index"], m["value"]
    for k in ("kind", "rule_id", "rule_version_seen", "extraction_seen", "occurrence_key", "course_key",
              "page_stem", "value_index", "value_seen"):
        t.setdefault(k, None)
    ctx = snap.ctx
    full = {"annotation_id": new_id("ap" if event.get("type") in ("approve", "reopen") else "an"),
            "type": event.get("type"), "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "author": (event.get("author") or "").strip(), "catalog": ctx.catalog, "crawl": ctx.crawl, "target": t,
            "verdict": event.get("verdict"), "expected": event.get("expected"), "note": event.get("note") or None,
            "supersedes": event.get("supersedes")}
    if full["type"] == "approve":
        st = rv.rule_status(rid)
        if st["open_wrong"] or st["open_missing"]:
            raise HTTPException(409, "a course is marked wrong or missing for this rule; it can't be approved")
    try:
        validate(full)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    log = LOADER.log(ctx)
    log.append(full)
    log.refresh()
    rv2 = _review(request, catalog, snap.ext)
    return {"event": full, "rule": _rule_summary(rv2, rid) if rid else None,
            "elapsed_ms": round(1000 * (time.perf_counter() - t0), 1)}


@router.get("/catalogs/{catalog}/annotations")
def list_annotations(request: Request, catalog: str, rule: str | None = None) -> list[dict]:
    rv = _review(request, catalog)
    return [e for e in rv.live if rule is None or e["target"].get("rule_id") == rule]
