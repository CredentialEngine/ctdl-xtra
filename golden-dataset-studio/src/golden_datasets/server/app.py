"""FastAPI app: the JSON API under /api and the built web app (web/dist) everywhere else.

Each work stream owns one router module; `ROUTERS` lists them. A missing module is skipped, so streams can land
independently.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse

from . import auth
from .state import Studio

WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"
ROUTERS = [
    "golden_datasets.server.routes_pages",    # W1: rendered pages, HTML view, archived assets
    "golden_datasets.server.routes_review",   # W4: catalogs, rules, rows, annotations, records
    "golden_datasets.server.routes_compare",  # W5: comparisons
    "golden_datasets.server.routes_prompt",   # W6: prompt text
    "golden_datasets.server.routes_golden",   # W7: golden publication
    "golden_datasets.server.routes_files",    # storage files: a debugging view of what the Studio keeps
    "golden_datasets.server.routes_profiles", # profiles: who is reviewing (name + role), shared on the root
    "golden_datasets.server.routes_crawls",   # Add a catalog: search xtra-cli's crawls, add one
]


def create_app(root: str, azure_root: str | None = None, crawls_root: str | None = None) -> FastAPI:
    app = FastAPI(title="CTDL Golden Rules Studio")
    app.state.studio = Studio(root, azure_root, crawls_root)
    app.add_middleware(GZipMiddleware, minimum_size=2048)  # rows, compare and rendered pages compress ~5-20x
    auth.install(app)  # the shared password, when the environment sets one

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "root": app.state.studio.root.uri}

    for name in ROUTERS:
        try:
            module = importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name != name:
                raise
            continue
        app.include_router(module.router)

    if WEB_DIST.exists():
        @app.get("/{path:path}", include_in_schema=False)
        def web(path: str):
            target = WEB_DIST / path
            if path and target.is_file():
                return FileResponse(target)
            return FileResponse(WEB_DIST / "index.html")

    return app


def cmd_serve(args) -> int:
    import uvicorn

    app = create_app(args.root, args.azure_root, args.crawls_root)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0
