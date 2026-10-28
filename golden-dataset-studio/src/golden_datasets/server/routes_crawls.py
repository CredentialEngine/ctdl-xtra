"""Add a catalog (spec §7.1): search the catalogs xtra-cli has crawled, and add one to the Studio.

The list is read from the crawls root (one `crawl.json` per crawl, ~8 s for 60 catalogs on Azure), so it is kept for
`TTL` seconds. Adding runs in a background thread; the picker shows its progress through `/api/catalogs`.
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request

from .. import crawls
from ..storage import open_root
from .state import studio

router = APIRouter(prefix="/api")
TTL = 300.0


def _list(st, refresh: bool = False) -> dict:
    hit = st.cache.get(("crawls",))
    if hit and not refresh and time.monotonic() - hit[0] < TTL:
        rows = hit[1]
    else:
        rows = crawls.list_crawled(open_root(st.crawls_root))
        st.cache[("crawls",)] = (time.monotonic(), rows)
    added = crawls.added_catalogs(st.root)
    return {"crawls_root": st.crawls_root,
            "items": [{**r, "added": r["catalog"] in added, "adding": r["catalog"] in st.adding} for r in rows]}


@router.get("/crawls")
def crawled(request: Request, refresh: bool = False) -> dict:
    return _list(studio(request), refresh)


@router.post("/crawls/{catalog}/add")
def add(request: Request, catalog: str, body: Annotated[dict, Body()]) -> dict:
    st = studio(request)
    row = next((r for r in _list(st)["items"] if r["catalog"] == catalog), None)
    if row is None:
        raise HTTPException(404, f"no crawl of {catalog}")
    if row["added"]:
        raise HTTPException(409, f"{row['name']} is already in the Studio")
    crawl = body.get("crawl") or row["crawl"]
    k = next((c for c in row["crawls"] if c["crawl"] == crawl), None)
    if k is None or not k["pages"]:
        raise HTTPException(400, f"{catalog}/{crawl} has no saved pages")
    with st._lock:
        if catalog in st.adding and st.adding[catalog]["step"] not in ("failed", "done"):
            return st.adding[catalog]
        job = {"catalog": catalog, "name": row["name"], "crawl": crawl, "seed_url": row["seed_url"],
               "pages": k["pages"], "by": body.get("by"), "step": "starting", "done": 0, "total": 0, "error": None,
               "started_at": time.time()}
        st.adding[catalog] = job

    def run() -> None:
        try:
            crawls.add_catalog(st.root, open_root(st.crawls_root), catalog, crawl, by=job["by"],
                               progress=lambda **kw: job.update(kw))
            st.cache.pop(("crawls",), None)
            with st._lock:  # the picker drops the job once its (re-read) manifest has the catalog
                for ctx in st._ctx.values():
                    ctx.invalidate()
        except Exception as exc:  # shown on the card; adding it again resumes
            print(f"add {catalog}: {exc}", file=sys.stderr)
            job.update(step="failed", error=str(exc))

    threading.Thread(target=run, name=f"add-{catalog}", daemon=True).start()
    return job


@router.delete("/crawls/{catalog}/add")
def dismiss(request: Request, catalog: str) -> dict:
    """Forget a failed add (the card goes away)."""
    st = studio(request)
    with st._lock:
        job = st.adding.get(catalog)
        if job and job["step"] == "failed":
            st.adding.pop(catalog)
    return {"ok": True}
