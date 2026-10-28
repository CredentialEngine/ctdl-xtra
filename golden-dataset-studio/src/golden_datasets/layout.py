"""Every path of the storage layout (spec §4.5), relative to the storage root.

    <root>/golden-dataset-studio/manifest.json
    <root>/<catalog>/golden-dataset-studio/{rules/<rule_id>/vNNNN.json, rulesets/vNNNN.json, annotations.jsonl,
                                          agent-runs/}
    <root>/<catalog>/<crawl>/{crawl.json, pages/}                                  read-only (xtra-cli)
    <root>/<catalog>/<crawl>/golden-dataset-studio/{pages.parquet, assets/, extractions/<id>/, golden/ruleset-vN/,
                                                   scores/pending.json}
"""

from __future__ import annotations

STUDIO = "golden-dataset-studio"
MANIFEST = f"{STUDIO}/manifest.json"


def catalog_dir(catalog: str) -> str:
    return f"{catalog}/{STUDIO}"


def rule_version(catalog: str, rule_id: str, version: int) -> str:
    return f"{catalog_dir(catalog)}/rules/{rule_id}/v{version:04d}.json"


def ruleset(catalog: str, version: int) -> str:
    return f"{catalog_dir(catalog)}/rulesets/v{version:04d}.json"


def annotations(catalog: str) -> str:
    return f"{catalog_dir(catalog)}/annotations.jsonl"


def agent_runs_dir(catalog: str) -> str:
    """Runs of Claude on the remote agent (agent_runs.py): `current.json` (the lock), `last.json`, `<run_id>/`."""
    return f"{catalog_dir(catalog)}/agent-runs"


def agent_run_dir(catalog: str, run_id: str) -> str:
    return f"{agent_runs_dir(catalog)}/{run_id}"


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


def crawl_dir(catalog: str, crawl: str) -> str:
    return f"{catalog}/{crawl}/{STUDIO}"


def pages_parquet(catalog: str, crawl: str) -> str:
    return f"{crawl_dir(catalog, crawl)}/pages.parquet"


def assets_dir(catalog: str, crawl: str) -> str:
    return f"{crawl_dir(catalog, crawl)}/assets"


def asset_file(catalog: str, crawl: str, sha256: str) -> str:
    return f"{assets_dir(catalog, crawl)}/files/{sha256}"


def extraction_dir(catalog: str, crawl: str, extraction: str) -> str:
    return f"{crawl_dir(catalog, crawl)}/extractions/{extraction}"


def extraction_file(catalog: str, crawl: str, extraction: str, table: str) -> str:
    name = "extraction.json" if table == "extraction" else f"{table}.parquet"
    return f"{extraction_dir(catalog, crawl, extraction)}/{name}"


def golden_dir(catalog: str, crawl: str, publication: str) -> str:
    return f"{crawl_dir(catalog, crawl)}/golden/{publication}"


def pending_score(catalog: str, crawl: str) -> str:
    """{due_at, reason}: a score due 5 minutes after the last review (Evals spec §4.3)."""
    return f"{crawl_dir(catalog, crawl)}/scores/pending.json"


EXTRACTION_TABLES = ("page_labels", "occurrences", "matches", "signals")
