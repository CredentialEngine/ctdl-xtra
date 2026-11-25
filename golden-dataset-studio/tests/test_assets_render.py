"""W1: `assets fetch`, the rendered page, the HTML view, and their routes (synthetic page; real AVC data is `slow`)."""

from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pyarrow.parquet as pq
import pytest

from golden_datasets import assets, engine, layout, manifest, model, render
from golden_datasets.context import Ctx

CAT, CRAWL, STEM = "test-catalog", "2026-01-01T00-00-00Z", "page-one"
URL = "https://example.edu/catalog/course/abc101"

PAGE = """<!doctype html><html><head>
<base href="/catalog/">
<meta http-equiv="refresh" content="0;url=https://evil.example">
<link rel="stylesheet" href="styles.css?123456789">
<link rel="icon" href="favicon.ico">
<script src="app.js"></script>
<style>@import url('https://fonts.example.com/css?family=X'); .x{background:url(img/bg.png)}</style>
</head><body onload="boom()">
<script>var a = 1;</script>
<div id="app"><style>.theme{color:red} @import "theme.css";</style>
  <table><tr><td>cell</td></tr></table>
  <script>more()</script>
  <div class="introtext" style="background:url('img/dot.gif')">This course provides a general
    survey of <span>basic</span> methods.</div>
  <a href="javascript:alert(1)" onclick="x()">bad link</a>
  <a href="../other">other</a>
  <img src="logo.png?1791852215158" srcset="logo.png 1x, logo@2x.png 2x" onerror="y()">
  <img src="https://www.facebook.com/tr?id=1">
  <svg><use href="#icon"></use><script>svgjs()</script></svg>
  <iframe srcdoc="<script>x</script>" src="https://example.edu/embed"></iframe>
</div>
</body></html>"""


# --- fixtures ------------------------------------------------------------------------------------------
@pytest.fixture()
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("GOLDEN_DATASETS_CACHE", str(tmp_path / "cache"))
    render._mem.clear()
    render._indexes.clear()
    render._checked.clear()
    return tmp_path / "cache"


@pytest.fixture()
def root(tmp_path, cache) -> Path:
    folder = tmp_path / "root"
    page = folder / layout.page_html(CAT, CRAWL, STEM)
    page.parent.mkdir(parents=True)
    page.write_text(PAGE)
    ctx = Ctx(str(folder), CAT, CRAWL)
    rows = [{"crawl": CRAWL, "page_stem": STEM, "url": URL, "requested_url": URL, "http_status": 200,
             "retrieved_at": None, "bytes": len(PAGE), "sha256": None,
             "html_path": layout.page_html(CAT, CRAWL, STEM), "title": "ABC 101 - Testing"}]
    pages_path = layout.pages_parquet(CAT, CRAWL)
    ctx.write_table(pages_path, rows, model.PAGES)

    def change(doc):
        cat = manifest.catalog_entry(doc, CAT)
        k = manifest.crawl_entry(cat, CRAWL)
        k.update(pages=pages_path, page_count=1, pages_dir=layout.pages_dir(CAT, CRAWL))
        cat["current_crawl"] = CRAWL

    manifest.update(ctx.root, change)
    return folder


BODIES = {
    "https://example.edu/catalog/styles.css": ("text/css", b".s{background:url(img/s.png)} @font-face{src:"
                                                           b"url(f.woff2) format('woff2'),url(f.woff) format('woff')}"),
    "https://example.edu/catalog/img/s.png": ("image/png", b"PNG-s"),
    "https://example.edu/catalog/f.woff2": ("font/woff2", b"WOFF2"),
    "https://example.edu/catalog/favicon.ico": ("image/x-icon", b"ICO"),
    "https://fonts.example.com/css?family=X": ("text/css", b"@font-face{src:url(https://fonts.example.com/x.woff2)}"),
    "https://fonts.example.com/x.woff2": ("font/woff2", b"XW2"),
    "https://example.edu/catalog/img/bg.png": ("image/png", b"BG"),
    "https://example.edu/catalog/img/dot.gif": ("application/octet-stream", b"GIF89a"),
    "https://example.edu/catalog/logo.png": ("image/png", b"LOGO"),
    "https://example.edu/catalog/logo@2x.png": ("image/png", b"LOGO2"),
}


