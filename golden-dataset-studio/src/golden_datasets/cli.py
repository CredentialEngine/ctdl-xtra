"""`golden-datasets`: the Studio's command line (spec §6).

Every command takes `--root` (or `GOLDEN_DATASETS_ROOT`): a folder or an `azure://https://…/container[/prefix]` URI.
Commands that work on one catalog take `--catalog` (or `GOLDEN_DATASETS_CATALOG`), either the folder name or its
short name (`avc`, `ccsf`, `marshall`, `ualr`, `wvu`).

Each command's implementation is imported lazily, so `--help` stays fast.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys

from .errors import UserError

DEFAULT_PORT = 8000


def _root_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--root", default=os.environ.get("GOLDEN_DATASETS_ROOT"),
                   help="storage root: a folder or azure://https://<account>.blob.core.windows.net/<container>[/prefix] "
                        "(default: $GOLDEN_DATASETS_ROOT)")


def _catalog_args(p: argparse.ArgumentParser, required: bool = True) -> None:
    p.add_argument("--catalog", "-c", default=os.environ.get("GOLDEN_DATASETS_CATALOG"),
                   required=required and not os.environ.get("GOLDEN_DATASETS_CATALOG"),
                   help="catalog folder or short name (avc, ccsf, marshall, ualr, wvu)")
    p.add_argument("--crawl", default=None, help="crawl id (default: the catalog's current crawl)")


def _cmd(p: argparse.ArgumentParser, target: str) -> None:
    """`target` is 'module:function'; the function receives the parsed args and returns an exit code."""
    p.set_defaults(_target=target)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="golden-datasets",
        description="CTDL Golden Dataset Studio: build golden datasets of CTDL Courses by improving rules.",
    )
    sub = ap.add_subparsers(dest="command", metavar="COMMAND")

    # --- Setup -----------------------------------------------------------------------------------------
    p = sub.add_parser("init", help="index a crawl's pages into pages.parquet and register it in the manifest")
    _root_args(p), _catalog_args(p)
    _cmd(p, "golden_datasets.extract:cmd_init")

    assets = sub.add_parser("assets", help="page assets (CSS, fonts, images)")
    asub = assets.add_subparsers(dest="assets_command", metavar="ACTION", required=True)
    p = asub.add_parser("fetch", help="download each page's CSS, fonts and images once, stored by hash; never runs JS")
    _root_args(p), _catalog_args(p)
    p.add_argument("--max-assets", type=int, default=400, help="safety limit on distinct asset URLs")
    _cmd(p, "golden_datasets.assets:cmd_fetch")

    p = sub.add_parser("import-v2", help="v2 rules.json → rule versions v1 + ruleset v1; v2 decisions → annotations")
    _root_args(p), _catalog_args(p)
    p.add_argument("--v2-root", default=None,
                   help="where v2's extractions/ and review-ui/ live (default: the storage root)")
    p.add_argument("--session", default=None, help="v2 review session id (default: the latest with decisions)")
    _cmd(p, "golden_datasets.import_v2:cmd_import_v2")

    # --- Run -------------------------------------------------------------------------------------------
    p = sub.add_parser("extract", help="run a ruleset version over the crawl (refuses if that extraction exists)")
    _root_args(p), _catalog_args(p)
    p.add_argument("--ruleset", type=int, default=None, help="ruleset version (default: the latest)")
    p.add_argument("--again", action="store_true", help="re-extract an extracted ruleset (gets a -b, -c … id)")
    _cmd(p, "golden_datasets.extract:cmd_extract")

    p = sub.add_parser("check", help="validate every primary/foreign key and every hash")
    _root_args(p), _catalog_args(p, required=False)
    _cmd(p, "golden_datasets.check:cmd_check")

    p = sub.add_parser("sql", help="DuckDB over named views (pages, occurrences, matches, signals, annotations, rules)")
    _root_args(p), _catalog_args(p)
    p.add_argument("query", help="SQL text")
    p.add_argument("--format", choices=["table", "csv", "json"], default="table")
    _cmd(p, "golden_datasets.query:cmd_sql")

    # --- For Claude ------------------------------------------------------------------------------------
    rule = sub.add_parser("rule", help="rules: list, show, annotations, draft, try, publish")
    rsub = rule.add_subparsers(dest="rule_command", metavar="ACTION", required=True)
    p = rsub.add_parser("list", help="every rule in the current ruleset, with status, fill and signal counts")
    _root_args(p), _catalog_args(p)
    _cmd(p, "golden_datasets.loop:cmd_rule_list")
    p = rsub.add_parser("show", help="a rule's definition, what/how/why, status, fill and signal counts")
    _root_args(p), _catalog_args(p)
    p.add_argument("rule_id")
    p.add_argument("--version", type=int, default=None)
    _cmd(p, "golden_datasets.loop:cmd_rule_show")
    p = rsub.add_parser("annotations", help="each annotation with value seen, expected text + location, note, page path")
    _root_args(p), _catalog_args(p)
    p.add_argument("rule_id")
    p.add_argument("--open", action="store_true", help="only verdicts that still need work")
    _cmd(p, "golden_datasets.loop:cmd_rule_annotations")
    p = rsub.add_parser("draft", help="current versions of one or more rules as an editable draft (JSON on stdout)")
    _root_args(p), _catalog_args(p)
    p.add_argument("rule_ids", nargs="+")
    _cmd(p, "golden_datasets.loop:cmd_rule_draft")
    p = rsub.add_parser("try", help="run a draft over the whole crawl and print the scorecard; writes nothing")
    _root_args(p), _catalog_args(p)
    p.add_argument("draft")
    p.add_argument("--json", action="store_true", help="print the scorecard as JSON")
    _cmd(p, "golden_datasets.loop:cmd_rule_try")
    p = rsub.add_parser("publish", help="new rule versions + ruleset version + extraction, uploaded together")
    _root_args(p), _catalog_args(p)
    p.add_argument("draft")
    p.add_argument("--note", default=None, help="one line for the ruleset version")
    p.add_argument("--force", action="store_true", help="publish even when a value marked correct changes")
    p.add_argument("--by", default="Claude Code via golden-datasets rule publish")
    _cmd(p, "golden_datasets.loop:cmd_rule_publish")

    pages = sub.add_parser("pages", help="saved pages: get, sample")
    psub = pages.add_subparsers(dest="pages_command", metavar="ACTION", required=True)
    p = psub.add_parser("get", help="make page files (and their assets) available locally and print their paths")
    _root_args(p), _catalog_args(p)
    p.add_argument("stems", nargs="+")
    p.add_argument("--to", default=None, help="copy the files into this folder")
    _cmd(p, "golden_datasets.loop:cmd_pages_get")
    p = psub.add_parser("sample", help="page paths where a rule fires, filtered by signal")
    _root_args(p), _catalog_args(p)
    p.add_argument("--rule", required=True)
    p.add_argument("--signal", default=None)
    p.add_argument("-n", type=int, default=20)
    _cmd(p, "golden_datasets.loop:cmd_pages_sample")

    # --- Prompt ----------------------------------------------------------------------------------------
    p = sub.add_parser("prompt", help="the same text the UI's Copy prompt button gives")
    _root_args(p), _catalog_args(p)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--rule", default=None)
    g.add_argument("--needs-work", action="store_true")
    _cmd(p, "golden_datasets.prompt:cmd_prompt")

    # --- Golden ----------------------------------------------------------------------------------------
    golden = sub.add_parser("golden", help="golden publication")
    gsub = golden.add_subparsers(dest="golden_command", metavar="ACTION", required=True)
    p = gsub.add_parser("publish", help="domain-only golden files (existing format + location + golden_id) + lineage")
    _root_args(p), _catalog_args(p)
    p.add_argument("--to", required=True, help="golden root: a folder or an azure:// prefix")
    p.add_argument("--allow-unapproved", action="store_true",
                   help="testing only: publish although some rules aren't approved (recorded in publication.json)")
    _cmd(p, "golden_datasets.golden:cmd_golden_publish")

    # --- Local work ------------------------------------------------------------------------------------
    p = sub.add_parser("sync", help="copy Studio files and pages between roots (both directions)")
    p.add_argument("--from", dest="src", required=True)
    p.add_argument("--to", dest="dst", required=True)
    p.add_argument("--catalog", "-c", default=None)
    p.add_argument("--crawl", default=None)
    p.add_argument("--pages", choices=["copy", "link", "skip"], default="copy",
                   help="saved pages: copy them, symlink them (local → local only), or skip them")
    p.add_argument("--studio-only", action="store_true", help="only golden-dataset-studio/ folders")
    p.add_argument("--dry-run", action="store_true")
    _cmd(p, "golden_datasets.sync:cmd_sync")

    p = sub.add_parser("serve", help="the web UI")
    _root_args(p)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--host", default="127.0.0.1")
    _cmd(p, "golden_datasets.server.app:cmd_serve")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "_target", None):
        ap.print_help()
        return 0
    if hasattr(args, "root") and args.root is None:
        ap.error("--root (or GOLDEN_DATASETS_ROOT) is required")
    module, func = args._target.split(":")
    try:
        code = getattr(importlib.import_module(module), func)(args)
    except BrokenPipeError:  # `golden-datasets … | head`
        return 0
    except UserError as exc:
        print(f"golden-datasets: {exc}", file=sys.stderr)
        return 2
    return int(code or 0)


if __name__ == "__main__":
    sys.exit(main())
