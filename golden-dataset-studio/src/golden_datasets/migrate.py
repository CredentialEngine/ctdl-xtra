"""`golden-datasets migrate --to-classes`: today's root → class folders (LearningProgram spec, approved items 20–22).

One time per root, and safe to run again: a second run finds nothing to do. `--dry-run` prints every step and changes
nothing. What it does:

1. **Class folders.** Everything the Studio keeps for a catalog moves under `course/` (the only class before this):
   `<catalog>/golden-dataset-studio/*` → `<catalog>/course/*`; per crawl, `extractions/` → `course/rule-runs/`,
   `golden/` → `course/golden/`, `scores/pending.json` → `course/scores-pending.json`; `pages.parquet` and `assets/`
   move up to `<catalog>/<crawl>/`. The root's `golden-dataset-studio/{profiles,agent-slots,agent-runs-recent}.json`
   move up to the root.
2. **xtra-cli's data goes back to xtra-cli's container** (`--xtra-root`): each extract output the Studio copied
   (`extract-outputs/<id>/`) → `<catalog>/<crawl>/extract/<id>/`, and each score (`scores/sc-NNNN/`) →
   `…/extract/<output id>/scores/<golden>/course/sc-NNNN/`.
3. **`course_key` → `record_external_identifier`** in every JSON, JSONL and Parquet file it moved (the annotation log,
   the occurrences tables, publications, agent run files), and the stale `course_key_rule` setting is dropped from
   the rulesets. A rewritten file keeps its original beside it as `<name>.legacy`; a rule run's `extraction.json`
   gets the new tables' hashes.
4. **Crawl copies.** `<catalog>/<crawl>/{crawl.json, pages/}` are removed once the same files (by size) are found in
   the catalog's crawl root (`--crawls-root`, else the one the manifest names, else `--xtra-root`); the manifest then
   names that root. A copy that can't be found elsewhere stays, and the Studio reads it where it is. (A symlinked
   `pages/` is unlinked; its target is never touched.)
5. **The manifest** becomes `manifest.json` (schema 2, per class); the old one stays as
   `golden-dataset-studio/manifest.json.legacy`.
"""

from __future__ import annotations

import io
import json
import sys
from dataclasses import dataclass, field

import pyarrow.parquet as pq

from . import layout, manifest
from .errors import UserError
from .storage import LocalRoot, Root, open_root
from .xtra_paths import extract_run_dir, score_dir, xtra_root

CLS = "course"
OLD = layout.STUDIO
LEGACY = ".legacy"
RENAMED = {"course_key": "record_external_identifier", "skipped_no_course_key": "skipped_no_record_external_identifier"}
ROOT_FILES = ("profiles.json", "agent-slots.json", "agent-runs-recent.json")


@dataclass
class Plan:
    moves: list[tuple[Root, str, Root, str]] = field(default_factory=list)   # (from root, path, to root, path)
    removals: list[tuple[str, str]] = field(default_factory=list)            # (path, why): crawl copies
    keeps: list[tuple[str, str]] = field(default_factory=list)               # (path, why)
    crawls_root: dict[str, str] = field(default_factory=dict)                # catalog → its crawl root
    path_map: dict[str, str] = field(default_factory=dict)                   # old Studio path → new (this run)
    xtra_map: dict[str, str] = field(default_factory=dict)                   # old Studio path → xtra path
    score_dirs: dict[str, str] = field(default_factory=dict)                 # old score folder → xtra folder


def _rename_keys(obj):
    """`course_key` → `record_external_identifier` at every depth; the stale `course_key_rule` setting is dropped."""
    if isinstance(obj, dict):
        return {RENAMED.get(k, k): _rename_keys(v) for k, v in obj.items() if k != "course_key_rule"}
    if isinstance(obj, list):
        return [_rename_keys(v) for v in obj]
    return obj


def rewrite(data: bytes, path: str) -> bytes | None:
    """The file in the new format, or None when it needs no change."""
    if path.endswith(".parquet"):
        table = pq.read_table(io.BytesIO(data))
        if not any(n in RENAMED for n in table.column_names):
            return None
        table = table.rename_columns([RENAMED.get(n, n) for n in table.column_names])
        buf = io.BytesIO()
        pq.write_table(table, buf, compression="zstd")
        return buf.getvalue()
    if path.endswith(".jsonl"):
        if b"course_key" not in data:
            return None
        lines = [json.dumps(_rename_keys(json.loads(x)), ensure_ascii=False) for x in data.decode().splitlines() if x]
        return ("\n".join(lines) + "\n").encode()
    if path.endswith(".json"):
        if b"course_key" not in data:
            return None
        return json.dumps(_rename_keys(json.loads(data)), ensure_ascii=False, indent=1).encode()
    return None


