"""Golden API (W7): the approval gate, what a publication would write (with a preview of each file), golden_id
collisions, and publishing."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Query, Request

from .. import golden, model
from ..errors import UserError
from ..review import LOADER
from .routes_review import rule_title
from .state import not_found, studio

router = APIRouter(prefix="/api")
HTML_PREVIEW_BYTES = 400_000


def _review(request: Request, catalog: str):
    st = studio(request)
    ctx = st.ctx(catalog)
    ext = ctx.latest_extraction()
    if not ext:
        raise not_found(f"{catalog}: nothing extracted yet")
    return st, ctx, LOADER.review(ctx, ext)


def _plan(st, ctx, rv) -> dict:
    """golden.plan for the latest extraction, kept until the annotation log moves."""
    key = ("golden-plan", ctx.catalog, rv.snap.ext, LOADER.log(ctx).offset)
    if key not in st.cache:
        st.cache[key] = golden.plan(rv)
    return st.cache[key]


def _records(p: dict, stem: str) -> list[dict]:
    if stem not in p["pages"]:
        raise not_found(f"{stem}: no courses on this page, so nothing is written for it")
    return p["pages"][stem]


@router.get("/catalogs/{catalog}/golden")
def golden_status(request: Request, catalog: str) -> dict:
    st, ctx, rv = _review(request, catalog)
    ext = rv.snap.ext
    ok, statuses = golden.approval(rv)
    full = _plan(st, ctx, rv)
    p = {k: full[k] for k in ("collisions", "courses", "records", "skipped_no_course_key")} | {
        "pages": len(full["pages"]), "fields": len(full["lineage"]),
        "page_stems": [{"stem": s, "records": len(r)} for s, r in sorted(full["pages"].items())]}
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


@router.get("/catalogs/{catalog}/golden/files/page/{stem}.json")
def golden_page_json(request: Request, catalog: str, stem: str) -> dict:
    st, ctx, rv = _review(request, catalog)
    records = _records(_plan(st, ctx, rv), stem)
    text = golden.page_json(records)
    return {"stem": stem, "records": len(records), "bytes": len(text.encode()), "text": text}


@router.get("/catalogs/{catalog}/golden/files/page/{stem}.html")
def golden_page_html(request: Request, catalog: str, stem: str) -> dict:
    st, ctx, rv = _review(request, catalog)
    _records(_plan(st, ctx, rv), stem)
    data = ctx.page_path(stem).read_bytes()
    return {"stem": stem, "bytes": len(data), "truncated": len(data) > HTML_PREVIEW_BYTES,
            "text": data[:HTML_PREVIEW_BYTES].decode("utf-8", errors="replace")}


@router.get("/catalogs/{catalog}/golden/files/lineage")
def golden_lineage(request: Request, catalog: str, q: str = "", offset: int = Query(0, ge=0),
                   limit: int = Query(100, ge=1, le=500)) -> dict:
    """lineage.parquet's rows, as they'd be written: filter by any cell's text, a page of rows at a time."""
    st, ctx, rv = _review(request, catalog)
    pub = golden.publication_name(ctx, rv)
    rows = [{"publication": pub, **r} for r in _plan(st, ctx, rv)["lineage"]]
    if q:
        needle = q.lower()
        rows = [r for r in rows if any(needle in str(v).lower() for v in r.values())]
    columns = model.LINEAGE.names
    return {"columns": columns, "total": len(_plan(st, ctx, rv)["lineage"]), "matched": len(rows), "offset": offset,
            "rows": [[r.get(c) for c in columns] for r in rows[offset:offset + limit]]}


@router.get("/catalogs/{catalog}/golden/files/publication.json")
def golden_publication_json(request: Request, catalog: str, author: str = "") -> dict:
    """publication.json as it would be written now. The lineage hash is only known once the file is written."""
    st, ctx, rv = _review(request, catalog)
    p = _plan(st, ctx, rv)
    ok, statuses = golden.approval(rv)
    by = f"{author} via the Studio UI" if author else "<you> via the Studio UI"
    doc = golden.publication_doc(ctx, rv, p, golden.publication_name(ctx, rv), golden.default_target(ctx), by, ok,
                                 statuses, {"rows": len(p["lineage"]), "sha256": "<computed when written>"})
    if len(doc["page_stems"]) > 20:
        doc["page_stems"] = doc["page_stems"][:20] + [f"… {len(p['pages']) - 20:,} more"]
    return {"text": json.dumps(doc, indent=2, ensure_ascii=False) + "\n", "truncated_page_stems": len(p["pages"]) > 20}
