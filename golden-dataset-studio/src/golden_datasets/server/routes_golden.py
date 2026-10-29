"""Golden datasets API (Evals spec §6.6): a read-only record of the catalog's golden dataset versions. Approving a
column's rule publishes it (routes_review's approve); nothing here writes.

- `GET /catalogs/{c}/golden`: one entry per version, newest first: its columns, its values (with how many are
  human-reviewed), its latest xtra score against the latest extract output, and where it is written.
- `GET /catalogs/{c}/golden/approve/{rule}`: what approving that rule would publish (the confirmation's numbers).
- `GET /catalogs/{c}/golden/{version}/…`: samples of the files a version wrote: a page's JSON in each tree, its HTML
  at the latest location, publication.json, lineage.parquet and golden.parquet.

The CLI's `golden-datasets golden publish` still publishes for engineers.
"""

from __future__ import annotations

import json
from collections import Counter

from fastapi import APIRouter, HTTPException, Query, Request

from .. import golden, model, scores
from ..review import LOADER
from ..storage import open_root
from .state import not_found, studio

router = APIRouter(prefix="/api")
HTML_PREVIEW_BYTES = 400_000
TREES = (golden.RULE_MATCHED, golden.HUMAN_REVIEWED, "latest")


def _pub(ctx, vs: dict, n: int) -> dict:
    try:
        return ctx.read_json(f"{vs[n]['path']}/publication.json", immutable=False)
    except FileNotFoundError:
        return {}


def _values_now(st, ctx, doc: dict) -> Counter:
    """The latest version's values as its files hold them now (each expert verdict rewrites a page's files): values
    with a CTDL term, and how many are human-reviewed. Kept until the annotation log moves."""
    rv = LOADER.review(ctx, doc["extraction"])
    key = ("golden-values", ctx.catalog, doc["publication"], doc.get("published_at"), LOADER.log(ctx).offset)
    if key not in st.cache:
        files = golden.trees(golden.plan(rv, set(doc.get("properties") or []))["pages"])
        st.cache[key] = Counter(
            values=sum(len(r["fields"]) for recs in files[golden.RULE_MATCHED].values() for r in recs),
            human=sum(len(r["fields"]) for recs in files[golden.HUMAN_REVIEWED].values() for r in recs))
    return st.cache[key]


def _table(ctx, path: str) -> list[dict]:
    """A version's Parquet file, read again each time (publishing rewrites it)."""
    import pyarrow.parquet as pq

    return pq.read_table(ctx.root.local_path(path, mutable=True)).to_pylist()


def _values_then(ctx, path: str) -> Counter:
    """An older version's values, as published (golden.parquet): those with a CTDL term."""
    try:
        rows = _table(ctx, f"{path}/golden.parquet")
    except FileNotFoundError:
        return Counter()
    rows = [r for r in rows if r["ctdl_property"]]
    return Counter(values=len(rows), human=sum(r["approval"] == "human" for r in rows))


def _of(doc: dict, vid: str) -> bool:
    """Whether a score read this version (as `ruleset-vN`, or as the human-reviewed values when it was the latest)."""
    g = doc["golden"]
    return g["id"] == vid or (g["kind"] == "human-reviewed" and g.get("from", "").rstrip("/").endswith(f"/{vid}"))


def _score(docs: list[dict], vid: str, output: str | None) -> dict | None:
    """The newest score of this version against the latest extract output: done (its exact matches, on the
    human-reviewed values if it has any, else the rule-matched ones), or still running."""
    for d in docs:
        if not _of(d, vid) or d["output"]["id"] != output or d["status"] not in ("done", "running"):
            continue
        if d["status"] == "running":
            return {"id": d["id"], "status": "running"}
        res = d.get("results") or {}
        basis = "human" if res.get("human") else "rule"
        r = res.get(basis)
        if r:
            return {"id": d["id"], "status": "done", "basis": basis, "rate": r["exact_match_rate"],
                    "values": r["values"], "match": r["outcomes"]["match"], "output": d["output"]["id"],
                    "finished_at": d.get("finished_at")}
    return None


