"""Evals (docs/qrspi/evals): score an xtra-cli extraction against a version of the golden dataset.

The Studio runs xtra-cli; it doesn't reimplement it. Every run and every eval is written under the Studio's own
folder, so the team's shared `records/` and match reports are never touched, and each one stays as a version:

    <crawl>/golden-dataset-studio/xtra-runs/x-0001/run.json
                                              out/<catalog>/<crawl>/{records/*.json, extract-report.json}
    <crawl>/golden-dataset-studio/evals/ev-0001/eval.json
                                          baseline/{hand,full}/<catalog>/<crawl>/<stem>/<stem>.json
                                          reports/{hand,full}-{exact,partial}.json
                                          fields.parquet

An xtra run is either `extract` (xtra-cli at a pinned commit, `--source-uri` the shared crawl, `--target-uri` the
run's `out/`) or `import` (a copy of the team's current `records/`).

An eval scores one run against one golden version, twice: the **hand** baseline keeps only the values a person
confirmed (`approval: human`), the **full** baseline keeps every value. Each is scored with `xtra score extraction
match --exactly` and `--partially`, so the counts are the scorer's own. The scorer's reports list every field that
isn't exact, so `fields.parquet` (one row per baseline field) is rebuilt from the baseline plus those outliers, and
its counts are checked against the reports'.

A golden version is `published` (the files in the golden container now), `verified` (xtra-golden-sets-verified,
every value counted as hand-checked) or an extraction `rs-NNNN` (`golden.plan`, unpublished: shown as unapproved).
Fields with no CTDL term (Learning Type) are left out: the scorer would reject the whole page file.
"""

from __future__ import annotations

import io
import json
import os
import re
import shlex
import subprocess
import tarfile
from collections import Counter, defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import manifest, model
from .context import Ctx
from .errors import UserError
from .storage import AzureRoot, Root, cache_home, open_root

DEFAULT_XTRA_REF = "origin/main"  # the scorer is on main since #314
SHARED_XTRA_ROOT = "azure://https://ceteststorage.blob.core.windows.net/xtra-cli-output"
VERIFIED_ROOT = "azure://https://ceteststorage.blob.core.windows.net/xtra-golden-sets-verified"
KINDS = ("hand", "full")


def kinds_for(golden: str) -> tuple[str, ...]:
    """The verified container is all hand-checked: it is one baseline, not a hand and a full one."""
    return ("hand",) if golden == "verified" else KINDS
MODES = ("exact", "partial")
Log = Callable[[str], None]


# --- paths --------------------------------------------------------------------------------------------
def studio_dir(ctx: Ctx) -> str:
    return f"{ctx.catalog}/{ctx.crawl}/golden-dataset-studio"


def run_dir(ctx: Ctx, run_id: str) -> str:
    return f"{studio_dir(ctx)}/xtra-runs/{run_id}"


def eval_dir(ctx: Ctx, eval_id: str) -> str:
    return f"{studio_dir(ctx)}/evals/{eval_id}"


def uri_of(root: Root, path: str) -> str:
    return f"{root.uri.rstrip('/')}/{path}"


def xtra_source(root: Root) -> str:
    """Where xtra-cli reads the crawl (pages + discovery): $GOLDEN_DATASETS_XTRA_SOURCE, else the shared container."""
    src = os.environ.get("GOLDEN_DATASETS_XTRA_SOURCE")
    if src:
        return src
    if isinstance(root, AzureRoot):
        return SHARED_XTRA_ROOT
    raise UserError("set GOLDEN_DATASETS_XTRA_SOURCE to the xtra-cli output root that holds the crawl's pages and "
                    "discovery runs (a folder, or azure://…/xtra-cli-output)")


def _next_id(items: list[dict], prefix: str) -> str:
    n = max((int(i["id"].split("-")[1]) for i in items), default=0)
    return f"{prefix}-{n + 1:04d}"


def runs(ctx: Ctx) -> list[dict]:
    return list(ctx.crawl_entry().get("xtra_runs", []))


def evals(ctx: Ctx) -> list[dict]:
    return list(ctx.crawl_entry().get("evals", []))


def _register(ctx: Ctx, key: str, item: dict) -> None:
    def change(m: dict) -> None:
        k = manifest.crawl_entry(manifest.catalog_entry(m, ctx.catalog), ctx.crawl)
        manifest.add_unique(k.setdefault(key, []), item, key=lambda i: i["id"])

    manifest.update(ctx.root, change)
    ctx.invalidate()


