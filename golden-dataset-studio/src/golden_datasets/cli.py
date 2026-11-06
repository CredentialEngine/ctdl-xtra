"""`golden-datasets`: the Studio's command line (spec §6).

Every command takes `--root` (or `GOLDEN_DATASETS_ROOT`): a folder or an `azure://https://…/container[/prefix]` URI.
Commands that work on one catalog take `--catalog` (or `GOLDEN_DATASETS_CATALOG`), either the folder name or its
short name (`avc`, `ccsf`, `marshall`, `ualr`, `wvu`). Unset variables are read from `golden-datasets.env` (KEY=VALUE
lines) in the current folder and its parents, the nearest first: Claude Code's shell commands don't share `export`s.

Each command's implementation is imported lazily, so `--help` stays fast.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path

from .errors import UserError

DEFAULT_PORT = 8000
ENV_FILE = "golden-datasets.env"
# the team's shared Studio root on Azure: the Azure version of the prompt points Claude here
DEFAULT_AZURE_ROOT = "azure://https://ceteststorage.blob.core.windows.net/xtra-cli-output/zz-scratch-review-ui-v3"


def load_env_file(start: Path | None = None) -> Path | None:
    """Set the unset variables from every `golden-datasets.env` in the current folder and its parents; the environment
    always wins, then the nearest file. So a folder's file can hold the root and catalog while a parent's holds shared
    settings (on K2: the SAS tokens in /var/lib/k2/work). Returns the nearest file read."""
    here = (start or Path.cwd()).resolve()
    nearest = None
    for folder in (here, *here.parents):
        f = folder / ENV_FILE
        if f.is_file():
            nearest = nearest or f
            for line in f.read_text().splitlines():
                key, sep, value = line.strip().partition("=")
                key = key.removeprefix("export ").strip()
                if sep and key and not key.startswith("#"):
                    os.environ.setdefault(key, value.strip().strip("'\""))
    return nearest


def _root_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--root", default=os.environ.get("GOLDEN_DATASETS_ROOT"),
                   help="storage root: a folder or azure://https://<account>.blob.core.windows.net/<container>[/prefix] "
                        "(default: $GOLDEN_DATASETS_ROOT)")


def _catalog_args(p: argparse.ArgumentParser, required: bool = True) -> None:
    p.add_argument("--catalog", "-c", default=os.environ.get("GOLDEN_DATASETS_CATALOG"),
                   required=required and not os.environ.get("GOLDEN_DATASETS_CATALOG"),
                   help="catalog folder or short name (avc, ccsf, marshall, ualr, wvu)")
    p.add_argument("--crawl", default=None, help="crawl id (default: the catalog's current crawl)")


def _crawls_root_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--crawls-root", default=os.environ.get("GOLDEN_DATASETS_CRAWLS_ROOT"),
                   help="where xtra-cli's crawls are (default: $GOLDEN_DATASETS_CRAWLS_ROOT, else the container above "
                        "an Azure root's prefix, else the root itself)")


def _target_args(p: argparse.ArgumentParser, prompt: bool = True) -> None:
    if prompt:
        p.add_argument("--target", choices=["local", "azure"], default="azure",
                       help="azure (default, what the Studio shows): Claude works on the Azure root after a minimal "
                            "setup; local: on --root itself")
    p.add_argument("--azure-root", default=os.environ.get("GOLDEN_DATASETS_AZURE_ROOT") or DEFAULT_AZURE_ROOT,
                   help="the Azure root the prompt's Azure version points Claude at (default: "
                        "$GOLDEN_DATASETS_AZURE_ROOT, else the team's shared prefix)")


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

    crawled = sub.add_parser("crawls", help="catalogs xtra-cli has crawled: list, add one to the Studio")
    csub = crawled.add_subparsers(dest="crawls_command", metavar="ACTION", required=True)
    p = csub.add_parser("list", help="one line per crawled catalog: its latest crawl's date, pages and status")
    _root_args(p), _crawls_root_args(p)
    p.add_argument("q", nargs="?", default=None, help="only catalogs whose name, folder or URL has these words")
    _cmd(p, "golden_datasets.crawls:cmd_list")
    p = csub.add_parser("add", help="copy a crawl into the root, index its pages, archive their assets, name it")
    _root_args(p), _crawls_root_args(p)
    p.add_argument("catalog", help="the crawled catalog's folder name")
    p.add_argument("--crawl", default=None, help="crawl id (default: its latest)")
    p.add_argument("--by", default=None, help="who added it (recorded in the manifest)")
    _cmd(p, "golden_datasets.crawls:cmd_add")

    p = sub.add_parser("import-v2", help="v2 rules.json → rule versions v1 + ruleset v1; v2 decisions → annotations")
    _root_args(p), _catalog_args(p)
    p.add_argument("--v2-root", default=None,
                   help="where v2's extractions/ and review-ui/ live (default: the storage root)")
    p.add_argument("--session", default=None, help="v2 review session id (default: the latest with decisions)")
    _cmd(p, "golden_datasets.import_v2:cmd_import_v2")

    props = sub.add_parser("properties", help="the property list (properties.csv): sync from the sheet, list, apply")
    prsub = props.add_subparsers(dest="properties_command", metavar="ACTION", required=True)
    p = prsub.add_parser("sync", help="the Phase 1 sheet → properties.csv (writes only the file: added / kept / "
                                      "removed, and warnings)")
    p.add_argument("--from", dest="source", default=None, metavar="FILE",
                   help="an xlsx export of the sheet, or a CSV of its Phase 1 tab (default: download the sheet)")
    p.add_argument("--accept-renames", action="store_true",
                   help="write a changed path or name on an existing rule id")
    _cmd(p, "golden_datasets.properties:cmd_sync")
    p = prsub.add_parser("list", help="properties.csv as a table")
    _cmd(p, "golden_datasets.properties:cmd_list")
    p = prsub.add_parser("apply", help="add properties.csv's new properties to catalogs, with no rule yet (one "
                                       "ruleset version per catalog that gets any)")
    _root_args(p)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--catalog", "-c", default=None, help="catalog folder or short name")
    g.add_argument("--all", action="store_true", help="every catalog in the root")
    p.add_argument("--by", default=os.environ.get("GOLDEN_DATASETS_AUTHOR", "golden-datasets properties apply"))
    _cmd(p, "golden_datasets.properties:cmd_apply")

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
    p.add_argument("rule_ids", nargs="*")
    p.add_argument("--all", action="store_true", help="every rule of the latest ruleset")
    p.add_argument("--for", dest="for_catalog", default=None, metavar="CATALOG",
                   help="a template for another catalog's first ruleset: every rule and the settings, for CATALOG")
    _cmd(p, "golden_datasets.loop:cmd_rule_draft")
    inferred_help = ("the values you worked out for courses marked wrong with no expected value: [{rule, course, "
                     "annotation, value}] (default: ./inferred.json if there is one)")
    p = rsub.add_parser("try", help="run a draft over the whole crawl, check every rule against every golden value, "
                                    "print the scorecard; writes nothing")
    _root_args(p), _catalog_args(p)
    p.add_argument("draft")
    p.add_argument("--json", action="store_true", help="print the scorecard as JSON")
    p.add_argument("--inferred", default=None, metavar="PATH", help=inferred_help)
    _cmd(p, "golden_datasets.loop:cmd_rule_try")
    p = rsub.add_parser("publish", help="new rule versions + ruleset version + extraction, uploaded together (one "
                                        "publish at a time; rebased on the latest version, or refused if another "
                                        "publish changed the same rules)")
    _root_args(p), _catalog_args(p)
    p.add_argument("draft")
    p.add_argument("--note", default=None, help="one line for the ruleset version")
    p.add_argument("--force", action="store_true", help="publish even when a golden value that was right gets worse")
    p.add_argument("--by", default="Claude Code via golden-datasets rule publish")
    p.add_argument("--inferred", default=None, metavar="PATH", help=inferred_help)
    _cmd(p, "golden_datasets.loop:cmd_rule_publish")
    p = rsub.add_parser("downstream", help="the rules that read these rules, directly or not (what an edit can move)")
    _root_args(p), _catalog_args(p)
    p.add_argument("rule_ids", nargs="+")
    _cmd(p, "golden_datasets.loop:cmd_rule_downstream")

    rsets = sub.add_parser("ruleset", help="ruleset versions: revert")
    rssub = rsets.add_subparsers(dest="ruleset_command", metavar="ACTION", required=True)
    p = rssub.add_parser("revert", help="publish a new version with every rule this version changed back to its "
                                        "previous version")
    _root_args(p), _catalog_args(p)
    p.add_argument("version", type=int)
    p.add_argument("--by", default=os.environ.get("GOLDEN_DATASETS_AUTHOR", "golden-datasets ruleset revert"))
    _cmd(p, "golden_datasets.loop:cmd_ruleset_revert")

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

    # --- Agent runs (Claude on the remote agent reports here; docs/qrspi/k2-runs) -----------------------
    runs = sub.add_parser("run", help="a Studio run on the remote agent: report progress, end it, show it")
    nsub = runs.add_subparsers(dest="run_command", metavar="ACTION", required=True)
    p = nsub.add_parser("note", help="one progress line, shown live in the Studio")
    _root_args(p)
    _catalog_args(p)
    p.add_argument("--run", default=None, help="the run id from the prompt (default: $GOLDEN_DATASETS_RUN)")
    p.add_argument("text", nargs="+")
    p.add_argument("--by", default="golden-rules agent")
    _cmd(p, "golden_datasets.agent_runs:cmd_note")
    p = nsub.add_parser("done", help="end the run with your report.json: it is checked, then shown in the Studio")
    _root_args(p)
    _catalog_args(p)
    p.add_argument("--run", default=None, help="default: $GOLDEN_DATASETS_RUN")
    p.add_argument("--report", default=None, metavar="PATH",
                   help="report.json (facts by id; the CLI checks it and writes the report with its links); - reads stdin")
    p.add_argument("--outcome", default=None, help="old prompts: a one-line outcome instead of --report")
    p.add_argument("--failed", action="store_true")
    p.add_argument("--summary-file", default=None, metavar="PATH",
                   help="your full report (Markdown), kept with the run and shown in the Studio; - reads stdin")
    p.add_argument("--by", default="golden-rules agent")
    _cmd(p, "golden_datasets.agent_runs:cmd_done")
    p = nsub.add_parser("show", help="the run record and its notes")
    _root_args(p)
    _catalog_args(p)
    p.add_argument("--run", required=True)
    _cmd(p, "golden_datasets.agent_runs:cmd_show")
    p = nsub.add_parser("context", help="each rule's last run and the annotations since (for a fresh session)")
    _root_args(p)
    _catalog_args(p)
    p.add_argument("rule_ids", nargs="+")
    _cmd(p, "golden_datasets.agent_runs:cmd_context")

    # --- Prompt ----------------------------------------------------------------------------------------
    p = sub.add_parser("prompt", help="the same text the UI's Copy prompt button gives")
    _root_args(p), _catalog_args(p)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--rule", default=None)
    g.add_argument("--needs-work", action="store_true")
    g.add_argument("--first-rules", action="store_true",
                   help="a catalog with no rules yet: write and publish its first ruleset from a template")
    _target_args(p)
    _cmd(p, "golden_datasets.prompt:cmd_prompt")

    # --- Golden ----------------------------------------------------------------------------------------
    golden = sub.add_parser("golden", help="dataset versions: publish (an approved rule's silver dataset), backfill")
    gsub = golden.add_subparsers(dest="golden_command", metavar="ACTION", required=True)
    to_help = ("golden root: a folder or an azure:// prefix (default: $GOLDEN_DATASETS_GOLDEN_ROOT, else `golden` "
               "beside a local root, else the xtra-golden-sets container)")
    p = gsub.add_parser("publish", help="publish properties into the silver dataset of the current ruleset (written "
                                        "whole: its version's silver tree, every value, also called rule-matched, and "
                                        "golden tree, only human-reviewed values; the latest location; lineage + "
                                        "golden.parquet)")
    _root_args(p), _catalog_args(p)
    p.add_argument("--to", default=None, help=to_help)
    p.add_argument("--property", action="append", default=None, metavar="NAME",
                   help="a property to publish, e.g. Description (repeatable; default: every property whose rule is "
                        "approved). Columns published earlier in the same ruleset stay")
    p.add_argument("--allow-unapproved", action="store_true",
                   help="testing only: publish a property although its rule isn't approved (recorded in publication.json)")
    _cmd(p, "golden_datasets.golden:cmd_golden_publish")
    p = gsub.add_parser("backfill", help="rebuild the publications made before versions (pub-…) as golden dataset "
                                         "versions (ruleset-vN), from their lineage and the immutable extractions")
    _root_args(p), _catalog_args(p)
    p.add_argument("--to", default=None, help=to_help)
    p.add_argument("--again", action="store_true",
                   help="also write every existing version again in the current layout (its columns, extraction and "
                        "publication time kept); old version folders aren't removed")
    _cmd(p, "golden_datasets.golden:cmd_golden_backfill")

    # --- Evals ---------------------------------------------------------------------------------------
    p = sub.add_parser("score", help="score xtra's extract output against a golden dataset with xtra's own scorer: the "
                                     "human-reviewed values and every rule-matched value (kept in scores/sc-NNNN)")
    _root_args(p), _catalog_args(p)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--ruleset", type=int, default=None, metavar="N",
                   help="the golden dataset ruleset vN (default: the latest)")
    g.add_argument("--draft", default=None, metavar="rs-NNNN", help="an unpublished extraction, as if it were published")
    g.add_argument("--human-reviewed", action="store_true",
                   help="the human-reviewed values as they are now (the latest version's trees)")
    p.add_argument("--output", default=None, metavar="PATH|ID",
                   help="the extract output: a copy's id (extract-outputs/<id>), or a folder with records/ and "
                        "extract-report.json (default: the latest in $GOLDEN_DATASETS_XTRA_SOURCE, copied when new)")
    p.add_argument("--by", default=os.environ.get("GOLDEN_DATASETS_AUTHOR", "golden-datasets score"))
    _cmd(p, "golden_datasets.scores:cmd_score")

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
    p.add_argument("--k2-url", default=os.environ.get("GOLDEN_DATASETS_K2_URL"),
                   help="K2 server running the remote agent (key: GOLDEN_DATASETS_K2_KEY); unset = runs are off and "
                        "run buttons open the prompt")
    p.add_argument("--k2-agent", default=os.environ.get("GOLDEN_DATASETS_K2_AGENT", "golden-rules"),
                   help="the K2 workspace whose agent runs the prompts; its folder is <K2 work>/<workspace>, where "
                        "<K2 work> is $GOLDEN_DATASETS_K2_WORK, else /var/lib/k2/work (the run prompt's paths)")
    p.add_argument("--agent-run-minutes", type=int, default=90, help="a run ends as timed out after this long")
    p.add_argument("--k2-max-runs", type=int, default=int(os.environ.get("GOLDEN_DATASETS_K2_MAX_RUNS") or 2),
                   help="AI runs working at once, all catalogs (default: $GOLDEN_DATASETS_K2_MAX_RUNS, else 2); set "
                        "K2's host_session_cell_cap for the workspace to the same number")
    p.add_argument("--prompt-users", default=os.environ.get("GOLDEN_DATASETS_PROMPT_USERS", "Eric Riddoch,Seth Alt"),
                   help="profiles whose run buttons also offer Open the prompt (comma-separated)")
    _target_args(p, prompt=False)
    _crawls_root_args(p)
    _cmd(p, "golden_datasets.server.app:cmd_serve")
    p = sub.add_parser("hash-password", help="salt and hash the Studio's shared password, for GOLDEN_DATASETS_PASSWORD_HASH")
    _cmd(p, "golden_datasets.server.auth:cmd_hash_password")
    return ap


def main(argv: list[str] | None = None) -> int:
    load_env_file()
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
