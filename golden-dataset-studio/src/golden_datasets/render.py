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

RENDER_VERSION = "r5"  # bump when the output of `render_html` changes

# Highlight styles the page pane relies on. Ranges use the CSS Custom Highlight API (no DOM change); outlines and
# badges live in an overlay `<div id="gds-overlay">` the pane appends as the last child of <html> (not of <body>).
HIGHLIGHT_CSS = """
html{scroll-behavior:auto!important}
noscript{display:none!important}
::highlight(gds-value){background-color:rgba(253,224,120,.92);color:#111}
::highlight(gds-expected){background-color:rgba(190,242,214,.95);color:#111}
::highlight(gds-mark){background-color:#ffe4ea;color:#9f1239;text-decoration:underline wavy #e11d48}
::highlight(gds-excluded){background-color:rgba(254,228,226,.9);color:#111}
::selection{background:#b3d4fc;color:inherit}
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
#gds-overlay .gds-box.gds-block.gds-focus{box-shadow:0 0 0 2.5px #2f54eb;background:rgba(47,84,235,.08)}
#gds-overlay .gds-box.gds-block.gds-ok{box-shadow:0 0 0 2px #12805c}
#gds-overlay .gds-box.gds-block.gds-bad{box-shadow:0 0 0 2px #d92d20}
#gds-overlay .gds-box.gds-excluded{border:1.5px dashed #b42318}
#gds-overlay .gds-box.gds-mark{box-shadow:0 0 0 2px #e11d48}
#gds-overlay .gds-badge{position:absolute;min-width:19px;height:19px;border-radius:10px;background:#f5a524;
  color:#fff;font:700 11px/19px Inter,Arial,sans-serif;text-align:center;padding:0 5px;box-sizing:border-box;
  box-shadow:0 1px 2px rgba(0,0,0,.25);letter-spacing:0;text-transform:none;white-space:nowrap}
#gds-overlay .gds-badge::before{content:attr(data-n)}
#gds-overlay .gds-badge.gds-expected{background:#12805c}
#gds-overlay .gds-badge.gds-block{background:#2f54eb;min-width:16px;height:16px;font-size:9.5px;line-height:16px;padding:0 4px}
#gds-overlay .gds-badge.gds-mark{background:#e11d48}
#gds-overlay .gds-badge.gds-excluded{background:#b42318}
#gds-overlay .gds-badge.gds-note{background:#2f54eb;min-width:16px;height:16px;font-size:9.5px;line-height:16px;padding:0 4px}
"""

_JS_URL = re.compile(r"^[\x00-\x20]*j[\s]*a[\s]*v[\s]*a[\s]*s[\s]*c[\s]*r[\s]*i[\s]*p[\s]*t[\s]*:", re.I)
_URL_ATTRS = ("src", "href", "poster", "action", "formaction", "background", "xlink:href", "data")
_ASSET_TAGS = {"img", "source", "video", "input", "link", "image", "use", "audio", "track", "embed"}

_STEP = re.compile(r"^\s*([a-zA-Z][\w:-]*)(?::nth-of-type\((\d+)\))?\s*$")
_M_EL0, _M_EL1, _M_R0, _M_R1 = "", "", "", ""  # private-use marker characters
_SPLIT = re.compile("([-])")

INDEX_TTL = 10.0  # seconds between checks of the manifest and assets.parquet's ETag (each is a round trip on Azure)


@dataclass
class AssetIndex:
    version: str = "none"
    by_url: dict[str, str] = field(default_factory=dict)          # canonical url -> sha256
    by_sha: dict[str, dict] = field(default_factory=dict)         # sha256 -> {content_type, final_url}


@dataclass
class Rendered:
    path: Path        # the HTML on disk
    gz_path: Path     # the same, gzip-compressed
    etag: str         # strong: a hash of the inputs, which determine the bytes


_index_lock = threading.Lock()
_indexes: dict[tuple, AssetIndex] = {}
_checked: dict[tuple, tuple[float, AssetIndex]] = {}
_mem_lock = threading.Lock()
_mem: OrderedDict[str, Rendered] = OrderedDict()


def rendered(ctx: Ctx, stem: str, url: str, pane_css: str | None = None) -> Rendered:
    """The rendered page, from the disk cache or made now (and cached)."""
    index = asset_index(ctx)
    key = _h("\0".join([RENDER_VERSION, ctx.root.uri, ctx.catalog, ctx.crawl, stem, _h(pane_css or ""),
                        index.version]))
    remembered = _remembered(key)
    if remembered is not None:
        return remembered
    path = _rendered_folder(ctx) / f"{stem}.{key[:20]}.html"
    gz_path = path.with_suffix(".html.gz")
    if not (path.exists() and gz_path.exists()):
        html = ctx.page_path(stem).read_bytes()
        text = render_html(html, url, Rewriter(index, asset_prefix(ctx.catalog)), pane_css).encode("utf-8")
        _write_both(path, gz_path, text)
    return _remember(key, Rendered(path=path, gz_path=gz_path, etag=f'"{key[:32]}"'))