@router.get("/catalogs/{catalog}/golden")
def golden_versions(request: Request, catalog: str) -> dict:
    st = studio(request)
    ctx = st.ctx(catalog)
    vs = golden.versions(ctx)
    docs = scores.all_scores(ctx) if vs else []
    outs = scores.outputs(ctx)
    latest_out = outs[-1]["id"] if outs else None
    out = []
    for n in sorted(vs, reverse=True):
        doc = _pub(ctx, vs, n)
        latest = n == max(vs)
        vid = golden.version_name(n)
        counts = _values_now(st, ctx, doc) if latest and doc else _values_then(ctx, vs[n]["path"])
        trees = doc.get("trees") or {}
        out.append({
            "id": vid, "ruleset_version": n, "latest": latest, "columns": golden.columns_of(doc.get("properties") or []),
            "values": counts["values"], "human": counts["human"], "published_at": doc.get("published_at"),
            "created_at": doc.get("created_at"), "published_by": doc.get("published_by"),
            "extraction": doc.get("extraction"), "score": _score(docs, vid, latest_out),
            "where": {"root": vs[n].get("to"), "version": f"catalogs/{ctx.catalog}/versions/{vid}/",
                      "trees": {t: {"prefix": golden.version_prefix(ctx, n, t), "pages": (trees.get(t) or {}).get("pages")}
                                for t in golden.TREES},
                      "latest": golden.latest_prefix(ctx) if latest else None, "studio": f"{vs[n]['path']}/"}})
    return {"catalog": ctx.catalog, "crawl": ctx.crawl, "versions": out, "latest_output": latest_out,
            "running": request.app.state.scores.busy(ctx.catalog)}


@router.get("/catalogs/{catalog}/golden/approve/{rule_id}")
def approve_preview(request: Request, catalog: str, rule_id: str) -> dict:
    """What approving this rule publishes: the golden dataset's columns now and after, and the column's values (how
    many are human-reviewed, how many its rule labels). `publishes` False: not a column's rule (approved as before)."""
    st = studio(request)
    ctx = st.ctx(catalog)
    rv = LOADER.review(ctx)
    if rule_id not in rv.snap.rules:
        raise not_found(f"unknown rule {rule_id}")
    what = golden.approval_publishes(rv, rule_id)
    if what is None:
        return {"publishes": False, "rule_id": rule_id}
    base = {"publishes": what["writes"], "rule_id": rule_id, "property": what["property"], "column": what["column"],
            "golden": what["golden"], "ruleset_version": what["ruleset_version"], "creates": what["creates"],
            "now": golden.columns_of(what["now"]), "after": golden.columns_of(what["after"]),
            "where": f"{golden.default_target(ctx).rstrip('/')}/catalogs/{ctx.catalog}/versions/{what['golden']}/"}
    if not what["writes"]:
        return base
    key = ("approve-values", ctx.catalog, rv.snap.ext, LOADER.log(ctx).offset, what["property"])
    if key not in st.cache:
        files = golden.trees(golden.plan(rv, {what["property"]})["pages"])[golden.RULE_MATCHED]
        mine = [f for recs in files.values() for r in recs for f in r["fields"] if f["property"] == what["property"]]
        st.cache[key] = {"values": len(mine), "human": sum(f["approval"] == "human" for f in mine)}
    v = st.cache[key]
    return base | v | {"rule": v["values"] - v["human"]}


# --- samples of what a version wrote ---------------------------------------------------------------------------
def _version(request: Request, catalog: str, vid: str):
    ctx = studio(request).ctx(catalog)
    m = golden.VERSION.match(vid)
    vs = golden.versions(ctx)
    if not m or int(m.group(1)) not in vs:
        raise not_found(f"{vid}: no such golden dataset")
    n = int(m.group(1))
    return ctx, n, vs[n], open_root(vs[n]["to"])


