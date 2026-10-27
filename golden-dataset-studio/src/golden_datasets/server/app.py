"""FastAPI app: the JSON API under /api and the built web app (web/dist) everywhere else."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


def create_app(root: str | None = None) -> FastAPI:
    app = FastAPI(title="CTDL Golden Dataset Studio")
    app.state.root_uri = root

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "root": root}

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

    uvicorn.run(create_app(args.root), host=args.host, port=args.port, log_level="info")
    return 0
