"""Do the engine's document-root css paths resolve, to the same text, in the page pane's render (Chromium)?

    uv run --with playwright python bench/check_paths_browser.py --root .data/root --catalog avc [--pages 20]

Starts the Studio's API on a free port, loads `/api/catalogs/<c>/pages/<stem>/render` for a sample of pages in
headless Chromium (JavaScript on in the test page only to evaluate; the render itself has no scripts), and for
elements picked with a few selectors checks that `document.querySelector(engine.Paths()(el))` finds an element whose
`textContent` equals the engine's `text_content(el)`. Also times cold and warm renders.
"""

from __future__ import annotations

import argparse
import hashlib
import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from golden_datasets import engine  # noqa: E402
from golden_datasets.context import Ctx  # noqa: E402

SELECTORS = [".introtext", "header.header h2", "header.header h3", ".new-rule", ".accordionheader", "li", "td", "p"]
PER_SELECTOR = 6


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(root: str, port: int):
    import uvicorn

    from golden_datasets.server.app import create_app

    server = uvicorn.Server(uvicorn.Config(create_app(root), host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    while not server.started:
        time.sleep(0.05)
    return server


def sample(ctx: Ctx, n: int) -> list[dict]:
    pages = sorted(ctx.pages(), key=lambda p: hashlib.sha1(p["page_stem"].encode()).hexdigest())
    courses = [p for p in pages if "-course-" in p["page_stem"]][: n // 2]
    programs = [p for p in pages if "-program-" in p["page_stem"]][: n - len(courses)]
    return courses + programs


def targets(html: bytes) -> list[dict]:
    doc = engine.parse(html)
    paths = engine.Paths()
    out = []
    for sel in SELECTORS:
        for el in engine.select(doc, sel)[:PER_SELECTOR]:
            text = engine.text_content(el)
            # a character range in the middle of the text, as the engine would store it
            a = len(text) // 3
            b = min(len(text), a + 25)
            out.append({"sel": sel, "path": paths(el), "text": text, "a": a, "b": b})
    return out


JS = """(ts) => ts.map(t => {
  const el = document.querySelector(t.path);
  if (!el) return {found: false};
  const tc = el.textContent;
  const norm = s => s.replace(/\\s+/g, ' ').trim();
  return {found: true, exact: tc === t.text, norm: norm(tc) === norm(t.text),
          range: tc.slice(t.a, t.b) === t.text.slice(t.a, t.b)};
})"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".data/root")
    ap.add_argument("--catalog", default="avc")
    ap.add_argument("--pages", type=int, default=20)
    ap.add_argument("--screenshot", help="save a screenshot of the first page here")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    ctx = Ctx(args.root, args.catalog)
    pages = sample(ctx, args.pages)
    port = free_port()
    server = serve(args.root, port)
    base = f"http://127.0.0.1:{port}/api/catalogs/{args.catalog}/pages"
    tot = {"pages": 0, "elements": 0, "found": 0, "exact": 0, "norm": 0, "range": 0}
    by_sel: dict[str, list[int]] = {}
    misses: list[str] = []
    cold, warm = [], []
    import httpx

    try:
        with sync_playwright() as p, httpx.Client() as http:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 1000})
            for i, row in enumerate(pages):
                stem = row["page_stem"]
                t0 = time.time()
                http.get(f"{base}/{stem}/render").raise_for_status()
                cold.append(time.time() - t0)
                t0 = time.time()
                http.get(f"{base}/{stem}/render").raise_for_status()
                warm.append(time.time() - t0)
                ts = targets(ctx.page_path(stem).read_bytes())
                page.goto(f"{base}/{stem}/render", wait_until="load")
                if i == 0 and args.screenshot:
                    page.screenshot(path=args.screenshot)
                res = page.evaluate(JS, [{k: t[k] for k in ("path", "text", "a", "b")} for t in ts])
                tot["pages"] += 1
                for t, r in zip(ts, res):
                    tot["elements"] += 1
                    s = by_sel.setdefault(t["sel"], [0, 0, 0])
                    s[0] += 1
                    if not r["found"]:
                        misses.append(f"{stem}: {t['path']}")
                        continue
                    tot["found"] += 1
                    s[1] += 1
                    for k in ("exact", "norm", "range"):
                        tot[k] += bool(r[k])
                    s[2] += bool(r["exact"])
                    if not r["exact"] and len(misses) < 40:
                        misses.append(f"{stem}: text differs at {t['path']}")
            browser.close()
    finally:
        server.should_exit = True
    print(f"pages {tot['pages']}  elements {tot['elements']}  resolved {tot['found']}  "
          f"textContent exact {tot['exact']}  whitespace-normalized {tot['norm']}  char range exact {tot['range']}")
    for sel, (n, f, e) in by_sel.items():
        print(f"  {sel:20s} {n:4d} elements, {f:4d} resolved, {e:4d} exact text")
    cold.sort()
    warm.sort()
    print(f"render over HTTP: cold median {cold[len(cold) // 2] * 1000:.0f} ms (max {cold[-1] * 1000:.0f}), "
          f"warm median {warm[len(warm) // 2] * 1000:.1f} ms (max {warm[-1] * 1000:.1f})")
    for m in misses[:20]:
        print("  miss:", m)
    return 0 if tot["found"] == tot["elements"] else 1


if __name__ == "__main__":
    sys.exit(main())
