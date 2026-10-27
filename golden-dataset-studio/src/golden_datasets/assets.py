"""`golden-datasets assets fetch`: archive each page's CSS, icons, fonts and images once, stored by hash (spec §9).

For every saved page it collects the stylesheets (`<link rel=stylesheet>`, `rel=preload as=style|font`), icons,
images (`<img src/srcset>`, `<source srcset>`, `<video poster>`) and every `url()` / `@import` in `<style>` elements
and `style=` attributes. Each distinct URL is fetched once with a desktop Chrome user agent and the page's URL as
Referer; fetched CSS is scanned for `@import` and `url()` in turn (fonts: woff2 only). JavaScript is never fetched
or run. Bodies go to `assets/files/<sha256>` (immutable); two Parquet tables say which page uses what
(`page_assets`) and which URL holds which body (`assets`).

URLs that differ only by a numeric cache-buster query (`footer-logo.png?1791852215158`, a different number on every
AVC page) are fetched once, under their canonical URL (`canonical_url`); `render.py` looks URLs up the same way.
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit, urlunsplit

from . import layout, manifest
from .context import Ctx
from .errors import ConflictError
from .model import ASSETS, PAGE_ASSETS

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/141.0.0.0 Safari/537.36")
PER_HOST = 2          # concurrent requests per host
WORKERS = 8           # concurrent requests overall

# url(...) with or without quotes, and @import "…" / @import '…' (the url() form is caught by the first branch).
CSS_URL = re.compile(r"""url\(\s*(?P<q>['"]?)(?P<u>[^'")]*?)(?P=q)\s*\)|@import\s+(?P<q2>['"])(?P<u2>[^'"]+)(?P=q2)""")
_FONT_NOT_WOFF2 = re.compile(r"\.(?:woff|ttf|eot|otf)(?:[?#]|$)|\.svg#", re.I)
_CACHE_BUSTER = re.compile(r"^\d{6,}$")
_SKIP_SCHEMES = ("data:", "javascript:", "mailto:", "tel:", "about:", "blob:", "#")
TRACKERS = (
    "google-analytics.com", "googletagmanager.com", "doubleclick.net", "googleadservices.com", "facebook.com",
    "facebook.net", "snapchat.com", "sc-static.net", "reddit.com", "redditstatic.com", "linkedin.com",
    "licdn.com", "amazon-adsystem.com", "mountain.com", "stackadapt.com", "bing.com", "hotjar.com",
    "clarity.ms", "adsrvr.org", "quantserve.com", "scorecardresearch.com",
)


# --- URLs --------------------------------------------------------------------------------------------
def canonical_url(url: str) -> str:
    """The URL an asset is archived under: no fragment, and no purely numeric cache-buster query."""
    parts = urlsplit(url)
    query = "" if _CACHE_BUSTER.match(parts.query or "") else parts.query
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def fetchable(url: str) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    host = urlsplit(url).hostname or ""
    return not any(host == t or host.endswith("." + t) for t in TRACKERS)


def skip_ref(ref: str) -> bool:
    return not ref or ref.strip().lower().startswith(_SKIP_SCHEMES)


def css_refs(css: str) -> list[str]:
    """Every `url()` and `@import` target in a piece of CSS, as written."""
    return [m.group("u") or m.group("u2") or "" for m in CSS_URL.finditer(css)]


def srcset_urls(value: str) -> list[str]:
    return [part.strip().split()[0] for part in value.split(",") if part.strip()]


def page_base(doc, url: str) -> str:
    base = doc.xpath("//base/@href")
    return urljoin(url, base[0].strip()) if base else url


# --- discovery (runs in worker processes) ------------------------------------------------------------
def discover(html: bytes, url: str) -> list[tuple[str, str]]:
    """(absolute url, kind) for every asset one page references, in document order, without duplicates."""
    import lxml.html

    doc = lxml.html.document_fromstring(html)
    base = page_base(doc, url)
    out: list[tuple[str, str]] = []

    def add(ref: str | None, kind: str, against: str = base) -> None:
        if ref is None or skip_ref(ref):
            return
        out.append((urljoin(against, ref.strip()), kind))

    for link in doc.iter("link"):
        rel = f" {(link.get('rel') or '').lower()} "
        href = link.get("href")
        if " stylesheet " in rel:
            add(href, "stylesheet")
        elif "icon" in rel:
            add(href, "icon")
        elif " preload " in rel and (link.get("as") or "").lower() in ("style", "font"):
            add(href, "stylesheet" if link.get("as") == "style" else "font")
    for style in doc.iter("style"):
        for ref in css_refs(style.text or ""):
            add(ref, "style-url")
    for el in doc.xpath("//*[@style]"):
        for ref in css_refs(el.get("style") or ""):
            add(ref, "style-url")
    for el in doc.iter("img", "source", "video", "input"):
        if el.tag in ("img", "input"):
            add(el.get("src"), "image")
        if el.tag == "video":
            add(el.get("poster"), "image")
        for ref in srcset_urls(el.get("srcset") or ""):
            add(ref, "image")
    seen: set[str] = set()
    uniq = []
    for u, k in out:
        if u not in seen and fetchable(u):
            seen.add(u)
            uniq.append((u, k))
    return uniq


def _discover_file(job: tuple[str, str, str]) -> tuple[str, str, list[tuple[str, str]]]:
    stem, path, url = job
    with open(path, "rb") as fh:
        return stem, url, discover(fh.read(), url)


# --- fetching ----------------------------------------------------------------------------------------
class Fetcher:
    def __init__(self):
        import httpx

        self.client = httpx.Client(follow_redirects=True, timeout=30, headers={"User-Agent": USER_AGENT},
                                   limits=httpx.Limits(max_connections=WORKERS * 2))
        self._hosts: dict[str, threading.Semaphore] = {}
        self._lock = threading.Lock()

    def _host(self, url: str) -> threading.Semaphore:
        host = urlsplit(url).netloc
        with self._lock:
            return self._hosts.setdefault(host, threading.Semaphore(PER_HOST))

    def get(self, url: str, referer: str) -> tuple[int, str, str, bytes]:
        import httpx

        with self._host(url):
            try:
                r = self.client.get(url, headers={"Referer": referer, "Accept": "*/*"})
                return r.status_code, str(r.url), r.headers.get("content-type", "").split(";")[0].strip(), r.content
            except httpx.HTTPError:
                return 0, url, "", b""

    def close(self) -> None:
        self.client.close()


def _is_css(ctype: str, url: str) -> bool:
    return "css" in ctype or urlsplit(url).path.endswith(".css")


def cmd_fetch(args) -> int:
    t0 = time.time()
    ctx = Ctx.from_args(args)
    crawl, catalog, root = ctx.crawl, ctx.catalog, ctx.root
    max_assets = getattr(args, "max_assets", 400) or 400
    pages = ctx.pages()

    # 1. discover (page files are made local in threads, parsed in processes)
    with ThreadPoolExecutor(16) as tp:
        paths = list(tp.map(lambda p: str(ctx.page_path(p["page_stem"])), pages))
    jobs = [(p["page_stem"], path, p["url"]) for p, path in zip(pages, paths)]
    with ProcessPoolExecutor() as pp:
        found = list(pp.map(_discover_file, jobs, chunksize=16))
    page_assets, uses, referer = [], Counter(), {}
    kind_of: dict[str, str] = {}
    for stem, url, refs in found:
        seen: set[str] = set()
        for u, kind in refs:
            c = canonical_url(u)
            if c in seen:  # page → asset rows hold the URL the asset is archived under (FK → assets.url)
                continue
            seen.add(c)
            page_assets.append({"crawl": crawl, "page_stem": stem, "url": c, "kind": kind})
            uses[c] += 1
            referer.setdefault(c, url)
            kind_of.setdefault(c, kind)
    t_discover = time.time() - t0

    # 2. what's already archived (a re-run only fetches what is missing)
    assets_path = f"{layout.assets_dir(catalog, crawl)}/assets.parquet"
    previous: dict[str, dict] = {}
    if root.exists(assets_path):
        for r in _read_mutable(ctx, assets_path):
            if r["sha256"] and r["status"] == 200 and root.exists(layout.asset_file(catalog, crawl, r["sha256"])):
                previous[r["url"]] = r

    # 3. fetch: stylesheets first, then icons/fonts, then images by how many pages use them
    order = {"stylesheet": 0, "style-url": 0, "font": 1, "icon": 1, "image": 2}
    queue = sorted(uses, key=lambda u: (order.get(kind_of[u], 3), -uses[u], u))
    rows: dict[str, dict] = {}
    referenced_by = {u: "page" for u in queue}
    now = manifest.now_iso()
    fetcher = Fetcher()
    stored = skipped = 0
    lock = threading.Lock()

    def one(url: str) -> list[str]:
        nonlocal stored, skipped
        prev = previous.get(url)
        if prev is not None:
            row = dict(prev)
            body = root.read_bytes(layout.asset_file(catalog, crawl, row["sha256"])) \
                if _is_css(row["content_type"] or "", row["final_url"] or url) else b""
            with lock:
                skipped += 1
        else:
            status, final, ctype, body = fetcher.get(url, referer.get(url) or referer.get(referenced_by[url], url))
            digest = hashlib.sha256(body).hexdigest() if body and status == 200 else None
            if digest:
                path = layout.asset_file(catalog, crawl, digest)
                if not root.exists(path):
                    try:
                        root.write_bytes(path, body, if_none_match=True)
                        with lock:
                            stored += 1
                    except ConflictError:
                        pass
            row = {"crawl": crawl, "url": url, "final_url": final, "status": status, "content_type": ctype,
                   "sha256": digest, "bytes": len(body), "referenced_by": None, "fetched_at": now}
        row["referenced_by"] = referenced_by[url]
        rows[url] = row
        children = []
        if row["sha256"] and _is_css(row["content_type"] or "", row["final_url"] or url):
            for ref in css_refs(body.decode("utf-8", "replace")):
                if skip_ref(ref):
                    continue
                child = canonical_url(urljoin(row["final_url"] or url, ref.strip()))
                if fetchable(child) and not _FONT_NOT_WOFF2.search(child):
                    children.append(child)
        return children

    try:
        with ThreadPoolExecutor(WORKERS) as tp:
            pending = queue[:max_assets]
            scheduled = set(pending)
            while pending:
                nxt: list[str] = []
                for url, children in zip(pending, tp.map(one, pending)):
                    for child in children:
                        if child not in scheduled and len(scheduled) < max_assets:
                            scheduled.add(child)
                            referenced_by[child] = url
                            nxt.append(child)
                pending = nxt
    finally:
        fetcher.close()
    not_fetched = max(0, len(queue) - max_assets)

    # 4. tables + manifest
    assets_rows = sorted(rows.values(), key=lambda r: r["url"])
    page_assets.sort(key=lambda r: (r["page_stem"], r["url"]))
    pa_path = f"{layout.assets_dir(catalog, crawl)}/page_assets.parquet"
    ctx.write_table(pa_path, page_assets, PAGE_ASSETS, if_none_match=False)
    ctx.write_table(assets_path, assets_rows, ASSETS, if_none_match=False)
    files_dir = f"{layout.assets_dir(catalog, crawl)}/files"

    def change(doc: dict) -> None:
        k = manifest.crawl_entry(manifest.catalog_entry(doc, catalog), crawl)
        k["assets"] = {"assets": assets_path, "page_assets": pa_path, "files": files_dir}

    manifest.update(root, change)
    ok = [r for r in assets_rows if r["sha256"]]
    total = sum(r["bytes"] for r in ok)
    msg = (f"{catalog}/{crawl}: {len(pages)} pages, {len(page_assets)} page→asset refs, {len(assets_rows)} assets "
           f"({len(ok)} archived, {len(assets_rows) - len(ok)} failed, {stored} new files, {skipped} already archived), "
           f"{total / 1e6:.1f} MB; discover {t_discover:.1f}s, total {time.time() - t0:.1f}s")
    if not_fetched:
        msg += f"; {not_fetched} URLs over --max-assets {max_assets} not fetched"
    print(msg)
    return 0


def _read_mutable(ctx: Ctx, path: str) -> list[dict]:
    """assets.parquet is rewritten by every run, so read it fresh, not through the immutable-file cache."""
    import io

    import pyarrow.parquet as pq

    return pq.read_table(io.BytesIO(ctx.root.read_bytes(path))).to_pylist()
