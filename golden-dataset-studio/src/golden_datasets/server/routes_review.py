"""Review API (W4): catalogs, rules, rows, page overlays, courses (Records tab) and annotations.

Every list is computed from one in-memory `Snapshot` of an extraction plus the annotation log (read
incrementally), so a request costs milliseconds once the extraction is loaded (spec §10).
"""

from __future__ import annotations

import time
from collections import Counter
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Query, Request

from .. import facets, golden, layout, model, profiles_rule, properties
from ..catalogs import CATALOGS, info
from ..errors import UserError
from ..log import FULL_NAMES, new_id, validate
from ..profiles import role_of, roles
from ..review import LOADER, Review, annotated_match, human_reviewed_counts, norm, reset_clears
from .state import not_found, studio

router = APIRouter(prefix="/api")

PAGE_RULE_TITLES = {"course-page": "Course pages", "program-page": "Program pages",
                    "program-page-with-courses": "Program pages that list courses"}
PLAIN_SUBTITLES = {"course-page": "Which pages are a single course's own page",
                   "program-page": "Which pages describe a degree or certificate",
                   "program-page-with-courses": "Which program pages name courses in their requirements"}
#: Record locators listed first, in this order (their titles come from their definitions: `locator_title`).
KNOWN_LOCATORS = ("locator-course-page", "locator-program-requirement")


PROPERTY_ROW = {r["label"]: r for r in properties.active()}


def locator_title(d: dict) -> tuple[str, str]:
    """A record locator's (title, subtitle), from what its definition does (sme-fixes §3): with `repeat`, many courses
    share a page (CCSF's department pages); without, the page is one course (AVC)."""
    if d.get("repeat"):
        return f"Course blocks: every {d['repeat']} on the page", "Several courses on one page, one block each"
    return "Whole page is one course", "Each page's content area is one course"


def rule_title(rule: dict, rules: dict[str, dict] | None = None) -> tuple[str, str]:
    """(title, subtitle) as the rule list shows them (screen 03). `rules` (the ruleset's): a page rule whose pages a
    repeating record locator reads is "Pages with courses", not a single course's own page."""
    if rule["kind"] == "page":
        repeats = any(r["kind"] == "locator" and r["definition"].get("repeat")
                      and rule["rule_id"] in (r["definition"].get("page_rules") or []) for r in (rules or {}).values())
        return (PAGE_RULE_TITLES.get(rule["rule_id"], rule["rule_id"]),
                "Pages with courses" if repeats else PLAIN_SUBTITLES.get(rule["rule_id"]) or rule.get("what") or "")
    if rule["kind"] == "locator":
        return locator_title(rule["definition"])
    label = rule.get("property_label") or rule["rule_id"]
    if rule["definition"].get("locator") not in (None, "locator-course-page"):
        label += " · program pages" if rule["definition"]["locator"] == "locator-program-requirement" \
            else f" · {rule['definition']['locator'].removeprefix('locator-')}"
    path = rule.get("ctdl_property") or ""
    if ">" in path:  # a child: no path in the sidebar, the parent's name instead (#8)
        return label, f"part of {parent_name(path)}"
    return label, path or "no CTDL term"


def parent_name(path: str) -> str:
    parent = path.split(">", 1)[0]
    return next((r["label"] for r in properties.active() if r["path"] == parent), properties.label_of(parent))


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
            "author_role": e.get("author_role"), "at": e["at"], "note": e.get("note"), "expected": e.get("expected"),
            "compared_with": e.get("compared_with"), "anchor": e.get("anchor"),
            **({"reasons": e["reasons"]} if e.get("reasons") else {}),
            "rule_version_seen": e["target"].get("rule_version_seen"), "value_seen": e["target"].get("value_seen")}


