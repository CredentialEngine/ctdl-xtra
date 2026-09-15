"""Object keys for a catalog run. No zip, no pack directory."""

from __future__ import annotations

from common.clock import run_id_for_path


def run_prefix(catalog_id: str, run_id: str) -> str:
    return f"{catalog_id.strip('/')}/{run_id_for_path(run_id)}"


def slots_key(catalog_id: str, run_id: str) -> str:
    return f"{run_prefix(catalog_id, run_id)}/slots.json"


def crawl_key(catalog_id: str, run_id: str) -> str:
    return f"{run_prefix(catalog_id, run_id)}/crawl.json"


def page_html_key(catalog_id: str, run_id: str, stem: str) -> str:
    return f"{run_prefix(catalog_id, run_id)}/pages/{stem}.html"


def page_meta_key(catalog_id: str, run_id: str, stem: str) -> str:
    return f"{run_prefix(catalog_id, run_id)}/pages/{stem}.meta.json"


def page_text_key(catalog_id: str, run_id: str, stem: str) -> str:
    return f"{run_prefix(catalog_id, run_id)}/pages/{stem}.txt"


def record_key(catalog_id: str, run_id: str, record_id: str) -> str:
    return f"{run_prefix(catalog_id, run_id)}/records/{record_id}.json"


def jsonld_key(catalog_id: str, run_id: str, record_id: str) -> str:
    return f"{run_prefix(catalog_id, run_id)}/jsonld/{record_id}.json"


def expected_key(catalog_id: str, run_id: str, record_id: str) -> str:
    return f"{run_prefix(catalog_id, run_id)}/expected/{record_id}.json"
