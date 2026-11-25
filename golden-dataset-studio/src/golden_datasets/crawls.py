"""Catalogs xtra-cli has crawled, and adding one to the Studio (spec §7.1, "Add a catalog").

The crawls root is xtra-cli's container, where it writes `<catalog>/<crawl>/crawl.json + pages/`
(`xtra_paths.xtra_root`: `GOLDEN_DATASETS_XTRA_SOURCE`, or the older `GOLDEN_DATASETS_CRAWLS_ROOT`; on Azure, the
container above the Studio root's prefix).

Everything a search row shows comes from the crawl itself: the institution's name from its saved pages (the name
their titles repeat, or the site name they declare), else from the host of `crawl.json`'s `seed_url`; `finished_at`,
`pages_saved` and `status` from `crawl.json`. The Studio never starts a crawl.

Adding a catalog names it in the manifest with the root its crawl is in (the Studio reads the crawl there, and
never copies it: LearningProgram spec, approved item 21), indexes the pages (`init`) and archives their assets. It is setup work, so it may list folders; the rest of the Studio never does.
"""

from __future__ import annotations

import html as htmllib
import json
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from urllib.parse import urlsplit

from . import layout, manifest
from .catalogs import CATALOGS
from .errors import UserError
from .storage import Root, open_root

ENV = "GOLDEN_DATASETS_CRAWLS_ROOT"  # the older name of xtra_paths.ENV, still read
# Host labels that say "catalog", not whose catalog it is.
GENERIC = {"www", "catalog", "catalogs", "coursecatalog", "main", "public", "prod", "m"}

# What separates a page's own name from the site's in a <title>: "Gender Studies (GNST) < University of Arkansas",
# "Contract Specialist | Professional and Workforce Development | University of Arkansas", "X - Lamar Community College".
TITLE_SEP = re.compile(r"\s*[|<>–—]\s*|\s+-\s+| - ")
# What a site's name carries that isn't the institution's: the catalog itself, its year, the platform.
NOISE = re.compile(r"\b(academic\s+)?(catalogs?|bulletins?|addendum|prod)\b|\b\d{4}\s*[-–]\s*\d{2,4}\b|\b20\d\d\b"
                   r"|smartcatalog\S*|www\.\S+", re.I)
NOT_A_NAME = re.compile(r"curr?[iq]+[cq]?unet|^(view|home|welcome|search.*|academic calendar)$", re.I)
INSTITUTION = re.compile(r"\b(university|college|institute|school|district|academy|seminary|polytechnic)\b", re.I)

_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_SITE = re.compile(r"<meta[^>]+property=[\"']og:site_name[\"'][^>]+content=[\"']([^\"']+)", re.I)

_INSTITUTIONS: dict[tuple[str, str, str], str | None] = {}  # (crawls root, catalog, crawl) → name: pages don't change


# --- CLI -----------------------------------------------------------------------------------------------


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


def _src(args) -> tuple[Root, Root]:
    root = open_root(args.root)
    return root, open_root(args.crawls_root or default_crawls_root(root))


def matches(row: dict, query: str) -> bool:
    hay = f"{row['name']} {row['catalog']} {row['seed_url'] or ''}".lower()
    return all(w in hay for w in re.split(r"\s+", query.lower().strip()) if w)


# --- Listing ---------------------------------------------------------------------------------------------


def default_crawls_root(root: Root) -> str:
    """xtra-cli's container (xtra_paths.xtra_root), else the root itself."""
    from .xtra_paths import xtra_root

    return xtra_root(root) or root.uri


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


# --- Adding --------------------------------------------------------------------------------------------


def add_catalog(root: Root, src: Root, catalog: str, crawl: str | None = None, by: str | None = None,
                progress=lambda **kw: None, log=print) -> dict:
    """Add one crawl to the Studio: name the catalog in the manifest with where its crawls are (read in place,
    never copied: approved item 21), index its pages and archive their assets.

    `progress(step=…, done=…, total=…)` is called as it goes. Safe to run again."""
    row, chosen = find_crawl(src, catalog, crawl)
    crawl = chosen["crawl"]
    page_count = index_pages(root, src, catalog, chosen, progress, log)
    name = row["name"] if chosen is row["crawls"][0] else display_name(
        catalog, chosen["seed_url"], read_institution(src, catalog, crawl))
    manifest.update(root, lambda doc: name_catalog(doc, catalog, name, chosen["seed_url"], src.uri, by))
    progress(step="done", done=page_count, total=page_count)
    return {"catalog": catalog, "crawl": crawl, "pages": page_count}


def find_crawl(src: Root, catalog: str, crawl: str | None) -> tuple[dict, dict]:
    row = _catalog_row(src, catalog)
    if row is None:
        raise UserError(f"no crawl of {catalog} under {src.uri}")
    chosen = next((c for c in row["crawls"] if c["crawl"] == (crawl or row["crawl"])), None)
    if chosen is None:
        raise UserError(f"{catalog} has no crawl {crawl}")
    if not chosen["pages"]:
        raise UserError(f"{catalog}/{chosen['crawl']} saved no pages")
    return row, chosen


def index_pages(root: Root, src: Root, catalog: str, chosen: dict, progress, log) -> int:
    from . import extract
    from .context import Ctx

    crawl = chosen["crawl"]
    progress(step="indexing", done=0, total=chosen["pages"])
    ctx = Ctx(root, catalog, crawl)
    ctx.crawl_root = src  # read in place; init records it in the manifest (crawls_root)
    out = extract.init(ctx, crawl)
    progress(step="assets", done=0, total=0)
    archive_assets(root, catalog, crawl, log)
    return out["page_count"]


