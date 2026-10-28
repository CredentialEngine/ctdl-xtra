"""Scores (Evals spec §4): one extract output compared with one golden dataset by xtra's own scorer, and kept.

    <crawl>/golden-dataset-studio/scores/sc-NNNN/{score.json, values.parquet}
    <crawl>/golden-dataset-studio/extract-outputs/<report last modified>/{records/, extract-report.json}

**The scorer** is xtra-cli's (`match_extraction_run`, a uv path dependency on `../xtra-cli`), called in-process with
two store adapters (`list_keys`, `get_json`, `describe_location`): `RecordsStore` reads an extract output's
`records/` where it is, and never writes; `GoldenStore` serves a golden dataset from memory, as the scorer reads it
(`<catalog>/<crawl>/<stem>/<stem>.json`). Nothing is written next to the records: the reports stay in memory.

**A golden dataset** is `ruleset-vN` (its version folder in the golden root), `human-reviewed` (the live page files at
the latest location: each expert verdict rewrites one, so `golden.parquet` would be stale) or a draft `rs-NNNN` (an
unpublished extraction, planned in memory). **Each score runs the scorer twice**, exact and partial each time: on the
human-reviewed values only (`approval: human`) and on every rule-matched value. Both results are kept.

Values without a CTDL term (Learning Type) are left out: the scorer rejects a page file that has one. A value with
`location: null` is implied, not on the page, and the scorer skips it (xtra-cli #343). The scorer pairs a page's
entities with its records by position and rejects an empty entity, so a basis drops trailing empty entities and
leaves out a page whose empty entity comes before a non-empty one.

**An extract output** is what `xtra catalog extract` wrote for the crawl (`$GOLDEN_DATASETS_XTRA_SOURCE`, else the
shared container). xtra overwrites it in place, so the first time the Studio sees a report (by ETag) it copies
`records/` and the report into `extract-outputs/<report last modified>/`, and scores read that copy.

A pair (golden dataset content, extract output) is scored once: asking again returns the score there is.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import subprocess
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from . import golden as golden_mod
from . import layout, manifest, model
from .context import Ctx
from .errors import UserError
from .storage import AzureRoot, Root, open_root

SHARED_XTRA_ROOT = "azure://https://ceteststorage.blob.core.windows.net/xtra-cli-output"
HUMAN_REVIEWED = "human-reviewed"
BASES = ("human", "rule")  # the human-reviewed values only; every rule-matched value
OUTCOMES = ("missing", "wrong", "partial", "match")
SLOT_NAMES = "this output uses slot names; re-extract with the current xtra-cli"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def column(ctdl_property: str) -> str:
    """The column's name in Evals: the CTDL term without `ceterms:`."""
    return ctdl_property.split(":", 1)[-1]


def _text(v) -> str | None:
    if v is None:
        return None
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


# --- store adapters ----------------------------------------------------------------------------------
class RecordsStore:
    """An extract output (`records/`, `extract-report.json`) under `base` in `root`, as the scorer sees it at
    `<catalog>/<crawl>/…`. Read-only; records are read once and kept for the next run."""

    def __init__(self, root: Root, base: str, catalog: str, crawl: str):
        self.root, self.base, self.prefix = root, base.strip("/"), f"{catalog}/{crawl}"
        self._json: dict[str, object] = {}

    def _path(self, key: str) -> str:
        key = key.strip("/")
        if key != self.prefix and not key.startswith(self.prefix + "/"):
            raise FileNotFoundError(key)
        return "/".join(p for p in (self.base, key[len(self.prefix):].strip("/")) if p)

    def list_keys(self, under: str = "") -> list[str]:
        try:
            path = self._path(under)
        except FileNotFoundError:
            return []
        cut = len(self.base) + 1 if self.base else 0
        return [f"{self.prefix}/{p[cut:]}" for p in self.root.list(path)]

    def get_json(self, key: str) -> object:
        if key not in self._json:
            self._json[key] = self.root.read_json(self._path(key))
        return self._json[key]

    def describe_location(self) -> str:
        return "/".join(p for p in (self.root.uri, self.base) if p)

    def records(self) -> list[str]:
        return [k for k in self.list_keys(f"{self.prefix}/records") if k.endswith(".json")]


