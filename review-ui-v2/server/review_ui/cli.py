"""review-ui-v2 command line: sample | extract | check-rules | rules | template | serve | export-feedback."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import engine
from .cache import (
    CACHE_SWITCH_ENV,
    CachedStore,
    DiskCache,
    cache_max_bytes,
    cache_root,
    warm,
)
from .extract import review_sessions, run_extraction
from .rules import validate_ruleset
from .rulesets import (
    RULESETS_PREFIX,
    PublishError,
    find_ruleset,
    publish_ruleset,
    read_rulesets,
    ruleset_key,
)
from .runs import CrawlRun, find_runs, list_pages
from .sample import pick_sample
from .store import Store, open_store
from .template import TEMPLATE_KEY, ConfigMissing, build_properties, load_template

PROJECT = Path(__file__).resolve().parents[2]  # .../review-ui
DEFAULT_ROOT = PROJECT.parent / "crawls"
PROPERTIES = (
    PROJECT / "templates" / "course.properties.json"
)  # authoring copy; publish it


def _spec(spec: str | None) -> str | Path | None:
    """A storage root given as text: an ``azure://`` URI stays text, a folder becomes a Path."""
    if not spec:
        return None
    return spec if spec.startswith("azure://") else Path(spec).resolve()


def _root(args) -> str | Path:
    """The storage root: a folder, or an ``azure://`` URI (never passed through Path,
    which would mangle the ``//``)."""
    spec = args.root or os.environ.get("REVIEW_UI_ROOT")
    if spec and spec.startswith("azure://"):
        return spec
    return Path(spec or DEFAULT_ROOT).resolve()


def _azure_message(exc: Exception, args) -> str | None:
    try:
        from .azure_store import explain_azure_error
    except (
        ImportError
    ):  # the azure extra is not installed, so this cannot be an Azure error
        return None
    root = str(_root(args)) if hasattr(args, "root") else ""
    return explain_azure_error(exc, root)


def resolve_run(root: Store | Path | str, wanted: str | None) -> CrawlRun:
    runs = find_runs(root)
    if wanted:
        runs = [r for r in runs if wanted in r.key]
    if len(runs) != 1:
        listing = "\n".join(f"  {r.key}" for r in find_runs(root)) or "  (none)"
        sys.exit(
            f"--run must match exactly one crawl run under {root} "
            f"(matched {len(runs)}). Runs found:\n{listing}"
        )
    return runs[0]


def _known_properties(store: Store) -> set[str]:
    try:
        return {p.name for p in load_template(store)}
    except ConfigMissing as exc:
        sys.exit(str(exc))


def _load_ruleset_file(path: str, known: set[str]) -> dict:
    try:
        ruleset = json.loads(Path(path).read_text("utf-8"))
        validate_ruleset(ruleset, known)
    except (OSError, ValueError) as exc:  # unreadable, not JSON, or RulesetError
        sys.exit(str(exc))
    return ruleset


def _rules_for(store: Store, run: CrawlRun, rules_file: str | None):
    """The ruleset to use for a run: the given draft file, else the one published in the
    storage root for the run's catalog. Returns (ruleset, template properties)."""
    properties = load_template_or_exit(store)
    known = {p.name for p in properties}
    if rules_file:
        return _load_ruleset_file(rules_file, known), properties
    published = find_ruleset(store, run.catalog_folder, known)
    if published is None:
        sys.exit(
            f"No ruleset for catalog {run.catalog_folder!r} in "
            f"{store.location(RULESETS_PREFIX)}. Publish one with `review-ui-v2 rules publish "
            "<file>`, or try a draft with --rules <file>."
        )
    if published.ruleset is None:
        sys.exit(published.error)
    return published.ruleset, properties


def load_template_or_exit(store: Store):
    try:
        return load_template(store)
    except ConfigMissing as exc:
        sys.exit(str(exc))


def cmd_build_properties(args) -> int:
    props = build_properties(args.csv)
    Path(args.out).write_text(json.dumps(props, indent=1) + "\n")
    print(f"wrote {len(props)} properties to {args.out}")
    return 0


def cmd_check_rules(args) -> int:
    store = open_store(_root(args))
    ruleset = _load_ruleset_file(args.rules, _known_properties(store))
    failures = engine.check_examples(ruleset)
    for failure in failures:
        print("FAIL", failure)
    print(
        f"{len(ruleset['field_rules'])} field rules, "
        f"{len(ruleset['label_rules'])} label rules, {len(failures)} example failures"
    )
    return 1 if failures else 0