# --- running xtra-cli --------------------------------------------------------------------------------
def _repo() -> Path:
    here = Path(__file__).resolve().parent
    out = subprocess.run(["git", "-C", str(here), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if out.returncode:
        raise UserError("xtra runs need the Studio to run from a git checkout of ctdl-xtra")
    return Path(out.stdout.strip())


def resolve_ref(ref: str) -> str:
    """The commit a branch, tag or sha names (fetched from origin first when it isn't known locally)."""
    if not re.fullmatch(r"[\w./-]{1,200}", ref):
        raise UserError(f"{ref!r}: not a git ref")
    repo = _repo()

    def rev(r: str) -> str | None:
        out = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"{r}^{{commit}}"],
                             capture_output=True, text=True)
        return out.stdout.strip() or None

    sha = rev(ref) or rev(f"origin/{ref}")
    if not sha:
        subprocess.run(["git", "-C", str(repo), "fetch", "--quiet", "origin", ref.removeprefix("origin/")],
                       capture_output=True)
        sha = rev(ref) or rev(f"origin/{ref}") or rev("FETCH_HEAD")
    if not sha:
        raise UserError(f"{ref}: no such branch, tag or commit")
    return sha


def xtra_bin(sha: str, log: Log) -> Path:
    """xtra-cli at this commit, installed once into the cache (editable, as its Dockerfile does, so lib/ resolves)."""
    base = cache_home() / "xtra-cli" / sha
    exe = base / "xtra-cli" / ".venv" / "bin" / "xtra"
    if exe.exists():
        return exe
    log(f"installing xtra-cli {sha[:7]} into {base}")
    archive = subprocess.run(["git", "-C", str(_repo()), "archive", sha, "xtra-cli"], capture_output=True, check=True)
    base.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(base, filter="data")
    proj = base / "xtra-cli"
    subprocess.run(["uv", "venv", "-q", "--clear", "-p", "3.12", str(proj / ".venv")], check=True, cwd=proj)
    subprocess.run(["uv", "pip", "install", "-q", "-p", str(proj / ".venv" / "bin" / "python"), "-e", ".[azure]"],
                   check=True, cwd=proj)
    return exe


def _conn_env(*uris: str) -> dict[str, str]:
    """The environment for xtra-cli: the connection string goes in AZURE_STORAGE_CONNECTION_STRING, never in argv."""
    env = dict(os.environ)
    if not env.get("AZURE_STORAGE_CONNECTION_STRING"):
        from .storage import _az_connection_string

        for u in uris:
            m = re.match(r"azure://https://([^.]+)\.blob\.core\.windows\.net/", u)
            if m:
                env["AZURE_STORAGE_CONNECTION_STRING"] = _az_connection_string(m.group(1))
                break
    return env


_SECRET = re.compile(r"(AccountKey|SharedAccessSignature|sig)=[^;&\s]+")


def mask(line: str) -> str:
    return _SECRET.sub(r"\1=***", line)


def shown(argv: list[str], exe: Path | None = None) -> str:
    """The command as someone would run it by hand: `xtra …` with one option per line (the connection string is left to
    AZURE_STORAGE_CONNECTION_STRING)."""
    words, groups = [], []
    for a in argv:
        if a.startswith("--"):
            groups.append([a])
        elif groups:
            groups[-1].append(shlex.quote(a))
        else:
            words.append(a)
    return " \\\n  ".join([" ".join(["xtra", *words]), *(" ".join(g) for g in groups)])


def run_xtra(exe: Path, argv: list[str], log: Log, env: dict[str, str], proc_hook=None) -> str:
    """Run xtra-cli, stream stderr to the log, return stdout. Raises UserError when it fails."""
    log("$ " + " ".join(["xtra", *map(shlex.quote, argv)]))
    p = subprocess.Popen([str(exe), *argv], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
                         cwd=exe.parent.parent.parent)
    if proc_hook:
        proc_hook(p)
    out: list[str] = []
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(lambda: out.append(p.stdout.read()))
        for line in p.stderr:
            log(mask(line.rstrip()))
        fut.result()
    if p.wait():
        raise UserError(f"xtra exited with {p.returncode}")
    return "".join(out)


