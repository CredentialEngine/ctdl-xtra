"""FastAPI app: JSON API for the review UI plus the built React bundle."""

from __future__ import annotations

import io
import json
import os
import re
import threading
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from .catalogs import CatalogIndex, cid_of, summarize
from .exports import (
    feedback_markdown,
    flagged_markdown,
    golden_for_page,
    labels_for_page,
    property_terms,
)
from .extract import (
    baseline_decisions,
    latest_extraction,
    latest_flags,
    review_sessions,
)
from .golden import NothingToSave, save_golden, saved_pages
from .review import FLAG_SCOPES, NOTE_SCOPES, REASONS, EventError, ReviewSession
from .runs import ROOT_ID, CrawlRun, split_page
from .store import Store, open_store
from .template import ConfigMissing, load_template
from .views import ExtractionView

PROJECT = Path(__file__).resolve().parents[2]
# In a container the built web app is copied somewhere fixed and named by this variable.
WEB_DIST = Path(os.environ.get("REVIEW_UI_WEB_DIST") or PROJECT / "web" / "dist")

# Pages keep their own stylesheets and inline styles; this only adds a margin and the
# highlight, with !important so the page's CSS can't override it. A ruleset's
# ``pane_css`` is appended for platform quirks (e.g. content hidden behind a click).
_PANE_CSS = """
body{margin:14px!important;background:#fff!important}
.xtra-hl{outline:3px solid #d97706!important;outline-offset:2px;
background:rgba(251,191,36,.35)!important}
"""
_PANE_JS = """
addEventListener('message',function(e){
  var m=e.data||{}; if(m.type!=='highlight')return;
  document.querySelectorAll('.xtra-hl').forEach(function(n){n.classList.remove('xtra-hl')});
  var first=null;
  (m.paths||[]).forEach(function(p){try{var n=document.querySelector(p);
    if(n){n.classList.add('xtra-hl');first=first||n}}catch(_){}});
  if(first)first.scrollIntoView({block:'center',behavior:'smooth'});
});
parent.postMessage({type:'ready'},'*');
"""


def _slug_title(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"-fall-\d{4}$|-spring-\d{4}$", "", slug)
    return slug.replace("-", " ").replace(",", " ").title()


class CatalogNotReady(RuntimeError):
    """The catalog has no extraction to review yet."""


class AppState:
    def __init__(
        self,
        store: Store,
        run: CrawlRun,
        extraction_id: str | None,
        review_id: str | None,
        new_review: bool,
        golden_store: Store | None = None,
    ):
        self.run = run
        self.store = store
        self.golden_store = golden_store or store
        self.lock = threading.Lock()
        extraction_id = extraction_id or latest_extraction(self.store, run.key)
        if not extraction_id:
            raise CatalogNotReady(
                f"No extraction for this run yet. Run `review-ui-v2 extract --run {run.key}` first."
            )
        self.view = ExtractionView(self.store, run.key, extraction_id)
        self.properties = load_template(store)
        self.stem_of_url = {row["url"]: stem for stem, row in self.view.pages.items()}
        if review_id:
            self.review = ReviewSession.open(self.store, run.key, review_id)
        else:
            existing = [
                s
                for s in review_sessions(self.store, run.key)
                if self.store.read_json(f"{run.key}/review-ui/{s}/session.json")[
                    "extraction_id"
                ]
                == extraction_id
            ]
            if existing and not new_review:
                self.review = ReviewSession.open(self.store, run.key, existing[-1])
            else:
                self.new_review()

    def new_review(self) -> ReviewSession:
        self.review = ReviewSession.create(
            self.store,
            self.run.key,
            self.view.extraction_id,
            carry_over=baseline_decisions(self.store, self.run.key),
            carry_flags=latest_flags(self.store, self.run.key),
        )
        return self.review

    def page_list(self) -> list[dict]:
        sample = self.view.sample() or [
            {"stem": s, "url": r["url"], "page_type": r["page_type"], "reason": ""}
            for s, r in self.view.pages.items()
        ]
        out = []
        for entry in sample:
            page = self.view.page(entry["stem"])
            title = self.view.pages[entry["stem"]].get("title") or _slug_title(
                page["url"]
            )
            if page["page_type"] == "course" and len(page["records"]) > 1:
                title = f"{title} · {len(page['records'])} courses"
            out.append(
                {
                    **entry,
                    "title": title,
                    "labels": sorted({l["label"] for l in page["labels"]}),
                    "record_count": len(page["records"]),
                    "keys": self.view.item_keys([entry["stem"]]),
                }
            )
        return out


