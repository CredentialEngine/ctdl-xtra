"""Server-wide state: the storage root and one cached `Ctx` per catalog.

Route modules get it with `studio(request)` and a catalog's context with `studio(request).ctx(catalog)`.
"""

from __future__ import annotations

import threading

from fastapi import HTTPException, Request

from ..catalogs import resolve
from ..context import Ctx
from ..storage import Root, open_root


class Studio:
    def __init__(self, root: Root | str, azure_root: str | None = None, crawls_root: str | None = None,
                 agent: dict | None = None):
        from ..cli import DEFAULT_AZURE_ROOT
        from ..crawls import default_crawls_root

        self.root = open_root(root)
        # where the Azure version of the prompt points Claude (the root itself when the Studio serves Azure)
        self.azure_root = self.root.uri if self.root.uri.startswith("azure://") else (azure_root or DEFAULT_AZURE_ROOT)
        self._ctx: dict[str, Ctx] = {}
        self._lock = threading.Lock()
        self.cache: dict = {}  # route modules may memoize derived data here, keyed by tuples
        # where xtra-cli's crawls are (Add a catalog searches it) and the catalogs being added: {folder: progress}
        self.crawls_root = crawls_root or default_crawls_root(self.root)
        self.adding: dict[str, dict] = {}
        # runs on the remote agent (agent_runs.py, routes_agent.py): {k2_url, k2_key, k2_agent, minutes, prompt_users}
        from ..agent_runs import K2
        agent = agent or {}
        self.prompt_users: list[str] = [n.strip() for n in agent.get("prompt_users", "").split(",") if n.strip()]
        self.agent_minutes: int = agent.get("minutes", 90)
        self.k2: K2 | None = None
        self.agent_off: str | None = None  # why runs are off, for the config route
        if not (agent.get("k2_url") and agent.get("k2_key")):
            self.agent_off = "no K2 server configured (--k2-url and GOLDEN_DATASETS_K2_KEY)"
        elif not self.root.uri.startswith("azure://"):
            self.agent_off = "the agent reports to the shared Azure root, and this Studio serves another root"
        else:
            self.k2 = K2(agent["k2_url"], agent["k2_key"], agent.get("k2_agent") or "golden-rules")

    def warm_crawls(self) -> None:
        """List the crawls once in the background, so Add a catalog opens fast (reading each crawl's name from its
        pages takes ~15 s the first time)."""
        def run() -> None:
            from .routes_crawls import _list

            try:
                _list(self)
            except Exception as exc:  # noqa: BLE001 — the modal lists them itself and shows any error
                print(f"listing crawls: {exc}")

        threading.Thread(target=run, name="warm-crawls", daemon=True).start()

    def ctx(self, catalog: str) -> Ctx:
        folder = resolve(catalog)
        with self._lock:
            if folder not in self._ctx:
                self._ctx[folder] = Ctx(self.root, folder, manifest_ttl=3.0)
            return self._ctx[folder]


def studio(request: Request) -> Studio:
    return request.app.state.studio


def not_found(msg: str) -> HTTPException:
    return HTTPException(status_code=404, detail=msg)