# --- xtra runs ---------------------------------------------------------------------------------------
def extract_run(ctx: Ctx, ref: str = DEFAULT_XTRA_REF, sample: bool = False, discovery_run: str | None = None,
                by: str = "", log: Log = print, proc_hook=None) -> dict:
    sha = resolve_ref(ref)
    exe = xtra_bin(sha, log)
    rid = _next_id(runs(ctx), "x")
    source, target = xtra_source(ctx.root), uri_of(ctx.root, f"{run_dir(ctx, rid)}/out")
    argv = ["catalog", "extract", "--with-template", "--source-uri", source, "--target-uri", target,
            "--catalog-id", ctx.catalog, "--run-id", ctx.crawl]
    if sample:
        argv.append("--only-golden-sample")
    if discovery_run:
        argv += ["--discovery-run-id", discovery_run]
    started = manifest.now_iso()
    run_xtra(exe, argv, log, _conn_env(source, target), proc_hook)
    report = ctx.root.read_json(f"{run_dir(ctx, rid)}/out/{ctx.catalog}/{ctx.crawl}/extract-report.json")
    doc = {"id": rid, "kind": "extract", "ref": ref, "commit": sha, "scope": "sample" if sample else "all",
           "source": source, "discovery_run_id": report.get("discovery_run_id", discovery_run),
           "records_written": report.get("records_written"), "pages_considered": report.get("pages_considered"),
           "skipped_by_reason": report.get("skipped_by_reason"), "started_at": started,
           "finished_at": manifest.now_iso(), "by": by, "commands": [shown(argv, exe)]}
    ctx.root.write_json(f"{run_dir(ctx, rid)}/run.json", doc, if_none_match=True)
    _register(ctx, "xtra_runs", {"id": rid, "path": run_dir(ctx, rid)})
    log(f"{rid}: {doc['records_written']} records")
    return doc


def import_run(ctx: Ctx, source: str | None = None, by: str = "", log: Log = print) -> dict:
    """A copy of the team's current records/ (and extract-report.json) as a run; reused when nothing changed."""
    source = source or xtra_source(ctx.root)
    src = open_root(source)
    prefix = f"{ctx.catalog}/{ctx.crawl}"
    sizes = src.sizes(f"{prefix}/records")
    if not sizes:
        raise UserError(f"{source}/{prefix}/records: no records")
    fingerprint = _fingerprint(sizes, src, f"{prefix}/extract-report.json")
    for r in runs(ctx):
        doc = ctx.read_json(f"{r['path']}/run.json")
        if doc.get("kind") == "import" and doc.get("fingerprint") == fingerprint:
            log(f"records/ unchanged since {r['id']}: reusing it")
            return doc
    rid = _next_id(runs(ctx), "x")
    out = f"{run_dir(ctx, rid)}/out/{prefix}"
    paths = [*sizes, f"{prefix}/extract-report.json"]
    log(f"{rid}: copying {len(paths):,} files from {source}")

    def copy(p: str) -> None:
        ctx.root.write_bytes(f"{out}/{p[len(prefix) + 1:]}", src.read_bytes(p))

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(copy, paths))
    report = src.read_json(f"{prefix}/extract-report.json")
    doc = {"id": rid, "kind": "import", "source": source, "fingerprint": fingerprint,
           "discovery_run_id": report.get("discovery_run_id"), "records_written": len(sizes),
           "pages_considered": report.get("pages_considered"), "skipped_by_reason": report.get("skipped_by_reason"),
           "scope": "sample" if report.get("only_golden_sample") else "all",
           "started_at": manifest.now_iso(), "finished_at": manifest.now_iso(), "by": by, "commands": []}
    ctx.root.write_json(f"{run_dir(ctx, rid)}/run.json", doc, if_none_match=True)
    _register(ctx, "xtra_runs", {"id": rid, "path": run_dir(ctx, rid)})
    return doc


def _fingerprint(sizes: dict[str, int], src: Root, report: str) -> str:
    import hashlib

    h = hashlib.sha256()
    for p, s in sorted(sizes.items()):
        h.update(f"{p}\t{s}\n".encode())
    h.update(src.read_bytes(report))
    return h.hexdigest()[:16]


