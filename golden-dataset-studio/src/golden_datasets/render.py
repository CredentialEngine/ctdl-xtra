"""The saved page as the page pane shows it (spec §9), and the markup window of the HTML view (spec §7.7).

`rendered(ctx, stem, pane_css)` parses the saved page with `engine.parse` and serializes **that** tree, so the
browser builds the same structure the engine computed its document-root css paths on. Then:

- `<script>` elements, every `on*` attribute, `srcdoc` and every `javascript:` URL are removed; `<meta http-equiv>`
  in `<head>` too;
- every stylesheet and `<style>` stays where it is (AVC's theme is a `<style>` inside `<body>`);
- asset URLs (attributes, `style=`, `<style>` text) are rewritten to `/api/catalogs/<catalog>/assets/<sha256>` when
  archived by `assets fetch`, else to the absolute live URL; links become absolute live URLs, and `<base>` loses its
  `href` (it would send the root-relative archive URLs to the live site);
- `pane_css` and the highlight styles are appended at the end of `<head>`.

Nothing inside `<body>` is added, removed or reordered except `<script>` elements, so no `tag:nth-of-type(n)` step of
another element changes and the engine's paths keep resolving. The result is cached on disk under
`cache_home()/rendered/`, keyed by root, catalog, crawl, stem, the pane_css hash and the asset index's version.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import os
import re
import tempfile
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin

import lxml.html
from lxml import etree

from . import engine
from .assets import CSS_URL, canonical_url, skip_ref
from .context import Ctx
from .errors import UserError
from .storage import cache_home

RENDER_VERSION = "r3"  # bump when the output of `render_html` changes

# Highlight styles the page pane relies on. Ranges use the CSS Custom Highlight API (no DOM change); outlines and
# badges live in an overlay `<div id="gds-overlay">` the pane appends as the last child of <html> (not of <body>).
HIGHLIGHT_CSS = """
html{scroll-behavior:auto!important}
noscript{display:none!important}
::highlight(gds-value){background-color:rgba(253,224,120,.92);color:#111}
::highlight(gds-expected){background-color:rgba(190,242,214,.95);color:#111}
::highlight(gds-mark){background-color:#ffe4ea;color:#9f1239;text-decoration:underline wavy #e11d48}
::selection{background:rgba(190,242,214,.95)}
#gds-overlay{position:absolute!important;left:0!important;top:0!important;width:0!important;height:0!important;
  overflow:visible!important;z-index:2147483646!important;pointer-events:none!important;margin:0!important;
  padding:0!important;border:0!important;display:block!important}
#gds-overlay .gds-box,#gds-overlay .gds-badge,#gds-overlay .gds-fill{margin:0;padding:0;border:0;background:none;
  opacity:1;transform:none;float:none;display:block}
#gds-overlay .gds-box{position:absolute;box-sizing:border-box;border-radius:3px;pointer-events:none}
#gds-overlay .gds-box.gds-value{box-shadow:0 0 0 1.5px rgba(245,165,36,.9)}
#gds-overlay .gds-box.gds-value.gds-whole{box-shadow:0 0 0 2.5px rgba(245,165,36,.95);background:rgba(253,224,120,.18)}
#gds-overlay .gds-box.gds-expected{box-shadow:0 0 0 2px #12805c}
#gds-overlay .gds-box.gds-block{box-shadow:0 0 0 1.5px rgba(47,84,235,.55)}
#gds-overlay .gds-box.gds-block.gds-focus{box-shadow:0 0 0 2.5px #2f54eb;background:rgba(47,84,235,.06)}
#gds-overlay .gds-box.gds-mark{box-shadow:0 0 0 2px #e11d48}
#gds-overlay .gds-badge{position:absolute;min-width:19px;height:19px;border-radius:10px;background:#f5a524;
  color:#fff;font:700 11px/19px Inter,Arial,sans-serif;text-align:center;padding:0 5px;box-sizing:border-box;
  box-shadow:0 1px 2px rgba(0,0,0,.25);letter-spacing:0;text-transform:none;white-space:nowrap}