def _review_state(s) -> dict:
    """Whether an expert confirmed the value (human-reviewed: `human` is their verdict), or only an engineer did
    (waiting for an expert); `checked` is the latest engineer's ✓ (the check an expert confirmed, or waits on)."""
    if s is None:
        return {"human_reviewed": False, "engineer_checked": False, "role": None, "human": None, "checked": None,
                "before_reset": None}
    def who(e: dict | None) -> dict | None:  # first-name authors of the first profiles by their full name
        return e and {**_event_brief(e), "author": FULL_NAMES.get(e["author"], e["author"])}
    return {"human_reviewed": s.human is not None, "engineer_checked": s.engineer_checked, "role": s.role,
            "human": who(s.human), "checked": who(s.checked), "before_reset": who(s.before_reset)}


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
        elif e["type"] == "reset" and t.get("kind") == "rule":  # ends the approval of every version
            last = {k: v for k, v in last.items() if k[0] != t.get("rule_id")}
    return sum(1 for r in ruleset["rules"] if last.get((r["rule_id"], r["version"])) == "approve")


@router.get("/catalogs")
def catalogs(request: Request) -> list[dict]:
    st = studio(request)
    doc = st.ctx(next(iter(CATALOGS))).manifest()
    entries = {c["catalog"]: c for c in doc["catalogs"]}
    out = []
    shown = lambda f: (info(f)["name"] if f in CATALOGS else (entries[f].get("name") or f)).lower()  # noqa: E731
    for folder in sorted(set(CATALOGS) | set(entries), key=shown):
        meta, e = info(folder), entries.get(folder)
        if folder not in CATALOGS and e:  # added from the picker: named from its crawl (crawls.display_name)
            meta = {**meta, "name": e.get("name") or folder, "institution": e.get("name") or folder}
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
    # catalogs being added from the picker (spec §7.1): a card with their progress until they're in the manifest
    for job in list(st.adding.values()):
        if job["step"] == "done" and job["catalog"] in entries:
            st.adding.pop(job["catalog"], None)
        elif job["catalog"] not in entries or job["step"] == "failed":
            out = [c for c in out if c["catalog"] != job["catalog"]]
            out.append({"catalog": job["catalog"], "short": job["catalog"], "name": job["name"],
                        "institution": job["name"], "platform": "", "logo": None, "pages": job["pages"],
                        "crawl": job["crawl"], "ruleset_version": None, "rules_total": 0, "rules_approved": 0,
                        "status": "failed" if job["step"] == "failed" else "adding",
                        "adding": {k: job[k] for k in ("step", "done", "total", "error")}})
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
    title, subtitle = rule_title(rule, rv.snap.rules)
    st = rv.rule_status(rid)
    comments = sum(1 for e in rv.live if e["type"] in ("comment",) and e["target"].get("rule_id") == rid
                   and e["target"]["kind"] != "rule")
    rule_comments = sum(1 for e in rv.live if e["type"] == "comment" and e["target"]["kind"] == "rule"
                        and e["target"].get("rule_id") == rid)
    questions = sum(1 for e in rv.live if e["type"] == "verdict" and e.get("verdict") == "question"
                    and e["target"].get("rule_id") == rid)
    page_q = sum(map(len, _page_questions(rv, rid).values())) if rule["kind"] == "page" else 0
    row = PROPERTY_ROW.get(rule.get("property_label")) if rule["kind"] == "property" else None
    extra = {}
    if rule["kind"] == "property":
        path = rule.get("ctdl_property") or ""
        extra = {"required": bool(row and row["required"]), "course_key": bool(row and row["course_key"]),
                 "no_rule": rule["definition"].get("rule_type") == "none", "list": bool(
                     rule["definition"].get("multiple")), "path_shown": properties.shown(path) or None,
                 "parent_label": parent_name(path) if ">" in path else None,
                 "input": input_words(rule, rv.snap.rules)}
    return {"rule_id": rid, "kind": rule["kind"], "version": rule["version"], "title": title, "subtitle": subtitle,
            "ctdl_property": rule.get("ctdl_property"), "property_label": rule.get("property_label"),
            "locator": rule["definition"].get("locator"), **st, "comments": comments + questions,
            "page_questions": page_q, "rule_comments": rule_comments, **extra}


