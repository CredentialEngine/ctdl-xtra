"""W1: rendered pages for the page pane, the HTML view's markup window, page metadata, and archived assets."""

from __future__ import annotations

import mimetypes
import threading
from urllib.parse import urlsplit

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from .. import layout, render
from ..context import Ctx
from ..errors import UserError
from .state import not_found, studio

router = APIRouter()

CSP = ("script-src 'none'; object-src 'none'; frame-src 'none'; worker-src 'none'; form-action 'none'; "
       "base-uri 'self' https: http:; default-src 'self' https: http: data:; "
       "style-src 'self' 'unsafe-inline' https: http:; img-src 'self' https: http: data:; "
       "font-src 'self' https: http: data:")
IMMUTABLE = "public, max-age=31536000, immutable"
_lock = threading.Lock()


def _ctx(request: Request, catalog: str) -> Ctx:
    try:
        ctx = studio(request).ctx(catalog)
        ctx.crawl  # noqa: B018 - raises when the catalog has no crawl
        return ctx
    except UserError as exc:
        raise not_found(str(exc)) from exc


def _pages(request: Request, ctx: Ctx) -> dict[str, dict]:
    """stem -> pages.parquet row, memoized per catalog and crawl."""
    cache = studio(request).cache
    key = ("pages_by_stem", ctx.catalog, ctx.crawl)
    got = cache.get(key)
    if got is None:
        with _lock:
            got = cache.get(key)
            if got is None:
                got = {p["page_stem"]: p for p in ctx.pages()}
                cache[key] = got
    return got


def _page(request: Request, ctx: Ctx, stem: str) -> dict:
    row = _pages(request, ctx).get(stem)
    if row is None:
        raise not_found(f"{ctx.catalog}: no page {stem!r}")
    return row


def _etag_matches(request: Request, etag: str) -> bool:
    inm = request.headers.get("if-none-match")
    return bool(inm) and (inm.strip() == "*" or etag in [t.strip() for t in inm.split(",")])


@router.get("/api/catalogs/{catalog}/pages/{stem}/render")
def page_render(request: Request, catalog: str, stem: str, ruleset: int | None = None):
    ctx = _ctx(request, catalog)
    row = _page(request, ctx, stem)
    try:
        pane_css = render.pane_css_for(ctx, ruleset)
    except (UserError, FileNotFoundError) as exc:
        raise not_found(f"{ctx.catalog}: no ruleset v{ruleset}") from exc
    r = render.rendered(ctx, stem, row["url"], pane_css)
    # With an explicit ruleset the bytes never change (short of a new asset fetch); "latest" can move.
    headers = {"ETag": r.etag, "Content-Security-Policy": CSP, "X-Content-Type-Options": "nosniff",
               "Cache-Control": "private, max-age=86400" if ruleset is not None else "private, max-age=600",
               "Vary": "Accept-Encoding"}
    if _etag_matches(request, r.etag):
        return Response(status_code=304, headers=headers)
    if "gzip" in request.headers.get("accept-encoding", ""):
        return FileResponse(r.gz_path, media_type="text/html; charset=utf-8",
                            headers={**headers, "Content-Encoding": "gzip"})
    return FileResponse(r.path, media_type="text/html; charset=utf-8", headers=headers)


@router.get("/api/catalogs/{catalog}/pages/{stem}/source")
def page_source(request: Request, catalog: str, stem: str, css_path: str | None = None,
                char_start: int | None = None, char_end: int | None = None, text: str | None = None,
                window: int = Query(60, ge=5, le=400)):
    ctx = _ctx(request, catalog)
    _page(request, ctx, stem)
    out = render.source_view(ctx.page_path(stem).read_bytes(), css_path, char_start, char_end, text, window=window)
    return JSONResponse({"stem": stem, **out})


@router.get("/api/catalogs/{catalog}/pages/{stem}/meta")
def page_meta(request: Request, catalog: str, stem: str):
    ctx = _ctx(request, catalog)
    row = _page(request, ctx, stem)
    return {"stem": stem, "url": row["url"], "title": row.get("title") or ""}


def _media_type(ctype: str | None, url: str) -> str:
    if ctype and ctype not in ("application/octet-stream", "binary/octet-stream"):
        return ctype
    guess = mimetypes.guess_type(urlsplit(url).path)[0]
    return guess or ctype or "application/octet-stream"


@router.get("/api/catalogs/{catalog}/assets/{sha256}")
def asset(request: Request, catalog: str, sha256: str):
    if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
        raise not_found("not an asset hash")
    ctx = _ctx(request, catalog)
    meta = render.asset_index(ctx).by_sha.get(sha256)
    if meta is None:
        raise not_found(f"{ctx.catalog}: no archived asset {sha256}")
    etag = f'"{sha256[:32]}"'
    media = _media_type(meta["content_type"], meta["final_url"])
    headers = {"Cache-Control": IMMUTABLE, "ETag": etag, "X-Content-Type-Options": "nosniff",
               "Access-Control-Allow-Origin": "*"}
    if _etag_matches(request, etag):
        return Response(status_code=304, headers=headers)
    try:
        local = ctx.root.local_path(layout.asset_file(ctx.catalog, ctx.crawl, sha256))
    except FileNotFoundError as exc:
        raise not_found(f"{ctx.catalog}: asset file {sha256} missing") from exc
    if "css" in media:
        body = render.asset_css(ctx, sha256, local.read_bytes())
        return Response(body, media_type=media, headers=headers)
    return FileResponse(local, media_type=media, headers=headers)
