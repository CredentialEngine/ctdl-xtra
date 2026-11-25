"""FastAPI app: the JSON API under /api and the built web app (web/dist) everywhere else.

Each work stream owns one router module; `ROUTERS` lists them. A missing module is skipped, so streams can land
independently.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from .. import telemetry
from . import auth
from .jobs import ScoreJobs
from .state import ClassParam, Studio

WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"
ROUTERS = [
    "golden_datasets.server.routes_pages",    # W1: rendered pages, HTML view, archived assets
    "golden_datasets.server.routes_agent",    # AI runs on K2 (before review: rules/picker isn't a rule id)
    "golden_datasets.server.routes_review",   # W4: catalogs, rules, rows, annotations, records
    "golden_datasets.server.routes_compare",  # W5: comparisons
    "golden_datasets.server.routes_prompt",   # W6: prompt text
    "golden_datasets.server.routes_golden",   # W7: golden publication
    "golden_datasets.server.routes_files",    # storage files: a debugging view of what the Studio keeps
    "golden_datasets.server.routes_profiles", # profiles: who is reviewing (name + role), shared on the root
    "golden_datasets.server.routes_crawls",   # Add a catalog: search xtra-cli's crawls, add one
    "golden_datasets.server.routes_evals",    # Evals: extract outputs and scores (docs/qrspi/evals)
    "golden_datasets.server.routes_findings", # findings, property status and discussion (learning-programs Phase 6)
]


def cmd_serve(args) -> int:
    import uvicorn

    from ..review import tune_gc

    app = create_app(args.root, args.azure_root, args.crawls_root, agent_settings(args))
    tune_gc()  # fewer collections over the big snapshots (review.GC_THRESHOLDS)
    app.state.studio.warm_crawls()
    app.state.studio.warm_home()  # the home page's table, so the first visit after a restart doesn't work it out
    start_background_loops(app)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def create_app(root: str, azure_root: str | None = None, crawls_root: str | None = None,
               agent: dict | None = None) -> FastAPI:
    app = FastAPI(title="CTDL Golden Dataset Studio")
    app.state.studio = Studio(root, azure_root, crawls_root, agent)
    app.state.scores = ScoreJobs()  # scores run as durable jobs, one per catalog at a time
    add_middleware(app)
    add_health(app)
    include_routers(app)
    telemetry.install(app)  # traces, only when OTEL_EXPORTER_OTLP_*ENDPOINT is set (telemetry.py)
    if WEB_DIST.exists():
        serve_web(app)
    return app


def agent_settings(args) -> dict:
    import os

    return {"k2_url": args.k2_url, "k2_key": os.environ.get("GOLDEN_DATASETS_K2_KEY"), "k2_agent": args.k2_agent,
            "minutes": args.agent_run_minutes, "prompt_users": args.prompt_users, "max_runs": args.k2_max_runs}


def start_background_loops(app: FastAPI) -> None:
    import threading

    # AI runs: start waiting runs, watch their K2 sessions, end them (every 5 s, never inside a request)
    threading.Thread(target=app.state.studio.queue.loop, args=(threading.Event(),), name="agent-runs",
                     daemon=True).start()
    # scores: running ones left by a restart become interrupted, then new extract outputs and pending scores
    threading.Thread(target=app.state.scores.loop, args=(app.state.studio, threading.Event()), name="scores",
                     daemon=True).start()


def add_middleware(app: FastAPI) -> None:
    app.add_middleware(GZipMiddleware, minimum_size=2048)  # rows, compare and rendered pages compress ~5-20x
    app.add_middleware(ClassParam)  # `?class=`: the class every route's context is for (Course by default)
    auth.install(app)  # the shared password, when the environment sets one


def add_health(app: FastAPI) -> None:
    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "root": app.state.studio.root.uri}


def include_routers(app: FastAPI) -> None:
    for name in ROUTERS:
        try:
            module = importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name != name:
                raise
            continue
        app.include_router(module.router)


def serve_web(app: FastAPI) -> None:
    @app.get("/{path:path}", include_in_schema=False)
    def web(path: str):
        target = WEB_DIST / path
        if path and target.is_file() and target.name != "index.html":
            return FileResponse(target)
        page = telemetry.browser_page(WEB_DIST / "index.html")  # the app's page, plus its telemetry config if on
        return FileResponse(WEB_DIST / "index.html") if page is None else HTMLResponse(page)
