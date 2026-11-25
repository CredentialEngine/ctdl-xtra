from __future__ import annotations

import pytest

from implementations.crawl_manifest import (
    MANIFEST_SCHEMA,
    LockedScope,
    ManifestError,
    locked_sha256,
    manifest_doc,
    read_locked,
)

SCOPE = LockedScope(
    seed_url="https://catalog.example.edu/",
    scope_prefix="",
    include_regex=("[?&]catoid=13(?!\\d)",),
    exclude_regex=(),
    seed_urls=("https://catalog.example.edu/index.php",),
    strategy="playwright",
)


def _doc(scope: LockedScope = SCOPE, from_run_id: str | None = None) -> dict:
    return manifest_doc(
        catalog_folder="catalog-example-edu",
        run_id="2026-09-17T14:20:01Z",
        created_at="2026-09-17T14:20:01Z",
        from_run_id=from_run_id,
        locked=scope,
        crawl_schema="xtra-crawl-2",
    )


def test_a_manifest_round_trips_and_carries_its_own_hash() -> None:
    doc = _doc()
    assert doc["schema"] == MANIFEST_SCHEMA
    assert doc["locked_sha256"] == locked_sha256(doc["locked"])
    assert read_locked(doc, key="m.json") == SCOPE


def test_no_scope_prefix_is_recorded_as_empty_not_null() -> None:
    assert _doc()["locked"]["scope_prefix"] == ""


def test_the_run_a_manifest_copied_from_is_recorded() -> None:
    assert _doc()["from_run_id"] is None
    copied = _doc(from_run_id="2026-09-16T10:00:00Z")
    assert copied["from_run_id"] == "2026-09-16T10:00:00Z"


def test_a_manifest_changed_after_it_was_written_is_refused() -> None:
    doc = _doc()
    doc["locked"]["include_regex"] = ["anything"]
    with pytest.raises(ManifestError, match="changed after it was written"):
        read_locked(doc, key="m.json")


@pytest.mark.parametrize(
    "doc",
    [
        None,
        [],
        {"schema": "something-else"},
        {"schema": MANIFEST_SCHEMA},
        {"schema": MANIFEST_SCHEMA, "locked": "not a dict"},
    ],
)
def test_a_document_that_is_not_a_manifest_is_refused(doc) -> None:
    with pytest.raises(ManifestError):
        read_locked(doc, key="m.json")


def test_the_resume_comparison_is_gone() -> None:
    from implementations import crawl_manifest

    for name in (
        "ManifestMismatchError",
        "legacy_differences",
        "mismatch_message",
        "CREATED_FOR_EXISTING_RUN",
    ):
        assert not hasattr(crawl_manifest, name), name
    assert not hasattr(SCOPE, "differences")