# --- golden versions ---------------------------------------------------------------------------------
def golden_options(ctx: Ctx) -> list[dict]:
    """What an eval can score against, newest first."""
    out = []
    pubs = ctx.crawl_entry().get("golden", [])
    if pubs:
        last = pubs[-1]
        out.append({"id": "published", "label": f"Published ({last['publication']})", "approved": True,
                    "to": last.get("to")})
    out.append({"id": "verified", "label": "Verified container (hand-checked pages)", "approved": True})
    for e in sorted(ctx.extractions(), key=lambda e: e["extraction"], reverse=True):
        out.append({"id": e["extraction"], "label": f"Extraction {e['extraction']} (ruleset v{e['ruleset_version']}, "
                                                    f"unpublished)", "approved": False})
    return out


def load_golden(ctx: Ctx, golden: str, log: Log = print) -> tuple[dict[str, list[dict]], dict]:
    """{page_stem: [record {golden_record_id, approval, fields: [...]}]} and a description of where it came from."""
    if golden == "published":
        pubs = ctx.crawl_entry().get("golden", [])
        if not pubs:
            raise UserError(f"{ctx.catalog}: nothing published yet")
        last = pubs[-1]
        target = open_root(last["to"])
        stems = set()
        for g in pubs:
            if g.get("to", "").rstrip("/") == target.uri.rstrip("/"):
                stems |= set(ctx.read_json(f"{g['path']}/publication.json").get("page_stems", []))
        pages = _read_pages(target, f"{ctx.catalog}/{ctx.crawl}", sorted(stems), log)
        return pages, {"golden": golden, "publication": last["publication"], "from": last["to"], "approved": True}
    if golden == "verified":
        target = open_root(os.environ.get("GOLDEN_DATASETS_VERIFIED_ROOT", VERIFIED_ROOT))
        prefix = f"{ctx.catalog}/{ctx.crawl}"
        stems = sorted({p.split("/")[-2] for p in target.list(prefix) if p.endswith(".json")})
        pages = _read_pages(target, prefix, stems, log)
        for recs in pages.values():  # every value in the verified container was checked by a person
            for r in recs if isinstance(recs, list) else []:
                for f in r.get("fields", []):
                    f.setdefault("approval", "human")
        return pages, {"golden": golden, "from": target.uri, "approved": True}
    if re.fullmatch(r"rs-\d{4}", golden):
        from . import golden as golden_mod
        from .review import LOADER

        rv = LOADER.review(ctx, golden)
        p = golden_mod.plan(rv)
        return dict(p["pages"]), {"golden": golden, "extraction": golden, "approved": False}
    raise UserError(f"{golden}: not a golden version (published, verified or rs-NNNN)")


def _read_pages(root: Root, prefix: str, stems: list[str], log: Log) -> dict[str, list[dict]]:
    log(f"reading {len(stems):,} golden pages from {root.uri}/{prefix}")

    def one(stem: str):
        try:
            doc = root.read_json(f"{prefix}/{stem}/{stem}.json")
        except FileNotFoundError:
            return stem, None
        return stem, [doc] if isinstance(doc, dict) else doc

    with ThreadPoolExecutor(max_workers=16) as pool:
        return {s: d for s, d in pool.map(one, stems) if d}


def baseline(pages: dict[str, list[dict]], kind: str) -> tuple[dict[str, list[dict]], list[dict]]:
    """The pages as xtra's scorer reads them, for `hand` or `full`, and the pages left out (with why).

    Fields without a CTDL term are dropped (the scorer rejects a page that has one). The scorer pairs a page's
    entities with its records by position and rejects an empty entity, so trailing empty entities are dropped and a
    page with an empty entity before a non-empty one is left out.
    """
    out, left_out = {}, []
    for stem, records in pages.items():
        ents = []
        for r in records:
            fields = [{"ctdl_property": f["ctdl_property"], "value": f["value"], "source_url": f.get("source_url"),
                       "property": f.get("property"), "approval": f.get("approval", "rule"),
                       "approved_by": f.get("approved_by"), "approved_at": f.get("approved_at"),
                       **({"location": f["location"]} if "location" in f else {})}
                      for f in r.get("fields", [])
                      if f.get("ctdl_property") and (kind == "full" or f.get("approval") == "human")]
            ents.append({"golden_record_id": r.get("golden_record_id") or r.get("golden_id"),
                         "approval": r.get("approval"), "fields": fields})
        while ents and not ents[-1]["fields"]:
            ents.pop()
        if not ents:
            continue
        if any(not e["fields"] for e in ents):
            left_out.append({"stem": stem, "why": "an earlier course on the page has no values in this baseline"})
            continue
        out[stem] = ents
    return out, left_out


