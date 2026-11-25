"""`golden-datasets init` and `golden-datasets extract` (spec §3.2, §4.3).

`init` indexes a crawl's saved pages into `pages.parquet` and registers the crawl in the manifest.

`extract` runs one ruleset version over every saved page of the crawl and writes an immutable extraction
(`page_labels`, `occurrences`, `matches`, `signals` + `extraction.json`). When a parent extraction exists, rules
whose `input_hash` is unchanged are copied from it (row-identical) and only the changed rules are rerun, on the
pages they can apply to.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime

from . import engine, layout, manifest, model, signals
from .context import Ctx
from .errors import ConflictError, UserError
from .sync import pick_crawl

_TITLE = re.compile(rb"<title[^>]*>(.*?)</title>", re.S | re.I)


# =====================================================================================================
# init
# =====================================================================================================
def cmd_init(args) -> int:
    ctx = Ctx(args.root, args.catalog, args.crawl)
    t = time.perf_counter()
    out = init(ctx, args.crawl)
    print(" · ".join(f"{k} {v}" for k, v in out.items()) + f" · {time.perf_counter() - t:.1f}s")
    return 0


def init(ctx: Ctx, crawl: str | None = None) -> dict:
    crawl = pick_crawl(ctx.crawl_root, ctx.catalog, crawl or ctx._crawl)
    pages_path = layout.pages_parquet(ctx.catalog, crawl)
    out = {"catalog": ctx.catalog, "crawl": crawl, "pages": _index_pages(ctx, crawl, pages_path)}
    n = len(ctx.read_table(pages_path, columns=["page_stem"]))
    _register_crawl(ctx, crawl, pages_path, n)
    out["page_count"] = n
    return out


def _index_pages(ctx: Ctx, crawl: str, pages_path: str) -> int | str:
    """Writes `pages.parquet` unless it exists; the number of pages it holds, or "exists"."""
    if ctx.root.exists(pages_path):
        return "exists"
    rows = _page_rows(ctx, crawl)
    ctx.write_table(pages_path, rows, model.PAGES)
    return len(rows)


def _register_crawl(ctx: Ctx, crawl: str, pages_path: str, n: int) -> None:
    def change(doc: dict) -> None:
        cat = manifest.catalog_entry(doc, ctx.catalog)
        k = manifest.crawl_entry(cat, crawl)
        k.update(crawl_json=layout.crawl_json(ctx.catalog, crawl), pages_dir=layout.pages_dir(ctx.catalog, crawl),
                 pages=pages_path, page_count=n)
        cat["current_crawl"] = crawl
        cat["crawls_root"] = ctx.crawl_root.uri

    manifest.update(ctx.root, change)


def _page_rows(ctx: Ctx, crawl: str) -> list[dict]:
    metas = [p for p in ctx.crawl_root.list(layout.pages_dir(ctx.catalog, crawl)) if p.endswith(".meta.json")]
    if not metas:
        raise UserError(f"no saved pages under {ctx.crawl_root.uri}/{layout.pages_dir(ctx.catalog, crawl)}")
    with ThreadPoolExecutor(max_workers=16) as pool:
        rows = list(pool.map(lambda p: _page_row(ctx, crawl, p), metas))
    rows = [r for r in rows if ctx.crawl_root.exists(r["html_path"])] if len(rows) < 50 else rows
    rows.sort(key=lambda r: r["page_stem"])
    return rows


def _page_row(ctx: Ctx, crawl: str, meta_path: str) -> dict:
    meta = json.loads(ctx.crawl_root.read_bytes(meta_path))
    stem = meta.get("stem") or meta_path.rsplit("/", 1)[-1][: -len(".meta.json")]
    html_path = layout.page_html(ctx.catalog, crawl, stem)
    head = ctx.crawl_root.local_path(html_path).open("rb").read(300_000)
    return {"crawl": crawl, "page_stem": stem, "url": meta.get("final_url") or meta["requested_url"],
            "requested_url": meta["requested_url"], "http_status": meta.get("http_status"),
            "retrieved_at": meta.get("retrieved_at"), "bytes": meta.get("bytes"), "sha256": meta.get("sha256"),
            "html_path": html_path, "title": _page_title(head)}


def _page_title(head: bytes) -> str | None:
    m = _TITLE.search(head)
    if not (m and m.group(1).strip()):
        return None
    import html as htmllib

    return re.sub(r"\s+", " ", htmllib.unescape(m.group(1).decode("utf-8", "replace"))).strip() or None


# =====================================================================================================
# extract
# =====================================================================================================
def cmd_extract(args) -> int:
    ctx = Ctx.from_args(args)
    t = time.perf_counter()
    meta = extract(ctx, args.ruleset, args.again, log=lambda m: print(m, file=sys.stderr))
    rows = " · ".join(f"{k.split('.')[0]} {v['rows']:,}" for k, v in meta["files"].items())
    print(f"{meta['extraction']} (ruleset v{meta['ruleset_version']}, parent {meta['parent_extraction']}): {rows}")
    print(f"  rerun {len(meta['rerun_rules'])} rules on {meta['rerun_pages']:,} pages · copied "
          f"{len(meta['copied_rules'])} · {time.perf_counter() - t:.1f}s")
    return 0


def extract(ctx: Ctx, ruleset_version: int | None = None, again: bool = False, created_by: str = "golden-datasets extract",
            log=lambda *a: None) -> dict:
    from .check import check_before_write

    v = ruleset_version or ctx.latest_ruleset()
    ext = next_extraction_id(ctx, v, again)
    rs, rules = ctx.ruleset_rules(v)
    parent = None if again else pick_parent(ctx, rs)
    result = compute(ctx, rules, rs["settings"], parent, log=log)
    check_before_write(ctx, rs, rules, result["tables"])
    try:
        return write_extraction(ctx, ext, v, parent, result, created_by)
    except ConflictError as exc:
        raise UserError(f"{ext}: {exc} (someone else wrote it first)") from None


def next_extraction_id(ctx: Ctx, ruleset_version: int, again: bool) -> str:
    existing = {e["extraction"] for e in ctx.extractions()}
    base = model.ext_id(ruleset_version)
    if base not in existing:
        return base
    if not again:
        raise UserError(f"extraction {base} already exists (extractions are immutable; use --again to re-extract)")
    for suffix in "bcdefghijklmnopqrstuvwxyz":
        if f"{base}-{suffix}" not in existing:
            return f"{base}-{suffix}"
    raise UserError("too many re-extractions")


def pick_parent(ctx: Ctx, ruleset: dict) -> str | None:
    """The extraction of the parent ruleset version (or the latest earlier one) on this crawl."""
    v = ruleset.get("parent_version")
    while v:
        ext = ctx.extraction_for(v)
        if ext:
            return ext
        v = ctx.ruleset(v).get("parent_version")
    return None


def write_extraction(ctx: Ctx, ext: str, ruleset_version: int, parent_ext: str | None, result: dict,
                     created_by: str) -> dict:
    files = _write_extraction_tables(ctx, ext, result["tables"])
    meta = {"catalog": ctx.catalog, "crawl": ctx.crawl, "extraction": ext, "ruleset_version": ruleset_version,
            "parent_extraction": parent_ext, "copied_from": parent_ext, "created_at": now_iso(),
            "created_by": created_by,
            "engine": {"name": "golden_datasets.engine", "css_path_anchor": "document root",
                       "offsets": "DOM textContent"},
            **result["meta"], "files": files}
    ctx.root.write_json(layout.extraction_file(ctx.catalog, ctx.crawl, ctx.cls, ext, "extraction"), meta, if_none_match=True)
    _register_extraction(ctx, ext, ruleset_version, parent_ext)
    return meta


def _write_extraction_tables(ctx: Ctx, ext: str, tables: dict[str, list[dict]]) -> dict[str, dict]:
    files = {}
    for name in layout.EXTRACTION_TABLES:
        info = ctx.write_table(layout.extraction_file(ctx.catalog, ctx.crawl, ctx.cls, ext, name), tables[name],
                               model.TABLE_SCHEMAS[name])
        files[f"{name}.parquet"] = {"rows": info["rows"], "sha256": info["sha256"]}
    return files


def _register_extraction(ctx: Ctx, ext: str, ruleset_version: int, parent_ext: str | None) -> None:
    def change(doc: dict) -> None:
        k = manifest.crawl_class(manifest.crawl_entry(manifest.catalog_entry(doc, ctx.catalog), ctx.crawl), ctx.cls)
        manifest.add_unique(k["extractions"], {"extraction": ext, "ruleset_version": ruleset_version,
                                               "path": layout.extraction_dir(ctx.catalog, ctx.crawl, ctx.cls, ext),
                                               "parent_extraction": parent_ext}, key=lambda e: e["extraction"])
        manifest.catalog_entry(doc, ctx.catalog)["status"] = "ready"

    manifest.update(ctx.root, change)


# =====================================================================================================
# compute: one ruleset over the crawl, rerunning only what changed
# =====================================================================================================
@dataclass
class _Work:
    """What one compute does: the pages to parse, what to compute on each, and what it copies from the parent."""
    pages: list[dict]
    parent_ext: str | None
    plan: dict
    by_kind: dict[str, set[str]]
    parent_tables: dict[str, list[dict]]
    locators_rerun: set[str] = field(default_factory=set)
    page_signals: bool = True
    no_rule: set[str] = field(default_factory=set)
    stems: list[str] = field(default_factory=list)
    need: dict = field(default_factory=dict)
    labels_from_parent: dict[str, list[str]] | None = None

    @property
    def first(self) -> bool:
        return not self.parent_ext

    @property
    def url_of(self) -> dict[str, str]:
        return {pg["page_stem"]: pg["url"] for pg in self.pages}


def compute(ctx: Ctx, rules: dict[str, dict], settings: dict, parent_ext: str | None = None,
            log=lambda *a: None) -> dict:
    """Run `rules` over the crawl (rerunning only what changed since `parent_ext`). Writes nothing.

    Returns {"tables": {name: rows}, "meta": {...}}. Used by `extract`, `rule try` and `rule publish`."""
    t0 = time.perf_counter()
    w = _plan_work(ctx, rules, settings, parent_ext, ctx.pages())
    log(f"  parsing {len(w.stems)} pages ({len(w.need['properties'])} property rules, labels={w.need['labels']})")
    paths = _local_page_paths(ctx, w.stems)
    t_fetch = time.perf_counter()
    results = _run_pages(_page_jobs(w, paths), rules, settings)
    t_pages = time.perf_counter()
    tables = _assemble_tables(w, rules, settings, results)
    t_end = time.perf_counter()
    return {"tables": tables, "meta": _compute_meta(w, rules, results, (t0, t_fetch, t_pages, t_end))}


def plan(rules: dict[str, dict], settings: dict, parent: dict | None, parent_rules: dict[str, dict] | None,
         parent_settings: dict | None) -> dict:
    """Which rules rerun and which are copied (spec §4.3)."""
    hashes = model.input_hashes(rules, settings["content_root"])
    if parent is None:
        return {"input_hashes": hashes, "rerun": set(rules), "copied": set(), "settings_changed": True}
    old = parent.get("input_hashes", {})
    rerun = {rid for rid in rules if old.get(rid) != hashes[rid]}
    # A changed key rule changes record_external_identifier on the occurrences of its locator.
    for loc in [r for r in rules if rules[r]["kind"] == "locator"]:
        code = model.key_rule_for(loc, rules)
        old_code = model.key_rule_for(loc, parent_rules or {}) if parent_rules else None
        if code in rerun or code != old_code:
            rerun.add(loc)
    return {"input_hashes": hashes, "rerun": rerun, "copied": set(rules) - rerun,
            "settings_changed": (parent_settings or {}) != settings}


def _plan_work(ctx: Ctx, rules: dict[str, dict], settings: dict, parent_ext: str | None, pages: list[dict]) -> _Work:
    """Which pages must be parsed, and what to compute on each."""
    p = _plan_against_parent(ctx, rules, settings, parent_ext)
    w = _Work(pages=pages, parent_ext=parent_ext, plan=p,
              by_kind={k: {r for r in rules if rules[r]["kind"] == k} for k in model.KINDS},
              parent_tables=_parent_tables(ctx, parent_ext))
    page_rules_rerun = p["rerun"] & w.by_kind["page"]
    w.locators_rerun = p["rerun"] & w.by_kind["locator"]
    w.page_signals = p["settings_changed"] or bool(page_rules_rerun or w.locators_rerun) or not parent_ext
    # a property with no rule yet runs nothing and keeps no rows (property-rules spec §4.6)
    w.no_rule = {f for f in w.by_kind["property"] if rules[f]["definition"].get("rule_type") == "none"}
    props_needed = _properties_needed(rules, w) - w.no_rule
    w.stems = _stems_to_parse(rules, w, props_needed, page_rules_rerun)
    _decide_page_needs(w, props_needed, page_rules_rerun)
    return w


def _local_page_paths(ctx: Ctx, stems: list[str]) -> dict:
    with ThreadPoolExecutor(max_workers=16) as tpool:
        return dict(zip(stems, tpool.map(ctx.page_path, stems)))


def _page_jobs(w: _Work, paths: dict) -> list[tuple]:
    url_of = w.url_of
    return [(s, url_of[s], str(paths[s]),
             {**w.need, "matched": None if w.labels_from_parent is None else w.labels_from_parent.get(s, [])})
            for s in w.stems]


def _run_pages(jobs: list[tuple], rules: dict[str, dict], settings: dict) -> list[dict]:
    n = workers()
    if n <= 1 or len(jobs) < 20:
        _init_worker(rules, settings)
        return [_run_page(j) for j in jobs]
    with ProcessPoolExecutor(max_workers=n, initializer=_init_worker, initargs=(rules, settings)) as pool:
        return list(pool.map(_run_page, jobs, chunksize=4))


def _assemble_tables(w: _Work, rules: dict[str, dict], settings: dict, results: list[dict]) -> dict[str, list[dict]]:
    """The fresh rows of what reran, the parent's rows of what was copied; every row with this ruleset's versions."""
    fresh = {name: [r for res in results for r in res[name]] for name in ("page_labels", "occurrences", "matches")}
    tables = {"page_labels": _page_labels(w, rules, fresh), "occurrences": _occurrences(w, rules, fresh),
              "matches": _matches(w, rules, fresh)}
    _stamp_rule_versions(tables, rules)
    tables["signals"] = _signals(w, tables, rules, settings, results)
    return {name: model.sort_rows(name, rows) for name, rows in tables.items()}


def _compute_meta(w: _Work, rules: dict[str, dict], results: list[dict], times: tuple[float, ...]) -> dict:
    t0, t_fetch, t_pages, t_end = times
    return {
        "input_hashes": w.plan["input_hashes"],
        "rerun_rules": sorted(w.plan["rerun"]) if w.parent_ext else sorted(rules),
        "copied_rules": sorted(w.plan["copied"]) if w.parent_ext else [],
        "rerun_pages": len(w.stems),
        "pages_total": len(w.pages),
        "pages_without_content_root": sum(1 for res in results if res.get("facts") and not res["facts"]["has_content_root"]),
        "timings_s": {"fetch_pages": round(t_fetch - t0, 2), "parse_and_rules": round(t_pages - t_fetch, 2),
                      "signals_and_assembly": round(t_end - t_pages, 2), "total": round(t_end - t0, 2)},
    }


def _plan_against_parent(ctx: Ctx, rules: dict[str, dict], settings: dict, parent_ext: str | None) -> dict:
    parent_meta = ctx.extraction_meta(parent_ext) if parent_ext else None
    parent_rules = parent_settings = None
    if parent_meta:
        prs, parent_rules = ctx.ruleset_rules(parent_meta["ruleset_version"])
        parent_settings = prs["settings"]
    return plan(rules, settings, parent_meta, parent_rules, parent_settings)


def _parent_tables(ctx: Ctx, parent_ext: str | None) -> dict[str, list[dict]]:
    if not parent_ext:
        return {}
    return {name: ctx.table(parent_ext, name).to_pylist() for name in layout.EXTRACTION_TABLES}


def _properties_needed(rules: dict[str, dict], w: _Work) -> set[str]:
    props = set(w.by_kind["property"]) if w.first else set(w.plan["rerun"] & w.by_kind["property"])
    for loc in w.locators_rerun:  # property rules of a rerun locator rerun too (their occurrence keys may change)
        props |= {f for f in w.by_kind["property"] if rules[f]["definition"]["locator"] == loc}
    return props


def _stems_to_parse(rules: dict[str, dict], w: _Work, props_needed: set[str], page_rules_rerun: set[str]) -> list[str]:
    if w.first or page_rules_rerun or w.page_signals:
        return [pg["page_stem"] for pg in w.pages]
    wanted_locs = {rules[f]["definition"]["locator"] for f in props_needed} | w.locators_rerun
    matched_rules = {(lb["page_stem"], lb["rule_id"]) for lb in w.parent_tables["page_labels"] if lb["matched"]}
    return sorted({pg["page_stem"] for pg in w.pages for loc in wanted_locs
                   if any((pg["page_stem"], pr) in matched_rules
                          for pr in rules[loc]["definition"].get("page_rules", []))})


def _decide_page_needs(w: _Work, props_needed: set[str], page_rules_rerun: set[str]) -> None:
    w.need = {"labels": w.first or bool(page_rules_rerun), "locators": sorted(w.by_kind["locator"]),
              "properties": sorted(props_needed), "page_facts": w.page_signals}
    if not w.need["labels"]:
        w.labels_from_parent = {}
        for lb in w.parent_tables["page_labels"]:
            if lb["matched"]:
                w.labels_from_parent.setdefault(lb["page_stem"], []).append(lb["rule_id"])


def _page_labels(w: _Work, rules: dict[str, dict], fresh: dict[str, list[dict]]) -> list[dict]:
    labels = fresh["page_labels"] if w.need["labels"] else w.parent_tables["page_labels"]
    return [r for r in labels if r["rule_id"] in rules]  # rules no longer in the ruleset leave no rows behind


def _occurrences(w: _Work, rules: dict[str, dict], fresh: dict[str, list[dict]]) -> list[dict]:
    if w.locators_rerun or w.first:
        return fresh["occurrences"]
    # a locator no longer in the ruleset leaves no occurrences behind
    occurrences = [o for o in w.parent_tables["occurrences"] if o["locator_rule_id"] in rules]
    _assert_same_keys(occurrences, fresh["occurrences"], w.stems)
    return occurrences


def _matches(w: _Work, rules: dict[str, dict], fresh: dict[str, list[dict]]) -> list[dict]:
    fresh_props = set(w.need["properties"])
    matches = [m for m in w.parent_tables.get("matches", []) if m["rule_id"] not in fresh_props] \
        + [m for m in fresh["matches"] if m["rule_id"] in fresh_props]
    return [r for r in matches if r["rule_id"] in rules and r["rule_id"] not in w.no_rule]


def _stamp_rule_versions(tables: dict[str, list[dict]], rules: dict[str, dict]) -> None:
    """Copied rows must carry the version of the rule in *this* ruleset (same hash, so same definition)."""
    for name, col in (("page_labels", "rule_version"), ("matches", "rule_version")):
        for r in tables[name]:
            r[col] = rules[r["rule_id"]]["version"]
    for o in tables["occurrences"]:
        o["locator_rule_version"] = rules[o["locator_rule_id"]]["version"]


def _signals(w: _Work, tables: dict[str, list[dict]], rules: dict[str, dict], settings: dict,
             results: list[dict]) -> list[dict]:
    facts = [res["facts"] for res in results if res.get("facts") is not None]
    old_page_signals = None if w.page_signals else [s for s in w.parent_tables["signals"] if s["target_kind"] == "page"
                                                    and (s.get("rule_id") is None or s["rule_id"] in rules)]
    return signals.compute(tables, rules, settings, facts, w.url_of, old_page_signals)


def _assert_same_keys(parent_occ: list[dict], fresh_occ: list[dict], stems: list[str]) -> None:
    """When locators are copied, rerunning property rules must find the same occurrences as the parent."""
    stems_set = set(stems)
    a = sorted(o["occurrence_key"] for o in parent_occ if o["page_stem"] in stems_set)
    b = sorted(o["occurrence_key"] for o in fresh_occ)
    if a != b:
        raise RuntimeError(f"occurrences differ from the parent extraction on unchanged locators "
                           f"({len(set(a) ^ set(b))} keys); is the engine deterministic?")


# --- the worker processes --------------------------------------------------------------------------
_W: dict = {}


def _init_worker(rules: dict, settings: dict) -> None:
    _W.update(rules=rules, settings=settings)


def _run_page(job: tuple) -> dict:
    stem, url, path, need = job
    with open(path, "rb") as fh:
        html = fh.read()
    return engine.run_page(stem, url, html, _W["rules"], _W["settings"], need)


def workers() -> int:
    return int(os.environ.get("GOLDEN_DATASETS_WORKERS", min(10, os.cpu_count() or 4)))


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