def _prefix(ctx, n: int, vs: dict, tree: str) -> str:
    if tree not in TREES:
        raise HTTPException(422, f"tree must be one of {', '.join(TREES)}")
    if tree == "latest":
        if n != max(golden.versions(ctx)):
            raise not_found("only the latest version is at the latest location")
        return golden.latest_prefix(ctx)
    return golden.version_prefix(ctx, n, tree)


@router.get("/catalogs/{catalog}/golden/{vid}/stems")
def version_stems(request: Request, catalog: str, vid: str, tree: str = golden.RULE_MATCHED) -> list[str]:
    """The pages that have a file in this tree."""
    ctx, n, entry, target = _version(request, catalog, vid)
    return sorted(golden.tree_stems(target, _prefix(ctx, n, entry, tree)))


@router.get("/catalogs/{catalog}/golden/{vid}/files/page/{stem}.json")
def version_page_json(request: Request, catalog: str, vid: str, stem: str, tree: str = golden.RULE_MATCHED) -> dict:
    ctx, n, entry, target = _version(request, catalog, vid)
    path = f"{_prefix(ctx, n, entry, tree)}{stem}/{stem}.json"
    try:
        text = target.read_text(path)
    except FileNotFoundError:
        raise not_found(f"{stem}: no file in this tree") from None
    return {"stem": stem, "path": f"{target.uri}/{path}", "records": len(json.loads(text)), "bytes": len(text.encode()),
            "text": text}


@router.get("/catalogs/{catalog}/golden/{vid}/files/page/{stem}.html")
def version_page_html(request: Request, catalog: str, vid: str, stem: str) -> dict:
    ctx, n, entry, target = _version(request, catalog, vid)
    path = f"{_prefix(ctx, n, entry, 'latest')}{stem}/{stem}.html"
    try:
        data = target.read_bytes(path)
    except FileNotFoundError:
        raise not_found(f"{stem}: no page at the latest location") from None
    return {"stem": stem, "path": f"{target.uri}/{path}", "bytes": len(data), "truncated": len(data) > HTML_PREVIEW_BYTES,
            "text": data[:HTML_PREVIEW_BYTES].decode("utf-8", errors="replace")}


@router.get("/catalogs/{catalog}/golden/{vid}/files/publication.json")
def version_publication(request: Request, catalog: str, vid: str) -> dict:
    ctx, n, entry, _ = _version(request, catalog, vid)
    doc = ctx.read_json(f"{entry['path']}/publication.json", immutable=False)
    more = len(doc.get("page_stems") or []) > 20
    if more:
        doc["page_stems"] = doc["page_stems"][:20] + [f"… {len(doc['page_stems']) - 20:,} more"]
    return {"text": json.dumps(doc, indent=2, ensure_ascii=False) + "\n", "truncated_page_stems": more}


@router.get("/catalogs/{catalog}/golden/{vid}/files/{table}.parquet")
def version_table(request: Request, catalog: str, vid: str, table: str, q: str = "", offset: int = Query(0, ge=0),
                  limit: int = Query(100, ge=1, le=500)) -> dict:
    """lineage.parquet's or golden.parquet's rows: filter by any cell's text, a page of rows at a time."""
    if table not in ("lineage", "golden"):
        raise not_found(f"{table}.parquet: not a file of a golden dataset")
    ctx, n, entry, _ = _version(request, catalog, vid)
    try:
        rows = _table(ctx, f"{entry['path']}/{table}.parquet")
    except FileNotFoundError:
        raise not_found(f"{vid} has no {table}.parquet") from None
    total = len(rows)
    if q:
        needle = q.lower()
        rows = [r for r in rows if any(needle in str(v).lower() for v in r.values())]
    columns = (model.LINEAGE if table == "lineage" else model.GOLDEN).names
    return {"columns": columns, "total": total, "matched": len(rows), "offset": offset,
            "rows": [[r.get(c) for c in columns] for r in rows[offset:offset + limit]]}