def is_implied(field: dict) -> bool:
    """xtra's scorer skips a value the golden data says isn't on the page (`location: null`, since xtra-cli #343)."""
    return "location" in field and field["location"] is None


def baseline_stats(pages: dict[str, list[dict]], kind: str) -> dict:
    """What a baseline holds: records, the fields xtra's scorer scores, per property, and what it doesn't score."""
    base, left_out = baseline(pages, kind)
    by: Counter = Counter()
    unscored: dict[tuple[str, str], int] = Counter()
    for ents in base.values():
        for e in ents:
            for f in e["fields"]:
                label = f.get("property") or _label(f["ctdl_property"])
                if is_implied(f):
                    unscored[(label, "implied: not read from the page")] += 1
                else:
                    by[label] += 1
    for recs in pages.values():
        for r in recs:
            for f in r.get("fields", []):
                if not f.get("ctdl_property") and (kind == "full" or f.get("approval") == "human"):
                    unscored[(f.get("property") or "?", "no CTDL term")] += 1
    order = model.PROPERTY_ORDER
    return {"records": sum(len(e) for e in base.values()), "pages": len(base), "fields": sum(by.values()),
            "properties": [{"property": p, "fields": n, "ctdl_property": model.CTDL_TERM.get(p)}
                           for p, n in sorted(by.items(), key=lambda kv: (order.get(kv[0], 99), kv[0]))],
            "not_scored": [{"property": p, "fields": n, "why": why} for (p, why), n in
                           sorted(unscored.items(), key=lambda kv: (order.get(kv[0][0], 99), kv[0][0]))],
            "left_out": left_out}


def extract_options(ctx: Ctx) -> dict:
    """What a new extraction can do: the discovery run, its review sample and population, and the records/ xtra-cli
    last wrote for the crawl."""
    try:
        src = open_root(xtra_source(ctx.root))
    except UserError as e:
        return {"error": str(e)}
    prefix = f"{ctx.catalog}/{ctx.crawl}"
    out: dict = {"source": src.uri}
    runs_ = sorted(src.list_dirs(f"{prefix}/discovery"))
    if runs_:
        out["discovery_run_id"] = runs_[-1]
        try:
            sample = src.read_json(f"{prefix}/discovery/{runs_[-1]}/golden-sample-course.json")
            out["sample_pages"], out["course_pages"] = len(sample.get("pages") or []), sample.get("population_size")
        except FileNotFoundError:
            pass
    try:
        rep_ = src.read_json(f"{prefix}/extract-report.json")
        out["latest"] = {"records": rep_.get("records_written"), "pages_considered": rep_.get("pages_considered"),
                         "discovery_run_id": rep_.get("discovery_run_id"),
                         "scope": "sample" if rep_.get("only_golden_sample") else "all"}
    except FileNotFoundError:
        pass
    return out


