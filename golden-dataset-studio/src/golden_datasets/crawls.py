"""Catalogs xtra-cli has crawled, and adding one to the Studio (spec §7.1, "Add a catalog").

The crawls root is where xtra-cli writes (`<catalog>/<crawl>/crawl.json + pages/`). It is the storage root itself
when the Studio serves that folder, or the container above the root's prefix on Azure (the Studio's root there is
`xtra-cli-output/<prefix>`, the crawls are in `xtra-cli-output/`). `GOLDEN_DATASETS_CRAWLS_ROOT` overrides it.

Everything a search row shows comes from the crawl itself: the institution's name from its saved pages (the name
their titles repeat, or the site name they declare), else from the host of `crawl.json`'s `seed_url`; `finished_at`,
`pages_saved` and `status` from `crawl.json`. The Studio never starts a crawl.

Adding a catalog copies one crawl's `crawl.json` and `pages/` into the root (server-side on Azure; nothing when
the crawls root is the root), indexes the pages (`init`), archives their assets, and names the catalog in the
manifest. It is setup work, so it may list folders; the rest of the Studio never does.
"""

from __future__ import annotations

import html as htmllib
import json
import os
import re
import sys
from collections import Counter
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


def display_name(catalog: str, seed_url: str | None, institution: str | None = None) -> str:
    """The name on the card: the configured one for the original five; else the institution's name read from the
    pages (`institution_name`); else the short name, capitalized (in capitals when it's 4 letters or fewer)."""
    if catalog in CATALOGS:
        return CATALOGS[catalog]["name"]
    if institution:
        return institution
    s = short_name(seed_url) if seed_url else catalog
    if len(s) <= 4:
        return s.upper()
    s = re.sub(r"(?<=[a-z])(college|university)$", r"-\1", s)  # canadacollege → Canada College
    return " ".join(p.capitalize() for p in s.split("-"))


# What separates a page's own name from the site's in a <title>: "Gender Studies (GNST) < University of Arkansas",
# "Contract Specialist | Professional and Workforce Development | University of Arkansas", "X - Lamar Community College".
TITLE_SEP = re.compile(r"\s*[|<>–—]\s*|\s+-\s+|\u00a0-\u00a0")
# What a site's name carries that isn't the institution's: the catalog itself, its year, the platform.
NOISE = re.compile(r"\b(academic\s+)?(catalogs?|bulletins?|addendum|prod)\b|\b\d{4}\s*[-–]\s*\d{2,4}\b|\b20\d\d\b"
                   r"|smartcatalog\S*|www\.\S+", re.I)
NOT_A_NAME = re.compile(r"curr?[iq]+[cq]?unet|^(view|home|welcome|search.*|academic calendar)$", re.I)
INSTITUTION = re.compile(r"\b(university|college|institute|school|district|academy|seminary|polytechnic)\b", re.I)


def _clean(text: str) -> str:
    text = NOISE.sub(" ", htmllib.unescape(text))
    return re.sub(r"\s+", " ", text).strip(" -–—|:,.\u00a0")


def institution_name(titles: list[str], site_names: list[str]) -> str | None:
    """The institution's name as its pages give it, or None.

    The candidate repeated by the most page titles (a whole title or a part between separators, naming a university,
    college, …); the site name the pages declare (`og:site_name`) when it says more than that candidate (it contains
    it) or when the titles name none. "Professional and Workforce Development | University of Arkansas" titles and
    the site name "University of Arkansas Professional and Workforce Development" give the latter."""
    counts: Counter = Counter()
    titles = [htmllib.unescape(t) for t in titles if t]
    for t in titles:
        parts = TITLE_SEP.split(t)
        # the whole title too, unless it's "page | site" ("University of Arkansas - Fort Smith" is one name)
        for part in {*parts, *([t] if not re.search(r"[|<>–—]", t) else [])}:
            c = _clean(part)
            if c and not NOT_A_NAME.search(c) and INSTITUTION.search(c):
                counts[c] += 1
    # a name only a few titles carry is a page's name, not the site's
    need = max(1, (len(titles) + 1) // 2)
    best = max((c for c in counts if counts[c] >= need), key=lambda c: (counts[c], len(c)), default=None)
    sites = Counter(c for c in (_clean(htmllib.unescape(s)) for s in site_names)
                    if len(c) > 2 and not NOT_A_NAME.search(c))
    site = sites.most_common(1)[0][0] if sites else None
    if site and (best is None or best.lower() in site.lower()):
        return site
    return best


_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_SITE = re.compile(r"<meta[^>]+property=[\"']og:site_name[\"'][^>]+content=[\"']([^\"']+)", re.I)


def read_institution(src: Root, catalog: str, crawl: str, sample: int = 8) -> str | None:
    """`institution_name` of a few saved pages of a crawl, spread over the first few hundred."""
    names = [p for p in src.list_first(layout.pages_dir(catalog, crawl), 400) if p.endswith(".html")]
    if not names:
        return None
    picked = names[:: max(1, len(names) // sample)][:sample]
    titles, sites = [], []
    for p in picked:
        try:
            head = src.read_bytes(p)[:200_000].decode("utf-8", "replace")
        except FileNotFoundError:
            continue
        if m := _TITLE.search(head):
            titles.append(re.sub(r"\s+", " ", m.group(1)).strip())
        if m := _SITE.search(head):
            sites.append(m.group(1))
    return institution_name(titles, sites)


def _crawl_row(src: Root, catalog: str, crawl: str) -> dict | None:
    try:
        doc = json.loads(src.read_bytes(layout.crawl_json(catalog, crawl)))
    except (FileNotFoundError, ValueError):
        return None
    return {"crawl": crawl, "seed_url": doc.get("seed_url") or doc.get("resolved_seed_url"),
            "finished_at": doc.get("finished_at") or doc.get("updated_at"), "pages": doc.get("pages_saved") or 0,
            "status": doc.get("status") or "incomplete"}


_INSTITUTIONS: dict[tuple[str, str, str], str | None] = {}  # (crawls root, catalog, crawl) → name: pages don't change


def _catalog_row(src: Root, catalog: str) -> dict | None:
    runs = sorted((d for d in src.list_dirs(catalog) if d[:4].isdigit()), reverse=True)
    crawls = [r for r in (_crawl_row(src, catalog, k) for k in runs) if r]
    if not crawls:
        return None
    latest = crawls[0]
    key = (src.uri, catalog, latest["crawl"])
    if key not in _INSTITUTIONS and catalog not in CATALOGS:
        _INSTITUTIONS[key] = read_institution(src, catalog, latest["crawl"])
    name = display_name(catalog, latest["seed_url"], _INSTITUTIONS.get(key))
    return {"catalog": catalog, "name": name, "seed_url": latest["seed_url"],
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
        cat.update(name=row["name"] if k is row["crawls"][0] else display_name(
                       catalog, k["seed_url"], read_institution(src, catalog, crawl)),
                   seed_url=k["seed_url"], crawls_root=src.uri,
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
