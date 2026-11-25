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
from dataclasses import dataclass, field
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


#: Fetch order: stylesheets first, then icons and fonts, then images (by how many pages use them).
_KIND_ORDER = {"stylesheet": 0, "style-url": 0, "font": 1, "icon": 1, "image": 2}


def cmd_fetch(args) -> int:
    t0 = time.time()
    ctx = Ctx.from_args(args)
    max_assets = getattr(args, "max_assets", 400) or 400
    pages = ctx.pages()
    refs = _discover_pages(ctx, pages)
    t_discover = time.time() - t0
    run = _AssetFetch(ctx, refs, _archived_assets(ctx), max_assets)
    run.fetch_all()
    assets_rows = _write_tables(ctx, refs.page_assets, run.rows)
    print(_summary(ctx, pages, refs, assets_rows, run) + f"; discover {t_discover:.1f}s, total "
          f"{time.time() - t0:.1f}s" + run.over_cap_note())
    return 0


@dataclass
class _PageRefs:
    """What the pages reference: page → asset rows, and per asset URL its use count, first referer and kind."""
    page_assets: list[dict] = field(default_factory=list)
    uses: Counter = field(default_factory=Counter)
    referer: dict[str, str] = field(default_factory=dict)
    kind_of: dict[str, str] = field(default_factory=dict)

    def add(self, crawl: str, stem: str, page_url: str, url: str, kind: str) -> None:
        self.page_assets.append({"crawl": crawl, "page_stem": stem, "url": url, "kind": kind})
        self.uses[url] += 1
        self.referer.setdefault(url, page_url)
        self.kind_of.setdefault(url, kind)


def _discover_pages(ctx: Ctx, pages: list[dict]) -> _PageRefs:
    """Page files are made local in threads, parsed in processes."""
    with ThreadPoolExecutor(16) as tp:
        paths = list(tp.map(lambda p: str(ctx.page_path(p["page_stem"])), pages))
    jobs = [(p["page_stem"], path, p["url"]) for p, path in zip(pages, paths)]
    with ProcessPoolExecutor() as pp:
        found = list(pp.map(_discover_file, jobs, chunksize=16))
    return _collect_refs(ctx.crawl, found)


def _archived_assets(ctx: Ctx) -> dict[str, dict]:
    """What's already archived, by URL (a re-run only fetches what is missing)."""
    assets_path = _assets_table_path(ctx)
    if not ctx.root.exists(assets_path):
        return {}
    return {r["url"]: r for r in _read_mutable(ctx, assets_path)
            if r["sha256"] and r["status"] == 200
            and ctx.root.exists(layout.asset_file(ctx.catalog, ctx.crawl, r["sha256"]))}