def cmd_rules_list(args) -> int:
    store = open_store(_root(args))
    known = _known_properties(store)
    published = read_rulesets(store, known)
    for entry in published:
        if entry.ruleset:
            print(f"{entry.catalog_folder}  v{entry.ruleset['version']}  {entry.key}")
        else:
            print(f"{entry.catalog_folder}  INVALID  {entry.key}\n  {entry.error}")
    if not published:
        print(f"(no rulesets in {store.location(RULESETS_PREFIX)})")
    return 0


def cmd_rules_publish(args) -> int:
    store = open_store(_root(args))
    ruleset = _load_ruleset_file(args.file, _known_properties(store))
    failures = engine.check_examples(ruleset)
    if failures:
        sys.exit("Rule examples fail:\n  " + "\n  ".join(failures))
    try:
        key = publish_ruleset(
            store, ruleset, _known_properties(store), force=args.force
        )
    except PublishError as exc:
        sys.exit(str(exc))
    print(
        f"published {ruleset['ruleset_id']} v{ruleset['version']} to {store.location(key)}"
    )
    return 0


def cmd_rules_pull(args) -> int:
    store = open_store(_root(args))
    key = ruleset_key(args.catalog)
    try:
        text = store.read_text(key)
    except FileNotFoundError:
        sys.exit(f"No ruleset at {store.location(key)}")
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text, end="")
    return 0


def _mb(size: int) -> str:
    return f"{size / 1024**2:,.1f} MB"


def _page_cache(store: Store, message: str) -> CachedStore | None:
    if isinstance(store, CachedStore):
        return store
    print(message)
    return None


NO_CACHE_MESSAGE = (
    "No page cache is in use: the root is a local folder, or caching is switched off "
    f"({CACHE_SWITCH_ENV}=0 / --no-cache)."
)


def cmd_cache_status(args) -> int:
    store = _page_cache(open_store(_root(args)), NO_CACHE_MESSAGE)
    if store is None:
        return 0
    cache = store.cache
    here, total = cache.stats(), cache.stats(namespace_only=False)
    print(f"cache folder : {cache.root}")
    print(f"this root    : {cache.namespace}")
    print(f"               {here.files} files, {_mb(here.bytes)}")
    print(
        f"whole cache  : {total.files} files, {_mb(total.bytes)} "
        f"(limit {_mb(cache.max_bytes)})"
    )
    return 0


def cmd_cache_clear(args) -> int:
    if args.all:
        removed = DiskCache(cache_root(), "", cache_max_bytes()).clear()
        print(f"cleared the whole page cache in {cache_root()} ({removed} files)")
        return 0
    store = _page_cache(open_store(_root(args)), NO_CACHE_MESSAGE)
    if store is None:
        return 0
    prefix = resolve_run(store, args.run).key if args.run else ""
    removed = store.cache.clear(prefix)
    print(f"cleared {removed} files for {prefix or store.cache.namespace}")
    return 0