def input_words(rule: dict, rules: dict[str, dict]) -> str:
    """What a property rule reads, in words, for the rule header (§4.2): "the course record", "the whole page"…"""
    from ..engine import input_of

    d = rule["definition"]
    inp = input_of(d)
    if d.get("rule_type") == "none":
        return "nothing yet: no rule"
    if d.get("rule_type") in model.DERIVED_RULE_TYPES:
        return "nothing on the page (a constant)" if d["rule_type"] == "constant" else "the page URL"
    if inp["from"] == "page":
        return "the whole page"
    if inp["from"] == "url":
        return "the page URL"
    if inp["from"] == "rule":
        parent = rules.get(inp.get("rule") or "", {})
        name = parent.get("property_label") or inp.get("rule")
        return f"{name}'s {'element' if inp.get('use') == 'element' else 'value'}"
    return "the course record"


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


def _find_row(ordered: list, focus: str) -> int | None:
    """Index of the row a link asks for (`?row=`): its key, else an occurrence key, a course key or a page stem."""
    for name in ("key", "occurrence_key", "course_key", "page_stem"):
        for i, (r, _) in enumerate(ordered):
            if r.get(name) == focus:
                return i
    if "@" not in focus:  # a course key typed with a space, or lower case
        f = focus.replace(" ", "").upper()
        for i, (r, _) in enumerate(ordered):
            if (r.get("course_key") or "") == f:
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


#: The rule list's groups after Page rules and Record locators (property-rules spec §4.8): `collapsed` ones start shut.
PROPERTY_GROUPS = (("required", "Required", False), ("other", "Other properties", False),
                   ("not-started", "Not started", True), ("program", "Program page lines", True))


def property_group(rule: dict) -> str:
    if rule["definition"].get("locator") not in (None, properties.COURSE_LOCATOR):
        return "program"
    row = PROPERTY_ROW.get(rule.get("property_label"))
    if row is not None and row["required"]:
        return "required"
    return "not-started" if rule["definition"].get("rule_type") == "none" else "other"


@router.get("/catalogs/{catalog}/rules")
def rules(request: Request, catalog: str, ext: str | None = None) -> dict:
    """The rule list. Properties: Required (in a fixed order, the course key first), then Other properties by how
    many values experts reviewed across every catalog, then sheet order; Not started (no rule yet) in sheet order;
    Program page lines. Sorted when the list loads (a verdict doesn't re-sort the list someone is looking at)."""
    rv = _review(request, catalog, ext)
    snap = rv.snap
    groups = []
    for kind, label in (("page", "Page rules"), ("locator", "Record locators")):
        ids = sorted((rid for rid, r in snap.rules.items() if r["kind"] == kind),
                     key=lambda r: (r not in PAGE_RULE_TITLES and r not in KNOWN_LOCATORS, r))
        items = [_rule_summary(rv, rid) for rid in ids]
        groups.append({"id": kind, "kind": kind, "label": label, "rules": items, "collapsed": False,
                       "approved": sum(1 for i in items if i["status"] == "approved")})
    doc = snap.ctx.manifest()
    counts = human_reviewed_counts(snap.ctx.root, [c["catalog"] for c in doc["catalogs"] if c.get("rulesets")],
                                   studio(request).ctx)
    by_group: dict[str, list[str]] = {g: [] for g, _, _ in PROPERTY_GROUPS}
    for rid, r in snap.rules.items():
        if r["kind"] == "property":
            by_group[property_group(r)].append(rid)

    def order(rid: str) -> tuple:
        r = snap.rules[rid]
        row = PROPERTY_ROW.get(r.get("property_label"))
        sheet = row["sheet_row"] if row else 999
        return (model.PROPERTY_ORDER.get(r.get("property_label"), 99), sheet, rid)

    by_group["required"].sort(key=order)
    by_group["other"].sort(key=lambda rid: (-counts.get(rid, 0), *order(rid)[1:]))
    by_group["not-started"].sort(key=lambda rid: order(rid)[1:])
    by_group["program"].sort(key=lambda rid: (snap.rules[rid]["definition"]["locator"], *order(rid)))
    for gid, label, collapsed in PROPERTY_GROUPS:
        if not by_group[gid]:
            continue
        items = [_rule_summary(rv, rid) for rid in by_group[gid]]
        groups.append({"id": gid, "kind": "property", "label": label, "rules": items, "collapsed": collapsed,
                       "approved": sum(1 for i in items if i["status"] == "approved")})
    return {"extraction": snap.ext, "ruleset_version": snap.ruleset_version, "groups": groups}


