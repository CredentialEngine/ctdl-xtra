"""Fetch one catalog page with retries. Playwright is the live download strategy."""

from __future__ import annotations

from typing import Any, Callable

from common.clock import utc_timestamp
from common.polite import PoliteLimiter
from implementations.engine import load_engine

load_engine()

from config import BROWSER_USER_AGENT
from html_text import slug_url
from normalize import normalize_html, sha256_bytes, sha256_text


def fetch_html_playwright(url: str) -> tuple[str, dict[str, Any]]:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True, channel="chrome")
        except Exception:
            browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1400, "height": 1800},
            user_agent=BROWSER_USER_AGENT,
            ignore_https_errors=True,
        )
        page = context.new_page()
        page.set_default_timeout(60000)
        try:
            try:
                response = page.goto(url, wait_until="load", timeout=60000)
            except PlaywrightTimeout:
                response = page.goto(
                    url, wait_until="domcontentloaded", timeout=60000
                )
        except PlaywrightError as exc:
            browser.close()
            raise RuntimeError(str(exc).splitlines()[0]) from None
        html = page.content()
        status = response.status if response is not None else None
        final_url = page.url
        browser.close()
    return html, {
        "requested_url": url,
        "final_url": final_url,
        "http_status": status,
        "retrieved_at": utc_timestamp(),
        "capture": "playwright",
        "media_type": "text/html",
    }


def download_one(
    url: str,
    *,
    limiter: PoliteLimiter,
    fetch_fn: Callable[[str], tuple[str, dict[str, Any]]],
    max_retries: int,
) -> tuple[str, dict[str, Any], str, str]:
    last_error: Exception | None = None
    html = ""
    meta: dict[str, Any] = {}
    for attempt in range(max_retries):
        try:
            with limiter.occupy():
                html, meta = fetch_fn(url)
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            if attempt + 1 < max_retries:
                limiter.backoff_sleep(attempt)
    if last_error is not None:
        raise last_error
    text = normalize_html(html)
    meta = {
        **meta,
        "snapshot_sha256": sha256_bytes(html.encode("utf-8")),
        "normalized_text_sha256": sha256_text(text),
        "normalized_chars": len(text),
        "stem": slug_url(url),
    }
    return html, meta, text, slug_url(url)