def asset_css(ctx: Ctx, sha: str, body: bytes) -> bytes:
    """An archived CSS file with its `url()` / `@import` rewritten against its own URL (cached on disk)."""
    index = asset_index(ctx)
    meta = index.by_sha.get(sha) or {}
    key = _h("\0".join([RENDER_VERSION, ctx.root.uri, ctx.catalog, ctx.crawl, sha, index.version]))
    path = _rendered_folder(ctx) / "css" / f"{key[:32]}.css"
    if path.exists():
        return path.read_bytes()
    css = body.decode("utf-8", "replace")
    out = Rewriter(index, asset_prefix(ctx.catalog)).css(css, meta.get("final_url") or "").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, out)
    return out


def pane_css_for(ctx: Ctx, ruleset: int | None) -> str | None:
    """`settings.pane_css` of that ruleset (default: the latest); None when the catalog has no ruleset yet."""
    versions = ctx.ruleset_versions()
    if ruleset is not None and ruleset not in versions:
        raise UserError(f"{ctx.catalog}: no ruleset v{ruleset}")
    if not versions:
        return None
    v = ruleset if ruleset is not None else versions[-1]
    return (ctx.ruleset(v).get("settings") or {}).get("pane_css") or None


def asset_prefix(catalog: str) -> str:
    return f"/api/catalogs/{catalog}/assets"


def _rendered_folder(ctx: Ctx) -> Path:
    return cache_home() / "rendered" / _h(ctx.root.uri)[:16] / ctx.catalog / ctx.crawl


def _remembered(key: str) -> Rendered | None:
    with _mem_lock:
        got = _mem.get(key)
        if got is not None:
            _mem.move_to_end(key)
        return got


def _remember(key: str, page: Rendered) -> Rendered:
    with _mem_lock:
        _mem[key] = page
        while len(_mem) > 2048:
            _mem.popitem(last=False)
    return page


def _write_both(path: Path, gz_path: Path, text: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, text)
    _atomic_write(gz_path, gzip.compress(text, compresslevel=5))


def render_html(html: bytes, url: str, rewriter: Rewriter, pane_css: str | None = None) -> str:
    doc = engine.parse(html)
    head = _head_of(doc)
    base = _base_url(doc, url)
    _drop_scripts(doc, head)
    for el in doc.iter():
        if isinstance(el.tag, str):
            _clean_element(el, rewriter, base)
    _append_styles(head, pane_css)
    return lxml.html.tostring(doc, encoding="unicode", doctype="<!DOCTYPE html>")


def _head_of(doc):
    """libxml2 always makes a <head> for a full document, but be safe: head is outside <body>."""
    head = doc.find("head")
    if head is None:
        head = etree.Element("head")
        doc.insert(0, head)
    return head


def _base_url(doc, url: str) -> str:
    bases = doc.xpath("//base[@href]")
    return urljoin(url, bases[0].get("href").strip()) if bases else url


def _drop_scripts(doc, head) -> None:
    for script in list(doc.iter("script")):
        script.drop_tree()  # keeps its tail text, so text nodes around it merge as in the browser
    for meta in head.xpath(".//meta[@http-equiv]"):
        meta.drop_tree()


def _clean_element(el, rewriter: Rewriter, base: str) -> None:
    for name in list(el.attrib):
        _clean_attribute(el, name, rewriter, base)
    if el.tag == "style" and el.text:
        el.text = rewriter.css(el.text, base)


def _clean_attribute(el, name: str, rewriter: Rewriter, base: str) -> None:
    attrib, low = el.attrib, name.lower()
    value = attrib[name]
    if _is_unsafe_or_base(el.tag, low, value):
        del attrib[name]
    elif low in _URL_ATTRS:
        attrib[name] = rewriter.url(value, base, archive=_is_asset(el.tag, low))
    elif low in ("srcset", "imagesrcset"):
        attrib[name] = rewriter.srcset(value, base)
    elif low == "style" and "url(" in value:
        attrib[name] = rewriter.css(value, base)


def _is_unsafe_or_base(tag: str, low: str, value: str) -> bool:
    """Scripts in any form go; so does `<base href>`: every URL is absolute now, and archive URLs are root-relative."""
    if low.startswith("on") or low == "srcdoc" or _JS_URL.match(value):
        return True
    return low in _URL_ATTRS and tag == "base"


def _is_asset(tag: str, low: str) -> bool:
    """Assets come from the archive; links and form actions go to the live URL."""
    return tag in _ASSET_TAGS or low in ("src", "poster", "background")


