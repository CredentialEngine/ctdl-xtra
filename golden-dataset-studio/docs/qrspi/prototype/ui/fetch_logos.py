"""Fetch each catalog's logo once, politely, into static/logos/ (run by hand; results are kept).

Strategy per catalog, using one saved page from the read-only mirror:
  1. the header <img> whose src/alt mentions "logo" / "wordmark";
  2. a background-image in the site's stylesheet for a logo class (CCSF, WVU use CSS backgrounds);
  3. apple-touch-icon, then favicon.
At most a handful of requests per site, 1 s apart, with a normal browser user agent.
Override: CCSF's saved pages only carry the CurricUNET platform logo and ccsf.edu answers scripted
requests with 403, so the college's own logo comes from Wikimedia Commons ("City College of San
Francisco logo.svg", fetched via the Wikipedia API). See OVERRIDES.
"""

from __future__ import annotations

import glob
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import httpx
import lxml.html

MIRROR = Path.home() / "review-ui-v3-data" / "xtra-cli-output"
OUT = Path(__file__).resolve().parent / "static" / "logos"
RUNS = {
    "avc": "avc-elumenapp-com-catalog-2026-27-welcome/2026-10-12T20-59-13Z",
    "ccsf": "ccsf-curricunet-com-catalog/2026-10-01T16-02-34Z",
    "marshall": "catalog-marshall-edu/2026-10-20T13-18-30Z",
    "ualr": "catalog-ualr-edu/2026-10-18T21-05-00Z",
    "wvu": "catalog-wvu-edu/2026-10-20T13-19-46Z",
}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"
OVERRIDES = {"ccsf": "File:City College of San Francisco logo.svg"}  # Wikimedia Commons file titles
LOGO_CSS = re.compile(r"([^{}]*(?:logo|masthead)[^{}]*)\{[^}]*?background(?:-image)?\s*:[^;}]*url\(\s*['\"]?([^'\")]+)", re.I)


def candidates(page: Path, url: str, client: httpx.Client):
    doc = lxml.html.fromstring(page.read_bytes())
    base = urljoin(url, (doc.xpath("//base/@href") or [url])[0])
    for img in doc.xpath("//img"):
        key = " ".join(filter(None, [img.get("src"), img.get("alt"), img.get("class")])).lower()
        if ("logo" in key or "wordmark" in key) and "footer" not in key and img.get("src"):
            yield "header image", urljoin(base, img.get("src"))
    for href in doc.xpath('//link[contains(concat(" ", @rel, " "), " stylesheet ")]/@href'):
        css_url = urljoin(base, href)
        if "bootstrap" in css_url or "fonts" in css_url:
            continue
        time.sleep(1)
        try:
            css = client.get(css_url).text
        except httpx.HTTPError:
            continue
        for u in re.findall(r"--[\w-]*logo[\w-]*\s*:\s*url\(\s*['\"]?([^'\")]+)", css, re.I):
            yield "css custom property", urljoin(css_url, u)
        for sel, u in LOGO_CSS.findall(css):
            if "sm" in sel or "small" in sel or "footer" in sel.lower():
                continue
            yield f"css background ({sel.strip()[:40]})", urljoin(css_url, u)
    for rel in ("apple-touch-icon", "icon"):
        for href in doc.xpath(f'//link[contains(@rel, "{rel}")]/@href'):
            yield rel, urljoin(base, href)
    yield "favicon", urljoin(url, "/favicon.ico")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    with httpx.Client(follow_redirects=True, timeout=20, headers={"User-Agent": UA}) as client:
        for short, run in RUNS.items():
            if short in OVERRIDES:
                api = client.get("https://en.wikipedia.org/w/api.php", params={"action": "query", "titles": OVERRIDES[short],
                                 "prop": "imageinfo", "iiprop": "url", "format": "json"})
                src = next(iter(api.json()["query"]["pages"].values()))["imageinfo"][0]["url"]
                time.sleep(1)
                (OUT / f"{short}.svg").write_bytes(client.get(src).content)
                report[short] = {"file": f"{short}.svg", "how": "Wikimedia Commons override", "src": src}
                continue
            pages = sorted(glob.glob(str(MIRROR / run / "pages" / "*.html")))
            page = Path(pages[len(pages) // 2])
            url = json.loads(page.with_suffix("").with_suffix(".meta.json").read_text())["final_url"]
            for how, src in candidates(page, url, client):
                time.sleep(1)
                try:
                    r = client.get(src, headers={"Referer": url})
                except httpx.HTTPError:
                    continue
                ctype = r.headers.get("content-type", "").split(";")[0]
                if ctype in ("application/octet-stream", "binary/octet-stream", ""):  # S3 often omits the type
                    head = r.content[:256]
                    ctype = ("image/png" if head.startswith(b"\x89PNG") else "image/jpeg" if head.startswith(b"\xff\xd8")
                             else "image/svg+xml" if b"<svg" in r.content[:2000] else ctype)
                if r.status_code != 200 or not ctype.startswith("image/") or len(r.content) < 200:
                    continue
                ext = {"image/svg+xml": "svg", "image/png": "png", "image/jpeg": "jpg", "image/gif": "gif",
                       "image/x-icon": "ico", "image/vnd.microsoft.icon": "ico", "image/webp": "webp"}.get(ctype, "img")
                for old in OUT.glob(f"{short}.*"):
                    old.unlink()
                (OUT / f"{short}.{ext}").write_bytes(r.content)
                report[short] = {"file": f"{short}.{ext}", "how": how, "src": src, "bytes": len(r.content)}
                break
    for v in report.values():  # white-on-transparent logos need a dark tile
        t = (OUT / v["file"]).read_text(errors="ignore").lower() if v["file"].endswith(".svg") else ""
        fills = re.findall(r'fill[:=]\s*"?\s*(#[0-9a-f]{3,6}|white)', t)
        v["dark_bg"] = bool(fills) and 2 * sum(f in ("#fff", "#ffffff", "white") for f in fills) >= len(fills)
    (OUT / "sources.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
