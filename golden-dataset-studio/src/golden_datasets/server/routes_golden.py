"""Golden API (W7): the approval gate, what a publication would write, golden_id collisions, and publishing."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request

from .. import golden
from ..errors import UserError
from ..review import LOADER
from .routes_review import rule_title
from .state import not_found, studio

router = APIRouter(prefix="/api")


@router.get("/catalogs/{catalog}/golden")
def golden_status(request: Request, catalog: str) -> dict:
    st = studio(request)
    ctx = st.ctx(catalog)
    ext = ctx.latest_extraction()
    if not ext:
        raise not_found(f"{catalog}: nothing extracted yet")
    rv = LOADER.review(ctx, ext)
    ok, statuses = golden.approval(rv)
    key = ("golden-plan", ctx.catalog, ext, LOADER.log(ctx).offset)
    if key not in st.cache:
        p = golden.plan(rv)
        st.cache[key] = {k: p[k] for k in ("collisions", "courses", "records", "skipped_no_course_key")} | {
            "pages": len(p["pages"]), "fields": len(p["lineage"])}
    p = st.cache[key]
    rules = []
    for s in statuses:
        title, subtitle = rule_title(rv.snap.rules[s["rule_id"]])
        rules.append({"rule_id": s["rule_id"], "title": title, "subtitle": subtitle, "kind": s["kind"],
                      "version": s["version"], "status": s["status"], "approved_by": s["approved_by"]})
    pubs = []
    for g in ctx.crawl_entry().get("golden", []):
        try:
            doc = ctx.read_json(f"{g['path']}/publication.json")
        except FileNotFoundError:
            continue
        pubs.append({k: doc.get(k) for k in ("publication", "extraction", "ruleset_version", "published_at",
                                              "published_by", "pages", "courses", "records", "lineage_rows", "to")}
                    | {"all_rules_approved": doc.get("approval_gate", {}).get("all_rules_approved")})
    target = golden.default_target(ctx)
    return {"ready": ok, "extraction": ext, "ruleset_version": rv.snap.ruleset_version, "rules": rules,
            "target": f"{target.rstrip('/')}/{ctx.catalog}/{ctx.crawl}/", **p,
            "publications": sorted(pubs, key=lambda x: x["published_at"] or "", reverse=True)}


@router.post("/catalogs/{catalog}/golden/publish")
def golden_publish(request: Request, catalog: str, body: Annotated[dict, Body()]) -> dict:
    ctx = studio(request).ctx(catalog)
    author = (body.get("author") or "").strip()
    if not author:
        raise HTTPException(400, "author is required")
    try:
        doc = golden.publish(ctx, golden.default_target(ctx), f"{author} via the Studio UI", log=lambda *a: None)
    except UserError as exc:
        raise HTTPException(409, str(exc)) from None
    return {"publication": doc["publication"], "path": f"{doc['to']}/{doc['to_prefix']}", "files": doc["pages"]}
