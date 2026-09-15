from __future__ import annotations

from common.keys import (
    crawl_key,
    expected_key,
    jsonld_key,
    page_html_key,
    page_meta_key,
    page_text_key,
    record_key,
    run_prefix,
    slots_key,
)

CATALOG = "example"
RUN = "2026-09-14T18:12:00Z"


def test_run_prefix_is_catalog_then_timestamp() -> None:
    assert run_prefix(CATALOG, RUN) == f"{CATALOG}/{RUN}"
    assert run_prefix("/example/", RUN) == f"{CATALOG}/{RUN}"


def test_etl_object_keys() -> None:
    assert slots_key(CATALOG, RUN).endswith("/slots.json")
    assert crawl_key(CATALOG, RUN).endswith("/crawl.json")
    assert page_html_key(CATALOG, RUN, "stem").endswith("/pages/stem.html")
    assert page_meta_key(CATALOG, RUN, "stem").endswith("/pages/stem.meta.json")
    assert page_text_key(CATALOG, RUN, "stem").endswith("/pages/stem.txt")
    assert record_key(CATALOG, RUN, "id").endswith("/records/id.json")
    assert jsonld_key(CATALOG, RUN, "id").endswith("/jsonld/id.json")
    assert expected_key(CATALOG, RUN, "id").endswith("/expected/id.json")
    assert "pack" not in slots_key(CATALOG, RUN)
    assert ".zip" not in crawl_key(CATALOG, RUN)
