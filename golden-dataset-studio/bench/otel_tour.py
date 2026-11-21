"""Use the Studio like a reviewer, page by page, so a traced Studio records page views, API calls and web vitals.

    STUDIO_PASSWORD=... uv run --with playwright python bench/otel_tour.py --base <studio url> \
        --catalog marshall --catalog training-uark-edu-portal-training --rounds 3 --out <dir> [--annotate]

Each user is a browser context with its own profile (created on "Who are you?" if missing). Every page is opened
with a hard load (so it gets its own FCP, LCP and TTFB), used for a moment (rules opened, rows stepped through, a course
searched, tabs switched by clicking: soft navigations), then closed, which ends its page view and makes the browser
flush its spans and report CLS and INP. Round 1 saves a screenshot of each page. `--annotate` marks one value ✓ per
catalog and round: it writes to the Studio's root, so run it only against a scratch Studio.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

USERS = [("OTel Tester", "engineer"), ("OTel Reviewer", "sme")]
TABS = ["rules", "records", "compare", "datasets", "evals"]


async def settle(page, ms: int = 800) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:  # noqa: BLE001 - a page that keeps polling still gets its screenshot
        pass
    await page.wait_for_timeout(ms)


async def sign_in(ctx, base: str, name: str, role: str, password: str | None) -> None:
    page = await ctx.new_page()
    await page.goto(f"{base}/#/")
    await page.wait_for_selector("h1")
    if await page.locator("input[type=password]").count():
        await page.fill("input[type=password]", password or "")
        await page.click("button[type=submit]")
        await page.wait_for_selector("select")
    if await page.locator("select").count():
        await page.wait_for_function("() => !document.querySelector('select').disabled")
        names = await page.eval_on_selector_all("select option", "os => os.map(o => o.value)")
        if name in names:
            await page.select_option("select", name)
        else:
            await page.select_option("select", "__add")
            await page.fill("input[placeholder='First name']", name)
        if await page.locator(f"input[type=radio][value={role}]").count():
            await page.check(f"input[type=radio][value={role}]")
        await page.click("button[type=submit]")
    await page.wait_for_selector("main#app", timeout=20000)
    await settle(page)
    await page.close()


async def open_page(ctx, url: str):
    page = await ctx.new_page()
    page.on("pageerror", lambda e: print(f"  page error: {e}"))
    await page.goto(url)
    await settle(page)
    return page


async def shoot(page, out: Path | None, name: str) -> None:
    if out:
        await page.screenshot(path=str(out / f"{name}.png"))
        print(f"  wrote {out / name}.png")


async def rule_ids(page, catalog: str, n: int) -> list[str]:
    return await page.evaluate("""async ([c, n]) => {
        const r = await (await fetch(`/api/catalogs/${encodeURIComponent(c)}/rules`)).json();
        const ids = [];
        for (const g of r.groups || []) for (const x of g.rules || []) {
          if (x.rule_id && x.total) ids.push(x.rule_id); }
        return ids.slice(0, n); }""", [catalog, n])


async def tour(ctx, base: str, catalog: str, rnd: int, out: Path | None, annotate: bool) -> None:
    shots = out if rnd == 1 else None
    c = f"{base}/#/c/{catalog}"

    page = await open_page(ctx, f"{base}/#/")  # catalog picker
    await page.wait_for_selector(".ctab tbody tr", timeout=30000)
    await shoot(page, shots, "catalogs")
    await page.close()

    page = await open_page(ctx, f"{c}/rules")  # rules: a few rules, rows stepped through
    rules = await rule_ids(page, catalog, 3)
    for i, rid in enumerate(rules):
        await page.evaluate("h => { location.hash = h }", f"#/c/{catalog}/rules/{rid}")  # soft navigation
        await settle(page, 1200)
        for _ in range(3):
            await page.keyboard.press("j")
            await page.wait_for_timeout(400)
        if annotate and i == 0 and await page.locator(".row.on").count():
            await page.keyboard.press("1")  # ✓ on the selected value
            await settle(page)
        if i == 0:
            await shoot(page, shots, f"rules-{catalog}")
    await page.close()

    page = await open_page(ctx, f"{c}/records")  # records: search a course, open it
    box = page.locator("input.search")
    if await box.count():
        await box.fill("1")
        await settle(page)
        first = page.locator(".rec-list a, .records a, table tbody tr").first
        if await first.count():
            await first.click()
            await settle(page)
    await shoot(page, shots, f"records-{catalog}")
    await page.close()

    for tab in ("compare", "datasets", "evals"):  # hard loads
        page = await open_page(ctx, f"{c}/{tab}")
        await page.wait_for_timeout(1500)
        await shoot(page, shots, f"{tab}-{catalog}")
        await page.close()

    page = await open_page(ctx, f"{c}/rules")  # soft navigations: the top bar's tabs, clicked
    for tab in TABS[1:] + ["rules"]:
        link = page.locator(f"a[href$='/{tab}']").first
        if await link.count():
            await link.click()
            await settle(page, 1000)
    await page.close()


async def main(args) -> None:
    from playwright.async_api import async_playwright

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
    password = os.environ.get("STUDIO_PASSWORD")
    async with async_playwright() as p:
        # PLAYWRIGHT_CHROMIUM: a Chromium already on disk, when this Playwright's own isn't installed
        browser = await p.chromium.launch(executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM") or None)
        for rnd in range(1, args.rounds + 1):
            for u, (name, role) in enumerate(USERS[: args.users]):
                ctx = await browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2,
                                                ignore_https_errors=False)
                await sign_in(ctx, args.base, name, role, password)
                for catalog in args.catalog:
                    print(f"round {rnd} · {name} · {catalog}")
                    await tour(ctx, args.base, catalog, rnd if u == 0 else 0, args.out, args.annotate)
                await ctx.close()
        await browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--catalog", action="append", required=True)
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--users", type=int, default=len(USERS))
    ap.add_argument("--out", type=Path, default=None, help="screenshots of round 1 (first user)")
    ap.add_argument("--annotate", action="store_true", help="mark values ✓ (writes: scratch Studios only)")
    asyncio.run(main(ap.parse_args()))
