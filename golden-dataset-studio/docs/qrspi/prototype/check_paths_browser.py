"""Do the document-root css paths (computed with lxml) resolve in a real browser?

Loads a sample of cleaned pages from the prototype server in headless Chromium and, for every match
and occurrence on them, runs querySelector(css_path) and checks the element's text contains raw_text.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import studio  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402

BASE = "http://127.0.0.1:8765"


async def main():
    con = studio.connect()
    stems = [r[0] for r in con.execute("""SELECT page_stem FROM (SELECT DISTINCT page_stem FROM occurrences WHERE extraction='rs-0002')
        ORDER BY hash(page_stem) LIMIT 60""").fetchall()]
    totals = {"pages": 0, "occurrences": 0, "occ_ok": 0, "matches": 0, "found": 0, "text_ok": 0, "offsets_exact": 0}
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await b.new_page()
        for stem in stems:
            rows = con.execute("""SELECT css_path, raw_text, char_start, char_end FROM matches WHERE extraction='rs-0002'
                AND page_stem = ? AND css_path IS NOT NULL""", [stem]).fetchall()
            occs = [r[0] for r in con.execute("SELECT css_path FROM occurrences WHERE extraction='rs-0002' AND page_stem=?", [stem]).fetchall()]
            await page.goto(f"{BASE}/api/c/{studio.CATALOG}/pages/{stem}/render", wait_until="domcontentloaded")
            res = await page.evaluate("""([rows, occs]) => {
                const out = {occ_ok: 0, found: 0, text_ok: 0, exact: 0};
                for (const c of occs) if (document.querySelector(c)) out.occ_ok++;
                for (const [css, raw, s, e] of rows) { const el = document.querySelector(css); if (!el) continue; out.found++;
                  const t = el.textContent, r = (raw || '').trim();
                  if (t.replace(/\\s+/g, ' ').includes(r.replace(/\\s+/g, ' '))) out.text_ok++;
                  if (t.slice(s, e) === raw) out.exact++; }
                return out; }""", [[list(r) for r in rows], occs])
            totals["pages"] += 1
            totals["occurrences"] += len(occs)
            totals["occ_ok"] += res["occ_ok"]
            totals["matches"] += len(rows)
            totals["found"] += res["found"]
            totals["text_ok"] += res["text_ok"]
            totals["offsets_exact"] += res["exact"]
        await b.close()
    out = json.dumps(totals, indent=2)
    (studio.SCRATCH / "paths-browser.json").write_text(out)
    print(out)


asyncio.run(main())