def create_app(
    root: Store | Path | str,
    default_run: CrawlRun | None = None,
    extraction_id: str | None = None,
    review_id: str | None = None,
    new_review: bool = False,
    golden_root: Store | Path | str | None = None,
) -> FastAPI:
    """One app, many catalogs. ``default_run`` (from ``--run``) skips the landing page.

    Each catalog lives under ``/api/c/<cid>/``, so two browsers can review different
    catalogs at once and a click can never land in the wrong review.
    """
    store = open_store(root)
    golden_store = open_store(golden_root, cache=False) if golden_root else store
    index = CatalogIndex(store, default_run)
    index.all()  # fail fast, with a clear message, if the field template is not published
    default_cid = cid_of(default_run) if default_run else None
    states: dict[str, AppState] = {}
    states_lock = threading.Lock()
    if default_run:  # fail fast, with a clear message, when --run is not reviewable
        states[default_cid] = AppState(
            store, default_run, extraction_id, review_id, new_review, golden_store
        )

    def S(cid: str) -> AppState:
        """The catalog's state, built on first use (which may start a review session)."""
        catalog = index.get(cid)
        if catalog is None:
            raise HTTPException(404, f"unknown catalog {cid}")
        with states_lock:
            if cid not in states:
                try:
                    states[cid] = AppState(
                        store, catalog.run, None, None, False, golden_store
                    )
                except CatalogNotReady as exc:
                    raise HTTPException(409, str(exc)) from exc
            return states[cid]

    app = FastAPI(title="xTRA review")
    app.add_middleware(
        GZipMiddleware, minimum_size=1000
    )  # saved pages are ~600 KB of CSS

    try:
        from azure.core.exceptions import AzureError
    except ImportError:  # azure extra not installed
        AzureError = None

    if AzureError is not None:
        from .azure_store import explain_azure_error

        @app.exception_handler(AzureError)
        async def _azure_error(_, exc: AzureError):
            message = (
                explain_azure_error(exc, str(root)) or f"Azure storage error: {exc}"
            )
            return JSONResponse({"detail": message}, status_code=502)

    @app.exception_handler(ConfigMissing)
    async def _config_missing(_, exc: ConfigMissing):
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.exception_handler(EventError)
    async def _event_error(_, exc: EventError):
        return JSONResponse({"error": str(exc)}, status_code=422)

    @app.get("/healthz")
    def healthz() -> dict:
        """Liveness for a container platform. Deliberately touches no storage, so a slow
        or unreachable Azure never gets the container restarted."""
        return {"status": "ok"}

    @app.get("/api/catalogs")
    def list_catalogs() -> dict:
        return {
            "catalogs": [summarize(store, c) for c in index.all()],
            "default": default_cid,
        }

    def stem_or_404(state: AppState, stem: str) -> str:
        if stem not in state.view.pages:
            raise HTTPException(404, f"unknown page {stem}")
        return stem

    def full_state(state: AppState) -> dict:
        report = state.view.report()
        ruleset = state.view.ruleset()
        return {
            "run": {"key": state.run.key, "catalog_folder": state.run.catalog_folder},
            "extraction": {
                "id": state.view.extraction_id,
                "ruleset": report["ruleset"],
                "records": report["records"],
                "regression": report["regression"],
            },
            "review": state.review.state(),
            "reviews": review_sessions(state.store, state.run.key),
            "pages": state.page_list(),
            "properties": [p.__dict__ for p in state.properties],
            "label_vocabulary": ruleset.get("label_vocabulary", []),
            "reasons": list(REASONS),
            "note_scopes": list(NOTE_SCOPES),
            "flag_scopes": list(FLAG_SCOPES),
            "golden": saved_pages(
                state.golden_store, state.run
            ),  # pages with a saved dataset
        }

    @app.get("/api/c/{cid}/state")
    def get_state(cid: str) -> dict:
        return full_state(S(cid))

    @app.get("/api/c/{cid}/pages/{stem}")
    def get_page(cid: str, stem: str) -> dict:
        state = S(cid)
        return state.view.page(stem_or_404(state, stem))

    def _main_html(state: AppState, stem: str):
        html = state.store.read_text(f"{state.run.key}/pages/{stem}.html")
        root = state.view.ruleset()["content_root"]
        main, assets = split_page(html, root)
        if main is None:
            raise HTTPException(404, f"page has nothing matching {root!r}")
        return main, assets

    @app.get("/api/c/{cid}/pages/{stem}/content", response_class=HTMLResponse)
    def page_content(cid: str, stem: str) -> str:
        state = S(cid)
        stem_or_404(state, stem)
        main, assets = _main_html(state, stem)
        url = state.view.pages[stem]["url"]
        soup = BeautifulSoup(f'<div id="{ROOT_ID}">{main}</div>', "lxml")
        for tag in soup.find_all(["script", "iframe", "object", "embed"]):
            tag.decompose()
        for tag in soup.find_all(True):
            for attr in [a for a in tag.attrs if a.lower().startswith("on")]:
                del tag.attrs[attr]
        base = urljoin(url, assets.base_href or "")
        links = "".join(
            f'<link rel="stylesheet" href="{urljoin(base, href)}">'
            for href in assets.stylesheets
        )
        inline = "".join(f"<style>{css}</style>" for css in assets.inline_styles)
        body = soup.body.decode_contents() if soup.body else str(soup)
        return (
            f'<!doctype html><html><head><meta charset="utf-8">'
            f'<base href="{base}" target="_blank">{links}{inline}'
            f"<style>{_PANE_CSS}{state.view.ruleset().get('pane_css', '')}</style></head>"
            f"<body>{body}<script>{_PANE_JS}</script></body></html>"
        )

    @app.get("/api/c/{cid}/pages/{stem}/source")
    def page_source(cid: str, stem: str) -> dict:
        state = S(cid)
        stem_or_404(state, stem)
        main, _ = _main_html(state, stem)
        return {"html": BeautifulSoup(main, "lxml").body.prettify()}

    @app.post("/api/c/{cid}/events")
    def post_event(cid: str, event: dict[str, Any]) -> dict:
        state = S(cid)
        with state.lock:
            saved = state.review.apply(event)
            return {"event": saved, "counts": state.review.counts()}

    @app.post("/api/c/{cid}/reviews")
    def start_review(cid: str) -> dict:
        state = S(cid)
        with state.lock:
            state.new_review()
        return full_state(state)

    @app.post("/api/c/{cid}/reviews/{review_id}/open")
    def open_review(cid: str, review_id: str) -> dict:
        state = S(cid)
        if review_id not in review_sessions(state.store, state.run.key):
            raise HTTPException(404, "unknown review")
        with state.lock:
            state.review = ReviewSession.open(state.store, state.run.key, review_id)
        return full_state(state)

    def _attach(content: Any, filename: str) -> Response:
        return Response(
            json.dumps(content, indent=2, ensure_ascii=False),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    def _golden(state: AppState, stem: str, terms: dict | None = None) -> list[dict]:
        return golden_for_page(
            state.view,
            state.review.decisions,
            stem,
            state.review.review_id,
            state.review.flags,
            terms,
        )

    @app.post("/api/c/{cid}/golden/{stem}")
    def save_golden_dataset(cid: str, stem: str) -> dict:
        """Save the page's verified values and source HTML to the golden-sets storage."""
        state = S(cid)
        stem_or_404(state, stem)
        with state.lock:
            try:
                return save_golden(
                    state.golden_store,
                    state.store,
                    state.run,
                    state.view,
                    state.review.decisions,
                    stem,
                    state.review.review_id,
                    state.review.flags,
                    property_terms(state.store),
                    f"{state.run.key}/pages/{stem}.html",
                )
            except NothingToSave as exc:
                raise HTTPException(422, str(exc)) from exc

    @app.get("/api/c/{cid}/export/golden/{stem}.json")
    def export_golden(cid: str, stem: str) -> Response:
        state = S(cid)
        return _attach(_golden(state, stem_or_404(state, stem)), f"golden-{stem}.json")

    @app.get("/api/c/{cid}/export/labels/{stem}.json")
    def export_page_labels(cid: str, stem: str) -> Response:
        state = S(cid)
        labels = labels_for_page(
            state.view,
            state.review.decisions,
            stem_or_404(state, stem),
            state.review.flags,
        )
        return _attach(labels, f"labels-{stem}.json")

    @app.get("/api/c/{cid}/export/labels.json")
    def export_labels(cid: str) -> Response:
        state = S(cid)
        labels = [
            l
            for stem in state.review.session["sample_stems"]
            for l in labels_for_page(
                state.view, state.review.decisions, stem, state.review.flags
            )
        ]
        return _attach(labels, "labels.json")

    @app.get("/api/c/{cid}/export/golden.zip")
    def export_golden_zip(cid: str) -> Response:
        state = S(cid)
        buffer = io.BytesIO()
        terms = property_terms(state.store)  # read the template once for every page
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for stem in state.review.session["sample_stems"]:
                archive.writestr(
                    f"golden/{stem}.json",
                    json.dumps(
                        _golden(state, stem, terms), indent=2, ensure_ascii=False
                    ),
                )
        return Response(
            buffer.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="golden-sample.zip"'},
        )

    @app.get("/api/c/{cid}/export/flagged.md")
    def export_flagged(cid: str) -> Response:
        state = S(cid)
        text = flagged_markdown(
            state.view, state.review.flags, state.run, state.review.review_id
        )
        return PlainTextResponse(
            text,
            headers={
                "Content-Disposition": 'attachment; filename="flagged-for-review.md"'
            },
        )

    @app.get("/api/c/{cid}/export/feedback.md")
    def export_feedback(cid: str) -> Response:
        state = S(cid)
        text = feedback_markdown(
            state.store, state.run, state.view, state.review.state(), state.stem_of_url
        )
        state.store.write_text(f"{state.review.base}/feedback.md", text)
        return PlainTextResponse(
            text,
            headers={"Content-Disposition": 'attachment; filename="feedback.md"'},
        )

    if WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
    return app
