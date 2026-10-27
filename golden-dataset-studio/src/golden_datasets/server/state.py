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
    def __init__(self, root: Root | str, azure_root: str | None = None, crawls_root: str | None = None):
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
