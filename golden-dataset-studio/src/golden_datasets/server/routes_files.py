"""Storage files (a debugging view): the files the Studio keeps for a catalog on its storage root, and a preview of
each one, so a reader can see how it all works under the hood.

`/files` lists them (it lists the root, which the Studio itself never needs to do: this is a debugging tool, so the
listing is cached for a few seconds). `/files/content` shows one listed file: JSON pretty-printed, the annotation
log as events (newest first, filterable), Parquet as a table (paged, filterable). Nothing here writes.
"""

from __future__ import annotations

import datetime as dt
import decimal
import functools
import json
import re
import subprocess
import time
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request

from .. import layout
from .state import studio

router = APIRouter(prefix="/api")

LIST_TTL = 10.0                 # seconds a listing is reused
TEXT_CAP = 400_000              # characters of a text file shown
MUTABLE = ("manifest.json", "annotations.jsonl", "/assets/assets.parquet", "/assets/page_assets.parquet")

# what each kind of file is, for the reader (first match wins)
ABOUT = [
    (r"(^|/)manifest\.json$", "The root's index: every catalog, its crawls, ruleset versions and their extractions. "
                              "Read with its ETag and written with optimistic concurrency, so writers never clash."),
    (r"/rules/[^/]+/v\d+\.json$", "One rule version, immutable: its definition (selector, regex …), what / how / why "
                                  "in plain words, examples, who published it, and a content hash."),
    (r"/rulesets/v\d+\.json$", "A ruleset version, immutable: which version of each rule runs, plus catalog settings. "
                               "Publishing a rule makes a new one; unchanged rules keep their version."),
    (r"/annotations\.jsonl$", "The annotation log, append-only: every verdict, comment and approval, one JSON event per "
                              "line. An edit is a new event whose `supersedes` names the old one."),
    (r"/crawl\.json$", "The crawl, as xtra-cli saved it (read-only for the Studio)."),
    (r"/pages\.parquet$", "Index of the crawl's saved pages (stem, URL, title, sizes), written by `golden-datasets init`."),
    (r"/assets/[^/]+\.parquet$", "The page assets (CSS, fonts, images) fetched once and stored by hash."),
    (r"/extractions/[^/]+/extraction\.json$", "One run of a ruleset over the crawl: which ruleset, when, row counts "
                                              "and hashes of its tables."),
    (r"/page_labels\.parquet$", "Extraction table: which page rules recognised each page."),
    (r"/occurrences\.parquet$", "Extraction table: each course a record locator found, with its css path on the page."),
    (r"/matches\.parquet$", "Extraction table: each field rule's value for each course, with where it sits on the page."),
    (r"/signals\.parquet$", "Extraction table: the uncertainty signals that order the Rules tab (length outliers, "
                            "label text in a value …)."),
    (r"/golden/[^/]+/lineage\.parquet$", "A golden publication's lineage: each published value → its rule, version, "
                                         "occurrence and verdicts. Stays in the Studio."),
    (r"/golden/[^/]+/publication\.json$", "A golden publication: its extraction, ruleset, approvals and where it went."),
]