class GoldenStore:
    """A golden dataset's pages {stem: entities}, served from memory at `<catalog>/<crawl>/<stem>/<stem>.json`."""

    def __init__(self, pages: dict[str, list[dict]], catalog: str, crawl: str, where: str):
        self.pages, self.prefix, self.where = pages, f"{catalog}/{crawl}", where

    def list_keys(self, under: str = "") -> list[str]:
        under = under.strip("/")
        return [k for k in (f"{self.prefix}/{s}/{s}.json" for s in sorted(self.pages)) if k.startswith(under)]

    def get_json(self, key: str) -> object:
        parts = key.strip("/").split("/")
        if len(parts) < 2 or parts[-2] not in self.pages:
            raise FileNotFoundError(key)
        return self.pages[parts[-2]]

    def describe_location(self) -> str:
        return self.where


def basis_pages(pages: dict[str, list[dict]], basis: str) -> tuple[dict[str, list[dict]], list[dict]]:
    """The pages as the scorer reads them for one basis (`human`: only `approval: human` values; `rule`: every
    value), and the pages left out (with why)."""
    out, left_out = {}, []
    for stem, records in pages.items():
        ents = []
        for r in records:
            fields = [f for f in r.get("fields", [])
                      if f.get("ctdl_property") and (basis == "rule" or f.get("approval") == "human")]
            ents.append({"golden_record_id": r.get("golden_record_id"), "approval": r.get("approval"), "fields": fields})
        while ents and not ents[-1]["fields"]:
            ents.pop()
        if not ents:
            continue
        if any(not e["fields"] for e in ents):
            left_out.append({"stem": stem, "why": "an earlier course on the page has no values in this basis"})
            continue
        out[stem] = ents
    return out, left_out


def is_implied(f: dict) -> bool:
    return "location" in f and f["location"] is None


# --- golden datasets ---------------------------------------------------------------------------------
@dataclass
class Golden:
    id: str                                  # ruleset-vN, human-reviewed or rs-NNNN
    kind: str                                # version, human-reviewed or draft
    where: str                               # where the page files are (or the extraction, for a draft)
    pages: dict[str, list[dict]]
    as_of: str = field(default_factory=_now)
    baseline_uri: str | None = None          # what `xtra score --baseline-uri` would read

    @functools.cached_property
    def sha256(self) -> str:
        return hashlib.sha256(model.canon(self.pages).encode()).hexdigest()


def _read_pages(root: Root, prefix: str) -> dict[str, list[dict]]:
    """Every `<stem>/<stem>.json` below `prefix` that holds a course."""
    prefix = prefix.strip("/")
    paths = []
    for p in root.list(prefix):
        parts = p[len(prefix) + 1:].split("/")
        if len(parts) == 2 and parts[1] == f"{parts[0]}.json":
            paths.append(p)

    def one(p: str):
        doc = root.read_json(p)
        return p.rsplit("/", 2)[-2], [doc] if isinstance(doc, dict) else doc

    with ThreadPoolExecutor(max_workers=16) as pool:
        return {s: d for s, d in pool.map(one, paths) if d}


def latest_golden(ctx: Ctx) -> str | None:
    vs = golden_mod.versions(ctx)
    return golden_mod.version_name(max(vs)) if vs else None


def load_golden(ctx: Ctx, gid: str) -> Golden:
    vs = golden_mod.versions(ctx)
    if gid == HUMAN_REVIEWED:
        to = vs[max(vs)]["to"] if vs else golden_mod.default_target(ctx)
        root = open_root(to)
        return Golden(gid, "human-reviewed", f"{root.uri}/{golden_mod.latest_prefix(ctx)}".rstrip("/"),
                      _read_pages(root, golden_mod.latest_prefix(ctx)), baseline_uri=root.uri)
    m = golden_mod.VERSION.match(gid)
    if m:
        n = int(m.group(1))
        if n not in vs:
            raise UserError(f"{gid}: no such golden dataset (published: "
                            f"{', '.join(golden_mod.version_name(v) for v in sorted(vs)) or 'none'})")
        root = open_root(vs[n]["to"])
        base = f"{root.uri}/catalogs/{ctx.catalog}/versions/{gid}"
        return Golden(gid, "version", f"{root.uri}/{golden_mod.version_prefix(ctx, n)}".rstrip("/"),
                      _read_pages(root, golden_mod.version_prefix(ctx, n)), baseline_uri=base)
    if gid in {e["extraction"] for e in ctx.extractions()}:
        from .review import LOADER

        return Golden(gid, "draft", f"extraction {gid} (unpublished)", golden_mod.plan(LOADER.review(ctx, gid))["pages"])
    raise UserError(f"{gid}: not a golden dataset (ruleset-vN, {HUMAN_REVIEWED} or a draft rs-NNNN)")


