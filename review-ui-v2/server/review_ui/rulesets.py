"""Rulesets published in the storage root, next to the crawls they apply to:

    <root>/review-ui-index/rulesets/<catalog_folder>/rules.json

The app never reads rulesets from its own files, so a new or changed ruleset reaches a
running (or deployed) app by being written here, with no redeploy.
"""

from __future__ import annotations

from dataclasses import dataclass

from .rules import RulesetError, validate_ruleset
from .store import Store

RULESETS_PREFIX = "review-ui-index/rulesets"


class PublishError(ValueError):
    pass


@dataclass(frozen=True)
class PublishedRuleset:
    key: str  # review-ui-index/rulesets/<dir>/rules.json
    catalog_folder: str
    ruleset: dict | None  # None when the file is invalid
    error: str | None = None


def ruleset_key(catalog_folder: str) -> str:
    return f"{RULESETS_PREFIX}/{catalog_folder}/rules.json"


def read_rulesets(store: Store, known_properties: set[str]) -> list[PublishedRuleset]:
    """Every review-ui-index/rulesets/*/rules.json in the root. An invalid file is returned with its error
    (not skipped), so the landing page can say what is wrong."""
    found = []
    for name in store.list_dir(RULESETS_PREFIX):
        key = f"{RULESETS_PREFIX}/{name}/rules.json"
        if not store.exists(key):
            continue
        folder, ruleset, error = name, None, None
        try:
            raw = store.read_json(key)
            folder = raw.get("catalog_folder", name) if isinstance(raw, dict) else name
            validate_ruleset(raw, known_properties)
            ruleset = raw
        except RulesetError as exc:
            error = str(exc)
        except ValueError as exc:  # not JSON
            error = f"{key} is not valid JSON: {exc}"
        found.append(PublishedRuleset(key, folder, ruleset, error))
    return found


def find_ruleset(
    store: Store, catalog_folder: str, known_properties: set[str]
) -> PublishedRuleset | None:
    for published in read_rulesets(store, known_properties):
        if published.catalog_folder == catalog_folder:
            return published
    return None


def publish_ruleset(
    store: Store, ruleset: dict, known_properties: set[str], force: bool = False
) -> str:
    """Validate and write a ruleset into the root; returns its key.

    The version must be higher than the published one, so an older draft cannot
    overwrite newer rules by accident (``force`` overrides).
    """
    validate_ruleset(
        ruleset, known_properties
    )  # raises RulesetError listing everything
    key = ruleset_key(ruleset["catalog_folder"])
    if store.exists(key) and not force:
        published = store.read_json(key).get("version", 0)
        if ruleset["version"] <= published:
            raise PublishError(
                f"{key} is already at version {published}; the new ruleset is "
                f"version {ruleset['version']}. Raise its version (or use --force)."
            )
    store.write_json(key, ruleset)
    return key
