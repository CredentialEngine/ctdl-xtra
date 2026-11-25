"""xtra-cli's container, which xtra-cli owns (LearningProgram spec, approved item 21): the Studio reads crawls, extract
outputs and scores where xtra-cli writes them, and keeps no copies.

    <xtra>/<catalog>/<crawl>/{crawl.json, pages/}                          the crawl
    <xtra>/<catalog>/<crawl>/{extraction_report/, extraction-*-report.json}  the latest extract output (overwritten)
    <xtra>/<catalog>/<crawl>/extract/<output id>/                          one extract output, kept: an older output
                                                                           the Studio copied (records/, its reports)
    <xtra>/<catalog>/<crawl>/extract/<output id>/scores/<golden>/<class>/<score id>/{score.json, values.parquet}
    <xtra>/<catalog>/<crawl>/extract/<output id>/scores/<golden>-<golden|silver>/<class>/<property>/score.json
    <xtra>/scores/<class>/<property>/<catalog>.jsonl                       one line per score of the property

`<output id>` is the output's report time (`2026-11-24T19-21-13Z`); `<golden>` the golden dataset it was scored
against (`ruleset-v3`, `human-reviewed`, `rs-0012`), and `<golden>-golden` / `<golden>-silver` one of its two trees
(the baselines xtra's scorer reads: approved items 25–28); `<property>` is xtra's own name for it
(`ceterms_name`, `ceterms_creditValue__schema_minValue`: `common.keys.property_key`). The Studio's whole score (every
property, both trees, each value's outcome) is the `<score id>` folder; each property's result and the history line
come from it.

Where it is: `$GOLDEN_DATASETS_XTRA_SOURCE` (`$GOLDEN_DATASETS_CRAWLS_ROOT` is read too, the older name for the same
container), else the container above an Azure root's prefix, else the shared `xtra-cli-output` container.
"""

from __future__ import annotations

import os

from .storage import AzureRoot, Root

SHARED = "azure://https://ceteststorage.blob.core.windows.net/xtra-cli-output"
ENV, OLD_ENV = "GOLDEN_DATASETS_XTRA_SOURCE", "GOLDEN_DATASETS_CRAWLS_ROOT"


def xtra_root(studio_root: Root | None = None) -> str | None:
    """xtra-cli's container: the setting, else the container above an Azure Studio root's prefix, else the shared
    one for an Azure root. None for a local Studio root with no setting."""
    src = os.environ.get(ENV) or os.environ.get(OLD_ENV)
    if src:
        return src
    if isinstance(studio_root, AzureRoot):
        if studio_root.prefix:
            return studio_root.uri[: -len(studio_root.prefix)].rstrip("/")
        return SHARED
    return None


def extract_run_dir(catalog: str, crawl: str, output: str) -> str:
    return f"{catalog}/{crawl}/extract/{output}"


def score_dir(catalog: str, crawl: str, output: str, golden: str, cls: str, score: str) -> str:
    """score.json and values.parquet of one score (Evals spec §4), under the extract output it scored."""
    return f"{extract_run_dir(catalog, crawl, output)}/scores/{golden}/{cls}/{score}"


def property_score_dir(catalog: str, crawl: str, output: str, baseline: str, cls: str, prop: str) -> str:
    """One property's result against one baseline (`ruleset-v3-golden`)."""
    return f"{extract_run_dir(catalog, crawl, output)}/scores/{baseline}/{cls}/{prop}"


def history(cls: str, prop: str, catalog: str) -> str:
    """A property's score history for one catalog: one JSON line per score, appended."""
    return f"scores/{cls}/{prop}/{catalog}.jsonl"