@router.get("/catalogs/{catalog}/rules/{rule_id}")
def rule(request: Request, catalog: str, rule_id: str, ext: str | None = None) -> dict:
    rv = _review(request, catalog, ext)
    if rule_id not in rv.snap.rules:
        raise not_found(f"{rule_id} is not in ruleset v{rv.snap.ruleset_version}")
    r = rv.snap.rules[rule_id]
    ctx = rv.snap.ctx
    loc = rv.snap.rules.get(r["definition"].get("locator") or "")  # where a property rule looks, titled like the locator
    return {**_rule_summary(rv, rule_id), "definition": r["definition"], "what": r.get("what", ""),
            "locator_title": locator_title(loc["definition"])[0] if loc else None,
            "how": r.get("how", ""), "why": r.get("why", ""), "examples": r.get("examples", []),
            "depends_on": r.get("depends_on", []), "content_hash": r["content_hash"],
            "published_by": r.get("published_by"), "published_at": r.get("published_at"),
            "parent_version": r.get("parent_version"), "versions": ctx.rule_versions(rule_id),
            "fill": rv.snap.fill(rule_id), "signal_counts": dict(rv.snap.signal_counts.get(rule_id, {})),
            "settings": {"content_root": rv.snap.settings.get("content_root")}}


@router.get("/catalogs/{catalog}/rules/{rule_id}/rows")
def rows(request: Request, catalog: str, rule_id: str, ext: str | None = None, offset: int = 0,
         limit: int = 200, q: str | None = None, focus: str | None = None,
         f: Annotated[list[str] | None, Query()] = None, order: str = "review",
         cross: Annotated[list[str] | None, Query()] = None, seed: int = 0, prior: bool = False,
         by: str | None = None, verdict: str | None = None) -> dict:
    """One page of a rule's rows in review order. `focus` (a row key, occurrence key, course key or page stem)
    extends the page so it includes that row, and returns its index as `focus_index` (links from Compare).
    The Sample drawer (facets.py): `f` filters by strata (`f=length:0–99 chars`, repeatable); `order` is `review`
    (the default above), `auto` (Autostratify: one combination of the `cross` strata after another, rarest first;
    `cross` omitted = the ones that split the rows most evenly) or `shuffle`, both seeded by `seed`. The first page
    also returns `sample`: the strata histograms, the crossed strata and their combinations. Rows carry `tags`:
    their bucket in each crossed or filtered stratum. `prior`: rows not reviewed yet whose record was reviewed in
    another rule come first (tagged "Reviewed in"); `sample.elsewhere` counts them either way. The "Annotated by"
filter (Evals spec §6.7): `by` = a person (the rows they marked or commented on, in any ruleset version, tagged with
the versions: "Annotated in"), `nobody` or `waiting` (engineer-checked); `verdict` = correct · wrong · note."""
    t0 = time.perf_counter()
    rv = _review(request, catalog, ext)
    if rule_id not in rv.snap.rules:
        raise not_found(f"{rule_id} is not in ruleset v{rv.snap.ruleset_version}")
    ordered = rv.ordered(rule_id)
    if q:
        ql = q.lower().replace(" ", "")
        ordered = [(r, s) for r, s in ordered if ql in (r.get("course_key") or "").lower()
                   or ql in (r.get("value") or "").lower().replace(" ", "") or ql in r["page_stem"]]
    if by or verdict:
        ann = rv.annotations(rule_id)
        ordered = [(r, s) for r, s in ordered if annotated_match(ann[r["key"]], by, verdict)]
    filters = facets.parse_filters(f)
    if order not in facets.ORDERS:
        raise HTTPException(status_code=422, detail=f"order must be one of {', '.join(facets.ORDERS)}")
    dims = rv.facet_dims(rule_id)
    by_key = {r["key"]: (r, s) for r, s in ordered}
    keys, sample = facets.sample_order(dims, list(by_key), filters, order,
                                       None if cross is None else [c for c in cross if c], seed)
    if by not in (None, "", "nobody", "waiting", "experts", "engineers") and "annotated_in" not in sample["tag_dims"]:  # whose rows: say which ruleset too
        sample["tag_dims"].append("annotated_in")
    elsewhere = rv.reviewed_elsewhere(rule_id, rv.snap.rows(rule_id), rv.row_states(rule_id, rv.snap.rows(rule_id)))
    sample["elsewhere"] = sum(1 for k in keys if k in elsewhere)
    sample["prior"] = prior
    if prior:
        keys = [k for k in keys if k in elsewhere] + [k for k in keys if k not in elsewhere]
    ordered = [by_key[k] for k in keys]
    per_page = repeats(rv, rule_id)
    if per_page:  # one row per page (sme-fixes §3): a page's courses together, in page order, pages in sample order
        ordered = by_page(ordered)

    def rule_name(rid: str) -> str:
        r = rv.snap.rules.get(rid)
        return (r and (r.get("property_label") or rule_title(r)[0])) or rid
    focus_index = _find_row(ordered, focus) if focus else None
    if focus_index is not None and focus_index >= offset + limit:
        limit = focus_index - offset + 20
    page = ordered[offset:offset + limit]
    snap = rv.snap
    spread_by, group, group_order = rv.spread_groups(rule_id)
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
                    "context": r["context"], "state": s.state, "verdict": _event_brief(s.verdict), **_review_state(s),
                    "reattached": s.reattached, "comments": [_event_brief(c) for c in s.comments],
                    "signal_count": len(r["signals"]) + len(s.history),
                    "group": group.get(r["key"]) if order == "review" and not filters else None,
                    "tags": facets.tags(dims, r["key"], sample["tag_dims"])
                    + ([{"dim": "elsewhere", "label": "Reviewed in",
                         "bucket": ", ".join(rule_name(x) for x in elsewhere[r["key"]])}]
                       if prior and r["key"] in elsewhere else []),
                    "page_questions": [_event_brief(e) for e in page_q.get(r["page_stem"], [])],
                    "other_pages": [{"page_stem": st, "url": snap.page[st]["url"], "title": snap.page[st]["title"]}
                                    for st in others], **_items(r, s),
                    **({"page_courses": per_page[r["page_stem"]]} if per_page else {})})
    missing = [_event_brief(e) | {"page_stem": e["target"].get("page_stem")} for e in rv.missing_events(rule_id)]
    sizes = Counter(group.values())
    spread = {"by": spread_by, "groups": [{"label": g, "rows": sizes[g]} for g in group_order if sizes[g]]}
    return {"rule_id": rule_id, "extraction": snap.ext, "total": len(ordered), "offset": offset, "rows": out,
            "spread": spread, "sample": sample if offset == 0 else None,
            "missing": missing, "focus_index": focus_index, "elapsed_ms": round(1000 * (time.perf_counter() - t0), 1)}


