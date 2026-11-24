"""Every path of the storage layout (spec §4.5; LearningProgram spec, approved items 20–21).

The Studio's own container (`--root`, `GOLDEN_DATASETS_ROOT`) holds only Studio data, per class:

    <root>/manifest.json
    <root>/<catalog>/<class>/{rules/<rule_id>/vNNNN.json, rulesets/vNNNN.json, annotations.jsonl, agent-runs/,
                              publish.json}
    <root>/<catalog>/<crawl>/{pages.parquet, assets/}
    <root>/<catalog>/<crawl>/<class>/{rule-runs/<rs-NNNN>/, golden/ruleset-vN/, scores-pending.json}

xtra-cli's container (`GOLDEN_DATASETS_XTRA_SOURCE`, see `xtra_paths`) holds what xtra-cli writes, read in place:
the crawls (`<catalog>/<crawl>/{crawl.json, pages/}`, from the root the manifest records per catalog), the extract
outputs, and the scores the Studio computes with xtra's scorer.

A rule run (`rs-NNNN`, once called an extraction) is the Studio's rules run over a crawl; an extract run is xtra's.
"""

from __future__ import annotations

STUDIO = "golden-dataset-studio"  # the folder the Studio used inside a catalog before class folders (migrate.py)
MANIFEST = "manifest.json"
LEGACY_MANIFEST = f"{STUDIO}/manifest.json"


# --- the Studio's container: per catalog and class ----------------------------------------------------------
def class_dir(catalog: str, cls: str) -> str:
    return f"{catalog}/{cls}"


def rule_version(catalog: str, cls: str, rule_id: str, version: int) -> str:
    return f"{class_dir(catalog, cls)}/rules/{rule_id}/v{version:04d}.json"


def rules_prefix(catalog: str, cls: str, rule_id: str) -> str:
    return f"{class_dir(catalog, cls)}/rules/{rule_id}/v"


def ruleset(catalog: str, cls: str, version: int) -> str:
    return f"{class_dir(catalog, cls)}/rulesets/v{version:04d}.json"


def annotations(catalog: str, cls: str) -> str:
    return f"{class_dir(catalog, cls)}/annotations.jsonl"


def agent_runs_dir(catalog: str, cls: str) -> str:
    """Runs of Claude on the remote agent (agent_runs.py): `current.json` (the lock), `last.json`, `<run_id>/`."""
    return f"{class_dir(catalog, cls)}/agent-runs"


def agent_run_dir(catalog: str, cls: str, run_id: str) -> str:
    return f"{agent_runs_dir(catalog, cls)}/{run_id}"


# --- the Studio's container: per crawl -------------------------------------------------------------------------
def crawl_dir(catalog: str, crawl: str) -> str:
    """The Studio's files about one crawl (its page index and assets), beside its class folders."""
    return f"{catalog}/{crawl}"


def pages_parquet(catalog: str, crawl: str) -> str:
    return f"{crawl_dir(catalog, crawl)}/pages.parquet"


def assets_dir(catalog: str, crawl: str) -> str:
    return f"{crawl_dir(catalog, crawl)}/assets"


def asset_file(catalog: str, crawl: str, sha256: str) -> str:
    return f"{assets_dir(catalog, crawl)}/files/{sha256}"


def crawl_class_dir(catalog: str, crawl: str, cls: str) -> str:
    return f"{crawl_dir(catalog, crawl)}/{cls}"


def extraction_dir(catalog: str, crawl: str, cls: str, extraction: str) -> str:
    """One rule run (`rs-NNNN`)."""
    return f"{crawl_class_dir(catalog, crawl, cls)}/rule-runs/{extraction}"


def extraction_file(catalog: str, crawl: str, cls: str, extraction: str, table: str) -> str:
    name = "extraction.json" if table == "extraction" else f"{table}.parquet"
    return f"{extraction_dir(catalog, crawl, cls, extraction)}/{name}"


def golden_dir(catalog: str, crawl: str, cls: str, publication: str) -> str:
    """publication.json, lineage.parquet and golden.parquet of one golden dataset version (the Studio's record)."""
    return f"{crawl_class_dir(catalog, crawl, cls)}/golden/{publication}"


def pending_score(catalog: str, crawl: str, cls: str) -> str:
    """{due_at, reason}: a score due 5 minutes after the last review (Evals spec §4.3)."""
    return f"{crawl_class_dir(catalog, crawl, cls)}/scores-pending.json"


# --- xtra-cli's container: the crawl, read in place ---------------------------------------------------------
def crawl_input(catalog: str, crawl: str) -> str:
    return f"{catalog}/{crawl}"


def crawl_json(catalog: str, crawl: str) -> str:
    return f"{catalog}/{crawl}/crawl.json"


def pages_dir(catalog: str, crawl: str) -> str:
    return f"{catalog}/{crawl}/pages"


def page_html(catalog: str, crawl: str, stem: str) -> str:
    return f"{pages_dir(catalog, crawl)}/{stem}.html"


def page_meta(catalog: str, crawl: str, stem: str) -> str:
    return f"{pages_dir(catalog, crawl)}/{stem}.meta.json"


EXTRACTION_TABLES = ("page_labels", "occurrences", "matches", "signals")