class _AssetFetch:
    """One run of fetches: each asset once (or reused from the archive), then what fetched CSS references."""

    def __init__(self, ctx: Ctx, refs: _PageRefs, previous: dict[str, dict], max_assets: int):
        self.ctx, self.refs, self.previous, self.max_assets = ctx, refs, previous, max_assets
        self.queue = sorted(refs.uses, key=lambda u: (_KIND_ORDER.get(refs.kind_of[u], 3), -refs.uses[u], u))
        self.rows: dict[str, dict] = {}
        self.referenced_by = {u: "page" for u in self.queue}
        self.now = manifest.now_iso()
        self.fetcher = Fetcher()
        self.stored = self.skipped = 0
        self.lock = threading.Lock()

    def fetch_all(self) -> None:
        try:
            with ThreadPoolExecutor(WORKERS) as tp:
                pending = self.queue[:self.max_assets]
                scheduled = set(pending)
                while pending:
                    pending = self._schedule_children(pending, tp.map(self.fetch_one, pending), scheduled)
        finally:
            self.fetcher.close()
        self._add_unfetched_rows()

    def fetch_one(self, url: str) -> list[str]:
        """The asset's row; returns the URLs its CSS references."""
        prev = self.previous.get(url)
        row, body = self._reuse(prev, url) if prev is not None else self._download(url)
        row["referenced_by"] = self.referenced_by[url]
        self.rows[url] = row
        if not (row["sha256"] and _is_css(row["content_type"] or "", row["final_url"] or url)):
            return []
        return _css_children(body, row["final_url"] or url)

    def over_cap_note(self) -> str:
        not_fetched = max(0, len(self.queue) - self.max_assets)
        return f"; {not_fetched} URLs over --max-assets {self.max_assets} not fetched" if not_fetched else ""

    def _schedule_children(self, pending: list[str], results, scheduled: set[str]) -> list[str]:
        nxt: list[str] = []
        for url, children in zip(pending, results):
            for child in children:
                if child not in scheduled and len(scheduled) < self.max_assets:
                    scheduled.add(child)
                    self.referenced_by[child] = url
                    nxt.append(child)
        return nxt

    def _add_unfetched_rows(self) -> None:
        """URLs over the cap still get a row (status 0, no file): page_assets.url → assets.url holds, and the page
        pane uses the live URL for them (spec §9: "if something isn't archived, the live URL is used")."""
        for url in self.queue:
            if url not in self.rows:
                self.rows[url] = {"crawl": self.ctx.crawl, "url": url, "final_url": None, "status": 0,
                                  "content_type": None, "sha256": None, "bytes": 0,
                                  "referenced_by": "page (not fetched: over --max-assets)", "fetched_at": None}

    def _reuse(self, prev: dict, url: str) -> tuple[dict, bytes]:
        row = dict(prev)
        body = self.ctx.root.read_bytes(layout.asset_file(self.ctx.catalog, self.ctx.crawl, row["sha256"])) \
            if _is_css(row["content_type"] or "", row["final_url"] or url) else b""
        with self.lock:
            self.skipped += 1
        return row, body

    def _download(self, url: str) -> tuple[dict, bytes]:
        referer = self.refs.referer
        status, final, ctype, body = self.fetcher.get(url, referer.get(url) or referer.get(self.referenced_by[url], url))
        digest = hashlib.sha256(body).hexdigest() if body and status == 200 else None
        if digest:
            self._store(digest, body)
        row = {"crawl": self.ctx.crawl, "url": url, "final_url": final, "status": status, "content_type": ctype,
               "sha256": digest, "bytes": len(body), "referenced_by": None, "fetched_at": self.now}
        return row, body

    def _store(self, digest: str, body: bytes) -> None:
        path = layout.asset_file(self.ctx.catalog, self.ctx.crawl, digest)
        if self.ctx.root.exists(path):
            return
        try:
            self.ctx.root.write_bytes(path, body, if_none_match=True)
            with self.lock:
                self.stored += 1
        except ConflictError:
            pass


def _write_tables(ctx: Ctx, page_assets: list[dict], rows: dict[str, dict]) -> list[dict]:
    """Both tables, and the manifest naming them; returns the assets rows."""
    assets_rows = sorted(rows.values(), key=lambda r: r["url"])
    page_assets.sort(key=lambda r: (r["page_stem"], r["url"]))
    assets_dir = layout.assets_dir(ctx.catalog, ctx.crawl)
    pa_path, assets_path = f"{assets_dir}/page_assets.parquet", _assets_table_path(ctx)
    ctx.write_table(pa_path, page_assets, PAGE_ASSETS, if_none_match=False)
    ctx.write_table(assets_path, assets_rows, ASSETS, if_none_match=False)

    def change(doc: dict) -> None:
        k = manifest.crawl_entry(manifest.catalog_entry(doc, ctx.catalog), ctx.crawl)
        k["assets"] = {"assets": assets_path, "page_assets": pa_path, "files": f"{assets_dir}/files"}

    manifest.update(ctx.root, change)
    return assets_rows


def _summary(ctx: Ctx, pages: list[dict], refs: _PageRefs, assets_rows: list[dict], run: _AssetFetch) -> str:
    ok = [r for r in assets_rows if r["sha256"]]
    total = sum(r["bytes"] for r in ok)
    failed = sum(1 for r in assets_rows if not r["sha256"] and r["fetched_at"])
    return (f"{ctx.catalog}/{ctx.crawl}: {len(pages)} pages, {len(refs.page_assets)} page→asset refs, "
            f"{len(assets_rows)} assets ({len(ok)} archived, {failed} failed, {run.stored} new files, "
            f"{run.skipped} already archived), {total / 1e6:.1f} MB")