@functools.lru_cache(maxsize=8)
def account_id(account: str) -> str | None:
    """The storage account's Azure resource id: $GOLDEN_DATASETS_AZURE_ACCOUNT_ID when it names this account (a
    deployed Studio has no Azure CLI), else from the signed-in Azure CLI (None when neither can say)."""
    import os

    env = os.environ.get("GOLDEN_DATASETS_AZURE_ACCOUNT_ID", "").strip()
    if env.lower().endswith(f"/storageaccounts/{account.lower()}"):
        return env
    try:
        r = subprocess.run(["az", "storage", "account", "show", "-n", account, "--query", "id", "-o", "tsv"],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (r.stdout.strip() or None) if r.returncode == 0 else None


#: The Azure tenant the portal links open in (its domain or id); without it the portal may open the wrong
#: directory and not find the resource. GOLDEN_DATASETS_AZURE_TENANT overrides it.
DEFAULT_TENANT = "credengine.onmicrosoft.com"


def tenant() -> str:
    import os

    return os.environ.get("GOLDEN_DATASETS_AZURE_TENANT") or DEFAULT_TENANT


def portal(root) -> dict | None:
    """Links into the Azure portal (they work for whoever is signed in to Azure): the account's storage browser, and
    a function from a root-relative path to that blob's page. None for a local root."""
    account = getattr(root, "account", None)
    if not account or account == "devstoreaccount1":
        return None
    rid = account_id(account)
    if not rid:
        return None
    enc = quote(rid, safe="")
    container, prefix = root.container_name, root.prefix
    base = f"https://portal.azure.com/#@{tenant()}"

    def blob(path: str) -> str:
        name = f"{prefix}/{path}" if prefix else path
        return (f"{base}/view/Microsoft_Azure_Storage/BlobPropertiesBladeV2/storageAccountId/{enc}"
                f"/path/{quote(f'{container}/{name}', safe='')}/isDeleted~/false/tabToload~/0")

    return {"browser": f"{base}/resource{rid}/storagebrowser",
            "container_url": f"{base}/view/Microsoft_Azure_Storage/ContainerMenuBlade/~/overview/storageAccountId/{enc}"
                             f"/path/{quote(container, safe='')}",
            "container": container, "prefix": prefix, "blob": blob}


def about(path: str) -> str:
    return next((text for pat, text in ABOUT if re.search(pat, path)), "")


def group(path: str, catalog: str) -> str:
    if path == layout.MANIFEST:
        return "Root"
    rest = path[len(catalog) + 1:]
    if rest.startswith(f"{layout.STUDIO}/rules/"):
        return "Rules"
    if rest.startswith(f"{layout.STUDIO}/rulesets/"):
        return "Rulesets"
    if rest.startswith(layout.STUDIO):
        return "Annotations"
    if "/extractions/" in rest:
        return "Extractions"
    if "/golden/" in rest:
        return "Golden publications"
    return "Crawl"


def _listing(request: Request, catalog: str) -> tuple[object, list[dict]]:
    st = studio(request)
    ctx = st.ctx(catalog)
    key = ("files", ctx.catalog, ctx.crawl)
    hit = st.cache.get(key)
    if hit and time.monotonic() - hit[0] < LIST_TTL:
        return ctx, hit[1]
    sizes: dict[str, int] = {}
    for prefix in (layout.catalog_dir(ctx.catalog), layout.crawl_dir(ctx.catalog, ctx.crawl)):
        try:
            sizes.update(ctx.root.sizes(prefix))
        except FileNotFoundError:
            pass
    for single in (layout.MANIFEST, layout.crawl_json(ctx.catalog, ctx.crawl)):
        s = ctx.root.stat(single)
        if s is not None:
            sizes[single] = s.size
    files = [{"path": p, "size": n, "group": group(p, ctx.catalog), "about": about(p)}
             for p, n in sorted(sizes.items())
             if "/assets/files/" not in p and not p.endswith((".lock", ".etag")) and "/." not in p]
    st.cache[key] = (time.monotonic(), files)
    return ctx, files


@router.get("/catalogs/{catalog}/files")
def files(request: Request, catalog: str) -> dict:
    """The catalog's Studio files on the storage root: the manifest, rules, rulesets, the annotation log, the crawl
    index, extractions and golden publications (not the saved pages or archived asset files)."""
    ctx, listed = _listing(request, catalog)
    links = portal(ctx.root)
    files = [f | {"portal": links["blob"](f["path"])} for f in listed] if links else listed
    return {"root": ctx.root.uri, "catalog": ctx.catalog, "crawl": ctx.crawl, "files": files,
            "portal": {k: v for k, v in links.items() if k != "blob"} if links else None}


def _plain(v):
    """A Parquet / DuckDB value as JSON."""
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, bytes):
        return v.hex()
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return v


@router.get("/catalogs/{catalog}/files/content")
def content(request: Request, catalog: str, path: str, offset: int = 0, limit: int = 100, q: str | None = None,
            newest: bool = True) -> dict:
    """One listed file. `kind`: `json` (`text`), `jsonl` (`rows` of events; newest first unless `newest=false`),
    `table` (Parquet: `columns`, `rows`), or `text`. `q` filters events and rows (case-insensitive, any column)."""
    ctx, listed = _listing(request, catalog)
    meta = next((f for f in listed if f["path"] == path), None)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"{path} is not one of this catalog's Studio files")
    limit = max(1, min(limit, 500))
    links = portal(ctx.root)
    head = {"path": path, "uri": f"{ctx.root.uri}/{path}", "size": meta["size"], "about": meta["about"],
            "portal": links["blob"](path) if links else None}
    root = ctx.root
    if path.endswith(".parquet"):
        import duckdb

        local = str(root.local_path(path, mutable=path.endswith(MUTABLE)))
        con = duckdb.connect()
        src = "read_parquet(?)"
        where, args = ("WHERE CAST(t AS VARCHAR) ILIKE ?", [f"%{q}%"]) if q else ("", [])
        total = con.execute(f"SELECT count(*) FROM {src}", [local]).fetchone()[0]
        matched = con.execute(f"SELECT count(*) FROM {src} t {where}", [local, *args]).fetchone()[0] if q else total
        cur = con.execute(f"SELECT * FROM {src} t {where} LIMIT ? OFFSET ?", [local, *args, limit, offset])
        cols = [d[0] for d in cur.description]
        rows = [[_plain(v) for v in r] for r in cur.fetchall()]
        return {**head, "kind": "table", "columns": cols, "total": total, "matched": matched, "offset": offset,
                "rows": rows}
    raw = root.read_bytes(path).decode("utf-8", errors="replace")
    if path.endswith(".jsonl"):
        lines = [(i + 1, line) for i, line in enumerate(raw.splitlines()) if line.strip()]
        if newest:
            lines.reverse()
        hit = [(n, line) for n, line in lines if not q or q.lower() in line.lower()]
        rows = []
        for n, line in hit[offset:offset + limit]:
            try:
                rows.append({"line": n, "event": json.loads(line)})
            except ValueError:
                rows.append({"line": n, "event": line})
        return {**head, "kind": "jsonl", "total": len(lines), "matched": len(hit), "offset": offset, "rows": rows}
    if path.endswith(".json"):
        try:
            text = json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
        except ValueError:
            text = raw
        return {**head, "kind": "json", "text": text[:TEXT_CAP], "truncated": len(text) > TEXT_CAP}
    return {**head, "kind": "text", "text": raw[:TEXT_CAP], "truncated": len(raw) > TEXT_CAP}
