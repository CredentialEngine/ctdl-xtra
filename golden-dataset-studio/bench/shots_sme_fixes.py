"""Screenshots of the sme-fixes behaviours (docs/qrspi/sme-fixes/03-spec.md), for the PR.

    uv run --with playwright python bench/shots_sme_fixes.py --base http://127.0.0.1:8811 --out docs/qrspi/sme-fixes/screens

Needs a Studio on a scratch copy of a local root with AVC (Estimated Duration folded into one list rule, and Entry
Condition: Description with an `absent_if` claim), CCSF and Marshall, and a scored golden dataset for AVC (see
docs/qrspi/sme-fixes/build-notes-*.md). Some shots save annotations: never point this at a shared root.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from shots_review import select_text, wait_pane

SHOTS = []


def shot(name, height=900):
    def deco(fn):
        SHOTS.append((name, fn, height))
        return fn
    return deco


async def zoom_in(page, times=2):
    for _ in range(times):
        b = page.locator('button[title*="oom in"], button[aria-label*="oom in"]').first
        if await b.count():
            await b.click()
            await page.wait_for_timeout(500)


async def click_text(page, text, selector="button"):
    await page.locator(selector, has_text=text).first.click()
    await page.wait_for_timeout(700)


@shot("01-highlight-bar")
async def _(page, base):
    await page.goto(f"{base}/#/c/avc/rules/course-description?row=ACCT199")
    await wait_pane(page)
    await zoom_in(page)
    await select_text(page, "body", "LIMITATION ON ENROLLMENT", 378)
    await page.wait_for_timeout(900)


@shot("02-not-in-answer")
async def _(page, base):
    await page.goto(f"{base}/#/c/avc/rules/course-description?row=ACCT199")
    await wait_pane(page)
    await zoom_in(page)
    await select_text(page, "body", "LIMITATION ON ENROLLMENT", 378)
    await page.wait_for_timeout(700)
    await click_text(page, "Not in answer")  # a draft ✕: Enter would save it and move to the next row
    await page.wait_for_timeout(1200)


@shot("03-duration-objects")
async def _(page, base):
    await page.goto(f"{base}/#/c/avc/rules/course-estimated-duration?row=ACCT199")
    await wait_pane(page)


@shot("04-label-a-new-duration")
async def _(page, base):
    await page.goto(f"{base}/#/c/avc/rules/course-estimated-duration?row=ACCT199")
    await wait_pane(page)
    await click_text(page, "Add a")
    await select_text(page, "body", "Total Course Lab Hours", 22)
    await page.wait_for_timeout(900)


@shot("05-not-on-the-page-claim")
async def _(page, base):
    await page.goto(f"{base}/#/c/avc/rules/course-entry-condition-description?row=ABDY112")
    await wait_pane(page)


@shot("06-nothing-found-no-claim")
async def _(page, base):
    await page.goto(f"{base}/#/c/marshall/rules/course-description?row=WS483")
    await wait_pane(page)


@shot("07-why-wrong")
async def _(page, base):
    await page.goto(f"{base}/#/c/avc/rules/course-entry-condition-description?row=ACCT199")
    await wait_pane(page)
    await page.keyboard.press("2")  # ✕
    await page.wait_for_timeout(900)


@shot("08-course-blocks-page-row")
async def _(page, base):
    await page.goto(f"{base}/#/c/ccsf/rules/locator-course-page?row=INTD100")
    await wait_pane(page)
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(900)


@shot("09-course-blocks-tab-into-a-course")
async def _(page, base):
    await page.goto(f"{base}/#/c/ccsf/rules/locator-course-page?row=INTD100")
    await wait_pane(page)
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(600)
    await page.keyboard.press("Enter")  # into the page's first course
    await page.wait_for_timeout(600)
    await page.keyboard.press("Tab")    # the next course on the same page
    await page.wait_for_timeout(1500)


@shot("10-evals-found-right", height=1400)
async def _(page, base):
    await page.goto(f"{base}/#/c/avc/evals")
    await page.wait_for_timeout(3500)
    await page.evaluate("() => { const b = [...document.querySelectorAll('button')].find(x => /Rule-matched/.test(x.textContent)); b?.click(); }")
    await page.wait_for_timeout(2500)


@shot("11-evals-where-its-wrong", height=1400)
async def _(page, base):
    await page.goto(f"{base}/#/c/avc/evals")
    await page.wait_for_timeout(3500)
    await page.evaluate("() => { const b = [...document.querySelectorAll('button')].find(x => /Rule-matched/.test(x.textContent)); b?.click(); }")
    await page.wait_for_timeout(2500)
    await page.evaluate("() => { const h = [...document.querySelectorAll('h2,h3,h4,summary,button')].find(x => /Where it.s wrong/i.test(x.textContent)); h?.scrollIntoView({block: 'start'}); if (h && h.tagName === 'SUMMARY') h.click(); }")
    await page.wait_for_timeout(1500)


@shot("12-run-not-responding")
async def _(page, base):
    await page.goto(f"{base}/#/c/marshall/rules/course-description")
    await page.wait_for_timeout(6000)


@shot("13-read-the-report")
async def _(page, base):
    await page.goto(f"{base}/#/c/avc/rules/course-description")
    await page.wait_for_timeout(3000)
    await click_text(page, "Read the report")
    await page.wait_for_timeout(1500)


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
            await page.add_init_script("try { localStorage.setItem('studio.tour.seen', '1');"
                                      " localStorage.setItem('studio.reviewer', '\"Jared Diener\"');"
                                      " localStorage.setItem('studio.role', '\"sme\"');"
                                      " localStorage.setItem('studio.loop.hidden', '1');"
                                      " localStorage.setItem('studio.theme', 'light') } catch (e) {}")
            await fn(page, base)
            await page.screenshot(path=str(out / f"{name}.png"))
            print("wrote", out / f"{name}.png")
            await ctx.close()
        await browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://127.0.0.1:8811")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--only")
    a = ap.parse_args()
    asyncio.run(main(a.base, a.out, a.only))
