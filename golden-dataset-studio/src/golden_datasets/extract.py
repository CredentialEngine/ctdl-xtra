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
from datetime import UTC, datetime

from . import engine, layout, manifest, model, signals
from .context import Ctx
from .errors import ConflictError, UserError
from .sync import pick_crawl

_TITLE = re.compile(rb"<title[^>]*>(.*?)</title>", re.S | re.I)


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def workers() -> int:
    return int(os.environ.get("GOLDEN_DATASETS_WORKERS", min(10, os.cpu_count() or 4)))


# =====================================================================================================
# init
# =====================================================================================================
def _page_row(ctx: Ctx, crawl: str, meta_path: str) -> dict:
    meta = json.loads(ctx.root.read_bytes(meta_path))
    stem = meta.get("stem") or meta_path.rsplit("/", 1)[-1][: -len(".meta.json")]
    html_path = layout.page_html(ctx.catalog, crawl, stem)
    head = ctx.root.local_path(html_path).open("rb").read(300_000)
    m = _TITLE.search(head)
    title = None
    if m and m.group(1).strip():
        import html as htmllib

        title = re.sub(r"\s+", " ", htmllib.unescape(m.group(1).decode("utf-8", "replace"))).strip() or None
    return {"crawl": crawl, "page_stem": stem, "url": meta.get("final_url") or meta["requested_url"],
            "requested_url": meta["requested_url"], "http_status": meta.get("http_status"),
            "retrieved_at": meta.get("retrieved_at"), "bytes": meta.get("bytes"), "sha256": meta.get("sha256"),
            "html_path": html_path, "title": title}


def init(ctx: Ctx, crawl: str | None = None) -> dict:
    crawl = pick_crawl(ctx.root, ctx.catalog, crawl or ctx._crawl)
    pages_path = layout.pages_parquet(ctx.catalog, crawl)
    out = {"catalog": ctx.catalog, "crawl": crawl}
    if ctx.root.exists(pages_path):
        out["pages"] = "exists"
    else:
        metas = [p for p in ctx.root.list(layout.pages_dir(ctx.catalog, crawl)) if p.endswith(".meta.json")]
        if not metas:
            raise UserError(f"no saved pages under {ctx.root.uri}/{layout.pages_dir(ctx.catalog, crawl)}")
        with ThreadPoolExecutor(max_workers=16) as pool:
            rows = list(pool.map(lambda p: _page_row(ctx, crawl, p), metas))
        rows = [r for r in rows if ctx.root.exists(r["html_path"])] if len(rows) < 50 else rows
        rows.sort(key=lambda r: r["page_stem"])
        ctx.write_table(pages_path, rows, model.PAGES)
        out["pages"] = len(rows)
    n = len(ctx.read_table(pages_path, columns=["page_stem"]))

    def change(doc: dict) -> None:
        cat = manifest.catalog_entry(doc, ctx.catalog)
        k = manifest.crawl_entry(cat, crawl)
        k.update(crawl_json=layout.crawl_json(ctx.catalog, crawl), pages_dir=layout.pages_dir(ctx.catalog, crawl),
                 pages=pages_path, page_count=n)
        cat["current_crawl"] = crawl

    manifest.update(ctx.root, change)
    out["page_count"] = n
    return out


def cmd_init(args) -> int:
    ctx = Ctx(args.root, args.catalog, args.crawl)
    t = time.perf_counter()
    out = init(ctx, args.crawl)
    print(" · ".join(f"{k} {v}" for k, v in out.items()) + f" · {time.perf_counter() - t:.1f}s")
    return 0


# =====================================================================================================
# extract
# =====================================================================================================
_W: dict = {}


def _init_worker(rules: dict, settings: dict) -> None:
    _W.update(rules=rules, settings=settings)


def _run_page(job: tuple) -> dict:
    stem, url, path, need = job
    with open(path, "rb") as fh:
        html = fh.read()
    return engine.run_page(stem, url, html, _W["rules"], _W["settings"], need)


def plan(rules: dict[str, dict], settings: dict, parent: dict | None, parent_rules: dict[str, dict] | None,
         parent_settings: dict | None) -> dict:
    """Which rules rerun and which are copied (spec §4.3)."""
    hashes = model.input_hashes(rules, settings["content_root"])
    if parent is None:
        return {"input_hashes": hashes, "rerun": set(rules), "copied": set(), "settings_changed": True}
    old = parent.get("input_hashes", {})
    rerun = {rid for rid in rules if old.get(rid) != hashes[rid]}
    # A changed code rule changes course_key on the occurrences of its locator.
    for loc in [r for r in rules if rules[r]["kind"] == "locator"]:
        code = model.code_rule_for(loc, rules, settings)
        old_code = model.code_rule_for(loc, parent_rules or {}, parent_settings or {}) if parent_rules else None
        if code in rerun or code != old_code:
            rerun.add(loc)
    return {"input_hashes": hashes, "rerun": rerun, "copied": set(rules) - rerun,
            "settings_changed": (parent_settings or {}) != settings}