def _append_styles(head, pane_css: str | None) -> None:
    for css, ident in ((pane_css, "gds-pane-css"), (HIGHLIGHT_CSS, "gds-highlight-css")):
        if css:
            style = etree.SubElement(head, "style")
            style.set("id", ident)
            style.text = css


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
        return CSS_URL.sub(lambda match: self._css_reference(match, base), css)

    def srcset(self, value: str, base: str) -> str:
        out = []
        for part in value.split(","):
            bits = part.strip().split(None, 1)
            if not bits:
                continue
            bits[0] = self.url(bits[0], base)
            out.append(" ".join(bits))
        return ", ".join(out)

    def _css_reference(self, match: re.Match, base: str) -> str:
        if match.group("u") is not None and match.group(0).startswith("url"):
            ref = match.group("u")
            return match.group(0) if skip_ref(ref) else f'url("{self.url(ref, base)}")'
        ref = match.group("u2")
        return match.group(0) if skip_ref(ref) else f'@import "{self.url(ref, base)}"'


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
    path = _assets_path(ctx)
    st = ctx.root.stat(path) if path else None
    if st is None:
        return AssetIndex()
    key = (ctx.root.uri, ctx.catalog, ctx.crawl, path)
    with _index_lock:
        got = _indexes.get(key)
        if got is not None and got.version == st.etag:
            return got
    idx = _read_index(ctx, path, st.etag)
    with _index_lock:
        _indexes[key] = idx
    return idx


def _assets_path(ctx: Ctx) -> str | None:
    try:
        entry = ctx.crawl_entry().get("assets") or {}
    except Exception:  # noqa: BLE001 - an unregistered crawl simply has no archive
        entry = {}
    return entry.get("assets")


def _read_index(ctx: Ctx, path: str, version: str) -> AssetIndex:
    import pyarrow.parquet as pq

    idx = AssetIndex(version=version)
    for r in pq.read_table(io.BytesIO(ctx.root.read_bytes(path))).to_pylist():
        if not r["sha256"]:
            continue
        idx.by_url[r["url"]] = r["sha256"]
        idx.by_url.setdefault(canonical_url(r["final_url"] or r["url"]), r["sha256"])
        idx.by_sha[r["sha256"]] = {"content_type": r["content_type"], "final_url": r["final_url"] or r["url"]}
    return idx


def source_view(html: bytes, css_path: str | None, char_start: int | None = None, char_end: int | None = None,
                text: str | None = None, context_bytes: int = 40_000, window: int = 60) -> dict:
    """The saved markup around the element `css_path` names: a window of lines, the element's line range and the
    character range (`char_start`/`char_end` in its textContent, or else the first occurrence of `text`)."""
    doc = engine.parse(html)
    el, found = _target_element(doc, css_path)
    picked, range_marked = _mark_char_range(el, found, char_start, char_end, text)
    if found:
        _mark_element(el)
    context = _context_element(doc, el, context_bytes)
    markers = _Markers().read(_context_markup(context, el, found))
    first, last, element = _window(markers, found, window)
    # first_line: 1-based number of lines[0] within the context markup; element: 0-based indexes into `lines`
    return {"css_path": css_path, "found": found, "context_path": engine.Paths()(context),
            "first_line": first + 1, "lines": markers.lines[first:last], "element": element,
            "marks": markers.marks_within(first, last) if range_marked else [], "text": picked,
            "truncated": first > 0 or last < len(markers.lines)}


def _target_element(doc, css_path: str | None):
    el = resolve_path(doc, css_path) if css_path else None
    if el is not None:
        return el, True
    body = doc.find("body")
    return (body if body is not None else doc), False


def _mark_char_range(el, found: bool, char_start, char_end, text) -> tuple[str | None, bool]:
    """The character range, as positions in the element's textContent: its text, and whether it is marked."""
    content = "".join(getattr(o, a) for o, a in _text_nodes(el))
    rng = _char_range(content, char_start, char_end, text)
    marked = bool(rng) and found and _mark_range(el, *rng)
    return (content[rng[0]:rng[1]] if rng else None), marked


def _char_range(content: str, char_start, char_end, text) -> tuple[int, int] | None:
    if char_start is not None and char_end is not None and 0 <= char_start <= char_end <= len(content) \
            and (not text or content[char_start:char_end].strip() == text.strip()):
        return char_start, char_end
    if text and text.strip():
        return find_text(content, text)
    return None


def _mark_element(el) -> None:
    """Element markers go in the text just before and just after it."""
    parent = el.getparent()
    if parent is None:
        return
    prev = el.getprevious()
    if prev is not None:
        prev.tail = (prev.tail or "") + _M_EL0
    else:
        parent.text = (parent.text or "") + _M_EL0
    el.tail = _M_EL1 + (el.tail or "")


