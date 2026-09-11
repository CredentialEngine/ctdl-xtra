"""Copy existing HTML freezes or capture live pages into a dated cache.

Writes cache/{yyyy-mm-dd}/{stem}.html. Refuses to overwrite. A rerun reuses
an older dated copy (or legacy snapshots/) instead of clobbering it.

Optional XTRA_CACHE_URL: after a successful local write, upload the same
relative path. Unset means local only.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from config import BROWSER_USER_AGENT, PACK, REPO_ROOT, SNAPSHOT_DIR, env_get
from active import active_slots, unique_pages
from normalize import sha256_bytes

_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ENGINE = Path(__file__).resolve().parent


def portable_path(path: Path) -> str:
    """Pack- or repo-relative POSIX path. Never a machine home path."""
    path = Path(path).absolute()
    for root in (PACK.absolute(), _ENGINE, _ENGINE.parent, REPO_ROOT):
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            continue
    return path.name


def redirect_urls(resp) -> list[str]:
    """URLs that redirected before the final response. Oldest first."""
    if resp is None:
        return []
    req = getattr(resp, "request", None)
    cur = getattr(req, "redirected_from", None) if req is not None else None
    chain: list[str] = []
    while cur is not None:
        url = getattr(cur, "url", None)
        if url:
            chain.append(url)
        cur = getattr(cur, "redirected_from", None)
    chain.reverse()
    return chain


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def cache_root() -> Path:
    return PACK / "cache"


def new_snapshot_path(stem: str, *, day: str | None = None) -> Path:
    return cache_root() / (day or utc_day()) / f"{stem}.html"


def find_cached_html(stem: str) -> Path | None:
    root = cache_root()
    if root.is_dir():
        days = sorted(
            (p for p in root.iterdir() if p.is_dir() and _DAY.match(p.name)),
            reverse=True,
        )
        for day_dir in days:
            path = day_dir / f"{stem}.html"
            if path.is_file():
                return path
    legacy = SNAPSHOT_DIR / f"{stem}.html"
    if legacy.is_file():
        return legacy
    return None


def snapshot_path(stem: str) -> Path:
    """Existing dated/legacy freeze, or today's cache path if none yet."""
    return find_cached_html(stem) or new_snapshot_path(stem)


def meta_path_for(html_path: Path) -> Path:
    return html_path.parent / f"{html_path.stem}.meta.json"


def meta_path(stem: str) -> Path:
    return meta_path_for(snapshot_path(stem))


def snapshot_rel(stem: str) -> str:
    return portable_path(snapshot_path(stem))


def maybe_upload_blob(dest: Path) -> None:
    base = env_get("XTRA_CACHE_URL")
    if not base or not dest.is_file():
        return
    try:
        rel = dest.absolute().relative_to(PACK.absolute()).as_posix()
    except ValueError:
        rel = f"{utc_day()}/{dest.name}"
    blob_url = base.rstrip("/") + "/" + rel
    try:
        from azure.storage.blob import BlobClient
    except ImportError:
        print(
            "XTRA_CACHE_URL is set but azure-storage-blob is not installed; "
            f"kept local {dest}",
            file=sys.stderr,
        )
        return
    try:
        client = BlobClient.from_blob_url(blob_url)
        with dest.open("rb") as fh:
            client.upload_blob(fh, overwrite=False)
        print(f"uploaded {rel}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"blob upload skipped ({exc})", file=sys.stderr)


def write_snapshot(html: str, *, dest: Path, meta: dict) -> bool:
    """Write HTML + sidecar meta. Returns False if dest already exists."""
    if dest.exists():
        print(f"refuse overwrite {dest}", flush=True)
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = html.encode("utf-8")
    dest.write_bytes(data)
    payload = dict(meta)
    payload["snapshot_sha256"] = sha256_bytes(data)
    payload["bytes"] = len(data)
    meta_path_for(dest).write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    maybe_upload_blob(dest)
    return True


def _existing_html(slot) -> Path | None:
    found = find_cached_html(slot.stem)
    if found is not None:
        return found
    candidates = []
    if slot.copy_html is not None:
        candidates.append(Path(slot.copy_html))
    candidates.append(SNAPSHOT_DIR / f"{slot.stem}.html")
    candidates.append((REPO_ROOT / "handoff" / "golden_set_v4" / "snapshots" / f"{slot.stem}.html").absolute())
    candidates.append(
        (REPO_ROOT / "golden_sets" / "sources" / "html" / f"{slot.stem}.html" / f"{slot.stem}.html").absolute()
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
        dest = snapshot_path(slot.stem)
        if dest.is_file():
            rows.append({"stem": slot.stem, "status": "reused", "path": portable_path(dest)})
            print(f"reused {dest}", flush=True)
            continue
        html = src.read_text(encoding="utf-8", errors="replace")
        retrieved = slot.retrieved_at
        sibling_meta = src.parent / f"{src.stem}.meta.json"
        if (not retrieved) and sibling_meta.is_file():
            retrieved = json.loads(sibling_meta.read_text(encoding="utf-8")).get("retrieved_at")
        if not retrieved:
            retrieved = _now()
        wrote = write_snapshot(
            html,
            dest=dest,
            meta={
                "requested_url": slot.requested_url,
                "final_url": slot.requested_url,
                "source_kind": "html",
                "media_type": "text/html",
                "retrieved_at": retrieved,
                "copied_from": portable_path(src),
                "http_status": None,
                "content_type": "text/html",
                "redirect_chain": [],
                "etag": None,
                "last_modified": None,
                "capture": "copied_existing_html_freeze",
            },
        )
        rows.append(
            {
                "stem": slot.stem,
                "status": "copied" if wrote else "refused",
                "path": portable_path(dest),
            }
        )
        print(f"{'copied' if wrote else 'refused'} {slot.stem}", flush=True)
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
            user_agent=BROWSER_USER_AGENT,
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
            dest = snapshot_path(slot.stem)
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
                    redirects = redirect_urls(resp)
                page.wait_for_timeout(800)
                html = page.content()
                wrote = write_snapshot(
                    html,
                    dest=dest,
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
                if not wrote:
                    status = "refused"
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
                    "path": portable_path(dest),
                }
            )
            print(f"  -> {status} http={http_status}", flush=True)
        browser.close()
    return rows


def freeze_all() -> dict:
    cache_root().mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    copied = copy_existing()
    fetched = fetch_missing()
    report = {
        "copied": copied,
        "fetched": fetched,
        "unique_pages": len(unique_pages()),
        "records": len(active_slots()),
    }
    (cache_root() / "freeze_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report
