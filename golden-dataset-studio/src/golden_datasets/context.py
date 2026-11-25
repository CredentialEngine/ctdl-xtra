"""`Ctx`: one catalog + crawl + class in one storage root, as every command and the server see it.

It reads through the manifest (never by listing), caches immutable files on disk via the root, and holds the
small helpers for reading and writing JSON and Parquet.
"""

from __future__ import annotations

import io
import json
from functools import cached_property

import pyarrow as pa
import pyarrow.parquet as pq

from . import classes, layout, manifest, model, telemetry
from .catalogs import resolve
from .errors import UserError
from .storage import Root, open_root


class Ctx:
    def __init__(self, root: Root | str, catalog: str, crawl: str | None = None, manifest_ttl: float = 0.0,
                 cls: str = "course"):
        self.root = open_root(root)
        self.catalog = resolve(catalog)
        self._crawl = crawl
        self.ctdl_class = classes.get(cls)  # the CLI always names it (`--class`); the server's tabs are per class
        self.cls = self.ctdl_class.slug
        self.manifest_ttl = manifest_ttl  # the server re-reads the manifest at most this often (seconds)
        self._manifest: tuple[float, dict] | None = None

    @classmethod
    def from_args(cls, args) -> Ctx:
        return cls(args.root, args.catalog, getattr(args, "crawl", None), cls=getattr(args, "cls", None) or "course")

    # -- manifest ---------------------------------------------------------------------------------------
    def manifest(self) -> dict:
        import time

        now = time.monotonic()
        if self._manifest and now - self._manifest[0] < self.manifest_ttl:
            return self._manifest[1]
        doc = manifest.load(self.root)[0]
        self._manifest = (now, doc)
        return doc

    def invalidate(self) -> None:
        self._manifest = None

    def entry(self) -> dict | None:
        return manifest.catalog_entry(self.manifest(), self.catalog, create=False)

    def class_entry(self) -> dict:
        """This class's rule_versions, rulesets and annotations (empty when it has none yet)."""
        return manifest.class_entry(self.entry(), self.cls, create=False)

    def crawl_class(self) -> dict:
        """This class's rule runs, golden versions and scores on the crawl."""
        return manifest.crawl_class(self.crawl_entry(), self.cls, create=False)

    @cached_property
    def crawl_root(self) -> Root:
        """Where the crawl is (xtra-cli's container, read in place): the root the catalog was added from, else
        xtra-cli's container, else the Studio's root."""
        from .xtra_paths import xtra_root

        e = self.entry() or {}
        return open_root(e.get("crawls_root") or xtra_root(self.root) or self.root.uri)

    @cached_property
    def crawl(self) -> str:
        if self._crawl:
            return self._crawl
        e = self.entry()
        if e and e.get("current_crawl"):
            return e["current_crawl"]
        raise UserError(f"{self.catalog}: no crawl registered; run `golden-datasets init --catalog {self.catalog}`")

    def crawl_entry(self) -> dict:
        e = self.entry()
        k = manifest.crawl_entry(e, self.crawl, create=False) if e else None
        if k is None:
            raise UserError(f"{self.catalog}/{self.crawl}: not registered; run `golden-datasets init`")
        return k

    def ruleset_versions(self) -> list[int]:
        return sorted(r["version"] for r in self.class_entry().get("rulesets", []))

    def latest_ruleset(self) -> int:
        v = self.ruleset_versions()
        if not v:
            raise UserError(f"{self.catalog}: no ruleset yet; add the catalog's first rules in the Studio (or `golden-datasets rule publish`)")
        return v[-1]

    def extractions(self) -> list[dict]:
        return list(self.crawl_class().get("extractions", []))

    def extraction_for(self, ruleset_version: int) -> str | None:
        """The latest extraction of this ruleset version on this crawl."""
        ids = [e["extraction"] for e in self.extractions() if e["ruleset_version"] == ruleset_version]
        return sorted(ids)[-1] if ids else None

    def latest_extraction(self) -> str | None:
        exts = self.extractions()
        if not exts:
            return None
        return max(exts, key=lambda e: (e["ruleset_version"], e["extraction"]))["extraction"]

    # -- reads ------------------------------------------------------------------------------------------
    def read_json(self, path: str, immutable: bool = True):
        if immutable:
            return json.loads(self.root.local_path(path).read_bytes())
        return self.root.read_json(path)

    def read_table(self, path: str, columns: list[str] | None = None) -> pa.Table:
        return pq.read_table(self.root.local_path(path), columns=columns)

    def rows(self, path: str) -> list[dict]:
        return self.read_table(path).to_pylist()

    def ruleset(self, version: int) -> dict:
        rs = self.read_json(layout.ruleset(self.catalog, self.cls, version))
        return {**rs, "rules": [model.current_kind(e) for e in rs["rules"]]}

    def rule(self, rule_id: str, version: int) -> dict:
        return model.current_kind(self.read_json(layout.rule_version(self.catalog, self.cls, rule_id, version)))

    def ruleset_rules(self, version: int) -> tuple[dict, dict[str, dict]]:
        rs = self.ruleset(version)
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=16) as pool:  # one round trip each on Azure: fetch them together
            read_rule = telemetry.in_this_request(lambda e: self.rule(e["rule_id"], e["version"]))
            docs = list(pool.map(read_rule, rs["rules"]))
        return rs, {e["rule_id"]: d for e, d in zip(rs["rules"], docs)}

    def rule_versions(self, rule_id: str) -> list[int]:
        prefix = layout.rules_prefix(self.catalog, self.cls, rule_id)
        return sorted(int(p[len(prefix):-5]) for p in self.class_entry().get("rule_versions", [])
                      if p.startswith(prefix))

    def pages(self) -> list[dict]:
        return self.rows(layout.pages_parquet(self.catalog, self.crawl))

    def extraction_meta(self, ext: str) -> dict:
        return self.read_json(layout.extraction_file(self.catalog, self.crawl, self.cls, ext, "extraction"))

    def table(self, ext: str, name: str) -> pa.Table:
        return self.read_table(layout.extraction_file(self.catalog, self.crawl, self.cls, ext, name))

    def page_path(self, stem: str):
        """Local file of a saved page, from xtra-cli's container (downloaded once into the cache from Azure)."""
        return self.crawl_root.local_path(layout.page_html(self.catalog, self.crawl, stem))

    # -- writes -----------------------------------------------------------------------------------------
    def write_table(self, path: str, rows: list[dict], schema: pa.Schema, if_none_match: bool = True) -> dict:
        table = pa.Table.from_pylist(rows, schema=schema)
        buf = io.BytesIO()
        pq.write_table(table, buf, compression="zstd")
        data = buf.getvalue()
        self.root.write_bytes(path, data, if_none_match=if_none_match)
        import hashlib

        return {"rows": len(rows), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