#gds-overlay .gds-badge::before{content:attr(data-n)}
#gds-overlay .gds-badge.gds-expected{background:#12805c}
#gds-overlay .gds-badge.gds-block{background:#2f54eb;min-width:16px;height:16px;font-size:9.5px;line-height:16px;padding:0 4px}
#gds-overlay .gds-badge.gds-mark{background:#e11d48}
"""

_JS_URL = re.compile(r"^[\x00-\x20]*j[\s]*a[\s]*v[\s]*a[\s]*s[\s]*c[\s]*r[\s]*i[\s]*p[\s]*t[\s]*:", re.I)
_URL_ATTRS = ("src", "href", "poster", "action", "formaction", "background", "xlink:href", "data")
_ASSET_TAGS = {"img", "source", "video", "input", "link", "image", "use", "audio", "track", "embed"}


# --- the asset index ---------------------------------------------------------------------------------
@dataclass
class AssetIndex:
    version: str = "none"
    by_url: dict[str, str] = field(default_factory=dict)          # canonical url -> sha256
    by_sha: dict[str, dict] = field(default_factory=dict)         # sha256 -> {content_type, final_url}


_index_lock = threading.Lock()
_indexes: dict[tuple, AssetIndex] = {}


INDEX_TTL = 10.0  # seconds between checks of the manifest and assets.parquet's ETag (each is a round trip on Azure)
_checked: dict[tuple, tuple[float, AssetIndex]] = {}


def asset_index(ctx: Ctx) -> AssetIndex:
    """The crawl's archived assets, re-read only when assets.parquet changes (it is rewritten by every fetch)."""
    ck = (ctx.root.uri, ctx.catalog, ctx.crawl)
    now = time.monotonic()
    with _index_lock:
        hit = _checked.get(ck)
        if hit is not None and now - hit[0] < INDEX_TTL:
            return hit[1]
    idx = _load_index(ctx)
    with _index_lock:
        _checked[ck] = (now, idx)
    return idx


def _load_index(ctx: Ctx) -> AssetIndex:
    try:
        entry = ctx.crawl_entry().get("assets") or {}
    except Exception:  # noqa: BLE001 - an unregistered crawl simply has no archive
        entry = {}
    path = entry.get("assets")
    st = ctx.root.stat(path) if path else None
    if st is None:
        return AssetIndex()
    key = (ctx.root.uri, ctx.catalog, ctx.crawl, path)
    with _index_lock:
        got = _indexes.get(key)
        if got is not None and got.version == st.etag:
            return got
    import pyarrow.parquet as pq

    idx = AssetIndex(version=st.etag)
    for r in pq.read_table(io.BytesIO(ctx.root.read_bytes(path))).to_pylist():
        if not r["sha256"]:
            continue
        idx.by_url[r["url"]] = r["sha256"]
        idx.by_url.setdefault(canonical_url(r["final_url"] or r["url"]), r["sha256"])
        idx.by_sha[r["sha256"]] = {"content_type": r["content_type"], "final_url": r["final_url"] or r["url"]}
    with _index_lock:
        _indexes[key] = idx
    return idx


class Rewriter:
    """Maps a reference found at `base` to the archive (`prefix/<sha>`) or to its absolute live URL."""

    def __init__(self, index: AssetIndex, prefix: str):
        self.index, self.prefix = index, prefix.rstrip("/")

    def url(self, ref: str, base: str, archive: bool = True) -> str:
        if skip_ref(ref):
            return ref
        absolute = urljoin(base, ref.strip())
        if archive:
            sha = self.index.by_url.get(canonical_url(absolute))
            if sha:
                return f"{self.prefix}/{sha}"
        return absolute

    def css(self, css: str, base: str) -> str:
        def sub(m: re.Match) -> str:
            if m.group("u") is not None and m.group(0).startswith("url"):
                ref = m.group("u")
                if skip_ref(ref):
                    return m.group(0)
                return f'url("{self.url(ref, base)}")'
            ref = m.group("u2")
            if skip_ref(ref):
                return m.group(0)
            return f'@import "{self.url(ref, base)}"'

        return CSS_URL.sub(sub, css)

    def srcset(self, value: str, base: str) -> str:
        out = []
        for part in value.split(","):
            bits = part.strip().split(None, 1)
            if not bits:
                continue
            bits[0] = self.url(bits[0], base)
            out.append(" ".join(bits))
        return ", ".join(out)


