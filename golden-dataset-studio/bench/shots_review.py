"""Screenshots of the Rules and Records tabs (W4) in headless Chromium, 1440×900 at 2x, like the agreed screens.

    uv run --with playwright python bench/shots_review.py --base http://127.0.0.1:8014 --out <dir> [--only 03]

Needs a running Studio (`golden-datasets serve`) with AVC and a built web app. Selections inside the sandboxed
page are made with a Range + a synthetic mouseup (Playwright's mouse hangs on sandboxed frames with scripts off).
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

CAT = "avc"


async def wait_pane(page, extra=1800):
    try:
        await page.wait_for_function(
            "() => { const f = document.querySelector('.gpp-body iframe');"
            " return !!f && !document.querySelector('.gpp-loading') && f.contentDocument"
            " && f.contentDocument.readyState === 'complete'; }", timeout=30000)
    except Exception:  # noqa: BLE001 — a missing pane still gets its screenshot
        pass
    await page.wait_for_timeout(extra)


async def select_text(page, css_inner: str, needle: str, length: int) -> bool:
    return await page.evaluate(
        """([css, needle, length]) => {
          const d = document.querySelector('.gpp-body iframe').contentDocument;
          const el = d.querySelector(css); if (!el) return false;
          const w = d.createTreeWalker(el, NodeFilter.SHOW_TEXT);
          let n; while ((n = w.nextNode())) { const i = n.data.indexOf(needle); if (i >= 0) {
            const r = d.createRange(); r.setStart(n, i); let last = n, m;
            while ((m = w.nextNode())) last = m;
            if (length >= 1000) r.setEnd(last, last.data.length); else r.setEnd(n, Math.min(n.data.length, i + length));
            const s = d.getSelection(); s.removeAllRanges(); s.addRange(r);
            d.dispatchEvent(new MouseEvent('mouseup', {bubbles: true})); return true; } }
          return false; }""",
        [css_inner, needle, length])


SHOTS = []


def shot(name):
    def deco(fn):
        SHOTS.append((name, fn))
        return fn
    return deco


@shot("01-catalog-picker")
async def s01(page, base):
    await page.goto(f"{base}/#/")
    await page.wait_for_selector(".cat.ready")
    await page.wait_for_timeout(600)


@shot("03-rules-tab-description-v2")
async def s03(page, base):
    await page.goto(f"{base}/#/c/{CAT}/rules/course-description?row=GEOG222")
    await page.wait_for_selector(".row.on")
    await wait_pane(page)


@shot("04-highlight-to-annotate")
async def s04(page, base):
    await page.goto(f"{base}/#/c/{CAT}/rules/course-description?row=AM135A")
    await page.wait_for_selector(".row.on")
    await wait_pane(page)
    await page.click(".row.on .cb.no")
    await page.wait_for_timeout(400)
    await select_text(page, "div.introtext", "The course explores", 2000)
    await page.wait_for_timeout(300)
    await page.fill(".row.on .note", "Advisory isn't part of the description either: drop it like the prerequisite.")
    await page.wait_for_timeout(1500)


@shot("05-unsure-needs-expert")
async def s05(page, base):
    await page.goto(f"{base}/#/c/{CAT}/rules/program-page-with-courses?row=avc-elumenapp-com-catalog-2026-27-program-computer-engineering-as-fall-2026-5a1e6e1354")
    await page.wait_for_selector(".row.on")
    await wait_pane(page)
    await page.click(".row.on .cb.talk")
    await page.fill(".row.on .note", "Does the college treat the courses on this page as part of the program?")
    await page.check(".row.on .chk-expert input")
    await page.hover(".tipwrap[data-tip]")
    await page.wait_for_timeout(600)


@shot("06-rules-tab-stub-name")
async def s06(page, base):
    await page.goto(f"{base}/#/c/{CAT}/rules/stub-name")
    await page.wait_for_selector(".row.on")
    await wait_pane(page)


@shot("12-locator-program-requirement")
async def s12(page, base):
    await page.goto(f"{base}/#/c/{CAT}/rules/locator-program-requirement?row=CFE101")
    await page.wait_for_selector(".row.on")
    await wait_pane(page)


@shot("12b-locator-add-missed-course")
async def s12b(page, base):
    await page.goto(f"{base}/#/c/{CAT}/rules/locator-program-requirement?row=CFE101")
    await page.wait_for_selector(".row.on")
    await wait_pane(page)
    await page.click("[data-tour=add-missed]")
    await page.wait_for_timeout(300)
    items = await page.query_selector_all(".mp-item.unc")
    if items:
        await items[0].click()
    await page.fill(".missed-panel .note", "A requirement line without ' - '; it still names a course.")
    await page.wait_for_timeout(1500)


@shot("07-records-tab")
async def s07(page, base):
    await page.goto(f"{base}/#/c/{CAT}/records/GEOG222")
    await page.wait_for_selector(".card")
    await wait_pane(page)


@shot("11-page-pane-html-view")
async def s11(page, base):
    await page.goto(f"{base}/#/c/{CAT}/rules/course-description?row=GEOG222")
    await page.wait_for_selector(".row.on")
    await wait_pane(page, 600)
    await page.click(".gpp-seg button:nth-child(2)")
    await page.wait_for_timeout(1500)


async def main(base: str, out: Path, only: str | None) -> None:
    from playwright.async_api import async_playwright

    out.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for name, fn in SHOTS:
            if only and not name.startswith(only):
                continue
            ctx = await browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
            page = await ctx.new_page()
            page.on("pageerror", lambda e, n=name: print(f"  [{n}] page error: {e}"))
            await page.add_init_script("try { localStorage.setItem('studio.tour.seen', '1') } catch (e) {}")
            await fn(page, base)
            await page.screenshot(path=str(out / f"{name}.png"))
            print("wrote", out / f"{name}.png")
            await ctx.close()
        await browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://127.0.0.1:8014")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--only")
    a = ap.parse_args()
    asyncio.run(main(a.base, a.out, a.only))