# --- evals -------------------------------------------------------------------------------------------
def run_eval(ctx: Ctx, xtra_run: str, golden: str, ref: str = DEFAULT_XTRA_REF, by: str = "", log: Log = print,
             proc_hook=None) -> dict:
    if xtra_run not in {r["id"] for r in runs(ctx)}:
        raise UserError(f"{xtra_run}: no such xtra run")
    run = ctx.read_json(f"{run_dir(ctx, xtra_run)}/run.json")
    sha = run.get("commit") or resolve_ref(ref)
    exe = xtra_bin(sha, log)
    pages, golden_meta = load_golden(ctx, golden, log)
    eid = _next_id(evals(ctx), "ev")
    edir = eval_dir(ctx, eid)
    source = uri_of(ctx.root, f"{run_dir(ctx, xtra_run)}/out")
    prefix = f"{ctx.catalog}/{ctx.crawl}"
    env = _conn_env(source)
    rows: list[dict] = []
    summary: dict[str, dict] = {}
    commands: list[str] = []
    records = _run_records(ctx, xtra_run)
    for kind in kinds_for(golden):
        base, left_out = baseline(pages, kind)
        summary[kind] = {"pages": len(base), "left_out": left_out}
        if not base:
            log(f"{kind}: no values in this golden version; not scored")
            continue
        broot = f"{edir}/baseline/{kind}"

        def write(item, broot=broot) -> None:
            stem, ents = item
            ctx.root.write_text(f"{broot}/{prefix}/{stem}/{stem}.json", json.dumps(ents, ensure_ascii=False, indent=1))

        with ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(write, base.items()))
        reports = {}
        for mode in MODES:
            argv = ["score", "extraction", "match", f"--{'exactly' if mode == 'exact' else 'partially'}",
                    "--source-uri", source, "--baseline-uri", uri_of(ctx.root, broot),
                    "--catalog-id", ctx.catalog, "--run-id", ctx.crawl]
            run_xtra(exe, argv, log, env, proc_hook)
            commands.append(shown(argv, exe))
            # the scorer writes its report beside the run's records: copy it before the next call replaces it
            rep = ctx.root.read_json(f"{run_dir(ctx, xtra_run)}/out/{prefix}/extraction-match-{mode}-report.json")
            ctx.root.write_json(f"{edir}/reports/{kind}-{mode}.json", rep)
            reports[mode] = rep
        kind_rows = fields_rows(eid, kind, base, reports, records)
        rows += kind_rows
        summary[kind] |= {"fields_total": reports["exact"]["fields_total"],
                          "exact_match_rate": reports["exact"]["exact_match_rate"],
                          "outcomes": dict(Counter(r["outcome"] for r in kind_rows)),
                          "pages_scored": reports["exact"]["pages_scored"],
                          "pages_skipped": reports["exact"]["pages_skipped"],
                          "pages_out_of_scope": reports["exact"]["pages_out_of_scope"]}
    info = ctx.write_table(f"{edir}/fields.parquet", rows, model.EVAL_FIELDS)
    doc = {"id": eid, "xtra_run": xtra_run, "xtra_commit": run.get("commit"), "scorer_commit": sha,
           "golden": golden_meta, "summary": summary, "fields": info, "created_at": manifest.now_iso(), "by": by,
           "commands": commands}
    ctx.root.write_json(f"{edir}/eval.json", doc, if_none_match=True)
    _register(ctx, "evals", {"id": eid, "path": edir, "xtra_run": xtra_run, "golden": golden})
    log(f"{eid}: " + " · ".join(f"{k} {s.get('exact_match_rate')} of {s.get('fields_total')}"
                                for k, s in summary.items() if "fields_total" in s))
    return doc


def _run_records(ctx: Ctx, run_id: str) -> dict[str, list[dict]]:
    """{page stem: [record]} of a run, the page's own record first, as the scorer pairs them."""
    prefix = f"{run_dir(ctx, run_id)}/out/{ctx.catalog}/{ctx.crawl}/records"
    names = sorted(p.rsplit("/", 1)[-1] for p in ctx.root.list(prefix) if p.endswith(".json"))
    by_stem: dict[str, list[str]] = defaultdict(list)
    for n in names:
        by_stem[n[:-5].split("--", 1)[0]].append(n)

    def one(item):
        stem, ns = item
        ns = sorted(ns, key=lambda n: (n != f"{stem}.json", n))
        return stem, [ctx.root.read_json(f"{prefix}/{n}") for n in ns]

    with ThreadPoolExecutor(max_workers=16) as pool:
        return dict(pool.map(one, by_stem.items()))


def _text(v) -> str | None:
    if v is None:
        return None
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def _label(ctdl: str) -> str:
    return {t: label for label, t in model.PROPERTIES if t}.get(ctdl) or ctdl.split(":")[-1]


