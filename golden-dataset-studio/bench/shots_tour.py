"""Screenshots of every step of the tour (spec §7.8) in headless Chromium, 1440×900 at 2x.

    uv run --with playwright python bench/shots_tour.py --base http://127.0.0.1:8015 --out <dir> [--root <studio root>]

Needs a running Studio (`golden-datasets serve`) with AVC and a built web app. Serve a *copy* of the demo root
(`golden-datasets sync --from .data/root-demo --to <tmp> -c avc --pages link`). The tour opens by itself on a fresh
browser; each step is reached with → and shot once it has settled. Afterwards it checks that Esc returns to where
the reader was and, given `--root`, that the tour wrote nothing (the annotation logs are byte-for-byte unchanged).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from pathlib import Path

CAT = "avc"
START = f"#/c/{CAT}/rules"


def fingerprint(root: Path | None) -> str | None:
    if root is None:
        return None
    h = hashlib.sha256()
    for p in sorted(root.rglob("annotations*.jsonl")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


async def settle(page, extra: int) -> str:
    await page.wait_for_function(
        "() => { const t = document.querySelector('.tour'); return t && t.dataset.state !== 'waiting'; }",
        timeout=20000)
    await page.wait_for_timeout(extra)
    return await page.evaluate("() => document.querySelector('.tour').dataset.step + ' · ' + document.querySelector('.tour').dataset.state")


async def main(base: str, out: Path, root: Path | None) -> None:
    from playwright.async_api import async_playwright

    out.mkdir(parents=True, exist_ok=True)
    before = fingerprint(root)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page = await ctx.new_page()
        page.on("pageerror", lambda e: print(f"  page error: {e}"))
        await page.goto(f"{base}/{START}")
        await page.wait_for_selector(".tour .tour-count", timeout=20000)
        n = await page.evaluate("() => +document.querySelector('.tour-count').textContent.split(' of ')[1]")
        for i in range(1, n + 1):
            # the page pane loads a saved page; Compare and the locator view load their own data
            state = await settle(page, 2600)
            name = f"tour-{i:02d}.png"
            await page.screenshot(path=str(out / name))
            print(f"wrote {out / name}  ({state}, {await page.evaluate('location.hash')})")
            if i < n:
                await page.keyboard.press("ArrowRight")
                await page.wait_for_timeout(250)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(600)
        back = await page.evaluate("location.hash")
        gone = await page.evaluate("!document.querySelector('.tour')")
        print(f"after Esc: tour closed={gone}, route={back} (started at {START})")
        await page.reload()
        await page.wait_for_timeout(1500)
        print(f"after reload: tour opened by itself again={await page.evaluate('!!document.querySelector(\".tour\")')}")
        await ctx.close()
        await browser.close()
    after = fingerprint(root)
    if root is not None:
        print("annotations unchanged" if before == after else "ANNOTATIONS CHANGED: the tour wrote data")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://127.0.0.1:8015")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--root", type=Path, help="the served Studio root, to check the tour wrote nothing")
    a = ap.parse_args()
    asyncio.run(main(a.base, a.out, a.root))
