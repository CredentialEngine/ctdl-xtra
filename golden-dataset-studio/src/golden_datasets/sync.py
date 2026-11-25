"""`golden-datasets sync --from A --to B [--catalog C]`: copy a catalog's Studio files between roots.

Works in both directions between a local folder and an Azure prefix (and local → local, Azure → Azure). It's a
setup command, so it may list folders; the Studio itself never does.

What it copies, per catalog: its class folders (`<catalog>/<class>/**`: rules, rulesets, annotations, agent runs)
and the crawl's Studio files (`<catalog>/<crawl>/**`: the page index, assets, rule runs, golden versions), and the
catalog's manifest entry, merged into the target's manifest. The crawl itself stays in xtra-cli's container, which
the entry names (`crawls_root`): the Studio reads it there and never copies it.

Files that already exist in the target with the same size are skipped, so a sync can be resumed. The append-only
logs are copied by appending what the target is missing, never by overwriting.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import layout, manifest
from .catalogs import resolve
from .errors import UserError
from .storage import AzureRoot, LocalRoot, Root, open_root

MUTABLE = ("/assets/assets.parquet", "/assets/page_assets.parquet")


def cmd_sync(args) -> int:
    src, dst = open_root(args.src), open_root(args.dst)
    catalogs = [resolve(args.catalog)] if args.catalog else studio_catalogs(src)
    if isinstance(dst, LocalRoot):
        Path(dst.base).mkdir(parents=True, exist_ok=True)
    for catalog in catalogs:
        stats = sync_catalog(src, dst, catalog, args.crawl, args.dry_run)
        print(", ".join(f"{k} {v}" for k, v in stats.items()))
    return 0


def studio_catalogs(src: Root) -> list[str]:
    doc, _ = manifest.load(src)
    catalogs = [c["catalog"] for c in doc["catalogs"] if manifest.has_rules(c)]
    if not catalogs:
        raise UserError("the source has no Studio catalogs; name one with --catalog")
    return catalogs


def sync_catalog(src: Root, dst: Root, catalog: str, crawl: str | None, dry_run: bool, log=print) -> dict:
    entry = source_entry(src, catalog)
    crawl = crawl or entry.get("current_crawl")
    classes = sorted(entry.get("classes") or {})
    logs = {layout.annotations(catalog, c) for c in classes}
    todo = files_to_copy(src, dst, studio_prefixes(catalog, classes, crawl), logs)
    stats = {"catalog": catalog, "crawl": crawl, "classes": ",".join(classes), "studio_files": len(todo)}
    if dry_run:
        return stats
    copy_files(src, dst, catalog, todo, log)
    stats.update(copy_logs(src, dst, logs))
    merge_entry(dst, catalog, entry, crawl, src.uri)
    stats["manifest"] = "merged"
    return stats


def source_entry(src: Root, catalog: str) -> dict:
    src_doc, _ = manifest.load(src)
    entry = manifest.catalog_entry(src_doc, catalog, create=False)
    if entry is None:
        raise UserError(f"{catalog}: not in {src.uri}'s manifest")
    return entry


def studio_prefixes(catalog: str, classes: list[str], crawl: str | None) -> list[str]:
    return [layout.class_dir(catalog, c) for c in classes] + ([layout.crawl_dir(catalog, crawl)] if crawl else [])


def files_to_copy(src: Root, dst: Root, prefixes: list[str], logs: set[str]) -> list[str]:
    plan: list[str] = []
    have: dict[str, int] = {}
    src_sizes: dict[str, int] = {}
    for prefix in prefixes:
        plan += src.list(prefix)
        src_sizes.update(src.sizes(prefix))
        have.update(target_sizes(dst, prefix))
    # Files rewritten in place (the asset tables) may keep their size; copy them every time.
    return [p for p in plan if p not in logs and (have.get(p) != src_sizes.get(p) or p.endswith(MUTABLE))]


def target_sizes(dst: Root, prefix: str) -> dict[str, int]:
    try:
        return dst.sizes(prefix)
    except FileNotFoundError:
        return {}


def copy_files(src: Root, dst: Root, catalog: str, todo: list[str], log) -> None:
    with ThreadPoolExecutor(max_workers=16) as pool:
        done = 0
        for _ in pool.map(lambda p: copy_one(src, dst, p), todo):
            done += 1
            if done % 200 == 0:
                log(f"  {catalog}: {done}/{len(todo)} files", file=sys.stderr)


def copy_logs(src: Root, dst: Root, logs: set[str]) -> dict[str, str]:
    return {f"annotations {path.split('/')[-2]}": copy_log(src, dst, path)
            for path in sorted(logs) if src.exists(path)}


def merge_entry(dst: Root, catalog: str, entry: dict, crawl: str | None, src_uri: str) -> None:
    entry = {**entry, "crawls": [k for k in entry["crawls"] if k["crawl"] == crawl] or entry["crawls"]}
    entry.setdefault("crawls_root", src_uri)  # a catalog added before crawls were read in place

    def change(doc: dict) -> None:
        doc["catalogs"] = [c for c in doc["catalogs"] if c["catalog"] != catalog] + [entry]
        doc["catalogs"].sort(key=lambda c: c["name"].lower())

    manifest.update(dst, change)


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