# --- extract outputs ---------------------------------------------------------------------------------
def xtra_source(root: Root) -> str:
    """Where xtra-cli writes extract outputs: $GOLDEN_DATASETS_XTRA_SOURCE, else the shared container."""
    src = os.environ.get("GOLDEN_DATASETS_XTRA_SOURCE")
    if src:
        return src
    if isinstance(root, AzureRoot):
        return SHARED_XTRA_ROOT
    raise UserError("set GOLDEN_DATASETS_XTRA_SOURCE to the xtra-cli output root (a folder, or azure://…/xtra-cli-output)")


def outputs(ctx: Ctx) -> list[dict]:
    """The extract outputs the Studio has seen (and copied), oldest first."""
    return list(ctx.crawl_entry().get("extract_outputs", []))


def _identity(root: Root, base: str, catalog: str, crawl: str) -> dict:
    """What identifies an extract output: its report's ETag and last-modified time, its counts."""
    path = "/".join(p for p in (base, "extract-report.json") if p)
    st = root.stat(path)
    if st is None:
        raise UserError(f"{root.uri}/{path}: no extract report")
    report = root.read_json(path)
    store = RecordsStore(root, base, catalog, crawl)
    n = len(store.records())
    modified = (st.modified or datetime.now(UTC)).astimezone(UTC)
    return {"id": modified.strftime("%Y-%m-%dT%H-%M-%SZ"), "path": store.describe_location(), "report_etag": st.etag,
            "last_modified": modified.strftime("%Y-%m-%dT%H:%M:%SZ"), "run_id": report.get("run_id"),
            "discovery_run_id": report.get("discovery_run_id"), "only_golden_sample": report.get("only_golden_sample"),
            "records": n, "records_written": report.get("records_written"),
            "records_mismatch": report.get("records_written") is not None and n != report.get("records_written")}


def see_output(ctx: Ctx, log=print) -> tuple[dict | None, bool]:
    """The latest extract output for the crawl (None if xtra hasn't written one), and whether it is new: the first
    time its report's ETag is seen, `records/` and the report are copied into extract-outputs/<id>/."""
    src = open_root(xtra_source(ctx.root))
    prefix = f"{ctx.catalog}/{ctx.crawl}"
    st = src.stat(f"{prefix}/extract-report.json")
    if st is None:
        return None, False
    known = next((o for o in outputs(ctx) if o["report_etag"] == st.etag), None)
    if known:
        return known, False
    ident = _identity(src, prefix, ctx.catalog, ctx.crawl)
    taken = {o["id"] for o in outputs(ctx)}
    base_id, n = ident["id"], 1
    while ident["id"] in taken:  # two outputs written within the same second
        n += 1
        ident["id"] = f"{base_id}-{n}"
    copy = layout.extract_output_dir(ctx.catalog, ctx.crawl, ident["id"])
    paths = [*src.list(f"{prefix}/records"), f"{prefix}/extract-report.json"]
    log(f"new extract output {ident['id']}: copying {len(paths):,} files into {copy}")

    def one(p: str) -> None:
        ctx.root.write_bytes(f"{copy}/{p[len(prefix) + 1:]}", src.read_bytes(p))

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(one, paths))
    entry = {**ident, "copy": copy, "seen_at": _now()}

    def change(m: dict) -> None:
        k = manifest.crawl_entry(manifest.catalog_entry(m, ctx.catalog), ctx.crawl)
        manifest.add_unique(k.setdefault("extract_outputs", []), entry, key=lambda o: o["report_etag"])

    manifest.update(ctx.root, change)
    ctx.invalidate()
    return entry, True


def resolve_output(ctx: Ctx, output: str | None, log=print) -> tuple[dict, RecordsStore]:
    """An extract output: None or `latest` (the one xtra wrote last, copied when new), a copy's id, or a folder that
    holds records/ and extract-report.json (a path or an azure:// URI, read in place)."""
    if output in (None, "latest"):
        entry, _ = see_output(ctx, log)
        if entry is None:
            raise UserError(f"{ctx.catalog}: xtra hasn't written an extract output for crawl {ctx.crawl} "
                            f"in {xtra_source(ctx.root)}")
        output = entry["id"]
    entry = next((o for o in reversed(outputs(ctx)) if o["id"] == output), None)
    if entry:
        return entry, RecordsStore(ctx.root, entry["copy"], ctx.catalog, ctx.crawl)
    root = open_root(output)
    base = "" if root.exists("extract-report.json") else f"{ctx.catalog}/{ctx.crawl}"
    return _identity(root, base, ctx.catalog, ctx.crawl), RecordsStore(root, base, ctx.catalog, ctx.crawl)


