"""Screenshots of every screen of the spec (§7) in headless Chromium, 1440×900 at 2x, like the agreed screens.

    uv run --with playwright python bench/shots_review.py --base http://127.0.0.1:8014 --out <dir> [--only 03]
    … --out docs/qrspi/evals/screens --only e   (the Evals spec's screens, docs/qrspi/evals/03-spec.md §9)

Needs a running Studio (`golden-datasets serve`) with AVC and a built web app. The Evals screens only open the approve
confirmation and the note box (nothing is saved); still, run the Studio on a scratch copy of the root and golden root. Selections inside the sandboxed
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
THEME = {"14-dark-mode": "dark"}


def shot(name, height=900):
    def deco(fn):
        SHOTS.append((name, fn, height))
        return fn
    return deco


@shot("01-catalog-picker")
async def s01(page, base):
    await page.goto(f"{base}/#/")
    await page.wait_for_selector(".ctab tbody tr")
    await page.wait_for_timeout(600)


@shot("01b-loop-modal")
async def s01b(page, base):
    await page.goto(f"{base}/#/")
    await page.wait_for_selector(".loop-node")
    # mid-run: the dot on its way from box 1 to box 2 (hold 900 ms, then a 1,300 ms run)
    await page.wait_for_timeout(1500)


@shot("01c-add-catalog-search")
async def s01c(page, base):
    await page.goto(f"{base}/#/")
    await page.wait_for_selector(".ctab tbody tr")
    await page.click("text=+ Add a catalog")
    await page.wait_for_selector(".ac-t tbody tr", timeout=60000)
    await page.fill(".ac-search", "ca")
    await page.click(".ac-info")
    await page.wait_for_timeout(300)


@shot("01d-add-catalog-confirm")
async def s01d(page, base):
    await page.goto(f"{base}/#/")
    await page.wait_for_selector(".ctab tbody tr")
    await page.click("text=+ Add a catalog")
    await page.wait_for_selector(".ac-t tbody tr", timeout=60000)
    await page.fill(".ac-search", "cabrillo")
    await page.press(".ac-search", "Enter")
    await page.wait_for_selector(".ac-found")
    await page.wait_for_timeout(300)


@shot("01e-add-catalog-adding")
async def s01e(page, base):
    # adds a small crawled catalog to the served root: run it against a scratch root, not the shared one
    await page.request.post(f"{base}/api/crawls/catalog-citruscollege-edu/add", data={"by": "Jared Diener"})
    await page.goto(f"{base}/#/")
    await page.wait_for_function("() => /Copying pages… [3-9][0-9]/.test(document.querySelector('.cat.adding')?.textContent ?? '')",
                                 timeout=60000)
    await page.wait_for_timeout(300)


@shot("01f-generate-rules")
async def s01f(page, base):
    # needs a catalog added from the picker that has no rules yet
    await page.goto(f"{base}/#/")
    await page.wait_for_selector(".cat .gen")
    await page.click(".cat .gen")
    await page.wait_for_selector("[data-testid=first-rules-prompt] h1")
    await page.wait_for_timeout(300)


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
    # no ✗ first: selecting text on the row's page opens the ✗ draft with it
    await select_text(page, "div.introtext", "The course explores", 2000)
    await page.wait_for_timeout(300)
    await page.fill(".row.on .note", "Advisory isn't part of the description either: drop it like the prerequisite.")
    await page.wait_for_timeout(1500)


@shot("04b-highlight-in-pieces")
async def s04b(page, base):
    await page.goto(f"{base}/#/c/{CAT}/rules/course-description?row=AM135A")
    await page.wait_for_selector(".row.on")
    await wait_pane(page)
    for _ in range(3):  # zoomed in, so the pieces and their × read at screenshot size
        await page.click("button[aria-label='Zoom in']")
    await wait_pane(page, 1500)
    # two drags, the later text first: the pieces are kept in page order, each with a × on the page and in the row
    await select_text(page, "div.introtext", "Topics include", 2000)
    await page.wait_for_timeout(300)
    await select_text(page, "div.introtext", "The course explores", len("The course explores the use of a 3D CAD environment."))
    await page.wait_for_timeout(300)
    await page.evaluate("() => document.querySelector('.row.on .expand')?.scrollIntoView({block: 'center'})")
    await page.wait_for_timeout(1500)


@shot("05-unsure-needs-expert")
async def s05(page, base):
    await page.goto(f"{base}/#/c/{CAT}/rules/course-description?row=NS922L")
    await page.wait_for_selector(".row.on")
    await wait_pane(page)
    await page.click(".row.on .cb.talk")
    await page.fill(".row.on .note", "Is the Advisory line part of the course description, or a separate requirement?")
    await page.check(".row.on .chk-expert input")
    await page.hover(".tipwrap[data-tip]")
    await page.wait_for_timeout(600)


@shot("12-locator-add-missed-course")
async def s12b(page, base):
    await page.goto(f"{base}/#/c/{CAT}/rules/locator-course-page?row=GEOG222")
    await page.wait_for_selector(".row.on")
    await wait_pane(page)
    await page.click("[data-tour=add-missed]")
    await page.wait_for_timeout(300)
    items = await page.query_selector_all(".mp-item.unc")
    if items:
        await items[0].click()
    await page.fill(".missed-panel .note", "A second course on this page that the locator didn't find.")
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


@shot("15-sample-autostratify")
async def s15(page, base):
    await page.goto(f"{base}/#/c/{CAT}/rules/course-description")
    await page.wait_for_selector(".row.on")
    await page.click(".sm-modes button:has-text('Autostratify')")
    await page.wait_for_selector(".row .sm-tag")
    await wait_pane(page, 800)


@shot("16-sample-manual-select")
async def s16(page, base):
    await page.goto(f"{base}/#/c/{CAT}/rules/course-description")
    await page.wait_for_selector(".row.on")
    await page.click(".sm-modes button:has-text('Manual select')")
    await page.click(".sm-dim:has-text('Leading label')")
    await page.click(".sm-bar:has-text('Advisory:')")
    await page.wait_for_selector(".row .sm-tag")
    await wait_pane(page, 800)


@shot("08c-compare-other-changed", height=1400)
async def s08c(page, base):
    await page.goto(f"{base}/#/c/{CAT}/compare?a=1&b=2")
    await page.wait_for_selector("[data-testid=sample]")
    await page.click(".sm-modes button:has-text('Autostratify')")
    await page.wait_for_selector(".crec .sm-tag")
    await page.evaluate("() => [...document.querySelectorAll('h2')].find((h) => h.textContent.startsWith('Other changed'))"
                        ".scrollIntoView()")
    await page.wait_for_timeout(600)


@shot("17-storage-files")
async def s17(page, base):
    await page.goto(f"{base}/#/c/{CAT}/rules/course-description")
    await page.wait_for_selector(".row.on")
    await page.click(".files-btn")
    await page.wait_for_selector(".sf-event")
    await page.wait_for_timeout(600)


@shot("18-rules-discussion")
async def s18(page, base):
    await page.goto(f"{base}/#/c/{CAT}/rules/course-description?row=GEOG222")
    await page.wait_for_selector(".row.on")
    await page.click("[data-testid=ruleset-talk] .talk-head")
    await page.click("[data-rule=course-description] .rule-talk-btn")
    await page.wait_for_selector("[data-testid=rule-talk]")
    await wait_pane(page, 600)


@shot("08-compare")
async def s08(page, base):
    await page.goto(f"{base}/#/c/{CAT}/compare?a=1&b=2")
    await page.wait_for_selector(".ann-row, .cmp-row, .verdicts, h1")
    await page.wait_for_timeout(1500)


@shot("08-compare-full", height=2400)
async def s08full(page, base):
    await s08(page, base)
    await page.click("text=contains-label-text")
    await page.wait_for_timeout(800)


@shot("09-prompt")
async def s09(page, base):
    await page.goto(f"{base}/#/c/{CAT}/prompt?rule=course-description")
    await page.wait_for_timeout(2000)


@shot("09-prompt-full", height=3200)
async def s09full(page, base):
    await s09(page, base)


@shot("10-golden-datasets")
async def s10(page, base):
    await page.goto(f"{base}/#/c/{CAT}/golden")
    await page.wait_for_selector("text=ruleset v3")
    await page.wait_for_timeout(800)
    await tidy_paths(page)


@shot("13-page-pane-view-tools")
async def s13(page, base):
    await page.goto(f"{base}/#/c/{CAT}/rules/course-description?row=GEOG222")
    await page.wait_for_selector(".row.on")
    await wait_pane(page, 800)
    for _ in range(4):
        await page.click("button[aria-label='Zoom in']")
    await page.click(".gpp-check input")
    await page.wait_for_timeout(2500)
    await page.evaluate("() => { try { localStorage.removeItem('studio.pane.zoom'); localStorage.removeItem('studio.pane.css') } catch (e) {} }")


@shot("09b-prompt-rendered")
async def s09b(page, base):
    await s09(page, base)
    await page.click("text=Rendered")
    await page.wait_for_timeout(600)


@shot("14-dark-mode")
async def s14(page, base):
    await page.goto(f"{base}/#/c/{CAT}/rules/course-description?row=GEOG222")
    await page.wait_for_selector(".row.on")
    await wait_pane(page)


# --- the Evals spec's screens (docs/qrspi/evals/screens) ------------------------------------------------------------
SCRATCH = "/scratchpad/"


async def go(page, url: str, wait: str) -> None:
    await page.goto(url)
    if await page.locator("button.idn-go").count():  # the profile screen: the reviewer is set, so just go on
        await page.click("button.idn-go")
    await page.wait_for_selector(wait, timeout=30000)


async def tidy_paths(page) -> None:
    """A scratch golden root shows as the local one (.data/golden)."""
    await page.evaluate("""(mark) => { const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let n;
      while ((n = w.nextNode())) if (n.data.includes(mark)) n.data = n.data.replace(/\\/\\S*?\\/scratchpad\\/shots\\/golden/g, '.data/golden'); }""",
                        SCRATCH)


@shot("e01-home-golden-dataset")
async def e01(page, base):
    await go(page, f"{base}/#/", ".ctab tbody tr")
    await page.wait_for_timeout(800)


@shot("e02-home-xtra-score")
async def e02(page, base):
    await go(page, f"{base}/#/?v=score", ".ctab tbody tr")
    await page.wait_for_timeout(800)


@shot("e03-evals-tab")
async def e03(page, base):
    await go(page, f"{base}/#/c/{CAT}/evals", ".evx-rows .evx-row")
    await page.wait_for_timeout(800)


@shot("e04-evals-row-diff")
async def e04(page, base):
    await go(page, f"{base}/#/c/{CAT}/evals?o=partial", ".evx-rows .evx-row")
    await page.click(".evx-rows .evx-row")
    await page.wait_for_selector("[data-testid=row-panel]")
    await wait_pane(page, 1200)


@shot("e05-compare-diff")
async def e05(page, base):
    await go(page, f"{base}/#/c/{CAT}/compare?a=1&b=2", "[data-testid=compare-value]")
    await page.evaluate("() => document.querySelector('[data-testid=compare-value]').scrollIntoView({block: 'center'})")
    await page.wait_for_timeout(600)


@shot("e06-approve-confirmation")
async def e06(page, base):
    await go(page, f"{base}/#/c/{CAT}/rules/course-code", "[data-tour=approve] .btn")
    await page.click("[data-tour=approve] .btn")
    await page.wait_for_selector("text=Approve and publish")
    await page.wait_for_timeout(600)


@shot("e07-golden-datasets-tab")
async def e07(page, base):
    await go(page, f"{base}/#/c/{CAT}/golden", "text=ruleset v3")
    await page.wait_for_timeout(800)
    await tidy_paths(page)


@shot("e08-rules-annotated-by-confirm")
async def e08(page, base):
    await go(page, f"{base}/#/c/{CAT}/rules/course-description?by=waiting", ".rows .row")
    await page.click(".rows .row")
    await page.wait_for_selector(".row.on")
    await wait_pane(page, 800)


@shot("e08b-rules-annotated-by-open")
async def e08b(page, base):
    await go(page, f"{base}/#/c/{CAT}/rules/course-description", ".ab-btn")
    await page.click(".ab-btn")
    await page.wait_for_selector(".ab-pop")
    await page.wait_for_timeout(400)


@shot("e09-records-annotated-by")
async def e09(page, base):
    await go(page, f"{base}/#/c/{CAT}/records?by=Jared+Diener", ".course-list .course-item")
    await page.click(".course-list .course-item")
    await page.wait_for_selector(".rec-head h1")
    await wait_pane(page, 800)


async def main(base: str, out: Path, only: str | None) -> None:
    from playwright.async_api import async_playwright

    out.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for name, fn, height in SHOTS:
            if only and not name.startswith(only):
                continue
            ctx = await browser.new_context(viewport={"width": 1440, "height": height}, device_scale_factor=2)
            page = await ctx.new_page()
            page.on("pageerror", lambda e, n=name: print(f"  [{n}] page error: {e}"))
            loop = "" if name == "01b-loop-modal" else " localStorage.setItem('studio.loop.hidden', '1');"
            await page.add_init_script("try { localStorage.setItem('studio.tour.seen', '1');"
                                      " localStorage.setItem('studio.reviewer', '\"Jared Diener\"');"
                                      " localStorage.setItem('studio.role', '\"sme\"');"
                                      f" localStorage.setItem('studio.rules.sample', '{int(name.startswith(('15', '16')))}');"
                                      f" localStorage.setItem('studio.compare.sample', '{int(name.startswith('08c'))}');" + loop +
                                      f" localStorage.setItem('studio.theme', '{THEME.get(name, 'light')}') }} catch (e) {{}}")
            await fn(page, base)
            if await page.evaluate("() => { const x = document.querySelector('.run-x'); x?.click(); return !!x }"):
                await page.wait_for_timeout(400)  # a past AI run's outcome isn't part of these screens
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