@router.get("/catalogs/{catalog}/match")
def match(request: Request, catalog: str, rule: str, occ: str, ext: str | None = None) -> dict:
    """One property rule's row on one occurrence, as `/rows` has it (its value, verdict, comments, review marks): what
    Evals and Compare show beside a diff, and what a note or a verdict there supersedes."""
    rv = _review(request, catalog, ext)
    snap = rv.snap
    if rule not in snap.rules:
        raise not_found(f"{rule} is not in ruleset v{snap.ruleset_version}")
    rows = snap.rows(rule)
    row = next((r for r in rows if r["occurrence_key"] == occ), None)
    if row is None:
        raise not_found(f"{rule} has no row on {occ} in {snap.ext}")
    s = rv.row_states(rule, rows).get(row["key"])  # every row: annotations re-attach across them
    r = snap.rules[rule]
    return {"rule_id": rule, "kind": r["kind"], "ctdl_property": r.get("ctdl_property"),
            "property_label": r.get("property_label"), "extraction": snap.ext, "key": row["key"],
            "occurrence_key": occ, "course_key": row["course_key"], "page_stem": row["page_stem"],
            "value": row["value"], "status": row["status"], "css_path": row["css_path"],
            "char_start": row["char_start"], "char_end": row["char_end"],
            "state": s.state if s else None, "verdict": _event_brief(s.verdict) if s else None, **_review_state(s),
            "comments": [_event_brief(c) for c in s.comments] if s else []}


