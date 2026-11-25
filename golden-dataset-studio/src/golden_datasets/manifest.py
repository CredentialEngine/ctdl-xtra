"""`manifest.json`: the index of every Studio path in a root (spec §4.1, §10).

Nothing is found by listing; readers open the manifest and follow its paths. Every writer updates it with
optimistic concurrency: read it with its ETag, change it, write it back only if the ETag is unchanged, and retry
on a conflict.

Shape (`golden-datasets-manifest/2`: per class, LearningProgram spec item 20):

    {"schema", "updated_at",
     "catalogs": [{"catalog", "name", "platform", "status", "current_crawl", "crawls_root" (where the crawls are),
                   "classes": {<class>: {"rule_versions": [path…], "rulesets": [{"version", "path"}],
                                         "annotations": path | null}},
                   "crawls": [{"crawl", "crawl_json", "pages_dir", "pages", "page_count", "assets": {…} | null,
                               "extract_outputs": [{"id", "path", "report_etag", "copy" (xtra root) | null, …}],
                               "classes": {<class>: {
                                   "extractions": [{"extraction", "ruleset_version", "path", "parent_extraction"}],
                                   "golden": [{"publication", "path", "to"}],
                                   "scores": [{"id", "path" (xtra root)}]}}}]}]}

`crawl_json`, `pages_dir` and the scores' and copies' paths are in xtra-cli's container; the rest in the root.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime

from .errors import ConflictError
from .storage import Root

PATH = "manifest.json"
SCHEMA = "golden-datasets-manifest/2"
#: What each class keeps, at the catalog level and per crawl.
CLASS_FIELDS = {"rule_versions": list, "rulesets": list, "annotations": lambda: None}
CRAWL_CLASS_FIELDS = {"extractions": list, "golden": list, "scores": list}


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
         "current_crawl": None, "classes": {}, "crawls": []}
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
         "assets": None, "extract_outputs": [], "classes": {}}
    cat["crawls"].append(k)
    cat["crawls"].sort(key=lambda x: x["crawl"])
    return k


def class_entry(cat: dict | None, cls: str, create: bool = True) -> dict:
    """A catalog's entry for one class: rule_versions, rulesets, annotations (empty, and not added, if `create` is
    False and the class has none)."""
    if cat is None:
        return {k: f() for k, f in CLASS_FIELDS.items()}
    got = (cat.get("classes") or {}).get(cls)
    if got is None:
        got = {k: f() for k, f in CLASS_FIELDS.items()}
        if create:
            cat.setdefault("classes", {})[cls] = got
    return got


def crawl_class(k: dict | None, cls: str, create: bool = True) -> dict:
    """A crawl's entry for one class: extractions (rule runs), golden, scores."""
    if k is None:
        return {f: [] for f in CRAWL_CLASS_FIELDS}
    got = (k.get("classes") or {}).get(cls)
    if got is None:
        got = {f: [] for f in CRAWL_CLASS_FIELDS}
        if create:
            k.setdefault("classes", {})[cls] = got
    return got


def has_rules(cat: dict, cls: str | None = None) -> bool:
    """The catalog has a ruleset (of this class, or of any)."""
    classes = cat.get("classes") or {}
    return any((v or {}).get("rulesets") for c, v in classes.items() if cls is None or c == cls)


def add_unique(items: list, value, key: Callable | None = None) -> None:
    k = key or (lambda x: x)
    if not any(k(x) == k(value) for x in items):
        items.append(value)