def uses_slot_names(store: RecordsStore) -> bool:
    """True when no record's `expected` has a `ceterms:` key: an extractor older than the slot-name mapping."""
    keys = store.records()
    for k in keys:
        if any(p.startswith("ceterms:") for p in (store.get_json(k).get("expected") or {})):
            return False
    return bool(keys)


# --- scoring -----------------------------------------------------------------------------------------
@functools.cache
def xtra_cli_commit() -> str | None:
    """The commit of the xtra-cli the scorer comes from (`+dirty` with uncommitted changes there)."""
    import implementations

    here = Path(implementations.__file__).resolve().parents[2]
    try:
        sha = subprocess.run(["git", "-C", str(here), "rev-parse", "HEAD"], capture_output=True, text=True,
                             check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(here), "status", "--porcelain", "--", "."], capture_output=True,
                               text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return sha + ("+dirty" if dirty else "")


def run_scorer(records: RecordsStore, pages: dict[str, list[dict]], catalog: str, crawl: str,
               where: str) -> dict[str, dict]:
    """xtra's scorer on these pages, exact and partial: {mode: report}."""
    from implementations.score_extraction_match import match_extraction_run

    store = GoldenStore(pages, catalog, crawl, where)
    return {mode: match_extraction_run(records, store, catalog, crawl, mode) for mode in ("exact", "partial")}


def value_rows(basis: str, pages: dict[str, list[dict]], reports: dict[str, dict]) -> list[dict]:
    """One row per scored value. Every value that isn't an exact match is in the exact report's outliers (with its
    similarity; partial is ≥ the threshold); the rest matched. The counts are checked against both reports."""
    from implementations.score_extraction_match import PARTIAL_THRESHOLD

    exact, partial = reports["exact"], reports["partial"]
    out_by: dict[tuple, list[dict]] = defaultdict(list)
    for o in exact["outliers"]:
        out_by[(o["stem"], o["entity"], o["ctdl_property"], _text(o["baseline_value"]))].append(o)
    scored = {p["stem"] for p in exact["pages"]}
    rows = []
    for stem, ents in sorted(pages.items()):
        if stem not in scored:
            continue
        for ei, ent in enumerate(ents):
            for f in ent["fields"]:
                if is_implied(f):
                    continue
                o = out_by[(stem, ei, f["ctdl_property"], _text(f["value"]))]
                o = o.pop(0) if o else None
                if o is None:
                    outcome, sim, got = "match", 1.0, _text(f["value"])
                elif o["outcome"] == "missing":
                    outcome, sim, got = "missing", None, None
                else:
                    sim = o["similarity"]
                    outcome, got = "partial" if sim >= PARTIAL_THRESHOLD else "wrong", _text(o["extracted_value"])
                loc = f.get("location") or {}
                rows.append({"basis": basis, "column": column(f["ctdl_property"]), "ctdl_property": f["ctdl_property"],
                             "property": f.get("property"), "golden_record_id": ent.get("golden_record_id"),
                             "page_stem": stem, "entity": ei, "outcome": outcome, "similarity": sim,
                             "golden_value": _text(f["value"]), "extracted_value": got, "source_url": f.get("source_url"),
                             "golden_css_path": loc.get("css_path"), "golden_char_start": loc.get("char_start"),
                             "golden_char_end": loc.get("char_end"), "approval": f.get("approval"),
                             "approved_by": f.get("approved_by"), "approved_at": f.get("approved_at")})
    got = Counter(r["outcome"] for r in rows)
    want = {"match": exact["outcomes"]["match"], "missing": exact["outcomes"]["missing"],
            "partial": partial["outcomes"]["partial"], "wrong": partial["outcomes"]["wrong"]}
    if len(rows) != exact["fields_total"] or any(got[k] != v for k, v in want.items()):
        raise UserError(f"{basis}: rebuilt counts {dict(got)} of {len(rows)} don't match the scorer's {want} "
                        f"of {exact['fields_total']}")
    return rows