def compute(ctx: Ctx, rules: dict[str, dict], settings: dict, parent_ext: str | None = None,
            log=lambda *a: None) -> dict:
    """Run `rules` over the crawl (rerunning only what changed since `parent_ext`). Writes nothing.

    Returns {"tables": {name: rows}, "meta": {...}}. Used by `extract`, `rule try` and `rule publish`."""
    t0 = time.perf_counter()
    pages = ctx.pages()
    parent_meta = ctx.extraction_meta(parent_ext) if parent_ext else None
    parent_rules = parent_settings = None
    if parent_meta:
        prs, parent_rules = ctx.ruleset_rules(parent_meta["ruleset_version"])
        parent_settings = prs["settings"]
    p = plan(rules, settings, parent_meta, parent_rules, parent_settings)
    rerun = p["rerun"]
    by_kind = {k: {r for r in rules if rules[r]["kind"] == k} for k in model.KINDS}

    parent_tables = {}
    if parent_ext:
        for name in layout.EXTRACTION_TABLES:
            parent_tables[name] = ctx.table(parent_ext, name).to_pylist()

    # Which pages must be parsed, and what to compute on each.
    page_rules_rerun = rerun & by_kind["page"]
    locators_rerun = rerun & by_kind["locator"]
    fields_rerun = rerun & by_kind["field"]
    page_signals = p["settings_changed"] or bool(page_rules_rerun or locators_rerun) or not parent_ext
    first = not parent_ext
    fields_needed = set(by_kind["field"]) if first else set(fields_rerun)
    for loc in locators_rerun:  # fields of a rerun locator rerun too (their occurrence keys may change)
        fields_needed |= {f for f in by_kind["field"] if rules[f]["definition"]["locator"] == loc}
    if first or page_rules_rerun or page_signals:
        stems = [pg["page_stem"] for pg in pages]
    else:
        wanted_locs = {rules[f]["definition"]["locator"] for f in fields_needed} | locators_rerun
        labels = parent_tables["page_labels"]
        matched_rules = {(lb["page_stem"], lb["rule_id"]) for lb in labels if lb["matched"]}
        stems = sorted({pg["page_stem"] for pg in pages for loc in wanted_locs
                        if any((pg["page_stem"], pr) in matched_rules
                               for pr in rules[loc]["definition"].get("page_rules", []))})
    need = {"labels": first or bool(page_rules_rerun), "locators": sorted(by_kind["locator"]),
            "fields": sorted(fields_needed), "page_facts": page_signals}
    url_of = {pg["page_stem"]: pg["url"] for pg in pages}
    labels_from_parent = None
    if not need["labels"]:
        labels_from_parent = {}
        for lb in parent_tables["page_labels"]:
            if lb["matched"]:
                labels_from_parent.setdefault(lb["page_stem"], []).append(lb["rule_id"])

    log(f"  parsing {len(stems)} pages ({len(need['fields'])} field rules, labels={need['labels']})")
    with ThreadPoolExecutor(max_workers=16) as tpool:
        paths = dict(zip(stems, tpool.map(ctx.page_path, stems)))
    t_fetch = time.perf_counter()
    jobs = [(s, url_of[s], str(paths[s]),
             {**need, "matched": None if labels_from_parent is None else labels_from_parent.get(s, [])})
            for s in stems]
    n = workers()
    if n <= 1 or len(jobs) < 20:
        _init_worker(rules, settings)
        results = [_run_page(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=n, initializer=_init_worker, initargs=(rules, settings)) as pool:
            results = list(pool.map(_run_page, jobs, chunksize=4))
    t_pages = time.perf_counter()

    fresh = {name: [r for res in results for r in res[name]] for name in ("page_labels", "occurrences", "matches")}
    fresh_fields = set(need["fields"])
    tables: dict[str, list[dict]] = {}
    if need["labels"]:
        tables["page_labels"] = fresh["page_labels"]
    else:
        tables["page_labels"] = parent_tables["page_labels"]
    if locators_rerun or first:
        tables["occurrences"] = fresh["occurrences"]
    else:
        tables["occurrences"] = parent_tables["occurrences"]
        _assert_same_keys(parent_tables["occurrences"], fresh["occurrences"], stems)
    tables["matches"] = [m for m in parent_tables.get("matches", []) if m["rule_id"] not in fresh_fields] \
        + [m for m in fresh["matches"] if m["rule_id"] in fresh_fields]
    # Rules that are no longer in the ruleset leave no rows behind.
    tables["page_labels"] = [r for r in tables["page_labels"] if r["rule_id"] in rules]
    tables["matches"] = [r for r in tables["matches"] if r["rule_id"] in rules]
    # Copied rows must carry the version of the rule in *this* ruleset (same hash, so same definition).
    for name, col in (("page_labels", "rule_version"), ("matches", "rule_version")):
        for r in tables[name]:
            r[col] = rules[r["rule_id"]]["version"]
    for o in tables["occurrences"]:
        o["locator_rule_version"] = rules[o["locator_rule_id"]]["version"]

    facts = [res["facts"] for res in results if res.get("facts") is not None]
    old_page_signals = None if page_signals else [s for s in parent_tables["signals"] if s["target_kind"] == "page"]
    tables["signals"] = signals.compute(tables, rules, settings, facts, url_of, old_page_signals)
    for name in tables:
        tables[name] = model.sort_rows(name, tables[name])
    t_end = time.perf_counter()
    meta = {
        "input_hashes": p["input_hashes"],
        "rerun_rules": sorted(rerun) if parent_ext else sorted(rules),
        "copied_rules": sorted(p["copied"]) if parent_ext else [],
        "rerun_pages": len(stems),
        "pages_total": len(pages),
        "pages_without_content_root": sum(1 for res in results if res.get("facts") and not res["facts"]["has_content_root"]),
        "timings_s": {"fetch_pages": round(t_fetch - t0, 2), "parse_and_rules": round(t_pages - t_fetch, 2),
                      "signals_and_assembly": round(t_end - t_pages, 2), "total": round(t_end - t0, 2)},
    }
    return {"tables": tables, "meta": meta}


def _assert_same_keys(parent_occ: list[dict], fresh_occ: list[dict], stems: list[str]) -> None:
    """When locators are copied, rerunning field rules must find the same occurrences as the parent."""
    stems_set = set(stems)
    a = sorted(o["occurrence_key"] for o in parent_occ if o["page_stem"] in stems_set)
    b = sorted(o["occurrence_key"] for o in fresh_occ)
    if a != b:
        raise RuntimeError(f"occurrences differ from the parent extraction on unchanged locators "
                           f"({len(set(a) ^ set(b))} keys); is the engine deterministic?")


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


def write_extraction(ctx: Ctx, ext: str, ruleset_version: int, parent_ext: str | None, result: dict,
                     created_by: str) -> dict:
    files = {}
    for name in layout.EXTRACTION_TABLES:
        info = ctx.write_table(layout.extraction_file(ctx.catalog, ctx.crawl, ext, name), result["tables"][name],
                               model.TABLE_SCHEMAS[name])
        files[f"{name}.parquet"] = {"rows": info["rows"], "sha256": info["sha256"]}
    meta = {"catalog": ctx.catalog, "crawl": ctx.crawl, "extraction": ext, "ruleset_version": ruleset_version,
            "parent_extraction": parent_ext, "copied_from": parent_ext, "created_at": now_iso(),
            "created_by": created_by,
            "engine": {"name": "golden_datasets.engine", "css_path_anchor": "document root",
                       "offsets": "DOM textContent"},
            **result["meta"], "files": files}
    ctx.root.write_json(layout.extraction_file(ctx.catalog, ctx.crawl, ext, "extraction"), meta, if_none_match=True)

    def change(doc: dict) -> None:
        k = manifest.crawl_entry(manifest.catalog_entry(doc, ctx.catalog), ctx.crawl)
        manifest.add_unique(k["extractions"], {"extraction": ext, "ruleset_version": ruleset_version,
                                               "path": layout.extraction_dir(ctx.catalog, ctx.crawl, ext),
                                               "parent_extraction": parent_ext}, key=lambda e: e["extraction"])
        manifest.catalog_entry(doc, ctx.catalog)["status"] = "ready"

    manifest.update(ctx.root, change)
    return meta


def pick_parent(ctx: Ctx, ruleset: dict) -> str | None:
    """The extraction of the parent ruleset version (or the latest earlier one) on this crawl."""
    v = ruleset.get("parent_version")
    while v:
        ext = ctx.extraction_for(v)
        if ext:
            return ext
        v = ctx.ruleset(v).get("parent_version")
    return None


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


def cmd_extract(args) -> int:
    ctx = Ctx.from_args(args)
    t = time.perf_counter()
    meta = extract(ctx, args.ruleset, args.again, log=lambda m: print(m, file=sys.stderr))
    rows = " · ".join(f"{k.split('.')[0]} {v['rows']:,}" for k, v in meta["files"].items())
    print(f"{meta['extraction']} (ruleset v{meta['ruleset_version']}, parent {meta['parent_extraction']}): {rows}")
    print(f"  rerun {len(meta['rerun_rules'])} rules on {meta['rerun_pages']:,} pages · copied "
          f"{len(meta['copied_rules'])} · {time.perf_counter() - t:.1f}s")
    return 0
