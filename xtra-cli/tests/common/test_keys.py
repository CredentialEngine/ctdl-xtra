from __future__ import annotations

import pytest

from common.keys import (
    STEM_DIGEST_LENGTH,
    STEM_SLUG_LIMIT,
    catalog_folder_name,
    crawl_key,
    dedupe_key,
    expected_key,
    failed_key,
    jsonld_key,
    page_html_key,
    page_meta_key,
    page_stem,
    record_key,
    run_prefix,
    state_key,
)

CATALOG = "catalog-example-edu"
RUN = "2026-09-14T18:12:00Z"
RUN_PATH = "2026-09-14T18-12-00Z"


@pytest.mark.parametrize(
    ("url", "folder"),
    [
        ("https://catalog.atlanticcape.edu/", "catalog-atlanticcape-edu"),
        ("https://catalog.brookdalecc.edu", "catalog-brookdalecc-edu"),
        (
            "https://catalog.bergen.edu/content.php?catoid=13&navoid=664",
            "catalog-bergen-edu-content-php-catoid-13-navoid-664",
        ),
        (
            "https://www.example.edu/academics/catalog/2026-2027/",
            "www-example-edu-academics-catalog-2026-2027",
        ),
        ("HTTP://Catalog.Example.EDU/Courses/#top", "catalog-example-edu-courses"),
    ],
)
def test_catalog_folder_name_examples(url: str, folder: str) -> None:
    assert catalog_folder_name(url) == folder


def test_catalog_folder_name_is_the_same_for_http_and_https() -> None:
    assert catalog_folder_name("http://catalog.example.edu/") == (
        catalog_folder_name("https://catalog.example.edu/")
    )


def test_dedupe_key_drops_scheme_and_fragment_and_keeps_query() -> None:
    assert dedupe_key("HTTP://X.EDU/a?b=1#frag") == "x.edu/a?b=1"
    assert dedupe_key("https://x.edu/a?b=1") == "x.edu/a?b=1"
    assert dedupe_key("https://x.edu") == "x.edu/"
    assert dedupe_key("https://x.edu/") == "x.edu/"
    # A non-default port is part of the identity; 443 on https is not.
    assert dedupe_key("https://x.edu:8443/a") == "x.edu:8443/a"
    assert dedupe_key("https://x.edu:443/a") == "x.edu/a"


def test_page_stem_is_readable_short_and_deterministic() -> None:
    url = "https://catalog.example.edu/english/engl101"
    stem = page_stem(url)
    assert stem == page_stem(url)
    assert stem.startswith("catalog-example-edu-english-engl101-")
    assert len(stem) <= STEM_SLUG_LIMIT + 1 + STEM_DIGEST_LENGTH


def test_page_stem_separates_urls_that_share_the_first_80_characters() -> None:
    """Truncation alone would collide, so the digest carries the difference."""
    shared = "https://catalog.example.edu/programs/" + ("a" * 80)
    first = page_stem(shared + "/one")
    second = page_stem(shared + "/two")
    assert first[:STEM_SLUG_LIMIT] == second[:STEM_SLUG_LIMIT]
    assert first != second
    assert len(first) == STEM_SLUG_LIMIT + 1 + STEM_DIGEST_LENGTH


def test_page_stem_never_ends_the_slug_with_a_hyphen() -> None:
    stem = page_stem("https://catalog.example.edu/" + "a" * 79 + "/x")
    assert "--" not in stem


def test_run_prefix_uses_the_hyphen_form_of_the_run_id() -> None:
    assert run_prefix(CATALOG, RUN) == f"{CATALOG}/{RUN_PATH}"
    assert run_prefix(f"/{CATALOG}/", RUN) == f"{CATALOG}/{RUN_PATH}"
    assert run_prefix(CATALOG, RUN_PATH) == f"{CATALOG}/{RUN_PATH}"


def test_run_object_keys() -> None:
    assert crawl_key(CATALOG, RUN).endswith("/crawl.json")
    assert state_key(CATALOG, RUN).endswith("/state.json")
    assert failed_key(CATALOG, RUN).endswith("/failed.jsonl")
    assert page_html_key(CATALOG, RUN, "stem").endswith("/pages/stem.html")
    assert page_meta_key(CATALOG, RUN, "stem").endswith("/pages/stem.meta.json")
    assert record_key(CATALOG, RUN, "id").endswith("/records/id.json")
    assert jsonld_key(CATALOG, RUN, "id").endswith("/jsonld/id.json")
    assert expected_key(CATALOG, RUN, "id").endswith("/expected/id.json")
    assert "pack" not in crawl_key(CATALOG, RUN)
    assert ".zip" not in crawl_key(CATALOG, RUN)


def test_the_crawler_no_longer_has_slots_or_page_text_keys() -> None:
    from common import keys

    assert not hasattr(keys, "slots_key")
    assert not hasattr(keys, "page_text_key")