def result(pages: dict[str, list[dict]], left_out: list[dict], reports: dict[str, dict], rows: list[dict]) -> dict:
    """One basis's result: the scorer's counts, per column too."""
    exact = reports["exact"]
    by: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        by[r["column"]][r["outcome"]] += 1
    implied: Counter = Counter(column(f["ctdl_property"]) for ents in pages.values() for e in ents
                               for f in e["fields"] if is_implied(f))
    return {"values": exact["fields_total"], "exact_match_rate": exact["exact_match_rate"],
            "outcomes": {o: sum(c[o] for c in by.values()) for o in OUTCOMES},
            "by_column": {col: {"values": sum(c.values()), **{o: c[o] for o in OUTCOMES}} for col, c in sorted(by.items())},
            "implied": dict(sorted(implied.items())), "pages_scored": exact["pages_scored"],
            "pages_skipped": exact["pages_skipped"], "pages_out_of_scope": exact["pages_out_of_scope"],
            "malformed": len(exact["malformed"]), "left_out": left_out}


def commands(ctx: Ctx, g: Golden, output: dict) -> list[str]:
    """The `xtra score` commands for the rule-matched result (the human-reviewed one keeps only `approval: human`
    values, which the CLI can't filter)."""
    if not g.baseline_uri:
        return []
    src = output["path"].removesuffix(f"/{ctx.catalog}/{ctx.crawl}")
    return [f"xtra score extraction match --{flag} \\\n  --source-uri {src} \\\n  --baseline-uri {g.baseline_uri} \\\n"
            f"  --catalog-id {ctx.catalog} \\\n  --run-id {ctx.crawl}" for flag in ("exactly", "partially")]


# --- score documents ---------------------------------------------------------------------------------
def score_ids(ctx: Ctx) -> list[str]:
    return [s["id"] for s in ctx.crawl_entry().get("scores", [])]


def read(ctx: Ctx, sid: str) -> dict:
    if sid not in score_ids(ctx):
        raise UserError(f"{sid}: no such score")
    return ctx.read_json(f"{layout.score_dir(ctx.catalog, ctx.crawl, sid)}/score.json", immutable=False)


def all_scores(ctx: Ctx) -> list[dict]:
    """Every score of the crawl, newest first."""
    ids = score_ids(ctx)
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(lambda s: read(ctx, s), reversed(ids)))


def values(ctx: Ctx, sid: str) -> list[dict]:
    return ctx.rows(f"{layout.score_dir(ctx.catalog, ctx.crawl, sid)}/values.parquet")


def _write(ctx: Ctx, doc: dict, **kw) -> None:
    ctx.root.write_json(f"{layout.score_dir(ctx.catalog, ctx.crawl, doc['id'])}/score.json", doc, **kw)


@dataclass
class Prepared:
    golden: Golden
    output: dict
    records: RecordsStore
    pair: str


def prepare(ctx: Ctx, golden: str | None, output: str | None = None, log=print) -> Prepared:
    """Read the golden dataset and find the extract output (copying it when new); no score yet."""
    gid = golden or latest_golden(ctx)
    if not gid:
        raise UserError(f"{ctx.catalog}: no golden dataset yet; approve a column, or score --{HUMAN_REVIEWED}")
    g = load_golden(ctx, gid)
    out, store = resolve_output(ctx, output, log)
    return Prepared(g, out, store, f"{g.id}@{g.sha256[:16]}|{out['report_etag']}")


def existing(ctx: Ctx, p: Prepared) -> dict | None:
    """The score of this pair (the same golden content and extract output), unless it failed or was interrupted."""
    for doc in all_scores(ctx):
        if doc.get("pair") == p.pair and doc["status"] in ("running", "done"):
            return doc
    return None


def begin(ctx: Ctx, p: Prepared, by: str, reason: str) -> dict:
    """score.json with status `running`, registered in the manifest."""
    ctx.invalidate()  # the server's manifest may be a few seconds old
    ids = score_ids(ctx)
    sid = f"sc-{max((int(i.split('-')[1]) for i in ids), default=0) + 1:04d}"
    doc = {"id": sid, "status": "running", "pair": p.pair, "created_at": _now(), "finished_at": None, "by": by,
           "reason": reason, "error": None,
           "golden": {"id": p.golden.id, "kind": p.golden.kind, "from": p.golden.where, "as_of": p.golden.as_of,
                      "sha256": p.golden.sha256},
           "output": p.output, "slot_names": None, "scorer": {"xtra_cli_commit": xtra_cli_commit()},
           "commands": commands(ctx, p.golden, p.output), "columns": [], "results": {}}
    _write(ctx, doc, if_none_match=True)

    def change(m: dict) -> None:
        k = manifest.crawl_entry(manifest.catalog_entry(m, ctx.catalog), ctx.crawl)
        manifest.add_unique(k.setdefault("scores", []), {"id": sid}, key=lambda s: s["id"])

    manifest.update(ctx.root, change)
    ctx.invalidate()
    return doc