# --- rendering ---------------------------------------------------------------------------------------
def render_html(html: bytes, url: str, rewriter: Rewriter, pane_css: str | None = None) -> str:
    doc = engine.parse(html)
    head = doc.find("head")
    if head is None:  # libxml2 always makes one for a full document, but be safe: head is outside <body>
        head = etree.Element("head")
        doc.insert(0, head)
    bases = doc.xpath("//base[@href]")
    base = urljoin(url, bases[0].get("href").strip()) if bases else url

    for script in list(doc.iter("script")):
        script.drop_tree()  # keeps its tail text, so text nodes around it merge as in the browser
    for meta in head.xpath(".//meta[@http-equiv]"):
        meta.drop_tree()

    for el in doc.iter():
        tag = el.tag
        if not isinstance(tag, str):
            continue
        attrib = el.attrib
        if not attrib:
            if tag == "style" and el.text:
                el.text = rewriter.css(el.text, base)
            continue
        for name in list(attrib):
            low = name.lower()
            value = attrib[name]
            if low.startswith("on") or low == "srcdoc":
                del attrib[name]
            elif _JS_URL.match(value):
                del attrib[name]
            elif low in _URL_ATTRS:
                if tag == "base":
                    del attrib[name]  # every URL is absolute now, and archive URLs are root-relative
                elif tag in _ASSET_TAGS or low in ("src", "poster", "background"):
                    attrib[name] = rewriter.url(value, base)
                else:  # links, form actions: the live URL
                    attrib[name] = rewriter.url(value, base, archive=False)
            elif low in ("srcset", "imagesrcset"):
                attrib[name] = rewriter.srcset(value, base)
            elif low == "style" and "url(" in value:
                attrib[name] = rewriter.css(value, base)
        if tag == "style" and el.text:
            el.text = rewriter.css(el.text, base)

    for css, ident in ((pane_css, "gds-pane-css"), (HIGHLIGHT_CSS, "gds-highlight-css")):
        if css:
            style = etree.SubElement(head, "style")
            style.set("id", ident)
            style.text = css
    return lxml.html.tostring(doc, encoding="unicode", doctype="<!DOCTYPE html>")


def pane_css_for(ctx: Ctx, ruleset: int | None) -> str | None:
    """`settings.pane_css` of that ruleset (default: the latest); None when the catalog has no ruleset yet."""
    versions = ctx.ruleset_versions()
    if ruleset is not None and ruleset not in versions:
        raise UserError(f"{ctx.catalog}: no ruleset v{ruleset}")
    if not versions:
        return None
    v = ruleset if ruleset is not None else versions[-1]
    return (ctx.ruleset(v).get("settings") or {}).get("pane_css") or None


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


@dataclass
class Rendered:
    path: Path        # the HTML on disk
    gz_path: Path     # the same, gzip-compressed
    etag: str         # strong: a hash of the inputs, which determine the bytes


_mem_lock = threading.Lock()
_mem: OrderedDict[str, Rendered] = OrderedDict()


def asset_prefix(catalog: str) -> str:
    return f"/api/catalogs/{catalog}/assets"