def cmd_cache_warm(args) -> int:
    store = _page_cache(open_store(_root(args)), NO_CACHE_MESSAGE)
    if store is None:
        return 0
    if not args.run:
        sys.exit("cache warm needs --run")
    run = resolve_run(store, args.run)
    started = {"last": -1}

    def progress(done: int, total: int) -> None:
        step = max(1, total // 20)  # about twenty updates
        if done // step != started["last"] or done == total:
            started["last"] = done // step
            print(f"  {done}/{total} files", flush=True)

    result = warm(store, run.key, threads=args.threads, progress=progress)
    print(
        f"{run.key}: downloaded {result.fetched}, already cached {result.already_cached}"
        + (f", {result.failed} missing" if result.failed else "")
    )
    return 0


def cmd_template_publish(args) -> int:
    store = open_store(_root(args))
    try:
        raw = json.loads(Path(args.file).read_text("utf-8"))
        names = [item["name"] for item in raw]
        for item in raw:  # the shape load_template needs
            item["term"], item["section"], item["required"], item["multiple"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sys.exit(
            f"{args.file} is not a field template ({exc!r}); build one with build-properties."
        )
    store.write_json(TEMPLATE_KEY, raw)
    print(f"published {len(names)} properties to {store.location(TEMPLATE_KEY)}")
    return 0


def cmd_sample(args) -> int:
    root = _root(args)
    run = resolve_run(root, args.run)
    store = open_store(root)
    key = f"{run.key}/review-ui/sample.json"
    if store.exists(key) and not args.force:
        sys.exit(
            f"{key} already exists; the sample is fixed across iterations. "
            "Use --force to replace it."
        )
    ruleset, _ = _rules_for(store, run, args.rules)
    pages = list_pages(store, run)
    picked = pick_sample(
        pages,
        ruleset.get("sample", {}),
        ruleset["page_types"],
        lambda p: store.read_text(p.html_key),
        target=args.size,
    )
    store.write_json(key, {"run": run.key, "size": len(picked), "pages": picked})
    kinds: dict[str, int] = {}
    for page in picked:
        kinds[page["page_type"]] = kinds.get(page["page_type"], 0) + 1
    print(f"sampled {len(picked)} pages into {key}: {kinds}")
    return 0


def cmd_extract(args) -> int:
    root = _root(args)
    run = resolve_run(root, args.run)
    ruleset, properties = _rules_for(open_store(root), run, args.rules)
    report = run_extraction(root, run, ruleset, properties, workers=args.workers)
    fill_summary = {
        rule: {
            label: f"{c.get('present', 0)}/{c['total']}" for label, c in labels.items()
        }
        for rule, labels in report["fill"].items()
    }
    print(json.dumps({k: v for k, v in report.items() if k != "fill"}, indent=2))
    print("fill (present/total per canonical_label):")
    print(json.dumps(fill_summary, indent=2))
    regression = report["regression"]
    if regression["regressions"]:
        print(
            f"\nREGRESSION: {len(regression['regressions'])} previously accepted "
            "value(s) changed:"
        )
        for item in regression["regressions"][:20]:
            print(f"  {item['key']}: was {item['was']!r}, now {item['now']!r}")
        return 1
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    from .api import CatalogNotReady, create_app

    root = _root(args)
    golden_root = _spec(args.golden_root or os.environ.get("REVIEW_UI_GOLDEN_ROOT"))
    print(f"crawls and reviews: {root}")
    print(
        f"golden sets:        {golden_root or f'{root} (REVIEW_UI_GOLDEN_ROOT is not set)'}"
    )
    run = resolve_run(root, args.run) if args.run else None
    try:
        app = create_app(
            root,
            run,
            extraction_id=args.extraction,
            review_id=args.review,
            new_review=args.new_review,
            golden_root=_spec(
                args.golden_root or os.environ.get("REVIEW_UI_GOLDEN_ROOT")
            ),
        )
    except CatalogNotReady as exc:
        sys.exit(str(exc))
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def cmd_export_feedback(args) -> int:
    from .exports import feedback_markdown
    from .review import ReviewSession
    from .views import ExtractionView

    root = _root(args)
    run = resolve_run(root, args.run)
    store = open_store(root)
    sessions = review_sessions(store, run.key)
    review_id = args.review or (sessions[-1] if sessions else None)
    if not review_id:
        sys.exit("no review sessions for this run yet")
    review = ReviewSession.open(store, run.key, review_id)
    view = ExtractionView(store, run.key, review.session["extraction_id"])
    stem_of_url = {row["url"]: stem for stem, row in view.pages.items()}
    text = feedback_markdown(store, run, view, review.state(), stem_of_url)
    key = f"{run.key}/review-ui/{review_id}/feedback.md"
    store.write_text(key, text)
    print(f"wrote {store.location(key)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="review-ui-v2")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, run=True):
        p.add_argument(
            "--root",
            help=f"storage root: a folder (default {DEFAULT_ROOT}) or an azure://https://<account>.blob.core.windows.net/<container>[/prefix]; env REVIEW_UI_ROOT",
        )
        p.add_argument(
            "--no-cache",
            action="store_true",
            help="do not use the local page cache for an Azure root",
        )
        if run:
            p.add_argument(
                "--run", help="crawl run: exact key or a unique substring of it"
            )

    p = sub.add_parser("build-properties", help="template CSV -> properties json")
    p.add_argument("--csv", required=True)
    p.add_argument("--out", default=str(PROPERTIES))
    p.set_defaults(func=cmd_build_properties)

    p = sub.add_parser(
        "check-rules",
        help="validate a ruleset file against the published template and run its examples",
    )
    common(p, run=False)
    p.add_argument("--rules", required=True)
    p.set_defaults(func=cmd_check_rules)

    p = sub.add_parser(
        "rules", help="rulesets published in the storage root: list | publish | pull"
    )
    rules_sub = p.add_subparsers(dest="rules_command", required=True)
    q = rules_sub.add_parser("list", help="list the published rulesets")
    common(q, run=False)
    q.set_defaults(func=cmd_rules_list)
    q = rules_sub.add_parser(
        "publish",
        help="validate a ruleset file and write it to <root>/review-ui-index/rulesets/<catalog>/rules.json",
    )
    common(q, run=False)
    q.add_argument("file")
    q.add_argument(
        "--force", action="store_true", help="allow a version that is not higher"
    )
    q.set_defaults(func=cmd_rules_publish)
    q = rules_sub.add_parser(
        "pull", help="print or save a published ruleset to edit it"
    )
    common(q, run=False)
    q.add_argument("catalog", help="the ruleset's catalog_folder")
    q.add_argument("--out", help="write to this file instead of printing")
    q.set_defaults(func=cmd_rules_pull)

    p = sub.add_parser(
        "cache", help="the local page cache for Azure roots: status | clear | warm"
    )
    cache_sub = p.add_subparsers(dest="cache_command", required=True)
    q = cache_sub.add_parser(
        "status", help="show what is cached and how much space it uses"
    )
    common(q, run=False)
    q.set_defaults(func=cmd_cache_status)
    q = cache_sub.add_parser(
        "clear", help="delete cached pages (this root, one run, or all)"
    )
    common(q)
    q.add_argument("--all", action="store_true", help="every root, not just this one")
    q.set_defaults(func=cmd_cache_clear)
    q = cache_sub.add_parser(
        "warm", help="download every page of a run into the cache, in parallel"
    )
    common(q)
    q.add_argument("--threads", type=int, default=16)
    q.set_defaults(func=cmd_cache_warm)

    p = sub.add_parser("template", help="the shared field template: publish")
    template_sub = p.add_subparsers(dest="template_command", required=True)
    q = template_sub.add_parser(
        "publish",
        help="write a properties json (from build-properties) to <root>/review-ui-index/templates/",
    )
    common(q, run=False)
    q.add_argument("file")
    q.set_defaults(func=cmd_template_publish)

    p = sub.add_parser("sample", help="pick the fixed review sample")
    common(p)
    p.add_argument(
        "--rules",
        help="a draft ruleset file; default: the ruleset published in the storage root",
    )
    p.add_argument("--size", type=int, help="default: the ruleset's sample target")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_sample)

    p = sub.add_parser("extract", help="run rules over every page of a run")
    common(p)
    p.add_argument(
        "--rules",
        help="a draft ruleset file; default: the ruleset published in the storage root",
    )
    p.add_argument("--workers", type=int)
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser(
        "serve",
        help="start the review app (with no --run: a landing page to choose a ruleset)",
    )
    common(p)
    p.add_argument("--extraction", help="default: latest")
    p.add_argument("--review", help="open this review session")
    p.add_argument(
        "--golden-root",
        help="where 'Save golden dataset' writes (a folder or azure:// URI, e.g. the "
        "xtra-golden-sets-verified container); default: $REVIEW_UI_GOLDEN_ROOT, else the "
        "crawl root",
    )
    p.add_argument(
        "--new-review",
        action="store_true",
        help="start a fresh session (default: resume the latest one for this extraction)",
    )
    p.add_argument(
        "--host",
        default=os.environ.get("REVIEW_UI_HOST", "127.0.0.1"),
        help="default: $REVIEW_UI_HOST, else 127.0.0.1 (a container sets 0.0.0.0)",
    )
    p.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("REVIEW_UI_PORT") or os.environ.get("PORT") or 8001),
        help="default: $REVIEW_UI_PORT, else $PORT, else 8001",
    )
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("export-feedback", help="write feedback.md for a review session")
    common(p)
    p.add_argument("--review", help="default: latest")
    p.set_defaults(func=cmd_export_feedback)

    args = parser.parse_args(argv)
    if getattr(args, "no_cache", False):
        os.environ[CACHE_SWITCH_ENV] = "0"  # inherited by extract's worker processes
    try:
        return args.func(args)
    except Exception as exc:  # Azure errors are explained; everything else is re-raised
        message = _azure_message(exc, args)
        if message is None:
            raise
        sys.exit(message)


if __name__ == "__main__":
    sys.exit(main())
