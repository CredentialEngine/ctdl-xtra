"""Copy existing HTML freezes or capture live pages into the v4 snapshot dir."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from config import ROOT as REPO_ROOT, SNAPSHOT_DIR
from active import active_slots, unique_pages
from normalize import sha256_bytes


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def snapshot_path(stem: str) -> Path:
    return SNAPSHOT_DIR / f"{stem}.html"


def meta_path(stem: str) -> Path:
    return SNAPSHOT_DIR / f"{stem}.meta.json"


def write_snapshot(html: str, *, dest: Path, meta: dict) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = html.encode("utf-8")
    dest.write_bytes(data)
    payload = dict(meta)
    payload["snapshot_sha256"] = sha256_bytes(data)
    payload["bytes"] = len(data)
    meta_path(dest.stem if dest.name.endswith(".html") else dest.name).write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _existing_html(slot) -> Path | None:
    candidates = []
    if slot.copy_html is not None:
        candidates.append(Path(slot.copy_html))
    candidates.append(SNAPSHOT_DIR / f"{slot.stem}.html")
    candidates.append(REPO_ROOT / "snapshots" / f"{slot.stem}.html")
    candidates.append(
        REPO_ROOT / "golden_sets" / "sources" / "html" / f"{slot.stem}.html" / f"{slot.stem}.html"
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def copy_existing() -> list[dict]:
    rows = []
    for slot in unique_pages():
        src = _existing_html(slot)
        if src is None:
            continue
        html = src.read_text(encoding="utf-8", errors="replace")
        dest = snapshot_path(slot.stem)
        retrieved = slot.retrieved_at
        sibling_meta = src.parent / f"{src.stem}.meta.json"
        if (not retrieved) and sibling_meta.is_file():
            retrieved = json.loads(sibling_meta.read_text(encoding="utf-8")).get("retrieved_at")
        if not retrieved:
            retrieved = _now()
        write_snapshot(
            html,
            dest=dest,
            meta={
                "requested_url": slot.requested_url,
                "final_url": slot.requested_url,
                "source_kind": "html",
                "media_type": "text/html",
                "retrieved_at": retrieved,
                "copied_from": str(src),
                "http_status": None,
                "content_type": "text/html",
                "redirect_chain": [],
                "etag": None,
                "last_modified": None,
                "capture": "copied_existing_html_freeze",
            },
        )
        rows.append({"stem": slot.stem, "status": "copied", "path": str(dest)})
        print(f"copied {slot.stem}", flush=True)
    return rows


def fetch_missing() -> list[dict]:
    missing = [slot for slot in unique_pages() if _existing_html(slot) is None]
    if not missing:
        return []
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "Playwright is required to freeze missing URLs. "
            "Install with: pip install playwright && playwright install chrome"
        ) from exc

    rows: list[dict] = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, channel="chrome")
        except Exception:
            browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1400, "height": 1800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            ignore_https_errors=True,
        )
        page = context.new_page()
        page.set_default_timeout(60000)
        for i, slot in enumerate(missing, start=1):
            print(f"[{i}/{len(missing)}] fetch {slot.requested_url}", flush=True)
            status = "ok"
            error = None
            html = ""
            http_status = None
            content_type = None
            final_url = slot.requested_url
            redirects: list[str] = []
            try:
                try:
                    resp = page.goto(slot.requested_url, wait_until="networkidle", timeout=60000)
                except PlaywrightTimeout:
                    resp = page.goto(slot.requested_url, wait_until="load", timeout=60000)
                    page.wait_for_timeout(1500)
                if resp is not None:
                    http_status = resp.status
                    content_type = resp.headers.get("content-type")
                    final_url = resp.url
                    redirects = [r.url for r in resp.request.redirected_from and [] or []]
                page.wait_for_timeout(800)
                html = page.content()
                write_snapshot(
                    html,
                    dest=snapshot_path(slot.stem),
                    meta={
                        "requested_url": slot.requested_url,
                        "final_url": final_url,
                        "source_kind": "html",
                        "media_type": "text/html",
                        "retrieved_at": _now(),
                        "copied_from": None,
                        "http_status": http_status,
                        "content_type": content_type,
                        "redirect_chain": redirects,
                        "etag": None,
                        "last_modified": None,
                        "capture": "playwright_page_content",
                    },
                )
            except Exception as exc:  # noqa: BLE001
                status = "error"
                error = str(exc)
            rows.append(
                {
                    "stem": slot.stem,
                    "url": slot.requested_url,
                    "status": status,
                    "error": error,
                    "http_status": http_status,
                }
            )
            print(f"  -> {status} http={http_status}", flush=True)
        browser.close()
    return rows


def freeze_all() -> dict:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    copied = copy_existing()
    fetched = fetch_missing()
    report = {
        "copied": copied,
        "fetched": fetched,
        "unique_pages": len(unique_pages()),
        "records": len(active_slots()),
    }
    (SNAPSHOT_DIR / "freeze_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report
