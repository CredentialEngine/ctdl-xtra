"""Server-wide state: the storage root and one cached `Ctx` per catalog.

Route modules get it with `studio(request)` and a catalog's context with `studio(request).ctx(catalog)`.
"""

from __future__ import annotations

import threading
from contextvars import ContextVar
from urllib.parse import parse_qs

from fastapi import HTTPException, Request

from .. import classes
from ..catalogs import resolve
from ..context import Ctx, SharedManifest
from ..storage import Root, open_root


class Studio:
    def __init__(self, root: Root | str, azure_root: str | None = None, crawls_root: str | None = None,
                 agent: dict | None = None):
        from ..cli import DEFAULT_AZURE_ROOT
        from ..crawls import default_crawls_root

        self.root = open_root(root)
        # where the Azure version of the prompt points Claude (the root itself when the Studio serves Azure)
        self.azure_root = self.root.uri if self.root.uri.startswith("azure://") else (azure_root or DEFAULT_AZURE_ROOT)
        self._ctx: dict[tuple[str, str], Ctx] = {}
        self.manifest = SharedManifest()  # one copy of the manifest for every context (context.SharedManifest)
        self._lock = threading.Lock()
        self.cache: dict = {}  # route modules may memoize derived data here, keyed by tuples
        # where xtra-cli's crawls are (Add a catalog searches it) and the catalogs being added: {folder: progress}
        self.crawls_root = crawls_root or default_crawls_root(self.root)
        self.adding: dict[str, dict] = {}
        # runs on the remote agent (agent_runs.py, routes_agent.py): {k2_url, k2_key, k2_agent, minutes, prompt_users,
        # max_runs}
        from ..agent_runs import DEFAULT_CAP, K2, Queue
        agent = agent or {}
        self.prompt_users: list[str] = [n.strip() for n in agent.get("prompt_users", "").split(",") if n.strip()]
        self.agent_minutes: int = agent.get("minutes", 90)
        self.agent_cap: int = int(agent.get("max_runs") or DEFAULT_CAP)  # runs working at once, all catalogs
        self.k2: K2 | None = None
        self.agent_off: str | None = None  # why runs are off, for the config route
        if not (agent.get("k2_url") and agent.get("k2_key")):
            self.agent_off = "no K2 server configured (--k2-url and GOLDEN_DATASETS_K2_KEY)"
        elif not self.root.uri.startswith("azure://"):
            self.agent_off = "the agent reports to the shared Azure root, and this Studio serves another root"
        else:
            self.k2 = K2(agent["k2_url"], agent["k2_key"], agent.get("k2_agent") or "golden-rules")
        self.queue = Queue(self.root, self.k2, self.agent_runs_of, self.catalog_folders, cap=self.agent_cap)

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

    def warm_home(self) -> threading.Thread:
        """Work out the home page's catalogs table for each class once, in the background, when the server starts:
        cold, it loads every catalog's latest extraction and plans its golden dataset (minutes of CPU on the biggest
        catalogs), and the first visit after a restart would wait for all of it. Then each catalog's rule list
        (`warm_rule_list`). One catalog at a time, through the same snapshot loader and caches a visit uses."""
        def run() -> None:
            from .. import telemetry
            from .routes_evals import home_summary

            for cls in classes.SLUGS:
                REQUEST_CLASS.set(cls)  # this thread's own context: routes' helpers read the class from it
                try:
                    with telemetry.span("warm.home", {"ce.class": cls}):
                        home_summary(self, cls)
                except Exception as exc:  # noqa: BLE001 — a visit works it out itself and shows any error
                    print(f"warming the home page ({cls}): {exc}")
            for folder, cls in self.catalog_folders():
                REQUEST_CLASS.set(cls)
                try:
                    with telemetry.span("warm.rules", {"ce.catalog.folder": folder, "ce.class": cls}):
                        self.warm_rule_list(folder, cls)
                except Exception as exc:  # noqa: BLE001
                    print(f"warming the rule list ({folder}, {cls}): {exc}")

        t = threading.Thread(target=run, name="warm-home", daemon=True)
        t.start()
        return t

    def warm_rule_list(self, folder: str, cls: str) -> None:
        """Work out a catalog's rule statuses and "Annotated by" counts for a class, as the Rules tab's first visit
        would (every rule's rows and row states, then the parent's: 13 s on Marshall, while the counts took 12 s
        alongside). They are kept per rule until its own annotations change, whichever snapshots stay loaded."""
        from ..review import LOADER

        ctx = self.ctx(folder, cls)
        ext = ctx.latest_extraction()
        if not ext:
            return
        rv = LOADER.review(ctx, ext)
        for rid in rv.snap.rules:
            rv.rule_status(rid)  # and its "Annotated by" counts (Review._summarize)

    def agent_runs(self, catalog: str):
        """A catalog's AI runs, with this Studio's K2, run length and prompt."""
        return self.agent_runs_of(resolve(catalog))

    def agent_runs_of(self, folder: str, cls: str | None = None):
        from ..agent_runs import AgentRuns, studio_prompter

        ctx = self.ctx(folder, cls)
        return AgentRuns(ctx, self.k2, self.agent_minutes, prompter=studio_prompter(ctx, self.azure_root))

    def catalog_folders(self) -> list[tuple[str, str]]:
        """Every catalog in the manifest, with each class that has rules there: the queue looks at each one's live
        runs (each catalog and class has its own runs and lock; all of them share the queue's places)."""
        from .. import manifest

        try:
            doc, _ = manifest.load(self.root)
        except FileNotFoundError:
            return []
        return [(c["catalog"], cls) for c in doc.get("catalogs", []) for cls in classes.SLUGS
                if manifest.has_rules(c, cls) or cls == "course"]

    def ctx(self, catalog: str, cls: str | None = None) -> Ctx:
        """A catalog's context for a class: `cls`, else the request's (`?class=`), else Course."""
        folder, cls = resolve(catalog), cls or REQUEST_CLASS.get()
        with self._lock:
            if (folder, cls) not in self._ctx:
                self._ctx[(folder, cls)] = Ctx(self.root, folder, manifest_ttl=3.0, cls=cls,
                                               shared_manifest=self.manifest)
            return self._ctx[(folder, cls)]


#: The class a request asks for (`?class=learningprogram`); Course when it names none.
REQUEST_CLASS: ContextVar[str] = ContextVar("request_class", default="course")


class ClassParam:
    """ASGI middleware: a request's `class` query parameter → REQUEST_CLASS, for every route's `studio().ctx()`."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from .. import classes
        from ..errors import UserError

        got = parse_qs(scope.get("query_string", b"").decode()).get("class")
        if got:
            try:
                token = REQUEST_CLASS.set(classes.get(got[0]).slug)
            except UserError as exc:
                from starlette.responses import JSONResponse

                return await JSONResponse({"detail": str(exc)}, status_code=422)(scope, receive, send)
            try:
                return await self.app(scope, receive, send)
            finally:
                REQUEST_CLASS.reset(token)
        return await self.app(scope, receive, send)


def studio(request: Request) -> Studio:
    return request.app.state.studio


def not_found(msg: str) -> HTTPException:
    return HTTPException(status_code=404, detail=msg)
