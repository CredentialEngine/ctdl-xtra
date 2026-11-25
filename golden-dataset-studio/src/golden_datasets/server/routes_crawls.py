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

from .. import crawls, telemetry
from ..storage import open_root
from .state import studio

router = APIRouter(prefix="/api")
TTL = 300.0


@router.get("/crawls")
def crawled(request: Request, refresh: bool = False) -> dict:
    return _list(studio(request), refresh)


@router.post("/crawls/{catalog}/add")
def add(request: Request, catalog: str, body: Annotated[dict, Body()]) -> dict:
    st = studio(request)
    row, crawl, pages = addable_crawl(st, catalog, body.get("crawl"))
    with st._lock:
        running = st.adding.get(catalog)
        if running and running["step"] not in ("failed", "done"):
            return running
        job = new_job(catalog, row, crawl, pages, body.get("by"))
        st.adding[catalog] = job
    attrs = {"ce.catalog.folder": catalog, "ce.crawl.id": crawl, "ce.crawl.pages": pages}
    carried = telemetry.carry()
    telemetry.set(attrs)
    threading.Thread(target=run_add_job, args=(job, st, attrs, carried), name=f"add-{catalog}", daemon=True).start()
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


def _list(st, refresh: bool = False) -> dict:
    rows = crawled_rows(st, refresh)
    added = crawls.added_catalogs(st.root)
    return {"crawls_root": st.crawls_root,
            "items": [{**r, "added": r["catalog"] in added, "adding": r["catalog"] in st.adding} for r in rows]}


def crawled_rows(st, refresh: bool) -> list[dict]:
    hit = st.cache.get(("crawls",))
    if hit and not refresh and time.monotonic() - hit[0] < TTL:
        return hit[1]
    rows = crawls.list_crawled(open_root(st.crawls_root))
    st.cache[("crawls",)] = (time.monotonic(), rows)
    return rows


def addable_crawl(st, catalog: str, crawl: str | None) -> tuple[dict, str, int]:
    """(the catalog's row, the crawl to add, its pages); refused when it's added already or saved no pages."""
    row = next((r for r in _list(st)["items"] if r["catalog"] == catalog), None)
    if row is None:
        raise HTTPException(404, f"no crawl of {catalog}")
    if row["added"]:
        raise HTTPException(409, f"{row['name']} is already in the Studio")
    crawl = crawl or row["crawl"]
    chosen = next((c for c in row["crawls"] if c["crawl"] == crawl), None)
    if chosen is None or not chosen["pages"]:
        raise HTTPException(400, f"{catalog}/{crawl} has no saved pages")
    return row, crawl, chosen["pages"]


def new_job(catalog: str, row: dict, crawl: str, pages: int, by: str | None) -> dict:
    return {"catalog": catalog, "name": row["name"], "crawl": crawl, "seed_url": row["seed_url"],
            "pages": pages, "by": by, "step": "starting", "done": 0, "total": 0, "error": None,
            "started_at": time.time()}


def run_add_job(job: dict, st, attrs: dict, carried: dict) -> None:
    with telemetry.job("catalog.add", attrs, carried=carried):
        _add(job, st, job["catalog"], job["crawl"])


def _add(job: dict, st, catalog: str, crawl: str) -> None:
    """Copy the crawl in, index and archive it (the add job's thread); a failure is shown on the picker's card."""
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
        telemetry.error(exc)