@router.get("/catalogs/{catalog}/annotators")
def annotators(request: Request, catalog: str, ext: str | None = None, by: str | None = None,
               verdict: str | None = None) -> dict:
    """The "Annotated by" dropdown of the Rules and Records tabs (Evals spec §6.7, §6.8): `people` [{name, role,
    values}] (property values each annotated), `waiting` (values an engineer checked, waiting for an expert), `experts` /
    `engineers` (values any subject matter expert / any engineer annotated) and, with
    `by` or `verdict`, `rules` {rule_id: rows that pass the filter} for the rule list."""
    rv = _review(request, catalog, ext)
    out = rv.people()
    out["rules"] = ({rid: sum(1 for a in rv.annotations(rid).values() if annotated_match(a, by, verdict))
                     for rid in rv.snap.rules} if by or verdict else None)
    return out


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
def courses(request: Request, catalog: str, q: str | None = None, ext: str | None = None, limit: int = 50,
            who: Annotated[str | None, Query(alias="by")] = None, verdict: str | None = None) -> list[dict]:
    """Courses by code, the annotated first; `by` / `verdict` (the "Annotated by" filter, as on /rows): only the
    courses with a property value that passes it (`by=nobody`: no property value annotated)."""
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
    if who or verdict:
        snap, keep, touched = rv.snap, set(), set()
        for rid, r in snap.rules.items():
            if r["kind"] != "property":
                continue
            for k, a in rv.annotations(rid).items():
                ck = snap.occurrences[k]["course_key"]
                if a["people"]:
                    touched.add(ck)
                if annotated_match(a, who, verdict):
                    keep.add(ck)
        items = [i for i in items if (i["course_key"] not in touched if who == "nobody" else i["course_key"] in keep)]
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
    annotations: dict = {}
    out = []
    for o in occs:
        props = []
        ms = snap.matches_by_occ[o["occurrence_key"]]
        rids = [rid for rid, r in snap.rules.items() if r["kind"] == "property"
                and r["definition"].get("locator") == o["locator_rule_id"]]  # every property, with a rule or not (R1)
        for rid in sorted(rids, key=lambda x: (model.PROPERTY_ORDER.get(snap.rules[x].get("property_label"), 99), x)):
            if rid not in states_cache:
                states_cache[rid] = rv.row_states(rid, snap.rows(rid))
                annotations[rid] = rv.annotations(rid)
            s = states_cache[rid].get(o["occurrence_key"])
            r = snap.rules[rid]
            m = ms.get(rid) or {"value": None, "status": "none", "full_css_path": None, "char_start": None,
                                "char_end": None}
            items = snap.items_by_occ[o["occurrence_key"]].get(rid) or []
            found = [x for x in items if x["status"] == "found"]
            is_list = bool(r["definition"].get("multiple"))
            ann = annotations[rid].get(o["occurrence_key"]) or {"people": {}}
            props.append({"rule_id": rid, "property_label": r.get("property_label"),
                          "ctdl_property": r.get("ctdl_property"),
                          "value": profiles_rule.row_value(found) if is_list and found else m["value"],
                          "status": m["status"],
                          "css_path": m["full_css_path"], "char_start": m["char_start"], "char_end": m["char_end"],
                          **({"items": [{"value_index": x["value_index"], "value": x["value"],
                                         "css_path": x["full_css_path"], "char_start": x["char_start"],
                                         "char_end": x["char_end"], **profiles_rule.row_item(x, o["css_path"])}
                                        for x in found]} if is_list else {}),
                          "state": s.state if s else None, "verdict": _event_brief(s.verdict) if s else None,
                          **_review_state(s), "annotators": ann["people"],
                          "comments": [_event_brief(c) for c in s.comments] if s else []})
        p = snap.page[o["page_stem"]]
        out.append({"occurrence_key": o["occurrence_key"], "page_stem": o["page_stem"], "url": p["url"],
                    "page_title": p["title"], "locator_rule_id": o["locator_rule_id"],
                    "css_path": o["css_path"], "properties": props})
    return {"course_key": course_key, "extraction": snap.ext, "occurrences": out}


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
    t0 = time.perf_counter()
    rv = _review(request, catalog, event.get("extraction"))
    snap = rv.snap
    t = dict(event.get("target") or {})
    rid = t.get("rule_id")
    if t.get("kind") == "ruleset":  # a comment on the whole ruleset: no rule
        t["rule_id"] = rid = None
        t["ruleset_version_seen"] = snap.ruleset_version
    elif t.get("kind") != "page" or rid is not None:
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
            r = snap.rules[rid]
            items = snap.items_by_occ[o["occurrence_key"]].get(rid) or []
            if r["definition"].get("rule_type") == "none":  # no rule yet: anyone can still say what the page shows
                if r["definition"].get("locator") != o["locator_rule_id"]:
                    raise HTTPException(400, f"{rid} has no row on this occurrence")
                t["value_index"], t["value_seen"] = None, None
            elif t.get("item"):  # one item of a list (property-rules spec §4.4)
                if event.get("verdict") == "missing":
                    t["value_index"], t["value_seen"] = None, None
                elif t.get("value_index") is None and event.get("supersedes"):
                    # ✕ on an object a reviewer added: it takes the add back (phase1-followups spec §3.4)
                    added = rv.by_id.get(event["supersedes"])
                    if added is None or added.get("verdict") != "missing":
                        raise HTTPException(400, "only an added item can be taken back")
                    t["value_index"], t["value_seen"] = None, (added.get("expected") or {}).get("text")
                else:
                    m = next((x for x in items if x["value_index"] == t.get("value_index")
                              and x["status"] == "found"), None)
                    if m is None:
                        raise HTTPException(400, f"{rid} has no item {t.get('value_index')} on this occurrence")
                    t["value_index"], t["value_seen"] = m["value_index"], m["value"]
            elif not items:
                raise HTTPException(400, f"{rid} has no row on this occurrence")
            else:
                found = [x["value"] for x in items if x["status"] == "found"]
                t["value_index"] = 0
                t["value_seen"] = "\n".join(found) if r["definition"].get("multiple") and found else items[0]["value"]
    for k in ("kind", "rule_id", "rule_version_seen", "extraction_seen", "occurrence_key", "course_key",
              "page_stem", "value_index", "value_seen"):
        t.setdefault(k, None)
    if not t.get("item"):
        t.pop("item", None)
    ctx = snap.ctx
    full = {"annotation_id": new_id("ap" if event.get("type") in ("approve", "reopen", "reset") else "an"),
            "type": event.get("type"), "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "author": (event.get("author") or "").strip(), "catalog": ctx.catalog, "crawl": ctx.crawl, "target": t,
            "verdict": event.get("verdict"), "expected": profiles_rule.with_object_text(event.get("expected")),
            "note": event.get("note") or None,
            "supersedes": event.get("supersedes")}
    if event.get("topic"):
        full["topic"] = event["topic"]
    if event.get("anchor") is not None:  # a comment on a piece of text on the page (sme-fixes §1)
        full["anchor"] = event["anchor"]
    role = event.get("author_role") or role_of(full, roles(ctx.root))
    if role:
        full["author_role"] = role
    if event.get("compared_with") is not None:
        full["compared_with"] = event["compared_with"]
    if event.get("reasons"):  # "Why wrong?" flags on a ✕ (sme-fixes §6)
        full["reasons"] = event["reasons"]
    if full["type"] == "reset":  # what the confirm dialog showed, for the record (nothing reads it back)
        full["counts"] = _reset_counts(rv, rid)["counts"]
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
    published = None
    if full["type"] == "verdict" and kind == "match":
        try:  # the verdict is saved either way; say if its page's golden file couldn't be rewritten
            published = golden.publish_page(ctx, t["page_stem"], f"{full['author']} marked {rid} {full['verdict']}",
                                            f"{full['author']} via the Studio UI", create=role == "sme")
        except (OSError, UserError) as exc:
            published = {"error": str(exc)}
    score = None
    if full["type"] == "approve":  # approving a column's rule publishes it, then scores it (Evals spec §4.1, §6.6)
        what = golden.approval_publishes(rv2, rid)
        if what and not what["writes"]:
            published = {"written": False, "column": None, "property": what["property"]}
        elif what:
            try:
                doc = golden.publish_approved(ctx, rid, f"{full['author']} via the Studio UI")
                published = {"written": True, "publication": doc["publication"], "created": doc["created"],
                             "column": what["column"], "columns": golden.columns_of(doc["properties"]),
                             "files": doc["pages"]}
                job = request.app.state.scores.after_publish(ctx, full["author"])
                score = {k: job[k] for k in ("id", "status")} | {"golden": job["golden"]["id"]} if job else None
            except (OSError, UserError) as exc:
                published = {"error": str(exc)}
    if full["type"] == "reset":  # the column leaves the silver dataset, the cleared values the golden one (§4.5)
        try:
            doc = golden.publish_reset(ctx, rid, f"{full['author']} via the Studio UI", full["note"])
            if doc:
                published = {"written": True, "publication": doc["publication"],
                             "columns": golden.columns_of(doc["properties"]), "files": doc["pages"]}
                job = request.app.state.scores.after_publish(ctx, full["author"])
                score = {k: job[k] for k in ("id", "status")} | {"golden": job["golden"]["id"]} if job else None
        except (OSError, UserError) as exc:
            published = {"error": str(exc)}
    return {"event": full, "rule": _rule_summary(rv2, rid) if rid else None, "published": published,
            "score": score, "elapsed_ms": round(1000 * (time.perf_counter() - t0), 1)}


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