# --- the plan -------------------------------------------------------------------------------------------------
def _new_catalog_path(catalog: str, rel: str) -> str:
    return f"{layout.class_dir(catalog, CLS)}/{rel}"


def relocate(path: str) -> str:
    """A Studio path's new place (files and folders alike); paths outside `golden-dataset-studio/` stay."""
    parts = path.split("/")
    if len(parts) >= 2 and parts[1] == OLD:
        return _new_catalog_path(parts[0], "/".join(parts[2:])).rstrip("/")
    if len(parts) >= 3 and parts[2] == OLD:
        rel = "/".join(parts[3:])
        if rel in ("extractions", "golden"):
            rel += "/"
        new = _new_crawl_path(parts[0], parts[1], rel)
        return (new or path).rstrip("/")
    return path


def _new_crawl_path(catalog: str, crawl: str, rel: str) -> str | None:
    """A crawl's Studio file in the Studio's root; None for what goes to xtra-cli's container."""
    if rel == "pages.parquet" or rel.startswith("assets/"):
        return f"{layout.crawl_dir(catalog, crawl)}/{rel}"
    if rel.startswith("extractions/"):
        return f"{layout.crawl_class_dir(catalog, crawl, CLS)}/rule-runs/{rel[len('extractions/'):]}"
    if rel.startswith("golden/"):
        return f"{layout.crawl_class_dir(catalog, crawl, CLS)}/{rel}"
    if rel == "scores/pending.json":
        return layout.pending_score(catalog, crawl, CLS)
    if rel.startswith(("scores/", "extract-outputs/")):
        return None
    return f"{layout.crawl_class_dir(catalog, crawl, CLS)}/{rel}"


def _same_files(a: Root, b: Root, prefix: str) -> bool:
    """Every file below `prefix` in `a` (or the file `prefix` itself) is in `b` with the same size."""
    try:
        mine, theirs = a.sizes(prefix), b.sizes(prefix)
        if not mine:
            st, other = a.stat(prefix), b.stat(prefix)
            return st is not None and other is not None and st.size == other.size
    except Exception:  # noqa: BLE001 - an unreachable root (no access from here) can't confirm anything
        return False
    return all(theirs.get(p) == n for p, n in mine.items())


def plan(root: Root, xtra: Root | None, crawls: Root | None, legacy: dict, log=print) -> Plan:
    p = Plan()
    for name in ROOT_FILES:
        if root.exists(f"{OLD}/{name}"):
            p.moves.append((root, f"{OLD}/{name}", root, name))
    for cat in legacy["catalogs"]:
        c = cat["catalog"]
        for path in root.list(f"{c}/{OLD}"):
            new = _new_catalog_path(c, path[len(f"{c}/{OLD}/"):])
            p.moves.append((root, path, root, new))
            p.path_map[path] = new
        for k in cat.get("crawls", []):
            crawl, base = k["crawl"], f"{c}/{k['crawl']}/{OLD}"
            outputs = {o["id"]: o for o in k.get("extract_outputs", [])}
            score_of: dict[str, str] = {}
            for sid in [s["id"] for s in k.get("scores", [])]:
                try:
                    doc = root.read_json(f"{base}/scores/{sid}/score.json")
                except FileNotFoundError:
                    p.keeps.append((f"{base}/scores/{sid}", "the manifest lists this score, but it has no score.json"))
                    continue
                score_of[sid] = score_dir(c, crawl, doc["output"]["id"], doc["golden"]["id"], CLS, sid)
                p.score_dirs[f"{base}/scores/{sid}"] = score_of[sid]
            for path in root.list(base):
                rel = path[len(base) + 1:]
                new = _new_crawl_path(c, crawl, rel)
                if new is not None:
                    p.moves.append((root, path, root, new))
                    p.path_map[path] = new
                    continue
                if xtra is None:
                    raise UserError(f"{c} has scores and extract outputs to move to xtra-cli's container: name it "
                                    "with --xtra-root (or GOLDEN_DATASETS_XTRA_SOURCE)")
                head, sid_or_id, rest = (rel.split("/", 2) + [""])[:3]
                if head == "scores" and sid_or_id in score_of:
                    target = f"{score_of[sid_or_id]}/{rest}"
                elif head == "extract-outputs" and sid_or_id in outputs:
                    target = f"{extract_run_dir(c, crawl, sid_or_id)}/{rest}"
                else:
                    target = f"{extract_run_dir(c, crawl, '_unregistered')}/{rel}"
                p.moves.append((root, path, xtra, target))
                p.xtra_map[path] = target
            # the crawl copy: removed when the same files are in the crawl root
            copy = [layout.crawl_json(c, crawl), layout.pages_dir(c, crawl)]
            candidates = [r for r in (crawls, _open(cat.get("crawls_root")), xtra) if r is not None
                          and r.uri != root.uri]
            found = next((r for r in candidates if _same_files(root, r, layout.crawl_input(c, crawl) + "/pages")
                          and _same_files(root, r, layout.crawl_json(c, crawl))), None)
            has_copy = root.exists(layout.crawl_json(c, crawl))
            if found is not None:
                p.crawls_root[c] = found.uri
                if has_copy:
                    p.removals += [(x, f"the same files are in {found.uri}") for x in copy]
            elif has_copy:
                p.crawls_root[c] = root.uri
                p.keeps += [(x, "not found in any crawl root: the Studio reads it here") for x in copy
                            if root.exists(x) or root.list(x)]
            else:
                p.crawls_root[c] = cat.get("crawls_root") or (crawls or xtra or root).uri
    return p


