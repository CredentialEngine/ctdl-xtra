from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

MANIFEST_SCHEMA = "xtra-crawl-manifest-1"


class ManifestError(RuntimeError):
    """The run's manifest cannot be trusted, so the run does not start."""


class RunExistsError(ManifestError):
    """The run id names a run that has already started."""


@dataclass(frozen=True)
class LockedScope:
    """The settings that decide which pages belong to a run."""

    seed_url: str
    scope_prefix: str
    include_regex: tuple[str, ...]
    exclude_regex: tuple[str, ...]
    seed_urls: tuple[str, ...]
    strategy: str

    def to_json(self) -> dict[str, Any]:
        return {
            "seed_url": self.seed_url,
            "scope_prefix": self.scope_prefix,
            "include_regex": list(self.include_regex),
            "exclude_regex": list(self.exclude_regex),
            "seed_urls": list(self.seed_urls),
            "strategy": self.strategy,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> LockedScope:
        return cls(
            seed_url=str(data["seed_url"]),
            scope_prefix=str(data.get("scope_prefix") or ""),
            include_regex=tuple(data.get("include_regex") or ()),
            exclude_regex=tuple(data.get("exclude_regex") or ()),
            seed_urls=tuple(data.get("seed_urls") or ()),
            strategy=str(data["strategy"]),
        )


def locked_sha256(locked: dict[str, Any]) -> str:
    canonical = json.dumps(
        locked, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def manifest_doc(
    *,
    catalog_folder: str,
    run_id: str,
    created_at: str,
    from_run_id: str | None,
    locked: LockedScope,
    crawl_schema: str,
) -> dict[str, Any]:
    locked_json = locked.to_json()
    return {
        "schema": MANIFEST_SCHEMA,
        "catalog_folder": catalog_folder,
        "run_id": run_id,
        "created_at": created_at,
        "from_run_id": from_run_id,
        "crawl_schema": crawl_schema,
        "locked": locked_json,
        "locked_sha256": locked_sha256(locked_json),
    }


def read_locked(doc: Any, *, key: str) -> LockedScope:
    """The locked scope of a stored manifest, refusing one that was altered."""
    if not isinstance(doc, dict) or doc.get("schema") != MANIFEST_SCHEMA:
        raise ManifestError(f"{key} is not an {MANIFEST_SCHEMA} manifest.")
    locked = doc.get("locked")
    if not isinstance(locked, dict):
        raise ManifestError(f"{key} has no locked scope.")
    if locked_sha256(locked) != doc.get("locked_sha256"):
        raise ManifestError(
            f"{key} was changed after it was written: its locked scope no "
            "longer matches locked_sha256."
        )
    try:
        return LockedScope.from_json(locked)
    except (KeyError, TypeError, ValueError) as exc:
        raise ManifestError(
            f"{key} has an unreadable locked scope: {exc}"
        ) from exc