def rendered(ctx: Ctx, stem: str, url: str, pane_css: str | None = None) -> Rendered:
    """The rendered page, from the disk cache or made now (and cached)."""
    index = asset_index(ctx)
    key = _h("\0".join([RENDER_VERSION, ctx.root.uri, ctx.catalog, ctx.crawl, stem, _h(pane_css or ""),
                        index.version]))
    with _mem_lock:
        got = _mem.get(key)
        if got is not None:
            _mem.move_to_end(key)
            return got
    folder = cache_home() / "rendered" / _h(ctx.root.uri)[:16] / ctx.catalog / ctx.crawl
    path = folder / f"{stem}.{key[:20]}.html"
    gz_path = path.with_suffix(".html.gz")
    if not (path.exists() and gz_path.exists()):
        html = ctx.page_path(stem).read_bytes()
        text = render_html(html, url, Rewriter(index, asset_prefix(ctx.catalog)), pane_css).encode("utf-8")
        folder.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, text)
        _atomic_write(gz_path, gzip.compress(text, compresslevel=5))
    out = Rendered(path=path, gz_path=gz_path, etag=f'"{key[:32]}"')
    with _mem_lock:
        _mem[key] = out
        while len(_mem) > 2048:
            _mem.popitem(last=False)
    return out


def _atomic_write(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def asset_css(ctx: Ctx, sha: str, body: bytes) -> bytes:
    """An archived CSS file with its `url()` / `@import` rewritten against its own URL (cached on disk)."""
    index = asset_index(ctx)
    meta = index.by_sha.get(sha) or {}
    key = _h("\0".join([RENDER_VERSION, ctx.root.uri, ctx.catalog, ctx.crawl, sha, index.version]))
    path = cache_home() / "rendered" / _h(ctx.root.uri)[:16] / ctx.catalog / ctx.crawl / "css" / f"{key[:32]}.css"
    if path.exists():
        return path.read_bytes()
    css = body.decode("utf-8", "replace")
    out = Rewriter(index, asset_prefix(ctx.catalog)).css(css, meta.get("final_url") or "").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, out)
    return out


# --- the HTML view -----------------------------------------------------------------------------------
_STEP = re.compile(r"^\s*([a-zA-Z][\w:-]*)(?::nth-of-type\((\d+)\))?\s*$")
_M_EL0, _M_EL1, _M_R0, _M_R1 = "\ue000", "\ue001", "\ue002", "\ue003"  # private-use marker characters
_SPLIT = re.compile("([\ue000-\ue003])")


def resolve_path(doc, css_path: str):
    """The element a document-root css path (`html > body:nth-of-type(1) > …`) names, or None. Falls back to
    cssselect for any other selector."""
    steps = [s for s in css_path.split(">")]
    m0 = _STEP.match(steps[0]) if steps else None
    if m0 and m0.group(1).lower() == doc.tag and all(_STEP.match(s) for s in steps[1:]):
        el = doc
        for s in steps[1:]:
            m = _STEP.match(s)
            tag, n = m.group(1).lower(), int(m.group(2) or 1)
            found = None
            for child in el:
                if child.tag == tag:
                    n -= 1
                    if n == 0:
                        found = child
                        break
            if found is None:
                return None
            el = found
        return el
    try:
        return engine.select_one(doc, css_path, self_too=True)
    except Exception:  # noqa: BLE001 - not a selector cssselect understands
        return None


def find_text(hay: str, needle: str) -> tuple[int, int] | None:
    """Where `needle` occurs in `hay`: exactly, else ignoring differences in whitespace (as the page pane does)."""
    want = needle.strip()
    if not want:
        return None
    i = hay.find(want)
    if i >= 0:
        return i, i + len(want)
    pattern = r"\s+".join(re.escape(w) for w in want.split())
    m = re.search(pattern, hay)
    return (m.start(), m.end()) if m else None


def _text_nodes(el):
    """(owner, attr) of every text node under `el`, in DOM textContent order (comments excluded)."""
    if not isinstance(el, etree._Comment | etree._ProcessingInstruction) and el.text:
        yield el, "text"
    for child in el:
        if isinstance(child.tag, str):
            yield from _text_nodes(child)
        if child.tail:
            yield child, "tail"


def _mark_range(el, start: int, end: int) -> bool:
    pos, done_start, done_end = 0, False, False
    for owner, attr in list(_text_nodes(el)):
        s = getattr(owner, attr)
        a, b = pos, pos + len(s)
        new = s
        if not done_end and a <= end <= b:
            new = new[: end - a] + _M_R1 + new[end - a:]
            done_end = True
        if not done_start and a <= start <= b and (start < b or start == end):
            new = new[: start - a] + _M_R0 + new[start - a:]
            done_start = True
        if new is not s:
            setattr(owner, attr, new)
        pos = b
        if done_start and done_end:
            break
    return done_start and done_end