def finish(ctx: Ctx, doc: dict, p: Prepared, log=print) -> dict:
    """Run the scorer on both bases, write values.parquet, and mark the score done (or failed)."""
    try:
        doc["slot_names"] = uses_slot_names(p.records)
        rows: list[dict] = []
        sizes = {}
        for basis in BASES:
            pages, left_out = basis_pages(p.golden.pages, basis)
            sizes[basis] = sum(1 for ents in pages.values() for e in ents for f in e["fields"] if not is_implied(f))
            if not sizes[basis]:
                doc["results"][basis] = None  # nothing to score on this basis
                continue
            reports = run_scorer(p.records, pages, ctx.catalog, ctx.crawl, f"{p.golden.where} ({basis})")
            mine = value_rows(basis, pages, reports)
            doc["results"][basis] = result(pages, left_out, reports, mine)
            rows += mine
        doc["golden"]["values"] = sizes
        doc["columns"] = sorted({r["column"] for r in rows if r["basis"] == "rule"})
        ctx.write_table(f"{layout.score_dir(ctx.catalog, ctx.crawl, doc['id'])}/values.parquet", rows,
                        model.SCORE_VALUES, if_none_match=False)
        doc["status"] = "done"
        if doc["slot_names"]:
            doc["error"] = SLOT_NAMES
    except Exception as e:  # noqa: BLE001 - the score says why it failed
        doc["status"], doc["error"] = "failed", str(e)
        log(f"{doc['id']} failed: {e}")
    doc["finished_at"] = _now()
    _write(ctx, doc)
    return doc


def score(ctx: Ctx, golden: str | None, output: str | None = None, by: str = "", reason: str = "", log=print) -> dict:
    """Score an extract output against a golden dataset, now (the CLI); an existing score of the pair is returned."""
    p = prepare(ctx, golden, output, log)
    return existing(ctx, p) or finish(ctx, begin(ctx, p, by, reason), p, log)


def interrupt_running(ctx: Ctx) -> list[str]:
    """A score left `running` by a restart becomes `interrupted` (it can be scored again)."""
    out = []
    for doc in all_scores(ctx):
        if doc["status"] == "running":
            doc["status"], doc["finished_at"] = "interrupted", _now()
            _write(ctx, doc)
            out.append(doc["id"])
    return out


def pending(ctx: Ctx) -> dict | None:
    """scores/pending.json, when its time has come."""
    try:
        doc = ctx.root.read_json(layout.pending_score(ctx.catalog, ctx.crawl))
    except FileNotFoundError:
        return None
    return doc if doc.get("due_at", "") <= _now() else None


def done_pending(ctx: Ctx) -> None:
    try:
        ctx.root.delete(layout.pending_score(ctx.catalog, ctx.crawl))
    except FileNotFoundError:
        pass


# --- CLI ---------------------------------------------------------------------------------------------
def _line(name: str, r: dict | None) -> str:
    if not r:
        return f"  {name:<15} no values to score"
    o = r["outcomes"]
    rate = "n/a" if r["exact_match_rate"] is None else f"{r['exact_match_rate']:.1%}"
    return (f"  {name:<15} {rate} exact of {r['values']:,} values · match {o['match']:,} · partial {o['partial']:,} "
            f"· wrong {o['wrong']:,} · missing {o['missing']:,}")


def cmd_score(args) -> int:
    ctx = Ctx.from_args(args)
    golden = HUMAN_REVIEWED if args.human_reviewed else args.draft or (
        golden_mod.version_name(args.ruleset) if args.ruleset else None)
    doc = score(ctx, golden, args.output, by=args.by, reason="golden-datasets score")
    out = doc["output"]
    print(f"{doc['id']}: extract output {out['id']} ({out['records']:,} records) vs {doc['golden']['id']} "
          f"[{doc['status']}]")
    if doc["status"] == "failed":
        print(f"  failed: {doc['error']}")
        return 1
    print(_line("human-reviewed", doc["results"].get("human")))
    print(_line("rule-matched", doc["results"].get("rule")))
    if out.get("records_mismatch"):
        print(f"  warning: {out['records']:,} records in the folder, the report says {out['records_written']:,}")
    if doc.get("slot_names"):
        print(f"  warning: {SLOT_NAMES}")
    return 0