def fields_rows(eid: str, kind: str, base: dict[str, list[dict]], reports: dict[str, dict],
                records: dict[str, list[dict]]) -> list[dict]:
    """One row per baseline field: the golden value, xtra's value and the outcome, from the two match reports.

    Every field that isn't an exact match is in the exact report's outliers; its partial-mode outcome and similarity
    are in the partial report's. Anything else is an exact match. The counts are checked against the reports.
    """
    exact, partial = reports["exact"], reports["partial"]

    def index(rep: dict) -> dict[tuple, list[dict]]:
        out: dict[tuple, list[dict]] = defaultdict(list)
        for o in rep["outliers"]:
            out[(o["stem"], o["entity"], o["ctdl_property"], _text(o["baseline_value"]))].append(o)
        return out

    ex, pa_ = index(exact), index(partial)
    status = {p["stem"]: p["status"] for p in exact["pages"]}
    status |= {s: "out of scope" for s in exact["out_of_scope"]} | {m["stem"]: "malformed" for m in exact["malformed"]}
    rows = []
    for stem, ents in sorted(base.items()):
        recs = records.get(stem, [])
        for ei, ent in enumerate(ents):
            rec = recs[ei] if ei < len(recs) else None
            seen: Counter = Counter()
            for f in ent["fields"]:
                key = (stem, ei, f["ctdl_property"], _text(f["value"]))
                vi = seen[f["ctdl_property"]]
                seen[f["ctdl_property"]] += 1
                st = status.get(stem, "out of scope")
                o = ex[key].pop(0) if ex.get(key) else None
                if is_implied(f):
                    outcome, sim, got = "implied", None, None
                elif st in ("out of scope", "malformed"):
                    outcome, sim, got = st, None, None
                elif o is None:
                    outcome, sim, got = "exact", 1.0, _text(f["value"])
                elif o["outcome"] == "missing":
                    outcome, sim, got = "missing", None, None
                else:
                    p = pa_[key].pop(0) if pa_.get(key) else {}
                    outcome, sim, got = p.get("outcome", "wrong"), p.get("similarity", o["similarity"]), \
                        _text(o["extracted_value"])
                rows.append({
                    "eval": eid, "golden": kind, "page_stem": stem, "entity": ei,
                    "golden_record_id": ent.get("golden_record_id"), "record_approval": ent.get("approval"),
                    "courses_on_page": len(ents), "property": f.get("property") or _label(f["ctdl_property"]),
                    "ctdl_property": f["ctdl_property"], "value_index": vi, "golden_value": _text(f["value"]),
                    "xtra_value": got, "outcome": outcome, "similarity": sim, "page_status": st,
                    "approval": f.get("approval"), "approved_by": f.get("approved_by"),
                    "approved_at": f.get("approved_at"), "template_id": (rec or {}).get("template_id"),
                    "source_url": f.get("source_url"),
                    "golden_css_path": (f.get("location") or {}).get("css_path"),
                    "golden_char_start": (f.get("location") or {}).get("char_start"),
                    "golden_char_end": (f.get("location") or {}).get("char_end"),
                })
    counted = [r for r in rows if r["outcome"] not in ("out of scope", "malformed", "implied")]
    got = Counter("match" if r["outcome"] == "exact" else "missing" if r["outcome"] == "missing" else "mismatch"
                  for r in counted)
    if len(counted) != exact["fields_total"] or any(got[k] != v for k, v in exact["outcomes"].items()):
        raise UserError(f"{kind}: rebuilt counts {dict(got)} of {len(counted)} don't match the scorer's "
                        f"{exact['outcomes']} of {exact['fields_total']}")
    return rows


# --- CLI ---------------------------------------------------------------------------------------------
def cmd_xtra_run(args) -> int:
    ctx = Ctx.from_args(args)
    if args.import_records:
        doc = import_run(ctx, args.source, by=args.by)
    else:
        doc = extract_run(ctx, args.ref, sample=args.sample, discovery_run=args.discovery_run, by=args.by)
    if args.then_eval:
        run_eval(ctx, doc["id"], args.then_eval, by=args.by)
    return 0


def cmd_eval_run(args) -> int:
    ctx = Ctx.from_args(args)
    run_eval(ctx, args.xtra_run, args.golden, by=args.by)
    return 0


def cmd_eval_show(args) -> int:
    ctx = Ctx.from_args(args)
    items = evals(ctx)
    eid = args.eval or (items[-1]["id"] if items else None)
    if not eid:
        raise UserError(f"{ctx.catalog}: no evals yet; run `golden-datasets eval run`")
    doc = ctx.read_json(f"{eval_dir(ctx, eid)}/eval.json")
    print(f"{eid}: {doc['xtra_run']} vs {doc['golden']['golden']}")
    for kind, s in doc["summary"].items():
        if not s.get("fields_total"):
            print(f"  {kind:<5} no values in scope" + ("" if "fields_total" in s else " (nothing to score)"))
            continue
        print(f"  {kind:<5} exact match rate {s['exact_match_rate']} of {s['fields_total']} fields · "
              + " · ".join(f"{k} {v}" for k, v in sorted(s["outcomes"].items())))
    return 0
