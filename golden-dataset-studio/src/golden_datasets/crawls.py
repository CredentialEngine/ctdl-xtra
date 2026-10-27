"""Catalogs xtra-cli has crawled, and adding one to the Studio (spec §7.1, "Add a catalog").

The crawls root is where xtra-cli writes (`<catalog>/<crawl>/crawl.json + pages/`). It is the storage root itself
when the Studio serves that folder, or the container above the root's prefix on Azure (the Studio's root there is
`xtra-cli-output/<prefix>`, the crawls are in `xtra-cli-output/`). `GOLDEN_DATASETS_CRAWLS_ROOT` overrides it.

Everything a search row shows comes from `crawl.json`: `seed_url` (the name is read from its host), `finished_at`,
`pages_saved` and `status`. The Studio never starts a crawl.

Adding a catalog copies one crawl's `crawl.json` and `pages/` into the root (server-side on Azure; nothing when
the crawls root is the root), indexes the pages (`init`), archives their assets, and names the catalog in the
manifest. It is setup work, so it may list folders; the rest of the Studio never does.
"""

from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from urllib.parse import urlsplit

from . import layout, manifest
from .catalogs import CATALOGS
from .errors import UserError
from .storage import AzureRoot, Root, open_root
from .sync import copy_one

ENV = "GOLDEN_DATASETS_CRAWLS_ROOT"
# Host labels that say "catalog", not whose catalog it is.
GENERIC = {"www", "catalog", "catalogs", "coursecatalog", "main", "public", "prod", "m"}


def default_crawls_root(root: Root) -> str:
    """$GOLDEN_DATASETS_CRAWLS_ROOT, else the container above an Azure root's prefix, else the root itself."""
    if os.environ.get(ENV):
        return os.environ[ENV]
    if isinstance(root, AzureRoot) and root.prefix:
        return root.uri[: -len(root.prefix)].rstrip("/")
    return root.uri


def short_name(seed_url: str) -> str:
    """The first host label that isn't generic: avc.elumenapp.com → avc, catalog.ualr.edu → ualr."""
    labels = (urlsplit(seed_url if "//" in seed_url else f"//{seed_url}").hostname or "").split(".")
    for label in labels[:-1]:
        if label not in GENERIC:
            return label
    return labels[0] if labels else seed_url


def display_name(catalog: str, seed_url: str | None) -> str:
    """The name on the card: the configured one for the original five, else the short name, capitalized
    (in capitals when it's 4 letters or fewer: AVC, UALR, Cuesta)."""
    if catalog in CATALOGS:
        return CATALOGS[catalog]["name"]
    s = short_name(seed_url) if seed_url else catalog
    return s.upper() if len(s) <= 4 else "-".join(p.capitalize() for p in s.split("-"))


def _crawl_row(src: Root, catalog: str, crawl: str) -> dict | None:
    try:
        doc = json.loads(src.read_bytes(layout.crawl_json(catalog, crawl)))
    except (FileNotFoundError, ValueError):
        return None
    return {"crawl": crawl, "seed_url": doc.get("seed_url") or doc.get("resolved_seed_url"),
            "finished_at": doc.get("finished_at") or doc.get("updated_at"), "pages": doc.get("pages_saved") or 0,
            "status": doc.get("status") or "incomplete"}


def _catalog_row(src: Root, catalog: str) -> dict | None:
    runs = sorted((d for d in src.list_dirs(catalog) if d[:4].isdigit()), reverse=True)
    crawls = [r for r in (_crawl_row(src, catalog, k) for k in runs) if r]
    if not crawls:
        return None
    latest = crawls[0]
    return {"catalog": catalog, "name": display_name(catalog, latest["seed_url"]), "seed_url": latest["seed_url"],
            "crawl": latest["crawl"], "finished_at": latest["finished_at"], "pages": latest["pages"],
            "status": latest["status"], "crawls": crawls}


def list_crawled(src: Root, added: set[str] = frozenset()) -> list[dict]:
    """One row per catalog folder that has at least one crawl, its latest crawl first; newest crawl first."""
    with ThreadPoolExecutor(max_workers=16) as pool:
        rows = [r for r in pool.map(lambda c: _catalog_row(src, c), src.list_dirs("")) if r]
    for r in rows:
        r["added"] = r["catalog"] in added
    rows.sort(key=lambda r: r["finished_at"] or "", reverse=True)
    return rows


