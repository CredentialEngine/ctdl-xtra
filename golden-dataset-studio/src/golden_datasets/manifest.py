"""`golden-dataset-studio/manifest.json`: the index of every Studio path in a root (spec §4.1, §10).

Nothing is found by listing; readers open the manifest and follow its paths. Every writer updates it with
optimistic concurrency: read it with its ETag, change it, write it back only if the ETag is unchanged, and retry
on a conflict.

Shape (`golden-datasets-manifest/1`):

    {"schema", "updated_at",
     "catalogs": [{"catalog", "name", "platform", "status", "current_crawl",
                   "rule_versions": [path…], "rulesets": [{"version", "path"}], "annotations": path | null,
                   "crawls": [{"crawl", "crawl_json", "pages_dir", "pages", "page_count", "assets": {…} | null,
                               "extractions": [{"extraction", "ruleset_version", "path", "parent_extraction"}],
                               "golden": [{"publication", "path", "to"}]}]}]}
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime

from .errors import ConflictError
from .storage import Root

PATH = "golden-dataset-studio/manifest.json"
SCHEMA = "golden-datasets-manifest/1"


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def empty() -> dict:
    return {"schema": SCHEMA, "updated_at": None, "catalogs": []}


def load(root: Root) -> tuple[dict, str | None]:
    """The manifest and its ETag (None when there is no manifest yet)."""
    st = root.stat(PATH)
    if st is None:
        return empty(), None
    # Read and stat can race; the ETag we return must describe the bytes we parsed, so re-check.
    for _ in range(5):
        data = root.read_bytes(PATH)
        st2 = root.stat(PATH)
        if st2 and st2.etag == st.etag:
            import json

            return json.loads(data), st.etag
        st = st2
    raise ConflictError("manifest keeps changing while being read")


def update(root: Root, change: Callable[[dict], None], retries: int = 8) -> dict:
    """Apply `change` (which mutates the manifest in place) and write it back atomically."""
    for attempt in range(retries):
        doc, etag = load(root)
        change(doc)
        doc["updated_at"] = now_iso()
        try:
            if etag is None:
                root.write_json(PATH, doc, if_none_match=True)
            else:
                root.write_json(PATH, doc, if_match=etag)
            return doc
        except ConflictError:
            time.sleep(0.05 * (attempt + 1))
    raise ConflictError("could not update the manifest: too many concurrent writers")


# --- helpers used by writers -------------------------------------------------------------------------
def catalog_entry(doc: dict, catalog: str, create: bool = True) -> dict | None:
    for c in doc["catalogs"]:
        if c["catalog"] == catalog:
            return c
    if not create:
        return None
    from .catalogs import info

    meta = info(catalog)
    c = {"catalog": catalog, "name": meta["name"], "platform": meta["platform"], "status": "not imported",
         "current_crawl": None, "rule_versions": [], "rulesets": [], "annotations": None, "crawls": []}
    doc["catalogs"].append(c)
    doc["catalogs"].sort(key=lambda x: x["name"].lower())
    return c


def crawl_entry(cat: dict, crawl: str, create: bool = True) -> dict | None:
    for k in cat["crawls"]:
        if k["crawl"] == crawl:
            return k
    if not create:
        return None
    k = {"crawl": crawl, "crawl_json": None, "pages_dir": None, "pages": None, "page_count": None,
         "assets": None, "extractions": [], "golden": []}
    cat["crawls"].append(k)
    cat["crawls"].sort(key=lambda x: x["crawl"])
    return k


def add_unique(items: list, value, key: Callable | None = None) -> None:
    k = key or (lambda x: x)
    if not any(k(x) == k(value) for x in items):
        items.append(value)
