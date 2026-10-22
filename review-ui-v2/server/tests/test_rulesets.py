import json

import pytest

from review_ui.rules import RulesetError
from review_ui.rulesets import (
    PublishError,
    find_ruleset,
    publish_ruleset,
    read_rulesets,
    ruleset_key,
)
from review_ui.store import LocalStore

CCSF = "ccsf-curricunet-com-catalog"


@pytest.fixture
def store(tmp_path):
    return LocalStore(tmp_path)


@pytest.fixture
def known(properties):
    return {p.name for p in properties}


def test_the_key_is_the_catalog_folder_under_review_ui_index_rulesets():
    assert ruleset_key(CCSF) == f"review-ui-index/rulesets/{CCSF}/rules.json"


def test_publishing_writes_the_ruleset_into_the_root(store, known, ruleset):
    assert publish_ruleset(store, ruleset, known) == ruleset_key(CCSF)
    assert store.read_json(ruleset_key(CCSF)) == ruleset


def test_an_invalid_ruleset_is_refused_and_not_written(store, known, ruleset):
    bad = {**ruleset, "content_root": "a[["}
    with pytest.raises(RulesetError, match="content_root"):
        publish_ruleset(store, bad, known)
    assert not store.exists(ruleset_key(CCSF))


def test_the_version_must_go_up(store, known, ruleset):
    publish_ruleset(store, ruleset, known)
    with pytest.raises(PublishError, match="already at version 2"):
        publish_ruleset(store, ruleset, known)  # same version
    with pytest.raises(PublishError):
        publish_ruleset(store, {**ruleset, "version": 1}, known)  # older
    publish_ruleset(store, {**ruleset, "version": 3}, known)
    assert store.read_json(ruleset_key(CCSF))["version"] == 3


def test_force_overrides_the_version_check(store, known, ruleset):
    publish_ruleset(store, ruleset, known)
    publish_ruleset(store, {**ruleset, "version": 1}, known, force=True)
    assert store.read_json(ruleset_key(CCSF))["version"] == 1


def test_read_rulesets_returns_valid_and_invalid_ones(store, known, ruleset):
    publish_ruleset(store, ruleset, known)
    store.write_json(
        "review-ui-index/rulesets/bad/rules.json", {"catalog_folder": "elsewhere"}
    )
    store.write_text("review-ui-index/rulesets/junk/rules.json", "not json")
    store.write_text(
        "review-ui-index/rulesets/README.txt", "ignored: not a ruleset folder"
    )
    found = {p.catalog_folder: p for p in read_rulesets(store, known)}
    assert found[CCSF].ruleset["version"] == 2 and found[CCSF].error is None
    assert (
        found["elsewhere"].ruleset is None and "ruleset_id" in found["elsewhere"].error
    )
    assert found["junk"].ruleset is None and "not valid JSON" in found["junk"].error
    assert set(found) == {CCSF, "elsewhere", "junk"}


def test_find_ruleset_matches_on_the_catalog_folder_inside_the_file(
    store, known, ruleset
):
    store.write_json("review-ui-index/rulesets/any-folder-name/rules.json", ruleset)
    assert find_ruleset(store, CCSF, known).ruleset["ruleset_id"] == CCSF
    assert find_ruleset(store, "nope", known) is None


def test_a_published_file_round_trips_as_json(store, known, ruleset):
    publish_ruleset(store, ruleset, known)
    assert json.loads(store.read_text(ruleset_key(CCSF))) == ruleset
