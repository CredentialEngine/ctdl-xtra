"""Take the prototype screenshots (headless Chromium, 1440×900) into qrspi/screens/.

    python shoot.py [--only 02] [--base http://127.0.0.1:8765]
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path(__file__).resolve().parents[2] / "screens"
CAT = "avc-elumenapp-com-catalog-2026-27-welcome"


async def wait_pane(page, extra=1800):
    """Wait for the page pane's iframe to load and its highlight to settle."""
    try:
        await page.wait_for_function(
            "() => { const f = document.querySelector('.b-body iframe'); const l = document.querySelector('.b-loading');"
            " return !f || (l && l.hidden && f.contentDocument && f.contentDocument.readyState === 'complete'); }",
            timeout=30000)
    except Exception:
        pass
    await page.wait_for_timeout(extra)


async def select_text(page, css_inner: str, needle: str, length: int):
    """Create a selection inside the sandboxed iframe with a Range and fire mouseup (research §6.2:
    Playwright's mouse hangs on sandboxed frames with scripts off)."""
    await page.evaluate(
        """([css, needle, length]) => {
          const d = document.querySelector('.b-body iframe').contentDocument;
          const el = d.querySelector(css); const w = d.createTreeWalker(el, NodeFilter.SHOW_TEXT);
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
    await page.evaluate("document.activeElement.blur()")
    await page.wait_for_timeout(1000)


@shot("05-unsure-needs-expert")
async def s05(page, base):
    await page.goto(f"{base}/#/c/{CAT}/rules/program-page-with-courses?row=avc-elumenapp-com-catalog-2026-27-program-computer-engineering-as-fall-2026-5a1e6e1354")
    await page.wait_for_selector(".row.on")
    await wait_pane(page, 2500)
    await page.click(".row.on .cb.talk")
    await page.wait_for_timeout(200)
    await page.fill(".row.on .note", "Does the college treat the courses on this page as part of the program, or as a separate list?")
    await page.check(".row.on .expert")
    await page.evaluate("document.activeElement.blur()")
    await page.evaluate("document.querySelector('.tipwrap').classList.add('show')")
    await page.wait_for_timeout(200)


@shot("06-rules-tab-stub-name")
async def s06(page, base):
    await page.goto(f"{base}/#/c/{CAT}/rules/stub-name")
    await page.wait_for_selector(".row.on")
    await wait_pane(page, 2500)
    await page.click("details.how summary")
    await page.wait_for_timeout(300)


@shot("12-locator-add-missed-course")
async def s12(page, base):
    stem = "avc-elumenapp-com-catalog-2026-27-program-child-and-family-education-specializat-3da00d774a"
    await page.goto(f"{base}/#/c/{CAT}/rules/locator-program-requirement?row={stem}")
    await page.wait_for_selector(".row.on")
    await wait_pane(page, 2000)
    await page.click("#missed-btn")
    await page.wait_for_timeout(400)
    # confirm the first marked spot: "CFE 201 fulfils CORE 8 Requirements" (no " - ", so the locator skipped it)
    await page.click("#missed-panel .mp-item.unc")
    await page.wait_for_timeout(300)
    await page.fill("#missed-panel .note", "A requirement line without ' - '; it still names a course.")
    await page.evaluate("document.activeElement.blur()")
    await page.wait_for_timeout(1800)


@shot("07-records-tab")
async def s07(page, base):
    await page.goto(f"{base}/#/c/{CAT}/records/GEOG222")
    await page.wait_for_selector(".card")
    await wait_pane(page)


@shot("08-compare")
async def s08(page, base):
    await page.goto(f"{base}/#/c/{CAT}/compare")
    await page.wait_for_selector(".sumline")
    await page.wait_for_timeout(500)


@shot("09-prompt")
async def s09(page, base):
    await page.goto(f"{base}/#/c/{CAT}/rules/course-description")
    await page.wait_for_selector(".row.on")
    await page.click("text=Improve this rule")  # lands on the Prompt tab with this rule preselected
    await page.wait_for_selector(".prompt-from")
    await page.wait_for_timeout(500)
    await page.evaluate("""() => { const pre = document.querySelector('.prompt-pre');
      const h = [...pre.querySelectorAll('.h3')].find(n => n.textContent.startsWith('### Annotations'));
      if (h) pre.scrollTop = h.offsetTop - pre.offsetTop - 40; }""")
    await page.wait_for_timeout(500)


@shot("10-golden")
async def s10(page, base):
    await page.goto(f"{base}/#/c/{CAT}/golden")
    await page.wait_for_selector(".gate")
    await page.wait_for_timeout(500)


@shot("11-page-pane-html-view")
async def s11(page, base):
    await page.goto(f"{base}/#/c/{CAT}/rules/course-code?row=ARTHC1100H")
    await page.wait_for_selector(".row.on")
    await wait_pane(page, 800)
    await page.click(".b-url .seg button[data-m=html]")
    await page.wait_for_timeout(1200)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8765")
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page = await ctx.new_page()
        page.on("pageerror", lambda e: print("  page error:", e))
        for name, fn in SHOTS:
            if args.only and not any(name.startswith(o) for o in args.only):
                continue
            await fn(page, args.base)
            await page.screenshot(path=OUT / f"{name}.png")
            print("saved", name)
            if name == "08-compare":  # the full-page shot shows one signal drilled into
                await page.evaluate("document.querySelectorAll('.sigrow')[1].click()")  # markup-leak: 11 records lost it
            if name in ("08-compare", "09-prompt"):
                # full-page variant: let the document scroll container grow to its content
                await page.add_style_tag(content="html,body{height:auto!important;overflow:visible!important} main{display:block!important}"
                                                  " .doc,.prompt-layout,.cmp-layout{overflow:visible!important;height:auto!important} .cmp-layout .col{height:auto!important}"
                                                  " .prompt-pre{overflow:visible!important}")
                await page.wait_for_timeout(300)
                await page.screenshot(path=OUT / f"{name}-full.png", full_page=True)
                print("saved", name + "-full")
        await browser.close()


asyncio.run(main())