@pytest.fixture()
def fetched(root, monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_get(self, url, referer):
        calls.append((url, referer))
        if url in BODIES:
            ctype, body = BODIES[url]
            return 200, url, ctype, body
        return 404, url, "text/html", b"nope"

    monkeypatch.setattr(assets.Fetcher, "get", fake_get)
    assets.cmd_fetch(SimpleNamespace(root=str(root), catalog=CAT, crawl=CRAWL, max_assets=400))
    return calls


def _ctx(root) -> Ctx:
    return Ctx(str(root), CAT, CRAWL)


# --- assets --------------------------------------------------------------------------------------------
def test_canonical_url_drops_numeric_cache_busters_only():
    assert assets.canonical_url("https://a.b/x.png?1791852215158") == "https://a.b/x.png"
    assert assets.canonical_url("https://a.b/css?family=X#y") == "https://a.b/css?family=X"
    assert assets.canonical_url("https://a.b/x.css?v=3") == "https://a.b/x.css?v=3"


def test_discover_finds_page_assets():
    found = dict(assets.discover(PAGE.encode(), URL))
    assert found["https://example.edu/catalog/styles.css?123456789"] == "stylesheet"
    assert found["https://example.edu/catalog/favicon.ico"] == "icon"
    assert found["https://fonts.example.com/css?family=X"] == "style-url"
    assert found["https://example.edu/catalog/theme.css"] == "style-url"     # a <style> inside <body>
    assert found["https://example.edu/catalog/img/dot.gif"] == "style-url"   # style= attribute
    assert found["https://example.edu/catalog/logo@2x.png"] == "image"
    assert not any("facebook" in u for u in found)   # trackers are skipped
    assert not any(u.endswith(".js") for u in found)  # scripts are never fetched


def test_fetch_archives_by_hash_and_registers(root, fetched):
    ctx = _ctx(root)
    fetched_urls = [u for u, _ in fetched]
    assert len(fetched_urls) == len(set(fetched_urls))                       # each URL once
    assert "https://example.edu/catalog/f.woff" not in fetched_urls          # fonts: woff2 only
    assert "https://example.edu/catalog/f.woff2" in fetched_urls             # followed from CSS
    assert "https://fonts.example.com/x.woff2" in fetched_urls               # through @import
    assert "https://example.edu/catalog/logo.png" in fetched_urls            # cache-buster collapsed
    assert dict(fetched)["https://example.edu/catalog/styles.css"] == URL    # Referer = the page
    k = ctx.crawl_entry()["assets"]
    assert k == {"assets": f"{layout.assets_dir(CAT, CRAWL)}/assets.parquet",
                 "page_assets": f"{layout.assets_dir(CAT, CRAWL)}/page_assets.parquet",
                 "files": f"{layout.assets_dir(CAT, CRAWL)}/files"}
    rows = {r["url"]: r for r in pq.read_table(root / k["assets"]).to_pylist()}
    css = rows["https://example.edu/catalog/styles.css"]
    assert css["sha256"] == hashlib.sha256(BODIES[css["url"]][1]).hexdigest()
    assert (root / layout.asset_file(CAT, CRAWL, css["sha256"])).read_bytes() == BODIES[css["url"]][1]
    assert rows["https://example.edu/catalog/img/s.png"]["referenced_by"] == "https://example.edu/catalog/styles.css"
    assert rows["https://example.edu/catalog/theme.css"]["status"] == 404 and rows[
        "https://example.edu/catalog/theme.css"]["sha256"] is None
    pa_rows = pq.read_table(root / k["page_assets"]).to_pylist()
    assert {r["page_stem"] for r in pa_rows} == {STEM}
    assert pq.read_table(root / k["page_assets"]).schema.equals(model.PAGE_ASSETS)


def test_fetch_rerun_fetches_only_what_is_missing(root, fetched, monkeypatch):
    render._checked.clear()
    again: list[str] = []
    monkeypatch.setattr(assets.Fetcher, "get", lambda self, url, ref: (again.append(url), (404, url, "", b""))[1])
    assets.cmd_fetch(SimpleNamespace(root=str(root), catalog=CAT, crawl=CRAWL, max_assets=400))
    assert again == ["https://example.edu/catalog/theme.css"]  # only the one that failed before


# --- render --------------------------------------------------------------------------------------------
def _paths_and_text(doc) -> list[tuple[str, str]]:
    paths = engine.Paths()
    body = doc.find("body")
    return [(paths(el), el.tag) for el in body.iter() if isinstance(el.tag, str) and el.tag != "script"]


def test_render_strips_scripts_and_keeps_every_body_path(root, fetched):
    ctx = _ctx(root)
    out = render.render_html(PAGE.encode(), URL, render.Rewriter(render.asset_index(ctx), "/api/catalogs/c/assets"),
                             pane_css=".accordionheader{height:auto!important}")
    assert "<script" not in out.lower()
    assert not re.search(r"\son[a-z]+=", out)
    assert "javascript:" not in out
    assert "srcdoc" not in out
    assert "http-equiv" not in out
    # the engine's css paths of every (non-script) body element are unchanged
    assert _paths_and_text(engine.parse(out)) == _paths_and_text(engine.parse(PAGE))
    # stylesheets and <style> stay where they are; pane_css and highlight styles end the <head>
    doc = engine.parse(out)
    head_styles = doc.find("head").findall("style")
    assert [s.get("id") for s in head_styles[-2:]] == ["gds-pane-css", "gds-highlight-css"]
    assert engine.select_one(doc, "#app > style") is not None
    # implied <tbody> is serialized, so the browser and the engine agree
    assert engine.select_one(doc, "table > tbody > tr > td") is not None
    # base keeps no href (archive URLs are root-relative)
    assert doc.find("head").find("base").get("href") is None


def test_render_rewrites_urls_to_archive_or_live(root, fetched):
    ctx = _ctx(root)
    idx = render.asset_index(ctx)
    out = render.render_html(PAGE.encode(), URL, render.Rewriter(idx, "/api/catalogs/c/assets"))
    sha = idx.by_url["https://example.edu/catalog/styles.css"]
    assert f'href="/api/catalogs/c/assets/{sha}"' in out                    # cache-busted URL found its archive copy
    assert f"/api/catalogs/c/assets/{idx.by_url['https://fonts.example.com/css?family=X']}" in out  # @import in <style>
    assert f"/api/catalogs/c/assets/{idx.by_url['https://example.edu/catalog/img/dot.gif']}" in out  # style=
    assert "https://example.edu/catalog/theme.css" in out                   # not archived: the live URL
    assert 'href="https://example.edu/other"' in out                        # links: absolute live URLs
    assert 'href="#icon"' in out                                             # fragments untouched
    logo2 = idx.by_url["https://example.edu/catalog/logo@2x.png"]
    assert f"/api/catalogs/c/assets/{logo2} 2x" in out                       # srcset


def test_rendered_is_cached_on_disk(root, fetched, cache):
    ctx = _ctx(root)
    a = render.rendered(ctx, STEM, URL, ".x{}")
    assert a.path.is_relative_to(cache / "rendered")
    render._mem.clear()
    mtime = a.path.stat().st_mtime_ns
    b = render.rendered(ctx, STEM, URL, ".x{}")
    assert b.path == a.path and b.etag == a.etag and b.path.stat().st_mtime_ns == mtime
    c = render.rendered(ctx, STEM, URL, ".y{}")
    assert c.path != a.path and c.etag != a.etag
    import gzip

    assert gzip.decompress(a.gz_path.read_bytes()) == a.path.read_bytes()


# --- HTML view -----------------------------------------------------------------------------------------
def test_source_view_marks_element_and_range():
    doc = engine.parse(PAGE)
    el = engine.select_one(doc, ".introtext")
    path = engine.Paths()(el)
    tc = engine.text_content(el)
    s = tc.index("general")
    out = render.source_view(PAGE.encode(), path, s, s + 7)
    assert out["found"] and out["text"] == "general"
    lines = out["lines"]
    e0, e1 = out["element"]
    assert lines[e0].lstrip().startswith('<div class="introtext"')
    assert "</div>" in lines[e1]
    (m,) = out["marks"]
    assert lines[m["line"]][m["start"]:m["end"]] == "general"
    assert not any(ch in "".join(lines) for ch in "")


def test_source_view_falls_back_to_text_search_and_spans_lines():
    doc = engine.parse(PAGE)
    path = engine.Paths()(engine.select_one(doc, ".introtext"))
    out = render.source_view(PAGE.encode(), path, 900, 950, text="general survey")
    assert out["text"].split() == ["general", "survey"]
    assert [out["lines"][m["line"]][m["start"]:m["end"]].strip() for m in out["marks"]] == ["general", "survey"]


def test_source_view_unknown_path():
    out = render.source_view(PAGE.encode(), "html > body:nth-of-type(1) > nav:nth-of-type(3)")
    assert out["found"] is False and out["element"] is None and out["lines"]


def test_resolve_path_matches_engine_paths():
    doc = engine.parse(PAGE)
    paths = engine.Paths()
    for el in doc.iter():
        if isinstance(el.tag, str):
            assert render.resolve_path(doc, paths(el)) is el


# --- routes --------------------------------------------------------------------------------------------
@pytest.fixture()
def client(root, fetched):
    from fastapi.testclient import TestClient

    from golden_datasets.server.app import create_app

    return TestClient(create_app(str(root)))


def test_render_route(client):
    r = client.get(f"/api/catalogs/{CAT}/pages/{STEM}/render")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "script-src 'none'" in r.headers["content-security-policy"]
    assert "<script" not in r.text and f"/api/catalogs/{CAT}/assets/" in r.text
    etag = r.headers["etag"]
    assert client.get(f"/api/catalogs/{CAT}/pages/{STEM}/render", headers={"If-None-Match": etag}).status_code == 304
    assert client.get(f"/api/catalogs/{CAT}/pages/nope/render").status_code == 404
    assert client.get(f"/api/catalogs/{CAT}/pages/{STEM}/render?ruleset=3").status_code == 404


def test_meta_and_source_routes(client):
    assert client.get(f"/api/catalogs/{CAT}/pages/{STEM}/meta").json() == {
        "stem": STEM, "url": URL, "title": "ABC 101 - Testing"}
    path = engine.Paths()(engine.select_one(engine.parse(PAGE), "span"))
    r = client.get(f"/api/catalogs/{CAT}/pages/{STEM}/source", params={"css_path": path, "text": "basic"})
    j = r.json()
    assert j["found"] and j["text"] == "basic" and j["marks"]


def test_asset_route(client, root):
    k = json.loads((root / manifest.PATH).read_text())["catalogs"][0]["crawls"][0]["assets"]
    rows = {r["url"]: r for r in pq.read_table(io.BytesIO((root / k["assets"]).read_bytes())).to_pylist()}
    gif = rows["https://example.edu/catalog/img/dot.gif"]["sha256"]
    r = client.get(f"/api/catalogs/{CAT}/assets/{gif}")
    assert r.status_code == 200 and r.content == b"GIF89a"
    assert r.headers["content-type"] == "image/gif"            # octet-stream → guessed from the URL
    assert "immutable" in r.headers["cache-control"]
    css = rows["https://example.edu/catalog/styles.css"]["sha256"]
    body = client.get(f"/api/catalogs/{CAT}/assets/{css}").text
    png = rows["https://example.edu/catalog/img/s.png"]["sha256"]
    assert f"/api/catalogs/{CAT}/assets/{png}" in body          # url() inside archived CSS → archive
    assert "https://example.edu/catalog/f.woff" in body          # not archived → live, absolute
    assert client.get(f"/api/catalogs/{CAT}/assets/{'0' * 64}").status_code == 404
    assert client.get(f"/api/catalogs/{CAT}/assets/zz").status_code == 404


# --- real data -----------------------------------------------------------------------------------------
REAL_ROOT = Path(__file__).resolve().parents[1] / ".data" / "root"
GEOG = "avc-elumenapp-com-catalog-2026-27-course-geog222-c85465e9c2"


@pytest.mark.slow
def test_avc_render_fast_and_paths_unchanged(cache):
    if not (REAL_ROOT / manifest.PATH).exists():
        pytest.skip("no local root at .data/root")
    import time

    ctx = Ctx(str(REAL_ROOT), "avc")
    url = next(p["url"] for p in ctx.pages() if p["page_stem"] == GEOG)
    t = time.perf_counter()
    r = render.rendered(ctx, GEOG, url, None)
    cold = time.perf_counter() - t
    render._mem.clear()
    t = time.perf_counter()
    render.rendered(ctx, GEOG, url, None).path.read_bytes()
    warm = time.perf_counter() - t
    assert cold < 1.0 and warm < 0.05
    out = r.path.read_text()
    assert "<script" not in out
    assert _paths_and_text(engine.parse(out)) == _paths_and_text(engine.parse(ctx.page_path(GEOG).read_bytes()))