def source_view(html: bytes, css_path: str | None, char_start: int | None = None, char_end: int | None = None,
                text: str | None = None, context_bytes: int = 40_000, window: int = 60) -> dict:
    """The saved markup around the element `css_path` names: a window of lines, the element's line range and the
    character range (`char_start`/`char_end` in its textContent, or else the first occurrence of `text`)."""
    doc = engine.parse(html)
    el = resolve_path(doc, css_path) if css_path else None
    found = el is not None
    if el is None:
        el = doc.find("body") if doc.find("body") is not None else doc
    # the character range, as positions in the element's textContent
    tc = "".join(getattr(o, a) for o, a in _text_nodes(el))
    rng = None
    if char_start is not None and char_end is not None and 0 <= char_start <= char_end <= len(tc) \
            and (not text or tc[char_start:char_end].strip() == text.strip()):
        rng = (char_start, char_end)
    elif text and text.strip():
        rng = find_text(tc, text)
    range_marked = bool(rng) and found and _mark_range(el, *rng)
    # element markers: in the text just before and just after it
    parent = el.getparent()
    if found and parent is not None:
        prev = el.getprevious()
        if prev is not None:
            prev.tail = (prev.tail or "") + _M_EL0
        else:
            parent.text = (parent.text or "") + _M_EL0
        el.tail = _M_EL1 + (el.tail or "")
    # the context: the nearest ancestor whose markup stays under `context_bytes`, at least the element itself
    for s in list(doc.iter("script", "svg")):
        if s.tag == "script":
            s.text = None
        else:
            for c in list(s):
                s.remove(c)
    ctx_el = el
    while ctx_el.getparent() is not None and ctx_el.getparent().tag != "html":
        up = ctx_el.getparent()
        if len(etree.tostring(up, encoding="unicode", method="html", with_tail=False)) > context_bytes:
            break
        ctx_el = up
    markup = etree.tostring(ctx_el, encoding="unicode", method="html", with_tail=False)
    if ctx_el is el and found:
        markup = _M_EL0 + markup + _M_EL1
    # find the markers, strip them, and report lines
    lines_raw = markup.split("\n")
    lines: list[str] = []
    el_lines = [None, None]
    marks: list[dict] = []
    in_range = False
    for li, line in enumerate(lines_raw):
        out: list[str] = []
        col = 0
        seg = 0 if in_range else None
        for part in _SPLIT.split(line):
            if part == _M_EL0:
                el_lines[0] = li
            elif part == _M_EL1:
                el_lines[1] = li
            elif part == _M_R0:
                in_range, seg = True, col
            elif part == _M_R1:
                if seg is not None:
                    marks.append({"line": li, "start": seg, "end": col})
                in_range, seg = False, None
            else:
                out.append(part)
                col += len(part)
        if in_range and seg is not None:
            marks.append({"line": li, "start": seg, "end": col})
        lines.append("".join(out))
    e0 = el_lines[0] if el_lines[0] is not None else 0
    e1 = el_lines[1] if el_lines[1] is not None else len(lines) - 1
    first = max(0, e0 - window)
    last = min(len(lines), max(e1, (marks[-1]["line"] if marks else e1)) + window + 1)
    if last - first > 4 * window + (e1 - e0):
        last = first + 4 * window + (e1 - e0)
    paths = engine.Paths()
    return {
        "css_path": css_path,
        "found": found,
        "context_path": paths(ctx_el),
        "first_line": first + 1,                    # 1-based number of lines[0] within the context markup
        "lines": lines[first:last],
        "element": [e0 - first, e1 - first] if found else None,   # 0-based indexes into `lines`
        "marks": [{**m, "line": m["line"] - first} for m in marks
                  if range_marked and first <= m["line"] < last and m["end"] > m["start"]],
        "text": tc[rng[0]:rng[1]] if rng else None,
        "truncated": first > 0 or last < len(lines),
    }