def archive_assets(root: Root, catalog: str, crawl: str, log) -> None:
    from . import assets

    try:
        assets.cmd_fetch(SimpleNamespace(root=root, catalog=catalog, crawl=crawl, max_assets=400))
    except Exception as exc:  # pages still open without their styles
        log(f"{catalog}: assets not archived ({exc})", file=sys.stderr)


def name_catalog(doc: dict, catalog: str, name: str, seed_url: str | None, crawls_root: str, by: str | None) -> None:
    cat = manifest.catalog_entry(doc, catalog)
    cat.update(name=name, seed_url=seed_url, crawls_root=crawls_root, added_by=by, added_at=manifest.now_iso())
    doc["catalogs"].sort(key=lambda c: c["name"].lower())


# --- One catalog's crawls ----------------------------------------------------------------------------------


def _catalog_row(src: Root, catalog: str) -> dict | None:
    runs = sorted((d for d in src.list_dirs(catalog) if d[:4].isdigit()), reverse=True)
    crawls = [r for r in (_crawl_row(src, catalog, k) for k in runs) if r]
    if not crawls:
        return None
    latest = crawls[0]
    name = display_name(catalog, latest["seed_url"], cached_institution(src, catalog, latest["crawl"]))
    return {"catalog": catalog, "name": name, "seed_url": latest["seed_url"],
            "crawl": latest["crawl"], "finished_at": latest["finished_at"], "pages": latest["pages"],
            "status": latest["status"], "crawls": crawls}


def _crawl_row(src: Root, catalog: str, crawl: str) -> dict | None:
    try:
        doc = json.loads(src.read_bytes(layout.crawl_json(catalog, crawl)))
    except (FileNotFoundError, ValueError):
        return None
    return {"crawl": crawl, "seed_url": doc.get("seed_url") or doc.get("resolved_seed_url"),
            "finished_at": doc.get("finished_at") or doc.get("updated_at"), "pages": doc.get("pages_saved") or 0,
            "status": doc.get("status") or "incomplete"}


def cached_institution(src: Root, catalog: str, crawl: str) -> str | None:
    key = (src.uri, catalog, crawl)
    if key not in _INSTITUTIONS and catalog not in CATALOGS:
        _INSTITUTIONS[key] = read_institution(src, catalog, crawl)
    return _INSTITUTIONS.get(key)


# --- Names -------------------------------------------------------------------------------------------------


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


def short_name(seed_url: str) -> str:
    """The first host label that isn't generic: avc.elumenapp.com → avc, catalog.ualr.edu → ualr."""
    labels = (urlsplit(seed_url if "//" in seed_url else f"//{seed_url}").hostname or "").split(".")
    for label in labels[:-1]:
        if label not in GENERIC:
            return label
    return labels[0] if labels else seed_url


def read_institution(src: Root, catalog: str, crawl: str, sample: int = 8) -> str | None:
    """`institution_name` of a few saved pages of a crawl, spread over the first few hundred."""
    names = [p for p in src.list_first(layout.pages_dir(catalog, crawl), 400) if p.endswith(".html")]
    if not names:
        return None
    picked = names[:: max(1, len(names) // sample)][:sample]
    titles, sites = [], []
    for head in filter(None, (read_head(src, p) for p in picked)):
        if m := _TITLE.search(head):
            titles.append(re.sub(r"\s+", " ", m.group(1)).strip())
        if m := _SITE.search(head):
            sites.append(m.group(1))
    return institution_name(titles, sites)


def read_head(src: Root, path: str) -> str | None:
    try:
        return src.read_bytes(path)[:200_000].decode("utf-8", "replace")
    except FileNotFoundError:
        return None


def institution_name(titles: list[str], site_names: list[str]) -> str | None:
    """The institution's name as its pages give it, or None.

    The candidate repeated by the most page titles (a whole title or a part between separators, naming a university,
    college, …); the site name the pages declare (`og:site_name`) when it says more than that candidate (it contains
    it) or when the titles name none. "Professional and Workforce Development | University of Arkansas" titles and
    the site name "University of Arkansas Professional and Workforce Development" give the latter."""
    titles = [htmllib.unescape(t) for t in titles if t]
    best = most_repeated_name(titles)
    site = declared_site_name(site_names)
    if site and (best is None or best.lower() in site.lower()):
        return site
    return best


def most_repeated_name(titles: list[str]) -> str | None:
    counts = Counter(name for title in titles for name in title_names(title))
    # a name only a few titles carry is a page's name, not the site's
    need = max(1, (len(titles) + 1) // 2)
    return max((c for c in counts if counts[c] >= need), key=lambda c: (counts[c], len(c)), default=None)


def title_names(title: str) -> list[str]:
    """The institution names one title holds: its parts, and the whole title unless it's "page | site"
    ("University of Arkansas - Fort Smith" is one name)."""
    parts = {*TITLE_SEP.split(title), *([title] if not re.search(r"[|<>–—]", title) else [])}
    names = (_clean(part) for part in parts)
    return [c for c in names if c and not NOT_A_NAME.search(c) and INSTITUTION.search(c)]


def declared_site_name(site_names: list[str]) -> str | None:
    sites = Counter(c for c in (_clean(htmllib.unescape(s)) for s in site_names)
                    if len(c) > 2 and not NOT_A_NAME.search(c))
    return sites.most_common(1)[0][0] if sites else None


def _clean(text: str) -> str:
    text = NOISE.sub(" ", htmllib.unescape(text))
    return re.sub(r"\s+", " ", text).strip(" -–—|:,. ")