def _open(uri: str | None) -> Root | None:
    if not uri:
        return None
    try:
        return open_root(uri)
    except Exception:  # noqa: BLE001 - e.g. no access to that container from here
        return None


# --- the new manifest ----------------------------------------------------------------------------------------
def new_manifest(legacy: dict, p: Plan) -> dict:
    def move(path: str | None) -> str | None:
        return relocate(path) if path else None

    out = {"schema": manifest.SCHEMA, "updated_at": manifest.now_iso(), "catalogs": []}
    for cat in legacy["catalogs"]:
        c = cat["catalog"]
        new = {k: v for k, v in cat.items() if k not in ("rule_versions", "rulesets", "annotations", "crawls")}
        new["crawls_root"] = p.crawls_root.get(c) or cat.get("crawls_root")
        new["classes"] = {CLS: {"rule_versions": [move(x) for x in cat.get("rule_versions", [])],
                                "rulesets": [{**r, "path": move(r["path"])} for r in cat.get("rulesets", [])],
                                "annotations": move(cat.get("annotations"))}}
        new["crawls"] = []
        for k in cat.get("crawls", []):
            crawl = k["crawl"]
            nk = {x: v for x, v in k.items() if x not in ("extractions", "golden", "scores", "extract_outputs")}
            nk["pages"] = move(k.get("pages"))
            if k.get("assets"):
                nk["assets"] = {x: (move(v) if isinstance(v, str) and v.startswith(f"{c}/") else v)
                                for x, v in k["assets"].items()}
            nk["extract_outputs"] = [{**o, "copy": extract_run_dir(c, crawl, o["id"]) if o.get("copy") else None}
                                     for o in k.get("extract_outputs", [])]
            old_scores = f"{c}/{crawl}/{OLD}/scores"
            nk["classes"] = {CLS: {
                "extractions": [{**e, "path": move(e["path"])} for e in k.get("extractions", [])],
                "golden": [{**g, "path": move(g["path"])} for g in k.get("golden", [])],
                "scores": [{"id": s["id"], "path": p.score_dirs.get(f"{old_scores}/{s['id']}")}
                           for s in k.get("scores", [])]}}
            new["crawls"].append(nk)
        out["catalogs"].append(new)
    return out


# --- run -------------------------------------------------------------------------------------------------------
def _remove(root: Root, path: str) -> None:
    """Delete a crawl copy; a symlink is unlinked, never followed."""
    if isinstance(root, LocalRoot):
        local = root._p(path)
        if local.is_symlink():
            local.unlink()
            return
        if local.is_dir():
            for f in sorted(local.rglob("*"), reverse=True):
                f.unlink() if not f.is_dir() or f.is_symlink() else f.rmdir()
            local.rmdir()
            return
    for f in root.list(path) or [path]:
        root.delete(f)