def _context_element(doc, el, context_bytes: int):
    """The nearest ancestor whose markup stays under `context_bytes`, at least the element itself."""
    _empty_scripts_and_svgs(doc)
    context = el
    while context.getparent() is not None and context.getparent().tag != "html":
        up = context.getparent()
        if len(_markup(up)) > context_bytes:
            break
        context = up
    return context


def _empty_scripts_and_svgs(doc) -> None:
    for s in list(doc.iter("script", "svg")):
        if s.tag == "script":
            s.text = None
        else:
            for c in list(s):
                s.remove(c)


def _context_markup(context, el, found: bool) -> str:
    markup = _markup(context)
    return _M_EL0 + markup + _M_EL1 if context is el and found else markup


def _markup(el) -> str:
    return etree.tostring(el, encoding="unicode", method="html", with_tail=False)


def _window(markers: _Markers, found: bool, window: int) -> tuple[int, int, list[int] | None]:
    e0 = markers.element_lines[0] if markers.element_lines[0] is not None else 0
    e1 = markers.element_lines[1] if markers.element_lines[1] is not None else len(markers.lines) - 1
    first = max(0, e0 - window)
    last_mark = markers.marks[-1]["line"] if markers.marks else e1
    last = min(len(markers.lines), max(e1, last_mark) + window + 1)
    last = min(last, first + 4 * window + (e1 - e0))
    return first, last, ([e0 - first, e1 - first] if found else None)


class _Markers:
    """Reads the markers out of the markup: the clean lines, the element's line range and the marked ranges."""

    def __init__(self):
        self.lines: list[str] = []
        self.element_lines: list[int | None] = [None, None]
        self.marks: list[dict] = []
        self.in_range = False

    def read(self, markup: str) -> _Markers:
        for li, line in enumerate(markup.split("\n")):
            self.lines.append(self.read_line(li, line))
        return self

    def read_line(self, li: int, line: str) -> str:
        out: list[str] = []
        col = 0
        seg = 0 if self.in_range else None
        for part in _SPLIT.split(line):
            if part in (_M_EL0, _M_EL1, _M_R0, _M_R1):
                seg = self.read_marker(part, li, col, seg)
            else:
                out.append(part)
                col += len(part)
        if self.in_range and seg is not None:
            self.marks.append({"line": li, "start": seg, "end": col})
        return "".join(out)

    def read_marker(self, marker: str, li: int, col: int, seg: int | None) -> int | None:
        if marker == _M_EL0:
            self.element_lines[0] = li
        elif marker == _M_EL1:
            self.element_lines[1] = li
        elif marker == _M_R0:
            self.in_range = True
            return col
        else:
            if seg is not None:
                self.marks.append({"line": li, "start": seg, "end": col})
            self.in_range = False
            return None
        return seg

    def marks_within(self, first: int, last: int) -> list[dict]:
        return [{**m, "line": m["line"] - first} for m in self.marks
                if first <= m["line"] < last and m["end"] > m["start"]]


def resolve_path(doc, css_path: str):
    """The element a document-root css path (`html > body:nth-of-type(1) > …`) names, or None. Falls back to
    cssselect for any other selector."""
    steps = css_path.split(">")
    if _is_document_path(doc, steps):
        return _follow_steps(doc, steps[1:])
    try:
        return engine.select_one(doc, css_path, self_too=True)
    except Exception:  # noqa: BLE001 - not a selector cssselect understands
        return None


def _is_document_path(doc, steps: list[str]) -> bool:
    m0 = _STEP.match(steps[0]) if steps else None
    return bool(m0 and m0.group(1).lower() == doc.tag and all(_STEP.match(s) for s in steps[1:]))


def _follow_steps(el, steps: list[str]):
    for step in steps:
        m = _STEP.match(step)
        el = _nth_child(el, m.group(1).lower(), int(m.group(2) or 1))
        if el is None:
            return None
    return el


def _nth_child(el, tag: str, n: int):
    for child in el:
        if child.tag == tag:
            n -= 1
            if n == 0:
                return child
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
        text = getattr(owner, attr)
        node_end = pos + len(text)
        marks_end = not done_end and pos <= end <= node_end
        marks_start = not done_start and pos <= start <= node_end and (start < node_end or start == end)
        if marks_end or marks_start:
            setattr(owner, attr, _insert_markers(text, pos, start if marks_start else None, end if marks_end else None))
        done_start, done_end = done_start or marks_start, done_end or marks_end
        pos = node_end
        if done_start and done_end:
            break
    return done_start and done_end


def _insert_markers(text: str, pos: int, start: int | None, end: int | None) -> str:
    if end is not None:
        text = text[: end - pos] + _M_R1 + text[end - pos:]
    if start is not None:
        text = text[: start - pos] + _M_R0 + text[start - pos:]
    return text


def _atomic_write(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()
