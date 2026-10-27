"""`golden-datasets sync --from A --to B [--catalog C]`: copy Studio files and saved pages between roots.

Works in both directions between a local folder and an Azure prefix (and local → local, Azure → Azure). It's a
setup command, so it may list folders; the Studio itself never does.

What it copies, per catalog:
- `<catalog>/golden-dataset-studio/**` (rules, rulesets, annotations) and `<catalog>/<crawl>/golden-dataset-studio/**`;
- unless `--studio-only`: the crawl's inputs, `crawl.json` and `pages/*` (`--pages copy | link | skip`);
- the catalog's manifest entry, merged into the target's manifest.

Files that already exist in the target with the same size are skipped, so a sync can be resumed. The append-only
log is copied by appending what the target is missing, never by overwriting.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import layout, manifest
from .catalogs import resolve
from .errors import UserError
from .storage import AzureRoot, LocalRoot, Root, open_root


def pick_crawl(root: Root, catalog: str, crawl: str | None) -> str:
    """The given crawl, else the manifest's current crawl, else the latest folder that has crawl.json + pages/."""
    if crawl:
        return crawl
    doc, _ = manifest.load(root)
    cat = manifest.catalog_entry(doc, catalog, create=False)
    if cat and cat.get("current_crawl"):
        return cat["current_crawl"]
    candidates = [d for d in root.list_dirs(catalog) if d[:4].isdigit() and root.exists(f"{catalog}/{d}/crawl.json")]
    if not candidates:
        raise UserError(f"no crawl found under {root.uri}/{catalog}")
    with_review = [d for d in candidates if root.list_dirs(f"{catalog}/{d}/review-ui")]
    return sorted(with_review or candidates)[-1]


def copy_one(src: Root, dst: Root, path: str) -> None:
    if isinstance(src, AzureRoot) and isinstance(dst, AzureRoot) and src.account == dst.account:
        dst.copy_from_url(path, src.blob_url_with_sas(path))
    elif isinstance(src, LocalRoot):
        dst.write_file(path, src.local_path(path))
    else:
        dst.write_bytes(path, src.read_bytes(path))


def copy_log(src: Root, dst: Root, path: str) -> str:
    """Append to the target what it is missing. Refuses when the two logs have diverged."""
    data = src.read_bytes(path)
    st = dst.stat(path)
    have = dst.read_bytes(path) if st else b""
    if have == data:
        return "same"
    if data.startswith(have):
        dst.append(path, data[len(have):])
        return f"appended {len(data) - len(have)} bytes"
    if have.startswith(data):
        return "target is ahead"
    raise UserError(f"{path}: the two logs have diverged; merge them by hand (they are append-only JSONL)")


def sync_catalog(src: Root, dst: Root, catalog: str, crawl: str | None, pages: str, studio_only: bool,
                 dry_run: bool, log=print) -> dict:
    crawl = pick_crawl(src, catalog, crawl)
    plan: list[str] = []
    for prefix in (layout.catalog_dir(catalog), layout.crawl_dir(catalog, crawl)):
        plan += src.list(prefix)
    page_files: list[str] = []
    if not studio_only:
        plan.append(layout.crawl_json(catalog, crawl))
        if pages != "skip":
            page_files = [p for p in src.list(layout.pages_dir(catalog, crawl))
                          if p.endswith(".html") or p.endswith(".meta.json")]
    have = {}
    for prefix in (layout.catalog_dir(catalog), layout.crawl_input(catalog, crawl)):
        try:
            have.update(dst.sizes(prefix))
        except FileNotFoundError:
            pass
    src_sizes = {}
    for prefix in (layout.catalog_dir(catalog), layout.crawl_input(catalog, crawl)):
        src_sizes.update(src.sizes(prefix))

    log_path = layout.annotations(catalog)
    todo = [p for p in plan if p != log_path and have.get(p) != src_sizes.get(p)]
    if pages == "link":
        if not (isinstance(src, LocalRoot) and isinstance(dst, LocalRoot)):
            raise UserError("--pages link works only from a local folder to a local folder")
        page_todo = []
    else:
        page_todo = [p for p in page_files if have.get(p) != src_sizes.get(p)]
    stats = {"catalog": catalog, "crawl": crawl, "studio_files": len(todo), "pages_to_copy": len(page_todo),
             "pages_total": len(page_files)}
    if dry_run:
        return stats
    if pages == "link":
        assert isinstance(src, LocalRoot) and isinstance(dst, LocalRoot)
        dst.symlink(layout.pages_dir(catalog, crawl), src.local_path(layout.pages_dir(catalog, crawl)))
    with ThreadPoolExecutor(max_workers=16) as pool:
        done = 0
        for _ in pool.map(lambda p: copy_one(src, dst, p), todo + page_todo):
            done += 1
            if done % 200 == 0:
                log(f"  {catalog}: {done}/{len(todo) + len(page_todo)} files", file=sys.stderr)
    if src.exists(log_path):
        stats["annotations"] = copy_log(src, dst, log_path)

    src_doc, _ = manifest.load(src)
    entry = manifest.catalog_entry(src_doc, catalog, create=False)
    if entry is not None:
        entry = {**entry, "crawls": [k for k in entry["crawls"] if k["crawl"] == crawl] or entry["crawls"]}

        def change(doc: dict) -> None:
            doc["catalogs"] = [c for c in doc["catalogs"] if c["catalog"] != catalog] + [entry]
            doc["catalogs"].sort(key=lambda c: c["name"].lower())

        manifest.update(dst, change)
        stats["manifest"] = "merged"
    return stats


def cmd_sync(args) -> int:
    src, dst = open_root(args.src), open_root(args.dst)
    if args.catalog:
        catalogs = [resolve(args.catalog)]
    else:
        doc, _ = manifest.load(src)
        catalogs = [c["catalog"] for c in doc["catalogs"] if c.get("rulesets")]
        if not catalogs:
            raise UserError("the source has no Studio catalogs; name one with --catalog")
    if isinstance(dst, LocalRoot):
        Path(dst.base).mkdir(parents=True, exist_ok=True)
    for catalog in catalogs:
        stats = sync_catalog(src, dst, catalog, args.crawl, args.pages, args.studio_only, args.dry_run)
        print(" · ".join(f"{k} {v}" for k, v in stats.items()))
    return 0