def migrate(root: Root, xtra: Root | None, crawls: Root | None, dry_run: bool, log=print) -> dict:
    legacy_path = layout.LEGACY_MANIFEST
    if not root.exists(legacy_path):
        if root.exists(layout.MANIFEST):
            log(f"{root.uri}: already migrated ({layout.MANIFEST}, {manifest.load(root)[0].get('schema')}): "
                "nothing to do")
            return {"moved": 0, "rewritten": 0, "removed": 0, "done": True}
        raise UserError(f"{root.uri}: no manifest to migrate")
    legacy = json.loads(root.read_bytes(legacy_path))
    p = plan(root, xtra, crawls, legacy, log)
    say = (lambda *a: log("would", *a)) if dry_run else log
    rewritten = 0
    for src, path, dst, new in p.moves:
        where = "" if dst is root else f" (xtra-cli's container {dst.uri})"
        if dry_run:
            say(f"move {path} → {new}{where}")
            continue
        data = src.read_bytes(path)
        changed = rewrite(data, new)
        if changed is not None:
            dst.write_bytes(new + LEGACY, data)
            dst.write_bytes(new, changed)
            rewritten += 1
        else:
            dst.write_bytes(new, data)
        src.delete(path)
        say(f"moved {path} → {new}{where}" + (" (course_key → record_external_identifier; original kept as "
                                              f"{new.rsplit('/', 1)[-1]}{LEGACY})" if changed is not None else ""))
    if not dry_run:
        _rehash_rule_runs(root, p, log)
    for path, why in p.removals:
        say(f"remove the crawl copy {path}: {why}")
        if not dry_run:
            _remove(root, path)
    for path, why in p.keeps:
        log(f"keep {path}: {why}")
    doc = new_manifest(legacy, p)
    for c, uri in sorted(p.crawls_root.items()):
        log(f"{c}: crawls {'would be ' if dry_run else ''}read from {uri}")
    if dry_run:
        say(f"write {layout.MANIFEST} ({manifest.SCHEMA}); keep the old one as {legacy_path}{LEGACY}")
        return {"moved": len(p.moves), "removed": len(p.removals), "done": False}
    root.write_json(layout.MANIFEST, doc)
    root.write_bytes(legacy_path + LEGACY, root.read_bytes(legacy_path))
    root.delete(legacy_path)
    _prune(root, [f"{c['catalog']}/{OLD}" for c in legacy["catalogs"]]
           + [f"{c['catalog']}/{k['crawl']}/{OLD}" for c in legacy["catalogs"] for k in c.get("crawls", [])])
    log(f"wrote {layout.MANIFEST} ({manifest.SCHEMA}); the old one is {legacy_path}{LEGACY}")
    return {"moved": len(p.moves), "rewritten": rewritten, "removed": len(p.removals), "done": True}


def _prune(root: Root, folders: list[str]) -> None:
    """The emptied `golden-dataset-studio/` folders of a local root (blob storage has no folders to leave). A folder
    that still holds a file other than a write lock stays."""
    if not isinstance(root, LocalRoot):
        return
    for folder in folders:
        top = root._p(folder)
        if not top.is_dir() or top.is_symlink():
            continue
        for f in top.rglob(".*.lock"):  # LocalRoot's write locks, not data
            if f.is_file():
                f.unlink()
        for d in sorted((x for x in top.rglob("*") if x.is_dir() and not x.is_symlink()), reverse=True):
            if not any(d.iterdir()):
                d.rmdir()
        if not any(top.iterdir()):
            top.rmdir()


def _rehash_rule_runs(root: Root, p: Plan, log) -> None:
    """A rule run's extraction.json names each table's sha256: the rewritten tables get theirs."""
    import hashlib

    metas = {n for n in p.path_map.values() if n.endswith("/extraction.json") and "/rule-runs/" in n}
    for meta_path in sorted(metas):
        meta = root.read_json(meta_path)
        base, changed = meta_path.rsplit("/", 1)[0], False
        for name, info in (meta.get("files") or {}).items():
            if root.exists(f"{base}/{name}{LEGACY}"):
                info["sha256"] = hashlib.sha256(root.read_bytes(f"{base}/{name}")).hexdigest()
                changed = True
        if changed:
            if not root.exists(meta_path + LEGACY):
                root.write_bytes(meta_path + LEGACY, root.read_bytes(meta_path))
            root.write_json(meta_path, meta)


def cmd_migrate(args) -> int:
    root = open_root(args.root)
    xtra_uri = args.xtra_root or xtra_root(root)
    xtra = open_root(xtra_uri) if xtra_uri else None
    crawls = open_root(args.crawls_root) if args.crawls_root else None
    if isinstance(xtra, LocalRoot):
        from pathlib import Path

        Path(xtra.base).mkdir(parents=True, exist_ok=True)
    out = migrate(root, xtra, crawls, args.dry_run, log=lambda *a: print(*a, file=sys.stdout))
    print(", ".join(f"{k} {v}" for k, v in out.items()))
    return 0