@router.get("/catalogs/{catalog}/rules/{rule_id}/reset-preview")
def reset_preview(request: Request, catalog: str, rule_id: str) -> dict:
    """The Reset rule dialog's numbers: what a reset clears (✓, ✕ with an answer, by author), the approval it ends,
    what it keeps, and whether the property's column leaves the silver dataset."""
    rv = _review(request, catalog)
    if rule_id not in rv.snap.rules:
        raise not_found(f"unknown rule {rule_id}")
    st = rv.rule_status(rule_id)
    prop = rv.snap.rules[rule_id].get("property_label")
    ctx, column = rv.snap.ctx, None
    vs = golden.versions(ctx)
    if vs:
        n = max(vs)
        try:
            props = ctx.read_json(f"{vs[n]['path']}/publication.json", immutable=False).get("properties") or []
        except FileNotFoundError:
            props = []
        if prop in props:
            column = {"column": golden.column_name(prop), "golden": golden.version_name(n)}
    out = _reset_counts(rv, rule_id)
    return {"rule_id": rule_id, "property": prop, **out,
            "approval": {"by": FULL_NAMES.get(st["approved_by"], st["approved_by"]), "at": st["approved_at"]}
            if st["status"] == "approved" else None,
            "column": column}


@router.get("/catalogs/{catalog}/discussion")
def discussion(request: Request, catalog: str) -> dict:
    """Comments on a whole rule or on the ruleset (the Rules tab sidebar): {ruleset: [...], rules: {rule_id: [...]}}.
    Each: annotation_id, author, at, note, topic (new-rule · approach · question-rule · other), rule_version_seen."""
    rv = _review(request, catalog)

    def brief(e: dict) -> dict:
        t = e["target"]
        return {"annotation_id": e["annotation_id"], "author": e["author"], "at": e["at"], "note": e.get("note"),
                "topic": e.get("topic"), "rule_id": t.get("rule_id"), "rule_version_seen": t.get("rule_version_seen"),
                "ruleset_version_seen": t.get("ruleset_version_seen")}

    d = rv.discussion()
    return {"ruleset": [brief(e) for e in d["ruleset"]],
            "rules": {rid: [brief(e) for e in es] for rid, es in d["rules"].items()}}


@router.get("/catalogs/{catalog}/annotations")
def list_annotations(request: Request, catalog: str, rule: str | None = None) -> list[dict]:
    rv = _review(request, catalog)
    return [e for e in rv.live if rule is None or e["target"].get("rule_id") == rule]