def added_catalogs(root: Root) -> set[str]:
    doc, _ = manifest.load(root)
    return {c["catalog"] for c in doc["catalogs"] if c.get("current_crawl")}


def add_catalog(root: Root, src: Root, catalog: str, crawl: str | None = None, by: str | None = None,
                progress=lambda **kw: None, log=print) -> dict:
    """Copy one crawl into the root, index its pages, archive their assets and name the catalog in the manifest.

    `progress(step=…, done=…, total=…)` is called as it goes. Safe to run again: copied files are skipped."""
    from . import assets, extract
    from .context import Ctx

    row = _catalog_row(src, catalog)
    if row is None:
        raise UserError(f"no crawl of {catalog} under {src.uri}")
    k = next((c for c in row["crawls"] if c["crawl"] == (crawl or row["crawl"])), None)
    if k is None:
        raise UserError(f"{catalog} has no crawl {crawl}")
    if not k["pages"]:
        raise UserError(f"{catalog}/{k['crawl']} saved no pages")
    crawl = k["crawl"]

    if src.uri != root.uri:
        files = [layout.crawl_json(catalog, crawl)] + [
            p for p in src.list(layout.pages_dir(catalog, crawl)) if p.endswith((".html", ".meta.json"))]
        have = root.sizes(layout.crawl_input(catalog, crawl))
        sizes = src.sizes(layout.crawl_input(catalog, crawl))
        todo = [p for p in files if have.get(p) != sizes.get(p)]
        progress(step="copying", done=len(files) - len(todo), total=len(files))
        with ThreadPoolExecutor(max_workers=32) as pool:
            for i, _ in enumerate(pool.map(lambda p: copy_one(src, root, p), todo), 1):
                if i % 100 == 0 or i == len(todo):
                    progress(step="copying", done=len(files) - len(todo) + i, total=len(files))

    progress(step="indexing", done=0, total=k["pages"])
    ctx = Ctx(root, catalog, crawl)
    out = extract.init(ctx, crawl)
    progress(step="assets", done=0, total=0)
    try:
        assets.cmd_fetch(SimpleNamespace(root=root, catalog=catalog, crawl=crawl, max_assets=400))
    except Exception as exc:  # pages still open without their styles
        log(f"{catalog}: assets not archived ({exc})", file=sys.stderr)

    def change(doc: dict) -> None:
        cat = manifest.catalog_entry(doc, catalog)
        cat.update(name=display_name(catalog, k["seed_url"]), seed_url=k["seed_url"], crawls_root=src.uri,
                   added_by=by, added_at=manifest.now_iso())
        doc["catalogs"].sort(key=lambda c: c["name"].lower())

    manifest.update(root, change)
    progress(step="done", done=out["page_count"], total=out["page_count"])
    return {"catalog": catalog, "crawl": crawl, "pages": out["page_count"]}


# --- CLI -----------------------------------------------------------------------------------------------
def _src(args) -> tuple[Root, Root]:
    root = open_root(args.root)
    return root, open_root(args.crawls_root or default_crawls_root(root))


def cmd_list(args) -> int:
    root, src = _src(args)
    rows = list_crawled(src, added_catalogs(root))
    if args.q:
        rows = [r for r in rows if matches(r, args.q)]
    for r in rows:
        print(f"{r['catalog']:<60} {(r['finished_at'] or '')[:10]:<10} {r['pages']:>6} {r['status']:<14}"
              f"{'added' if r['added'] else ''}")
    return 0


def cmd_add(args) -> int:
    root, src = _src(args)
    out = add_catalog(root, src, args.catalog, args.crawl, by=args.by,
                      progress=lambda **kw: print(f"  {kw['step']} {kw['done']}/{kw['total']}", file=sys.stderr)
                      if kw["step"] != "copying" or kw["done"] == kw["total"] else None)
    print(" · ".join(f"{k} {v}" for k, v in out.items()))
    return 0


def matches(row: dict, query: str) -> bool:
    hay = f"{row['name']} {row['catalog']} {row['seed_url'] or ''}".lower()
    return all(w in hay for w in re.split(r"\s+", query.lower().strip()) if w)