def _collect_refs(crawl: str, found: list[tuple[str, str, list[tuple[str, str]]]]) -> _PageRefs:
    refs = _PageRefs()
    for stem, page_url, page_refs in found:
        seen: set[str] = set()
        for u, kind in page_refs:
            c = canonical_url(u)
            if c not in seen:  # page → asset rows hold the URL the asset is archived under (FK → assets.url)
                seen.add(c)
                refs.add(crawl, stem, page_url, c, kind)
    return refs


def _css_children(body: bytes, base: str) -> list[str]:
    """The assets a stylesheet references (fonts: woff2 only)."""
    children = []
    for ref in css_refs(body.decode("utf-8", "replace")):
        if skip_ref(ref):
            continue
        child = canonical_url(urljoin(base, ref.strip()))
        if fetchable(child) and not _FONT_NOT_WOFF2.search(child):
            children.append(child)
    return children


def _assets_table_path(ctx: Ctx) -> str:
    return f"{layout.assets_dir(ctx.catalog, ctx.crawl)}/assets.parquet"


def _read_mutable(ctx: Ctx, path: str) -> list[dict]:
    """assets.parquet is rewritten by every run, so read it fresh, not through the immutable-file cache."""
    import io

    import pyarrow.parquet as pq

    return pq.read_table(io.BytesIO(ctx.root.read_bytes(path))).to_pylist()


def _is_css(ctype: str, url: str) -> bool:
    return "css" in ctype or urlsplit(url).path.endswith(".css")


# --- discovery (runs in worker processes) ------------------------------------------------------------
def _discover_file(job: tuple[str, str, str]) -> tuple[str, str, list[tuple[str, str]]]:
    stem, path, url = job
    with open(path, "rb") as fh:
        return stem, url, discover(fh.read(), url)


def discover(html: bytes, url: str) -> list[tuple[str, str]]:
    """(absolute url, kind) for every asset one page references, in document order, without duplicates."""
    import lxml.html

    doc = lxml.html.document_fromstring(html, parser=lxml.html.HTMLParser(encoding="utf-8"))  # saved as UTF-8
    base = page_base(doc, url)
    found = [(urljoin(base, ref.strip()), kind) for ref, kind in _asset_refs(doc)
             if ref is not None and not skip_ref(ref)]
    return _unique_fetchable(found)


def _asset_refs(doc):
    """(reference as written, kind), in document order: links, then styles, then images."""
    yield from _link_refs(doc)
    yield from _style_refs(doc)
    yield from _image_refs(doc)


def _unique_fetchable(found: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    uniq = []
    for u, k in found:
        if u not in seen and fetchable(u):
            seen.add(u)
            uniq.append((u, k))
    return uniq


def _link_refs(doc):
    for link in doc.iter("link"):
        rel = f" {(link.get('rel') or '').lower()} "
        href = link.get("href")
        if " stylesheet " in rel:
            yield href, "stylesheet"
        elif "icon" in rel:
            yield href, "icon"
        elif " preload " in rel and (link.get("as") or "").lower() in ("style", "font"):
            yield href, "stylesheet" if link.get("as") == "style" else "font"


def _style_refs(doc):
    for style in doc.iter("style"):
        for ref in css_refs(style.text or ""):
            yield ref, "style-url"
    for el in doc.xpath("//*[@style]"):
        for ref in css_refs(el.get("style") or ""):
            yield ref, "style-url"


def _image_refs(doc):
    for el in doc.iter("img", "source", "video", "input"):
        if el.tag in ("img", "input"):
            yield el.get("src"), "image"
        if el.tag == "video":
            yield el.get("poster"), "image"
        for ref in srcset_urls(el.get("srcset") or ""):
            yield ref, "image"


# --- fetching ----------------------------------------------------------------------------------------
class Fetcher:
    def __init__(self):
        import httpx

        self.client = httpx.Client(follow_redirects=True, timeout=30, headers={"User-Agent": USER_AGENT},
                                   limits=httpx.Limits(max_connections=WORKERS * 2))
        self._hosts: dict[str, threading.Semaphore] = {}
        self._lock = threading.Lock()

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

    def _host(self, url: str) -> threading.Semaphore:
        host = urlsplit(url).netloc
        with self._lock:
            return self._hosts.setdefault(host, threading.Semaphore(PER_HOST))


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
